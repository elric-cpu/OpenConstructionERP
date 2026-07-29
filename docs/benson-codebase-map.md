# Benson Integrated Codebase Map

## Baseline

- Upstream release: OpenConstructionERP `v12.9.0`
- Pinned commit: `19bd8e0856b549e40472e2b57a6c82b8a0722a73`
- Preserved baseline: 7,564 tracked paths and 183 backend module directories
- Archived prior fork: `archive/benson-fork-0072bc061`

## Additive Surfaces

| Path | Purpose |
|---|---|
| `backend/app/modules/benson_*` | Edition adapters over upstream business services |
| `backend/app/core/edition.py` | English-only locale and project-context policy |
| `frontend/src/editions/` | Compile-time edition and locale-loader overlay |
| `frontend/src/modules/benson-operations/` | Additive route, navigation, and search registration |
| `packs/benson-eastern-oregon/` | Partner pack extending the upstream US profile |
| `scripts/verify_upstream_parity.py` | Mechanical upstream-subset proof |
| `scripts/check_benson_artifact.py` | English-only artifact proof |
| `benson-app/`, `benson-erp/` | Preserved references; not production runtimes |

## Edition Contract

The production image is built with `OE_EDITION=benson`,
`OE_SUPPORTED_LOCALES=en`, `OE_DEFAULT_LOCALE=en-US`, and
`OE_DEFAULT_REGION=benson_eastern_oregon`. County, local jurisdiction, and an
IANA timezone are required on each Benson project. The operating profile never
uses a county allowlist and never assumes all Eastern Oregon work is in Pacific
time.
