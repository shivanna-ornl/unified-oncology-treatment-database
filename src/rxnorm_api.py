from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import normalize_surface, pipe_join, read_csv, read_json, sha256_file, write_csv, write_json


API_ROOT = "https://rxnav.nlm.nih.gov/REST"
CORE_TTYS = {"IN", "MIN", "PIN", "BN"}
PRODUCT_TTYS = {
    "SCDC",
    "SBDC",
    "SCDF",
    "SBDF",
    "SCDFP",
    "SBDFP",
    "SCDG",
    "SBDG",
    "SCDGP",
    "SCD",
    "SBD",
}
PACK_TTYS = {"GPCK", "BPCK"}
ALL_TTYS = CORE_TTYS | PRODUCT_TTYS | PACK_TTYS


def fetch_json(url: str, attempts: int = 5) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "unified-oncology-treatment-database/1.0",
        },
    )
    error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = exc
            time.sleep(min(8, attempt * 0.75))
    raise RuntimeError(f"RxNorm request failed after {attempts} attempts: {url}: {error}")


def fetch_concept_group(ttys: list[str]) -> list[dict[str, str]]:
    tty_value = "+".join(ttys)
    url = f"{API_ROOT}/allconcepts.json?tty={urllib.parse.quote_plus(tty_value, safe='+')}"
    payload = fetch_json(url)
    return payload.get("minConceptGroup", {}).get("minConcept", []) or []


def load_surfaces(repo: Path) -> set[str]:
    baseline = repo / "work" / "provisional"
    surfaces: set[str] = set()
    for row in read_csv(baseline / "Anchor_Drugs.csv"):
        surface = normalize_surface(row.get("anchor_drug_name"))
        if surface:
            surfaces.add(surface)
    for row in read_csv(baseline / "Anchor_Drugs_And_Synonyms.csv"):
        surface = normalize_surface(row.get("synonym_name"))
        if surface and surface not in {"none", "null", "n/a", "na"}:
            surfaces.add(surface)
    return surfaces


def expected_version(repo: Path) -> dict[str, str]:
    path = repo / "metadata" / "build_release.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        "version": str(payload.get("rxnorm_dataset_version", "")),
        "apiVersion": str(payload.get("rxnorm_api_version", "")),
    }


def load_core_concepts(cache_dir: Path) -> list[dict[str, str]]:
    payload = read_json(cache_dir / "allconcepts_in_min_pin_bn.json")
    return payload.get("minConceptGroup", {}).get("minConcept", []) or []


def classify_tty(tty: str) -> str:
    if tty == "IN":
        return "single_ingredient"
    if tty == "MIN":
        return "multi_ingredient"
    if tty == "PIN":
        return "precise_ingredient"
    if tty == "BN":
        return "brand"
    if tty in PACK_TTYS:
        return "pack"
    if tty in PRODUCT_TTYS:
        return "product_or_formulation"
    return "other"


