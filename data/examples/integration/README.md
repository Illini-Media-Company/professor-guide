# Synthetic integration examples

All people, grades, source links, primary-instructor claims, ratings, and review evidence here are invented. `data_kind` is `development_fixture`; production publication rejects these inputs. The zero and null grades deliberately demonstrate distinct states, and primary designation is explicit rather than inferred from array order.

`tests/test_integration.py` exercises these examples with synthetic schedule/history fixtures. Use their shapes for real normalized outputs, following the [contract](../../../docs/data-contract.md).

## Reviewing different source names

Suppose an invented schedule occurrence says `Example, Alex` while the grade
row says `Example, Alexandra Q`. After reviewing evidence that both names
identify the same verified person in that course/term, add this entry to the
occurrence's optional `grade_name_matches` array:

```json
{
  "grade_record_id": "synthetic-zero",
  "primary_instructor_name_raw": "Example, Alexandra Q",
  "source_url": "https://example.org/synthetic-fixture",
  "reviewed_by": "Synthetic reviewer",
  "verified_at": "2026-01-01T00:00:00Z",
  "evidence": ["Invented faculty evidence connects both names to this person."],
  "primary_evidence": ["Invented grade source explicitly names Alexandra as primary."]
}
```

The grade's raw name must actually be `Example, Alexandra Q`; do not alter it
to make a match. The URL must occur in both input envelopes' `sources`. This
review applies only to `synthetic-zero` and the occurrence's course/term;
another row with the same name still needs its own review. The grade's primary
evidence does not designate a section-primary role: the occurrence can keep
`is_primary: false`, and a CRN-less grade retains `section_id: null`.

`tests/test_grade_attribution.py` exercises this invented name difference,
scope restrictions, provenance, conflicting identities, and publication
preservation. It also checks the committed real reviews against saved terms,
without source requests. The live Miles reviews are recorded in
[`data/inputs/verified-links.json`](../../inputs/verified-links.json); original
grade and schedule names remain unchanged.
