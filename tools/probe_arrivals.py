#!/usr/bin/env python3
"""
WB 探针：记录每个客户端 VECTOR 到达服务端的仿真时刻。

为什么：论文 §8.1 说超时要按"目标掉线率 δ + 延迟分布"标定。
要标定就得知道到达时间的经验分布（尤其是 99 分位），而不是靠公式猜。

用法：
  export FLAMINGO_ARRIVALS=/abs/path/arrivals.jsonl
  python abides.py -c flamingo -n 1024 -i 1 -w fixed   # 配合 WB_WT_FLAMINGO_REPORT=120s 拿全分布

输出每行：{"iter":1,"client":37,"t":<仿真时刻,秒,相对纪元>}
分析：tools/calibrate.py
幂等。
"""
import os
import sys

TARGET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "agent", "flamingo", "SA_ServiceAgent.py")

MARKER = "[WB-ARR]"
ANCHOR = '                bench.record_arrival("report_vectors", currentTime, expected_total=self.num_clients)\n'

SNIPPET = '''                _wb_arr = os.environ.get("FLAMINGO_ARRIVALS")  # [WB-ARR]
                if _wb_arr:
                    with open(_wb_arr, "a", encoding="utf-8") as _f:
                        _f.write('{"iter": %d, "client": %d, "t": %.6f}\\n'
                                 % (int(self.current_iteration), int(sender_id),
                                    float(currentTime.value) / 1e9))
'''


def main():
    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    if MARKER in src:
        print("ALREADY_PATCHED")
        return 0

    if src.count(ANCHOR) != 1:
        print(f"ERROR: anchor matched {src.count(ANCHOR)} times", file=sys.stderr)
        return 1

    src = src.replace(ANCHOR, ANCHOR + SNIPPET)

    with open(TARGET + ".orig2", "w", encoding="utf-8") as f:
        f.write(open(TARGET, "r", encoding="utf-8").read())
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"PATCHED arrivals probe -> {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
