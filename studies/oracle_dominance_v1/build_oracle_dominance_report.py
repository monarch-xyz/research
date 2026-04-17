from __future__ import annotations

import csv
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt

from pipeline import (
    MarketRef,
    allocate_evenly,
    build_current_exposure_table,
    build_market_vendor_allocation,
    fetch_live_markets,
    fetch_market_history,
    fetch_oracle_metadata,
    infer_current_loan_asset_prices,
)
from plot_style import MUTED, MONARCH_PRIMARY, PANEL, TEXT, apply_monarch_style, series_color

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
TOP_HISTORY_MARKETS = 100
HISTORY_DAYS = 180
MAX_WORKERS = 12
PRIMARY_METRIC = "repriced_supply_usd"


def parse_json_map(value: str) -> dict[str, float]:
    if not value:
        return {}
    return {k: float(v) for k, v in json.loads(value).items()}


def aggregate_current_vendor_totals(current_rows: list[dict]) -> list[dict]:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for row in current_rows:
        for metric_key, output_metric in (("supply_split_json", "supply_usd"), ("borrow_split_json", "borrow_usd")):
            for vendor, value in parse_json_map(row[metric_key]).items():
                totals[(vendor, output_metric)] += value

    rows = [
        {"vendor": vendor, "metric": metric, "exposure_usd": round(value, 2)}
        for (vendor, metric), value in sorted(totals.items(), key=lambda item: (item[0][1], -item[1], item[0][0]))
    ]
    return rows


def select_top_history_markets(markets: list[MarketRef], metadata: dict, top_n: int) -> list[tuple[MarketRef, list[str]]]:
    scored: list[tuple[MarketRef, list[str]]] = []
    for market in markets:
        oracle_output = metadata.get((market.chain_id, market.oracle_address))
        allocation = build_market_vendor_allocation(market, oracle_output)
        if not allocation.vendors:
            continue
        if (market.supply_assets_usd or 0) <= 0:
            continue
        scored.append((market, allocation.vendors))

    scored.sort(key=lambda item: item[0].supply_assets_usd or 0, reverse=True)
    return scored[:top_n]


def fetch_one_history(market: MarketRef, vendors: list[str], current_prices: dict[tuple[int, str], float]) -> tuple[MarketRef, list[dict], list[str]]:
    history = fetch_market_history(market.unique_key, market.chain_id, days=HISTORY_DAYS)
    current_price = current_prices.get((market.chain_id, market.loan_asset_address))
    rows: list[dict] = []
    for point in history:
        supply_usd = float(point.get("supplyAssetsUsd") or 0)
        borrow_usd = float(point.get("borrowAssetsUsd") or 0)
        repriced_supply = None
        repriced_borrow = None
        if current_price is not None:
            if point.get("supplyAssets") is not None:
                repriced_supply = (int(point["supplyAssets"]) / (10 ** market.loan_asset_decimals)) * current_price
            if point.get("borrowAssets") is not None:
                repriced_borrow = (int(point["borrowAssets"]) / (10 ** market.loan_asset_decimals)) * current_price
        rows.append(
            {
                "timestamp": int(point["timestamp"]),
                "supply_usd": supply_usd,
                "borrow_usd": borrow_usd,
                "repriced_supply_usd": float(repriced_supply if repriced_supply is not None else supply_usd),
                "repriced_borrow_usd": float(repriced_borrow if repriced_borrow is not None else borrow_usd),
            }
        )
    return market, rows, vendors


def build_historical_vendor_series(selected: list[tuple[MarketRef, list[str]]], current_prices: dict[tuple[int, str], float]) -> tuple[list[dict], list[str]]:
    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_one_history, market, vendors, current_prices): (market, vendors)
            for market, vendors in selected
        }
        for future in as_completed(futures):
            market, vendors = futures[future]
            try:
                market_obj, history_rows, vendors = future.result()
            except Exception as exc:
                errors.append(f"{market.chain_id}:{market.unique_key}: {exc}")
                continue
            for point in history_rows:
                day = point["timestamp"]
                for metric in ("supply_usd", "borrow_usd", "repriced_supply_usd", "repriced_borrow_usd"):
                    split = allocate_evenly(float(point[metric]), vendors)
                    for vendor, value in split.items():
                        totals[(str(day), vendor, metric)] += value

    rows = [
        {
            "timestamp": timestamp,
            "vendor": vendor,
            "metric": metric,
            "exposure_usd": round(value, 2),
        }
        for (timestamp, vendor, metric), value in sorted(totals.items(), key=lambda item: (int(item[0][0]), item[0][1], item[0][2]))
    ]
    return rows, errors


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_series(rows: list[dict], metric: str) -> dict[str, list[tuple[int, float]]]:
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        if row["metric"] != metric:
            continue
        series[row["vendor"]].append((int(row["timestamp"]), float(row["exposure_usd"])))
    for vendor in series:
        series[vendor].sort(key=lambda item: item[0])
    return dict(series)


def filter_top_vendors(series: dict[str, list[tuple[int, float]]], top_n: int = 8) -> dict[str, list[tuple[int, float]]]:
    ranked = sorted(series.items(), key=lambda item: item[1][-1][1] if item[1] else 0, reverse=True)
    top = dict(ranked[:top_n])
    if len(ranked) > top_n:
        other: dict[int, float] = defaultdict(float)
        for _, values in ranked[top_n:]:
            for ts, amount in values:
                other[ts] += amount
        top["Other"] = sorted(other.items())
    return top


