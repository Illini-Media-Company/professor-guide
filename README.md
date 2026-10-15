# Professor Guide

A Daily Illini UIUC course/professor project. React + Vite + Tailwind renders saved JSON on GitHub Pages at `/professor-guide/`; Python collects and integrates data offline. No accounts, database, or always-running backend.

Jon's collection/integration infrastructure is implemented. Grade calculations, identity verification/RMP, and the full frontend belong to the three teammates. The interface is an integration shell and small original data-loading demonstration.

## Local setup

Use **Node 24** (`.nvmrc`) and **Python 3.11+** (CI uses 3.11). Run from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run dev
```

Open **http://localhost:5173/professor-guide/**. Python's installable dependency is `certifi`, used for verified HTTPS on every platform. No Mac certificate override or existing cache is required. The committed normalized data works without network access.

## One update command

```sh
python -m scripts.update_data
```

This discovers the configured current term, collects departments using verified batch endpoints, reuses saved historical assignments, loads any normalized teammate inputs, validates all components and joins, generates coverage reports, stages the complete publication, and switches `public/data/integration.json` only after validation. Any collection/access/parsing/input/build failure prevents automated deployment. Previous published source timestamps are preserved on failure.

```sh
python -m scripts.update_data --scope sample
python -m scripts.update_data --subjects CS ECE STAT IS
python -m scripts.update_data --courses "CS 374" "ECE 374"
python -m scripts.update_data --term 2026-fall
python -m scripts.update_data --reuse-current   # no source requests; useful after a fresh checkout
python -m scripts.update_data --refresh-history
```

`config/collection.json` explicitly selects Fall 2026 and expires on December 31, 2026. The term must appear in discovered schedules; the collector never assumes the next term exists. Review this configuration before the next semester. `--term` is an explicit operator override. Default empty subject/course lists mean all discovered subjects. A sample or department override deliberately narrows coverage; inspect its report before committing it to production.

The client uses verified HTTPS, a 20-second timeout, at most two retries, and at least 0.4 seconds between requests. HTTP 401/403 immediately stop collection. HTTP/network failures are not unavailable courses. Valid parent-index absence is unavailable; malformed indexes and incomplete data are errors. Prior-calendar-year raw responses cache for 30 days, current-year responses for six hours. `--refresh` bypasses raw caches. Normalized historical schedules are reused from committed data until explicitly refreshed, independently of optional caches. See [operations](docs/operations.md).

## Data and coverage

- [Current campus coverage](docs/current-coverage.md): all **186** discovered Fall 2026 departments, **4,452 listings**, **12,839 registration sections**, **13,640 meetings**, and **18,594 unresolved listed instructor occurrences** at collection.
- [Pilot coverage](docs/pilot-coverage.md): Fall 2026 and Spring 2025 for CS/ECE 374 and CS/STAT/IS 107; 308 registration sections across ten course/term pairs.
- [Integration history coverage](docs/integration-history-coverage.md): the history currently assembled with the campus schedule.
- Missing instructors remain empty; multiple instructors remain on their actual meetings. Source names and original attributes remain available. There are 534 meetings without listed instructors in the campus sample, not 534 known professors.
- Explicit “Same as”/“See” relationships retain evidence and applicable terms; they never merge registration CRNs. `data/mappings/course-aliases.json` optionally supplies reviewed official evidence with explicit term IDs.

These are registration/meeting counts, not unique teaching groups, people, or grade samples. Term + CRN remains the section key. Raw instructor order does **not** establish a primary instructor or verified identity.

## Frontend and teammate interfaces

Fetch `${import.meta.env.BASE_URL}data/integration.json`, then resolve available `files.*.path` relative to `data/`. Each entry gives status, exact byte size, SHA-256, and source collection time. File paths are immutable. `pending` means absent teammate data; it never means a valid zero.

The manifest supplies schedule, history, aliases, coverage, and integration-preview objects. GPA, professors/RMP, and verified occurrence links remain explicitly pending until their owners supply normalized inputs. Source schedule identities remain null even after separate verified links are added. Existing `public/data/course-explorer.json` and `teaching-history.json` keep their original formats and are retained for existing consumers.

Ready-to-use tasks and completion criteria: [three teammate handoffs](docs/team-handoffs.md). Exact schemas, fields, join constraints, and additive migration notes: [data contract](docs/data-contract.md). Synthetic input examples: `data/examples/integration/`.

```sh
python -m scripts.preview_integration
```

This builds a **synthetic** integration example in ignored `data/previews/`; it does not publish fixtures into production. The live integration shell is useful while teammate files are pending. Production publication rejects synthetic inputs.

## Checks

```sh
npm run test:data
npm run validate:data
npm run build
npx playwright install chromium
npm run test:embed
npm run preview
```

Preview: **http://localhost:4173/professor-guide/**. Embedding test: **http://localhost:4173/professor-guide/embed-test.html**. Chromium checks exercise iframe widths 320/375/768, keyboard controls, 200% shell CSS zoom, and query/hash URLs. These complement the offline collection, aliases, missing/multiple instructors, historical caching, verified-join, file-hash, failure-preservation, and fresh-checkout tests.

## GitHub Pages and automated refresh

`.github/workflows/pages.yml` runs offline checks, validates all published data/hashes, builds the site, and runs embed checks before deployment. Main pushes deploy; PRs check without deploying. Weekly Monday **10:20 UTC** and manual refreshes collect according to configuration. Archived normalized history is reused. The workflow commits validated data to Git before deploying the exact built artifact; the deployment does not depend on another push-triggered workflow. Source caches are optional performance aids, not the durable last-successful data store.

```sh
gh workflow run pages.yml -f refresh=true -f scope=campus
gh run list --workflow pages.yml
```

Production refresh/deployment runs share one concurrency group. If main is protected, the refresh attempts a data PR and a check run on that branch; no deployment occurs until merge. Repository policy must permit the corresponding bot push or PR. See [operations and restoration](docs/operations.md).

Site: **https://illini-media-company.github.io/professor-guide/**. Pages uses GitHub Actions. The exact embedding handoff and its verification state are in [docs/embed.md](docs/embed.md).

## Layout and ownership

| Path | Purpose |
| --- | --- |
| `src/` | Frontend owner's interface; integration shell provided |
| `scripts/` | Jon's collection, validation, integration, publication, verification |
| `config/` | Reviewed current-term selection and collection/input configuration |
| `data/inputs/` | Normalized teammate inputs, optional until supplied |
| `data/mappings/` | Reviewed identity/alias mappings; source records remain separate |
| `data/examples/` | Clearly labeled synthetic fixtures |
| `data/snapshots/`, `data/reports/`, `.cache/` | Ignored local candidates, attempt reports, and raw caches |
| `public/data/` | Committed normalized public data, immutable objects, manifest |
| `docs/` | Coverage, contracts, operations, embedding, team handoffs |

Raw downloads, environments, dependencies, disposable caches, and test output stay out of Git and the site. Keep genuinely confidential/unlicensed source inputs out of `public/`; this publisher serves only the documented normalized outputs.

Salary Guide was inspected at `42a41bc09bf1cb2883ea044b6436fc34e13916d4`; its React/Vite, repository path, and saved-JSON patterns informed the starter. See [verified Course Explorer observations](docs/course-explorer-api.md). Current API documentation, rate-limit guarantees, and archive immutability could not be verified. The collector uses paced requests and immediately respects access denial.
