"""Validated teammate inputs and a hash-addressed, manifest-last publication."""

import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import warnings

from scripts.data_contract import DataError, atomic_write_text, require, timestamp, validate_document
from scripts.teaching_history import counts


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def provenance(data):
    require(data["schema_version"] == 1, "Unsupported teammate schema")
    require(data["data_kind"] in ("live", "development_fixture"), "Invalid data kind")
    timestamp(data["collected_at"])
    require(isinstance(data["records"], list), "Records must be a list")
    require(data["sources"], "Sources are required")
    for source in data["sources"]:
        require(source["url"].startswith("https://"), "HTTPS provenance required")
        timestamp(source["fetched_at"])


def finite_number(value, minimum, maximum):
    return value is None or (type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum)


def validate_input(data, dataset):
    try:
        provenance(data)
        require(data["dataset"] == dataset, "Wrong teammate dataset")
        ids = set()
        for record in data["records"]:
            identifier = record["professor_id"] if dataset == "professors" else record["id"]
            require(isinstance(identifier, str) and identifier and identifier not in ids, "Missing/duplicate record ID")
            ids.add(identifier)
            if dataset == "gpa":
                from scripts.teaching_history import parse_term_id
                from scripts.data_contract import COURSE_PATTERN
                parse_term_id(record["term_id"])
                require(bool(COURSE_PATTERN.fullmatch(record["course_code"])), "Invalid grade course code")
                require(record["grain"] in ("section", "course_term", "instructor_course_term"), "Invalid grade grain")
                require(finite_number(record["gpa"], 0, 4), "GPA must be null or a finite 0–4 value")
                require(record["student_count"] is None or (type(record["student_count"]) is int and record["student_count"] >= 0), "Invalid student count")
                if record["grain"] == "section":
                    require(record["section_id"].startswith(record["term_id"] + ":") and bool(re.fullmatch(r"\d{5}", record["section_id"].split(":")[-1])), "Section grades require a term + CRN")
                else:
                    require(record.get("section_id") is None, "Grades without CRNs must not claim section attribution")
                if record["grain"] == "instructor_course_term":
                    require(bool(record.get("primary_instructor_name_raw")), "Source primary instructor required")
            elif dataset == "professors":
                require(record["display_name"] and record["identity_evidence"], "Verified identity evidence required")
                rmp = record.get("rmp")
                if rmp is not None:
                    require(rmp["scope"] == "professor", "RMP summaries must remain professor-wide")
                    require(finite_number(rmp["overall_quality"], 0, 5), "Invalid RMP quality")
                    require(type(rmp["num_ratings"]) is int and rmp["num_ratings"] >= 0, "Invalid RMP sample count")
                    timestamp(rmp["collected_at"])
                    require(rmp["source_url"].startswith("https://"), "RMP source required")
                for link in record.get("faculty_links", []):
                    require(link["url"].startswith("https://") and link["evidence"], "Faculty URL verification required")
                    timestamp(link["verified_at"])
            else:
                require(dataset == "verified_occurrences", "Unknown teammate input")
                require(record["verified"] is True and record["evidence"], "Uncertain matches cannot be verified links")
                require(type(record["instructor_index"]) is int and record["instructor_index"] >= 0, "Invalid instructor index")
                require(type(record["is_primary"]) is bool, "Primary designation must be explicit")
                if record["is_primary"]:
                    require(record.get("primary_evidence"), "Do not infer primary instructor from source order")
                timestamp(record["verified_at"])
    except (KeyError, TypeError, AttributeError) as error:
        raise DataError(f"Malformed {dataset} input: {error}") from error
    return data


def snapshots_of(schedule, history):
    # The current campus source takes precedence over an archived copy of its term.
    return [schedule] + [snapshot for snapshot in history["snapshots"] if snapshot["term"]["id"] != schedule["term"]["id"]]


