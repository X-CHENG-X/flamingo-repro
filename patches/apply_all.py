#!/usr/bin/env python3
"""
Flamingo 复现补丁集 —— 一键应用。

背景：作者开源的 PPFL 代码库在当前依赖版本下无法直接跑通，且存在两处会
影响实验结论的实现缺陷。本脚本把复现所需的全部改动做成幂等规则，
按顺序应用到一个干净的上游克隆上。

用法：
    python patches/apply_all.py --repo /path/to/ppfl --branch main
    python patches/apply_all.py --repo /path/to/ppfl --branch fedlearn
    python patches/apply_all.py --repo /path/to/ppfl --branch both
    python patches/apply_all.py --repo /path/to/ppfl --branch both --dry-run

规则一览（括号内为文件内标记，用于幂等判断）：

  R1  超时参数化                     (WB-WAIT)    util/param.py
  R2  邻接图种子可控                 (WB-SEED)    util/param.py
  R3  修正第 1 轮硬编码 2s           (WB-WAIT1)   agent/flamingo/SA_ServiceAgent.py
  R4  sklearn partial_fit 关键字传参 (WB-SKLEARN) 4 个 agent 文件
  R5  回传权重改为副本               (WB-COPY)    2 个 service agent
  R6  timedelta->ns 且非负           (WB-NS)      google_malicious / dkg
  R7  数据集走本地缓存               (WB-CACHE)   config/*.py

注意：R5 是本复现发现的**实质缺陷修复**（详见 docs/FINDINGS.md），
不打会导致加密版精度虚高约 6 个百分点。
"""
import argparse
import os
import re
import sys

# ---------------------------------------------------------------- 规则定义

WAIT_NAMES = [
    "wt_flamingo_report", "wt_flamingo_crosscheck", "wt_flamingo_reconstruction",
    "wt_google_adkey", "wt_google_graph", "wt_google_share",
    "wt_google_collection", "wt_google_crosscheck",
    "wt_google_reconstruction",
    "wt_google_recontruction",      # fedlearn 分支里这个变量名少了 s，两处都兼容
]

# 变量名 -> 环境变量（拼写错误的也映射到同一个）
def _env_of(name):
    if name.startswith("wt_flamingo_"):
        return "WB_WT_FLAMINGO_" + name[len("wt_flamingo_"):].upper()
    if name.endswith("recontruction"):
        return "WB_WT_GOOGLE_RECONSTRUCTION"
    return "WB_WT_GOOGLE_" + name[len("wt_google_"):].upper()

SEED_OLD = "root_seed = get_random_bytes(32) "
SEED_NEW = ('root_seed = (bytes.fromhex(os.environ["FLAMINGO_ROOT_SEED"])  # [WB-SEED]\n'
            '             if os.environ.get("FLAMINGO_ROOT_SEED") else get_random_bytes(32))')

ITER1_OLD = ("            self._expected_wakeup_time = currentTime + pd.Timedelta('2s')\n"
             "            self.setWakeup(currentTime + pd.Timedelta('2s'))\n")
ITER1_NEW = ("            # [WB-WAIT1] 上游硬编码 2s，与后续轮次用的 wt_flamingo_report 不一致\n"
             "            self._expected_wakeup_time = currentTime + param.wt_flamingo_report\n"
             "            self.setWakeup(currentTime + param.wt_flamingo_report)\n")

# fedlearn 分支的单行写法
ITER1_ALT_OLD = "        self.setWakeup(currentTime + server_comp_delay + pd.Timedelta('2s'))\n"
ITER1_ALT_NEW = ("        # [WB-WAIT1] 上游硬编码 2s，与后续轮次用的 wt_flamingo_report 不一致\n"
                 "        self.setWakeup(currentTime + server_comp_delay + param.wt_flamingo_report)\n")

RE_PARTIAL_FIT = re.compile(r"partial_fit\(([^()]*?),?\s*self\.classes\)")
RE_SEND_COPY = re.compile(r'"coefs":\s*mlp\.coefs_,(\s*\n\s*)"ints":\s*mlp\.intercepts_,')
RE_TD = re.compile(r"int\(\(dt_protocol_end - startTime\)\.to_timedelta64\(\)\)")
RE_CACHE = re.compile(r"fetch_data\(dataset,\s*return_X_y=True\)")

