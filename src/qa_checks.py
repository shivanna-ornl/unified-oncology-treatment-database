from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import normalize_surface, valid_surface, write_csv, write_json
from materialize import PUBLIC_TABLES


CHECKS: list[tuple[str, str, str]] = [
    (
        "drug_synonym_id_multiple_anchors",
        "SELECT COUNT(*) FROM (SELECT synonym_id FROM production_Anchor_Drugs_And_Synonyms "
        "GROUP BY synonym_id HAVING COUNT(DISTINCT anchor_drug_id) > 1)",
        "A synonym ID identifies one anchor drug.",
    ),
    (
        "drug_surface_multiple_anchors",
        "SELECT COUNT(*) FROM (SELECT norm_surface(synonym_name) s "
        "FROM production_Anchor_Drugs_And_Synonyms GROUP BY s "
        "HAVING COUNT(DISTINCT anchor_drug_id) > 1)",
        "A normalized drug synonym identifies one compatible anchor.",
    ),
    (
        "drug_synonym_blank_or_sentinel",
        "SELECT COUNT(*) FROM production_Anchor_Drugs_And_Synonyms "
        "WHERE is_valid_surface(synonym_name) = 0",
        "Blank and literal-null drug synonyms are excluded.",
    ),
    (
        "drug_exact_rxnorm_target_conflict",
        "SELECT COUNT(*) FROM production_Anchor_Drugs_And_Synonyms s "
        "JOIN rxnorm_surface_resolution r ON r.normalized_surface_form = norm_surface(s.synonym_name) "
        "JOIN canonical_drug_concept c ON c.anchor_drug_id = s.anchor_drug_id "
        "WHERE r.mapping_status = 'accepted' AND r.canonical_tty IN ('IN','MIN') "
        "AND r.canonical_rxcui <> c.canonical_rxcui",
        "An exact RxNorm ingredient agrees with its public IN/MIN anchor.",
    ),
    (
        "canonical_drug_not_in_or_min",
        "SELECT COUNT(*) FROM canonical_drug_concept WHERE canonical_tty NOT IN ('IN','MIN')",
        "Public canonical drugs are only IN or MIN concepts.",
    ),
    (
        "drug_synonym_orphan_anchor",
        "SELECT COUNT(*) FROM production_Anchor_Drugs_And_Synonyms s "
        "LEFT JOIN production_Anchor_Drugs a USING(anchor_drug_id) WHERE a.anchor_drug_id IS NULL",
        "Every drug synonym target exists.",
    ),
    (
        "anchor_drug_source_orphan",
        "SELECT COUNT(*) FROM production_Anchor_Drug_Source x "
        "LEFT JOIN production_Anchor_Drugs a USING(anchor_drug_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE a.anchor_drug_id IS NULL OR s.source_id IS NULL",
        "Anchor-drug provenance foreign keys resolve.",
    ),
    (
        "drug_synonym_source_orphan",
        "SELECT COUNT(*) FROM production_Anchor_Drug_Synonym_Source x "
        "LEFT JOIN production_Anchor_Drugs_And_Synonyms y USING(synonym_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE y.synonym_id IS NULL OR s.source_id IS NULL",
        "Drug-synonym provenance foreign keys resolve.",
    ),
    (
        "regimen_synonym_id_multiple_anchors",
        "SELECT COUNT(*) FROM (SELECT regimen_synonym_id FROM production_Regimens_And_Synonyms "
        "GROUP BY regimen_synonym_id HAVING COUNT(DISTINCT regimen_id) > 1)",
        "A regimen synonym ID identifies one regimen.",
    ),
    (
        "regimen_surface_multiple_anchors",
        "SELECT COUNT(*) FROM (SELECT norm_surface(regimen_synonym) s "
        "FROM production_Regimens_And_Synonyms GROUP BY s "
        "HAVING COUNT(DISTINCT regimen_id) > 1)",
        "A normalized regimen synonym identifies one regimen.",
    ),
    (
        "regimen_synonym_blank_or_sentinel",
        "SELECT COUNT(*) FROM production_Regimens_And_Synonyms "
        "WHERE is_valid_surface(regimen_synonym) = 0",
        "Blank and literal-null regimen synonyms are excluded.",
    ),
    (
        "regimen_synonym_orphan",
        "SELECT COUNT(*) FROM production_Regimens_And_Synonyms x "
        "LEFT JOIN production_Anchor_Regimen r USING(regimen_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE r.regimen_id IS NULL OR s.source_id IS NULL",
        "Regimen-synonym foreign keys resolve.",
    ),
    (
        "regimen_source_exact_duplicates",
        "SELECT COUNT(*) FROM (SELECT regimen_id, source_id FROM production_Regimen_Source "
        "GROUP BY regimen_id, source_id HAVING COUNT(*) > 1)",
        "Regimen_Source contains no exact duplicate rows.",
    ),
    (
        "regimen_source_orphan",
        "SELECT COUNT(*) FROM production_Regimen_Source x "
        "LEFT JOIN production_Anchor_Regimen r USING(regimen_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE r.regimen_id IS NULL OR s.source_id IS NULL",
        "Regimen provenance foreign keys resolve.",
    ),
    (
        "regimen_drug_orphan",
        "SELECT COUNT(*) FROM production_Anchor_Drugs_To_Regimens x "
        "LEFT JOIN production_Anchor_Regimen r USING(regimen_id) "
        "LEFT JOIN production_Anchor_Drugs d USING(anchor_drug_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE r.regimen_id IS NULL OR d.anchor_drug_id IS NULL OR s.source_id IS NULL",
        "Every regimen-drug and provenance foreign key resolves.",
    ),
    (
        "conditions_regimen_or_source_orphan",
        "SELECT COUNT(*) FROM production_Conditions_And_Regimens x "
        "LEFT JOIN production_Anchor_Regimen r USING(regimen_id) "
        "LEFT JOIN production_Data_Sources s USING(source_id) "
        "WHERE r.regimen_id IS NULL OR s.source_id IS NULL",
        "Condition associations reference valid regimens and sources.",
    ),
    (
        "clinical_trial_source_orphan",
        "SELECT COUNT(*) FROM production_Clinical_Trials x "
        "LEFT JOIN production_Data_Sources s USING(source_id) WHERE s.source_id IS NULL",
        "Clinical-trial provenance references a valid source.",
    ),
]


def scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0] or 0)


def grouped_counts(connection: sqlite3.Connection, query: str) -> dict[str, int]:
    return {str(row[0] or "(blank)"): int(row[1]) for row in connection.execute(query)}


def run(repo: Path) -> dict[str, Any]:
    database_path = repo / "work" / "treatment_validation.sqlite"
    if not database_path.exists():
        raise FileNotFoundError(f"Build database not found: {database_path}")
    connection = sqlite3.connect(database_path)
    connection.create_function("norm_surface", 1, normalize_surface, deterministic=True)
    connection.create_function("is_valid_surface", 1, lambda value: int(valid_surface(value)), deterministic=True)
    try:
        checks = []
        for name, query, requirement in CHECKS:
            observed = scalar(connection, query)
            checks.append(
                {
                    "check": name,
                    "observed_issues": observed,
                    "expected_issues": 0,
                    "status": "PASS" if observed == 0 else "FAIL",
                    "requirement": requirement,
                }
            )
        schema_checks = []
        for name, expected in PUBLIC_TABLES.items():
            actual = [row[1] for row in connection.execute(f'PRAGMA table_info("production_{name}")')]
            schema_checks.append(
                {
                    "table": name,
                    "expected": expected,
                    "actual": actual,
                    "status": "PASS" if actual == expected else "FAIL",
                }
            )
        row_counts = {
            name: scalar(connection, f'SELECT COUNT(*) FROM "production_{name}"')
            for name in PUBLIC_TABLES
        }
        tty_counts = grouped_counts(
            connection,
            "SELECT canonical_tty, COUNT(*) FROM canonical_drug_concept GROUP BY canonical_tty",
        )
        mapping_counts = grouped_counts(
            connection,
            "SELECT mapping_status, COUNT(*) FROM rxnorm_surface_resolution GROUP BY mapping_status",
        )
        quarantine_counts = {
            "drug_terms": grouped_counts(
                connection,
                "SELECT quarantine_reason, COUNT(*) FROM audit_drug_term_quarantine GROUP BY quarantine_reason",
            ),
            "drug_anchors": grouped_counts(
                connection,
                "SELECT quarantine_reason, COUNT(*) FROM audit_legacy_drug_anchor_quarantine GROUP BY quarantine_reason",
            ),
            "regimen_synonyms": grouped_counts(
                connection,
                "SELECT quarantine_reason, COUNT(*) FROM audit_regimen_synonym_quarantine GROUP BY quarantine_reason",
            ),
            "regimen_drug_links": grouped_counts(
                connection,
                "SELECT quarantine_reason, COUNT(*) FROM audit_regimen_drug_quarantine GROUP BY quarantine_reason",
            ),
        }
        version = json.loads((repo / "cache" / "rxnorm" / "version.json").read_text(encoding="utf-8"))
        all_pass = all(row["status"] == "PASS" for row in checks + schema_checks)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": "PASS" if all_pass else "FAIL",
            "rxnorm_dataset_version": version.get("version", ""),
            "rxnorm_api_version": version.get("apiVersion", ""),
            "checks": checks,
            "schema_checks": schema_checks,
            "production_row_counts": row_counts,
            "canonical_tty_counts": tty_counts,
            "rxnorm_surface_mapping_counts": mapping_counts,
            "quarantine_counts": quarantine_counts,
        }
        qa_dir = repo / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        write_json(qa_dir / "qa_report.json", report)
        write_csv(
            qa_dir / "qa_checks.csv",
            ["check", "observed_issues", "expected_issues", "status", "requirement"],
            checks,
        )
        markdown = [
            "# Production pipeline QA report",
            "",
            f"**Overall status:** {report['overall_status']}",
            "",
            f"**RxNorm dataset version:** `{report['rxnorm_dataset_version']}`  ",
            f"**RxNorm API version:** `{report['rxnorm_api_version']}`",
            "",
            "## Integrity checks",
            "",
            "| Check | Issues | Status |",
            "|---|---:|:---:|",
        ]
        markdown.extend(
            f"| {row['check']} | {row['observed_issues']} | {row['status']} |" for row in checks
        )
        markdown.extend(["", "## Production row counts", "", "| Table | Rows |", "|---|---:|"])
        markdown.extend(f"| {name} | {count:,} |" for name, count in row_counts.items())
        markdown.extend(
            [
                "",
                "## Audit interpretation",
                "",
                "Public production tables contain only mappings that passed the semantic and relational gates. RxNorm evidence, crosswalks, and quarantined rows are stored in `audit/` as supporting artifacts and are not additional production tables.",
            ]
        )
        (qa_dir / "QA_REPORT.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
        return report
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = run(args.repo.resolve())
    print(json.dumps({"overall_status": report["overall_status"]}, indent=2))
    if report["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

