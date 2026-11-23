#!/usr/bin/env python3
"""
WB 工具：DKG 四步的消息到达时间（对应论文 Fig.9）。

数据来源：runs/20261122_dkg_n60/console.log 里的
  "Message arrival time (seconds) for 4 steps:"
  后面紧跟 4 行列表，每行 60 个到达时刻（60 个解密者）。

论文结论：60 个解密者时完整 DKG 不到 10 秒，每个解密者本地计算约 2 秒。
"""
import ast
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")
LOG = os.path.join(REPO, "runs", "20261122_dkg_n60", "console.log")

C_LINE = "#C25B4A"
C_DOT = "#3F6C8F"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"

STEP_LABELS = [
    "1  share + commit",
    "2  accept / complain",
    "3  broadcast share",
    "4  broadcast qual",
]


def load(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    idx = None
    for i, ln in enumerate(lines):
        if "Message arrival time" in ln:
            idx = i
            break
    if idx is None:
        return None
    rows = []
    for ln in lines[idx + 1:]:
        t = ln.strip()
        if not t:
            continue
        if not t.startswith("["):
            break
        rows.append(np.array(ast.literal_eval(t), dtype=float))
        if len(rows) == 4:
            break
    return rows if len(rows) == 4 else None


def main():
    rows = load(LOG)
    if not rows:
        print("no DKG data", file=sys.stderr)
        return 1

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    rng = np.random.default_rng(0)

    for i, arr in enumerate(rows):
        y = i + 1 + rng.uniform(-0.16, 0.16, size=len(arr))
        ax.scatter(arr, y, s=16, color=C_DOT, alpha=0.65, linewidths=0, zorder=3)
        ax.plot([arr.min(), arr.max()], [i + 1, i + 1],
                color=C_LINE, linewidth=1.6, alpha=0.75, zorder=2)
        ax.annotate(f"{arr.max():.2f}s", xy=(arr.max(), i + 1),
                    xytext=(6, 0), textcoords="offset points",
                    fontsize=9, color=C_INK, va="center")

    total = max(a.max() for a in rows)
    ax.axvline(total, color=C_INK, linewidth=1.0, linestyle=(0, (5, 4)), zorder=1)
    ax.annotate(f"all done {total:.2f}s", xy=(total, 4.55),
                xytext=(-6, 0), textcoords="offset points",
                fontsize=9.5, color=C_INK, ha="right", va="center")

    ax.set_yticks(range(1, 5))
    ax.set_yticklabels(STEP_LABELS)
    ax.set_ylim(0.4, 4.85)
    ax.set_xlim(-0.3, total * 1.06)
    ax.set_xlabel("Message arrival time at the server (s)")
    ax.set_title("DKG among 60 decryptors — 4 steps", loc="left", pad=12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color=C_GRID, linewidth=0.9)
    ax.set_axisbelow(True)

    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "10_dkg_steps.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    for i, arr in enumerate(rows):
        print(f"  step{i+1}: {arr.min():.2f} -> {arr.max():.2f}s  ({len(arr)} decryptors)")
    print(f"  total {total:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
