from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import normalize_surface, read_csv, read_json, sha256_file, valid_surface, write_json
from materialize import PUBLIC_TABLES


def header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return next(csv.reader(stream))


def add(checks: list[dict[str, Any]], name: str, observed: int, requirement: str) -> None:
    checks.append(
        {
            "check": name,
            "observed_issues": observed,
            "expected_issues": 0,
            "status": "PASS" if observed == 0 else "FAIL",
            "requirement": requirement,
        }
    )


def run(repo: Path) -> dict[str, Any]:
    production = repo / "outputs" / "production"
    audit = repo / "audit"
    release_manifest = read_json(repo / "metadata" / "release_manifest.json")
    rows = {name: read_csv(production / f"{name}.csv") for name in PUBLIC_TABLES}
    checks: list[dict[str, Any]] = []

    schema_issues = sum(
        header(production / f"{name}.csv") != expected
        for name, expected in PUBLIC_TABLES.items()
    )
    add(checks, "exported_public_schema_mismatch", schema_issues, "Every exported CSV header must match the public contract exactly.")

    count_issues = sum(
        len(rows[name]) != int(release_manifest["row_counts"][name])
        for name in PUBLIC_TABLES
    )
    add(checks, "exported_row_count_mismatch", count_issues, "Exported row counts must match the release manifest.")

    hash_issues = 0
    for relative, metadata in release_manifest["files"].items():
        path = repo / relative
        if not path.exists() or sha256_file(path) != metadata["sha256"]:
            hash_issues += 1
    add(checks, "release_hash_mismatch", hash_issues, "Every production and audit CSV must match its release SHA-256 hash.")

    sources = {row["source_id"] for row in rows["Data_Sources"]}
    anchors = {row["anchor_drug_id"] for row in rows["Anchor_Drugs"]}
    synonyms = {row["synonym_id"] for row in rows["Anchor_Drugs_And_Synonyms"]}
    regimens = {row["regimen_id"] for row in rows["Anchor_Regimen"]}

    drug_surface_targets: dict[str, set[str]] = defaultdict(set)
    drug_id_targets: dict[str, set[str]] = defaultdict(set)
    invalid_drug_synonyms = 0
    for row in rows["Anchor_Drugs_And_Synonyms"]:
        surface = normalize_surface(row["synonym_name"])
        drug_surface_targets[surface].add(row["anchor_drug_id"])
        drug_id_targets[row["synonym_id"]].add(row["anchor_drug_id"])
        invalid_drug_synonyms += not valid_surface(row["synonym_name"])
    add(checks, "exported_drug_surface_ambiguity", sum(len(value) > 1 for value in drug_surface_targets.values()), "A normalized exported drug synonym must map to one anchor.")
    add(checks, "exported_drug_synonym_id_ambiguity", sum(len(value) > 1 for value in drug_id_targets.values()), "An exported drug synonym ID must map to one anchor.")
    add(checks, "exported_drug_blank_or_sentinel", invalid_drug_synonyms, "Exported drug synonyms must not be blank or literal-null placeholders.")
    add(checks, "exported_drug_synonym_orphan", sum(row["anchor_drug_id"] not in anchors for row in rows["Anchor_Drugs_And_Synonyms"]), "Every exported drug synonym target must exist.")
    add(checks, "exported_anchor_provenance_orphan", sum(row["anchor_drug_id"] not in anchors or row["source_id"] not in sources for row in rows["Anchor_Drug_Source"]), "Every exported anchor provenance key must resolve.")
    add(checks, "exported_synonym_provenance_orphan", sum(row["synonym_id"] not in synonyms or row["source_id"] not in sources for row in rows["Anchor_Drug_Synonym_Source"]), "Every exported drug-synonym provenance key must resolve.")

    regimen_surface_targets: dict[str, set[str]] = defaultdict(set)
    invalid_regimen_synonyms = 0
    for row in rows["Regimens_And_Synonyms"]:
        regimen_surface_targets[normalize_surface(row["regimen_synonym"])].add(row["regimen_id"])
        invalid_regimen_synonyms += not valid_surface(row["regimen_synonym"])
    add(checks, "exported_regimen_surface_ambiguity", sum(len(value) > 1 for value in regimen_surface_targets.values()), "A normalized exported regimen synonym must map to one regimen.")
    add(checks, "exported_regimen_blank_or_sentinel", invalid_regimen_synonyms, "Exported regimen synonyms must not be blank or literal-null placeholders.")
    add(checks, "exported_regimen_synonym_orphan", sum(row["regimen_id"] not in regimens or row["source_id"] not in sources for row in rows["Regimens_And_Synonyms"]), "Every exported regimen-synonym key must resolve.")

    regimen_source_pairs = [(row["regimen_id"], row["source_id"]) for row in rows["Regimen_Source"]]
    add(checks, "exported_regimen_source_duplicate", len(regimen_source_pairs) - len(set(regimen_source_pairs)), "Exported Regimen_Source rows must be exact-duplicate free.")
    add(checks, "exported_regimen_source_orphan", sum(regimen not in regimens or source_id not in sources for regimen, source_id in regimen_source_pairs), "Every exported regimen provenance key must resolve.")
    add(checks, "exported_regimen_drug_orphan", sum(row["regimen_id"] not in regimens or row["anchor_drug_id"] not in anchors or row["source_id"] not in sources for row in rows["Anchor_Drugs_To_Regimens"]), "Every exported regimen-drug key must resolve.")
    add(checks, "exported_condition_orphan", sum(row["regimen_id"] not in regimens or row["source_id"] not in sources for row in rows["Conditions_And_Regimens"]), "Every exported condition association key must resolve.")
    add(checks, "exported_clinical_trial_source_orphan", sum(row["source_id"] not in sources for row in rows["Clinical_Trials"]), "Every exported clinical-trial source key must resolve.")

    concepts = {
        row["anchor_drug_id"]: (row["canonical_rxcui"], row["canonical_tty"])
        for row in read_csv(audit / "canonical_drug_concept.csv")
    }
    surface_resolution = {
        row["normalized_surface_form"]: row
        for row in read_csv(audit / "rxnorm_surface_resolution.csv")
        if row["mapping_status"] == "accepted" and row["canonical_tty"] in {"IN", "MIN"}
    }
    semantic_conflicts = 0
    for row in rows["Anchor_Drugs_And_Synonyms"]:
        resolution = surface_resolution.get(normalize_surface(row["synonym_name"]))
        if resolution and concepts[row["anchor_drug_id"]][0] != resolution["canonical_rxcui"]:
            semantic_conflicts += 1
    add(checks, "exported_exact_rxnorm_target_conflict", semantic_conflicts, "An exact exported RxNorm term must agree with its public IN/MIN anchor.")
    add(checks, "exported_non_in_min_anchor", sum(tty not in {"IN", "MIN"} for _, tty in concepts.values()), "Every exported canonical drug must be an IN or MIN.")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
        "checks": checks,
        "verified_public_tables": len(PUBLIC_TABLES),
        "verified_hashed_files": len(release_manifest["files"]),
    }
    write_json(repo / "qa" / "export_verification.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run(args.repo.resolve())
    print(json.dumps({"overall_status": result["overall_status"]}, indent=2))
    if result["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
