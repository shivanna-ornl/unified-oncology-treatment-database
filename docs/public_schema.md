# Public production schema

Only the CSVs in `outputs/production/` constitute the public database. Column
order is part of the release contract.

## Tables

### `Anchor_Drugs`

| Column | Meaning |
|---|---|
| `anchor_drug_id` | Stable release-local primary key |
| `anchor_drug_name` | Canonical RxNorm IN or MIN name |

### `Anchor_Drugs_And_Synonyms`

| Column | Meaning |
|---|---|
| `synonym_id` | Synonym primary key |
| `anchor_drug_id` | FK to `Anchor_Drugs` |
| `synonym_name` | Normalized synonym surface |

### `Anchor_Drug_Source`

| Column | Meaning |
|---|---|
| `source_id` | FK to `Data_Sources` |
| `anchor_drug_id` | FK to `Anchor_Drugs` |

### `Anchor_Drug_Synonym_Source`

| Column | Meaning |
|---|---|
| `source_id` | FK to `Data_Sources` |
| `synonym_id` | FK to `Anchor_Drugs_And_Synonyms` |

### `Anchor_Regimen`

| Column | Meaning |
|---|---|
| `regimen_id` | Regimen primary key |
| `regimen_name` | Canonical regimen name |

### `Regimens_And_Synonyms`

| Column | Meaning |
|---|---|
| `regimen_synonym_id` | Regimen synonym row key |
| `regimen_synonym` | Normalized regimen synonym |
| `source_id` | FK to `Data_Sources` |
| `regimen_id` | FK to `Anchor_Regimen` |

### `Regimen_Source`

| Column | Meaning |
|---|---|
| `regimen_id` | FK to `Anchor_Regimen` |
| `source_id` | FK to `Data_Sources` |

### `Anchor_Drugs_To_Regimens`

| Column | Meaning |
|---|---|
| `regimen_id` | FK to `Anchor_Regimen` |
| `anchor_drug_id` | FK to `Anchor_Drugs` |
| `source_id` | FK to `Data_Sources` |

### `Conditions_And_Regimens`

| Column | Meaning |
|---|---|
| `condition_id` | Condition-association row key |
| `condition_name` | Normalized HemOnc condition name |
| `regimen_id` | FK to `Anchor_Regimen` |
| `source_id` | FK to `Data_Sources` |

### `Clinical_Trials`

| Column | Meaning |
|---|---|
| `row_id` | Release-local row key |
| `interventions_id` | AACT intervention identifier |
| `clinical_trial_id` | ClinicalTrials.gov NCT identifier |
| `name` | Intervention name |
| `other_name` | AACT intervention other name |
| `source_id` | FK to `Data_Sources` |

### `Data_Sources`

| Column | Meaning |
|---|---|
| `source_id` | Source primary key |
| `dataset_name` | Source name |
| `dataset_link` | Acquisition/documentation URL |
| `dataset_description` | Short source description |

## Relationships

```text
Data_Sources 1--* Anchor_Drug_Source *--1 Anchor_Drugs
Data_Sources 1--* Anchor_Drug_Synonym_Source *--1 Anchor_Drugs_And_Synonyms
Anchor_Drugs 1--* Anchor_Drugs_And_Synonyms

Data_Sources 1--* Regimen_Source *--1 Anchor_Regimen
Anchor_Regimen 1--* Regimens_And_Synonyms
Anchor_Regimen 1--* Anchor_Drugs_To_Regimens *--1 Anchor_Drugs
Anchor_Regimen 1--* Conditions_And_Regimens
Data_Sources 1--* Clinical_Trials
```

## Expected publication-build row counts

| Table | Rows |
|---|---:|
| `Anchor_Drugs` | 5,478 |
| `Anchor_Drugs_And_Synonyms` | 31,855 |
| `Anchor_Drug_Source` | 15,363 |
| `Anchor_Drug_Synonym_Source` | 40,006 |
| `Anchor_Regimen` | 2,151 |
| `Regimens_And_Synonyms` | 3,215 |
| `Regimen_Source` | 2,302 |
| `Anchor_Drugs_To_Regimens` | 5,507 |
| `Conditions_And_Regimens` | 3,361 |
| `Clinical_Trials` | 265,027 |
| `Data_Sources` | 7 |

