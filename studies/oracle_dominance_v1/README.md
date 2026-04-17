# Oracle Dominance v1

This folder is the reusable starting point for Monarch / Morpho oracle research.

## Why this exists

The goal is to stop re-deriving the same workflow every time we want to publish a market-structure or oracle-vendor post.

This v1 pipeline is built around code that already exists in:
- Monarch frontend market + historical fetchers
- the `oracles` scanner and its published metadata

## Canonical inputs

### 1. Market discovery
Use Monarch-first market discovery, with Morpho API as the fallback reference.

Relevant files:
- `../src/sources/monarchApi.ts`
- `/Users/anton/projects/monarch/src/data-sources/morpho-api/market.ts`
- `/Users/anton/projects/monarch/src/graphql/morpho-api-queries.ts`

### 2. Oracle composition
Use scanner-native oracle metadata, not ad hoc parsing.

Relevant files:
- `../src/types.ts`
- `../src/scanner.ts`
- `../src/analyzers/feedProviderMatcher.ts`
- `/Users/anton/projects/monarch/src/hooks/useOracleMetadata.ts`

### 3. Historical market state
Use Morpho historical market state shape as the reference time series.

Relevant file:
- `/Users/anton/projects/monarch/src/data-sources/morpho-api/historical.ts`

## v1 attribution rules

1. A market's oracle composition is treated as immutable.
2. Extract all recognized vendor legs from the market's oracle metadata.
3. Split market responsibility evenly across recognized vendors.
4. Track hardcoded / non-vendor legs separately.
5. Keep both supply-weighted and borrow-weighted exposure.
6. For the special "current price applied to historical balances" view, reprice historical token balances using the latest token USD price.

## Intended outputs

- `vendor_dominance_current.csv`
- `vendor_dominance_6m.csv`
- `hardcoded_exposure_summary.csv`
- `oracle_dominance_6m.svg`
- `oracle_dominance_6m.png`
- `oracle_top_growers_6m.svg`
- `oracle_top_growers_6m.png`

## Publishing workflow

1. run analysis
2. inspect output tables
3. generate charts
4. draft research summary
5. apply anti-slop editing
6. publish findings and source code together

## Run it

From `/Users/anton/projects/oracles`:

```bash
python3 research/oracle_dominance_v1/run.py --output-dir research/oracle_dominance_v1/output --days 180
```

This currently writes CSV outputs for:
- current vendor dominance
- 6 month vendor time series
- hardcoded exposure summary

## Notes

This folder is deliberately Python-first for plotting speed and notebook ergonomics.
The source of truth still comes from the TypeScript repos above.
