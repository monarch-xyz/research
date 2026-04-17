from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

from plot_style import MUTED, MONARCH_PRIMARY, PANEL, TEXT, apply_monarch_style, series_color

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
CURRENT_CSV = OUTPUT_DIR / "vendor_dominance_current.csv"
HISTORICAL_CSV = OUTPUT_DIR / "vendor_dominance_6m.csv"
HARDCODED_CSV = OUTPUT_DIR / "hardcoded_exposure_summary.csv"
PRIMARY_METRIC = "repriced_supply_usd"


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


def build_summary(current_totals: list[dict[str, object]], growth_rows: list[dict[str, object]], hardcoded_rows: list[dict[str, str]]) -> str:
    supply = [row for row in current_totals if row["metric"] == "supply_usd"]
    borrow = [row for row in current_totals if row["metric"] == "borrow_usd"]
    total_supply = sum(float(row["exposure_usd"]) for row in supply)
    total_borrow = sum(float(row["exposure_usd"]) for row in borrow)
    top_supply = supply[:5]
    best_growth = growth_rows[:5]
    hardcoded = {row["metric"]: float(row["value"]) for row in hardcoded_rows}

    lines = [
        "# Oracle dominance research summary",
        "",
        "We did this to put the Chronicle and Midas support work in context.",
        "The point was not just to say Monarch shows two more oracle vendors. The point was to see where those vendors sit inside the broader Morpho / Monarch oracle stack.",
        "",
        "## Current supply dominance",
    ]
    for row in top_supply:
        share = 0 if total_supply == 0 else float(row["exposure_usd"]) / total_supply * 100
        lines.append(f"- {row['vendor']}: ${float(row['exposure_usd']):,.0f} ({share:.2f}%)")
    lines.extend([
        "",
        "## What stands out",
        f"- Chainlink is still the clear center of gravity by a wide margin: ${float(top_supply[0]['exposure_usd']):,.0f} of current supply-weighted exposure in this dataset.",
        f"- Chronicle is already meaningful in context, not just as a new logo: ${next(float(r['exposure_usd']) for r in top_supply if r['vendor']=='Chronicle'):,.0f} of current supply-weighted exposure.",
        f"- Midas is smaller today, but not trivial: ${next(float(r['exposure_usd']) for r in supply if r['vendor']=='midas'):,.0f} of current supply-weighted exposure.",
        f"- Markets with hardcoded legs still matter: {hardcoded.get('markets_with_hardcoded_legs', 0):,.0f} markets, ${hardcoded.get('supply_assets_usd', 0):,.0f} supply, ${hardcoded.get('borrow_assets_usd', 0):,.0f} borrow.",
        "",
        "## Fastest growers over the observed window",
    ])
    for row in best_growth:
        lines.append(f"- {row['vendor']}: {float(row['pct_gain']):.2f}% growth, ${float(row['abs_gain_usd']):,.0f} absolute gain")
    lines.extend([
        "",
        f"Observed window in the current output: {len(load_series(load_csv(HISTORICAL_CSV), PRIMARY_METRIC).get('Chainlink', []))} daily points over roughly 30 days.",
        "This is enough to show the current hierarchy and short-window growth, but it is not yet the full 6-month cut we want.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    current_rows = load_csv(CURRENT_CSV)
    historical_rows = load_csv(HISTORICAL_CSV)
    hardcoded_rows = load_csv(HARDCODED_CSV)

    current_totals = aggregate_current_vendor_totals(current_rows)
    repriced_series = load_series(historical_rows, PRIMARY_METRIC)
    top_line_series = filter_top_vendors(repriced_series, top_n=8)
    growth_rows = build_growth_rows(repriced_series)

    write_csv(OUTPUT_DIR / "vendor_current_totals.csv", current_totals)
    write_csv(OUTPUT_DIR / "vendor_growth_from_existing.csv", growth_rows)

    plot_line_chart(
        top_line_series,
        "Oracle dominance over time (repriced supply)",
        OUTPUT_DIR / "oracle_dominance_from_existing.png",
        OUTPUT_DIR / "oracle_dominance_from_existing.svg",
    )
    plot_growth_chart(
        growth_rows,
        "Top oracle growers over the observed window",
        OUTPUT_DIR / "oracle_growth_from_existing.png",
        OUTPUT_DIR / "oracle_growth_from_existing.svg",
    )

    summary = build_summary(current_totals, growth_rows, hardcoded_rows)
    (OUTPUT_DIR / "RESEARCH_SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
