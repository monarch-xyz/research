# Oracle Dominance v1

Reusable research pipeline for Morpho market-level oracle vendor dominance.

## Structure

- `run.py`: CLI entrypoint for public reruns
- `pipeline.py`: high-level orchestration and reusable exports
- `models.py`: shared data classes
- `analysis.py`: oracle path decomposition, allocation, and aggregation
- `clients/morpho.py`: Morpho GraphQL market + historical time-series client
- `clients/monarch.py`: Monarch indexer market universe client
- `clients/oracle_gist.py`: scanner gist metadata client
- `utils/env.py`: local env resolution (read-only; does not write secrets)
- `utils/http.py`: shared JSON HTTP helpers
- `build_oracle_dominance_report.py`: chart/report builder from live pipeline functions
- `build_report_from_existing.py`: chart/report builder from existing CSV outputs
- `output/`: gitignored study outputs

## Method

1. Fetch live markets and apply cutoff/filter policy.
2. Break each market oracle path into recognized vendors and assumption legs.
3. Build current exposure totals and historical vendor time-series.

## CLI

Run from repo root:

```bash
python3 -m studies.oracle_dominance_v1.run \
  --output-dir studies/oracle_dominance_v1/output \
  --days 180 \
  --min-borrow-usd 500000 \
  --recognized-tokens-only

python3 -m studies.oracle_dominance_v1.build_oracle_dominance_report \
  --days 90 \
  --top-markets 100 \
  --min-borrow-usd 500000 \
  --recognized-tokens-only
```

Optional methodology flags:

- `--require-listed`: include only markets present in the Monarch indexer universe
- `--recognized-tokens-only`: exclude unknown-token-symbol markets

Default methodology is public-data oriented:

- `min borrow USD`: `500000`
- `require listed`: `false`
- `recognized tokens only`: `false`

## Outputs

Primary CSV outputs:

- `vendor_dominance_current.csv`
- `vendor_dominance_<days>d.csv`
- `hardcoded_exposure_summary.csv`

Current note:
- assumption exposure outputs in this v1 study are still heuristic and should not be treated as final public headline numbers until the shared assumption engine is locked.
