#!/usr/bin/env python3
"""
WB 工具：独立评估 Flamingo 服务端产出的全局权重，并与明文基线对比。

目的：区分两种可能
  (a) 服务端评估有问题（同一份权重在我的管线里掉下来）
  (b) 权重确实更好（我的管线也给高分）→ 差异在客户端训练

用法：python tools/eval_weights.py runs/wdump/w_iter10.pkl
"""
import os
import pickle
import sys

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, "data", "pmlb")


def load_data(seed=42):
    from pmlb import fetch_data
    X, y = fetch_data("mnist", return_X_y=True, local_cache_dir=CACHE)
    X = StandardScaler().fit(X).transform(X)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=seed)
    X_te, X_help, y_te, y_help = train_test_split(X_te, y_te, test_size=0.1, random_state=seed)
    return X_tr, y_tr, X_te, y_te, X_help, y_help, np.unique(y_tr)


def evaluate(coefs, ints, X_te, y_te, X_help, y_help, classes):
    ev = MLPClassifier(max_iter=1, warm_start=True)
    ev.partial_fit(X_help, y_help, classes=classes)
    ev.coefs_ = [c.copy() for c in coefs]
    ev.intercepts_ = [i.copy() for i in ints]
    return float(ev.score(X_te, y_te))


def stats(name, coefs):
    flat = np.concatenate([c.ravel() for c in coefs])
    print(f"  {name:12s} n={flat.size:6d}  mean={flat.mean():+.6f}  "
          f"std={flat.std():.6f}  absmax={np.abs(flat).max():.4f}  L2={np.linalg.norm(flat):.3f}")


def main():
    pkl = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, "runs", "wdump", "w_iter10.pkl")
    with open(pkl, "rb") as f:
        d = pickle.load(f)

    X_tr, y_tr, X_te, y_te, X_help, y_help, classes = load_data(42)
    print(f"测试集 {X_te.shape}，与 fedlearn 服务端一致")
    print(f"服务端自报 score: {d['score']:.6f}  (shape={d.get('X_test_shape')})")

    acc = evaluate(d["coefs"], d["intercepts"], X_te, y_te, X_help, y_help, classes)
    print(f"本管线复评 score: {acc:.6f}   (差 {abs(acc - d['score']) * 100:.4f} 个百分点)")
    stats("flamingo", d["coefs"])

    # 对照：明文基线同轮次的权重
    base = os.path.join(REPO, "results", "baseline_exact_seed42.csv")
    if os.path.isfile(base):
        import csv
        rows = list(csv.DictReader(open(base, encoding="utf-8")))
        print(f"  明文基线第 {rows[-1]['round']} 轮: {rows[-1]['accuracy_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
