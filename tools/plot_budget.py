#!/usr/bin/env python3
"""
WB 工具：加速比从 1.97× 到 3.3× 的来源（超时预算的敏感性）。

两种预算口径：
  - 统一 25s：每步都等 25s，两侧掉线率严格可比（δ=1%）
  - 论文预算 ×2.5：Flamingo 25/7.5/7.5，BBGLR 25/25/75/25/7.5/5
    （论文原文是 10/3/3 与 10/10/30/10/3/2，等比放大 2.5 倍）

结论：加速比几乎完全由「预算的不对称程度」决定，而不是实现差异。
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")

C_FLAM = "#C25B4A"
C_BBGLR = "#3F6C8F"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"

# 每轮平均耗时（仿真时间，秒）
UNIFORM = {"Flamingo": 77.56, "BBGLR": 155.13}      # 实测 10 轮
ASYMM = {"Flamingo": 43.03, "BBGLR": 163.20}       # Flamingo 实测 10 轮；BBGLR 实测前 3 轮
SETUP = 62.0                                        # 一次性 DKG
ROUNDS = 10


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    groups = ["Uniform 25s per step\n(delta matched, our default)",
              "Paper's budget × 2.5\n(25/7.5/7.5  vs  25/25/75/25/7.5/5)"]
    fl = [UNIFORM["Flamingo"], ASYMM["Flamingo"]]
    bb = [UNIFORM["BBGLR"], ASYMM["BBGLR"]]

    x = np.arange(2)
    w = 0.32
    b1 = ax.bar(x - w / 2, fl, width=w, color=C_FLAM, label="Flamingo", zorder=3)
    b2 = ax.bar(x + w / 2, bb, width=w, color=C_BBGLR, label="BBGLR", zorder=3)

    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.1f}s",
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=9, color=C_INK)

    # 组上方标加速比
    for i, (f, b) in enumerate(zip(fl, bb)):
        ax.annotate(f"{b / f:.2f}×", (i, max(f, b) * 1.16), ha="center",
                    fontsize=13, color=C_INK)

    ax.axhline(0, color="#B9BFC6", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=9.5)
    ax.set_ylabel("Time per round, simulated (s)")
    ax.set_ylim(0, max(bb) * 1.32)
    ax.set_title("Where the 3× comes from: the timeout budget, not the code",
                 loc="left", pad=12)
    ax.legend(loc="upper left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=C_GRID, linewidth=0.9)
    ax.set_axisbelow(True)

    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "15_budget_sensitivity.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)

    for name, f, b in (("uniform", fl[0], bb[0]), ("paper×2.5", fl[1], bb[1])):
        print(f"  {name:10s} per-round {f:6.2f} vs {b:6.2f}  -> {b / f:.2f}x")
    tf = SETUP + ROUNDS * ASYMM["Flamingo"]
    tb = ROUNDS * ASYMM["BBGLR"]
    print(f"  with setup ({SETUP:.0f}s): total {tf:.0f}s vs {tb:.0f}s -> {tb / tf:.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
