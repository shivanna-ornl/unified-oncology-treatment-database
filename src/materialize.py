from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from common import normalize_surface, sha256_file, valid_surface, write_json


PUBLIC_TABLES: dict[str, list[str]] = {
    "Anchor_Drugs": ["anchor_drug_id", "anchor_drug_name"],
    "Anchor_Drugs_And_Synonyms": ["synonym_id", "anchor_drug_id", "synonym_name"],
    "Anchor_Drug_Source": ["source_id", "anchor_drug_id"],
    "Anchor_Drug_Synonym_Source": ["source_id", "synonym_id"],
    "Anchor_Regimen": ["regimen_id", "regimen_name"],
    "Regimens_And_Synonyms": [
        "regimen_synonym_id",
        "regimen_synonym",
        "source_id",
        "regimen_id",
    ],
    "Regimen_Source": ["regimen_id", "source_id"],
    "Anchor_Drugs_To_Regimens": ["regimen_id", "anchor_drug_id", "source_id"],
    "Conditions_And_Regimens": ["condition_id", "condition_name", "regimen_id", "source_id"],
    "Clinical_Trials": [
        "row_id",
        "interventions_id",
        "clinical_trial_id",
        "name",
        "other_name",
        "source_id",
    ],
    "Data_Sources": ["source_id", "dataset_name", "dataset_link", "dataset_description"],
}

