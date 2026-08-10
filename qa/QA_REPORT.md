# Production pipeline QA report

**Overall status:** PASS

**RxNorm dataset version:** `03-Aug-2026`  
**RxNorm API version:** `3.1.354`

## Integrity checks

| Check | Issues | Status |
|---|---:|:---:|
| drug_synonym_id_multiple_anchors | 0 | PASS |
| drug_surface_multiple_anchors | 0 | PASS |
| drug_synonym_blank_or_sentinel | 0 | PASS |
| drug_exact_rxnorm_target_conflict | 0 | PASS |
| canonical_drug_not_in_or_min | 0 | PASS |
| drug_synonym_orphan_anchor | 0 | PASS |
| anchor_drug_source_orphan | 0 | PASS |
| drug_synonym_source_orphan | 0 | PASS |
| regimen_synonym_id_multiple_anchors | 0 | PASS |
| regimen_surface_multiple_anchors | 0 | PASS |
| regimen_synonym_blank_or_sentinel | 0 | PASS |
| regimen_synonym_orphan | 0 | PASS |
| regimen_source_exact_duplicates | 0 | PASS |
| regimen_source_orphan | 0 | PASS |
| regimen_drug_orphan | 0 | PASS |
| conditions_regimen_or_source_orphan | 0 | PASS |
| clinical_trial_source_orphan | 0 | PASS |

## Production row counts

| Table | Rows |
|---|---:|
| Anchor_Drugs | 5,478 |
| Anchor_Drugs_And_Synonyms | 31,855 |
| Anchor_Drug_Source | 15,363 |
| Anchor_Drug_Synonym_Source | 40,006 |
| Anchor_Regimen | 2,151 |
| Regimens_And_Synonyms | 3,215 |
| Regimen_Source | 2,302 |
| Anchor_Drugs_To_Regimens | 5,507 |
| Conditions_And_Regimens | 3,361 |
| Clinical_Trials | 265,027 |
| Data_Sources | 7 |

## Audit interpretation

Public production tables contain only mappings that passed the semantic and relational gates. RxNorm evidence, crosswalks, and quarantined rows are stored in `audit/` as supporting artifacts and are not additional production tables.
