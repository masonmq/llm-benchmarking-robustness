# Annotation study runbook

How to run one weekly cycle of the robustness annotation study, in order, and what to do when something goes wrong.
Commands are run from `robustness_v2/` unless noted; `PY` means `robustness/annotation_app/.venv/bin/python`.

**Rule for every live step** (upload, publish, database change): one person does it, after a second person has OK'd it,
and checks the result right after. Everything else is local and safe to repeat.

## Where things live

| What | Where | In git? |
|---|---|---|
| App code, deployment config, instruction templates | `robustness/annotation_app/` | yes |
| Analysis, report and pilot scripts | `robustness/data/annotators/*.py`, `robustness/data/annotators/code_pilot/*.py` | yes |
| Papers, agent runs, original data | `robustness/data/Annotator-Test/<paper_id>/` (runs + `data/`) | no |
| Roster (usernames ↔ screening IDs, no names/emails), assignment workbook, notes, reports | `robustness/data/annotators/` | no |
| Built sites (public shell only) | `annotation_app/dist/round1/site/<paper_id>/` → GitHub Pages repo, folder `robustness-evaluation/` | Pages repo |
| Built private files (papers, data, previews) | `annotation_app/dist/round1/private/` → Cloudflare R2 bucket `robustness-annotation-files` | no |
| Responses, assignments, visit log | Cloudflare D1 database `robustness-annotations` | no |
| Worker (login, access, saving) | `annotation_app/deployment/cloudflare/worker.js` | yes |

Names and emails never go into files in the repository. Use screening IDs (`ID 7`) and usernames (`cr-…`, `an-…`).
The study password is never written in files or chat; it is shared separately.

## Weekly cycle

### 1. Get the papers in (the slow part)

Each paper folder in `robustness/data/Annotator-Test/<paper_id>/` needs:
- `data/`: the original materials (data, codebook, README, original code) from the paper's own OSF/materials link
  (listed in `robustness/data/_robustness/all_claims.xlsx`, column `original_materials`);
- the agent runs: `1_test_01` … `1_test_05` (or `test_01` …), one per human reanalysis, each with `execution_result.json`,
  `execution_results.json`, `metadata.json`, `universal_schema.json`, `original_paper.pdf` and `candidate_artifacts/…/*.py`.

Pick replacement papers from the paper-picker sheet: same field and same agent-vs-human match ("Agree" = identical
results, marked `*`; otherwise "Disagree"); never a training paper or one already used.

### 2. Check each paper

```bash
cd robustness/annotation_app
$PY check_paper.py ../data/Annotator-Test/<paper_id> [...]
```

