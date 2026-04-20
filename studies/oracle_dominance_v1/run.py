from __future__ import annotations

import argparse
import json
from pathlib import Path

from studies.oracle_dominance_v1.pipeline import run_v1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Monarch/Morpho oracle dominance v1 pipeline")
    parser.add_argument(
        "--output-dir",
        default="studies/oracle_dominance_v1/output",
        help="Directory for CSV outputs",
    )
    parser.add_argument("--days", type=int, default=180, help="Historical lookback window in days")
    parser.add_argument(
        "--min-borrow-usd",
        type=float,
        default=500_000,
        help="Minimum current market borrow USD for inclusion",
    )
    parser.add_argument(
        "--require-listed",
        action="store_true",
        help="Only include markets listed in the Monarch indexer universe",
    )
    parser.add_argument(
        "--recognized-tokens-only",
        action="store_true",
        help="Exclude markets whose loan/collateral token symbols are unknown",
    )
    args = parser.parse_args()

    result = run_v1(
        Path(args.output_dir),
        days=args.days,
        min_borrow_usd=args.min_borrow_usd,
        require_listed=args.require_listed,
        recognized_tokens_only=args.recognized_tokens_only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
