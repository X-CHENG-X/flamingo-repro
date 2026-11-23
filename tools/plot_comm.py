#!/usr/bin/env python3
"""
WB 工具：通信量对比（对应论文 Fig.6）。

数据来自 tools/probe_comm.py 在 Kernel.sendMessage 层的计量，
格式 { "<type>|<sender>|<recipient>": {"bytes":N,"msgs":M} }。

处理：
  1. 用「收到消息最多的那个 id」判定服务端
  2. 按方向聚合：server->x / x->server
  3. 输出两张面板：
     (a) 每轮服务端总通信量（入 / 出）
     (b) 每客户端通信量（上行 / 下行）
"""
import json
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(REPO, "figures")
COMM = os.path.join(REPO, "runs", "comm")

C_FLAM = "#C25B4A"
C_BBGLR = "#3F6C8F"
C_INK = "#3F4A56"
C_GRID = "#E6E8EB"


def load(path):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["totals"]


def analyze(totals, n_clients=1024):
    """返回 (server_in, server_out, per_msg, server_id)"""
    recv_count = defaultdict(int)
    parsed = []
    for key, v in totals.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        mtype, s, r = parts[0], int(parts[1]), int(parts[2])
        parsed.append((mtype, s, r, v["bytes"], v["msgs"]))
        recv_count[r] += v["msgs"]

    if not recv_count:
        return None
    server_id = max(recv_count, key=recv_count.get)

    server_in = defaultdict(lambda: [0, 0])    # x -> server
    server_out = defaultdict(lambda: [0, 0])   # server -> x
    for mtype, s, r, b, m in parsed:
        if r == server_id and s != server_id:
            e = server_in[mtype]
            e[0] += b
            e[1] += m
        elif s == server_id and r != server_id:
            e = server_out[mtype]
            e[0] += b
            e[1] += m

    tot_in = sum(v[0] for v in server_in.values())
    tot_out = sum(v[0] for v in server_out.values())
    return {"server_id": server_id, "in": dict(server_in), "out": dict(server_out),
            "tot_in": tot_in, "tot_out": tot_out, "n_clients": n_clients}


def mb(x):
    return x / 1e6


def main():
    fl = load(os.path.join(COMM, "flamingo.json"))
    bb = load(os.path.join(COMM, "bbglr.json"))
    a_fl = analyze(fl) if fl else None
    a_bb = analyze(bb) if bb else None

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.titlesize": 12.5, "axes.labelsize": 11,
        "axes.edgecolor": "#B9BFC6", "axes.linewidth": 0.9,
        "axes.labelcolor": C_INK, "xtick.color": "#4A4F55", "ytick.color": "#4A4F55",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.3))

    names = [n for n, a in (("Flamingo", a_fl), ("BBGLR", a_bb)) if a]
    cols = [C_FLAM if n == "Flamingo" else C_BBGLR for n in names]

    # --- (a) 服务端收到的通信量（可比） ---
    ax = axes[0]
    vals = [mb(a["tot_in"]) for a in (a_fl, a_bb) if a]
    x = np.arange(len(vals))
    bars = ax.bar(x, vals, width=0.5, color=cols, zorder=3)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:.1f} MB", (b.get_x() + b.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 5),
                    ha="center", fontsize=9.5, color=C_INK)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("MB per round")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.set_title("Server inbound  (clients → server)", loc="left", pad=12)

    # --- (b) 每客户端上行 ---
    ax = axes[1]
    vals2 = [mb(a["tot_in"]) / a["n_clients"] * 1000 for a in (a_fl, a_bb) if a]
    bars = ax.bar(np.arange(len(vals2)), vals2, width=0.5, color=cols, zorder=3)
    for b, v in zip(bars, vals2):
        ax.annotate(f"{v:.1f} KB", (b.get_x() + b.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 5),
                    ha="center", fontsize=9.5, color=C_INK)
    ax.set_xticks(np.arange(len(vals2)))
    ax.set_xticklabels(names)
    ax.set_ylabel("KB per client per round")
    ax.set_ylim(0, max(vals2) * 1.22)
    ax.set_title("Client uplink  (16K-dim vector + crypto)", loc="left", pad=12)

    for ax in axes:
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color=C_GRID, linewidth=0.9)
        ax.set_axisbelow(True)

    fig.tight_layout(pad=2.2)
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, "11_communication.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    print("wrote", out)

    for name, a in (("Flamingo", a_fl), ("BBGLR", a_bb)):
        if not a:
            print(f"  {name}: no data")
            continue
        print(f"\n{name}  (server id={a['server_id']})")
        print(f"  inbound  {mb(a['tot_in']):8.1f} MB    outbound {mb(a['tot_out']):8.1f} MB")
        for mt, (b, m) in sorted(a["in"].items(), key=lambda kv: -kv[1][0]):
            print(f"    in  {mt:22s} {mb(b):8.2f} MB  msgs={m}")
        for mt, (b, m) in sorted(a["out"].items(), key=lambda kv: -kv[1][0]):
            print(f"    out {mt:22s} {mb(b):8.2f} MB  msgs={m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
