# Unified Oncology Treatment Database

This repository contains the reproducible, end-to-end implementation of the
multisource oncology treatment database described in the accompanying
manuscript and technical documentation. It standardizes supported source
exports, integrates drug and regimen terminology using the documented source
priority, applies a final RxNorm semantic-validation gate, materializes the
public relational tables, and runs database and file-level QA.

Raw third-party datasets are not distributed here. The repository contains the
code, input contracts, version/checksum manifest, generated public production
tables, RxNorm mapping audits, and QA results needed to understand and
reproduce the publication build.

## Pipeline

```text
HemOnc / CanMED / DrugBank / NCIt / SEER*Rx / AACT
                          |
                          v
              source-specific preprocessing
                          |
                          v
       deterministic priority integration and provenance
                          |
                          v
     RxNorm exact-surface + TTY/relationship validation
                          |
                          v
          SQL production-table materialization
                          |
                          v
              database QA + exported-file QA
```

The drug-source priority is HemOnc, CanMED, DrugBank, RxNorm, NCI
Thesaurus, and SEER*Rx. AACT is retained as a stand-alone clinical-trial
source. RxNorm does not replace the source priority: it acts after integration
as a semantic validator. Only a unique RxNorm `IN` or `MIN` is eligible as a
public canonical drug target. `PIN`, `BN`, product/formulation, and pack
concepts are typed evidence and are traversed through RxNorm relationships;
unresolved or non-unique mappings are stored in `audit/`.

## Publication build

- Build: `publication-build-2026-08-09`
- RxNorm dataset: `03-Aug-2026`
- RxNorm API: `3.1.354`
- Public tables: 11 CSV files under `outputs/production/`
- Canonical drugs: 5,478 (`IN`: 5,307; `MIN`: 171)
- Canonical regimens: 2,151
- QA status: PASS

The exact raw-file versions, dates, filenames, SHA-256 checksums, acquisition
locations, and access restrictions are recorded in
[`metadata/source_manifest.json`](metadata/source_manifest.json).

## Quick start

1. Install Python 3.10 or newer. The pipeline uses only the standard library.
2. Obtain the source files described in [`docs/data_sources.md`](docs/data_sources.md).
3. Place them under `raw/` using the documented folder layout.
4. Copy the source configuration:

   ```bash
   cp config/sources.example.json config/sources.json
   ```

5. Run the full build:

   ```bash
   python3 src/run_pipeline.py
   ```

The first run queries the public RxNorm REST API and creates an ignored local
cache under `cache/rxnorm/`. The build stops if the API release differs from
the publication version, preventing an undocumented mixed-version result.

For absolute paths or nonstandard storage, edit the ignored
`config/sources.json` or pass `--source-config /path/to/config.json`.

## Repository layout

```text
config/               raw-file path contract
metadata/             source, build, RxNorm, and release manifests
src/                  preprocessing, integration, API, materialization, QA
sql/pipeline/         executable production SQL
sql/reference/        original manuscript-era SQL retained for traceability
outputs/production/   public production CSVs
audit/                supporting mapping, crosswalk, and quarantine artifacts
qa/                   integrity checks and machine-readable QA reports
docs/                 data acquisition, methods, schema, and reproducibility
raw/                   ignored local source files
cache/                 ignored local RxNorm API cache
work/                  ignored intermediate tables and SQLite build database
tests/                 unit tests for normalization and schema contracts
```

## Reproducibility commands

```bash
# Full raw-to-production build
python3 src/run_pipeline.py

# Unit tests
python3 -m unittest discover -s tests -v

# Re-run QA on an existing build
make qa

# Intentionally move to a newer RxNorm release
python3 src/run_pipeline.py --refresh-rxnorm --allow-rxnorm-version-change
```

When moving to a newer RxNorm release, update
`metadata/build_release.json`, regenerate all production/audit outputs, and
commit the new version metadata together. See
[`docs/reproducibility.md`](docs/reproducibility.md) for the complete protocol.

## Public and supporting outputs

Only the 11 files under `outputs/production/` are the public production
contract. RxNorm resolution details, legacy-to-canonical crosswalks, semantic
reassignments, and quarantine files under `audit/` are supporting artifacts.
They enable review and reproducibility but are not additional public database
tables. See [`docs/public_schema.md`](docs/public_schema.md) and
[`docs/audit_and_qa.md`](docs/audit_and_qa.md).

## Licensing

The code is available under the MIT License. That license does not grant rights
to third-party source data or override their terms. Users are responsible for
obtaining and using HemOnc, CanMED, DrugBank, RxNorm, NCIt, AACT, and SEER*Rx
under the applicable licenses and citation requirements. See `NOTICE` and the
source manifest before redistributing derived artifacts.