AGENT_FILES = [
    "agent/flamingo/SA_ClientAgent.py",
    "agent/flamingo/SA_ServiceAgent.py",
    "agent/google_malicious/SA_ClientAgent.py",
    "agent/google_malicious/SA_ServiceAgent.py",
]
SERVER_FILES = [
    "agent/flamingo/SA_ServiceAgent.py",
    "agent/google_malicious/SA_ServiceAgent.py",
]
TD_FILES = [
    "agent/google_malicious/SA_ServiceAgent.py",
    "agent/google_malicious/SA_ClientAgent.py",
    "agent/dkg/SA_ServiceAgent.py",
    "agent/dkg/SA_ClientAgent.py",
]
CONFIG_FILES = ["config/flamingo.py", "config/google_malicious.py"]

BOTH = [AGENT_FILES, SERVER_FILES, TD_FILES, CONFIG_FILES]     # 两分支都有


class Ctx:
    def __init__(self, repo, dry):
        self.repo = repo
        self.dry = dry
        self.applied = []
        self.skipped = []
        self.missing = []

    def path(self, rel):
        return os.path.join(self.repo, rel)

    def read(self, rel):
        p = self.path(rel)
        if not os.path.isfile(p):
            return None
        return open(p, encoding="utf-8").read()

    def write(self, rel, text):
        if self.dry:
            return
        p = self.path(rel)
        with open(p + ".bak", "w", encoding="utf-8") as f:
            f.write(open(p, encoding="utf-8").read())
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)


# ---------------------------------------------------------------- 各条规则

def r1_waits(ctx):
    """把 9 个超时改成可被环境变量覆盖。"""
    rel = "util/param.py"
    src = ctx.read(rel)
    if src is None:
        ctx.missing.append((rel, "R1"))
        return
    if "[WB-WAIT]" in src:
        ctx.skipped.append((rel, "R1", "already"))
        return

    if "import os" not in src.split("\n\n")[0]:
        src = "import os  # [WB-WAIT]\n" + src

    n = 0
    for name in WAIT_NAMES:
        env = _env_of(name)
        pat = re.compile(rf"^{name} = pd\.Timedelta\('([^']+)'\)(.*)$", re.M)
        m = pat.search(src)
        if not m:
            continue
        default, trailing = m.group(1), m.group(2)
        new = f'{name} = pd.Timedelta(os.environ.get("{env}", "{default}"))  # [WB-WAIT]{trailing}'
        src = src[:m.start()] + new + src[m.end():]
        n += 1
    if n == 0:
        ctx.missing.append((rel, "R1"))
        return
    # 顺带修第 1 轮硬编码
    ctx.write(rel, src)
    ctx.applied.append((rel, "R1", f"{n} timeouts"))


def r2_seed(ctx):
    rel = "util/param.py"
    src = ctx.read(rel)
    if src is None:
        ctx.missing.append((rel, "R2"))
        return
    if "[WB-SEED]" in src:
        ctx.skipped.append((rel, "R2", "already"))
        return
    if src.count(SEED_OLD) != 1:
        ctx.missing.append((rel, "R2"))
        return
    ctx.write(rel, src.replace(SEED_OLD, SEED_NEW))
    ctx.applied.append((rel, "R2", "root_seed from env"))


def r3_iter1(ctx):
    rel = "agent/flamingo/SA_ServiceAgent.py"
    src = ctx.read(rel)
    if src is None:
        ctx.missing.append((rel, "R3"))
        return
    if "[WB-WAIT1]" in src:
        ctx.skipped.append((rel, "R3", "already"))
        return

    # main 分支：两行写法
    if src.count(ITER1_OLD) == 1:
        ctx.write(rel, src.replace(ITER1_OLD, ITER1_NEW))
        ctx.applied.append((rel, "R3", "iter-1 wait (2 lines)"))
        return
    # fedlearn 分支：单行写法
    if src.count(ITER1_ALT_OLD) == 1:
        ctx.write(rel, src.replace(ITER1_ALT_OLD, ITER1_ALT_NEW))
        ctx.applied.append((rel, "R3", "iter-1 wait (1 line)"))
        return
    ctx.missing.append((rel, "R3"))


