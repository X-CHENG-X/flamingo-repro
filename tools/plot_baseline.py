#!/usr/bin/env python3
"""
WB 工具：明文 FedAvg 基线 vs 安全聚合(Flamingo) 的准确率对比图。

输入：
  results/baseline_accuracy_seed*.csv   （tools/fedavg_baseline.py 产出，多种子）
  runs/T10_n128_mnist/console.log       （fedlearn 的 Flamingo 运行，含每轮 MLP SCORE）

产出：figures/7_baseline_vs_secure.png
"""
import csv
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")

C_BASE = "#8A9199"      # 基线：中灰
C_FLAM = "#C25B4A"      # Flamingo：赤陶
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"

RE_SCORE = re.compile(r"MLP SCORE:\s*([\d.]+)")


def load_baselines():
    curves = []
    for p in sorted(glob.glob(os.path.join(REPO, "results", "baseline_accuracy_seed*.csv"))):
        with open(p, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            curves.append([float(r["accuracy_pct"]) for r in rows])
    return np.array(curves) if curves else None


def load_flamingo(path):
    if not os.path.isfile(path):
        return None
    vals = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_SCORE.search(line)
            if m:
                vals.append(float(m.group(1)) * 100.0)
    return np.array(vals) if vals else None


def main():
    base = load_baselines()
    fl = load_flamingo(os.path.join(REPO, "runs", "T10_n128_mnist", "console.log"))

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(7.6, 4.6))

    if base is not None:
        n = base.shape[1]
        T = np.arange(1, n + 1)
        mean = base.mean(axis=0)
        lo, hi = base.min(axis=0), base.max(axis=0)
        ax.fill_between(T, lo, hi, color=C_BASE, alpha=0.18, zorder=2, linewidth=0)
        ax.plot(T, mean, color=C_BASE, linewidth=2.0, marker="s", markersize=4,
                zorder=3, label=f"Plaintext FedAvg  ({base.shape[0]} seeds, mean±range)")
        ax.annotate(f"{mean[-1]:.1f}%", xy=(T[-1], mean[-1]), textcoords="offset points",
                    xytext=(9, -12), fontsize=9.5, color="#5C636B", va="center")

    if fl is not None:
        T = np.arange(1, len(fl) + 1)
        ax.plot(T, fl, color=C_FLAM, linewidth=2.2, marker="o", markersize=5,
                zorder=4, label="Flamingo + secure aggregation")
        ax.annotate(f"{fl[-1]:.1f}%", xy=(T[-1], fl[-1]), textcoords="offset points",
                    xytext=(9, 2), fontsize=9.5, color=C_FLAM, va="center")

    ax.set_xlabel("Aggregation round  t")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("Does secure aggregation change accuracy?   (MNIST, 128 clients)",
                 loc="left", pad=12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color=C_GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.set_xlim(1, max(base.shape[1] if base is not None else 1,
                       len(fl) if fl is not None else 1) + 1.0)
    lo_all = min(np.min(base) if base is not None else 100,
                 np.min(fl) if fl is not None else 100)
    hi_all = max(np.max(base) if base is not None else 0,
                 np.max(fl) if fl is not None else 0)
    ax.set_ylim(max(0, lo_all - 8), min(100, hi_all + 5))
    ax.legend(loc="lower right")

    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "7_baseline_vs_secure.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    if base is not None:
        print(f"baseline: {base.shape[0]} seeds, final mean {base[:, -1].mean():.2f}% "
              f"(range {base[:, -1].min():.2f}-{base[:, -1].max():.2f})")
    if fl is not None:
        print(f"flamingo: {len(fl)} rounds, final {fl[-1]:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
