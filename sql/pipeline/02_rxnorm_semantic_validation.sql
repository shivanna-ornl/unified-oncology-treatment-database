-- New semantic-referee step.  This script is intentionally placed after the
-- reconstructed Drug_Staging_Table and before public materialization.

DROP TABLE IF EXISTS rxnorm_exact_accepted;
CREATE TABLE rxnorm_exact_accepted AS
SELECT
    normalized_surface_form,
    canonical_rxcui,
    norm_surface(canonical_name) AS canonical_name,
    canonical_tty,
    mapping_rule
FROM rxnorm_surface_resolution
WHERE mapping_status = 'accepted'
  AND canonical_tty IN ('IN', 'MIN')
  AND canonical_rxcui <> ''
  AND is_valid_surface(canonical_name) = 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rx_exact_surface
    ON rxnorm_exact_accepted(normalized_surface_form);

-- Direct anchor evidence is strongest because it validates the provisional
-- anchor itself.  If it is absent, all accepted terms for a legacy anchor must
-- converge to one IN/MIN before an inherited default is allowed.
DROP TABLE IF EXISTS legacy_anchor_evidence;
CREATE TABLE legacy_anchor_evidence AS
SELECT DISTINCT
    d.legacy_anchor_drug_id,
    d.term_kind,
    d.normalized_surface_form,
    r.canonical_rxcui,
    r.canonical_name,
    r.canonical_tty,
    r.mapping_rule
FROM Drug_Staging_Table d
JOIN rxnorm_exact_accepted r USING (normalized_surface_form);

DROP TABLE IF EXISTS legacy_anchor_default;
CREATE TABLE legacy_anchor_default AS
WITH direct AS (
    SELECT
        legacy_anchor_drug_id,
        COUNT(DISTINCT canonical_rxcui) AS target_count,
        MIN(canonical_rxcui) AS canonical_rxcui
    FROM legacy_anchor_evidence
    WHERE term_kind = 'anchor'
    GROUP BY legacy_anchor_drug_id
), all_evidence AS (
    SELECT
        legacy_anchor_drug_id,
        COUNT(DISTINCT canonical_rxcui) AS target_count,
        MIN(canonical_rxcui) AS canonical_rxcui
    FROM legacy_anchor_evidence
    GROUP BY legacy_anchor_drug_id
), selected AS (
    SELECT
        a.legacy_anchor_drug_id,
        CASE
            WHEN d.target_count = 1 THEN d.canonical_rxcui
            WHEN COALESCE(d.target_count, 0) = 0 AND a.target_count = 1
                THEN a.canonical_rxcui
            ELSE NULL
        END AS canonical_rxcui,
        CASE
            WHEN d.target_count = 1 THEN 'direct_anchor_exact_rxnorm'
            WHEN COALESCE(d.target_count, 0) = 0 AND a.target_count = 1
                THEN 'unique_convergent_term_evidence'
            WHEN COALESCE(d.target_count, 0) > 1
                THEN 'ambiguous_direct_anchor_evidence'
            WHEN a.target_count > 1
                THEN 'ambiguous_legacy_anchor_evidence'
            ELSE 'no_rxnorm_ingredient_evidence'
        END AS default_rule
    FROM all_evidence a
    LEFT JOIN direct d USING (legacy_anchor_drug_id)
)
SELECT
    s.legacy_anchor_drug_id,
    s.canonical_rxcui,
    r.canonical_name,
    r.canonical_tty,
    s.default_rule
FROM selected s
LEFT JOIN (
    SELECT DISTINCT canonical_rxcui, canonical_name, canonical_tty
    FROM rxnorm_exact_accepted
) r USING (canonical_rxcui);

CREATE UNIQUE INDEX IF NOT EXISTS idx_legacy_anchor_default
    ON legacy_anchor_default(legacy_anchor_drug_id);

