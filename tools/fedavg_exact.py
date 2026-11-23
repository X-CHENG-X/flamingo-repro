#!/usr/bin/env python3
"""
WB 工具：逐位复刻版明文 FedAvg + 可选编码消融。

用途：定位「加密版精度 96.4% 高于明文 FedAvg」的反常。

与 fedavg_baseline.py 的区别：字面照抄 fedlearn 客户端训练路径
  - 每轮新建 MLPClassifier(warm_start=True)（Adam 动量因此每轮重置）
  - 手工塞入 10 个内部属性（coefs_/intercepts_/n_iter_/n_layers_/n_outputs_/
    t_/_no_improvement_count/loss_/best_loss_/loss_curve_/out_activation_）
  - 第 1 轮用不带 random_state 的 MLPClassifier()（与上游一致）
  - 服务端评估也是「新建 + partial_fit(X_help) 再覆盖权重」的写法

加 --encode 后，聚合走上游那条路：每个客户端 (w+c)*2^m 截断成 uint32，
按 uint32 累加（溢出即回绕），再 /n/2^m - c 解码。

用法：
  python tools/fedavg_exact.py -i 10            # 纯明文浮点平均
  python tools/fedavg_exact.py -i 10 --encode   # 加上整数编码往返
"""
import argparse
import csv
import os
import sys
import time
from math import floor

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, "data", "pmlb")

C_OFF = 100        # 上游 config 默认 constant
M_SHIFT = 16       # 上游 config 默认 multiplier（作用是指数）


def load_data(seed):
    from pmlb import fetch_data
    X, y = fetch_data("mnist", return_X_y=True, local_cache_dir=CACHE)
    X = StandardScaler().fit(X).transform(X)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=seed)
    X_te, X_help, y_te, y_help = train_test_split(X_te, y_te, test_size=0.1, random_state=seed)
    return X_tr, y_tr, X_te, y_te, X_help, y_help, np.unique(y_tr)


def split_clients(X_tr, y_tr, n_clients, nk, seed):
    rng = np.random.default_rng(seed)
    classes = np.unique(y_tr)
    out = []
    for _ in range(n_clients):
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


def set_state(mlp, coefs, ints, n_iter, n_layers, n_outputs, t, nic,
              loss, best_loss, curve):
    """照抄上游：把全局状态塞进新建 estimator。"""
    mlp.coefs_ = [c.copy() for c in coefs]
    mlp.intercepts_ = [i.copy() for i in ints]
    mlp.n_iter_ = n_iter
    mlp.n_layers_ = n_layers
    mlp.n_outputs_ = n_outputs
    mlp.t_ = t
    mlp._no_improvement_count = nic
    mlp.loss_ = loss
    mlp.best_loss_ = best_loss
    mlp.loss_curve_ = list(curve)
    mlp.out_activation_ = "softmax"
    return mlp


def encode(a):
    return ((a + C_OFF) * (2 ** M_SHIFT)).astype(np.uint32)


