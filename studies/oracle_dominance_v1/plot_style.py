"""Monarch-aligned plotting defaults for research charts."""

from __future__ import annotations

MONARCH_PRIMARY = "#f45f2d"
BACKGROUND = "#0b0f14"
PANEL = "#121821"
GRID = "#2a3441"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
OTHER = "#64748b"

SERIES = [
    "#f45f2d",  # Monarch primary
    "#4E79A7",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#76B7B2",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
    OTHER,
]


def apply_monarch_style(plt):
    """Apply a reusable matplotlib theme for Monarch research output."""
    plt.rcParams.update(
        {
            "figure.facecolor": BACKGROUND,
            "axes.facecolor": PANEL,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT,
            "axes.titlecolor": TEXT,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "grid.color": GRID,
            "grid.alpha": 0.35,
            "text.color": TEXT,
            "legend.facecolor": PANEL,
            "legend.edgecolor": GRID,
            "savefig.facecolor": BACKGROUND,
            "savefig.edgecolor": BACKGROUND,
            "font.size": 11,
            "axes.titlesize": 15,
            "axes.labelsize": 11,
        }
    )


def series_color(index: int) -> str:
    return SERIES[index % len(SERIES)]
