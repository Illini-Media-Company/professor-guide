"""Discover years, terms, subjects, and courses from official XML indexes."""

import argparse
from datetime import datetime, timezone
import re
import sys
import xml.etree.ElementTree as ET

from scripts.data_contract import API_BASE, TERMS, DataError, require


def parse_xml(body, expected_root="course"):
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise DataError(f"Invalid XML: {error}") from error
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    require(root.tag == expected_root, f"Expected {expected_root} XML, got {root.tag}")
    return root


def historical_year(year):
    # A conservative cache policy; current-year terms retain the short TTL.
    return year < datetime.now(timezone.utc).year


class CourseExplorerDiscovery:
    def __init__(self, client):
        self.client = client
        self.sources = {}
        self.responses = {}

    def read(self, url, root_tag, historical=False):
        if url not in self.responses:
            response = self.client.fetch(url, expected_root=root_tag, historical=historical)
            self.responses[url] = (parse_xml(response["body"], root_tag), response["fetched_at"])
            self.sources[url] = {"url": url, "fetched_at": response["fetched_at"]}
        return self.responses[url]

    @staticmethod
    def entries(root, container_name, child_name):
        container = root.find(container_name)
        require(container is not None, f"Missing {container_name} index container")
        entries = list(container)
        require(all(entry.tag == child_name for entry in entries), "Unexpected index entry")
        identifiers = [entry.get("id") for entry in entries]
        require(all(identifiers) and len(set(identifiers)) == len(identifiers), "Missing/duplicate index IDs")
        return entries

    def years(self):
        root, fetched_at = self.read(API_BASE + ".xml", "schedule")
        years = []
        for entry in self.entries(root, "calendarYears", "calendarYear"):
            identifier = entry.get("id")
            require(bool(re.fullmatch(r"\d{4}", identifier)), "Invalid calendar year")
            require(entry.get("href") == f"{API_BASE}/{identifier}.xml", "Year index URL mismatch")
            years.append(int(identifier))
        require(years, "Empty calendar year index")
        return years, fetched_at

    def terms(self, year):
        years, root_time = self.years()
        if year not in years:
            return {}, {"source_url": API_BASE + ".xml", "checked_at": root_time, "reason": "year_not_listed"}
        url = f"{API_BASE}/{year}.xml"
        root, fetched_at = self.read(url, "calendarYear", historical=historical_year(year))
        require(root.get("id") == str(year), "Year index ID mismatch")
        terms = {}
        for entry in self.entries(root, "terms", "term"):
            href = entry.get("href", "")
            season = href.removeprefix(f"{API_BASE}/{year}/").removesuffix(".xml")
            require(season in TERMS and href == f"{API_BASE}/{year}/{season}.xml", "Unexpected term index URL")
            require(season not in terms, "Duplicate term season")
            require(entry.text and entry.text.strip(), "Missing term label")
            terms[season] = {
                "id": f"{year}-{season}", "year": year, "season": season,
                "source_term_id": entry.get("id"), "label": entry.text.strip(),
            }
        return terms, {"source_url": url, "checked_at": fetched_at, "reason": "term_not_listed"}

    def term(self, year, season):
        terms, evidence = self.terms(year)
        if season not in terms:
            return None, evidence
        return terms[season], {**evidence, "reason": "term_listed"}

    def course(self, term, code):
        """Absence in a valid parent index is unavailable; request failures raise."""
        year, season = term["year"], term["season"]
        subject, number = code.split()
        term_url = f"{API_BASE}/{year}/{season}.xml"
        root, fetched_at = self.read(term_url, "term", historical=historical_year(year))
        calendar = root.find("parents/calendarYear")
        require(root.get("id") == term["source_term_id"], "Term index ID mismatch")
        require(calendar is not None and calendar.get("id") == str(year), "Term index year mismatch")
        subjects = {}
        for entry in self.entries(root, "subjects", "subject"):
            identifier = entry.get("id")
            require(entry.get("href") == f"{API_BASE}/{year}/{season}/{identifier}.xml", "Subject index URL mismatch")
            subjects[identifier] = entry.get("href")
        if subject not in subjects:
            return False, {"source_url": term_url, "checked_at": fetched_at, "reason": "subject_not_listed"}
        url = subjects[subject]
        root, fetched_at = self.read(url, "subject", historical=historical_year(year))
        calendar, source_term = root.find("parents/calendarYear"), root.find("parents/term")
        require(root.get("id") == subject, "Subject index ID mismatch")
        require(calendar is not None and calendar.get("id") == str(year), "Subject index year mismatch")
        require(source_term is not None and source_term.get("id") == term["source_term_id"] and source_term.get("href") == term_url, "Subject index term mismatch")
        courses = {}
        for entry in self.entries(root, "courses", "course"):
            identifier = entry.get("id")
            require(entry.get("href") == f"{API_BASE}/{year}/{season}/{subject}/{identifier}.xml", "Course index URL mismatch")
            courses[identifier] = entry.get("href")
        available = number in courses
        return available, {"source_url": url, "checked_at": fetched_at, "reason": "course_listed" if available else "course_not_listed"}


def main():
    # Imported here to keep discovery independent of transport/parser orchestration.
    from scripts.collect_course_explorer import CourseExplorerClient, add_client_arguments

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True)
    add_client_arguments(parser)
    args = parser.parse_args()
    try:
        discovery = CourseExplorerDiscovery(CourseExplorerClient.from_args(args))
        for year in args.years:
            require(1900 <= year <= 2200, "Invalid year")
            terms, evidence = discovery.terms(year)
            print(f'{year}: {", ".join(term["id"] for term in terms.values()) or "not listed"}')
            print(f'  {evidence["source_url"]} (fetched {evidence["checked_at"]})')
    except (DataError, OSError) as error:
        print(f"Discovery failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
