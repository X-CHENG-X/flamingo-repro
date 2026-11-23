#!/usr/bin/env python3
"""
WB 工具：复现实验的全部图表（matplotlib，300 dpi）。

产出 figures/：
  1_calibration.png     超时 -> 掉线率（标定曲线，论文 §8.1 的做法）
  2_single_round.png    单轮端到端时长（多配置对比）
  3_amortized.png       多轮摊销（一次性 setup vs 每轮 setup）
  4_multi_round.png     实测累计时长 vs 轮数 T

样式约定：
  - 白底、无上/右边框、仅浅网格
  - 标注用深灰 #3F4A56，箭头不压数据线
  - 文字不贴边框（bbox_inches='tight' + pad_inches）
  - 全部 300 dpi
"""
import argparse
import csv
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(REPO, "runs")
FIG = os.path.join(REPO, "figures")
RESULTS = os.path.join(REPO, "results")

# ---- 视觉常量 ----
C_FLAM = "#C25B4A"      # Flamingo：赤陶
C_BBGLR = "#3F6C8F"     # BBGLR：钢蓝
C_INK = "#3F4A56"       # 标注 / 箭头
C_MUTED = "#8A9199"     # 次要元素
C_GRID = "#E6E8EB"
DPI = 300

DISPLAY = {
    "flamingo_cal25": "Flamingo\ncalibrated 25s",
    "bbglr_cal25": "BBGLR\ncalibrated 25s",
    "flamingo_adaptive99": "Flamingo\nadaptive 99%",
    "bbglr_adaptive99": "BBGLR\nadaptive 99%",
    "flamingo_fixed": "Flamingo\nfixed 10s",
    "bbglr_fixed": "BBGLR\nfixed",
}

RE_TS = re.compile(r"^\s+\+\s+([\d.]+)s\s+server ")
RE_VEC = re.compile(r"receives last vectors \((\d+)/(\d+) msgs\)")
RE_ITER = re.compile(r"^--- Iteration (\d+) \(start:")        # 时间线块
RE_ITER_SUM = re.compile(r"^--- Iteration (\d+) ---\s*$")     # 统计块
RE_RECON = re.compile(r"^\s{4}reconstruction\s+([\d.]+)s")
RE_DECTGT = re.compile(r"^\s+dec_targets:\s*(\d+)")
RE_ONLINE = re.compile(r"^\s+online_clients:\s*(\d+)")
RE_SCORE = re.compile(r"MLP SCORE:\s*([\d.]+)")


def apply_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10.5,
        "axes.titlesize": 12.5,
        "axes.titleweight": "medium",
        "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6",
        "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK,
        "xtick.color": "#4A4F55",
        "ytick.color": "#4A4F55",
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "grid.color": C_GRID,
        "grid.linewidth": 0.9,
        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })


def tidy(ax, grid_axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#B9BFC6")
    ax.spines["bottom"].set_color("#B9BFC6")
    ax.grid(axis=grid_axis, color=C_GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, name)
    fig.savefig(p, dpi=DPI, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", p)


# ---------- 1. 标定曲线 ----------
def fig_calibration():
    path = os.path.join(RESULTS, "calibration.csv")
    if not os.path.isfile(path):
        print("skip calibration: no csv")
        return
    xs, ys = [], []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            xs.append(float(row["timeout_s"]))
            ys.append(float(row["dropout_pct"]))

    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    ax.plot(xs, ys, color=C_FLAM, linewidth=2.0, marker="o", markersize=5,
            markerfacecolor="white", markeredgewidth=1.6, zorder=4)

    ax.axhline(1.0, color=C_MUTED, linewidth=1.0, linestyle=(0, (5, 4)), zorder=2)
    ax.annotate("target δ = 1%", xy=(0.6, 1.0), xytext=(0.9, 3.3),
                ha="left", fontsize=9, color=C_INK)

    i25 = min(range(len(xs)), key=lambda i: abs(xs[i] - 25))
    ax.plot([xs[i25]], [ys[i25]], marker="*", markersize=13, color=C_INK, zorder=6)
    ax.annotate(f"{xs[i25]:.0f}s → {ys[i25]:.2f}%",
                xy=(xs[i25], ys[i25]), xytext=(xs[i25] + 1.2, ys[i25] + 5.4),
                fontsize=9.5, color=C_INK, ha="left",
                arrowprops=dict(arrowstyle="-|>", color=C_INK, linewidth=1.0,
                                shrinkA=0, shrinkB=7))

    for t, lab, dx, dy in ((2, "upstream 1st round\n(hard-coded 2s)", 3.0, 4.0),
                           (10, "upstream default\n10s", 2.5, 3.2)):
        j = min(range(len(xs)), key=lambda i: abs(xs[i] - t))
        ax.plot([xs[j]], [ys[j]], marker="s", markersize=6,
                markerfacecolor="white", markeredgecolor=C_MUTED, markeredgewidth=1.5, zorder=5)
        ax.annotate(f"{lab}  {ys[j]:.1f}%", xy=(xs[j], ys[j]),
                    xytext=(xs[j] + dx, ys[j] + dy), fontsize=8.5, color=C_MUTED,
                    arrowprops=dict(arrowstyle="-", color=C_MUTED, linewidth=0.8,
                                    shrinkA=0, shrinkB=5))

    ax.set_xlabel("Report step timeout (s)")
    ax.set_ylabel("Client dropout rate (%)")
    ax.set_title("Timeout calibration   (n=1024, empirical arrivals)", loc="left", pad=12)
    ax.set_xlim(0, max(xs) + 2)
    ax.set_ylim(0, max(ys) * 1.18)
    tidy(ax)
    save(fig, "1_calibration.png")


# ---------- 2. 单轮对比 ----------
def parse_run(rundir):
    d = os.path.join(RUNS, rundir)
    log = os.path.join(d, "console.log")
    if not os.path.isfile(log):
        return None
    total = None
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_TS.match(line)
            if m:
                total = float(m.group(1))
    online = n_total = None
    dump = os.path.join(d, "sum.jsonl")
    if os.path.isfile(dump):
        with open(dump, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        if lines:
            online = json.loads(lines[0]).get("n_online")
    if online is None:
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = RE_VEC.search(line)
                if m:
                    online, n_total = int(m.group(1)), int(m.group(2))
    meta = {}
    mp = os.path.join(d, "meta.json")
    if os.path.isfile(mp):
        with open(mp, "r", encoding="utf-8") as f:
            meta = json.load(f)
    return {"total": total, "online": online, "n_total": n_total or meta.get("n"), **meta}


def fig_single_round(specs):
    data = {}
    for label, rundir in specs:
        r = parse_run(rundir)
        if r and r["total"]:
            data[label] = r
            print(f"  {label:22s} {r['total']:7.2f}s  online={r.get('online')}")
    if not data:
        print("skip single-round: no runs")
        return data

    labels = list(data)
    vals = [data[k]["total"] for k in labels]
    colors = [C_FLAM if data[k]["protocol"] == "flamingo" else C_BBGLR for k in labels]

    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    x = np.arange(len(labels))
    bars = ax.bar(x, vals, color=colors, width=0.56, zorder=3)

    ax.set_ylabel("Time per round (s)")
    ax.set_title("Single-round end-to-end time   (n=1024, 16K-dim, 1 VM)", loc="left", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels([DISPLAY.get(k, k) for k in labels])
    tidy(ax)
    ax.set_ylim(0, max(vals) * 1.24)

    for b, k, v in zip(bars, labels, vals):
        on, nt = data[k].get("online"), data[k].get("n_total") or 1024
        ann = f"{v:.1f}s"
        if on:
            ann += f"\n{100.0 * on / nt:.1f}% online"
        ax.annotate(ann, (b.get_x() + b.get_width() / 2, v), textcoords="offset points",
                    xytext=(0, 6), ha="center", va="bottom", fontsize=9, color=C_INK)
    save(fig, "2_single_round.png")
    return data


# ---------- 3. 摊销 ----------
def fig_amortized(fl_total, bb_total, setup):
    T = np.arange(1, 21)
    f = setup + T * fl_total
    b = T * bb_total

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    ax.plot(T, b, color=C_BBGLR, linewidth=2.0, marker="s", markersize=3.6,
            label=f"BBGLR — setup every round  ({bb_total:.1f}s/round)")
    ax.plot(T, f, color=C_FLAM, linewidth=2.0, marker="o", markersize=3.6,
            label=f"Flamingo — one-time setup {setup:.0f}s + {fl_total:.1f}s/round")

    cross = setup / (bb_total - fl_total)
    if 1 < cross < 20:
        yc = cross * bb_total
        ax.plot([cross], [yc], marker="*", markersize=12, color=C_INK, zorder=6)
        ax.annotate(f"break-even\n≈ {cross:.1f} rounds", xy=(cross, yc),
                    xytext=(cross + 2.4, yc * 0.38), fontsize=9.5, color=C_INK,
                    arrowprops=dict(arrowstyle="-|>", color=C_INK, linewidth=1.0,
                                    shrinkA=0, shrinkB=7))

    ax.set_xlabel("Aggregation rounds  T")
    ax.set_ylabel("Cumulative time (s)")
    ax.set_title("Amortization of the one-time setup", loc="left", pad=12)
    ax.set_xlim(1, 20)
    ax.set_ylim(0, max(b.max(), f.max()) * 1.12)
    tidy(ax, "both")
    ax.legend(loc="upper left", handlelength=2.2, labelspacing=0.7)
    save(fig, "3_amortized.png")


# ---------- 4. 多轮实测 ----------
def parse_iter_totals(rundir):
    """每轮时长 = 该轮时间线块内的最大时间戳。

    注意：日志里 "+ X.XXXs" 是**相对本轮起点**的偏移（不是全局仿真时刻），
    所以不能做相邻块差分。
    """
    log = os.path.join(RUNS, rundir, "console.log")
    if not os.path.isfile(log):
        return []
    out, cur = [], None
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if RE_ITER.match(line):
                if cur is not None:
                    out.append(cur)
                cur = 0.0
                continue
            m = RE_TS.match(line)
            if m and cur is not None:
                cur = max(cur, float(m.group(1)))
    if cur is not None:
        out.append(cur)
    return out


def fig_multi_round(fl_dir, bb_dir):
    fl = parse_iter_totals(fl_dir)
    bb = parse_iter_totals(bb_dir)
    if not fl or not bb:
        print("skip multi-round: missing runs")
        return
    n = min(len(fl), len(bb))
    T = np.arange(1, n + 1)

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.3),
                            gridspec_kw={"width_ratios": [1.15, 1]})

    ax = axes[0]
    w = 0.38
    ax.bar(T - w / 2, fl[:n], width=w, color=C_FLAM, zorder=3, label="Flamingo")
    ax.bar(T + w / 2, bb[:n], width=w, color=C_BBGLR, zorder=3, label="BBGLR")
    ax.set_xlabel("Round  t")
    ax.set_ylabel("Time (s)")
    ax.set_title(f"Per-round time   (mean {np.mean(fl[:n]):.1f}s vs {np.mean(bb[:n]):.1f}s)",
                 loc="left", pad=12)
    ax.set_xticks(T)
    tidy(ax)
    ax.set_ylim(0, max(max(fl[:n]), max(bb[:n])) * 1.22)
    ax.legend(loc="upper right")

    ax = axes[1]
    cf = np.cumsum(fl[:n])
    cb = np.cumsum(bb[:n])
    ax.plot(T, cb, color=C_BBGLR, linewidth=2.0, marker="s", markersize=4, label="BBGLR")
    ax.plot(T, cf, color=C_FLAM, linewidth=2.0, marker="o", markersize=4, label="Flamingo")
    ax.set_xlabel("Aggregation rounds  T")
    ax.set_ylabel("Cumulative time (s)")
    ax.set_title(f"Cumulative — {cb[-1] / cf[-1]:.2f}× speedup at T={n}", loc="left", pad=12)
    ax.set_xlim(1, n)
    ax.set_ylim(0, cb[-1] * 1.14)
    tidy(ax, "both")
    ax.legend(loc="upper left")

    fig.tight_layout(pad=2.2)
    save(fig, "4_multi_round.png")

    print("\n  round |  Flamingo  |   BBGLR")
    for i in range(n):
        print(f"  {i + 1:5d} | {fl[i]:9.2f}s | {bb[i]:8.2f}s")
    print(f"  total | {cf[-1]:9.2f}s | {cb[-1]:8.2f}s   speedup {cb[-1] / cf[-1]:.2f}×")


# ---------- 5. recon 成本 vs 需重构掩码数 ----------
def parse_recon_points(rundir):
    """每个 iteration 的 (dec_targets, recon_seconds, online_clients)。"""
    log = os.path.join(RUNS, rundir, "console.log")
    if not os.path.isfile(log):
        return []
    pts, cur = [], None
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if RE_ITER_SUM.match(line):
                if cur and "recon" in cur and "dec_targets" in cur:
                    pts.append(cur)
                cur = {}
                continue
            if cur is None:
                continue
            m = RE_DECTGT.match(line)
            if m:
                cur["dec_targets"] = int(m.group(1))
                continue
            m = RE_ONLINE.match(line)
            if m:
                cur["online"] = int(m.group(1))
                continue
            m = RE_RECON.match(line)
            if m:
                cur["recon"] = float(m.group(1))
    if cur and "recon" in cur and "dec_targets" in cur:
        pts.append(cur)
    return pts


def fig_recon_scaling(dirs):
    pts = []
    for d in dirs:
        for p in parse_recon_points(d):
            p["run"] = d
            pts.append(p)
    if len(pts) < 3:
        print("skip recon-scaling: not enough points")
        return

    x = np.array([p["dec_targets"] for p in pts], dtype=float)
    y = np.array([p["recon"] for p in pts], dtype=float)

    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    yhat = A @ np.array([slope, intercept])
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    ax.scatter(x, y, s=52, color=C_FLAM, edgecolor="white", linewidth=1.1, zorder=4,
               label="measured rounds")

    xs = np.linspace(0, x.max() * 1.04, 50)
    ax.plot(xs, slope * xs + intercept, color=C_INK, linewidth=1.4,
            linestyle=(0, (6, 3)), zorder=3,
            label=f"fit: {slope * 1000:.2f} ms per mask pair  (R²={r2:.3f})")

    ax.set_xlabel("Mask pairs requiring reconstruction  ($n_{dec\\_targets}$)")
    ax.set_ylabel("Server reconstruction time (s)")
    ax.set_title("Reconstruction cost scales linearly with dropout-induced pairs",
                 loc="left", pad=12)
    ax.set_xlim(-x.max() * 0.03, x.max() * 1.05)
    ax.set_ylim(0, y.max() * 1.12)
    tidy(ax, "both")
    ax.legend(loc="upper left", handlelength=2.2)

    # 标注掉线率最高的那个点（最贵的样本）
    imax = int(np.argmax(y))
    ax.annotate(f"{y[imax]:.1f}s @ {int(x[imax])} pairs",
                xy=(x[imax], y[imax]), xytext=(x[imax] * 0.62, y[imax] * 0.97),
                fontsize=9, color=C_INK,
                arrowprops=dict(arrowstyle="-|>", color=C_INK, linewidth=1.0,
                                shrinkA=0, shrinkB=7))

    save(fig, "5_recon_scaling.png")
    print(f"  recon scaling: {len(pts)} points, {slope * 1000:.2f} ms/pair, R2={r2:.3f}")


def fig_accuracy(specs):
    """specs: [(label, console.log 路径)]，解析 fedlearn 的 'MLP SCORE' 序列。"""
    series = []
    for label, path in specs:
        if not os.path.isfile(path):
            continue
        vals = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = RE_SCORE.search(line)
                if m:
                    vals.append(float(m.group(1)) * 100.0)
        if vals:
            series.append((label, vals))
            print(f"  {label}: {len(vals)} rounds, final {vals[-1]:.2f}%")

    if not series:
        print("skip accuracy: no MLP SCORE found")
        return

    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    colors = [C_FLAM, C_BBGLR, C_INK]
    for i, (label, vals) in enumerate(series):
        T = np.arange(1, len(vals) + 1)
        ax.plot(T, vals, color=colors[i % len(colors)], linewidth=2.0,
                marker="o", markersize=4.6, label=label)
        ax.annotate(f"{vals[-1]:.1f}%", xy=(T[-1], vals[-1]),
                    textcoords="offset points", xytext=(8, -3),
                    fontsize=9.5, color=colors[i % len(colors)], va="center")

    ax.set_xlabel("Aggregation round  t")
    ax.set_ylabel("Test accuracy (%)")
    ax.set_title("Federated training under secure aggregation  (MNIST, 128 clients)",
                 loc="left", pad=12)
    ax.set_ylim(max(0, min(min(v) for _, v in series) - 12),
                min(100, max(max(v) for _, v in series) + 6))
    ax.set_xlim(1, max(len(v) for _, v in series) + 0.9)
    tidy(ax, "both")
    ax.legend(loc="lower right")
    save(fig, "6_training_accuracy.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", type=float, default=62.0, help="one-time setup seconds")
    ap.add_argument("--flamingo", default="20261122_n1024_cal25_flamingo")
    ap.add_argument("--bbglr", default="20261122_n1024_cal25_bbglr")
    ap.add_argument("--t10-flamingo", default="20261122_T10_cal25_flamingo")
    ap.add_argument("--t10-bbglr", default="20261122_T10_cal25_bbglr")
    ap.add_argument("--acc", action="append", default=[],
                    help="label=path/to/console.log（fedlearn 训练日志），可多次指定")
    args = ap.parse_args()

    apply_style()
    fig_calibration()

    specs = [("flamingo_cal25", args.flamingo), ("bbglr_cal25", args.bbglr),
             ("flamingo_adaptive99", "20261122_n1024_i1_adaptive99"),
             ("bbglr_adaptive99", "20261122_n1024_i1_bbglr_adaptive99")]
    data = fig_single_round(specs)

    # 摊销用 T=10 实测的稳态每轮均值（更贴近真实训练会话）；
    # 拿不到就退回单轮实测。
    fl10 = parse_iter_totals(args.t10_flamingo)
    bb10 = parse_iter_totals(args.t10_bbglr)
    fl_pr = float(np.mean(fl10)) if fl10 else (data.get("flamingo_cal25") or {}).get("total")
    bb_pr = float(np.mean(bb10)) if bb10 else (data.get("bbglr_cal25") or {}).get("total")
    if fl_pr and bb_pr:
        fig_amortized(fl_pr, bb_pr, args.setup)

    fig_multi_round(args.t10_flamingo, args.t10_bbglr)

    fig_recon_scaling([
        args.t10_flamingo,
        args.flamingo,
        "20261122_n1024_i1",             # 16% 掉线那轮（硬编码 2s）
        "20261122_n128_i3",
        "20261122_n1024_i1_adaptive99",
    ])

    if args.acc:
        specs = []
        for item in args.acc:
            label, path = item.split("=", 1) if "=" in item else (item, item)
            specs.append((label, path))
        fig_accuracy(specs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