def r4_partial_fit(ctx):
    for rel in AGENT_FILES:
        src = ctx.read(rel)
        if src is None:
            continue
        if "classes=self.classes" in src:
            ctx.skipped.append((rel, "R4", "already"))
            continue
        new, n = RE_PARTIAL_FIT.subn(r"partial_fit(\1,classes=self.classes)", src)
        if n == 0:
            continue
        ctx.write(rel, new)
        ctx.applied.append((rel, "R4", f"{n} call(s)"))


def r5_send_copy(ctx):
    for rel in SERVER_FILES:
        src = ctx.read(rel)
        if src is None:
            continue
        # 已修过（无论有没有标记）都跳过
        if "[WB-COPY]" in src or "c.copy() for c in mlp.coefs_" in src:
            ctx.skipped.append((rel, "R5", "already"))
            continue
        new, n = RE_SEND_COPY.subn(
            r'"coefs": [c.copy() for c in mlp.coefs_],\1'
            r'"ints": [i.copy() for i in mlp.intercepts_],', src)
        if n == 0:
            continue
        new = new.replace(
            "        # Send the result back to each client.\n",
            "        # [WB-COPY] 发送副本：与服务端共享数组会导致串行训练、精度虚高\n"
            "        # Send the result back to each client.\n", 1)
        ctx.write(rel, new)
        ctx.applied.append((rel, "R5", f"{n} site(s)"))


def r6_timedelta(ctx):
    for rel in TD_FILES:
        src = ctx.read(rel)
        if src is None:
            continue
        if "[WB-NS]" in src:
            ctx.skipped.append((rel, "R6", "already"))
            continue
        if not RE_TD.search(src):
            continue
        new = RE_TD.sub("int(max(0, pd.Timedelta(dt_protocol_end - startTime).value))  # [WB-NS]", src)
        ctx.write(rel, new)
        ctx.applied.append((rel, "R6", "timedelta -> ns"))


def r7_cache(ctx):
    for rel in CONFIG_FILES:
        src = ctx.read(rel)
        if src is None:
            continue
        if "[WB-CACHE]" in src:
            ctx.skipped.append((rel, "R7", "already"))
            continue
        new, n = RE_CACHE.subn(
            'fetch_data(dataset, return_X_y=True, local_cache_dir="data/pmlb")  # [WB-CACHE]', src)
        if n == 0:
            continue
        ctx.write(rel, new)
        ctx.applied.append((rel, "R7", f"{n} call(s)"))


RULES = [
    ("R1 超时参数化", r1_waits),
    ("R2 种子可控", r2_seed),
    ("R3 首轮 2s", r3_iter1),
    ("R4 partial_fit", r4_partial_fit),
    ("R5 回传副本", r5_send_copy),
    ("R6 timedelta", r6_timedelta),
    ("R7 数据缓存", r7_cache),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="上游克隆的根目录")
    ap.add_argument("--branch", choices=["main", "fedlearn", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo, "agent")):
        print(f"错误：{repo} 看起来不是 PPFL 仓库（缺 agent/）", file=sys.stderr)
        return 2

    ctx = Ctx(repo, args.dry_run)
    print(f"目标仓库: {repo}")
    print(f"分支: {args.branch}   模式: {'DRY-RUN' if args.dry_run else 'APPLY'}\n")

    for name, fn in RULES:
        fn(ctx)
        print(f"  [{name}] done")

    print("\n--- 已应用 ---" if ctx.applied else "\n--- 无需改动 ---")
    for rel, rule, detail in ctx.applied:
        print(f"  {rule}  {rel}   ({detail})")
    if ctx.skipped:
        print("--- 已存在（幂等跳过）---")
        for rel, rule, detail in ctx.skipped:
            print(f"  {rule}  {rel}")
    if ctx.missing:
        print("--- 未匹配（可能需要人工确认）---")
        for rel, rule in ctx.missing:
            print(f"  {rule}  {rel}")

    print(f"\n合计：应用 {len(ctx.applied)} 处，跳过 {len(ctx.skipped)} 处，未匹配 {len(ctx.missing)} 处")
    if ctx.applied and not args.dry_run:
        print("原文件已备份为 *.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main())