def decode(a, n):
    return (a.astype(np.float64) / n) / float(2 ** M_SHIFT) - C_OFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--iterations", type=int, default=10)
    ap.add_argument("-n", "--clients", type=int, default=128)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--encode", action="store_true",
                    help="聚合走 (w+100)*2^16 -> uint32 -> 解码 的路径")
    args = ap.parse_args()
    tag = "exact_encode" if args.encode else "exact"

    print("[1/3] 载入 MNIST")
    X_tr, y_tr, X_te, y_te, X_help, y_help, classes = load_data(args.seed)
    nk = floor(len(X_tr) / args.clients)
    print(f"      X_train={X_tr.shape} X_test={X_te.shape} nk={nk} "
          f"clients={args.clients} epochs={args.epochs} encode={args.encode}")

    local = split_clients(X_tr, y_tr, args.clients, nk, args.seed)

    g = {"coefs": None, "ints": None, "n_iter": 0, "t": 0, "nic": 0,
         "loss": 0.0, "best_loss": 0.0, "curve": [], "n_layers": 3, "n_outputs": 10}

    rows = []
    print(f"[2/3] 训练 {args.iterations} 轮")
    print(f"      {'round':>5} {'acc':>9} {'sec':>7} {'note':>10}")
    t0 = time.time()
    for t in range(1, args.iterations + 1):
        ts = time.time()
        sum_c = sum_i = None
        metas = []
        wrapped = 0
        for cid in range(args.clients):
            if t == 1:
                mlp = MLPClassifier()
            else:
                mlp = MLPClassifier(warm_start=True)
                set_state(mlp, g["coefs"], g["ints"], g["n_iter"], g["n_layers"],
                          g["n_outputs"], g["t"], g["nic"], g["loss"],
                          g["best_loss"], g["curve"])
            Xc, yc = local[cid]
            if os.environ.get("WB_DBG") and cid == 0 and 1 < t <= 3:
                _pre = np.concatenate([c.ravel() for c in mlp.coefs_])
                print("        [dbg] t=%d START std=%.5f" % (t, _pre.std()))
            for _ in range(args.epochs):
                mlp.partial_fit(Xc, yc, classes=classes)
            if os.environ.get("WB_DBG") and cid == 0 and 1 < t <= 3:
                _post = np.concatenate([c.ravel() for c in mlp.coefs_])
                print("        [dbg] t=%d END   std=%.5f" % (t, _post.std()))

            cs = [encode(c) for c in mlp.coefs_] if args.encode else mlp.coefs_
            is_ = [encode(i) for i in mlp.intercepts_] if args.encode else mlp.intercepts_

            if sum_c is None:
                dt = np.uint32 if args.encode else np.float64
                sum_c = [c.copy().astype(dt) for c in cs]
                sum_i = [i.copy().astype(dt) for i in is_]
            else:
                for k in range(len(cs)):
                    if args.encode:
                        before = sum_c[k].astype(np.uint64) + cs[k].astype(np.uint64)
                        wrapped += int(np.sum(before > 0xFFFFFFFF))
                        sum_c[k] = (sum_c[k] + cs[k]).astype(np.uint32)   # 回绕，同上游
                        sum_i[k] = (sum_i[k] + is_[k]).astype(np.uint32)
                    else:
                        sum_c[k] += cs[k]
                        sum_i[k] += is_[k]
            metas.append((mlp.n_iter_, mlp.t_, mlp._no_improvement_count,
                          float(mlp.loss_), float(mlp.best_loss_)))

        n = args.clients
        if args.encode:
            g["coefs"] = [decode(c, n) for c in sum_c]
            g["ints"] = [decode(i, n) for i in sum_i]
        else:
            g["coefs"] = [c / n for c in sum_c]
            g["ints"] = [i / n for i in sum_i]

        m = np.array(metas, dtype=float)
        g["n_iter"] = int(m[:, 0].mean())
        g["t"] = int(m[:, 1].mean())
        g["nic"] = int(m[:, 2].mean())
        g["loss"] = float(m[:, 3].mean())
        g["best_loss"] = float(m[:, 4].mean())
        g["n_layers"] = len(g["coefs"]) + 1
        g["n_outputs"] = g["coefs"][-1].shape[1]
        g["curve"] = []

        ev = MLPClassifier(max_iter=1, warm_start=True)
        ev.partial_fit(X_help, y_help, classes=classes)
        ev.n_iter_ = g["n_iter"]
        ev.n_layers_ = g["n_layers"]
        ev.n_outputs_ = g["n_outputs"]
        ev.t_ = g["t"]
        ev.coefs_ = [c.copy() for c in g["coefs"]]
        ev.intercepts_ = [i.copy() for i in g["ints"]]
        acc = float(ev.score(X_te, y_te))

        dt = time.time() - ts
        note = f"wrap={wrapped}" if args.encode and wrapped else ""
        _flat = np.concatenate([c.ravel() for c in g["coefs"]])
        rows.append({"round": t, "accuracy_pct": round(acc * 100, 3),
                     "seconds": round(dt, 2), "uint32_wraps": wrapped,
                     "coef_std": round(float(_flat.std()), 6),
                     "coef_absmax": round(float(np.abs(_flat).max()), 4)})
        print(f"      {t:>5} {acc * 100:>8.2f}% {dt:>6.1f}s "
              f"std={_flat.std():.4f} absmax={np.abs(_flat).max():.3f} {note}")

    out = os.path.join(REPO, "results", f"baseline_{tag}_seed{args.seed}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["round", "accuracy_pct", "seconds", "uint32_wraps", "coef_std", "coef_absmax"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n总墙钟 {time.time() - t0:.1f}s  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
