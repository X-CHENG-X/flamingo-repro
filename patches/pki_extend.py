#!/usr/bin/env python3
"""
把 PKI 里的客户端密钥扩展到 N 个（增量，不覆盖已有）。

上游 pki_files/setup_pki.py 硬编码生成 512 个客户端密钥，因此 -n 512 是实际上限，
论文的 1K 规模无法运行。本脚本只补生成 client<existing>..client<N-1>。

用法：
    python patches/pki_extend.py --repo /path/to/ppfl --n 1024

须先运行上游自带的 setup_pki.py（它还会生成服务端密钥与解密者密钥），本脚本只做补充。
幂等：已够数时直接 NOOP。
"""
import argparse
import os
import re
import sys

try:
    from Cryptodome.PublicKey import ECC
except ImportError:
    print("需要 pycryptodomex：pip install pycryptodomex", file=sys.stderr)
    raise


def existing_count(pki_dir):
    n = 0
    for fn in os.listdir(pki_dir):
        m = re.fullmatch(r"client(\d+)\.pem", fn)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--n", type=int, default=1024)
    args = ap.parse_args()

    pki_dir = os.path.join(os.path.abspath(args.repo), "pki_files")
    if not os.path.isdir(pki_dir):
        print(f"错误：{pki_dir} 不存在，请先运行上游 pki_files/setup_pki.py", file=sys.stderr)
        return 2

    have = existing_count(pki_dir)
    print(f"现有客户端密钥 {have} 个，目标 {args.n}")
    if have >= args.n:
        print("NOOP")
        return 0

    for i in range(have, args.n):
        key = ECC.generate(curve="P-256")
        with open(os.path.join(pki_dir, f"client{i}.pem"), "w", encoding="utf-8") as f:
            f.write(key.export_key(format="PEM"))
    print(f"已生成 {args.n - have} 个 -> 现有 {existing_count(pki_dir)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
