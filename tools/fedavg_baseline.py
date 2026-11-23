#!/usr/bin/env python3
"""
WB 工具：明文 FedAvg 基线（对照组）。

目的：论文 Fig.10 里的 "Baseline" 线（不加密的 FedAvg）**没有开源**，
而"安全聚合不损失精度"这句话必须有它作参照才成立。本脚本在完全不涉及
ABIDES / 掩码 / 整数编码的前提下，复刻 fedlearn 分支的训练协议：

  数据：pmlb MNIST（本地缓存）→ StandardScaler（在全体 X 上 fit，与上游一致）
        → train_test_split(test_size=0.25) → X_test 再切 10% 作 X_help
  客户端：128 个，每个固定分到 nk = floor(len(X_train)/128) ≈ 410 条，
         并保证覆盖全部 10 个类别（复刻上游的补类逻辑）
  本地训练：MLPClassifier.partial_fit 跑 5 个 epoch（= 5 次 partial_fit）
  聚合：服务端直接对 coefs_ / intercepts_ 做**浮点逐元素平均**（标准 FedAvg）
  第 1 轮：各客户端从各自随机初始化开始（与上游一致），之后再从全局模型继续

用法：
  python tools/fedavg_baseline.py [-i 10] [-n 128] [--seed 42]
输出：每轮准确率，并写 results/baseline_accuracy.csv
"""
import argparse
import copy
import csv
import os
import sys
from math import floor

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, "data", "pmlb")


def load_data(seed):
    from pmlb import fetch_data
    X, y = fetch_data("mnist", return_X_y=True, local_cache_dir=CACHE)
    scaler = StandardScaler().fit(X)          # 与上游一致：在全体 X 上 fit
    X = scaler.transform(X)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=seed)
    X_te, X_help, y_te, y_help = train_test_split(
        X_te, y_te, test_size=0.1, random_state=seed)
    return X_tr, y_tr, X_te, y_te, X_help, y_help, np.unique(y_tr)


def split_clients(X_tr, y_tr, n_clients, nk, seed, mode="overlap"):
    if mode == "disjoint":
        perm = np.random.default_rng(seed).permutation(len(X_tr))
        chunks = np.array_split(perm[: n_clients * nk], n_clients)
        return [(X_tr[c].copy(), y_tr[c].copy()) for c in chunks]
    """每个客户端一份固定本地数据，且覆盖全部类别（复刻上游逻辑）。"""
    rng = np.random.default_rng(seed)
    classes = np.unique(y_tr)
    out = []
    for cid in range(n_clients):
        idx = rng.choice(len(X_tr), size=nk, replace=False)
        perm = rng.permutation(len(X_tr))
        p = 0
        while len(set(y_tr[idx])) < len(classes):
            add = perm[p]
            merged = np.concatenate((idx, [add]))
            if len(set(y_tr[merged])) > len(set(y_tr[idx])):
                u, c = np.unique(y_tr[idx], return_counts=True)
                dup = u[c > 1]
                rm = np.where(y_tr[idx] == dup[0])[0][0]
                idx = np.concatenate(([add], np.delete(idx, rm)))
            p += 1
        out.append((X_tr[idx].copy(), y_tr[idx].copy()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--iterations", type=int, default=10)
    ap.add_argument("-n", "--clients", type=int, default=128)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=5, help="每客户端本地 epoch 数")
    ap.add_argument("--split", choices=["overlap", "disjoint"], default="overlap",
                    help="客户端数据划分：overlap=随机重叠（上游实现），disjoint=不重叠均分（论文文字）")
    args = ap.parse_args()

    print(f"[1/3] 载入 MNIST（缓存 {CACHE}）")
    X_tr, y_tr, X_te, y_te, X_help, y_help, classes = load_data(args.seed)
    nk = floor(len(X_tr) / args.clients)
    print(f"      X_train={X_tr.shape}  X_test={X_te.shape}  "
          f"clients={args.clients}  nk={nk}  classes={classes.tolist()}  split={args.split}")

    print("[2/3] 切分客户端本地数据")
    local = split_clients(X_tr, y_tr, args.clients, nk, args.seed, args.split)

    # 用 X_help 建一个结构模板，之后各客户端深拷贝它并替换权重
    proto = MLPClassifier(max_iter=1, warm_start=True, random_state=0)
    proto.partial_fit(X_help, y_help, classes=classes)

    g_coefs, g_ints = None, None
    rows = []
    print(f"[3/3] 训练 {args.iterations} 轮（明文聚合，无加密）")
    print(f"      {'round':>5} {'accuracy':>10} {'elapsed':>9}")
    import time
    t0 = time.time()
    for t in range(1, args.iterations + 1):
        ts = time.time()
        coefs_acc, ints_acc = None, None
        for cid in range(args.clients):
            if t == 1:
                # 复刻上游：第 1 轮每个客户端各自随机初始化（互不相同）。
                # 上游用的是 MLPClassifier() 不设 random_state（不可复现），
                # 这里用 random_state=cid 固定下来，语义等价。
                m = MLPClassifier(max_iter=1, warm_start=True, random_state=cid)
            else:
                m = copy.deepcopy(proto)
                m.coefs_ = [c.copy() for c in g_coefs]
                m.intercepts_ = [i.copy() for i in g_ints]
            Xc, yc = local[cid]
            for _ in range(args.epochs):
                m.partial_fit(Xc, yc, classes=classes)
            if coefs_acc is None:
                coefs_acc = [c.copy() for c in m.coefs_]
                ints_acc = [i.copy() for i in m.intercepts_]
            else:
                for k in range(len(coefs_acc)):
                    coefs_acc[k] += m.coefs_[k]
                    ints_acc[k] += m.intercepts_[k]
        g_coefs = [c / args.clients for c in coefs_acc]
        g_ints = [i / args.clients for i in ints_acc]

        ev = copy.deepcopy(proto)
        ev.coefs_ = [c.copy() for c in g_coefs]
        ev.intercepts_ = [i.copy() for i in g_ints]
        acc = float(ev.score(X_te, y_te))

        dt = time.time() - ts
        rows.append({"round": t, "accuracy": round(acc, 6),
                     "accuracy_pct": round(acc * 100, 3), "seconds": round(dt, 2)})
        print(f"      {t:>5} {acc * 100:>9.2f}% {dt:>8.1f}s")

    out = os.path.join(REPO, "results", f"baseline_accuracy_seed{args.seed}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["round", "accuracy", "accuracy_pct", "seconds"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n总墙钟 {time.time() - t0:.1f}s   wrote {out}")
    print(f"最终准确率 {rows[-1]['accuracy_pct']:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
