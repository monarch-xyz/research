from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import run_v1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Monarch/Morpho oracle dominance v1 pipeline")
    parser.add_argument("--output-dir", default="research/oracle_dominance_v1/output", help="Directory for CSV outputs")
    parser.add_argument("--days", type=int, default=180, help="Historical lookback window in days")
    args = parser.parse_args()

    result = run_v1(Path(args.output_dir), days=args.days)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
