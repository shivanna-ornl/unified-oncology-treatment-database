-- Materialize the unchanged public production schema from validated staging.

DROP TABLE IF EXISTS production_Data_Sources;
CREATE TABLE production_Data_Sources AS
SELECT
    CAST(source_id AS INTEGER) AS source_id,
    dataset_name,
    dataset_link,
    dataset_description
FROM integrated_Data_Sources
ORDER BY CAST(source_id AS INTEGER);

DROP TABLE IF EXISTS production_Anchor_Drugs;
CREATE TABLE production_Anchor_Drugs AS
SELECT anchor_drug_id, canonical_drug_name AS anchor_drug_name
FROM canonical_drug_concept
ORDER BY anchor_drug_id;

DROP TABLE IF EXISTS production_Anchor_Drugs_And_Synonyms;
CREATE TABLE production_Anchor_Drugs_And_Synonyms AS
WITH candidates AS (
    SELECT DISTINCT
        c.anchor_drug_id,
        v.normalized_surface_form AS synonym_name
    FROM Validated_Drug_Staging_Table v
    JOIN canonical_drug_concept c USING (canonical_rxcui)
    WHERE is_valid_surface(v.normalized_surface_form) = 1
      AND v.normalized_surface_form <> c.canonical_drug_name
), unique_surfaces AS (
    SELECT synonym_name
    FROM candidates
    GROUP BY synonym_name
    HAVING COUNT(DISTINCT anchor_drug_id) = 1
)
SELECT
    ROW_NUMBER() OVER (ORDER BY c.synonym_name, c.anchor_drug_id) AS synonym_id,
    c.anchor_drug_id,
    c.synonym_name
FROM candidates c
JOIN unique_surfaces u USING (synonym_name)
ORDER BY synonym_id;

DROP TABLE IF EXISTS production_Anchor_Drug_Source;
CREATE TABLE production_Anchor_Drug_Source AS
WITH valid_sources AS (
    SELECT DISTINCT
        c.anchor_drug_id,
        CAST(d.source_id AS INTEGER) AS source_id
    FROM Drug_Staging_Table d
    JOIN Validated_Drug_Staging_Table v
      ON v.legacy_anchor_drug_id = d.legacy_anchor_drug_id
     AND v.term_kind = d.term_kind
     AND COALESCE(v.legacy_synonym_id, -1) = COALESCE(d.legacy_synonym_id, -1)
     AND v.normalized_surface_form = d.normalized_surface_form
    JOIN canonical_drug_concept c USING (canonical_rxcui)
    JOIN production_Data_Sources s
      ON s.source_id = CAST(d.source_id AS INTEGER)
)
SELECT source_id, anchor_drug_id
FROM valid_sources
ORDER BY anchor_drug_id, source_id;

DROP TABLE IF EXISTS production_Anchor_Drug_Synonym_Source;
CREATE TABLE production_Anchor_Drug_Synonym_Source AS
WITH synonym_lookup AS (
    SELECT synonym_id, anchor_drug_id, synonym_name
    FROM production_Anchor_Drugs_And_Synonyms
), source_candidates AS (
    SELECT DISTINCT
        CAST(d.source_id AS INTEGER) AS source_id,
        l.synonym_id
    FROM Drug_Staging_Table d
    JOIN Validated_Drug_Staging_Table v
      ON v.legacy_anchor_drug_id = d.legacy_anchor_drug_id
     AND v.term_kind = d.term_kind
     AND COALESCE(v.legacy_synonym_id, -1) = COALESCE(d.legacy_synonym_id, -1)
     AND v.normalized_surface_form = d.normalized_surface_form
    JOIN canonical_drug_concept c USING (canonical_rxcui)
    JOIN synonym_lookup l
      ON l.anchor_drug_id = c.anchor_drug_id
     AND l.synonym_name = v.normalized_surface_form
    JOIN production_Data_Sources s
      ON s.source_id = CAST(d.source_id AS INTEGER)
)
SELECT source_id, synonym_id
FROM source_candidates
ORDER BY synonym_id, source_id;

