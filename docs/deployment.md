# Deployment verification

GitHub Pages is enabled for `Illini-Media-Company/professor-guide` with `build_type: workflow` and HTTPS enforcement. The configured URL is https://illini-media-company.github.io/professor-guide/.

Before the initial push, local verification passed 42 Python checks, full published-data/hash validation, the production build, and five Chromium embed checks. Full current-term collection and cached reruns were verified; the campus snapshot covers all 186 discovered departments. Grade/professor inputs remain explicitly pending.

Remote workflow runs and deployed-URL verification will be recorded here after the initial GitHub run. The exact iframe handoff is in `embed.md`; authenticated DI staging remains external because no session or staging URL was supplied.
