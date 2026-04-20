from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

from studies.oracle_dominance_v1.plot_style import MUTED, MONARCH_PRIMARY, PANEL, TEXT, apply_monarch_style, series_color

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
CURRENT_CSV = OUTPUT_DIR / "vendor_dominance_current.csv"
HARDCODED_CSV = OUTPUT_DIR / "hardcoded_exposure_summary.csv"
PRIMARY_METRIC = "repriced_supply_usd"


def resolve_historical_csv(explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path)

    exact_candidates = sorted(path for path in OUTPUT_DIR.glob("vendor_dominance_*d.csv") if path.name != CURRENT_CSV.name)
    if exact_candidates:
        return exact_candidates[-1]

    fallback_candidates = sorted(
        path for path in OUTPUT_DIR.glob("vendor_dominance_*d*.csv") if path.name != CURRENT_CSV.name
    )
    if not fallback_candidates:
        raise FileNotFoundError("No historical vendor dominance CSV found. Pass --historical-csv explicitly.")
    return fallback_candidates[-1]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_json_map(value: str) -> dict[str, float]:
    if not value:
        return {}
    return {k: float(v) for k, v in json.loads(value).items()}


def aggregate_current_vendor_totals(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        for key, metric in (("supply_split_json", "supply_usd"), ("borrow_split_json", "borrow_usd")):
            for vendor, value in parse_json_map(row[key]).items():
                totals[(vendor, metric)] += value
    out = [
        {"vendor": vendor, "metric": metric, "exposure_usd": round(value, 2)}
        for (vendor, metric), value in sorted(totals.items(), key=lambda item: (item[0][1], -item[1], item[0][0]))
    ]
    return out


def load_series(rows: list[dict[str, str]], metric: str) -> dict[str, list[tuple[int, float]]]:
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        row_metric = row.get("metric")
        if row_metric != metric:
            continue
        if "timestamp" in row and row["timestamp"]:
            ts = int(row["timestamp"])
        else:
            ts = int(dt.datetime.fromisoformat(row["as_of"]).timestamp())
        series[row["vendor"]].append((ts, float(row["exposure_usd"])))
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


def build_growth_rows(series: dict[str, list[tuple[int, float]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
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


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_line_chart(series: dict[str, list[tuple[int, float]]], title: str, output_png: Path, output_svg: Path) -> None:
    apply_monarch_style(plt)
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for index, (vendor, values) in enumerate(series.items()):
        xs = [dt.datetime.utcfromtimestamp(ts) for ts, _ in values]
        ys = [value / 1_000_000 for _, value in values]
        color = MUTED if vendor == "Other" else series_color(index)
        ax.plot(xs, ys, label=vendor, color=color, linewidth=2.4)
    ax.set_title(title)
    ax.set_ylabel("USD exposure (millions)")
    ax.set_xlabel("date")
    ax.grid(True, axis="y")
    legend = ax.legend(frameon=True, ncols=2)
    for text in legend.get_texts():
        text.set_color(TEXT)
    fig.tight_layout()
    fig.savefig(output_png, dpi=180)
    fig.savefig(output_svg)
    plt.close(fig)


def normalize_share_series(series: dict[str, list[tuple[int, float]]]) -> dict[str, list[tuple[int, float]]]:
    totals: dict[int, float] = defaultdict(float)
    for values in series.values():
        for ts, value in values:
            totals[ts] += value

    normalized: dict[str, list[tuple[int, float]]] = {}
    for vendor, values in series.items():
        normalized[vendor] = []
        for ts, value in values:
            total = totals.get(ts, 0.0)
            share = 0.0 if total <= 0 else value / total * 100
            normalized[vendor].append((ts, share))
    return normalized


def plot_share_chart(series: dict[str, list[tuple[int, float]]], title: str, output_png: Path, output_svg: Path) -> None:
    apply_monarch_style(plt)
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for index, (vendor, values) in enumerate(series.items()):
        xs = [dt.datetime.utcfromtimestamp(ts) for ts, _ in values]
        ys = [value for _, value in values]
        color = MUTED if vendor == "Other" else series_color(index)
        ax.plot(xs, ys, label=vendor, color=color, linewidth=2.4)
    ax.set_title(title)
    ax.set_ylabel("Share of total exposure (%)")
    ax.set_xlabel("date")
    ax.set_ylim(0, 100)
    ax.grid(True, axis="y")
    legend = ax.legend(frameon=True, ncols=2)
    for text in legend.get_texts():
        text.set_color(TEXT)
    fig.tight_layout()
    fig.savefig(output_png, dpi=180)
    fig.savefig(output_svg)
    plt.close(fig)


def plot_growth_chart(rows: list[dict[str, object]], title: str, output_png: Path, output_svg: Path) -> None:
    apply_monarch_style(plt)
    top_rows = [row for row in rows if row["pct_gain"] is not None][:8]
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    vendors = [str(row["vendor"]) for row in top_rows][::-1]
    values = [float(row["pct_gain"]) for row in top_rows][::-1]
    colors = [series_color(i) for i in range(len(values))]
    if colors:
        colors[-1] = MONARCH_PRIMARY
    bars = ax.barh(vendors, values, color=colors)
    ax.set_title(title)
    ax.set_xlabel("Growth %")
    ax.grid(True, axis="x")
    for bar, row in zip(bars, top_rows[::-1]):
        ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height() / 2, f"${float(row['abs_gain_usd'])/1_000_000:.1f}M", va="center", color=TEXT, fontsize=10)
    fig.tight_layout()
    fig.savefig(output_png, dpi=180)
    fig.savefig(output_svg)
    plt.close(fig)


def build_summary(
    current_totals: list[dict[str, object]],
    growth_rows: list[dict[str, object]],
    hardcoded_rows: list[dict[str, str]],
    historical_rows: list[dict[str, str]],
) -> str:
    supply = [row for row in current_totals if row["metric"] == "supply_usd"]
    borrow = [row for row in current_totals if row["metric"] == "borrow_usd"]
    total_supply = sum(float(row["exposure_usd"]) for row in supply)
    total_borrow = sum(float(row["exposure_usd"]) for row in borrow)
    top_supply = supply[:5]
    best_growth = growth_rows[:5]
    hardcoded = {row["metric"]: float(row["value"]) for row in hardcoded_rows}
    point_count = len(load_series(historical_rows, PRIMARY_METRIC).get("Chainlink", []))

    lines = [
        "# Oracle dominance research summary",
        "",
        f"This report summarizes the current oracle vendor mix and recent exposure trend across the selected market set.",
        f"Current supply-weighted exposure in this cut: ${total_supply:,.0f}. Current borrow-weighted exposure: ${total_borrow:,.0f}.",
        "",
        "## Current supply dominance",
    ]
    for row in top_supply:
        share = 0 if total_supply == 0 else float(row["exposure_usd"]) / total_supply * 100
        lines.append(f"- {row['vendor']}: ${float(row['exposure_usd']):,.0f} ({share:.2f}%)")
    lines.extend([
        "",
        "## What stands out",
        f"- The largest current vendor is {top_supply[0]['vendor']} at ${float(top_supply[0]['exposure_usd']):,.0f} of supply-weighted exposure.",
        f"- Markets with hardcoded legs still matter: {hardcoded.get('markets_with_hardcoded_legs', 0):,.0f} markets, ${hardcoded.get('supply_assets_usd', 0):,.0f} supply, ${hardcoded.get('borrow_assets_usd', 0):,.0f} borrow.",
        "",
        "## Fastest growers over the observed window",
    ])
    for row in best_growth:
        lines.append(f"- {row['vendor']}: {float(row['pct_gain']):.2f}% growth, ${float(row['abs_gain_usd']):,.0f} absolute gain")
    lines.extend([
        "",
        f"Observed window in the current output: {point_count} daily points.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build charts and summary from existing oracle dominance CSV outputs")
    parser.add_argument("--current-csv", default=str(CURRENT_CSV), help="Path to vendor_dominance_current.csv")
    parser.add_argument("--historical-csv", default=None, help="Path to a historical vendor dominance CSV")
    parser.add_argument("--hardcoded-csv", default=str(HARDCODED_CSV), help="Path to hardcoded_exposure_summary.csv")
    args = parser.parse_args()

    current_rows = load_csv(Path(args.current_csv))
    historical_csv = resolve_historical_csv(args.historical_csv)
    historical_rows = load_csv(historical_csv)
    hardcoded_rows = load_csv(Path(args.hardcoded_csv))

    current_totals = aggregate_current_vendor_totals(current_rows)
    repriced_series = load_series(historical_rows, PRIMARY_METRIC)
    top_line_series = filter_top_vendors(repriced_series, top_n=8)
    top_share_series = normalize_share_series(top_line_series)
    growth_rows = build_growth_rows(repriced_series)

    write_csv(OUTPUT_DIR / "vendor_current_totals.csv", current_totals)
    write_csv(OUTPUT_DIR / "vendor_growth_from_existing.csv", growth_rows)

    plot_line_chart(
        top_line_series,
        "Oracle dominance over time (repriced supply)",
        OUTPUT_DIR / "oracle_dominance_from_existing.png",
        OUTPUT_DIR / "oracle_dominance_from_existing.svg",
    )
    plot_share_chart(
        top_share_series,
        "Oracle share over time (repriced supply, normalized to 100%)",
        OUTPUT_DIR / "oracle_share_from_existing.png",
        OUTPUT_DIR / "oracle_share_from_existing.svg",
    )
    plot_growth_chart(
        growth_rows,
        "Top oracle growers over the observed window",
        OUTPUT_DIR / "oracle_growth_from_existing.png",
        OUTPUT_DIR / "oracle_growth_from_existing.svg",
    )

    summary = build_summary(current_totals, growth_rows, hardcoded_rows, historical_rows)
    (OUTPUT_DIR / "RESEARCH_SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