def preview(schedule, history, inputs):
    sections = {section["id"]: section for snapshot in snapshots_of(schedule, history) for section in snapshot["sections"]}
    people = {record["professor_id"] for record in inputs.get("professors", {}).get("records", [])}
    verified = inputs.get("verified_occurrences", {}).get("records", [])
    for record in verified:
        require(record["professor_id"] in people, "Verified link references an unknown professor")
        section = sections.get(record["section_id"])
        require(section is not None and section["listing_id"] == record["listing_id"], "Verified link references an unknown section/listing")
        meetings = {meeting["id"]: meeting for meeting in section["meetings"]}
        meeting = meetings.get(record["meeting_id"])
        require(meeting is not None and record["instructor_index"] < len(meeting["instructors"]), "Verified link references an unknown instructor occurrence")
        require(meeting["instructors"][record["instructor_index"]]["name_raw"] == record["name_raw"], "Verified name differs from preserved source name")
    attributions = []
    for grade in inputs.get("gpa", {}).get("records", []):
        listing_id = f'{grade["term_id"]}:{grade["course_code"]}'
        candidates = [record for record in verified if record["listing_id"] == listing_id and record["is_primary"] and record["name_raw"] == grade.get("primary_instructor_name_raw")]
        if grade["grain"] == "section":
            candidates = [record for record in candidates if record["section_id"] == grade["section_id"]]
        elif grade["grain"] == "course_term":
            candidates = []
        ids = {record["professor_id"] for record in candidates}
        attributions.append({"grade_record_id": grade["id"], "listing_id": listing_id,
                             "section_id": grade.get("section_id") if grade["grain"] == "section" else None,
                             "grain": grade["grain"], "professor_id": next(iter(ids)) if len(ids) == 1 else None,
                             "status": "verified" if len(ids) == 1 else "unresolved"})
    return {"schema_version": 1, "dataset": "integration_preview", "data_kind": schedule["data_kind"],
            "collected_at": max((data["collected_at"] for data in [schedule, history, *inputs.values()]), key=timestamp), "grade_attributions": attributions,
            "pending_inputs": [name for name in ("gpa", "professors", "verified_occurrences") if name not in inputs],
            "coverage": counts(schedule["sections"])}


def validate_reviewed_aliases(mapping):
    from urllib.parse import urlparse
    require(mapping["schema_version"] == 1 and isinstance(mapping["aliases"], list), "Invalid reviewed alias mapping")
    from scripts.data_contract import COURSE_PATTERN
    from scripts.teaching_history import parse_term_id
    for record in mapping["aliases"]:
        require(len(record["course_codes"]) >= 2 and all(COURSE_PATTERN.fullmatch(code) for code in record["course_codes"]), "Reviewed aliases require course codes")
        require(record["term_ids"] and record["reviewed_by"] and record["evidence"], "Alias review and applicable terms are required")
        timestamp(record["reviewed_at"])
        for term in record["term_ids"]: parse_term_id(term)
        for evidence in record["evidence"]:
            hostname = urlparse(evidence["source_url"]).hostname or ""
            require(evidence["source_url"].startswith("https://") and (hostname == "illinois.edu" or hostname.endswith(".illinois.edu")), "Official HTTPS alias evidence required")
            require("Same as" in evidence["text"] or "See " in evidence["text"], "Explicit alias evidence required")
    return mapping


def aliases(schedule, history, mapping=None):
    records = []
    for snapshot in snapshots_of(schedule, history):
        for relation in snapshot["relationships"]:
            records.append({**relation, "applicable_terms": [snapshot["term"]["id"]]})
    return {"schema_version": 1, "dataset": "course_aliases", "data_kind": schedule["data_kind"],
            "collected_at": max([schedule["collected_at"], history["collected_at"]], key=timestamp), "records": records,
            "reviewed_records": validate_reviewed_aliases(mapping)["aliases"] if mapping else []}


def _stage_bundle(directory, schedule, history, inputs=None, coverage=None, allow_fixtures=False, reviewed_aliases=None):
    """Write immutable objects first, then atomically switch the single manifest."""
    inputs = inputs or {}
    validate_document(schedule)
    validate_document(history)
    for name, data in inputs.items():
        validate_input(data, name)
    require(allow_fixtures or all(data["data_kind"] == "live" for data in [schedule, history, *inputs.values()]), "Synthetic inputs are forbidden in production")
    documents = {"schedule": schedule, "history": history, "aliases": aliases(schedule, history, reviewed_aliases), **inputs}
    if reviewed_aliases is not None:
        documents["reviewed_aliases"] = validate_reviewed_aliases(reviewed_aliases)
    documents["preview"] = preview(schedule, history, inputs)
    if coverage is not None:
        require([row["subject"] for row in coverage["departments"]] == coverage["requested_subjects"], "Incomplete department coverage")
        require(all(row["status"] in ("collected", "no_listings") for row in coverage["departments"]), "Failed department coverage cannot be published")
        require(sum(row["course_count"] for row in coverage["departments"]) == len(schedule["courses"]), "Department course count mismatch")
        require(sum(row["section_count"] for row in coverage["departments"]) == len(schedule["sections"]), "Department section count mismatch")
        documents["department_coverage"] = coverage
    directory = Path(directory)
    files = {}
    staged = []
    for name, data in documents.items():
        body = encoded(data)
        digest = hashlib.sha256(body).hexdigest()
        relative = f"objects/{digest}.json"
        files[name] = {"status": "available", "path": relative, "sha256": digest, "bytes": len(body), "collected_at": data.get("collected_at", schedule["collected_at"])}
        staged.append((relative, body))
    for name in ("gpa", "professors", "verified_occurrences"):
        if name not in files:
            files[name] = {"status": "pending", "path": None, "sha256": None, "bytes": None, "collected_at": None}
    manifest = {"schema_version": 1, "dataset": "professor_guide", "data_kind": schedule["data_kind"],
                "collected_at": max((item["collected_at"] for item in files.values() if item["collected_at"]), key=timestamp),
                "current_term": schedule["term"], "coverage": counts(schedule["sections"]), "files": files}
    # All validation/join work above completes before any published object is written.
    for relative, body in staged:
        target = directory / relative
        if target.exists():
            require(target.read_bytes() == body, "Immutable object hash collision/corruption")
        else:
            atomic_write_text(target, body.decode())
    atomic_write_text(directory / "integration.json", encoded(manifest).decode())
    return manifest