-- Classify each distinct legacy term.  Exact active RxNorm evidence takes
-- precedence.  An exact match that RxNorm cannot uniquely reduce to IN/MIN is
-- never allowed to inherit a source-priority anchor.
DROP TABLE IF EXISTS provisional_term_decision;
CREATE TABLE provisional_term_decision AS
WITH terms AS (
    SELECT DISTINCT
        legacy_anchor_drug_id,
        legacy_anchor_drug_name,
        term_kind,
        legacy_synonym_id,
        normalized_surface_form
    FROM Drug_Staging_Table
), annotated AS (
    SELECT
        t.*,
        x.match_count,
        x.mapping_status AS rxnorm_mapping_status,
        x.mapping_rule AS rxnorm_mapping_rule,
        x.matched_rxcuis,
        x.matched_ttys,
        x.concept_classes,
        e.canonical_rxcui AS exact_rxcui,
        e.canonical_name AS exact_name,
        e.canonical_tty AS exact_tty,
        d.canonical_rxcui AS inherited_rxcui,
        d.canonical_name AS inherited_name,
        d.canonical_tty AS inherited_tty,
        d.default_rule
    FROM terms t
    LEFT JOIN rxnorm_surface_resolution x USING (normalized_surface_form)
    LEFT JOIN rxnorm_exact_accepted e USING (normalized_surface_form)
    LEFT JOIN legacy_anchor_default d USING (legacy_anchor_drug_id)
)
SELECT
    *,
    CASE
        WHEN exact_rxcui IS NOT NULL THEN exact_rxcui
        WHEN CAST(COALESCE(match_count, '0') AS INTEGER) > 0 THEN NULL
        ELSE inherited_rxcui
    END AS assigned_rxcui,
    CASE
        WHEN exact_rxcui IS NOT NULL THEN exact_name
        WHEN CAST(COALESCE(match_count, '0') AS INTEGER) > 0 THEN NULL
        ELSE inherited_name
    END AS assigned_name,
    CASE
        WHEN exact_rxcui IS NOT NULL THEN exact_tty
        WHEN CAST(COALESCE(match_count, '0') AS INTEGER) > 0 THEN NULL
        ELSE inherited_tty
    END AS assigned_tty,
    CASE
        WHEN exact_rxcui IS NOT NULL THEN 'accepted_exact_rxnorm'
        WHEN CAST(COALESCE(match_count, '0') AS INTEGER) > 0 THEN 'quarantine_rxnorm_not_unique_in_min'
        WHEN inherited_rxcui IS NOT NULL THEN 'accepted_unique_anchor_inheritance'
        ELSE 'quarantine_anchor_not_validated'
    END AS decision_status
FROM annotated;

-- A normalized surface may not map to multiple incompatible targets.  Exact
-- RxNorm evidence already converges globally; ambiguous inherited surfaces are
-- removed as a unit rather than resolved by source or ID order.
DROP TABLE IF EXISTS surface_assignment_cardinality;
CREATE TABLE surface_assignment_cardinality AS
SELECT
    normalized_surface_form,
    COUNT(DISTINCT assigned_rxcui) AS target_count,
    GROUP_CONCAT(DISTINCT assigned_rxcui) AS assigned_rxcuis
FROM provisional_term_decision
WHERE assigned_rxcui IS NOT NULL
GROUP BY normalized_surface_form;

DROP TABLE IF EXISTS Validated_Drug_Staging_Table;
CREATE TABLE Validated_Drug_Staging_Table AS
SELECT DISTINCT
    p.legacy_anchor_drug_id,
    p.legacy_anchor_drug_name,
    p.term_kind,
    p.legacy_synonym_id,
    p.normalized_surface_form,
    p.assigned_rxcui AS canonical_rxcui,
    p.assigned_name AS canonical_drug_name,
    p.assigned_tty AS canonical_tty,
    p.decision_status
FROM provisional_term_decision p
JOIN surface_assignment_cardinality c USING (normalized_surface_form)
WHERE p.assigned_rxcui IS NOT NULL
  AND p.assigned_tty IN ('IN', 'MIN')
  AND c.target_count = 1;

CREATE INDEX IF NOT EXISTS idx_validated_drug_rxcui
    ON Validated_Drug_Staging_Table(canonical_rxcui);
CREATE INDEX IF NOT EXISTS idx_validated_drug_surface
    ON Validated_Drug_Staging_Table(normalized_surface_form);
CREATE INDEX IF NOT EXISTS idx_validated_drug_legacy_term
    ON Validated_Drug_Staging_Table(
        legacy_anchor_drug_id,
        term_kind,
        legacy_synonym_id,
        normalized_surface_form
    );

