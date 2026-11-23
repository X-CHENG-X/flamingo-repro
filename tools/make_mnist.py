#!/usr/bin/env python3
"""
WB 工具：离线准备 pmlb 格式的 MNIST（绕过 GitHub 直连）。

背景：fedlearn 分支用 `pmlb.fetch_data('mnist')`，该函数直接从
github.com/EpistasisLab/penn-ml-benchmarks 读 mnist.tsv.gz。
国内 raw.githubusercontent 不通，jsdelivr 对 >20MB 文件返回错误页。

做法：
  1. 从 S3 / Google 镜像拉 MNIST 原始 idx 文件（4 个，各 ~10MB）
  2. 转成 pmlb 的目录布局 <cache>/mnist/mnist.tsv.gz（784 列 + target）
  3. 之后 fetch_data(..., local_cache_dir=<cache>) 命中缓存，不再联网

用法：python tools/make_mnist.py [cache_dir]
默认 cache_dir = <repo>/data/pmlb
"""
import gzip
import os
import struct
import sys
import urllib.request

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIRRORS = [
    "https://ossci-datasets.s3.amazonaws.com/mnist/{}",
    "https://storage.googleapis.com/cvdf-datasets/mnist/{}",
]

FILES = [
    "train-images-idx3-ubyte.gz",
    "train-labels-idx1-ubyte.gz",
    "t10k-images-idx3-ubyte.gz",
    "t10k-labels-idx1-ubyte.gz",
]


def fetch(fn, cache):
    dst = os.path.join(cache, fn)
    if os.path.isfile(dst) and os.path.getsize(dst) > 1_000:
        print(f"  cached {fn}")
        return dst
    last = None
    for m in MIRRORS:
        url = m.format(fn)
        try:
            print(f"  GET {url}")
            urllib.request.urlretrieve(url, dst)
            if os.path.getsize(dst) > 1_000:
                return dst
        except Exception as e:      # noqa: BLE001
            last = e
            print(f"    failed: {e}")
    raise RuntimeError(f"all mirrors failed for {fn}: {last}")


def read_images(path):
    with gzip.open(path, "rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        assert magic == 2051, magic
        buf = f.read(n * rows * cols)
    return np.frombuffer(buf, dtype=np.uint8).reshape(n, rows * cols)


def read_labels(path):
    with gzip.open(path, "rb") as f:
        magic, n = struct.unpack(">II", f.read(8))
        assert magic == 2049, magic
        buf = f.read(n)
    return np.frombuffer(buf, dtype=np.uint8)


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "data", "pmlb")
    raw = os.path.join(cache, "_raw_mnist")
    os.makedirs(raw, exist_ok=True)

    print("[1/3] 下载原始 idx")
    for fn in FILES:
        fetch(fn, raw)

    print("[2/3] 解析")
    Xtr = read_images(os.path.join(raw, FILES[0]))
    ytr = read_labels(os.path.join(raw, FILES[1]))
    Xte = read_images(os.path.join(raw, FILES[2]))
    yte = read_labels(os.path.join(raw, FILES[3]))
    X = np.vstack([Xtr, Xte])
    y = np.concatenate([ytr, yte])
    print(f"  X={X.shape} y={y.shape}")

    print("[3/3] 写 pmlb 缓存")
    out_dir = os.path.join(cache, "mnist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "mnist.tsv.gz")
    cols = [f"pixel_{i}" for i in range(X.shape[1])]
    df = pd.DataFrame(X, columns=cols)
    df["target"] = y
    df.to_csv(out, sep="\t", index=False, compression="gzip")
    print(f"  wrote {out}  ({os.path.getsize(out) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
