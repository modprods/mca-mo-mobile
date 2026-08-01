## Why

Form submissions are logged to a live SharePoint Excel table without a submission timestamp, and evolving the row shape in place risks disrupting the production workbook. We need a dated row schema on a new table, a safe backfill from `form.log`, and an env-based cutover so live writes stay on the original table until ready.

## What Changes

- Prepend a real Excel date/time (`date`) to each SharePoint form submission row (ISO datetime via Microsoft Graph).
- Update the canonical column order to: `date, age, send_screenshot, email, send_further_emails`.
- Add `backfill-excel.py` to parse `form.log` and append historical rows to table `FormSubmissions-v02` (client-created sheet/table; app does not create worksheets or tables).
- Keep live appends controlled solely by `TABLE_NAME` so production can remain on `FormSubmissions` until cutover to `FormSubmissions-v02`.
- Document cutover: flip `TABLE_NAME`; leave the original sheet/table as an archive (no dual-write, no code references to the old table name beyond config).

## Capabilities

### New Capabilities
- `sharepoint-form-submissions`: Append and read form submission rows in the configured SharePoint Excel table, including the `date` column and `TABLE_NAME`-based targeting.
- `form-log-backfill`: CLI backfill of `form.log` lines into a target Excel table (default `FormSubmissions-v02`) without changing live app write targets.

### Modified Capabilities

## Impact

- `main.py`: row builder, `FORM_TABLE_HEADERS`, SharePoint append path (already uses `TABLE_NAME`).
- New `backfill-excel.py`; tests for log parsing, row shape, and backfill behaviour.
- `env.sample` / ops notes for `TABLE_NAME` cutover; `read-excel.py` continues to follow `TABLE_NAME`.
- Client prerequisite: worksheet `Submissions-v02` with Excel table `FormSubmissions-v02` and headers including a Date Time–formatted `date` column.
- No new Python dependencies; same Graph client-credentials auth.
