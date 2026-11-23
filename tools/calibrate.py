#!/usr/bin/env python3
"""
WB 工具：从 arrivals.jsonl 标定「超时 -> 掉线率」，并写出 calibration.csv。

背景：论文 §8.1 的做法是按目标掉线率 δ 反推每步等待时间。上游代码里
这些超时是作者机器上的定值（10s/3s/3s），直接搬过来会得到完全不同的 δ
（本机 10s -> 4.3%，而上游第 1 轮还硬编码 2s -> 15%）。

用法：
  python tools/calibrate.py runs/<dir>/arrivals.jsonl [-o results/calibration.csv]
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    ts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ts.append(json.loads(line)["t"])
    a = np.array(ts, dtype=float)
    if a.size == 0:
        return a
    return np.sort(a - a.min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arrivals")
    ap.add_argument("-o", "--out", default=os.path.join(REPO, "results", "calibration.csv"))
    ap.add_argument("-n", "--num-clients", type=int, default=1024)
    args = ap.parse_args()

    a = load(args.arrivals)
    if a.size == 0:
        print("no arrivals", file=sys.stderr)
        return 1

    total = max(args.num_clients, a.size)
    grid = [1, 2, 5, 7.5, 10, 15, 20, 25, 30]
    rows = []
    print(f"arrivals={a.size}, total_clients={total}, max={a[-1]:.2f}s\n")
    print(f"{'timeout(s)':>10} {'dropped':>8} {'dropout%':>9}   {'p(dropout<=x)':>10}")
    for t in grid:
        dropped = int((a > t).sum()) + (total - a.size)
        pct = 100.0 * dropped / total
        rows.append({"timeout_s": t, "dropped": dropped, "dropout_pct": round(pct, 3)})
        print(f"{t:>10} {dropped:>8} {pct:>8.2f}%")

    print("\n分位数：")
    for q in (90, 95, 97, 98, 99, 99.5, 99.9):
        print(f"  p{q:<5} = {np.percentile(a, q):7.3f}s  (超时设为此值 -> 掉线 {100 - q:.1f}%)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timeout_s", "dropped", "dropout_pct"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