def plot_line_chart(series: dict[str, list[tuple[int, float]]], title: str, output_png: Path, output_svg: Path) -> None:
    apply_monarch_style(plt)
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for index, (vendor, values) in enumerate(series.items()):
        xs = [ts for ts, _ in values]
        ys = [value / 1_000_000 for _, value in values]
        color = series_color(index)
        if vendor == "Other":
            color = MUTED
        ax.plot(xs, ys, label=vendor, color=color, linewidth=2.4)
    ax.set_title(title)
    ax.set_ylabel("USD exposure (millions)")
    ax.set_xlabel("timestamp")
    ax.grid(True, axis="y")
    legend = ax.legend(frameon=True, ncols=2)
    for text in legend.get_texts():
        text.set_color(TEXT)
    fig.tight_layout()
    fig.savefig(output_png, dpi=180)
    fig.savefig(output_svg)
    plt.close(fig)


def build_growth_rows(series: dict[str, list[tuple[int, float]]]) -> list[dict]:
    rows: list[dict] = []
    for vendor, values in series.items():
        if len(values) < 2 or vendor == "Other":
            continue
        first = values[0][1]
        last = values[-1][1]
        abs_gain = last - first
        pct_gain = None if first <= 0 else ((last - first) / first) * 100
        rows.append(
            {
                "vendor": vendor,
                "start_usd": round(first, 2),
                "end_usd": round(last, 2),
                "abs_gain_usd": round(abs_gain, 2),
                "pct_gain": round(pct_gain, 2) if pct_gain is not None else None,
            }
        )
    rows.sort(key=lambda row: (row["pct_gain"] is None, -(row["pct_gain"] or -10**18)))
    return rows


def plot_growth_chart(rows: list[dict], title: str, output_png: Path, output_svg: Path) -> None:
    apply_monarch_style(plt)
    top_rows = [row for row in rows if row["pct_gain"] is not None][:8]
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    vendors = [row["vendor"] for row in top_rows][::-1]
    values = [row["pct_gain"] for row in top_rows][::-1]
    bars = ax.barh(vendors, values, color=[MONARCH_PRIMARY if i == len(values) - 1 else series_color(i) for i in range(len(values))])
    ax.set_title(title)
    ax.set_xlabel("Growth %")
    ax.grid(True, axis="x")
    for bar, row in zip(bars, top_rows[::-1]):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, f"${row['abs_gain_usd']/1_000_000:.1f}M", va="center", color=TEXT, fontsize=10)
    fig.tight_layout()
    fig.savefig(output_png, dpi=180)
    fig.savefig(output_svg)
    plt.close(fig)


def write_summary(current_totals: list[dict], growth_rows: list[dict], history_errors: list[str], selected_count: int, output_path: Path) -> None:
    supply = [row for row in current_totals if row["metric"] == "supply_usd"]
    total_supply = sum(row["exposure_usd"] for row in supply)
    top_three = supply[:3]
    lines = [
        "# Oracle dominance v1 findings",
        "",
        f"- Historical series built from the top {selected_count} current markets by supply using immutable oracle composition.",
        f"- Current recognized supply exposure in this cut: ${total_supply:,.0f}.",
        f"- Top 3 current supply vendors: " + ", ".join(f"{row['vendor']} (${row['exposure_usd']:,.0f})" for row in top_three) + ".",
    ]
    if growth_rows:
        best = growth_rows[0]
        lines.append(f"- Fastest grower by percentage over the window: {best['vendor']} ({best['pct_gain']}%, ${best['abs_gain_usd']:,.0f} absolute gain).")
    if history_errors:
        lines.append(f"- Historical fetch failures skipped: {len(history_errors)} markets.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    markets = fetch_live_markets()
    metadata = fetch_oracle_metadata()
    current_prices = infer_current_loan_asset_prices(markets)
    current_rows = build_current_exposure_table(markets, metadata)
    current_totals = aggregate_current_vendor_totals(current_rows)
    selected = select_top_history_markets(markets, metadata, TOP_HISTORY_MARKETS)
    historical_rows, history_errors = build_historical_vendor_series(selected, current_prices)
    growth_rows = build_growth_rows(load_series(historical_rows, PRIMARY_METRIC))

    write_csv(OUTPUT_DIR / 'vendor_current_totals.csv', current_totals)
    write_csv(OUTPUT_DIR / 'vendor_dominance_180d_top100.csv', historical_rows)
    write_csv(OUTPUT_DIR / 'vendor_growth_180d_top100.csv', growth_rows)
    write_csv(OUTPUT_DIR / 'history_errors.csv', [{"error": error} for error in history_errors])

    top_line_series = filter_top_vendors(load_series(historical_rows, PRIMARY_METRIC), top_n=8)
    plot_line_chart(
        top_line_series,
        'Oracle dominance over time (repriced supply, top 100 markets)',
        OUTPUT_DIR / 'oracle_dominance_180d_top100.png',
        OUTPUT_DIR / 'oracle_dominance_180d_top100.svg',
    )
    plot_growth_chart(
        growth_rows,
        'Top oracle growers over the window',
        OUTPUT_DIR / 'oracle_growth_180d_top100.png',
        OUTPUT_DIR / 'oracle_growth_180d_top100.svg',
    )
    write_summary(current_totals, growth_rows, history_errors, len(selected), OUTPUT_DIR / 'RESEARCH_SUMMARY.md')

    print(json.dumps({
        'market_count': len(markets),
        'selected_history_markets': len(selected),
        'history_error_count': len(history_errors),
        'output_dir': str(OUTPUT_DIR),
    }, indent=2))


if __name__ == '__main__':
    main()
