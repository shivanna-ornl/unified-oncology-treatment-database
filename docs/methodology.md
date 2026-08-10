# Pipeline methodology

## Source-specific preprocessing

- **HemOnc:** active drug and regimen concepts are linked to concept synonyms.
  Primary-systemic regimen components are obtained from `sigs.csv`; condition
  associations come from `pointer.table.csv`.
- **CanMED:** NDC generic names are candidate anchors and brand names are terms.
- **DrugBank:** common names are candidate anchors and the pipe-delimited
  vocabulary synonyms are unnested. Chemical identifiers and structures are
  not used by this pipeline.
- **RxNorm:** active concept catalogs are obtained through the API. Terms that
  overlap the multisource vocabulary participate at Priority 4; full semantic
  validation occurs after integration.
- **NCI Thesaurus:** preferred terms and synonyms are selected only for the
  drug-related semantic types documented in the reference SQL.
- **SEER*Rx:** drug and regimen alternate names and regimen components are
  unnested.
- **AACT:** DRUG interventions are joined to their intervention other names and
  retained as a stand-alone clinical-trial table.

All surface strings are Unicode NFKC-normalized, trimmed, lowercased, and
whitespace-collapsed. Blank values and literal placeholders such as `none`,
`null`, and `n/a` are excluded.

## Priority integration

Drug terms form connected synonym components. Each component's provisional
representative is the lexically stable candidate from the highest-priority
source represented in that component:

1. HemOnc
2. CanMED
3. DrugBank
4. RxNorm
5. NCI Thesaurus
6. SEER*Rx

Provenance is retained for every anchor and term. Regimens use the same
deterministic component construction with HemOnc ahead of SEER*Rx. AACT does
not participate in anchor priority.

## Final RxNorm semantic validation

The final semantic gate runs after cross-source integration and before public
materialization. Exact normalized surfaces are typed using active RxNorm
concepts:

- `IN`: single ingredient; eligible canonical target
- `MIN`: multi-ingredient; eligible canonical target
- `PIN`: precise ingredient; intermediate evidence
- `BN`: brand name; intermediate evidence
- product/formulation TTYs: intermediate evidence
- `GPCK`/`BPCK`: pack evidence; not an ingredient target

For PIN, BN, and product/formulation concepts, the pipeline requests related
IN and MIN concepts. Automatic acceptance requires convergence to exactly one
IN or MIN. An exact semantic result takes precedence over provisional synonym
inheritance. An unmatched term may inherit a provisional anchor only when that
anchor has one validated IN/MIN default. Non-unique or unresolved records are
quarantined.

## Production materialization

The SQL under `sql/pipeline/` creates the same public table/column contract
documented in `public_schema.md`. Materialization enforces one compatible
anchor per normalized term, removes blank/sentinel names, resolves every
foreign key, and emits exact-distinct association rows. RxCUI, TTY, relationship
evidence, and quarantine reasons remain in supporting audit outputs.

The original manuscript-era SQL is retained unchanged under `sql/reference/`
for traceability. The executable implementation uses portable Python and
SQLite while maintaining the documented source roles and public schema.

