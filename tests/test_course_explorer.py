"""Small offline checks covering the boundaries most likely to corrupt team data."""

from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from scripts.collect_course_explorer import CourseExplorerClient, build_snapshot, collect_to_file, extract_relationships
from scripts.data_contract import API_BASE, DataError, atomic_write_json, validate_snapshot
from scripts.publish_data import publish

FIXTURES = Path(__file__).resolve().parents[1] / "data/examples/course-explorer-xml"
FIXTURE_TIME = "2026-01-01T00:00:00Z"


class FixtureClient:
    def fetch(self, url, expected_root="course", **kwargs):
        discovery_dir = FIXTURES.parent / "discovery-xml"
        if expected_root == "schedule":
            file = discovery_dir / "schedule.xml"
        elif expected_root == "calendarYear":
            file = discovery_dir / f'year-{url.rsplit("/", 1)[-1]}'
        elif expected_root == "term":
            file = discovery_dir / "term.xml"
        elif expected_root == "subject":
            file = discovery_dir / f'subject-{url.rsplit("/", 1)[-1].lower()}'
        else:
            subject = url.split("/")[-2].lower()
            suffix = "detail" if "?mode=detail" in url else "index"
            file = FIXTURES / f"{subject}-{suffix}.xml"
        body = file.read_text()
        match = re.search(r"/schedule/(\d{4})/(spring|fall)", url)
        if match:
            year, season = match.groups()
            source_term_id = f'1{year}{"1" if season == "spring" else "8"}'
            body = body.replace('/2026/fall', f'/{year}/{season}').replace('/2026.xml', f'/{year}.xml').replace('Fall 2026', f'{season.title()} {year}').replace('id="2026"', f'id="{year}"').replace('id="120268"', f'id="{source_term_id}"')
        return {"url": url, "fetched_at": FIXTURE_TIME, "body": body}


def fixture_snapshot():
    return build_snapshot(FixtureClient(), 2026, "fall", ["CS 374", "ECE 374"], data_kind="development_fixture")


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
                if "CS/374.xml?" in url:
                    response["body"] = response["body"].replace('id="10003"', 'id="99999"')
                return response
        with self.assertRaisesRegex(DataError, "Incomplete detailed"):
            build_snapshot(IncompleteClient(), 2026, "fall", ["CS 374"])

    def test_crn_cannot_be_used_without_term(self):
        self.snapshot["sections"][0]["id"] = "10001"
        with self.assertRaisesRegex(DataError, "term \+ CRN"):
            validate_snapshot(self.snapshot)

    def test_repeated_crns_in_different_terms_have_different_ids(self):
        class SpringClient(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                response["body"] = response["body"].replace("/2026/fall", "/2026/spring").replace("Fall 2026", "Spring 2026").replace('id="120268"', 'id="120261"')
                return response
        spring = build_snapshot(SpringClient(), 2026, "spring", ["CS 374", "ECE 374"], data_kind="development_fixture")
        self.assertEqual(spring["sections"][0]["crn"], self.snapshot["sections"][0]["crn"])
        self.assertEqual(spring["sections"][0]["id"], "2026-spring:10001")
        self.assertNotEqual(spring["sections"][0]["id"], self.snapshot["sections"][0]["id"])


class PreservationTests(unittest.TestCase):
    def test_failed_refresh_preserves_candidate_and_published_bytes_and_timestamps(self):
        class FailingClient(FixtureClient):
            def fetch(self, url, **kwargs):
                if "ECE/374.xml?" in url:
                    raise DataError("Simulated exhausted timeout")
                return super().fetch(url, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "published.json"
            atomic_write_json(candidate, fixture_snapshot())
            publish(candidate, public, allow_fixtures=True)
            candidate_before, public_before = candidate.read_bytes(), public.read_bytes()
            with self.assertRaisesRegex(DataError, "exhausted timeout"):
                collect_to_file(FailingClient(), 2026, "fall", ["CS 374", "ECE 374"], candidate)
            self.assertEqual(candidate.read_bytes(), candidate_before)
            self.assertEqual(public.read_bytes(), public_before)
            self.assertEqual(json.loads(public.read_text())["collected_at"], FIXTURE_TIME)

    def test_invalid_candidate_cannot_replace_published_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "published.json"
            atomic_write_json(candidate, fixture_snapshot())
            publish(candidate, public, allow_fixtures=True)
            original = public.read_bytes()
            candidate.write_text('{"schema_version": 999}')
            with self.assertRaises(DataError):
                publish(candidate, public, allow_fixtures=True)
            self.assertEqual(public.read_bytes(), original)

    def test_fixture_publication_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, public = Path(directory) / "candidate.json", Path(directory) / "published.json"
            atomic_write_json(candidate, fixture_snapshot())
            with self.assertRaisesRegex(DataError, "allow-fixtures"):
                publish(candidate, public)
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
            with patch("scripts.collect_course_explorer.urlopen", side_effect=URLError("timeout")) as request, patch("scripts.collect_course_explorer.time.sleep"):
                with self.assertRaises(DataError):
                    client.fetch(self.url)
                self.assertEqual(request.call_count, 3)
                self.assertTrue(all(call.kwargs["timeout"] == 3 for call in request.call_args_list))

    def test_404_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.collect_course_explorer.urlopen", side_effect=HTTPError(self.url, 404, "Missing", {}, None)) as request:
                with self.assertRaises(DataError):
                    CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 1)

    def test_429_can_retry_and_succeed(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = (FIXTURES / "cs-index.xml").read_bytes()
            limited = HTTPError(self.url, 429, "Rate limited", {}, None)
            with patch("scripts.collect_course_explorer.urlopen", side_effect=[limited, response]) as request, patch("scripts.collect_course_explorer.time.sleep") as sleep:
                result = CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 2)
                sleep.assert_any_call(1)
                self.assertEqual(result["url"], self.url)

    def test_html_response_is_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b"<html>Service unavailable</html>"
            with patch("scripts.collect_course_explorer.urlopen", return_value=response):
                with self.assertRaisesRegex(DataError, "Expected course XML"):
                    CourseExplorerClient(directory).fetch(self.url)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cache_retains_fetch_timestamp_and_refresh_does_not_use_stale_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = (FIXTURES / "cs-index.xml").read_bytes()
            with patch("scripts.collect_course_explorer.urlopen", return_value=response) as request:
                first = CourseExplorerClient(directory).fetch(self.url)
                cached = CourseExplorerClient(directory).fetch(self.url)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(cached, first)
            with patch("scripts.collect_course_explorer.urlopen", side_effect=URLError("offline")):
                with self.assertRaises(DataError):
                    CourseExplorerClient(directory, retries=0, cache_ttl=0).fetch(self.url)
            saved = json.loads(next(Path(directory).glob("*.json")).read_text())
            self.assertEqual(saved["fetched_at"], first["fetched_at"])


if __name__ == "__main__":
    unittest.main()
