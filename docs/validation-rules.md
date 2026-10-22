# Validation rules

Current deterministic checks report empty sheets, missing/duplicate headers, duplicate populated rows, null counts, and structural empty rows. Empty rows are counted rather than silently discarded.

The following rules are deliberately unresolved and cannot be assumed: country normalization code system, employment-status vocabulary, required employee/assignment keys, placeholder keys such as `NEW`, assignment composite key, and job-title/job-level semantics. Unknown country/status values must retain raw values and be flagged, not normalized to defaults, when the related transformation phase is added.

