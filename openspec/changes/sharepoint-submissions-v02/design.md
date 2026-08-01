## Context

See proposal.md for motivation. Today the app appends four-column rows to Graph path `/sites/{SITE_ID}/drive/root:/{LOCATION}:/workbook/tables/{TABLE_NAME}/rows/add` with `TABLE_NAME=FormSubmissions`. Successful submissions are also appended to local `form.log` as ISO timestamps plus key=value fields. Excel table/sheet creation is out of API scope for this project (Sites.Selected write to existing workbook content only as used today).

## Goals / Non-Goals

**Goals:**
- Extend the append row shape with a real Excel datetime `date` column.
- Add an offline backfill path from `form.log` into client-created `FormSubmissions-v02`.
- Keep production writes on the current table until an env cutover.

**Non-Goals:**
- Creating worksheets or tables via Graph.
- Dual-writing to old and new tables.
- Changing `form.log` line format (beyond continuing to use ISO timestamps).
- Backfilling or rewriting historical rows in the live `FormSubmissions` table.
- Idempotent/resume-safe backfill (operator clears target table or accepts duplicates on re-run).

## Decisions

### 1. Cutover knob = existing `TABLE_NAME`
- **Choice:** Live app and `read-excel.py` keep using `TABLE_NAME`; cutover is set env to `FormSubmissions-v02` and restart.
- **Why:** Already wired; no code fork for old vs new table names.
- **Alternative:** Hard-code v02 or add a separate `WRITE_TABLE_NAME` — rejected as redundant.

### 2. Backfill targets v02 explicitly
- **Choice:** `backfill-excel.py` defaults to table `FormSubmissions-v02` (optional CLI/env override for testing), independent of the app's `TABLE_NAME`.
- **Why:** Lets operators migrate/test while production `.env` still points at `FormSubmissions`.
- **Alternative:** Require temporarily flipping `TABLE_NAME` for backfill — rejected (too easy to leave prod writing to v02 mid-test, or block backfill while prod must stay on v1).

### 3. Date value format for Graph
- **Choice:** Write UTC ISO-8601 (e.g. `2026-08-01T06:21:43Z` or offset form Graph accepts) so Excel stores a real date/time; display format is set on the column in the workbook by the client.
- **Why:** Excel best practice; human-readable strings sort/filter poorly.
- **Alternative:** Pre-formatted `YYYY-MM-DD HH:MM:SS` string — rejected per product decision.

### 4. Shared row builder
- **Choice:** One pure function builds `[date, age, send_screenshot, email, send_further_emails]` used by `/process-submission` and backfill (backfill supplies date from the log line).
- **Why:** Single column contract; tests cover both paths.
- **Alternative:** Separate backfill-only mapping — rejected (drift risk).

### 5. form.log parsing
- **Choice:** Parse lines matching the existing transaction pattern: `{iso} age='…' send_screenshot={True|False} email='…' send_further_emails={True|False}`; map `email='(none)'` → `""`.
- **Why:** Matches current `log_form_transaction` output (~1k+ lines already).
- **Alternative:** Only backfill from live Excel — rejected (no `date` on v1; log is source of truth for timestamps).

### 6. Sheet vs table naming
- **Choice:** Client sheet name `Submissions-v02`; Excel table name `FormSubmissions-v02`. Code only ever addresses the table name via Graph.
- **Why:** Graph `tables/{name}` API is table-scoped; sheet name is a human/org convention only.

## Risks / Trade-offs

- [Re-running backfill duplicates rows] → Document clear-table-first; no dedupe in v1 of the script.
- [Client table missing or wrong headers] → Append fails; surface clear errors; do not auto-create structure.
- [Graph datetime parsing quirks] → Verify one manual/test row in Excel shows as Date Time before bulk backfill; adjust ISO form if needed.
- [Prod accidentally pointed at v02 early] → Keep default/sample docs at `FormSubmissions` until cutover checklist; backfill uses separate default.
- [Large form.log (~1k+ rows) rate/timeouts] → Use sequential appends with logging; consider batching later only if needed.

## Migration Plan

1. Client creates sheet `Submissions-v02` and table `FormSubmissions-v02` with headers `date, age, send_screenshot, email, send_further_emails`; format `date` as Date Time.
2. Deploy code that can write the five-column shape (prod `.env` still `TABLE_NAME=FormSubmissions` until step 5 — **note:** five-column appends to the four-column live table will fail; see below).
3. Run `backfill-excel.py` against production `form.log` into `FormSubmissions-v02`; spot-check with `TABLE_NAME=FormSubmissions-v02` + `read-excel.py` (or Excel UI).
4. Optionally run a non-prod instance with `TABLE_NAME=FormSubmissions-v02` to verify live appends.
5. Cutover: set production `TABLE_NAME=FormSubmissions-v02`, restart; leave old sheet/table untouched as archive.
6. Rollback: set `TABLE_NAME` back to `FormSubmissions` (accept that post-cutover rows on v02 are not on v1; four-column shape mismatch if code already emits `date`).

**Deploy sequencing note:** Shipping the five-column row builder while prod still targets the four-column `FormSubmissions` table is incompatible. Prefer either (a) deploy backfill + row-builder only after cutover env is ready and use a short maintenance window, or (b) gate the `date` column on whether `TABLE_NAME` is the v02 table / an explicit flag. Prefer (b) only if zero-downtime on the old table is required during testing; otherwise cutover `TABLE_NAME` in the same release that enables the new row shape, after backfill is verified.

## Open Questions

- None that block implementation; confirm Graph-accepted datetime string with a single test append during apply if needed.
