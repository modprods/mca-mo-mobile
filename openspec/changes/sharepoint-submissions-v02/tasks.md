## 1. Row shape and headers

- [ ] 1.1 Update `FORM_TABLE_HEADERS` to `date, age, send_screenshot, email, send_further_emails`
- [ ] 1.2 Extend `form_submission_row_values` (or successor) to accept a UTC datetime and prepend an ISO-8601 `date` value suitable for Graph Excel date/time cells
- [ ] 1.3 Wire `/process-submission` to stamp UTC now when building the SharePoint row
- [ ] 1.4 Update unit tests for row values, CSV headers, and SharePoint append payload shape

## 2. form.log backfill CLI

- [ ] 2.1 Add pure parser for `form.log` transaction lines (ISO timestamp + age/send_screenshot/email/send_further_emails); map `email='(none)'` to empty string
- [ ] 2.2 Add `backfill-excel.py` that reads a log path, parses lines, builds five-column rows, and appends to table `FormSubmissions-v02` by default (overrideable without changing app `TABLE_NAME`)
- [ ] 2.3 Skip malformed lines with logging and continue; reuse existing Graph auth/append helpers where practical
- [ ] 2.4 Add tests for parser and backfill orchestration (mocked Graph)

## 3. Config and docs

- [ ] 3.1 Update `env.sample` to document `TABLE_NAME` cutover (`FormSubmissions` → `FormSubmissions-v02`) and that the client creates sheet/table manually
- [ ] 3.2 Document deploy sequencing: verify backfill on `FormSubmissions-v02` before flipping production `TABLE_NAME`; ship five-column live appends only when cutting over (same release as env flip) so the four-column live table is not written with five values
- [ ] 3.3 Confirm `read-excel.py` still follows `TABLE_NAME` and emits the new CSV header

## 4. Verification

- [ ] 4.1 Run unit tests for SharePoint/backfill changes
- [ ] 4.2 Smoke-check (when credentials/workbook available): one test append + backfill sample into `FormSubmissions-v02` and confirm `date` appears as Excel date/time
