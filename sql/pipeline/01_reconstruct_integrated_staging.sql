-- Construct the final integrated staging graph from the deterministic
-- cross-source preprocessing outputs.

DROP TABLE IF EXISTS Drug_Staging_Table;
CREATE TABLE Drug_Staging_Table AS
SELECT
    CAST(a.anchor_drug_id AS INTEGER) AS legacy_anchor_drug_id,
    norm_surface(a.anchor_drug_name) AS legacy_anchor_drug_name,
    'anchor' AS term_kind,
    NULL AS legacy_synonym_id,
    norm_surface(a.anchor_drug_name) AS normalized_surface_form,
    CAST(s.source_id AS INTEGER) AS source_id
FROM integrated_Anchor_Drugs a
LEFT JOIN integrated_Anchor_Drug_Source s
  ON s.anchor_drug_id = a.anchor_drug_id
WHERE is_valid_surface(a.anchor_drug_name) = 1

UNION ALL

SELECT
    CAST(a.anchor_drug_id AS INTEGER) AS legacy_anchor_drug_id,
    norm_surface(a.anchor_drug_name) AS legacy_anchor_drug_name,
    'synonym' AS term_kind,
    CAST(x.synonym_id AS INTEGER) AS legacy_synonym_id,
    norm_surface(x.synonym_name) AS normalized_surface_form,
    CAST(s.source_id AS INTEGER) AS source_id
FROM integrated_Anchor_Drugs_And_Synonyms x
JOIN integrated_Anchor_Drugs a
  ON a.anchor_drug_id = x.anchor_drug_id
LEFT JOIN integrated_Anchor_Drug_Synonym_Source s
  ON s.synonym_id = x.synonym_id
WHERE is_valid_surface(a.anchor_drug_name) = 1
  AND is_valid_surface(x.synonym_name) = 1;

CREATE INDEX IF NOT EXISTS idx_drug_staging_anchor
    ON Drug_Staging_Table(legacy_anchor_drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_staging_surface
    ON Drug_Staging_Table(normalized_surface_form);

DROP TABLE IF EXISTS regimen_anchor_crosswalk;
CREATE TABLE regimen_anchor_crosswalk AS
WITH valid AS (
    SELECT
        CAST(regimen_id AS INTEGER) AS legacy_regimen_id,
        norm_surface(regimen_name) AS normalized_regimen_name
    FROM integrated_Anchor_Regimen
    WHERE is_valid_surface(regimen_name) = 1
), canonical AS (
    SELECT
        normalized_regimen_name,
        MIN(legacy_regimen_id) AS regimen_id
    FROM valid
    GROUP BY normalized_regimen_name
)
SELECT
    v.legacy_regimen_id,
    c.regimen_id,
    v.normalized_regimen_name AS regimen_name
FROM valid v
JOIN canonical c USING (normalized_regimen_name);

CREATE INDEX IF NOT EXISTS idx_regimen_crosswalk_legacy
    ON regimen_anchor_crosswalk(legacy_regimen_id);
