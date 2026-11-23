#!/usr/bin/env python3
"""
WB 工具：完整训练会话对比（对应论文 Fig.10 的 MNIST 版）。

三条准确率曲线：明文 FedAvg / Flamingo / BBGLR（三者训练管线完全相同，
只替换聚合方式；两个加密实现都已修掉"传引用"的 bug）。

右侧面板把两种时间分开画：
  - 仿真时间（等待 + 计算，ABIDES 时间轴）—— 论文 Fig.10a 用的口径
  - 墙钟时间（真实 CPU 耗时）
两者结论相反，必须分开看。
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

C_FLAM = "#C25B4A"
C_BBGLR = "#3F6C8F"
C_BASE = "#8A9199"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"
RE_SCORE = re.compile(r"MLP SCORE:\s*([\d.]+)")

SIM = {"Flamingo": 162.4, "BBGLR": 654.4}      # 秒，来自日志首末事件时刻
WALL = {"Flamingo": 380.0, "BBGLR": 158.0}     # 秒，/usr/bin/time


def from_csv(p):
    if not os.path.isfile(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    return np.array([float(r["accuracy_pct"]) for r in rows])


def from_log(p):
    if not os.path.isfile(p):
        return None
    out = []
    for line in open(p, "r", encoding="utf-8", errors="replace"):
        m = RE_SCORE.search(line)
        if m:
            out.append(float(m.group(1)) * 100)
    return np.array(out) if out else None


def main():
    base = from_csv(os.path.join(REPO, "results", "baseline_exact_seed42.csv"))
    fl = from_log(os.path.join(REPO, "runs", "fixed", "console.log"))
    bb = from_log(os.path.join(REPO, "runs", "baseline_bbglr_mnist", "console.log"))

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4),
                             gridspec_kw={"width_ratios": [1.45, 1]})

    # ---- (a) 准确率 ----
    ax = axes[0]
    for arr, color, label, mk in (
            (base, C_BASE, "Plaintext FedAvg", "s"),
            (fl, C_FLAM, "Flamingo", "o"),
            (bb, C_BBGLR, "BBGLR", "D")):
        if arr is None or len(arr) == 0:
            continue
        T = np.arange(1, len(arr) + 1)
        ax.plot(T, arr, color=color, linewidth=2.0, marker=mk, markersize=4.2,
                label=label, zorder=3)
        print(f"  {label:18s} rounds={len(arr)} final={arr[-1]:.2f}%")
    ax.set_xlabel("Aggregation round  t")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("Accuracy — same training, different aggregation", loc="left", pad=12)
    ax.set_ylim(30, 100)
    ax.legend(loc="lower right")

    # ---- (b) 两种时间口径 ----
    ax = axes[1]
    names = ["Flamingo", "BBGLR"]
    x = np.arange(len(names))
    w = 0.34
    sim_v = [SIM[n] for n in names]
    wall_v = [WALL[n] for n in names]
    b1 = ax.bar(x - w / 2, sim_v, width=w, color="#B9C7D2", zorder=3,
                label="simulated (ABIDES clock)")
    b2 = ax.bar(x + w / 2, wall_v, width=w, color="#D9B7AC", zorder=3,
                label="wall clock (CPU)")
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}s",
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=9, color=C_INK)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Time for 10 rounds (s)")
    ax.set_ylim(0, max(sim_v + wall_v) * 1.2)
    ax.set_title("Time — two different clocks", loc="left", pad=12)
    ax.legend(loc="upper left", fontsize=9)

    for ax in axes:
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", color=C_GRID, linewidth=0.9)
        ax.set_axisbelow(True)

    fig.tight_layout(pad=2.2)
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "14_full_session.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    print(f"  sim  : Flamingo {SIM['Flamingo']:.0f}s vs BBGLR {SIM['BBGLR']:.0f}s "
          f"({SIM['BBGLR']/SIM['Flamingo']:.2f}x)")
    print(f"  wall : Flamingo {WALL['Flamingo']:.0f}s vs BBGLR {WALL['BBGLR']:.0f}s "
          f"({WALL['Flamingo']/WALL['BBGLR']:.2f}x slower)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
