"""Small offline checks covering the boundaries most likely to corrupt team data."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from scripts.course_explorer import CourseExplorerClient, extract_relationships
from scripts.collect_campus import collect, department_snapshot
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import API_BASE, DataError, RequestError, atomic_write_json, validate_snapshot
from scripts.integration import publish_bundle

from tests.fixtures import FIXTURES, FIXTURE_TIME, FixtureClient, RecordingClient, archive_fixture, fixture_snapshot


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture_snapshot()

    def test_separate_sections_and_meeting_instructor_relationships(self):
        sections = {section["crn"]: section for section in self.snapshot["sections"]}
        self.assertEqual(set(sections), {"10001", "10002", "10003", "20001"})
        self.assertEqual(sections["10001"]["id"], "2026-fall:10001")
        lecture, lab = sections["10001"]["meetings"]
        self.assertEqual([person["name_raw"] for person in lecture["instructors"]], ["Example, Alex", "Example, Blair"])
        self.assertEqual([person["name_raw"] for person in lab["instructors"]], ["Example, Casey"])
        self.assertEqual(lecture["type"], {"code": "LEC", "label": "Lecture"})
        self.assertEqual(lab["type"]["code"], "LAB")
        self.assertEqual(sections["10002"]["meetings"][0]["type"]["code"], "DIS")
        self.assertTrue(all(person["professor_id"] is None for person in lecture["instructors"]))

    def test_empty_and_absent_instructor_lists_are_preserved(self):
        empty = self.snapshot["sections"][1]["meetings"][0]
        missing = self.snapshot["sections"][2]["meetings"][0]
        self.assertEqual((empty["instructors"], empty["instructor_list_status"]), ([], "empty"))
        self.assertEqual((missing["instructors"], missing["instructor_list_status"]), ([], "missing"))

    def test_cross_listings_retain_registration_records_and_explicit_evidence(self):
        cs, ece = self.snapshot["courses"]
        self.assertTrue(set(cs["section_ids"]).isdisjoint(ece["section_ids"]))
        relationships = self.snapshot["relationships"]
        self.assertEqual(len(relationships), 3)
        cs_alias = next(item for item in relationships if item["from_listing_id"].endswith("CS 374"))
        self.assertEqual(cs_alias["to_listing_id"], "2026-fall:ECE 374")
        self.assertEqual(cs_alias["evidence"][0]["text"], "Same as ECE 374.")
        self.assertTrue(any(item["relation"] == "see" for item in relationships))

    def test_same_schedule_and_prerequisites_do_not_create_aliases(self):
        courses = deepcopy(self.snapshot["courses"])
        for course in courses:
            course["description"] = "Prerequisite: CS 374 and ECE 374. See CS 225 for preparation advice. Prerequisite: See CS 374."
            course["course_section_information"] = ""
        self.assertEqual(extract_relationships(courses), [])

    def test_incomplete_detail_response_is_rejected(self):
        class IncompleteClient(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                if "CS.xml?mode=cascade" in url:
                    response["body"] = response["body"].replace('detailedSections', 'missingSections')
                return response
        discovery = CourseExplorerDiscovery(IncompleteClient())
        term, _ = discovery.term(2026, 'fall')
        with self.assertRaisesRegex(DataError, "Missing detailedSections"):
            department_snapshot(discovery, term, 'CS')

    def test_crn_cannot_be_used_without_term(self):
        self.snapshot["sections"][0]["id"] = "10001"
        with self.assertRaisesRegex(DataError, "term \+ CRN"):
            validate_snapshot(self.snapshot)

    def test_repeated_crns_in_different_terms_have_different_ids(self):
        spring = fixture_snapshot(2025, "spring")
        self.assertEqual(spring["sections"][0]["crn"], self.snapshot["sections"][0]["crn"])
        self.assertEqual(spring["sections"][0]["id"], "2025-spring:10001")
        self.assertNotEqual(spring["sections"][0]["id"], self.snapshot["sections"][0]["id"])


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.history = archive_fixture()

    def test_failed_refresh_preserves_candidate_and_published_bytes_and_timestamps(self):
        class FailingClient(FixtureClient):
            def fetch(self, url, **kwargs):
                if "ECE.xml?mode=cascade" in url:
                    raise DataError("Simulated exhausted timeout")
                return super().fetch(url, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "public" / "integration.json"
            atomic_write_json(candidate, fixture_snapshot())
            publish_bundle(public.parent, json.loads(candidate.read_text()), self.history, allow_fixtures=True)
            candidate_before, public_before = candidate.read_bytes(), public.read_bytes()
            with self.assertRaisesRegex(DataError, "exhausted timeout"):
                collect(FailingClient(), "2026-fall", candidate)
            self.assertEqual(candidate.read_bytes(), candidate_before)
            self.assertEqual(public.read_bytes(), public_before)
            self.assertEqual(json.loads(public.read_text())["collected_at"], FIXTURE_TIME)

    def test_failed_batch_responses_preserve_candidate_and_report_errors(self):
        for failure in ('malformed_xml', 'missing_course', 'duplicate_crn', 'http_404'):
            class BrokenBatch(FixtureClient):
                def fetch(self, url, **kwargs):
                    response = super().fetch(url, **kwargs)
                    if url.endswith('ECE.xml?mode=cascade'):
                        if failure == 'http_404':
                            raise RequestError('HTTP 404 after successful department discovery')
                        if failure == 'malformed_xml':
                            response['body'] = '<subject>'
                        elif failure == 'missing_course':
                            response['body'] = response['body'].replace('id="ECE 374"', 'id="ECE 999"')
                        else:
                            response['body'] = response['body'].replace('20001', '10001')
                    return response
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                candidate = Path(directory)/'candidate.json'
                atomic_write_json(candidate, fixture_snapshot())
                before = candidate.read_bytes()
                with self.assertRaises(DataError):
                    collect(BrokenBatch(), '2026-fall', candidate)
                self.assertEqual(candidate.read_bytes(), before)
                report = json.loads(candidate.with_suffix('.coverage.json').read_text())
                # Cross-department collisions are rejected at final merged validation.
                if failure != 'duplicate_crn':
                    self.assertEqual(report['departments'][-1]['status'], 'error')
                    self.assertNotIn('unavailable', [row['status'] for row in report['departments']])

    def test_invalid_candidate_cannot_replace_published_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "public" / "integration.json"
            atomic_write_json(candidate, fixture_snapshot())
            publish_bundle(public.parent, json.loads(candidate.read_text()), self.history, allow_fixtures=True)
            original = public.read_bytes()
            candidate.write_text('{"schema_version": 999}')
            with self.assertRaises(DataError):
                publish_bundle(public.parent, json.loads(candidate.read_text()), self.history, allow_fixtures=True)
            self.assertEqual(public.read_bytes(), original)

    def test_fixture_publication_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "public" / "integration.json"
            atomic_write_json(candidate, fixture_snapshot())
            with self.assertRaisesRegex(DataError, "Synthetic"):
                publish_bundle(public.parent, json.loads(candidate.read_text()), self.history,
                               coverage=self.history['department_coverage']['2026-fall'])
            self.assertFalse(public.exists())

    def test_replace_failure_leaves_old_file_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "published.json"
            public.write_text("last successful snapshot")
            with patch("scripts.data_contract.os.replace", side_effect=OSError("Simulated disk failure")):
                with self.assertRaises(OSError):
                    atomic_write_json(public, fixture_snapshot())
            self.assertEqual(public.read_text(), "last successful snapshot")
            self.assertEqual(list(Path(directory).iterdir()), [public])


class HttpClientTests(unittest.TestCase):
    url = f"{API_BASE}/2026/fall/CS/374.xml"

    def test_transient_requests_have_timeouts_and_bounded_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            client = CourseExplorerClient(directory, timeout=3, retries=2)
            with patch("scripts.course_explorer.urlopen", side_effect=URLError("timeout")) as request, patch("scripts.course_explorer.time.sleep"):
                with self.assertRaises(DataError):
                    client.fetch(self.url)
                self.assertEqual(request.call_count, 3)
                self.assertTrue(all(call.kwargs["timeout"] == 3 for call in request.call_args_list))

    def test_404_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.course_explorer.urlopen", side_effect=HTTPError(self.url, 404, "Missing", {}, None)) as request:
                with self.assertRaises(DataError):
                    CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 1)

    def test_429_can_retry_and_succeed(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = (FIXTURES / "cs-detail.xml").read_bytes()
            limited = HTTPError(self.url, 429, "Rate limited", {}, None)
            with patch("scripts.course_explorer.urlopen", side_effect=[limited, response]) as request, patch("scripts.course_explorer.time.sleep") as sleep:
                result = CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 2)
                sleep.assert_any_call(1)
                self.assertEqual(result["url"], self.url)

    def test_html_response_is_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = b"<html>Service unavailable</html>"
            with patch("scripts.course_explorer.urlopen", return_value=response):
                with self.assertRaisesRegex(DataError, "Expected course XML"):
                    CourseExplorerClient(directory).fetch(self.url)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cache_retains_fetch_timestamp_and_refresh_does_not_use_stale_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = (FIXTURES / "cs-detail.xml").read_bytes()
            with patch("scripts.course_explorer.urlopen", return_value=response) as request:
                first = CourseExplorerClient(directory).fetch(self.url)
                cached = CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(cached, first)
            with patch("scripts.course_explorer.urlopen", side_effect=URLError("offline")):
                with self.assertRaises(DataError):
                    CourseExplorerClient(directory, retries=0, cache_ttl=0).fetch(self.url)
            saved = json.loads(next(Path(directory).glob("*.json")).read_text())
            self.assertEqual(saved["fetched_at"], first["fetched_at"])


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
        with self.assertRaises(DataError):
            CourseExplorerDiscovery(BrokenIndex()).term(2026, "fall")


class HistoricalCacheTests(unittest.TestCase):
    def test_history_uses_longer_cache_and_refresh_still_fails_without_network(self):
        url = API_BASE + "/2025/spring/CS/374.xml"
        fetched_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / (hashlib.sha256(url.encode()).hexdigest() + ".json")
            atomic_write_json(cache, {"url": url, "fetched_at": fetched_at, "body": (FIXTURES / "cs-detail.xml").read_text()})
            with patch("scripts.course_explorer.urlopen", side_effect=URLError("offline")) as request:
                response = CourseExplorerClient(directory, retries=0, cache_ttl=60).fetch(url, historical=True)
                self.assertEqual(response["fetched_at"], fetched_at)
                request.assert_not_called()
                with self.assertRaises(RequestError):
                    CourseExplorerClient(directory, retries=0, cache_ttl=0).fetch(url, historical=True)
            self.assertEqual(json.loads(cache.read_text())["fetched_at"], fetched_at)


if __name__ == "__main__":
    unittest.main()