DROP TABLE IF EXISTS audit_rxnorm_semantic_overrides;
CREATE TABLE audit_rxnorm_semantic_overrides AS
SELECT DISTINCT
    p.legacy_anchor_drug_id,
    p.legacy_anchor_drug_name,
    p.term_kind,
    p.legacy_synonym_id,
    p.normalized_surface_form,
    p.inherited_rxcui AS provisional_default_rxcui,
    p.inherited_name AS provisional_default_name,
    p.inherited_tty AS provisional_default_tty,
    p.exact_rxcui AS validated_rxcui,
    p.exact_name AS validated_name,
    p.exact_tty AS validated_tty,
    p.rxnorm_mapping_rule,
    CASE
        WHEN p.inherited_tty = 'IN' AND p.exact_tty = 'MIN'
            THEN 'single_anchor_to_multi_ingredient_target'
        WHEN p.inherited_tty = 'MIN' AND p.exact_tty = 'IN'
            THEN 'multi_anchor_component_to_single_ingredient_target'
        ELSE 'incompatible_ingredient_target_reassigned'
    END AS override_class
FROM provisional_term_decision p
WHERE p.exact_rxcui IS NOT NULL
  AND p.inherited_rxcui IS NOT NULL
  AND p.exact_rxcui <> p.inherited_rxcui;

DROP TABLE IF EXISTS audit_drug_term_quarantine;
CREATE TABLE audit_drug_term_quarantine AS
SELECT
    p.legacy_anchor_drug_id,
    p.legacy_anchor_drug_name,
    p.term_kind,
    p.legacy_synonym_id,
    p.normalized_surface_form,
    p.match_count,
    p.rxnorm_mapping_status,
    p.rxnorm_mapping_rule,
    p.matched_rxcuis,
    p.matched_ttys,
    p.concept_classes,
    p.default_rule,
    CASE
        WHEN p.assigned_rxcui IS NOT NULL AND c.target_count > 1
            THEN 'quarantine_surface_maps_to_multiple_targets'
        ELSE p.decision_status
    END AS quarantine_reason,
    c.assigned_rxcuis
FROM provisional_term_decision p
LEFT JOIN surface_assignment_cardinality c USING (normalized_surface_form)
WHERE p.assigned_rxcui IS NULL
   OR COALESCE(c.target_count, 0) <> 1;

DROP TABLE IF EXISTS canonical_drug_concept;
CREATE TABLE canonical_drug_concept AS
SELECT
    ROW_NUMBER() OVER (ORDER BY canonical_drug_name, canonical_rxcui) AS anchor_drug_id,
    canonical_rxcui,
    canonical_drug_name,
    canonical_tty
FROM (
    SELECT DISTINCT
        canonical_rxcui,
        canonical_drug_name,
        canonical_tty
    FROM Validated_Drug_Staging_Table
    WHERE canonical_tty IN ('IN', 'MIN')
      AND is_valid_surface(canonical_drug_name) = 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_drug_rxcui
    ON canonical_drug_concept(canonical_rxcui);

-- One legacy anchor can split where exact evidence exposes the original
-- combination-drug/component conflation.  Only a unique default is eligible
-- for regimen-drug remapping.
DROP TABLE IF EXISTS legacy_drug_anchor_crosswalk;
CREATE TABLE legacy_drug_anchor_crosswalk AS
SELECT
    d.legacy_anchor_drug_id,
    d.canonical_rxcui,
    c.anchor_drug_id,
    c.canonical_drug_name,
    c.canonical_tty,
    d.default_rule
FROM legacy_anchor_default d
JOIN canonical_drug_concept c USING (canonical_rxcui)
WHERE d.canonical_rxcui IS NOT NULL;

DROP TABLE IF EXISTS audit_legacy_drug_anchor_quarantine;
CREATE TABLE audit_legacy_drug_anchor_quarantine AS
SELECT
    a.anchor_drug_id AS legacy_anchor_drug_id,
    norm_surface(a.anchor_drug_name) AS legacy_anchor_drug_name,
    COALESCE(d.default_rule, 'no_rxnorm_ingredient_evidence') AS quarantine_reason
FROM integrated_Anchor_Drugs a
LEFT JOIN legacy_anchor_default d
  ON d.legacy_anchor_drug_id = CAST(a.anchor_drug_id AS INTEGER)
WHERE d.canonical_rxcui IS NULL;
