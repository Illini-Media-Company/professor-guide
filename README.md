# Professor Guide

The Daily Illini’s UIUC course/professor guide. React + Vite + Tailwind loads saved JSON on GitHub Pages at `/professor-guide/`. Python collects and integrates data offline; there is no database or always-running backend.

Live site: **https://illini-media-company.github.io/professor-guide/**

## Local setup

Use Node 24 (`.nvmrc`) and Python 3.11+. Run from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run dev
```

Open **http://localhost:5173/professor-guide/**. Committed data works without contacting Course Explorer. `certifi` supplies verified HTTPS for collection; no certificate override is needed.

## Update data

With the virtual environment active:

```sh
python -m scripts.update_data                  # collect, validate, integrate, publish
python -m scripts.update_data --reuse-current  # integrate saved data, no source requests
```

`config/collection.json` selects the current term, archive start year, review deadline, and optional teammate inputs. It currently selects Fall 2026, with a review deadline of December 31, 2026. Available terms are discovered from official indexes. Complete archived semesters are reused until explicitly refreshed. HTTP 401/403 or an HTTP 202 automated-access challenge stops collection immediately; failed refreshes keep the last good publication.

The production update always collects every department. `--start-year 2023` selects the archive’s first calendar year; `--term 2026-fall` selects the current/end term. Every available winter, spring, summer, and fall term within that range is included. `collect_campus` is the single collection engine; it also accepts explicit courses for isolated investigation without narrowing production coverage. Run `python -m scripts.update_data --help` for all options. Collection-only commands, cache behavior, publication safety, deployment, restoration, and the DI iframe snippet are in [operations](docs/operations.md).

## Data and team ownership

The shared entry point is **`public/data/integration.json`**. Its `files` entries resolve to immutable JSON objects for the current schedule, teaching history, aliases, coverage, and optional teammate outputs. All consumers should use this manifest. The data page shows real coverage, source dates, and per-term downloads. It loads only the small archive index; schedules load when requested.

| Owner | Work |
| --- | --- |
| Jon | Repository, Course Explorer collection, integration, publication, Pages deployment |
| GPA owner | Grade-source processing, calculations, normalized `data/inputs/gpa.json` |
| Matching owner | Identity verification, RMP/faculty links, normalized professor and occurrence files |
| Frontend owner | Search, results, profiles, charts, and final interface in `src/` |

[Team handoffs](docs/team-handoffs.md) provide input/output instructions and a Python reading example. [Data contract](docs/data-contract.md) defines fields and joins. Original instructor names remain available; source professor IDs stay unresolved. Missing grades/ratings are unavailable, never fabricated zeros. Synthetic development fixtures live only in `data/examples/` and are rejected by production publication.

[Current coverage](docs/current-coverage.md): 186 Fall 2026 departments, 4,452 listings, and 12,839 registration sections. [History coverage](docs/integration-history-coverage.md) records the archive’s actual collected and unavailable terms. The configured range is 2023 through Fall 2026; discovery alone is not a claim that collection succeeded. See [verified API observations](docs/course-explorer-api.md) for source behavior and verification limits.

Collection and integration use one path: `update_data` → `collect_campus` → validated archive → publication. `scripts/course_explorer.py` holds shared HTTP/XML helpers. Retired pilot collectors and the earlier history envelope have been removed. New work uses the manifest and per-term archive files. Historical records keep the original v1 course/section format; the public history envelope is now a version 2 index so several years do not become one giant download. See the contract’s migration notes. The site retains objects for the current and previous publication; Git preserves older versions.

## Checks and preview

```sh
npm run test:data
npm run validate:data
npm run build
npx playwright install chromium
npm run test:embed
npm run preview
```

Preview: **http://localhost:4173/professor-guide/**. Iframe test: **http://localhost:4173/professor-guide/embed-test.html**. Data tests are offline; browser tests cover loading, errors, narrow iframes, keyboard controls, and zoom.

## Deployment

GitHub Pages uses the single workflow in `.github/workflows/pages.yml`. Main pushes check and deploy; PRs check only. Weekly Monday 10:20 UTC and manual refreshes collect, run checks, commit validated data, and deploy the tested artifact.

```sh
gh workflow run pages.yml -f refresh=true
gh run list --workflow pages.yml
```

[Operations](docs/operations.md) covers repository settings, failure behavior, rollback, and embedding. DI staging verification still needs an authenticated staging session; no DI CMS content has been edited.

## Layout

- `src/`: frontend and shared manifest loader.
- `scripts/`: collectors, validation, integration, publication, and deployment verification.
- `config/`: reviewed collection settings.
- `data/inputs/`, `data/mappings/`, `data/examples/`: teammate outputs, reviewed mappings, synthetic fixtures.
- `public/data/`: committed generated visitor data.
- `tests/`: offline data checks and browser embed checks.
- `docs/`: contract, operations, teammate handoffs, API observations, and generated coverage reports.

Dependencies, environments, raw downloads, local candidates, caches, and test output are ignored. Salary Guide’s React/Vite, repository base path, and saved-JSON patterns informed the starter; its inspected revision is recorded in the API notes.