DROP TABLE IF EXISTS production_Anchor_Regimen;
CREATE TABLE production_Anchor_Regimen AS
SELECT DISTINCT regimen_id, regimen_name
FROM regimen_anchor_crosswalk
ORDER BY regimen_id;

DROP TABLE IF EXISTS audit_regimen_synonym_quarantine;
CREATE TABLE audit_regimen_synonym_quarantine AS
WITH candidates AS (
    SELECT
        CAST(r.regimen_synonym_id AS INTEGER) AS legacy_regimen_synonym_id,
        norm_surface(r.regimen_synonym) AS regimen_synonym,
        CAST(r.source_id AS INTEGER) AS source_id,
        x.regimen_id
    FROM integrated_Regimens_And_Synonyms r
    LEFT JOIN regimen_anchor_crosswalk x
      ON x.legacy_regimen_id = CAST(r.regimen_id AS INTEGER)
), cardinality AS (
    SELECT regimen_synonym, COUNT(DISTINCT regimen_id) AS target_count
    FROM candidates
    WHERE is_valid_surface(regimen_synonym) = 1
      AND regimen_id IS NOT NULL
    GROUP BY regimen_synonym
)
SELECT c.*,
    CASE
        WHEN is_valid_surface(c.regimen_synonym) = 0 THEN 'blank_or_literal_null'
        WHEN c.regimen_id IS NULL THEN 'invalid_regimen_foreign_key'
        WHEN COALESCE(n.target_count, 0) <> 1 THEN 'synonym_maps_to_multiple_regimens'
        ELSE 'not_quarantined'
    END AS quarantine_reason
FROM candidates c
LEFT JOIN cardinality n USING (regimen_synonym)
WHERE is_valid_surface(c.regimen_synonym) = 0
   OR c.regimen_id IS NULL
   OR COALESCE(n.target_count, 0) <> 1;

DROP TABLE IF EXISTS production_Regimens_And_Synonyms;
CREATE TABLE production_Regimens_And_Synonyms AS
WITH candidates AS (
    SELECT DISTINCT
        norm_surface(r.regimen_synonym) AS regimen_synonym,
        CAST(r.source_id AS INTEGER) AS source_id,
        x.regimen_id
    FROM integrated_Regimens_And_Synonyms r
    JOIN regimen_anchor_crosswalk x
      ON x.legacy_regimen_id = CAST(r.regimen_id AS INTEGER)
    JOIN production_Data_Sources s
      ON s.source_id = CAST(r.source_id AS INTEGER)
    WHERE is_valid_surface(r.regimen_synonym) = 1
), unique_surfaces AS (
    SELECT regimen_synonym
    FROM candidates
    GROUP BY regimen_synonym
    HAVING COUNT(DISTINCT regimen_id) = 1
)
SELECT
    ROW_NUMBER() OVER (ORDER BY c.regimen_synonym, c.regimen_id, c.source_id) AS regimen_synonym_id,
    c.regimen_synonym,
    c.source_id,
    c.regimen_id
FROM candidates c
JOIN unique_surfaces u USING (regimen_synonym)
ORDER BY regimen_synonym_id;

DROP TABLE IF EXISTS production_Regimen_Source;
CREATE TABLE production_Regimen_Source AS
SELECT DISTINCT
    x.regimen_id,
    CAST(r.source_id AS INTEGER) AS source_id
FROM integrated_Regimen_Source r
JOIN regimen_anchor_crosswalk x
  ON x.legacy_regimen_id = CAST(r.regimen_id AS INTEGER)
JOIN production_Data_Sources s
  ON s.source_id = CAST(r.source_id AS INTEGER)
ORDER BY x.regimen_id, CAST(r.source_id AS INTEGER);

