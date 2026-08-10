from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from common import normalize_surface, read_json, sha256_file, valid_surface, write_csv, write_json


DRUG_FIELDS = ["source_id", "anchor_name", "synonym_name"]
REGIMEN_FIELDS = ["source_id", "regimen_name", "regimen_synonym", "drug_name"]
CONDITION_FIELDS = ["source_id", "condition_name", "regimen_name"]
TRIAL_FIELDS = ["interventions_id", "clinical_trial_id", "name", "other_name", "source_id"]

NCIT_DRUG_TYPES = {
    "enzyme",
    "antibiotics",
    "hazardous or poisonous substance",
    "amino acids, peptides, and proteins",
    "immunologic factor",
    "inorganic chemical",
    "nucleic acid, nucleoside, or nucleotide",
    "organic chemical",
    "pharmacologic substance",
}


def load_config(repo: Path, config_path: Path) -> dict[str, Path]:
    payload = read_json(config_path)
    result: dict[str, Path] = {}
    for key, value in payload["files"].items():
        path = Path(value)
        result[key] = path if path.is_absolute() else repo / path
    return result


def require_inputs(paths: dict[str, Path], source_manifest: dict[str, Any]) -> None:
    required = {item["key"]: item for item in source_manifest["inputs"] if item.get("required", True)}
    missing = [f"{key}: {paths.get(key, '(not configured)')}" for key in required if key not in paths or not paths[key].exists()]
    if missing:
        raise FileNotFoundError("Required source inputs are missing:\n- " + "\n- ".join(missing))
    mismatches = []
    for key, item in required.items():
        expected = item.get("sha256")
        if expected and sha256_file(paths[key]) != expected:
            mismatches.append(f"{key}: expected {expected}, found {sha256_file(paths[key])}")
    if mismatches:
        raise ValueError("Source checksum mismatch:\n- " + "\n- ".join(mismatches))


def split_terms(value: Any, separators: tuple[str, ...] = ("|", ";")) -> list[str]:
    values = [str(value or "")]
    for separator in separators:
        values = [part for item in values for part in item.split(separator)]
    return sorted({normalize_surface(item) for item in values if valid_surface(item)})


def zip_csv(archive: zipfile.ZipFile, member: str, delimiter: str = ",") -> Iterator[dict[str, str]]:
    with archive.open(member) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            yield from csv.DictReader(stream, delimiter=delimiter)


def hemonc_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    drug_rows: set[tuple[int, str, str]] = set()
    regimen_rows: set[tuple[int, str, str, str]] = set()
    condition_rows: set[tuple[int, str, str]] = set()
    with zipfile.ZipFile(path) as archive:
        concept_member = next(name for name in archive.namelist() if name.endswith("concept_stage.csv"))
        synonym_member = next(name for name in archive.namelist() if name.endswith("concept_synonym_stage.csv"))
        sigs_member = next(name for name in archive.namelist() if name.endswith("Tables/sigs.csv"))
        pointer_member = next(name for name in archive.namelist() if name.endswith("Tables/pointer.table.csv"))

        concepts: dict[str, tuple[str, str]] = {}
        for row in zip_csv(archive, concept_member):
            if normalize_surface(row.get("invalid_reason")):
                continue
            code = str(row.get("concept_code", ""))
            name = normalize_surface(row.get("concept_name"))
            domain = normalize_surface(row.get("domain_id"))
            if code and valid_surface(name):
                concepts[code] = (name, domain)

        synonyms: dict[str, set[str]] = defaultdict(set)
        for row in zip_csv(archive, synonym_member):
            if normalize_surface(row.get("invalid_reason")):
                continue
            code = str(row.get("synonym_concept_code", ""))
            synonym = normalize_surface(row.get("synonym_name"))
            if code and valid_surface(synonym):
                synonyms[code].add(synonym)

        for code, (name, domain) in concepts.items():
            if domain == "drug":
                if synonyms.get(code):
                    for synonym in synonyms[code]:
                        drug_rows.add((1, name, synonym))
                else:
                    drug_rows.add((1, name, ""))

        for row in zip_csv(archive, sigs_member):
            if "primary systemic" not in normalize_surface(row.get("component_role")):
                continue
            regimen = normalize_surface(row.get("regimen"))
            component = normalize_surface(row.get("component"))
            if not valid_surface(regimen) or not valid_surface(component):
                continue
            regimen_code = str(row.get("regimen_cui", ""))
            regimen_synonyms = synonyms.get(regimen_code, set())
            if regimen_synonyms:
                for synonym in regimen_synonyms:
                    regimen_rows.add((1, regimen, synonym, component))
            else:
                regimen_rows.add((1, regimen, "", component))
            drug_rows.add((1, component, ""))

        for row in zip_csv(archive, pointer_member):
            condition = normalize_surface(row.get("condition"))
            regimen = normalize_surface(row.get("regimen"))
            if valid_surface(condition) and valid_surface(regimen):
                condition_rows.add((1, condition, regimen))

    return (
        [dict(zip(DRUG_FIELDS, row)) for row in sorted(drug_rows)],
        [dict(zip(REGIMEN_FIELDS, row)) for row in sorted(regimen_rows)],
        [dict(zip(CONDITION_FIELDS, row)) for row in sorted(condition_rows)],
    )


