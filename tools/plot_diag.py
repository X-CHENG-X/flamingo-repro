#!/usr/bin/env python3
"""
WB 工具：诊断图 —— 加密版 vs 明文基线的「准确率」与「权重尺度」双轨迹。

第 1 轮两者几乎完全重合（std 0.0044 vs 0.0045），第 2 轮起分叉：
加密版权重持续变"锐"，明文基线几乎停滞。这说明差异发生在
「全局模型回传 → 客户端续训」这一段，而不是聚合或编码。

用法：python tools/plot_diag.py
"""
import csv
import glob
import os
import pickle
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")

C_FLAM = "#C25B4A"
C_BASE = "#8A9199"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"


def flamingo_traj():
    csv_p = os.path.join(REPO, "results", "flamingo_std_traj.csv")
    if os.path.isfile(csv_p):
        rows = list(csv.DictReader(open(csv_p, encoding="utf-8")))
        return (np.array([int(r["round"]) for r in rows]),
                np.array([float(r["accuracy_pct"]) for r in rows]),
                np.array([float(r["coef_std"]) for r in rows]))
    xs, accs, stds = [], [], []
    for p in sorted(glob.glob(os.path.join(REPO, "runs", "wdump", "w_iter*.pkl"))):
        i = int(os.path.basename(p).split("iter")[1].split(".")[0])
        d = pickle.load(open(p, "rb"))
        flat = np.concatenate([c.ravel() for c in d["coefs"]])
        xs.append(i)
        accs.append(d["score"] * 100)
        stds.append(flat.std())
    return np.array(xs), np.array(accs), np.array(stds)


def baseline_traj():
    p = os.path.join(REPO, "results", "baseline_exact_seed42.csv")
    if not os.path.isfile(p):
        return None, None, None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    xs = [int(r["round"]) for r in rows]
    accs = [float(r["accuracy_pct"]) for r in rows]
    stds = [float(r["coef_std"]) for r in rows]
    return np.array(xs), np.array(accs), np.array(stds)


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "legend.frameon": False, "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fx, fa, fs = flamingo_traj()
    bx, ba, bs = baseline_traj()
    if len(fx) == 0 or bx is None:
        print("missing data")
        return 1

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.3))

    ax = axes[0]
    ax.plot(bx, ba, color=C_BASE, linewidth=2.0, marker="s", markersize=4.5,
            label="Plaintext FedAvg (replica)")
    ax.plot(fx, fa, color=C_FLAM, linewidth=2.2, marker="o", markersize=4.5,
            label="Flamingo (secure)")
    ax.set_xlabel("Round  t")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("Accuracy", loc="left", pad=12)
    ax.set_ylim(min(ba.min(), fa.min()) - 6, 101)
    ax.legend(loc="lower right")

    ax = axes[1]
    ax.plot(bx, bs, color=C_BASE, linewidth=2.0, marker="s", markersize=4.5,
            label="Plaintext FedAvg (replica)")
    ax.plot(fx, fs, color=C_FLAM, linewidth=2.2, marker="o", markersize=4.5,
            label="Flamingo (secure)")
    ax.set_xlabel("Round  t")
    ax.set_ylabel("Weight std (global model)")
    ax.set_title("Model sharpness", loc="left", pad=12)
    ax.annotate("round 1 overlaps:\n0.0044 vs 0.0045",
                xy=(1, fs[0]), xytext=(4.6, 0.062), fontsize=9, color=C_INK,
                arrowprops=dict(arrowstyle="-|>", color=C_INK, linewidth=1.0,
                                shrinkA=0, shrinkB=6))
    ax.legend(loc="upper left")

    for ax in axes:
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(color=C_GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.set_xlim(1, max(fx.max(), bx.max()) + 0.5)

    fig.tight_layout(pad=2.2)
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "8_divergence_diagnosis.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)
    print(f"  flamingo std: {fs[0]:.4f} -> {fs[-1]:.4f}")
    print(f"  baseline std: {bs[0]:.4f} -> {bs[-1]:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
