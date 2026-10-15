"""Discovery, multi-term coverage, and whole-bundle failure preservation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts.collect_course_explorer import CourseExplorerClient
from scripts.collect_teaching_history import collect_history_to_file
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import API_BASE, DataError, RequestError, atomic_write_json
from scripts.integration import publish_bundle
from scripts.teaching_history import build_history, render_report, validate_history
from tests.test_course_explorer import FIXTURES, FIXTURE_TIME, FixtureClient, fixture_snapshot

TERMS = ["2026-fall", "2025-spring"]
COURSES = ["CS 374", "ECE 374"]


class RecordingClient(FixtureClient):
    def __init__(self):
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        return super().fetch(url, **kwargs)


def history_fixture():
    return build_history(FixtureClient(), TERMS, COURSES, "development_fixture")


class DiscoveryTests(unittest.TestCase):
    def test_year_and_term_indexes_are_discovered(self):
        client = RecordingClient()
        discovery = CourseExplorerDiscovery(client)
        term, evidence = discovery.term(2025, "spring")
        self.assertEqual(term["source_term_id"], "120251")
        self.assertEqual(evidence["source_url"], API_BASE + "/2025.xml")
        discovery.term(2025, "spring")
        self.assertEqual(client.calls.count(API_BASE + ".xml"), 1)
        self.assertEqual(client.calls.count(API_BASE + "/2025.xml"), 1)

    def test_unlisted_year_and_term_are_not_guessed_or_requested(self):
        client = RecordingClient()
        discovery = CourseExplorerDiscovery(client)
        term, evidence = discovery.term(2024, "fall")
        self.assertIsNone(term)
        self.assertEqual(evidence["reason"], "year_not_listed")
        self.assertNotIn(API_BASE + "/2024.xml", client.calls)
        term, evidence = discovery.term(2026, "spring")
        self.assertIsNone(term)
        self.assertEqual(evidence["reason"], "term_not_listed")
        self.assertNotIn(API_BASE + "/2026/spring.xml", client.calls)

    def test_unlisted_course_and_subject_are_unavailable_with_index_evidence(self):
        client = RecordingClient()
        discovery = CourseExplorerDiscovery(client)
        term, _ = discovery.term(2026, "fall")
        available, evidence = discovery.course(term, "CS 999")
        self.assertFalse(available)
        self.assertEqual(evidence["reason"], "course_not_listed")
        self.assertTrue(evidence["source_url"].endswith("/CS.xml"))
        available, evidence = discovery.course(term, "STAT 107")
        self.assertFalse(available)
        self.assertEqual(evidence["reason"], "subject_not_listed")
        self.assertNotIn(API_BASE + "/2026/fall/STAT.xml", client.calls)

    def test_missing_index_container_is_a_failure_not_unavailability(self):
        class BrokenIndex(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                if url.endswith("/2026.xml"):
                    response["body"] = response["body"].replace("<terms>", "<broken>").replace("</terms>", "</broken>")
                return response
        attempt = build_history(BrokenIndex(), ["2026-fall"], COURSES, "development_fixture")
        self.assertEqual(attempt["coverage"]["totals"]["error_course_terms"], 2)
        self.assertEqual(attempt["coverage"]["totals"]["unavailable_course_terms"], 0)
        self.assertEqual(attempt["coverage"]["courses"][0]["error_kind"], "validation")
        with self.assertRaises(DataError):
            validate_history(attempt)


class HistoryTests(unittest.TestCase):
    def test_multi_term_bundle_preserves_v1_snapshots_and_roles(self):
        history = history_fixture()
        self.assertEqual([snapshot["term"]["id"] for snapshot in history["snapshots"]], TERMS)
        first, second = history["snapshots"]
        self.assertEqual(first["sections"][0]["crn"], second["sections"][0]["crn"])
        self.assertNotEqual(first["sections"][0]["id"], second["sections"][0]["id"])
        totals = history["coverage"]["totals"]
        self.assertEqual((totals["section_count"], totals["meeting_count"]), (8, 10))
        self.assertEqual(totals["missing_instructor_meetings"], 4)
        self.assertEqual(totals["multiple_instructor_meetings"], 4)
        self.assertEqual(totals["unresolved_occurrences"], 10)
        self.assertEqual(totals["meeting_types"], {"DIS": 2, "LAB": 4, "LEC": 4})
        self.assertEqual(first["relationships"][0]["to_listing_id"], "2026-fall:ECE 374")
        self.assertEqual(first["sections"][0]["meetings"][0]["instructors"][0]["name_raw"], "Example, Alex")
        self.assertIn("not unique people", render_report(history))

    def test_confirmed_unavailable_pairs_are_complete_explicit_coverage(self):
        history = build_history(FixtureClient(), ["2026-fall", "2026-spring"], ["CS 374", "CS 999", "STAT 107"], "development_fixture")
        totals = history["coverage"]["totals"]
        self.assertEqual((totals["requested_course_terms"], totals["collected_course_terms"], totals["unavailable_course_terms"]), (6, 1, 5))
        self.assertEqual(totals["error_course_terms"], 0)
        self.assertEqual(history["snapshots"][0]["requested_courses"], ["CS 374"])
        validate_history(history)

    def test_all_unavailable_can_be_reported_without_fake_empty_v1_snapshot(self):
        history = build_history(FixtureClient(), ["2024-fall"], COURSES, "development_fixture")
        self.assertEqual(history["snapshots"], [])
        self.assertEqual(history["coverage"]["totals"]["unavailable_course_terms"], 2)
        validate_history(history)

    def test_tampered_counts_missing_pairs_and_missing_evidence_fail_validation(self):
        history = history_fixture()
        for mutate in (
            lambda data: data["coverage"]["courses"][0].update(section_count=999),
            lambda data: data["coverage"]["courses"].pop(),
            lambda data: data["coverage"]["terms"][0].update(source_url="https://example.org/"),
        ):
            with self.subTest(mutate=mutate):
                invalid = deepcopy(history)
                mutate(invalid)
                with self.assertRaises(DataError):
                    validate_history(invalid)

    def test_http_404_after_positive_discovery_is_a_request_error(self):
        class MissingAfterIndex(FixtureClient):
            def fetch(self, url, **kwargs):
                if url.endswith("/ECE/374.xml?mode=detail"):
                    raise RequestError("Request failed: HTTP 404")
                return super().fetch(url, **kwargs)
        attempt = build_history(MissingAfterIndex(), ["2026-fall"], COURSES, "development_fixture")
        row = attempt["coverage"]["courses"][1]
        self.assertEqual((row["status"], row["error_kind"]), ("error", "request"))
        self.assertEqual(attempt["coverage"]["totals"]["unavailable_course_terms"], 0)

    def test_cross_listing_crn_collision_is_reported_as_validation_failure(self):
        class ConflictingSections(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                if "/ECE/374.xml" in url:
                    response["body"] = response["body"].replace('id="20001"', 'id="10001"').replace('/20001.xml', '/10001.xml')
                return response
        attempt = build_history(ConflictingSections(), ["2026-fall"], COURSES, "development_fixture")
        self.assertEqual(attempt["snapshots"], [])
        self.assertEqual(attempt["coverage"]["totals"]["error_course_terms"], 2)
        self.assertIn("Duplicate section ID", render_report(attempt))
        with self.assertRaises(DataError):
            validate_history(attempt)

    def test_late_failure_preserves_entire_candidate_and_published_bundle(self):
        class LateFailure(FixtureClient):
            def fetch(self, url, **kwargs):
                if "/2025/spring/ECE/374.xml?" in url:
                    raise RequestError("Simulated exhausted network timeout")
                return super().fetch(url, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            candidate, public, report = [Path(directory) / filename for filename in ("candidate.json", "public/integration.json", "attempt.md")]
            atomic_write_json(candidate, history_fixture())
            publish_bundle(public.parent, fixture_snapshot(), json.loads(candidate.read_text()), allow_fixtures=True)
            candidate_before, public_before = candidate.read_bytes(), public.read_bytes()
            with self.assertRaises(DataError):
                collect_history_to_file(LateFailure(), TERMS, COURSES, candidate, report, "development_fixture")
            self.assertEqual(candidate.read_bytes(), candidate_before)
            self.assertEqual(public.read_bytes(), public_before)
            self.assertIn("FAILED ATTEMPT", report.read_text())
            self.assertIn("request", report.read_text())
            self.assertEqual(json.loads(public.read_text())["collected_at"], FIXTURE_TIME)

    def test_parse_failure_is_reported_and_not_saved_as_a_candidate(self):
        class BadDetail(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                if "?mode=detail" in url:
                    response["body"] = "<course>"
                return response
        with tempfile.TemporaryDirectory() as directory:
            candidate, report = Path(directory) / "candidate.json", Path(directory) / "report.md"
            with self.assertRaises(DataError):
                collect_history_to_file(BadDetail(), TERMS, COURSES, candidate, report, "development_fixture")
            self.assertFalse(candidate.exists())
            self.assertIn("validation", report.read_text())

    def test_invalid_history_cannot_replace_previous_published_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "public/integration.json"
            history = history_fixture()
            atomic_write_json(candidate, history)
            publish_bundle(public.parent, fixture_snapshot(), json.loads(candidate.read_text()), allow_fixtures=True)
            original = public.read_bytes()
            history["coverage"]["totals"]["unresolved_occurrences"] = 0
            atomic_write_json(candidate, history)
            with self.assertRaises(DataError):
                publish_bundle(public.parent, fixture_snapshot(), json.loads(candidate.read_text()), allow_fixtures=True)
            self.assertEqual(public.read_bytes(), original)


class HistoricalCacheTests(unittest.TestCase):
    def test_history_uses_longer_cache_and_refresh_still_fails_without_network(self):
        url = API_BASE + "/2025/spring/CS/374.xml"
        fetched_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / (hashlib.sha256(url.encode()).hexdigest() + ".json")
            atomic_write_json(cache, {"url": url, "fetched_at": fetched_at, "body": (FIXTURES / "cs-index.xml").read_text()})
            with patch("scripts.collect_course_explorer.urlopen", side_effect=URLError("offline")) as request:
                response = CourseExplorerClient(directory, retries=0, cache_ttl=60).fetch(url, historical=True)
                self.assertEqual(response["fetched_at"], fetched_at)
                request.assert_not_called()
                with self.assertRaises(RequestError):
                    CourseExplorerClient(directory, retries=0, cache_ttl=0).fetch(url, historical=True)
            self.assertEqual(json.loads(cache.read_text())["fetched_at"], fetched_at)


if __name__ == "__main__":
    unittest.main()
