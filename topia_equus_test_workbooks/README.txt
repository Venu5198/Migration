Topia-to-Equus UI Test Workbooks
================================

All records are synthetic test data, not real employee information.
Each workbook uses the same small, controlled four-row header shape as the previously exercised fixture.

01_valid_basic.xlsx — basic two-row upload and migration.
02_valid_numeric_ids.xlsx — numeric-looking IDs and mixed date formats.
03_valid_blank_optional_fields.xlsx — blank optional fields/null handling.
04_negative_missing_employee_id.xlsx — negative validation test; should not be reported as reconciliation-passed if the required ID is rejected.
05_valid_many_rows.xlsx — ten rows for output counts, report UI, and history testing.

Important: These small fixtures contain only eight example fields. They are for initial UI/API testing and may not satisfy every requirement of a full production Topia export. Expected outcomes depend on the current parser/mapping configuration. Do not use the negative fixture in production.