def simplify_related(payload: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = {"IN": [], "MIN": []}
    groups = payload.get("relatedGroup", {}).get("conceptGroup", []) or []
    for group in groups:
        tty = group.get("tty")
        if tty not in output:
            continue
        for item in group.get("conceptProperties", []) or []:
            output[tty].append(
                {
                    "rxcui": str(item.get("rxcui", "")),
                    "name": str(item.get("name", "")),
                    "tty": tty,
                }
            )
    for tty in output:
        output[tty] = list({item["rxcui"]: item for item in output[tty]}.values())
    return output


def resolve_concept(
    concept: dict[str, str],
    related: dict[str, dict[str, list[dict[str, str]]]],
) -> dict[str, str]:
    tty = concept["tty"]
    if tty in {"IN", "MIN"}:
        return {
            "status": "accepted",
            "canonical_rxcui": concept["rxcui"],
            "canonical_name": concept["name"],
            "canonical_tty": tty,
            "rule": f"exact_{tty.lower()}",
        }
    if tty in PACK_TTYS:
        return {
            "status": "quarantine_pack",
            "canonical_rxcui": "",
            "canonical_name": "",
            "canonical_tty": "",
            "rule": "pack_not_ingredient_target",
        }

    candidates = related.get(concept["rxcui"], {"IN": [], "MIN": []})
    mins = candidates.get("MIN", [])
    ingredients = candidates.get("IN", [])
    if len(mins) == 1:
        selected = mins[0]
        return {
            "status": "accepted",
            "canonical_rxcui": selected["rxcui"],
            "canonical_name": selected["name"],
            "canonical_tty": "MIN",
            "rule": f"{tty.lower()}_to_unique_min",
        }
    if len(mins) == 0 and len(ingredients) == 1:
        selected = ingredients[0]
        return {
            "status": "accepted",
            "canonical_rxcui": selected["rxcui"],
            "canonical_name": selected["name"],
            "canonical_tty": "IN",
            "rule": f"{tty.lower()}_to_unique_in",
        }
    if not mins and not ingredients:
        status = "quarantine_no_ingredient_relation"
        rule = f"{tty.lower()}_without_related_in_min"
    else:
        status = "quarantine_ambiguous_relation"
        rule = f"{tty.lower()}_multiple_related_in_min"
    return {
        "status": status,
        "canonical_rxcui": "",
        "canonical_name": "",
        "canonical_tty": "",
        "rule": rule,
    }


def build_surface_resolution(
    surfaces: set[str],
    concepts: list[dict[str, str]],
    related: dict[str, dict[str, list[dict[str, str]]]],
) -> list[dict[str, str | int]]:
    concepts_by_surface: dict[str, list[dict[str, str]]] = defaultdict(list)
    for concept in concepts:
        normalized = normalize_surface(concept.get("name"))
        if normalized in surfaces:
            concepts_by_surface[normalized].append(concept)

    rows: list[dict[str, str | int]] = []
    for surface in sorted(surfaces):
        matches = concepts_by_surface.get(surface, [])
        if not matches:
            rows.append(
                {
                    "normalized_surface_form": surface,
                    "match_count": 0,
                    "matched_rxcuis": "",
                    "matched_ttys": "",
                    "matched_names": "",
                    "concept_classes": "",
                    "mapping_status": "unmatched",
                    "mapping_rule": "no_exact_active_rxnorm_concept",
                    "canonical_rxcui": "",
                    "canonical_name": "",
                    "canonical_tty": "",
                }
            )
            continue

        decisions = [resolve_concept(match, related) for match in matches]
        accepted = {
            (decision["canonical_rxcui"], decision["canonical_name"], decision["canonical_tty"])
            for decision in decisions
            if decision["status"] == "accepted"
        }
        rejected_statuses = {decision["status"] for decision in decisions if decision["status"] != "accepted"}
        if len(accepted) == 1 and not rejected_statuses:
            canonical_rxcui, canonical_name, canonical_tty = next(iter(accepted))
            mapping_status = "accepted"
            mapping_rule = pipe_join(decision["rule"] for decision in decisions)
        elif len(accepted) == 1 and rejected_statuses <= {"quarantine_no_ingredient_relation"}:
            canonical_rxcui, canonical_name, canonical_tty = next(iter(accepted))
            mapping_status = "accepted"
            mapping_rule = pipe_join(decision["rule"] for decision in decisions if decision["status"] == "accepted")
        elif not accepted and rejected_statuses == {"quarantine_pack"}:
            canonical_rxcui = canonical_name = canonical_tty = ""
            mapping_status = "quarantine_pack"
            mapping_rule = "pack_not_ingredient_target"
        elif not accepted:
            canonical_rxcui = canonical_name = canonical_tty = ""
            mapping_status = "quarantine_unresolved_rxnorm_concept"
            mapping_rule = pipe_join(decision["rule"] for decision in decisions)
        else:
            canonical_rxcui = canonical_name = canonical_tty = ""
            mapping_status = "quarantine_multiple_canonical_targets"
            mapping_rule = "exact_surface_resolves_to_multiple_in_min_targets"

        rows.append(
            {
                "normalized_surface_form": surface,
                "match_count": len(matches),
                "matched_rxcuis": pipe_join(match["rxcui"] for match in matches),
                "matched_ttys": pipe_join(match["tty"] for match in matches),
                "matched_names": pipe_join(match["name"] for match in matches),
                "concept_classes": pipe_join(classify_tty(match["tty"]) for match in matches),
                "mapping_status": mapping_status,
                "mapping_rule": mapping_rule,
                "canonical_rxcui": canonical_rxcui,
                "canonical_name": normalize_surface(canonical_name),
                "canonical_tty": canonical_tty,
            }
        )
    return rows


def ensure_catalogs(
    repo: Path,
    refresh: bool = False,
    allow_version_change: bool = False,
) -> dict[str, Any]:
    cache_dir = repo / "cache" / "rxnorm"
    cache_dir.mkdir(parents=True, exist_ok=True)
    version_path = cache_dir / "version.json"
    if refresh or not version_path.exists():
        version_payload = fetch_json(f"{API_ROOT}/version.json")
        write_json(version_path, version_payload)
    else:
        version_payload = read_json(version_path)
    expected = expected_version(repo)
    if (
        expected.get("version")
        and (
            version_payload.get("version") != expected.get("version")
            or version_payload.get("apiVersion") != expected.get("apiVersion")
        )
        and not allow_version_change
    ):
        raise RuntimeError(
            "RxNorm version does not match the publication build: "
            f"expected {expected}, found {version_payload}. "
            "Use --allow-version-change only when creating a new documented release."
        )

    core_path = cache_dir / "allconcepts_in_min_pin_bn.json"
    seed_version_path = cache_dir / "version_seed.json"
    seed_version = read_json(seed_version_path) if seed_version_path.exists() else {}
    if (
        refresh
        or not core_path.exists()
        or seed_version.get("version") != version_payload.get("version")
        or seed_version.get("apiVersion") != version_payload.get("apiVersion")
    ):
        core_concepts = fetch_concept_group(sorted(CORE_TTYS))
        write_json(core_path, {"minConceptGroup": {"minConcept": core_concepts}})
        write_json(seed_version_path, version_payload)
    else:
        core_concepts = load_core_concepts(cache_dir)
    product_path = cache_dir / "allconcepts_product_form_pack.json"
    if refresh or not product_path.exists():
        product_concepts: list[dict[str, str]] = []
        for tty_group in [
            sorted(PRODUCT_TTYS),
            sorted(PACK_TTYS),
        ]:
            product_concepts.extend(fetch_concept_group(tty_group))
        write_json(
            product_path,
            {"minConceptGroup": {"minConcept": product_concepts}},
        )
    else:
        product_payload = read_json(product_path)
        product_concepts = product_payload.get("minConceptGroup", {}).get("minConcept", []) or []
    return {
        "version": version_payload,
        "core_concepts": core_concepts,
        "product_concepts": product_concepts,
        "core_path": core_path,
        "product_path": product_path,
        "version_path": version_path,
    }


def run(
    repo: Path,
    refresh: bool = False,
    workers: int = 12,
    allow_version_change: bool = False,
) -> dict[str, Any]:
    cache_dir = repo / "cache" / "rxnorm"
    catalogs = ensure_catalogs(repo, refresh=refresh, allow_version_change=allow_version_change)
    surfaces = load_surfaces(repo)
    if not surfaces:
        raise RuntimeError("No provisional drug surfaces found; run source preprocessing and integration first.")
    version_payload = catalogs["version"]
    core_concepts = catalogs["core_concepts"]
    product_concepts = catalogs["product_concepts"]
    core_path = catalogs["core_path"]
    product_path = catalogs["product_path"]
    version_path = catalogs["version_path"]

    concepts_by_id: dict[str, dict[str, str]] = {}
    for item in core_concepts + product_concepts:
        tty = str(item.get("tty", ""))
        if tty not in ALL_TTYS:
            continue
        concept = {
            "rxcui": str(item.get("rxcui", "")),
            "name": str(item.get("name", "")),
            "tty": tty,
        }
        concepts_by_id[f"{concept['rxcui']}\u0000{tty}"] = concept
    concepts = list(concepts_by_id.values())

    matched_noncanonical = {
        concept["rxcui"]
        for concept in concepts
        if concept["tty"] not in {"IN", "MIN"}
        and concept["tty"] not in PACK_TTYS
        and normalize_surface(concept["name"]) in surfaces
    }

    related_raw_path = cache_dir / "related_in_min_raw.json"
    related_raw = read_json(related_raw_path) if related_raw_path.exists() and not refresh else {}
    missing = sorted(matched_noncanonical - set(related_raw))

    def fetch_related(rxcui: str) -> tuple[str, dict[str, Any]]:
        url = f"{API_ROOT}/rxcui/{urllib.parse.quote(rxcui)}/related.json?tty=IN+MIN"
        return rxcui, fetch_json(url)

    if missing:
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_related, rxcui): rxcui for rxcui in missing}
            for future in concurrent.futures.as_completed(futures):
                rxcui, payload = future.result()
                related_raw[rxcui] = payload
                completed += 1
                if completed % 100 == 0 or completed == len(missing):
                    print(f"RxNorm relationships: {completed}/{len(missing)}")
        write_json(related_raw_path, related_raw)
    elif not related_raw_path.exists():
        write_json(related_raw_path, related_raw)

    related_raw = {
        rxcui: related_raw[rxcui]
        for rxcui in sorted(matched_noncanonical)
        if rxcui in related_raw
    }
    write_json(related_raw_path, related_raw)

    related = {rxcui: simplify_related(payload) for rxcui, payload in related_raw.items()}
    surface_rows = build_surface_resolution(surfaces, concepts, related)
    write_csv(
        cache_dir / "surface_resolution.csv",
        [
            "normalized_surface_form",
            "match_count",
            "matched_rxcuis",
            "matched_ttys",
            "matched_names",
            "concept_classes",
            "mapping_status",
            "mapping_rule",
            "canonical_rxcui",
            "canonical_name",
            "canonical_tty",
        ],
        surface_rows,
    )

    version_after = fetch_json(f"{API_ROOT}/version.json") if refresh or missing else version_payload
    if version_after != version_payload:
        raise RuntimeError(f"RxNorm version changed during fetch: {version_payload} -> {version_after}")

    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rxnorm_dataset_version": version_payload.get("version", ""),
        "rxnorm_api_version": version_payload.get("apiVersion", ""),
        "api_root": API_ROOT,
        "version_endpoint": f"{API_ROOT}/version.json",
        "allconcepts_endpoint": f"{API_ROOT}/allconcepts.json?tty=<TTY_LIST>",
        "related_endpoint_template": f"{API_ROOT}/rxcui/<RXCUI>/related.json?tty=IN+MIN",
        "surface_count": len(surfaces),
        "concept_count": len(concepts),
        "matched_noncanonical_rxcui_count": len(matched_noncanonical),
        "related_response_count": len(related_raw),
        "automatic_matching": "normalized exact surface match only",
        "canonical_target_ttys": ["IN", "MIN"],
        "cache_sha256": {
            "allconcepts_in_min_pin_bn.json": sha256_file(core_path),
            "allconcepts_product_form_pack.json": sha256_file(product_path),
            "related_in_min_raw.json": sha256_file(related_raw_path),
            "surface_resolution.csv": sha256_file(cache_dir / "surface_resolution.csv"),
            "version.json": sha256_file(version_path),
        },
    }
    write_json(cache_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--allow-version-change", action="store_true")
    args = parser.parse_args()
    run(
        args.repo.resolve(),
        refresh=args.refresh,
        workers=args.workers,
        allow_version_change=args.allow_version_change,
    )


if __name__ == "__main__":
    main()
