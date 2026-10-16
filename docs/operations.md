# Collection, deployment, and embedding

Use the [README](../README.md) for installation and routine checks. Run commands from the repository root with `.venv` active.

## Routine collection

`python -m scripts.update_data` is the normal entry point. It discovers available schedules, collects the configured current term, reuses archived history, validates teammate inputs, reports coverage, and publishes one coherent dataset.

```sh
python -m scripts.update_data --start-year 2023
python -m scripts.update_data --term 2026-fall
python -m scripts.update_data --reuse-current
python -m scripts.update_data --refresh-history
```

Production collection covers every discovered department in each term. `--reuse-current` makes no source requests and prefers committed data over ignored local candidates. It fails if required history is not archived yet. `--refresh-history` explicitly recollects history and cannot be combined with offline reuse.

`config/collection.json` selects the current term and review deadline. Expired configuration fails closed; review both fields at semester change. An explicit `--term` override must still appear in official indexes. `archive_start_year` sets the first calendar year; the current term is the archive end. Every winter/spring/summer/fall within that range is requested, and missing terms need official parent-index absence evidence.

The archive covers every listed course in each term, independently of GPA inputs. Grades outside the configured date range require a reviewed range extension; a grade naming a course absent from an archived semester must remain unresolved rather than inventing a CRN or copying an alias’s sections.

## Source requests and cache

Public XML uses verified HTTPS, a 20-second timeout, at most two retries by default (maximum five), and at least one second between requests. HTTP 401/403, HTTP 202, or an `x-amzn-waf-action: challenge/captcha` response stops immediately without retry. The initial backfill encountered an actual HTTP 202 challenge; this is an access failure, never evidence of an unavailable course/term. Do not solve/bypass challenges or switch origins to evade them. Resume normally only after access is available again. `Retry-After` is honored up to 60 seconds; longer delays defer the refresh. Network/HTTP/parsing errors fail the attempt. Only absence from a successfully parsed official parent index means unavailable.

Prior-calendar-year XML caches for 30 days; current-year/discovery responses cache for six hours. `--refresh` bypasses raw caches; `--refresh-history` bypasses raw caches and saved normalized candidates during history collection too. Expired or invalid data is never a request-failure fallback. A cache older than an already published source fetch cannot roll that source backward. Cache hits and reused normalized history preserve original source timestamps. `.cache/` is disposable; committed JSON is the durable last successful data store.

## Collection without publication

Use these only when reviewing an isolated candidate. They write outside `public/` and do not change the live manifest:

```sh
python -m scripts.course_explorer_discovery --years 2025 2026
python -m scripts.collect_campus --term 2026-fall --subjects CS ECE
python -m scripts.collect_campus --term 2025-spring \
  --courses "CS 374" "ECE 374" "CS 107" "STAT 107" "IS 107" \
  --output data/snapshots/selected-2025-spring.json
```

Candidates and their `.coverage.json` attempt reports live in ignored `data/snapshots/`. `collect_campus` accepts one explicit term per run; repeat it for another term and use distinct output paths. The same collector powers the full multi-term archive through `update_data`. Investigation commands do not update the production manifest.

## Publication and retention

The history v2 index references one v1 schedule and department-coverage object per collected semester. Historical objects are immutable and reused across refreshes. A cold checkout can reuse the committed archive without XML caches. Complete local backfill candidates under `data/snapshots/archive/` are resumable after validation; partial coverage files are never mistaken for completed semesters.

The publisher validates a complete temporary bundle: schemas, coverage, source timestamps, teammate joins, exact byte sizes, and SHA-256 hashes. It promotes immutable `objects/<sha256>.json` files, then atomically replaces `integration.json` last. A failure before that switch leaves the previous manifest, referenced data, and collection timestamps intact. Reports are restored if publication fails. Production rejects synthetic inputs.

After a successful changed publication, objects referenced by the new manifest and the immediately preceding manifest are retained; older unreferenced objects are removed. This gives in-flight readers one previous generation and bounds accumulation across refreshes. Identical republishes do not discard the retained generation. A cleanup error is reported without treating a completed publication as a failed refresh. Interrupted writes may leave extra objects until the next changed successful publication. Per-term schedules and coverage files referenced by an archive index are included in retention. Older complete datasets remain recoverable from Git history.

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
gh workflow run pages.yml -f refresh=true
gh run list --workflow pages.yml
python -m scripts.verify_site https://illini-media-company.github.io/professor-guide/ \
  --expected-manifest public/data/integration.json
```

The [initial deployment](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672910528) and [full refresh](https://github.com/Illini-Media-Company/professor-guide/actions/runs/38672971027) passed. The refresh used 375 live requests, zero cache hits, collected all 186 departments, reused committed history, and persisted data before deploying. An independent browser check also loaded the deployed iframe from a different parent origin. Current runs are on the [workflow page](https://github.com/Illini-Media-Company/professor-guide/actions/workflows/pages.yml).

## Restore a publication

Restore the complete data directory and both generated reports from a known-good v2 archive commit, then validate/build and commit normally:

```sh
git log --oneline -- public/data
git restore --source=<known-good-commit> -- public/data docs/current-coverage.md docs/integration-history-coverage.md
npm run validate:data
npm run build
git add public/data docs/current-coverage.md docs/integration-history-coverage.md
git commit -m "data: restore last successful publication"
git push origin main
```

Never restore only an object or replace collection timestamps with the restoration time. No cache is required for rollback. Earlier v1 history/preview publications require their matching older code too; the current pipeline intentionally does not load those retired formats. The cleanup removed the last unreferenced objects from that pilot format; all prior publications remain in Git.

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

The validator caps each JSON object below 95 MiB and retained public data below 900 MiB, leaving room under GitHub’s file/site limits. Validation and deployed verification follow every nested archive hash, not just the top-level index.

GitHub’s published-site size limit is documented in [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). The per-object budget stays below GitHub’s [large-file limit](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
