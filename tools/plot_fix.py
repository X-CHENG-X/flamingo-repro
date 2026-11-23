#!/usr/bin/env python3
"""
WB 工具：三条准确率曲线对比 —— 明文基线 / 加密(有 bug) / 加密(修复后)。

数据来源：
  results/baseline_exact_seed42.csv   明文 FedAvg（逐位复刻上游训练路径）
  results/flamingo_std_traj.csv       加密版（修复前，模型回传传引用）
  runs/fixed/console.log              加密版（修复后，回传副本）
"""
import csv
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")

C_BASE = "#8A9199"
C_FIX = "#3F6C8F"
C_BUG = "#C25B4A"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"

RE_SCORE = re.compile(r"MLP SCORE:\s*([\d.]+)")


def from_csv(p, col="accuracy_pct"):
    if not os.path.isfile(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    return np.array([float(r[col]) for r in rows])


def from_log(p):
    if not os.path.isfile(p):
        return None
    vals = []
    for line in open(p, encoding="utf-8", errors="replace"):
        m = RE_SCORE.search(line)
        if m:
            vals.append(float(m.group(1)) * 100)
    return np.array(vals) if vals else None


def main():
    base = from_csv(os.path.join(REPO, "results", "baseline_exact_seed42.csv"))
    bug = from_csv(os.path.join(REPO, "results", "flamingo_std_traj.csv"))
    fix = from_log(os.path.join(REPO, "runs", "fixed", "console.log"))

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(7.8, 4.6))

    offsets = {"bug": (9, 0), "base": (10, 8), "fix": (10, -9)}
    for key, arr, color, label, style in (
            ("bug", bug, C_BUG, "Secure agg. — before fix (weights sent by reference)", "o"),
            ("base", base, C_BASE, "Plaintext FedAvg (same pipeline)", "s"),
            ("fix", fix, C_FIX, "Secure agg. — after fix (weights sent as copies)", "D")):
        if arr is None or len(arr) == 0:
            continue
        T = np.arange(1, len(arr) + 1)
        ax.plot(T, arr, color=color, linewidth=2.0, marker=style, markersize=4.2,
                label=label, zorder=3)
        ax.annotate(f"{arr[-1]:.2f}%", xy=(T[-1], arr[-1]), textcoords="offset points",
                    xytext=offsets[key], fontsize=9.5, color=color, va="center")

    ax.set_xlabel("Aggregation round  t")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("Same pipeline, one line of code   (MNIST, 128 clients, 5 epochs)",
                 loc="left", pad=12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color=C_GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.set_xlim(1, 10.9)
    ax.set_ylim(30, 101)
    ax.legend(loc="lower right", fontsize=9)

    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "9_fix_verification.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    for name, arr in (("buggy", bug), ("base", base), ("fixed", fix)):
        if arr is not None and len(arr):
            print(f"  {name:6s} {len(arr)} rounds  final {arr[-1]:.2f}%")


if __name__ == "__main__":
    sys.exit(main())
