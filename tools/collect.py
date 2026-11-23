#!/usr/bin/env python3
"""
WB 工具：把 runs/*/console.log 解析成一张汇总 CSV。

上游只往 stdout 打人读的文本，没有结构化输出，扫参后要手工抄数字。
本脚本按固定格式（"--- Iteration k ---" 段 + "--- Average across N iterations ---" 段）
解析，输出 results/summary.csv，每行 = 一次运行的一个 iteration。

用法：python tools/collect.py [runs 目录] [-o 输出 csv]
"""
import argparse
import csv
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RE_ITER = re.compile(r"^--- Iteration (\d+) ---\s*$")
RE_AVG = re.compile(r"^--- Average across (\d+) iterations ---\s*$")
RE_HDR = re.compile(r"^Protocol Iterations: (\d+), Clients: (\d+),")
RE_TS = re.compile(r"^\s+\+\s+([\d.]+)s\s+server ")
RE_KV = re.compile(r"^\s+(online_clients|offline_clients|dec_targets|decryptor_shares):\s*(\d+)")
RE_SRV = re.compile(r"^\s{4}(report|crosscheck|reconstruction)\s+([\d.]+)s")
RE_CLI = re.compile(r"^\s{4}(report|crosscheck|reconstruction)\s+avg=([\d.]+)s")
RE_COMM = re.compile(r"^\s{4}Comm (.+?)\s{2,}([\d,]+) bytes/iter")
RE_AVG_SRV = re.compile(r"^\s{2}Server (report|crosscheck|reconstruction)\s+([\d.]+)s")

# BBGLR（google_malicious）走另一套日志格式：没有 "--- Iteration k ---" 块，
# 只有 "######## Microbenchmarks ########" 里的 timedelta 均值。
RE_MB_SECTION = re.compile(r"^(Service|Client) Agent mean time per iteration")
RE_MB_LINE = re.compile(r"^\s{4}(Report|Crosscheck|Reconstruction) step:\s+"
                        r"(\d+) days (\d+):(\d+):([\d.]+)")


def _td(days, h, m, s):
    return int(days) * 86400 + int(h) * 3600 + int(m) * 60 + float(s)


def parse_bbglr_style(path):
    """BBGLR 格式兜底：从 Microbenchmarks 段取服务端/客户端均值，从时间线取总时长。"""
    srv, cli, total = {}, {}, None
    section = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = RE_TS.match(line)
            if m:
                total = float(m.group(1))
                continue
            m = RE_MB_SECTION.match(line)
            if m:
                section = m.group(1).lower()
                continue
            if section:
                m = RE_MB_LINE.match(line)
                if m:
                    key = m.group(1).lower()
                    val = _td(m.group(2), m.group(3), m.group(4), m.group(5))
                    (srv if section == "service" else cli)[key] = val
    if total is None:
        return None
    row = {"iteration": 1}
    for k, v in srv.items():
        row[f"srv_{k}"] = v
    for k, v in cli.items():
        row[f"cli_{k}"] = v
    # 单轮总时长（含网络等待），单独用一列，不与计算耗时混在一起
    row["round_total_s"] = total
    return row



def parse_log(path):
    iters = []
    avg = {}
    n_clients = None
    n_iters = None
    cur = None
    section = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")

            m = RE_HDR.match(line)
            if m:
                n_iters, n_clients = int(m.group(1)), int(m.group(2))
                continue

            if RE_AVG.match(line):
                section = "avg"
                cur = None
                continue

            m = RE_ITER.match(line)
            if m:
                section = "iter"
                cur = {"iteration": int(m.group(1))}
                iters.append(cur)
                continue

            if section == "iter" and cur is not None:
                m = RE_KV.match(line)
                if m:
                    cur[m.group(1)] = int(m.group(2))
                    continue
                if line.startswith("  Communication (bytes):"):
                    cur["_in_comm"] = True
                    continue
                m = RE_SRV.match(line)
                if m:
                    cur[f"srv_{m.group(1)}"] = float(m.group(2))
                    continue
                m = RE_CLI.match(line)
                if m:
                    cur[f"cli_{m.group(1)}"] = float(m.group(2))
                    continue
                m = RE_COMM.match(line)
                if m:
                    key = "comm_" + re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_")
                    cur[key] = int(m.group(2).replace(",", ""))
                    continue

            if section == "avg":
                m = RE_AVG_SRV.match(line)
                if m:
                    avg[f"srv_{m.group(1)}"] = float(m.group(2))
                    continue
                m = RE_CLI.match(line)
                if m:
                    avg[f"cli_{m.group(1)}"] = float(m.group(2))
                    continue
                m = RE_COMM.match(line)
                if m:
                    key = "comm_" + re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_")
                    avg[key] = int(m.group(2).replace(",", ""))

    for it in iters:
        it.pop("_in_comm", None)
    return n_clients, n_iters, iters, avg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_dir", nargs="?", default=os.path.join(REPO, "runs"))
    ap.add_argument("-o", "--out", default=os.path.join(REPO, "results", "summary.csv"))
    args = ap.parse_args()

    rows = []
    for name in sorted(os.listdir(args.runs_dir)):
        d = os.path.join(args.runs_dir, name)
        log = os.path.join(d, "console.log")
        if not (os.path.isdir(d) and os.path.isfile(log)):
            continue
        meta = {}
        mp = os.path.join(d, "meta.json")
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                meta = json.load(f)

        n_clients, n_iters, iters, avg = parse_log(log)
        if not iters:
            # 兜底：BBGLR 格式
            row = parse_bbglr_style(log)
            if row is None:
                print(f"[skip] {name}: no iteration block", file=sys.stderr)
                continue
            row.update({"run": name, "clients": n_clients, **meta})
            rows.append(row)
            continue
        for it in iters:
            row = {"run": name, "clients": n_clients or meta.get("n"), **meta, **it}
            row.setdefault("srv_report", avg.get("srv_report"))
            rows.append(row)

    if not rows:
        print("no data", file=sys.stderr)
        return 1

    # 并集列，保持稳定顺序
    pref = ["run", "protocol", "wait_mode", "n", "iterations", "iteration",
            "online_clients", "offline_clients", "dec_targets", "decryptor_shares",
            "srv_report", "srv_crosscheck", "srv_reconstruction",
            "cli_report", "cli_crosscheck", "cli_reconstruction"]
    keys = list(pref)
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"wrote {args.out}: {len(rows)} rows from {len({r['run'] for r in rows})} runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
