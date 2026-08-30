from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import normalize_surface, read_csv, valid_surface, write_csv, write_json


SOURCE_PRIORITY = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 7: 6}
DATA_SOURCES = [
    (1, "HemOncKB", "https://hemonc.org/wiki/HemOncKB", "Oncology drug, regimen, and condition vocabulary."),
    (2, "CanMED", "https://seer.cancer.gov/oncologytoolbox/canmed/", "Cancer Medications Enquiry Database NDC resource."),
    (3, "DrugBank Vocabulary", "https://go.drugbank.com/releases/latest#open-data", "CC0 open-data identifiers, names, and synonyms."),
    (4, "RxNorm", "https://www.nlm.nih.gov/research/umls/rxnorm/", "Normalized clinical drug terminology and relationships."),
    (5, "NCI Thesaurus", "https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/", "NCI reference terminology."),
    (6, "AACT", "https://aact.ctti-clinicaltrials.org/downloads/snapshots", "Aggregate Analysis of ClinicalTrials.gov."),
    (7, "SEER*Rx", "https://seer.cancer.gov/seertools/seerrx/", "Oncology drug and regimen coding resource."),
]


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, first: str, second: str) -> None:
        self.add(first)
        self.add(second)
        left, right = self.find(first), self.find(second)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def integrate_drugs(rows: list[dict[str, str]]) -> tuple[dict[str, int], dict[str, str], dict[str, list[dict[str, Any]]]]:
    graph = UnionFind()
    anchor_candidates: dict[str, set[int]] = defaultdict(set)
    term_sources: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        source_id = int(row["source_id"])
        anchor = normalize_surface(row["anchor_name"])
        synonym = normalize_surface(row["synonym_name"])
        if not valid_surface(anchor):
            continue
        graph.add(anchor)
        anchor_candidates[anchor].add(source_id)
        term_sources[anchor].add(source_id)
        if valid_surface(synonym) and synonym != anchor:
            graph.union(anchor, synonym)
            term_sources[synonym].add(source_id)

    components: dict[str, set[str]] = defaultdict(set)
    for term in graph.parent:
        components[graph.find(term)].add(term)
    canonical_by_root: dict[str, str] = {}
    for root, terms in components.items():
        candidates = [
            (SOURCE_PRIORITY.get(source_id, 99), term)
            for term in terms
            for source_id in anchor_candidates.get(term, set())
        ]
        canonical_by_root[root] = min(candidates)[1] if candidates else min(terms)
    canonical_by_term = {term: canonical_by_root[graph.find(term)] for term in graph.parent}
    anchors = sorted(set(canonical_by_term.values()))
    anchor_ids = {name: index for index, name in enumerate(anchors, start=1)}

    anchor_rows = [
        {"anchor_drug_id": anchor_ids[name], "anchor_drug_name": name}
        for name in anchors
    ]
    synonyms = sorted(term for term, canonical in canonical_by_term.items() if term != canonical)
    synonym_rows = [
        {
            "synonym_id": index,
            "anchor_drug_id": anchor_ids[canonical_by_term[term]],
            "synonym_name": term,
        }
        for index, term in enumerate(synonyms, start=1)
    ]
    synonym_ids = {row["synonym_name"]: row["synonym_id"] for row in synonym_rows}
    anchor_source_rows = sorted(
        {
            (source_id, anchor_ids[canonical_by_term[term]])
            for term, sources in term_sources.items()
            for source_id in sources
        }
    )
    synonym_source_rows = sorted(
        {
            (source_id, synonym_ids[term])
            for term, sources in term_sources.items()
            if term in synonym_ids
            for source_id in sources
        }
    )
    tables: dict[str, list[dict[str, Any]]] = {
        "Anchor_Drugs": anchor_rows,
        "Anchor_Drugs_And_Synonyms": synonym_rows,
        "Anchor_Drug_Source": [
            {"source_id": source_id, "anchor_drug_id": anchor_id}
            for source_id, anchor_id in anchor_source_rows
        ],
        "Anchor_Drug_Synonym_Source": [
            {"source_id": source_id, "synonym_id": synonym_id}
            for source_id, synonym_id in synonym_source_rows
        ],
    }
    return anchor_ids, canonical_by_term, tables


