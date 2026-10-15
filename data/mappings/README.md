# Reviewed mappings

`course-aliases.json` is consumed by the shared publisher. The array starts empty. A reviewed entry needs course codes, explicit applicable `term_ids`, review identity/time, and exact official “Same as”/“See” evidence and URL. Automated source relationships are already published with their terms and provenance; reviewed records remain separate and never merge CRNs.

`professor-identities.json` is the matching owner's review workspace. It is not automatically interpreted as verified identity links. That owner produces `data/inputs/professors.json` and `verified-links.json` with explicit evidence; uncertain names remain unresolved.

See [the implemented contract](../../docs/data-contract.md) and [team handoffs](../../docs/team-handoffs.md).
