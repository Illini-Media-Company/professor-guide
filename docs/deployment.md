# Observed deployment verification

GitHub Pages is enabled for `Illini-Media-Company/professor-guide` with `build_type: workflow` and HTTPS enforcement.

- Live site: **https://illini-media-company.github.io/professor-guide/**
- Embedding test: **https://illini-media-company.github.io/professor-guide/embed-test.html**
- Initial implementation: [`1f0e0b8`](https://github.com/Illini-Media-Company/professor-guide/commit/1f0e0b88d4d2dbbbc5c92296141b5a0edfd910e1).
- [Initial push check/build/deployment](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672910528): **passed**.
- [Manual full campus refresh/persistence/deployment](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672971027): **passed**.
- Automatically persisted data commit: [`4238304`](https://github.com/Illini-Media-Company/professor-guide/commit/4238304bb3c52e6ff3c9f42f675fe54e9f286b88).

The manual run used a fresh runner: 375 live source requests, zero cache hits, all 186 discovered departments collected. It reused committed normalized history without changing its source timestamps. The current source timestamp became `2026-10-15T02:52:23Z`; the archived history retained `2026-10-15T02:20:50Z`. These UTC dates correspond to October 14, 2026, Central time.

Both runs passed the then-current 42 Python checks, published-data/hash validation, production build, and five Chromium embed checks before deployment. The refresh committed data before uploading/deploying its tested artifact. Its deploy job then verified the exact expected manifest revision, HTML, two JS/CSS assets, all six available JSON hashes, and the embedding test page. This proves persistence/deployment works without relying on another push workflow being triggered by the bot commit.

An independent local verification of the deployed URL also checked the expected manifest and every object hash. A Chromium page with a different parent origin successfully loaded the actual deployed iframe and its current-campus data. Mobile widths, native keyboard controls, 200% CSS shell zoom, and query/hash URLs passed local/runner checks.

Final safeguards add chronological timestamp comparison across timezone offsets, `Retry-After` handling, cache freshness floors against committed data, and offline reuse that ignores stale local candidates. The expanded local suite passes **46** checks. The latest main CI/deployment result is available on the [workflow page](https://github.com/Illini-Media-Company/professor-guide/actions/workflows/pages.yml); each successful main run verifies the exact manifest it deployed.

Grade calculations/data, verified identities/RMP/faculty data, and the full interface remain teammate implementations. Their input files are explicitly pending. The exact iframe handoff is in [embed.md](embed.md). Authenticated DI staging verification remains external: no staging URL/session was supplied, and no DI CMS content was modified.
