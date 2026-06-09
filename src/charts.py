"""Publication-quality matplotlib figures for the fact sheet + dashboard.

Figure 1 (signature): "The Innovation Clock" stacked timeline — each negotiated
    drug is a lane from approval (year 0) to its last new indication, with a dot
    per new indication and a vertical clock line at year 9 (small molecule) or 13
    (biologic); the price-controlled region after the clock is shaded.
Figure 2: spend x time-to-last-indication scatter, colored by modality.

Saves SVG + PNG to factsheet/figures/.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from . import util

FIG_DIR = util.ROOT / "factsheet" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
JSON_IN = util.PROCESSED / "dashboard_data.json"

# Restrained policy-report palette
C_SM = "#1b6ca8"     # small molecule (blue)
C_BIO = "#d4761f"    # biologic (amber)
C_CLOCK = "#444444"
C_AFTER = "#e8b4b8"  # price-controlled region shading
INK = "#222222"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#888888", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 150,
})


def _load() -> Dict[str, Any]:
    return json.loads(JSON_IN.read_text())


def _color(mod: str) -> str:
    return C_BIO if mod == "biologic" else C_SM


def timeline(payload: Dict[str, Any], negotiated_only: bool = True,
             fname: str = "fig1_innovation_clock") -> str:
    drugs = [d for d in payload["drugs"] if d["modality"] and d["original_approval_date"]]
    if negotiated_only:
        drugs = [d for d in drugs if d["in_negotiated"]]
    # sort: biologics group then small molecule, each by approval date
    drugs.sort(key=lambda d: (d["modality"] != "small molecule", d["original_approval_date"]))

    n = len(drugs)
    fig, ax = plt.subplots(figsize=(7.6, max(4.0, 0.133 * n + 0.9)))
    xmax = 0
    for i, d in enumerate(drugs):
        y = n - i
        clk = d["clock_year"]
        col = _color(d["modality"])
        years = [iv["years_after_launch"] for iv in d["indications"] if iv["years_after_launch"] is not None]
        last = max(years) if years else 0
        xmax = max(xmax, last, clk)
        # baseline from 0 to last indication
        ax.plot([0, max(last, clk)], [y, y], color="#dddddd", lw=0.8, zorder=1)
        # approval marker (year 0)
        ax.scatter([0], [y], s=18, color=col, marker="|", zorder=3)
        # indication dots, colored darker if after the clock
        for yr in years:
            after = yr >= clk
            ax.scatter([yr], [y], s=15,
                       color=col, edgecolor=(C_CLOCK if after else "none"),
                       linewidth=0.6, alpha=0.95 if after else 0.7, zorder=4)
        # clock tick
        ax.scatter([clk], [y], s=26, marker="d", color=C_CLOCK, zorder=5)
        ax.text(-0.4, y, d["brand"], ha="right", va="center", fontsize=5.6, color=INK)

    xmax = min(xmax + 1, 28)
    # shade typical price-controlled regions (9+ and 13+) lightly as guides
    ax.axvspan(9, xmax, color=C_AFTER, alpha=0.10, zorder=0)
    ax.axvline(9, color=C_SM, ls=":", lw=1.0, alpha=0.7)
    ax.axvline(13, color=C_BIO, ls=":", lw=1.0, alpha=0.7)
    ax.text(9, n + 1.0, "clock yr 9", color=C_SM, fontsize=6, ha="center")
    ax.text(13, n + 1.8, "clock yr 13", color=C_BIO, fontsize=6, ha="center")

    ax.set_xlim(0, xmax)
    ax.set_ylim(0, n + 2.4)
    ax.set_yticks([])
    ax.set_xlabel("Years after first FDA approval", fontsize=8)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_title("The Innovation Clock: new indications vs. the Medicare negotiation deadline",
                 fontsize=9.5, color=INK, loc="left", pad=8)
    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C_SM, markersize=7, label="Small molecule indication"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C_BIO, markersize=7, label="Biologic indication"),
        Line2D([0], [0], marker="d", color="w", markerfacecolor=C_CLOCK, markersize=8, label="Negotiation clock"),
        Patch(facecolor=C_AFTER, alpha=0.3, label="Price-controlled region"),
    ]
    ax.legend(handles=legend, loc="upper right", fontsize=6.5, frameon=True,
              facecolor="white", edgecolor="#dddddd", framealpha=0.9)
    fig.tight_layout()
    return _save(fig, fname)


def scatter(payload: Dict[str, Any], fname: str = "fig2_spend_vs_time") -> str:
    # canonical cohort = the 40 IRA-negotiated drugs
    drugs = [d for d in payload["drugs"]
             if d["in_negotiated"] and d["modality"] and d["original_approval_date"] and d["total_spend"]]
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    for mod, col in (("small molecule", C_SM), ("biologic", C_BIO)):
        xs, ys, labels = [], [], []
        for d in drugs:
            if d["modality"] != mod:
                continue
            years = [iv["years_after_launch"] for iv in d["indications"] if iv["years_after_launch"] is not None]
            last = max(years) if years else 0
            xs.append(last)
            ys.append(d["total_spend"] / 1e9)
            labels.append(d)
        ax.scatter(xs, ys, s=[40 + (28 if d["in_negotiated"] else 0) for d in labels],
                   color=col, alpha=0.7, edgecolor="white", linewidth=0.6,
                   label=f"{mod}")
        # annotate the biggest spenders
        for x, yv, d in sorted(zip(xs, ys, labels), key=lambda t: -t[1])[:6]:
            ax.annotate(d["brand"], (x, yv), fontsize=6.2, color=INK,
                        xytext=(3, 3), textcoords="offset points")
    ax.axvline(9, color=C_SM, ls=":", lw=1, alpha=0.6)
    ax.axvline(13, color=C_BIO, ls=":", lw=1, alpha=0.6)
    ax.set_yscale("log")
    ax.set_xlabel("Years from approval to most recent new indication")
    ax.set_ylabel("Latest-year Medicare spend ($B, log scale)")
    ax.set_title("Spend vs. how long a drug keeps earning new indications (40 negotiated drugs)",
                 fontsize=10.5, color=INK, loc="left", pad=8)
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    ax.grid(axis="y", color="#eeeeee", lw=0.7)
    fig.tight_layout()
    return _save(fig, fname)


def histogram(payload: Dict[str, Any], fname: str = "fig3_distribution") -> str:
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    bins = list(range(0, 29, 1))
    for mod, col in (("small molecule", C_SM), ("biologic", C_BIO)):
        vals = []
        for d in payload["drugs"]:
            if d["modality"] != mod or not d["in_negotiated"]:  # 40 negotiated only
                continue
            vals += [iv["years_after_launch"] for iv in d["indications"] if iv["years_after_launch"] is not None]
        ax.hist(vals, bins=bins, color=col, alpha=0.55, label=f"{mod} (n={len(vals)})")
    ax.axvline(9, color=C_SM, ls=":", lw=1.2)
    ax.axvline(13, color=C_BIO, ls=":", lw=1.2)
    ax.set_xlabel("Years after approval that a new indication was granted")
    ax.set_ylabel("# new indications")
    ax.set_title("When new indications are approved, by modality (40 negotiated drugs)", fontsize=10.5, loc="left", color=INK)
    ax.legend(fontsize=7.5, frameon=False)
    fig.tight_layout()
    return _save(fig, fname)


def _save(fig, fname: str) -> str:
    png = FIG_DIR / f"{fname}.png"
    svg = FIG_DIR / f"{fname}.svg"
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)
    return str(png)


def run() -> List[str]:
    payload = _load()
    paths = [timeline(payload), scatter(payload), histogram(payload)]
    print("Wrote figures:")
    for p in paths:
        print("  ", p)
    return paths


if __name__ == "__main__":
    run()
