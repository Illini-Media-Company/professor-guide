# Working here

Read [README.md](README.md) for commands and [docs/backlog.md](docs/backlog.md) for product decisions.

- Use saved data for UI work; avoid live collection unless the task needs it.
- Publish data through `scripts.update_data`; never hand-edit manifest hashes or generated objects. Keep source evidence, review caches, and existing verified links.
- Read [the contract](docs/data-contract.md) before changing attribution. Initials alone cannot establish identity. Missing values stay Pending; real zeros remain valid. GPA is course-specific; RMP is professor-wide.
- Review scripts/config are fingerprinted in audit ledgers; changes require the affected review workflow to be rerun.
- Preserve `/professor-guide/`, hash navigation, and the 800px iframe. Main pushes deploy after checks.
- Run checks for the changed area. Documentation edits need link checks only. Keep guidance brief and avoid duplicating it across files.
