#!/usr/bin/env python3
"""
WB 工具：求和精度 τ 曲线（对应论文 Fig.8b/8d）。

τ 定义（论文 §2.4）：最终的和里包含了「被选中客户端」的多大比例。
本实现里 = 本轮实际参与聚合的客户端数 / 本轮选中的客户端数。

两个面板（各协议一栏），每栏三条线对应三档等待超时。
BBGLR 在 w=5s 下会崩（mi_bytes is None），单独标注。
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")

C_INK = "#3F4A56"
C_GRID = "#E6E8EB"
RE_VEC = re.compile(r"receives last vectors \((\d+)/(\d+) msgs\)")

# 每个协议：[(等待档, 目录, 颜色)]
FL = [("5s", "runs/w5_flamingo", "#C25B4A"),
      ("10s", "runs/w10_flamingo", "#D98A6A"),
      ("25s", "runs/20261122_T10_cal25_flamingo", "#EBC3B4")]
BB = [("25s", "runs/20261122_T10_cal25_bbglr", "#3F6C8F")]


def flamingo_tau(d):
    p = os.path.join(REPO, d, "sum.jsonl")
    if not os.path.isfile(p):
        return None
    out = []
    for line in open(p, "r", encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            out.append(100.0 * r["n_online"] / r["n_total"])
    return np.array(out) if out else None


def bbglr_tau(d):
    p = os.path.join(REPO, d, "console.log")
    if not os.path.isfile(p):
        return None
    out = []
    for line in open(p, "r", encoding="utf-8", errors="replace"):
        m = RE_VEC.search(line)
        if m:
            out.append(100.0 * int(m.group(1)) / int(m.group(2)))
    return np.array(out) if out else None


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.4), sharey=True)

    for ax, series, title, loader in (
            (axes[0], FL, "Flamingo", flamingo_tau),
            (axes[1], BB, "BBGLR", bbglr_tau)):
        drew = False
        for wait, d, color in series:
            arr = loader(d)
            if arr is None or len(arr) == 0:
                print(f"  {title} w={wait}: no data")
                continue
            T = np.arange(1, len(arr) + 1)
            ax.plot(T, arr, color=color, linewidth=2.0, marker="o", markersize=4.2,
                    label=f"w = {wait}", zorder=3)
            print(f"  {title:9s} w={wait:4s} rounds={len(arr)} "
                  f"τ avg={arr.mean():.2f}%  final={arr[-1]:.2f}%")
            drew = True
        if not drew:
            ax.annotate("crashed at round 1\n(mi_bytes is None)",
                        xy=(0.5, 0.5), xycoords="axes fraction",
                        ha="center", va="center", fontsize=10, color="#B03A2E")
        if title == "BBGLR":
            ax.annotate("w = 5s / 10s: crashed in round 1\n"
                        "(missing mask shares → mi_bytes is None)",
                        xy=(0.03, 0.06), xycoords="axes fraction",
                        fontsize=9, color="#B03A2E", va="bottom")
        ax.set_title(title, loc="left", pad=12)
        ax.set_xlabel("Aggregation round  t")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(color=C_GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.legend(loc="lower right", title="waiting time", title_fontsize=9, fontsize=9)

    axes[0].set_ylabel(r"Sum accuracy  $\tau$  (%)")
    axes[0].set_ylim(88, 100.6)
    fig.suptitle("Fraction of selected clients included in the sum  (n=1024)",
                 x=0.012, ha="left", fontsize=12.5, y=1.02)

    fig.tight_layout(pad=2.0)
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "12_tau.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
