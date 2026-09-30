# Synthetic demo data

These files contain no real student records. Select the matching built-in example before importing so the column headers and units match.

- `acceleration.csv`: x seconds, y m/s²; square x, linear fit, fixed zero with a rationale. Expected coefficient 0.021 m/s⁴; intentionally claim m/s² to demonstrate the finding.
- `spring.csv`: x centimeters, y newtons; identity x, linear/free fit. Coefficient is reported in N/m after canonical conversion.
- `reciprocal-domain.csv`: x seconds, y meters; reciprocal transform includes zero and must reject without dropping a row.

The app's `apps/web/lib/examples.ts` is the authoritative seed fixture for its three selectable examples. Additional origin-shift, constant-y, and offset-temperature cases are exercised in backend tests.
