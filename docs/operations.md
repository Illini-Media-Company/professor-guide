# Collection, deployment, and embedding

Use the [README](../README.md) for installation and routine checks. Run commands from the repository root with `.venv` active.

## Routine collection

`python -m scripts.update_data` is the normal entry point. It discovers available schedules, collects the configured current term, reuses archived history, validates teammate inputs, reports coverage, and publishes one coherent dataset.

```sh
python -m scripts.update_data --subjects CS ECE STAT IS
python -m scripts.update_data --courses "CS 374" "ECE 374"
python -m scripts.update_data --term 2026-fall
python -m scripts.update_data --reuse-current
python -m scripts.update_data --refresh-history
```

Narrowed collections replace the current publication with that narrower scope; inspect coverage before committing. `--reuse-current` makes no source requests and prefers committed data over ignored local candidates. It fails if required history is not archived yet. `--refresh-history` explicitly recollects history and cannot be combined with offline reuse.

`config/collection.json` selects the current term and review deadline. Expired configuration fails closed; review both fields at semester change. An explicit `--term` override must still appear in official indexes. Empty subject/course lists mean all discovered departments.

Normalized GPA inputs add required historical course/term pairs to the configured pilot. Archived normalized history is reused when it covers those pairs. Otherwise the v1 history collector collects the required terms × union of courses; extra pairs remain explicit in coverage, and `requested_history_pairs` identifies actual requirements.

## Source requests and cache

Public XML uses verified HTTPS, a 20-second timeout, at most two retries by default (maximum five), and at least 0.4 seconds between requests. HTTP 401/403 stops immediately. `Retry-After` is honored up to 60 seconds; longer delays defer the refresh. Network/HTTP/parsing errors fail the attempt. Only absence from a successfully parsed official parent index means unavailable.

Prior-calendar-year XML caches for 30 days; current-year/discovery responses cache for six hours. `--refresh` bypasses raw caches; `--refresh-history` bypasses raw caches during history collection too. Expired or invalid data is never a request-failure fallback. A cache older than an already published source fetch cannot roll that source backward. Cache hits and reused normalized history preserve original source timestamps. `.cache/` is disposable; committed JSON is the durable last successful data store.

## Collection without publication

Use these only when reviewing an isolated candidate. They write outside `public/` and do not change the live manifest:

```sh
python -m scripts.course_explorer_discovery --years 2025 2026
python -m scripts.collect_campus --term 2026-fall --subjects CS ECE
python -m scripts.collect_teaching_history --terms 2026-fall 2025-spring \
  --courses "CS 374" "ECE 374" "CS 107" "STAT 107" "IS 107"
```

Candidates and attempt reports live in ignored `data/snapshots/` and `data/reports/`. The original individual-course collector and `scripts.publish_data` remain available for the two compatibility JSON files; they do not update the integration manifest. New integrations use `update_data`.

## Publication and retention

The publisher validates a complete temporary bundle: schemas, coverage, source timestamps, teammate joins, exact byte sizes, and SHA-256 hashes. It promotes immutable `objects/<sha256>.json` files, then atomically replaces `integration.json` last. A failure before that switch leaves the previous manifest, referenced data, and collection timestamps intact. Reports are restored if publication fails. Production rejects synthetic inputs.

After a successful changed publication, objects referenced by the new manifest and the immediately preceding manifest are retained; older unreferenced objects are removed. This gives in-flight readers one previous generation and bounds accumulation across refreshes. Identical republishes do not discard the retained generation. A cleanup error is reported without treating a completed publication as a failed refresh. Interrupted writes may leave extra objects until the next changed successful publication. The original compatibility JSON files are outside this pruning policy. Older complete datasets remain recoverable from Git history.

Consumers must resolve all files from one manifest response. Do not guess filenames, mix generations, or edit hashes/timestamps by hand. See the [contract](data-contract.md) and [reading example](team-handoffs.md#read-the-published-data).

## GitHub Pages

Repository: `Illini-Media-Company/professor-guide`; default branch: `main`. Under **Settings → Pages**, select **GitHub Actions**. Vite uses `/professor-guide/` for assets and data URLs. HTTPS is enabled.

The single workflow runs on main pushes, PRs, weekly Monday 10:20 UTC, and manual dispatch. PRs check without deploying. Production runs share a concurrency group with cancellation disabled. Refresh sequence:

1. Collect/integrate locally, run offline data checks and published-data/hash validation.
2. Build the site and run Chromium embed checks.
3. Commit/push changed public JSON and coverage reports.
4. Upload that tested artifact, deploy Pages, and verify the exact manifest revision, assets, all referenced JSON hashes, and iframe test page.

A failed collection, check, build, or persistence step prevents deployment. Bot commits made with `GITHUB_TOKEN` do not normally trigger another push workflow; the same refresh run deploys its artifact. Tokens need contents write, Pages write/id-token, and pull-request/actions write for the protected-main fallback. If main rejects a push, the workflow attempts a data PR and dispatches branch checks, then stops before deployment. Repository policy must permit those bot actions.

```sh
gh workflow run pages.yml -f refresh=true -f scope=campus
gh run list --workflow pages.yml
python -m scripts.verify_site https://illini-media-company.github.io/professor-guide/ \
  --expected-manifest public/data/integration.json
```

The [initial deployment](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672910528) and [full refresh](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672971027) passed. The refresh used 375 live requests, zero cache hits, collected all 186 departments, reused committed history, and persisted data before deploying. An independent browser check also loaded the deployed iframe from a different parent origin. Current runs are on the [workflow page](https://github.com/Illini-Media-Company/professor-guide/actions/workflows/pages.yml).

## Restore a publication

Restore the complete data directory and both generated reports from one known-good commit, then validate/build and commit normally:

```sh
git log --oneline -- public/data
git restore --source=<known-good-commit> -- public/data docs/current-coverage.md docs/integration-history-coverage.md
npm run validate:data
npm run build
git add public/data docs/current-coverage.md docs/integration-history-coverage.md
git commit -m "data: restore last successful publication"
git push origin main
```

Never restore only an object or replace collection timestamps with the restoration time. No cache is required for rollback.

## Daily Illini iframe handoff

Use this in a DI custom HTML block:

```html
<iframe
  src="https://illini-media-company.github.io/professor-guide/?embed=1"
  title="Professor Guide — UIUC courses and professors"
  width="100%"
  height="800"
  style="border: 0; display: block;"
  loading="lazy"
></iframe>
<p>
  <a href="https://illini-media-company.github.io/professor-guide/"
     target="_blank" rel="noopener">Open Professor Guide full page</a>
</p>
```

The frame has its own scrolling, an accessible title, and a full-page alternative. No dynamic resize messages are used. Query/hash navigation works without a history-route fallback.

Run `npm run build`, `npm run preview`, and open **http://localhost:4173/professor-guide/embed-test.html**. The deployed equivalent is **https://illini-media-company.github.io/professor-guide/embed-test.html**. Chromium checks cover 320/375/768px widths, keyboard disclosures/links, overflow, query/hash loading, and 200% CSS shell zoom. CSS zoom does not certify every browser or assistive technology.

**DI staging remains external:** no authenticated staging session was supplied and no CMS content has been edited. Before DI publication, check the snippet in the DI theme for mobile width, keyboard traversal, scrolling, the full-page link, and retention of iframe attributes.
