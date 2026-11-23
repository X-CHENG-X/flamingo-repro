#!/usr/bin/env python3
"""
WB 探针：验证「聚合结果 == 明文均值」（透明性数值检验）。

思路：客户端在编码前把 float_vec 的统计量（mean/std）写一行；
      服务端在解码后把全局权重的统计量写一行。
      若加密层透明，服务端解码后的均值应等于各客户端 float_vec 均值的平均。

为什么用统计量而不是全量 dump：80000 维 × 128 客户端 = 41 MB/轮，
统计量足以发现「缩放错、偏移错、掩码没抵消」这类错误（都会让均值对不上）。

环境变量：
  FL_DUMP_CLIENT=<path>   客户端写 <path>.client.jsonl
  FL_DUMP_SERVER=<path>   服务端写 <path>.server.jsonl
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "agent", "flamingo", "SA_ClientAgent.py")
SRV = os.path.join(REPO, "agent", "flamingo", "SA_ServiceAgent.py")

MARK = "[WB-TRANSP]"

# 客户端：在 vec = 编码之前插桩
CLI_ANCHOR = "        vec = np.vectorize(lambda d: (d+self.c) * pow(2,self.m))(float_vec).astype(self.vector_dtype)\n"
CLI_SNIPPET = '''        _wb_p = os.environ.get("FL_DUMP_CLIENT")  # [WB-TRANSP]
        if _wb_p:
            with open(_wb_p + ".client.jsonl", "a", encoding="utf-8") as _f:
                _f.write('{"iter": %d, "cid": %d, "mean": %.10f, "std": %.10f, "absmax": %.10f}\\n'
                         % (int(self.current_iteration), int(self.id),
                            float(np.mean(float_vec)), float(np.std(float_vec)),
                            float(np.max(np.abs(float_vec)))))
'''

# 服务端：在 score 之前插桩
SRV_ANCHOR = '        print("[Server] MLP SCORE: ", mlp.score(self.X_test,self.y_test))\n'
SRV_SNIPPET = '''        _wb_p = os.environ.get("FL_DUMP_SERVER")  # [WB-TRANSP]
        if _wb_p:
            with open(_wb_p + ".server.jsonl", "a", encoding="utf-8") as _f:
                _f.write('{"iter": %d, "clients": %d, "mean": %.10f, "std": %.10f, "absmax": %.10f}\\n'
                         % (int(self.current_iteration), int(rec),
                            float(np.mean(nums)), float(np.std(nums)),
                            float(np.max(np.abs(nums)))))
'''


def patch(path, anchor, snippet, backup_suffix):
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        return "already"
    if src.count(anchor) != 1:
        return f"ANCHOR_MISS({src.count(anchor)})"
    open(path + backup_suffix, "w", encoding="utf-8").write(src)
    open(path, "w", encoding="utf-8").write(src.replace(anchor, anchor + snippet))
    return "ok"


def main():
    print("client:", patch(CLI, CLI_ANCHOR, CLI_SNIPPET, ".bak_transp"))
    print("server:", patch(SRV, SRV_ANCHOR, SRV_SNIPPET, ".bak_transp"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