AUDIT_TABLES = [
    "audit_rxnorm_semantic_overrides",
    "audit_drug_term_quarantine",
    "audit_legacy_drug_anchor_quarantine",
    "audit_regimen_synonym_quarantine",
    "audit_regimen_drug_quarantine",
    "legacy_drug_anchor_crosswalk",
    "canonical_drug_concept",
    "legacy_anchor_default",
]


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def load_csv_table(connection: sqlite3.Connection, path: Path, table_name: str) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError(f"CSV has no header: {path}")
        if not headers or len(headers) != len(set(headers)):
            raise ValueError(f"Invalid or duplicate CSV headers in {path}: {headers}")
        table = quote_identifier(table_name)
        columns = ", ".join(f"{quote_identifier(header)} TEXT" for header in headers)
        connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(f"CREATE TABLE {table} ({columns})")
        placeholders = ", ".join("?" for _ in headers)
        insert_sql = f"INSERT INTO {table} VALUES ({placeholders})"
        batch: list[list[str]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(headers):
                raise ValueError(
                    f"CSV width mismatch in {path} row {row_number}: "
                    f"expected {len(headers)}, found {len(row)}"
                )
            batch.append(row)
            if len(batch) >= 10_000:
                connection.executemany(insert_sql, batch)
                batch.clear()
        if batch:
            connection.executemany(insert_sql, batch)


def execute_sql(connection: sqlite3.Connection, path: Path) -> None:
    connection.executescript(path.read_text(encoding="utf-8"))


def create_input_indexes(connection: sqlite3.Connection) -> None:
    statements = [
        "CREATE INDEX idx_i_anchor_drug_id ON integrated_Anchor_Drugs(anchor_drug_id)",
        "CREATE INDEX idx_i_anchor_source_drug ON integrated_Anchor_Drug_Source(anchor_drug_id)",
        "CREATE INDEX idx_i_drug_syn_anchor ON integrated_Anchor_Drugs_And_Synonyms(anchor_drug_id)",
        "CREATE INDEX idx_i_drug_syn_id ON integrated_Anchor_Drugs_And_Synonyms(synonym_id)",
        "CREATE INDEX idx_i_syn_source_id ON integrated_Anchor_Drug_Synonym_Source(synonym_id)",
        "CREATE INDEX idx_i_regimen_id ON integrated_Anchor_Regimen(regimen_id)",
        "CREATE INDEX idx_i_regimen_syn_regimen ON integrated_Regimens_And_Synonyms(regimen_id)",
        "CREATE INDEX idx_i_regimen_source_regimen ON integrated_Regimen_Source(regimen_id)",
        "CREATE INDEX idx_i_drug_regimen_regimen ON integrated_Anchor_Drugs_To_Regimens(regimen_id)",
        "CREATE INDEX idx_i_drug_regimen_drug ON integrated_Anchor_Drugs_To_Regimens(anchor_drug_id)",
        "CREATE INDEX idx_i_data_source_id ON integrated_Data_Sources(source_id)",
        "CREATE INDEX idx_rxnorm_surface ON rxnorm_surface_resolution(normalized_surface_form)",
    ]
    for statement in statements:
        connection.execute(statement)


def table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")]


def export_query(
    connection: sqlite3.Connection,
    query: str,
    output_path: Path,
    expected_columns: Iterable[str] | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cursor = connection.execute(query)
    columns = [item[0] for item in cursor.description]
    if expected_columns is not None and columns != list(expected_columns):
        raise ValueError(
            f"Schema mismatch for {output_path.name}: expected {list(expected_columns)}, found {columns}"
        )
    count = 0
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        while True:
            rows = cursor.fetchmany(10_000)
            if not rows:
                break
            writer.writerows(rows)
            count += len(rows)
    return count


def run(repo: Path) -> dict[str, object]:
    cache_csv = repo / "cache" / "rxnorm" / "surface_resolution.csv"
    version_path = repo / "cache" / "rxnorm" / "version.json"
    manifest_path = repo / "cache" / "rxnorm" / "manifest.json"
    for required in (cache_csv, version_path, manifest_path):
        if not required.exists():
            raise FileNotFoundError(f"Required RxNorm cache is missing: {required}")

    build_dir = repo / "work"
    build_dir.mkdir(parents=True, exist_ok=True)
    database_path = build_dir / "treatment_validation.sqlite"
    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)
    connection.create_function("norm_surface", 1, normalize_surface, deterministic=True)
    connection.create_function("is_valid_surface", 1, lambda value: int(valid_surface(value)), deterministic=True)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    try:
        for path in sorted((repo / "work" / "provisional").glob("*.csv")):
            load_csv_table(connection, path, f"integrated_{path.stem}")
        load_csv_table(connection, cache_csv, "rxnorm_surface_resolution")
        create_input_indexes(connection)
        connection.commit()

        execute_sql(connection, repo / "sql" / "pipeline" / "01_reconstruct_integrated_staging.sql")
        execute_sql(connection, repo / "sql" / "pipeline" / "02_rxnorm_semantic_validation.sql")
        execute_sql(connection, repo / "sql" / "pipeline" / "03_materialize_production.sql")
        connection.commit()

        production_dir = repo / "outputs" / "production"
        audit_dir = repo / "audit"
        row_counts: dict[str, int] = {}
        for name, columns in PUBLIC_TABLES.items():
            row_counts[name] = export_query(
                connection,
                f"SELECT {', '.join(quote_identifier(column) for column in columns)} "
                f"FROM {quote_identifier('production_' + name)}",
                production_dir / f"{name}.csv",
                columns,
            )

        for table_name in AUDIT_TABLES:
            export_query(
                connection,
                f"SELECT * FROM {quote_identifier(table_name)}",
                audit_dir / f"{table_name}.csv",
                table_columns(connection, table_name),
            )
        export_query(
            connection,
            "SELECT * FROM rxnorm_surface_resolution",
            audit_dir / "rxnorm_surface_resolution.csv",
            table_columns(connection, "rxnorm_surface_resolution"),
        )

        rxnorm_version = json.loads(version_path.read_text(encoding="utf-8"))
        rxnorm_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        release_manifest = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": "raw source preprocessing -> priority integration -> RxNorm semantic validation -> public materialization",
            "rxnorm_dataset_version": rxnorm_version.get("version", ""),
            "rxnorm_api_version": rxnorm_version.get("apiVersion", ""),
            "rxnorm_api_root": rxnorm_manifest.get("api_root", ""),
            "public_schema_version": 1,
            "row_counts": row_counts,
            "inputs": {},
            "files": {},
        }
        input_files = (
            sorted((repo / "sql" / "reference").glob("*.sql"))
            + sorted((repo / "sql" / "pipeline").glob("*.sql"))
            + [
                repo / "metadata" / "build_release.json",
                repo / "metadata" / "source_manifest.json",
            ]
            + sorted((repo / "work" / "standardized").glob("*manifest.json"))
            + sorted((repo / "work" / "provisional").glob("*manifest.json"))
            + [cache_csv]
        )
        release_manifest["inputs"] = {
            str(path.relative_to(repo)): {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in input_files
        }
        all_release_files = sorted(production_dir.glob("*.csv")) + sorted(audit_dir.glob("*.csv"))
        release_manifest["files"] = {
            str(path.relative_to(repo)): {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in all_release_files
        }
        write_json(repo / "metadata" / "rxnorm_api_manifest.json", rxnorm_manifest)
        write_json(repo / "metadata" / "release_manifest.json", release_manifest)
        return release_manifest
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run(args.repo.resolve())
    print(json.dumps(result["row_counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