def canmed_rows(path: Path) -> list[dict[str, Any]]:
    rows: set[tuple[int, str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            anchor = normalize_surface(row.get("Generic Name"))
            brand = normalize_surface(row.get("Brand Name"))
            if valid_surface(anchor):
                rows.add((2, anchor, brand if valid_surface(brand) and brand != anchor else ""))
    return [dict(zip(DRUG_FIELDS, row)) for row in sorted(rows)]


def drugbank_rows(path: Path) -> list[dict[str, Any]]:
    rows: set[tuple[int, str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            anchor = normalize_surface(row.get("Common name"))
            if not valid_surface(anchor):
                continue
            synonyms = split_terms(row.get("Synonyms"), ("|",))
            if synonyms:
                for synonym in synonyms:
                    rows.add((3, anchor, synonym if synonym != anchor else ""))
            else:
                rows.add((3, anchor, ""))
    return [dict(zip(DRUG_FIELDS, row)) for row in sorted(rows)]


def ncit_rows(path: Path) -> list[dict[str, Any]]:
    rows: set[tuple[int, str, str]] = set()
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith("/Thesaurus.txt") or name == "Thesaurus.txt")
        with archive.open(member) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
                for fields in csv.reader(stream, delimiter="\t"):
                    if len(fields) < 8 or normalize_surface(fields[7]) not in NCIT_DRUG_TYPES:
                        continue
                    names = [
                        normalize_surface(value)
                        for value in fields[3].split("|")
                        if valid_surface(value)
                    ]
                    if not names:
                        continue
                    anchor = names[0]
                    for synonym in names[1:] or [""]:
                        rows.add((5, anchor, synonym if synonym != anchor else ""))
    return [dict(zip(DRUG_FIELDS, row)) for row in sorted(rows)]


def seer_rows(drug_path: Path, regimen_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    drugs: set[tuple[int, str, str]] = set()
    regimens: set[tuple[int, str, str, str]] = set()
    with drug_path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            anchor = normalize_surface(row.get("Name"))
            if not valid_surface(anchor):
                continue
            synonyms = split_terms(row.get("Alternate Name"))
            if synonyms:
                for synonym in synonyms:
                    drugs.add((7, anchor, synonym if synonym != anchor else ""))
            else:
                drugs.add((7, anchor, ""))
    with regimen_path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            regimen = normalize_surface(row.get("Name"))
            if not valid_surface(regimen):
                continue
            synonyms = split_terms(row.get("Alternate Names")) or [""]
            components = split_terms(row.get("Drugs"))
            for component in components:
                drugs.add((7, component, ""))
                for synonym in synonyms:
                    regimens.add((7, regimen, synonym if synonym != regimen else "", component))
    return (
        [dict(zip(DRUG_FIELDS, row)) for row in sorted(drugs)],
        [dict(zip(REGIMEN_FIELDS, row)) for row in sorted(regimens)],
    )


def rxnorm_rows(cache_dir: Path, existing_surfaces: set[str]) -> list[dict[str, Any]]:
    payload = read_json(cache_dir / "allconcepts_in_min_pin_bn.json")
    concepts = payload.get("minConceptGroup", {}).get("minConcept", []) or []
    rows = {
        (4, surface, "")
        for concept in concepts
        if (surface := normalize_surface(concept.get("name"))) in existing_surfaces
    }
    return [dict(zip(DRUG_FIELDS, row)) for row in sorted(rows)]


def aact_rows(interventions: Path, other_names: Path, work_dir: Path) -> list[dict[str, Any]]:
    database = work_dir / "aact_join.sqlite"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE interventions (id TEXT, nct_id TEXT, name TEXT)")
        connection.execute("CREATE TABLE other_names (intervention_id TEXT, name TEXT)")
        with interventions.open("r", encoding="utf-8-sig", newline="") as stream:
            batch = []
            for row in csv.DictReader(stream, delimiter="|"):
                if normalize_surface(row.get("intervention_type")) == "drug":
                    batch.append((row.get("id", ""), row.get("nct_id", ""), row.get("name", "")))
                if len(batch) >= 10_000:
                    connection.executemany("INSERT INTO interventions VALUES (?, ?, ?)", batch)
                    batch.clear()
            if batch:
                connection.executemany("INSERT INTO interventions VALUES (?, ?, ?)", batch)
        with other_names.open("r", encoding="utf-8-sig", newline="") as stream:
            batch = []
            for row in csv.DictReader(stream, delimiter="|"):
                batch.append((row.get("intervention_id", ""), row.get("name", "")))
                if len(batch) >= 10_000:
                    connection.executemany("INSERT INTO other_names VALUES (?, ?)", batch)
                    batch.clear()
            if batch:
                connection.executemany("INSERT INTO other_names VALUES (?, ?)", batch)
        connection.execute("CREATE INDEX idx_other_intervention ON other_names(intervention_id)")
        result = []
        query = """
            SELECT DISTINCT i.id, i.nct_id, i.name, o.name, 6
            FROM interventions i
            JOIN other_names o ON o.intervention_id = i.id
            WHERE lower(trim(i.name)) <> lower(trim(o.name))
            ORDER BY i.id, i.nct_id, i.name, o.name
        """
        for row in connection.execute(query):
            result.append(dict(zip(TRIAL_FIELDS, row)))
        return result
    finally:
        connection.close()
        database.unlink(missing_ok=True)


def run(repo: Path, config_path: Path) -> dict[str, Any]:
    csv.field_size_limit(1024 * 1024 * 128)
    source_manifest = read_json(repo / "metadata" / "source_manifest.json")
    paths = load_config(repo, config_path)
    require_inputs(paths, source_manifest)
    work_dir = repo / "work"
    standardized = work_dir / "standardized"
    standardized.mkdir(parents=True, exist_ok=True)

    hemonc_drugs, hemonc_regimens, conditions = hemonc_rows(paths["hemonc_zip"])
    canmed = canmed_rows(paths["canmed_ndc"])
    drugbank = drugbank_rows(paths["drugbank_vocabulary"])
    ncit = ncit_rows(paths["ncit_flat_zip"])
    seer_drugs, seer_regimens = seer_rows(paths["seer_drugs"], paths["seer_regimens"])
    non_rxnorm = hemonc_drugs + canmed + drugbank + ncit + seer_drugs
    existing_surfaces = {
        normalize_surface(value)
        for row in non_rxnorm
        for value in (row["anchor_name"], row["synonym_name"])
        if valid_surface(value)
    }
    rxnorm = rxnorm_rows(repo / "cache" / "rxnorm", existing_surfaces)
    drug_terms = sorted(
        {tuple(str(row[field]) for field in DRUG_FIELDS) for row in non_rxnorm + rxnorm},
        key=lambda row: (int(row[0]), row[1], row[2]),
    )
    regimen_terms = sorted(
        {tuple(str(row[field]) for field in REGIMEN_FIELDS) for row in hemonc_regimens + seer_regimens},
        key=lambda row: (int(row[0]), row[1], row[2], row[3]),
    )
    trials = aact_rows(paths["aact_interventions"], paths["aact_intervention_other_names"], work_dir)

    write_csv(standardized / "drug_terms.csv", DRUG_FIELDS, [dict(zip(DRUG_FIELDS, row)) for row in drug_terms])
    write_csv(standardized / "regimen_terms.csv", REGIMEN_FIELDS, [dict(zip(REGIMEN_FIELDS, row)) for row in regimen_terms])
    write_csv(standardized / "conditions.csv", CONDITION_FIELDS, conditions)
    write_csv(standardized / "clinical_trials.csv", TRIAL_FIELDS, trials)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_config": str(config_path),
        "input_sha256": {key: sha256_file(path) for key, path in paths.items() if path.exists()},
        "row_counts": {
            "drug_terms": len(drug_terms),
            "regimen_terms": len(regimen_terms),
            "conditions": len(conditions),
            "clinical_trials": len(trials),
        },
        "drug_term_counts_by_source": {
            str(source_id): sum(int(row[0]) == source_id for row in drug_terms)
            for source_id in (1, 2, 3, 4, 5, 7)
        },
    }
    write_json(standardized / "preprocess_manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-config", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    config = args.source_config or repo / "config" / "sources.json"
    print(json.dumps(run(repo, config.resolve()), indent=2))


if __name__ == "__main__":
    main()