`OK` is required. Then read the notes: dropped duplicates (Task 1 removed when Task 1 and Task 2 give identical
results), result-mismatch warnings (check each one is real), and files left out. Also confirm by hand:
- every file has a viewer (no "download only") and documents show real text;
- the data file the agent's code loads is the paper's own (compare with the claim's materials);
- no reviewer-visible text reveals the source (plans/results mentioning "agent", "LLM", model names).

### 3. Update the plan and build

1. Edit `PAPERS` in `robustness/data/annotators/build_round1.py` (week, paper, field, Agree/Disagree, 2 code reviewers,
   1 annotator). Rules: one paper per person per week, nobody reviews a paper twice, ≤ 3 papers per person.
   Then: `$PY robustness/data/annotators/build_round1.py` (rebuilds the workbook and roster).
2. `$PY robustness/annotation_app/roster.py assignments --staff <staff accounts>` (staff/test account names are in the private `robustness/data/annotators/local_accounts.json`, which also holds the site link, worker URL and contact emails; get it from the study team) (writes `assignments.sql`;
   compare it with the previous file: only the intended rows should change).
3. Build each paper:
   ```bash
   cd robustness/annotation_app
   $PY build_pages.py ../data/Annotator-Test/<paper_id> --site-dir dist/round1/site/<paper_id> \
       --private-dir dist/round1/private --api-base <worker URL: api_base in local_accounts.json>
   ```
4. Instructions: `$PY instructions/make_instructions.py --week N --deadline "Wednesday, November 4, 2026"`
   → `robustness/data/annotators/weekN_instructions/pdf/`. Check each PDF's link, username and deadline.

### 4. Go live (ask first, check after each)

```bash
# a. private files (uploads only new/changed files; rerun if any upload fails)
$PY upload_private.py dist/round1/private --bucket robustness-annotation-files --config deployment/cloudflare/wrangler.toml
# b. public site: copy dist/round1/site/<paper_id> into the Pages repo's robustness-evaluation/, commit, push
# c. access list
cd deployment/cloudflare && npx --yes wrangler d1 execute robustness-annotations --remote --command "$(cat ../../../data/annotators/assignments.sql)"
```

Then log in with the test account on every new paper and click through Parts 1–4.

### 5. Send

Drive: each person's PDF in their folder. Email: one email per task type (BCC), with deadline, ~3–4 hours per paper,
password sent separately.

### 6. Monitor (any time, read-only)

```bash
$PY robustness/data/annotators/progress.py --weeks 1,2,3,4      # finished analyses per person
$PY robustness/data/annotators/time_estimates.py --weeks 1,2    # time per analysis
```
The `visits` table in D1 shows first/last time each person opened each paper.

### 7. Report

1. Snapshot responses, then code any new "No/Unclear/Insufficient information" explanations into
   `part2_theme_codes.csv` and code-fidelity ratings below 5 into `part3_theme_codes.csv` (the scripts refuse to run
   until every answer is coded). Part 2 themes describe the plan only (reviewers answer before seeing code).
2. `$PY analyze_report.py --weeks … --responses report/_responses_<date>.json --part2-min-reviewers 3`
3. `$PY analyze_agreement.py --weeks … --responses … --part2-min-reviewers 3`
4. `$PY make_report_docx.py` (generated report) or `$PY update_report_docx.py <edited.docx> <new.docx>` (keeps the
   edited report's wording and layout; only numbers, charts, tables and dated notes change).

Every number in a report comes from these scripts; never type numbers by hand.

## Known problems and fixes

| Problem | How it showed up | Fix |
|---|---|---|
| Run folders one level too deep (`paper/paper/1_test_01`) | `check_paper.py` finds no runs | Move the run folders up one level |
| A run is missing `execution_result.json` or it is empty | Mismatch warnings on every number; blank recorded output | Get the file from whoever ran the agent, or use another paper |
| Agent code file missing from a run | `PROBLEM: Planned code supplied` | Same as above |
| Wrong paper's materials in `data/` | Data/README don't match the claim's OSF link | Replace with the paper's own materials |
| Single "sequential" run (one run, five paths) | One run folder with `_artifacts/`, no `1_test_0x` | Not the round 1 format; use another paper |
| A file has no viewer | `preview_file` returns "download" | Add a viewer in `preview.py` (e.g. SPSS saved as `.dat`, images) |
| Page stuck on "Loading…" | No visit logged for that paper | Usually invalid JSON in the packet (e.g. `NaN`); `build_pages.py` now writes `null` |
| Person sees the sign-in page after logging in | They are not on that paper's access list | Apply `assignments.sql` |
| Annotator finished Part 2 but not Part 4 on the last analysis | Paper shows 9/10 | Ask them to open it and submit Part 4 |
| `wrangler` OAuth error | `code: 7403` or 10000 | Retry; use `--command`, not `--file` |
| `upload_private.py` hangs | Hidden `npx` prompt | Script uses `npx --yes` and a timeout; rerun |
| `git status` fails | `git-lfs: command not found` | Install Git LFS |

## Round 1 decisions to keep

- Neutral wording from week 3 on: reviewers do not see "agent"; analyses are labelled "Analysis A–E".
- Part 2 results use only analyses with all three reviews; Part 3/4 charts use every rating.
- Themes are listed only if they appear in ≥ 3 analyses from ≥ 2 reviewers.
- Final deadline for all round 1 work: Wednesday, November 4.
- Decision log: `robustness/data/annotators/round1_notes.md` (not in git; contains people's situations).
