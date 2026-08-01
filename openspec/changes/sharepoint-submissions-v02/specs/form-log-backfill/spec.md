## Purpose

Backfills historical landing-page form submissions from the server `form.log` into a SharePoint Excel table for migration and verification before cutover.

## ADDED Requirements

### Requirement: Backfill CLI reads form.log and appends rows
The system SHALL provide a `backfill-excel.py` CLI that reads a `form.log` file, parses each transaction line, and appends corresponding rows to a SharePoint Excel table.

#### Scenario: Successful backfill line
- **WHEN** the CLI is run against a form.log containing a valid transaction line
- **THEN** one row MUST be appended with `date` from the log timestamp and `age`, `send_screenshot`, `email`, and `send_further_emails` from the parsed fields

### Requirement: Default target table is FormSubmissions-v02
Unless overridden, the backfill CLI MUST append to the Excel table `FormSubmissions-v02` and MUST NOT change the live application's configured `TABLE_NAME`.

#### Scenario: Default table target
- **WHEN** the backfill CLI runs without an explicit table override
- **THEN** rows MUST be written to `FormSubmissions-v02`

### Requirement: Log sentinel email maps to empty
When parsing `form.log`, the system MUST treat `email='(none)'` as an empty email value in the Excel row.

#### Scenario: No-email log line
- **WHEN** a log line has `email='(none)'`
- **THEN** the appended row's email field MUST be empty

### Requirement: Invalid lines are skipped with logging
The backfill CLI MUST skip unparseable lines, log them, and continue processing remaining lines.

#### Scenario: Malformed line
- **WHEN** a form.log line does not match the expected transaction format
- **THEN** that line MUST NOT be appended and processing MUST continue for subsequent lines
