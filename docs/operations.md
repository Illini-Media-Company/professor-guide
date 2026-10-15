# Collection, persistence, deployment, and restoration

## Normal operation

Install Node 24 and Python 3.11 with `requirements.txt`. Activate `.venv`, run `npm ci`, then `python -m scripts.update_data` from the repository root. No secret or Mac-specific setting is needed to collect public Course Explorer XML. `certifi` supplies a maintained public trust bundle with certificate verification enabled.

`config/collection.json` is the current-term decision, not a guess based on the newest published semester. It selects `2026-fall` through `2026-12-31`; collection must also discover that term in the official calendar/year indexes. Expired configuration fails closed. At semester change, review the available term and update both fields. An explicit `--term YEAR-season` override is verified against available schedules.

The default command collects all discovered departments. `--scope sample` selects AAS/CS/MATH/CHEM/MUS. `--subjects` or `--courses` narrows it explicitly. Department indexes and `?mode=cascade` responses must contain matching course sets. Batch course/section parents, IDs, source URLs, and all resulting records are validated. Ordinary individual-course collection remains available with `scripts.collect_course_explorer`; the pilot remains available with `scripts.collect_teaching_history`.

The live mixed sample and campus collection verified 186 subjects. Source corrections can occur; archived data is not assumed immutable. `--refresh` bypasses raw XML caches. `--refresh-history` explicitly rebuilds historical normalized data, which otherwise remains durable and unchanged.

## History required by grades

When `data/inputs/gpa.json` exists, its normalized `term_id`/`course_code` records add historical requirements alongside `historical_requests` in the configuration. The current campus term is already collected. The existing normalized history is reused when it covers every required pair. Otherwise the existing history collector collects the required terms and the union of required courses. Its established v1 format is a rectangular course × term grid; any extra pairs are explicit in coverage, not falsely described as grade-required. `requested_history_pairs` records the actual configured/grade requirements on newly collected history.

This interface is ready for the GPA owner; no grade input currently exists in production. Grade calculations and source-to-term translation remain with that owner. Missing or unavailable grades are not zero. A valid average of zero remains zero.

## Publication transaction

1. Discover and collect into ignored local candidates. Source failures retain previous normalized public data; access denial stops immediately.
2. Load and validate any teammate inputs. Perform identity/grade join checks without changing source records.
3. Prepare reports and a temporary complete publication outside the live data directory.
4. Validate schemas, coverage, joins, byte sizes, and hashes in that temporary publication.
5. Copy immutable `objects/<sha256>.json` files, then atomically replace the single `integration.json` manifest last.

A failure before the manifest switch leaves the old manifest and all its source timestamps intact. An interrupted immutable-object copy can leave an unreferenced object; it cannot make old readers reference half-written data. Reports are restored if publication fails. Legacy public course/history files are not rewritten by integration publication.

The manifest is the transaction boundary for consumers. Resolve every object from one manifest response. Do not independently guess or mix object filenames. Each available entry contains `path`, `sha256`, `bytes`, and `collected_at`; each pending teammate entry has null values rather than fake empty/zero observations.

## Durable data and workflow behavior

Normalized `public/data/` files and their original source timestamps are committed to Git. They survive cache eviction, runner replacement, and fresh checkouts. Normalized historical data is loaded through the committed manifest (or the retained initial history file). `.cache/course-explorer` only speeds source requests. Raw XML never goes into the public artifact.

One workflow handles push checks/deployment, PR checks, manual refreshes, and weekly Monday 10:20 UTC refreshes. All production jobs share one concurrency group, with cancellation disabled. The default branch is `main`.

Refresh sequence: checkout → optional collection/publication locally → offline tests → full public-data/hash validation → production build → embed tests → commit/push changed normalized files and reports → upload the already tested site → Pages deploy → verify the exact deployed manifest hash plus assets/data hashes. A failed refresh, test, build, or persistence step prevents deployment and leaves the previous live artifact in place.

Commits made with `GITHUB_TOKEN` do not normally trigger another push workflow. Deployment deliberately happens in the same successful refresh workflow, so it cannot silently depend on that suppressed trigger. The build exports the manifest SHA-256 to the deploy job; CDN verification checks that exact revision. Workflow tokens need contents write, Pages write/id-token, and (for a protected-main fallback) pull-request/actions write.

If a main push is protected, the workflow attempts a `data-refresh/<run-id>` branch and PR, dispatches checks on that branch, then stops before deployment. Merge after review triggers normal main deployment. Organization settings can disallow bot PR creation; that policy is an external repository control, not something the workflow bypasses. This repository had no branch rules when initially inspected.

## Restore a previous published version

Find a known-good commit and restore the complete data directory, preserving the manifest and all referenced objects together:

```sh
git log --oneline -- public/data
git restore --source=<known-good-commit> -- public/data docs/current-coverage.md docs/integration-history-coverage.md
npm run validate:data
npm run build
git add public/data docs/current-coverage.md docs/integration-history-coverage.md
git commit -m "data: restore last successful publication"
git push origin main
```

Do not replace only an object or invent a new collection timestamp during restoration. If reverting a whole bad update is preferable, `git revert <bad-update-commit>` followed by checks and a normal push is also supported. Old normalized objects remain in Git history independently of caches. Retained immutable objects are intentionally not pruned during refresh; review site/repository size before introducing a retention policy.

## Verification boundaries

Live verified: public XML discovery, five-department sample, all current-term departments, actual missing labels/instructors, multiple instructors, roles, and source provenance. Fixture tested: explicit empty-section/meeting flags, uncertain mappings, valid zero/null values, HTTP failures/access denial, interrupted publication, and fresh cache-free operation. Browser checked: iframe shell widths, keyboard, and CSS 200% shell zoom; final DI CMS/theme behavior needs a DI staging session. Grade/RMP data and full interface remain teammate work.