DROP TABLE IF EXISTS audit_regimen_drug_quarantine;
CREATE TABLE audit_regimen_drug_quarantine AS
SELECT
    CAST(r.regimen_id AS INTEGER) AS legacy_regimen_id,
    CAST(r.anchor_drug_id AS INTEGER) AS legacy_anchor_drug_id,
    CAST(r.source_id AS INTEGER) AS source_id,
    CASE
        WHEN x.regimen_id IS NULL THEN 'invalid_regimen_foreign_key'
        WHEN d.anchor_drug_id IS NULL THEN 'drug_anchor_not_uniquely_validated'
        WHEN s.source_id IS NULL THEN 'invalid_source_foreign_key'
        ELSE 'not_quarantined'
    END AS quarantine_reason
FROM integrated_Anchor_Drugs_To_Regimens r
LEFT JOIN regimen_anchor_crosswalk x
  ON x.legacy_regimen_id = CAST(r.regimen_id AS INTEGER)
LEFT JOIN legacy_drug_anchor_crosswalk d
  ON d.legacy_anchor_drug_id = CAST(r.anchor_drug_id AS INTEGER)
LEFT JOIN production_Data_Sources s
  ON s.source_id = CAST(r.source_id AS INTEGER)
WHERE x.regimen_id IS NULL
   OR d.anchor_drug_id IS NULL
   OR s.source_id IS NULL;

DROP TABLE IF EXISTS production_Anchor_Drugs_To_Regimens;
CREATE TABLE production_Anchor_Drugs_To_Regimens AS
SELECT DISTINCT
    x.regimen_id,
    d.anchor_drug_id,
    CAST(r.source_id AS INTEGER) AS source_id
FROM integrated_Anchor_Drugs_To_Regimens r
JOIN regimen_anchor_crosswalk x
  ON x.legacy_regimen_id = CAST(r.regimen_id AS INTEGER)
JOIN legacy_drug_anchor_crosswalk d
  ON d.legacy_anchor_drug_id = CAST(r.anchor_drug_id AS INTEGER)
JOIN production_Data_Sources s
  ON s.source_id = CAST(r.source_id AS INTEGER)
ORDER BY x.regimen_id, d.anchor_drug_id, CAST(r.source_id AS INTEGER);

DROP TABLE IF EXISTS production_Conditions_And_Regimens;
CREATE TABLE production_Conditions_And_Regimens AS
WITH validated AS (
    SELECT DISTINCT
        norm_surface(c.condition_name) AS condition_name,
        x.regimen_id,
        CAST(c.source_id AS INTEGER) AS source_id
    FROM integrated_Conditions_And_Regimens c
    JOIN regimen_anchor_crosswalk x
      ON x.legacy_regimen_id = CAST(c.regimen_id AS INTEGER)
    JOIN production_Data_Sources s
      ON s.source_id = CAST(c.source_id AS INTEGER)
    WHERE is_valid_surface(c.condition_name) = 1
)
SELECT
    ROW_NUMBER() OVER (ORDER BY condition_name, regimen_id, source_id) AS condition_id,
    condition_name,
    regimen_id,
    source_id
FROM validated
ORDER BY condition_id;

DROP TABLE IF EXISTS production_Clinical_Trials;
CREATE TABLE production_Clinical_Trials AS
SELECT DISTINCT
    CAST(c.row_id AS INTEGER) AS row_id,
    c.interventions_id,
    c.clinical_trial_id,
    c.name,
    c.other_name,
    CAST(c.source_id AS INTEGER) AS source_id
FROM integrated_Clinical_Trials c
JOIN production_Data_Sources s
  ON s.source_id = CAST(c.source_id AS INTEGER)
ORDER BY CAST(c.row_id AS INTEGER), c.interventions_id, c.clinical_trial_id,
         c.name, c.other_name, CAST(c.source_id AS INTEGER);
