#!/usr/bin/env python3
"""
WB 工具：校验 sum.jsonl —— 每轮的和是否正确。

判定依据：客户端输入是全 1 向量（SA_ClientAgent.sendVectors 里 np.ones），
两两掩码抵消 + 掉线者掩码重构之后，final_sum 的每个分量必须等于
本轮在线客户端数。即：
    sum_min == sum_max == n_online  且  sum_unique == 1

用法：python tools/verify.py [sum.jsonl ...]
      不给参数则扫描 runs/*/sum.jsonl
"""
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        print(f"{path}: empty")
        return False

    hdr = "{:>4} {:>7} {:>8} {:>8} {:>5}  {}"
    print(f"\n{path}")
    print(hdr.format("iter", "online", "dec_tgt", "sum_min", "uniq", "result"))
    allok = True
    for r in rows:
        ok = (r["sum_min"] == r["sum_max"] == r["n_online"] and r["sum_unique"] == 1)
        allok = allok and ok
        print(hdr.format(r["iteration"], r["n_online"], r["n_dec_targets"],
                         r["sum_min"], r["sum_unique"], "PASS" if ok else "FAIL"))
    print(f"  -> {'ALL PASS' if allok else 'SOME FAILED'} ({len(rows)} rounds)")
    return allok


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = sorted(glob.glob(os.path.join(REPO, "runs", "*", "sum.jsonl")))
    if not paths:
        print("no sum.jsonl found", file=sys.stderr)
        return 1
    results = [check(p) for p in paths]
    print(f"\n{sum(results)}/{len(results)} files passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
