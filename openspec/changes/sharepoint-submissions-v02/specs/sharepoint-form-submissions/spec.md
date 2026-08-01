## Purpose

Records landing-page form submissions into a configured SharePoint Excel table via Microsoft Graph, including a real submission timestamp column.

## ADDED Requirements

### Requirement: Submission row includes date and form fields
The system SHALL append each successful form submission as one Excel table row with columns in this order: `date`, `age`, `send_screenshot`, `email`, `send_further_emails`.

#### Scenario: Row values for a complete submission
- **WHEN** a submission is processed with age, optional email, and MCA updates preference
- **THEN** the appended row MUST contain a real date/time value for `date`, the age label, whether a screenshot email was requested, the email address (empty when none), and the further-emails preference

### Requirement: Date column is a real Excel date/time
The system MUST write `date` as a real Excel date/time value (ISO-8601 datetime suitable for Graph workbook cells), not a human-formatted display string.

#### Scenario: Timestamp written for Graph
- **WHEN** a submission row is built for SharePoint append
- **THEN** `date` MUST be an ISO-8601 datetime representing the submission processing time in UTC

### Requirement: Target table is configured by TABLE_NAME
The system SHALL append and read SharePoint form rows using the Excel table named by the `TABLE_NAME` environment variable within the configured workbook.

#### Scenario: Live writes follow TABLE_NAME
- **WHEN** `TABLE_NAME` is set to `FormSubmissions`
- **THEN** appends MUST target the `FormSubmissions` table and MUST NOT write to `FormSubmissions-v02`

#### Scenario: Cutover via config
- **WHEN** `TABLE_NAME` is set to `FormSubmissions-v02`
- **THEN** appends MUST target the `FormSubmissions-v02` table

### Requirement: CSV export header matches table columns
When exporting table rows as CSV, the system SHALL emit a header row of `date,age,send_screenshot,email,send_further_emails` followed by the data rows.

#### Scenario: CSV header
- **WHEN** form submission rows are written as CSV
- **THEN** the first line MUST be `date,age,send_screenshot,email,send_further_emails`

### Requirement: No workbook structure creation
The system MUST NOT create SharePoint worksheets or Excel tables; the client is responsible for creating sheet `Submissions-v02` and table `FormSubmissions-v02` with the required headers before use.

#### Scenario: Missing target table
- **WHEN** append is attempted against a table that does not exist
- **THEN** the operation MUST fail with an error suitable for logging (and existing submission error handling), without attempting to create the table
