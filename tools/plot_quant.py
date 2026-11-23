#!/usr/bin/env python3
"""
WB 工具：量化精度对训练准确率的影响。

编码是 (w + c) · 2^m 截断成 uint32，解码再除回来，所以量化步长 = 2^-m。
m 越小越省位宽，但误差越大；m 越大越精确，但累加会撞 uint32 上限。

数据：runs/quant_m<M>/console.log 里的 "MLP SCORE" 序列。
"""
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

C_LINE = "#C25B4A"
C_INK = "#3F4A56"
C_MUTED = "#8A9199"
C_GRID = "#E6E8EB"
RE_SCORE = re.compile(r"MLP SCORE:\s*([\d.]+)")


def load_all():
    out = {}
    for d in glob.glob(os.path.join(REPO, "runs", "quant_m*")):
        m = int(os.path.basename(d).replace("quant_m", ""))
        p = os.path.join(d, "console.log")
        if not os.path.isfile(p):
            continue
        vals = []
        for line in open(p, "r", encoding="utf-8", errors="replace"):
            mt = RE_SCORE.search(line)
            if mt:
                vals.append(float(mt.group(1)) * 100)
        if vals:
            out[m] = vals
    return dict(sorted(out.items()))


def main():
    data = load_all()
    if not data:
        print("no data", file=sys.stderr)
        return 1

    ms = list(data.keys())
    first = [data[m][0] for m in ms]
    last = [data[m][-1] for m in ms]

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    x = np.array(ms)

    ax.plot(x, last, color=C_LINE, linewidth=2.2, marker="o", markersize=6,
            label="round 5 (final)", zorder=4)
    ax.plot(x, first, color=C_MUTED, linewidth=1.6, marker="s", markersize=4.5,
            linestyle="--", label="round 1", zorder=3)

    for xi, yi in zip(x, last):
        dx, dy, ha = (0, 9, "center") if yi > 40 else (12, -4, "left")
        ax.annotate(f"{yi:.1f}%", (xi, yi), textcoords="offset points",
                    xytext=(dx, dy), ha=ha, fontsize=8.8, color=C_INK)

    # 量化步长标注
    for xi in x:
        ax.annotate(f"2$^{{{-xi}}}$", (xi, 1), xycoords=("data", "axes fraction"),
                    textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=8.2, color=C_MUTED)

    ax.axvspan(18.6, max(x) + 0.5, color="#E8B4AC", alpha=0.35, zorder=1)
    ax.annotate("uint32\noverflow\n(m $\\geq$ 19)", xy=(18.75, 55), fontsize=8.5,
                color="#8C3A2E", va="center")

    ax.set_xlabel("encoding precision  m   (quantization step = 2$^{-m}$)")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("How coarse can the encoding get before training breaks?",
                 loc="left", pad=12)
    ax.set_xticks(x)
    ax.set_xlim(min(x) - 0.6, max(x) + 1.2)
    ax.set_ylim(0, 100)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color=C_GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right")

    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "13_quantization.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    for m in ms:
        print(f"  m={m:2d}  step=2^-{m:<2d}  round1={data[m][0]:6.2f}%  "
              f"final={data[m][-1]:6.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
