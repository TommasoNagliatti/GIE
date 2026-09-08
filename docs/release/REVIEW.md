# Release preparation review — 2026-09-08

## Preserved
No trained model, dataset, core mathematics, frozen demo or simulator was edited. 1,025 pre-existing functional/evidence files were compared byte-for-byte. A portable 221-file manifest covers core, models, data, demo, tests and site profile. Publication changes are README, ignore rules, requirements (previously installed SciPy), Git attributes and new documentation/audit tools.

## Original local inventory
| Folder | MiB before preparation |
|---|---:|
| .venv | 330.18 |
| .venv-demo | 334.29 |
| outputs | 304.08 |
| simulacao | 60.78 |
| models | 15.11 |
| data | 4.99 |
| docs | 0.24 |
| src | 0.21 |
| demo | 0.06 |
| tests | 0.05 |

Two non-environment files exceeded 25 MiB: Motor 2 V1 test predictions (26.01 MiB) and July EV predictions (25.82 MiB). Both remain local and ignored. No non-environment file exceeded 50 or 100 MiB. The public selection is approximately 50.8 MiB; its largest file is the V2 96-cycle JSON at 8.04 MiB.

## Security and privacy
The actual Git index was scanned for credential formats, private keys, quoted credential assignments and personal paths. No credential candidate was detected. This is a bounded scan, not an absolute guarantee. Environments, secrets files, local caches, temporary sessions and private migration archives are excluded.

Reviewed provenance references remain only in two frozen Motor 1 metadata files and the original OSM weather reference. They are preserved to avoid changing reference models and are not installation requirements. Documentation uses relative paths. Screenshots are saved demo views, not account/credential screens.

No third-party EPW weather package is included; the reproduction guide provides the source download. No license was selected automatically.

## Validation
169 tests passed; 3 historical whole-disk snapshot checks are explicitly skipped by the portable runner and covered by the new frozen manifest. No unresolved failures. A dashboard test exceeded its existing 40-second timeout once, then passed unchanged. Core and simulation tests also passed in a copy materialized from staged files alone. No training or full 24-hour simulation was repeated.

All six README images and relative README links resolve to staged files. Existing Git uses main. Publication remains a manual GitHub Desktop action. No remote is created and no push is performed by this preparation.
