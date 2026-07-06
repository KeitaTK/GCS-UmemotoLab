#!/usr/bin/env python3
"""サンプル5（RTK Fixed）のグラフ生成スクリプト"""

import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

CSV_PATH = Path(__file__).resolve().parent.parent / "logs" / "compare_sample5.csv"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "sample5_rtk_fixed.png"


def load_data(csv_path: Path) -> dict:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    data = {
        "fix_u": [],
        "sats_u": [],
        "lat_u": [],
        "lon_u": [],
        "alt_u": [],
        "fix_p": [],
        "sats_p": [],
        "lat_p": [],
        "lon_p": [],
        "alt_p": [],
    }
    for row in rows:
        for key in data:
            val = row.get(key, "").strip()
            if val == "":
                data[key].append(np.nan)
            else:
                data[key].append(float(val))
    return data


def main():
    data = load_data(CSV_PATH)
    samples = np.arange(1, len(data["fix_p"]) + 1)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle(
        "Sample 5: RTK Fixed (fix=6) — Long-duration Continuous Measurement\n"
        "2026-07-01 | 27 satellites | 36.075726°N 136.213710°E | Alt 2.9m",
        fontsize=14,
        fontweight="bold",
    )

    # ── Subplot 1: Fix Type ──────────────────────────────
    ax = axes[0]
    ax.plot(samples, data["fix_p"], "o-", color="#2ecc71", linewidth=2, markersize=8,
            markerfacecolor="white", markeredgewidth=2, label="Pixhawk (fix=6 RTK Fixed)")
    ax.axhline(6, color="#27ae60", linestyle="--", alpha=0.4, linewidth=1)
    ax.set_ylabel("Fix Type", fontsize=12)
    ax.set_ylim(0, 7)
    ax.set_yticks([0, 1, 2, 3, 4, 5, 6])
    ax.set_yticklabels(["0", "1", "2: 2D", "3: 3D", "4: DGPS", "5: RTK Float", "6: RTK Fixed"])
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.annotate(
        "[OK] RTK Fixed (fix=6) — All 20 samples consistent",
        xy=(1, 6), xytext=(3, 6.4),
        fontsize=11, color="#27ae60", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#27ae60"),
    )

    # ── Subplot 2: Satellite Count ────────────────────────
    ax = axes[1]
    ax.plot(samples, data["sats_p"], "s-", color="#3498db", linewidth=2, markersize=8,
            markerfacecolor="white", markeredgewidth=2, label="Pixhawk satellites")
    ax.set_ylabel("Satellite Count", fontsize=12)
    ax.set_ylim(0, 35)
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)

    # ── Subplot 3: Latitude / Longitude / Altitude ────────
    ax = axes[2]
    # Plot lat/lon on twin axes
    color_lat = "#e74c3c"
    color_lon = "#8e44ad"
    color_alt = "#e67e22"

    ax.plot(samples, data["lat_p"], "o-", color=color_lat, linewidth=2, markersize=8,
            markerfacecolor="white", markeredgewidth=2, label=f"Latitude")
    ax.set_ylabel("Latitude (°)", fontsize=12, color=color_lat)
    ax.tick_params(axis="y", labelcolor=color_lat)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.6f"))

    ax2 = ax.twinx()
    ax2.plot(samples, data["lon_p"], "s-", color=color_lon, linewidth=2, markersize=8,
             markerfacecolor="white", markeredgewidth=2, label="Longitude")
    ax2.set_ylabel("Longitude (°)", fontsize=12, color=color_lon)
    ax2.tick_params(axis="y", labelcolor=color_lon)
    ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.6f"))

    ax3 = ax.twinx()
    ax3.spines.right.set_position(("axes", 1.12))
    ax3.plot(samples, data["alt_p"], "D-", color=color_alt, linewidth=2, markersize=8,
             markerfacecolor="white", markeredgewidth=2, label="Altitude (m)")
    ax3.set_ylabel("Altitude (m)", fontsize=12, color=color_alt)
    ax3.tick_params(axis="y", labelcolor=color_alt)

    # Combine legends from all three y-axes
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines3, labels3 = ax3.get_legend_handles_labels()
    ax.legend(
        lines1 + lines2 + lines3,
        labels1 + labels2 + labels3,
        loc="upper left",
        fontsize=9,
    )

    ax.set_xlabel("Sample Number", fontsize=12)
    ax.set_xticks(samples)
    ax.grid(True, alpha=0.3)

    # ── Footer ────────────────────────────────────────────
    fig.text(
        0.5, 0.01,
        "[!] u-blox data unavailable (TIME mode — NMEA output disabled). "
        "Horizontal position error cannot be calculated.\n"
        "Pixhawk values: lat/lon/alt are completely stable (zero variation) across all 20 samples.",
        ha="center", fontsize=9, color="gray", style="italic",
    )

    plt.tight_layout(rect=[0, 0.04, 0.9, 0.96])
    fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Graph saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()