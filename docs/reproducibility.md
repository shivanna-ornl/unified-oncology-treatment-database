# Reproducibility protocol

## 1. Obtain and verify inputs

Download each source from the official location listed in `data_sources.md`.
Place the files under `raw/` or create `config/sources.json` with absolute
paths. The source preprocessor calculates SHA-256 hashes and requires an exact
match to `metadata/source_manifest.json`.

This strict check is intentional. A different source snapshot is a different
database release and must be recorded as such rather than silently substituted.

## 2. Configure local paths

```bash
cp config/sources.example.json config/sources.json
```

`config/sources.json` is ignored by Git so absolute paths and local storage
details are not committed.

## 3. Run the build

```bash
python3 src/run_pipeline.py
```

Stages execute in this order:

1. Verify raw-file checksums.
2. Ensure the pinned RxNorm concept catalogs are available through the API.
3. Standardize source-specific drug, regimen, condition, and trial records.
4. Integrate sources with deterministic priority and provenance.
5. Resolve exact RxNorm surfaces and relevant IN/MIN relationships.
6. Execute the SQL staging, semantic-validation, and materialization steps.
7. Export all 11 public CSVs.
8. Export supporting audit files.
9. Run relational and exported-file QA.
10. Write the release and API manifests.

The ignored `work/` directory contains standardized intermediates,
provisional tables, and the temporary SQLite database. The ignored
`cache/rxnorm/` directory contains API responses.

## 4. Verify the result

```bash
python3 -m unittest discover -s tests -v
make qa
```

Review:

- `qa/QA_REPORT.md`
- `qa/qa_report.json`
- `qa/export_verification.json`
- `metadata/release_manifest.json`

The release manifest records row counts and SHA-256 hashes for every production
and audit CSV.

## RxNorm release behavior

The pipeline compares the API response with `metadata/build_release.json` and
stops if the dataset or API version differs. This prevents a current API
response from being combined with publication-era inputs without disclosure.

To intentionally create a new version:

```bash
python3 src/run_pipeline.py \
  --refresh-rxnorm \
  --allow-rxnorm-version-change
```

Then update `metadata/build_release.json`, review the generated
`metadata/rxnorm_api_manifest.json`, regenerate all outputs, run QA, and commit
the metadata and outputs together. The RxNorm API exposes its current release;
it is not a permanent archive for historical API builds.

## Determinism

Within a fixed set of input checksums and RxNorm API responses, terms and IDs
are ordered deterministically. Source-priority representatives, public IDs,
association rows, and exports are sorted before writing. Timestamps in
manifests will differ between runs; CSV content hashes should remain stable.

