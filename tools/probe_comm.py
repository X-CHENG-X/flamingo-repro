#!/usr/bin/env python3
"""
WB 探针：在消息传输层统一计量通信量，一次拿到任意协议的完整分项。

为什么不在各 agent 里逐个埋点：上游只给 Flamingo 埋了 2 个消息类型
（VECTOR / SIGN），BBGLR 一个都没埋。改在 Kernel.sendMessage 里计量，
对所有协议一视同仁，也不用改业务代码。

输出：环境变量 WB_COMM_DUMP 指定的 json，结构为
  { "<msg_type>|<direction>": {"bytes": N, "msgs": M}, ... }
其中 direction ∈ {server->client, client->server, server<->server}

用法：
  export WB_COMM_DUMP=/abs/path/comm.json
  python abides.py -c flamingo -n 1024 -i 1 -w fixed
幂等。
"""
import os
import sys

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Kernel.py")

MARK = "[WB-COMM]"

IMPORTS = """import os as _wb_os, sys as _wb_sys, json as _wb_json, atexit as _wb_atexit  # [WB-COMM]
import numpy as _wb_np

_WB_COMM = {}


def _wb_size(o, depth=0):
    if depth > 8:
        return 0
    if isinstance(o, _wb_np.ndarray):
        return int(o.nbytes)
    if isinstance(o, (bytes, bytearray)):
        return len(o)
    if isinstance(o, str):
        return len(o.encode("utf-8", "ignore"))
    if isinstance(o, dict):
        return sum(_wb_size(k, depth + 1) + _wb_size(v, depth + 1) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return sum(_wb_size(v, depth + 1) for v in o)
    if isinstance(o, (int, float, bool)):
        return 8
    try:
        return int(_wb_sys.getsizeof(o))
    except Exception:
        return 0


def _wb_record(sender, recipient, msg):
    path = _wb_os.environ.get("WB_COMM_DUMP")
    if not path:
        return
    body = getattr(msg, "body", None)
    mtype = "?"
    if isinstance(body, dict):
        mtype = str(body.get("msg") or body.get("msg_type") or "?")
    key = "%s|%s|%s" % (mtype, sender, recipient)
    ent = _WB_COMM.setdefault(key, {"bytes": 0, "msgs": 0})
    ent["bytes"] += _wb_size(body)
    ent["msgs"] += 1


def _wb_dump():
    path = _wb_os.environ.get("WB_COMM_DUMP")
    if not path or not _WB_COMM:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            _wb_json.dump({"totals": _WB_COMM}, f, indent=1, sort_keys=True)
    except Exception:
        pass


_wb_atexit.register(_wb_dump)

"""

ANCHOR = "  def sendMessage(self, sender = None, recipient = None, msg = None, delay = 0, tag = None):\n"
INJECT = "    _wb_record(sender, recipient, msg)  # [WB-COMM]\n"


def main():
    src = open(P, encoding="utf-8").read()
    if MARK in src:
        print("ALREADY_PATCHED")
        return 0

    if src.count(ANCHOR) != 1:
        print("anchor miss:", src.count(ANCHOR), file=sys.stderr)
        return 1

    # 在模块最前面插入助手（放在首个 import 之后更稳妥，这里直接放文件头）
    src = IMPORTS + src
    # 在 sendMessage 的 docstring 之后、第一行语句之前注入
    idx = src.index(ANCHOR) + len(ANCHOR)
    # 跳过紧随其后的注释块，插入到 "if sender is None:" 之前
    anchor2 = "    if sender is None:\n"
    j = src.index(anchor2, idx)
    src = src[:j] + INJECT + src[j:]

    open(P + ".orig_comm", "w", encoding="utf-8").write(open(P, encoding="utf-8").read())
    open(P, "w", encoding="utf-8").write(src)
    print("PATCHED Kernel.sendMessage with comm accounting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
