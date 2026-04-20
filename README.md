# monarch-xyz/research

Reusable research code, charts, and methodology for Monarch- and Morpho-centric analysis.

## Principles

1. Start from repo-grounded data models, not ad hoc scraping.
2. Keep study logic modular and auditable.
3. Prefer reusable Python scripts over one-off notebooks.
4. Keep generated outputs under gitignored `output/` folders.

## Current studies

- `studies/oracle_dominance_v1/`
  - modular clients (`morpho`, `monarch`, `oracle_gist`)
  - shared env/config/http helpers
  - reusable analysis/pipeline functions
  - CLI reruns via `python3 -m studies.oracle_dominance_v1.run`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
