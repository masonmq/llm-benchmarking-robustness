# Robustness annotation app

This draft converts a paper folder into one compact form containing one page per task-specific analysis. It reads each run's `universal_schema.json` and `execution_results.json`, performs non-judgment preflight checks, and autosaves human responses to SQLite.

Run the Zunick example from the repository root:

```bash
python robustness/annotation_app/server.py \
  robustness/data/Annotator-Test/Zunick_JournExpSocPsych_2017_zlw
```

Install the optional preview readers and start with pilot password protection:

```bash
pip install -r robustness/annotation_app/requirements.txt
ANNOTATION_PASSWORD='choose-a-long-password' ANNOTATION_SESSION_SECRET='another-long-random-secret' python robustness/annotation_app/server.py \
  robustness/data/Annotator-Test/Zunick_JournExpSocPsych_2017_zlw
```

Then open <http://127.0.0.1:8000>. Use `--host 0.0.0.0` only on a trusted network. Without `ANNOTATION_PASSWORD`, the app retains its unauthenticated local-development mode.

To inspect the extracted review data without running the form:

```bash
python robustness/annotation_app/extract.py PAPER_FOLDER --output review_packet.json
```

Expected structure: one paper directory containing run subdirectories. Each run must contain `universal_schema.json` and `execution_results.json`; code may be anywhere below that run. Five runs produce ten form pages (Task1 and Task2 per run).

The database defaults to `robustness/annotation_app/annotations.sqlite3`. Supply `--database PATH` to put it elsewhere. Progress is keyed by paper, annotator name, and analysis ID.

The extractor automates identity, execution-status, code-presence, filename, and path-name checks. Sample validity, methodological defensibility, code semantics, and conclusion validity remain human judgments.

The form uses four-part staged disclosure: source materials, the proposed analysis, implementation code, and execution results/conclusion. The focal claim comes from `the claim from SCORE collection` and Task 2's instruction comes from `instructions_for_task_2` in `data/_robustness/all_claims.xlsx`, matched case-insensitively on `paper_id`.

Integrated viewers support PDF; line-numbered Python/R/Stata/SAS/text; expandable JSON; searchable CSV/Excel/SPSS/Stata/SAS/R-data tables; and DOCX converted to safe HTML. Previews are limited to 100 rows and 100 columns, while original downloads remain available. Password mode protects the APIs and files with an HTTP-only session cookie. This shared-password implementation is appropriate only for a pilot; an internet deployment should terminate HTTPS and use individual magic-link identities.

## GitHub Pages + Cloudflare free deployment

GitHub Pages hosts only the public application shell. Papers, data, generated previews, and responses remain behind the authenticated Cloudflare Worker. The browser stores a signed 30-day login token; no protected files are copied into the Pages site.

1. Create a Cloudflare D1 database and private R2 bucket named `robustness-annotation-files`.
2. Copy `deployment/cloudflare/wrangler.example.toml` to `wrangler.toml` (not in git) and fill in the D1 ID, GitHub Pages origin and pilot settings.
3. From `deployment/cloudflare`, initialize the database and secrets:

```bash
npx wrangler d1 execute robustness-annotations --remote --file schema.sql
npx wrangler secret put ANNOTATION_PASSWORD
npx wrangler secret put SESSION_SECRET
npx wrangler secret put ALLOWED_ANNOTATORS
npx wrangler deploy
```

Set `ALLOWED_ANNOTATORS` to a comma-separated list such as
`annotator01,annotator02,annotator03`. Matching ignores capitalization and outer
spaces, but responses are always stored under the canonical spelling in this list.
When the allowlist is set, sessions for names outside it stop working.

4. Build one paper locally, using the deployed Worker URL:

```bash
python robustness/annotation_app/build_pages.py PAPER_FOLDER \
  --api-base https://robustness-annotation-api.YOUR-SUBDOMAIN.workers.dev
python robustness/annotation_app/upload_private.py robustness/annotation_app/dist/private \
  --bucket robustness-annotation-files \
  --config robustness/annotation_app/deployment/cloudflare/wrangler.toml
```

5. Publish `dist/site` under the desired directory of the `github.io` repository. Alternatively, copy `deployment/github-pages.yml.example` to `.github/workflows/annotation-pages.yml`, set repository variables `PAPER_FOLDER` and `ANNOTATION_API_URL`, and add the Cloudflare account/token secrets.

The build defaults to twenty 100-row preview pages per dataset so deployment size stays bounded. Increase `--max-pages` when fuller browsing is justified. Original authenticated downloads are unaffected by this preview cap.

## Annotator roles, roster, and assignments

Usernames starting with `an-` skip Part 3 (code review) and go from Part 2 straight to Part 4. All other usernames (`cr-`, pilot, and local development) review code. Both `server.py` and `deployment/cloudflare/worker.js` enforce this, and the review rules in the two files must be kept in sync.

`roster.py` manages usernames in `robustness/data/annotators/annotator_roster.xlsx`. That file is gitignored because it holds names and emails.

```bash
python robustness/annotation_app/roster.py generate --reviewers 15 --annotators 15
python robustness/annotation_app/roster.py allowed --extra PILOT_NAMES...   # paste into: npx wrangler secret put ALLOWED_ANNOTATORS
python robustness/annotation_app/roster.py assignments                      # prints the wrangler command that applies it
```

To limit each annotator to the papers in the roster's `assigned_papers` column, first create the `assignments` table (rerun `schema.sql`) and apply the SQL generated by `roster.py assignments`. Then set `ENFORCE_ASSIGNMENTS = "true"` in `wrangler.toml` and redeploy. Rerun `roster.py assignments` and apply it whenever assignments change; this needs no redeploy.

Tests: `python -m unittest test_extract test_server` from this folder, and `node --test robustness/annotation_app/deployment/cloudflare/worker.test.mjs` from the repository root.

Annotator instruction templates for each role are in `instructions/`.

## Export responses

Responses are stored in the Cloudflare D1 `responses` table. Export all papers to a
flat CSV (one row per annotator and analysis) with:

```bash
python robustness/annotation_app/export_responses.py
```

Use `--paper PAPER_ID` to export a single paper. Run `npx wrangler login` first if
the Cloudflare CLI session has expired.
