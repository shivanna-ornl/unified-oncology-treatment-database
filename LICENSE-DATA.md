# Data licensing and attribution

## Scope

To the extent that the Unified Oncology Treatment Database contributors hold
copyright or database rights in them, files under `outputs/production/`,
`audit/`, `qa/`, and `metadata/` are distributed under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International license
([CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/),
SPDX: `CC-BY-NC-SA-4.0`). This archive-level treatment is required because
the tables incorporate and adapt terminology from the full HemOncKB release.
Rights in individual source-derived elements remain subject to their
applicable upstream terms.

Repository-authored source code and original documentation are separately
licensed under the MIT License in `LICENSE`. Raw third-party source packages
are not included in this repository or its release archives.

## HemOncKB attribution

The production and audit tables contain adapted terminology from HemOncKB,
using the 2024-06-20 full ontology export obtained through the HemOnc
Dataverse. HemOncKB is produced by HemOnc.org LLC and the full release is
available to academic and noncommercial users under CC BY-NC-SA 4.0.

HemOncKB material was modified for this database by selecting source tables
and fields; normalizing case, spelling, and whitespace; integrating and
deduplicating terminology with other sources; assigning release-local
identifiers; mapping and filtering terms using RxNorm; and separating
accepted and quarantined records. HemOnc.org LLC has not endorsed this
derived database.

Source, dataset, and license information:

- <https://hemonc.org/wiki/HemOncKB>
- <https://doi.org/10.7910/DVN/FPO4HB>
- <https://creativecommons.org/licenses/by-nc-sa/4.0/>

Redistribution or adaptation of the HemOnc-derived tables must retain
attribution, remain noncommercial, identify modifications, and use the same
CC BY-NC-SA 4.0 license.

Requested citation:

> Warner JL, Dymshyts D, Reich CG, Gurley MJ, Hochheiser H, Moldwin ZH,
> Belenkaya R, Williams AE, Yang PC. HemOnc: A new standard vocabulary for
> chemotherapy regimen representation in the OMOP Common Data Model. *Journal
> of Biomedical Informatics*. 2019;96:103239.
> <https://doi.org/10.1016/j.jbi.2019.103239>

## DrugBank Vocabulary Open Data

The DrugBank input is limited to the DrugBank Vocabulary Open Data dataset:
identifiers, names, and synonyms released under the CC0 1.0 Universal
public-domain dedication (SPDX: `CC0-1.0`). No content from DrugBank's
separately licensed full database is used. The downloaded source package is
not included; only integrated vocabulary elements appear in the derived
tables.

Source and dedication information:

- <https://go.drugbank.com/releases/latest#open-data>
- <https://creativecommons.org/publicdomain/zero/1.0/>

## Other sources

The release also contains derived elements from CanMED, NCI Thesaurus,
RxNorm, AACT/ClinicalTrials.gov, and SEER*Rx. Source versions, acquisition
locations, checksums, and applicable attribution or access terms are recorded
in `metadata/source_manifest.json`. In particular, the NCI Thesaurus source
is used under CC BY 4.0 with NCI attribution. Public-domain status or a
permissive source license does not remove the CC BY-NC-SA 4.0 terms that apply
to the combined HemOnc-derived database tables.

This file documents the project's release treatment of upstream licenses; it
does not grant rights beyond those held by the project or the upstream
licensors.
