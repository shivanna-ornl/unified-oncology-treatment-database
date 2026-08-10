# Required data sources

Raw datasets are deliberately excluded from Git. The publication build checks
every required file against the SHA-256 value in
`metadata/source_manifest.json` before preprocessing.

## Required files

| Source | Publication release/snapshot | Obtain from | Access and redistribution | Expected local path |
|---|---|---|---|---|
| HemOncKB | 2024-06-20 ontology export; archive assembled 2024-07-10 | [HemOncKB availability and Dataverse link](https://hemonc.org/wiki/HemOncKB) | Full data are available for academic/non-commercial use. Review the release-specific CC BY and CC BY-NC-SA terms. | `raw/hemonc/dataverse_files.zip` |
| CanMED NDC | Version 1.24.0; manuscript access date 2024-10-01 | [CanMED](https://seer.cancer.gov/oncologytoolbox/canmed/) | US Government work/public domain; follow SEER citation guidance. | `raw/canmed/ndconc_results.csv` |
| DrugBank Vocabulary | 2024 manuscript-build vocabulary export; the file does not encode an internal release number | [DrugBank releases](https://go.drugbank.com/releases/latest#open-data) | Obtain directly from DrugBank. Do not commit or redistribute the downloaded file unless the applicable license permits it. | `raw/drugbank/drugbank vocabulary.csv` |
| NCI Thesaurus | 24.05d | [NCI EVS FTP](https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/) | CC BY 4.0 with attribution. | `raw/ncit/Thesaurus_24.05d.FLAT.zip` |
| AACT interventions | 2024-07-10 snapshot | [AACT snapshots](https://aact.ctti-clinicaltrials.org/downloads/snapshots) | Publicly downloadable; follow AACT and ClinicalTrials.gov citation guidance. | `raw/aact/interventions.txt` |
| AACT intervention other names | 2024-07-10 snapshot | [AACT snapshots](https://aact.ctti-clinicaltrials.org/downloads/snapshots) | Same as above. | `raw/aact/intervention_other_names.txt` |
| SEER*Rx drugs | Downloaded snapshot dated 2024-07-10; no formal version in CSV | [SEER*Rx downloads](https://seer.cancer.gov/seertools/seerrx/) | US Government/public-domain resource; follow SEER citation guidance. | `raw/seer_rx/drugs.csv` |
| SEER*Rx regimens | Downloaded snapshot dated 2024-07-10; no formal version in CSV | [SEER*Rx downloads](https://seer.cancer.gov/seertools/seerrx/) | Same as above. | `raw/seer_rx/regimens.csv` |

CanMED HCPCS was archived with the research inputs but is not required by the
current NDC-based transformation. Its archived checksum is retained as an
optional-input note in the source manifest.

## HemOnc archive members used

The preprocessor reads these members directly from `dataverse_files.zip`:

- `2024-06-20 20-00-29.concept_stage.csv`
- `2024-06-20 20-00-30.concept_synonym_stage.csv`
- `Tables/sigs.csv`
- `Tables/pointer.table.csv`

The archive does not need to be unpacked.

## AACT preparation

The build requires the pipe-delimited `interventions` and
`intervention_other_names` tables. If starting from an AACT PostgreSQL dump,
export those two tables with their original column names and `|` delimiter.
AACT publishes nightly database snapshots; use the archived 2024-07-10 files
and manifest checksums to reproduce this build exactly.

## RxNorm API

RxNorm is retrieved through the public REST API implemented in
`src/rxnorm_api.py`; no RxNorm RRF files are required. The publication build
used:

- Dataset version: `03-Aug-2026`
- API version: `3.1.354`
- API root: `https://rxnav.nlm.nih.gov/REST`
- Version endpoint: `https://rxnav.nlm.nih.gov/REST/version.json`

The API documentation states that the API returns NLM's non-proprietary
RxNorm vocabulary and generally does not require a separate API license. Full
downloadable RxNorm/UMLS files require acceptance of the UMLS license. Review
the [RxNorm API documentation](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html)
and [RxNorm FAQ](https://www.nlm.nih.gov/research/umls/rxnorm/faq.html).

## Folder tree

```text
raw/
  hemonc/dataverse_files.zip
  canmed/ndconc_results.csv
  drugbank/drugbank vocabulary.csv
  ncit/Thesaurus_24.05d.FLAT.zip
  aact/interventions.txt
  aact/intervention_other_names.txt
  seer_rx/drugs.csv
  seer_rx/regimens.csv
```

