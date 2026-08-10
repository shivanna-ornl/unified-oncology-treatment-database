from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrate_sources import run as integrate_sources
from materialize import run as materialize
from preprocess_sources import run as preprocess_sources
from qa_checks import run as run_qa
from rxnorm_api import ensure_catalogs, run as validate_rxnorm
from verify_exports import run as verify_exports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the unified oncology treatment database from configured raw inputs."
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-config", type=Path)
    parser.add_argument("--refresh-rxnorm", action="store_true")
    parser.add_argument("--allow-rxnorm-version-change", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    repo = args.repo.resolve()
    config = args.source_config
    if config is None:
        local = repo / "config" / "sources.json"
        config = local if local.exists() else repo / "config" / "sources.example.json"
    config = config.resolve()

    catalogs = ensure_catalogs(
        repo,
        refresh=args.refresh_rxnorm,
        allow_version_change=args.allow_rxnorm_version_change,
    )
    preprocess = preprocess_sources(repo, config)
    integration = integrate_sources(repo)
    rxnorm = validate_rxnorm(
        repo,
        refresh=args.refresh_rxnorm,
        workers=args.workers,
        allow_version_change=args.allow_rxnorm_version_change,
    )
    release = materialize(repo)
    qa = run_qa(repo)
    export_qa = verify_exports(repo)
    result = {
        "status": "PASS"
        if qa["overall_status"] == "PASS" and export_qa["overall_status"] == "PASS"
        else "FAIL",
        "source_config": str(config),
        "rxnorm_dataset_version": rxnorm["rxnorm_dataset_version"],
        "rxnorm_api_version": rxnorm["rxnorm_api_version"],
        "preprocessed_rows": preprocess["row_counts"],
        "integrated_rows": integration["row_counts"],
        "production_rows": release["row_counts"],
        "qa_status": qa["overall_status"],
        "export_qa_status": export_qa["overall_status"],
        "catalog_concepts": len(catalogs["core_concepts"]) + len(catalogs["product_concepts"]),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