def publish_bundle(directory, schedule, history, inputs=None, coverage=None, allow_fixtures=False, reviewed_aliases=None):
    directory = Path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    previous = validate_bundle(directory)[0] if (directory / "integration.json").exists() else None
    with tempfile.TemporaryDirectory(prefix=".professor-guide-stage-", dir=directory.parent) as temporary:
        stage = Path(temporary)
        manifest = _stage_bundle(stage, schedule, history, inputs, coverage, allow_fixtures, reviewed_aliases)
        validate_bundle(stage)
        for item in manifest["files"].values():
            if item["status"] == "available":
                source, target = stage / item["path"], directory / item["path"]
                if target.exists():
                    require(source.read_bytes() == target.read_bytes(), "Immutable object corrupted")
                else:
                    atomic_write_text(target, source.read_text(encoding="utf-8"))
        atomic_write_text(directory / "integration.json", encoded(manifest).decode())
    if manifest != previous:
        prune_objects(directory, [manifest, previous] if previous else [manifest])
    return manifest


def prune_objects(directory, manifests):
    """Keep the current and previous publication; Git holds older versions.

    Call only after a successful manifest switch. An identical publication keeps
    the previous generation too. Cleanup failures must not report a committed
    publication as failed or trigger report rollback.
    """
    keep = {item["path"] for manifest in manifests for item in manifest["files"].values()
            if item["status"] == "available"}
    for target in (Path(directory) / "objects").glob("*.json"):
        if re.fullmatch(r"[a-f0-9]{64}\.json", target.name) and f"objects/{target.name}" not in keep:
            try:
                target.unlink()
            except OSError as error:
                warnings.warn(f"Published successfully; could not remove old object {target}: {error}")


def validate_bundle(directory):
    directory = Path(directory)
    manifest = read(directory / "integration.json")
    require(manifest["schema_version"] == 1 and manifest["dataset"] == "professor_guide", "Invalid integration manifest")
    documents = {}
    for name, item in manifest["files"].items():
        if item["status"] == "pending":
            require(name in ("gpa", "professors", "verified_occurrences") and all(item[key] is None for key in ("path", "sha256", "bytes", "collected_at")), "Pending data must not look like zero data")
            continue
        require(item["status"] == "available" and bool(re.fullmatch(r"objects/[a-f0-9]{64}\.json", item["path"])), "Unsafe object path")
        body = (directory / item["path"]).read_bytes()
        require(hashlib.sha256(body).hexdigest() == item["sha256"] and len(body) == item["bytes"], "Published file hash/size mismatch")
        require(item["path"] == f'objects/{item["sha256"]}.json', "Hash path mismatch")
        documents[name] = json.loads(body)
    for name in ("schedule", "history"):
        validate_document(documents[name])
    inputs = {name: validate_input(documents[name], name) for name in ("gpa", "professors", "verified_occurrences") if name in documents}
    require(documents["preview"] == preview(documents["schedule"], documents["history"], inputs), "Inconsistent integration preview")
    expected_aliases = aliases(documents["schedule"], documents["history"], documents.get("reviewed_aliases"))
    if "reviewed_records" not in documents["aliases"]:
        expected_aliases.pop("reviewed_records")  # Earlier additive integration preview.
    require(documents["aliases"] == expected_aliases, "Inconsistent alias evidence")
    require(manifest["coverage"] == counts(documents["schedule"]["sections"]), "Inconsistent manifest coverage")
    require(manifest["current_term"] == documents["schedule"]["term"], "Inconsistent current term")
    for name, data in documents.items():
        require(manifest["files"][name]["collected_at"] == data.get("collected_at", documents["schedule"]["collected_at"]), "Source timestamp mismatch")
    require(manifest["collected_at"] == max((item["collected_at"] for item in manifest["files"].values() if item["collected_at"]), key=timestamp), "Manifest timestamp mismatch")
    require(manifest["data_kind"] == "development_fixture" or all(data.get("data_kind", "live") == "live" for data in documents.values()), "Production includes synthetic data")
    return manifest, documents
