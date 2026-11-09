# Professor Guide

The Daily Illini’s UIUC course and professor guide. React/Vite reads saved JSON; Python collects and prepares it. Hosted on [GitHub Pages](https://illini-media-company.github.io/professor-guide/).

## Develop

Node 24 (`.nvmrc`), Python 3.11+. Run from the repo root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci
npm run dev
```

Open **http://localhost:5173/professor-guide/**. Saved data is ready to use.

- UI changes: `npm run test:ui`, `npm run build`, `npm run test:embed`.
- Data changes: `npm run test:data`, `npm run validate:data`.
- Install the browser once: `npx playwright install chromium`.
- Preview: `npm run preview`; iframe test at `/professor-guide/embed-test.html`. Browser tests use port 4173; stop stale preview servers first.

## Find things

- `src/Guide.jsx`: search and details; `src/guide.js`: filtering and GPA calculations; `src/data.js`: loading; `src/index.css`: styling.
- `scripts/`: collection, matching, validation, publication. `config/`: term settings and reviewed matching rules.
- `data/inputs/`: normalized GPA, instructors, and verified links. `data/mappings/`: evidence and unresolved queues. `data/examples/`: synthetic test fixtures.
- `public/data/integration.json`: published manifest; `files.guide` is the compact visitor index. Hashed objects are generated.

## Update and deploy

```sh
python -m scripts.update_data --reuse-current  # rebuild using saved sources
python -m scripts.update_data                  # collect schedules and publish locally
```

Pushes to `main` deploy after checks. PRs check only. The weekly Monday 10:20 UTC workflow refreshes schedules. Deploy saved data manually with `gh workflow run pages.yml --ref main -f refresh=false`.

[Operations](docs/operations.md): collection, rollback, and the DI iframe snippet. [Data contract](docs/data-contract.md): schemas and attribution rules. [Review workflow](data/mappings/README.md): matching and evidence. [Backlog](docs/backlog.md): current scope and remaining work.

Coverage: [schedule](docs/current-coverage.md) · [archive](docs/integration-history-coverage.md) · [GPA identities](docs/identity-review-coverage.md) · [RMP](docs/rmp-coverage.md).
