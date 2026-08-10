# Audit and QA artifacts

Audit files support review of the public build. They are not additional public
production tables.

## Audit directory

| File | Role |
|---|---|
| `rxnorm_surface_resolution.csv` | Exact surface matches, candidate RxCUIs/TTYs, relationship rule, and accepted IN/MIN target |
| `canonical_drug_concept.csv` | Internal public-anchor to RxCUI/TTY crosswalk |
| `legacy_drug_anchor_crosswalk.csv` | Provisional integrated anchor to validated public anchor |
| `legacy_anchor_default.csv` | Unique IN/MIN default evidence for provisional anchors |
| `audit_rxnorm_semantic_overrides.csv` | Exact term evidence that differs from provisional inheritance |
| `audit_drug_term_quarantine.csv` | Drug terms withheld from public materialization and reason |
| `audit_legacy_drug_anchor_quarantine.csv` | Provisional anchors without one eligible IN/MIN default |
| `audit_regimen_synonym_quarantine.csv` | Invalid or non-unique regimen synonym rows |
| `audit_regimen_drug_quarantine.csv` | Regimen-drug rows whose keys could not be validated |
| `missing_regimen_drug_terms.csv` | Source regimen components absent from the provisional drug graph |

## QA directory

- `qa_checks.csv`: zero-tolerance relational and semantic checks.
- `qa_report.json`: complete database-level QA, schema checks, row counts, TTY
  counts, and quarantine summaries.
- `QA_REPORT.md`: human-readable QA summary.
- `export_verification.json`: independent checks over the written CSV headers,
  row counts, hashes, ambiguity, semantics, duplicates, and foreign keys.

The pipeline exits nonzero if database-level or exported-file QA fails.