def integrate_regimens(
    rows: list[dict[str, str]],
    drug_anchor_ids: dict[str, int],
    drug_canonical: dict[str, str],
) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    graph = UnionFind()
    candidates: dict[str, set[int]] = defaultdict(set)
    term_sources: dict[str, set[int]] = defaultdict(set)
    source_drugs: list[tuple[str, str, int]] = []
    for row in rows:
        source_id = int(row["source_id"])
        regimen = normalize_surface(row["regimen_name"])
        synonym = normalize_surface(row["regimen_synonym"])
        drug = normalize_surface(row["drug_name"])
        if not valid_surface(regimen):
            continue
        graph.add(regimen)
        candidates[regimen].add(source_id)
        term_sources[regimen].add(source_id)
        if valid_surface(synonym) and synonym != regimen:
            graph.union(regimen, synonym)
            term_sources[synonym].add(source_id)
        if valid_surface(drug):
            source_drugs.append((regimen, drug, source_id))

    components: dict[str, set[str]] = defaultdict(set)
    for term in graph.parent:
        components[graph.find(term)].add(term)
    canonical_by_root = {
        root: min(
            (SOURCE_PRIORITY.get(source_id, 99), term)
            for term in terms
            for source_id in candidates.get(term, {99})
        )[1]
        for root, terms in components.items()
    }
    canonical_by_term = {term: canonical_by_root[graph.find(term)] for term in graph.parent}
    names = sorted(set(canonical_by_term.values()))
    regimen_ids = {name: index for index, name in enumerate(names, start=1)}
    anchor_rows = [{"regimen_id": regimen_ids[name], "regimen_name": name} for name in names]

    synonym_rows = []
    synonym_index = 1
    for term in sorted(canonical_by_term):
        canonical = canonical_by_term[term]
        if term == canonical:
            continue
        for source_id in sorted(term_sources[term]):
            synonym_rows.append(
                {
                    "regimen_synonym_id": synonym_index,
                    "regimen_synonym": term,
                    "source_id": source_id,
                    "regimen_id": regimen_ids[canonical],
                }
            )
            synonym_index += 1
    regimen_source_rows = sorted(
        {
            (regimen_ids[canonical_by_term[term]], source_id)
            for term, sources in term_sources.items()
            for source_id in sources
        }
    )
    drug_links = set()
    missing_drugs = set()
    for regimen, drug, source_id in source_drugs:
        canonical_drug = drug_canonical.get(drug)
        if canonical_drug is None:
            missing_drugs.add(drug)
            continue
        drug_links.add((regimen_ids[canonical_by_term[regimen]], drug_anchor_ids[canonical_drug], source_id))
    tables: dict[str, list[dict[str, Any]]] = {
        "Anchor_Regimen": anchor_rows,
        "Regimens_And_Synonyms": synonym_rows,
        "Regimen_Source": [
            {"regimen_id": regimen_id, "source_id": source_id}
            for regimen_id, source_id in regimen_source_rows
        ],
        "Anchor_Drugs_To_Regimens": [
            {"regimen_id": regimen_id, "anchor_drug_id": drug_id, "source_id": source_id}
            for regimen_id, drug_id, source_id in sorted(drug_links)
        ],
        "audit_missing_regimen_drugs": [{"drug_name": name} for name in sorted(missing_drugs)],
    }
    return canonical_by_term, tables


def run(repo: Path) -> dict[str, Any]:
    standardized = repo / "work" / "standardized"
    provisional = repo / "work" / "provisional"
    provisional.mkdir(parents=True, exist_ok=True)
    drug_rows = read_csv(standardized / "drug_terms.csv")
    regimen_rows = read_csv(standardized / "regimen_terms.csv")
    drug_anchor_ids, drug_canonical, drug_tables = integrate_drugs(drug_rows)
    regimen_canonical, regimen_tables = integrate_regimens(
        regimen_rows, drug_anchor_ids, drug_canonical
    )

    conditions = []
    condition_id = 1
    regimen_name_to_id = {
        row["regimen_name"]: row["regimen_id"] for row in regimen_tables["Anchor_Regimen"]
    }
    condition_seen = set()
    for row in read_csv(standardized / "conditions.csv"):
        regimen = normalize_surface(row["regimen_name"])
        canonical = regimen_canonical.get(regimen)
        if canonical is None:
            continue
        item = (normalize_surface(row["condition_name"]), regimen_name_to_id[canonical], int(row["source_id"]))
        if item in condition_seen:
            continue
        condition_seen.add(item)
        conditions.append(
            {
                "condition_id": condition_id,
                "condition_name": item[0],
                "regimen_id": item[1],
                "source_id": item[2],
            }
        )
        condition_id += 1

    clinical_trials = []
    for index, row in enumerate(read_csv(standardized / "clinical_trials.csv"), start=1):
        clinical_trials.append(
            {
                "row_id": index,
                "interventions_id": row["interventions_id"],
                "clinical_trial_id": row["clinical_trial_id"],
                "name": row["name"],
                "other_name": row["other_name"],
                "source_id": 6,
            }
        )
    data_sources = [
        {
            "source_id": source_id,
            "dataset_name": name,
            "dataset_link": link,
            "dataset_description": description,
        }
        for source_id, name, link, description in DATA_SOURCES
    ]

    schemas = {
        "Anchor_Drugs": ["anchor_drug_id", "anchor_drug_name"],
        "Anchor_Drugs_And_Synonyms": ["synonym_id", "anchor_drug_id", "synonym_name"],
        "Anchor_Drug_Source": ["source_id", "anchor_drug_id"],
        "Anchor_Drug_Synonym_Source": ["source_id", "synonym_id"],
        "Anchor_Regimen": ["regimen_id", "regimen_name"],
        "Regimens_And_Synonyms": ["regimen_synonym_id", "regimen_synonym", "source_id", "regimen_id"],
        "Regimen_Source": ["regimen_id", "source_id"],
        "Anchor_Drugs_To_Regimens": ["regimen_id", "anchor_drug_id", "source_id"],
        "Conditions_And_Regimens": ["condition_id", "condition_name", "regimen_id", "source_id"],
        "Clinical_Trials": ["row_id", "interventions_id", "clinical_trial_id", "name", "other_name", "source_id"],
        "Data_Sources": ["source_id", "dataset_name", "dataset_link", "dataset_description"],
    }
    tables = {
        **drug_tables,
        **{key: value for key, value in regimen_tables.items() if not key.startswith("audit_")},
        "Conditions_And_Regimens": conditions,
        "Clinical_Trials": clinical_trials,
        "Data_Sources": data_sources,
    }
    for name, fields in schemas.items():
        write_csv(provisional / f"{name}.csv", fields, tables[name])
    write_csv(
        repo / "audit" / "missing_regimen_drug_terms.csv",
        ["drug_name"],
        regimen_tables["audit_missing_regimen_drugs"],
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_priority": [1, 2, 3, 4, 5, 7],
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "missing_regimen_drug_terms": len(regimen_tables["audit_missing_regimen_drugs"]),
    }
    write_json(provisional / "integration_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run(args.repo.resolve()), indent=2))


if __name__ == "__main__":
    main()
