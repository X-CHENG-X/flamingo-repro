# Flamingo Reproduction Harness

Reproduction of the experimental section of **Flamingo: Multi-Round Single-Server Secure
Aggregation with Client Dropouts** (CRYPTO 2023), on top of the authors' open-source PPFL
codebase, using the ABIDES discrete-event simulator.

This repository contains **patches, measurement tools, and a written record** — not a fork of
the protocol implementation. You apply it to a clean clone of the upstream code.

> **Why patches are necessary.** The upstream code does not run as-is under current library
> versions, and it contains two defects that *change the experimental conclusions*: one makes
> the secure-aggregation variant look ~6 accuracy points better than plaintext FedAvg, and one
> makes the BBGLR baseline crash whenever clients drop out. Both are documented in
> [`docs/FINDINGS.md`](docs/FINDINGS.md) with minimal reproductions.

---

## Contents

```
patches/
  apply_all.py        one-shot, idempotent patch applier (8 rules, --repo / --dry-run)
  pki_extend.py       extend the PKI from the hardcoded 512 keys to N clients
tools/
  calibrate.py        derive the timeout that yields a target dropout rate δ
  verify.py           verify aggregation correctness from sum.jsonl
  make_mnist.py       build a pmlb-compatible MNIST cache (offline, mirror-based)
  fedavg_baseline.py  plaintext FedAvg reference (no ABIDES)
  fedavg_exact.py     bit-exact replica of the upstream client path (+ encoding ablation)
  eval_weights.py     re-evaluate saved global weights independently
  probe_comm.py       transport-level communication accounting for any protocol
  probe_transparency.py   check that the aggregate equals the plaintext mean
  plot_*.py           15 figures (calibration, timing, τ, comms, DKG, accuracy, scaling)
docs/
  REPORT.md           full experimental report (Chinese, academic style)
  REPRO.md            item-by-item reproduction log incl. debugging trails
  FINDINGS.md         the defects, with minimal reproductions
results/
  figures/            15 figures at 300 dpi
  summary.csv         all runs, one row per run
```

---

## Quick start

### 1. Environment

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements.txt
```

Tested with: numpy 1.26.4, pandas 2.2.3, scikit-learn 1.7.2, PyNaCl 1.6.2,
pycryptodomex 3.24.2. **numpy ≥ 2 is not supported** by the upstream time-handling code.

### 2. Get the upstream code

```bash
git clone <upstream-url> ppfl
```

The patches target the layout with `agent/flamingo/`, `agent/google_malicious/`,
`agent/dkg/`, `config/`, `util/param.py` (the two branches used in the paper: `main` for
the summation experiments, `fedlearn` for the training experiments).

### 3. Apply patches

```bash
python patches/apply_all.py --repo ppfl --branch main       # timing experiments
python patches/apply_all.py --repo ppfl --branch fedlearn   # training experiments
python patches/apply_all.py --repo ppfl --branch fedlearn --dry-run   # preview
```

The applier is idempotent: re-running reports `already` and changes nothing. Originals are
saved as `*.bak`.

### 4. Keys and dataset

```bash
python patches/pki_extend.py --repo ppfl --n 1024     # upstream hardcodes 512
python tools/make_mnist.py                            # -> ppfl/data/pmlb/mnist/mnist.tsv.gz
```

### 5. Calibrate the timeout to δ ≈ 1 %

```bash
cd ppfl && mkdir -p runs/calib
FLAMINGO_ARRIVALS=$PWD/runs/calib/arrivals.jsonl \
  WB_WT_FLAMINGO_REPORT=120s python abides.py -c flamingo -n 1024 -i 1 -p 1 -w fixed
python ../tools/calibrate.py runs/calib/arrivals.jsonl
```

### 6. Run a comparison

```bash
export FLAMINGO_ROOT_SEED=$(printf "11%.0s" {1..32})   # fixed graph, comparable runs

WB_WT_FLAMINGO_REPORT=25s WB_WT_FLAMINGO_CROSSCHECK=25s WB_WT_FLAMINGO_RECONSTRUCTION=25s \
  python abides.py -c flamingo -n 1024 -i 10 -p 1 -w fixed

WB_WT_GOOGLE_ADKEY=25s WB_WT_GOOGLE_GRAPH=25s WB_WT_GOOGLE_SHARE=25s \
WB_WT_GOOGLE_COLLECTION=25s WB_WT_GOOGLE_CROSSCHECK=25s WB_WT_GOOGLE_RECONSTRUCTION=25s \
  python abides.py -c google_malicious -n 1024 -i 10 -p 1 -w fixed
```

All timeouts are overridable via `WB_WT_*` environment variables; unset ones fall back to the
upstream defaults, so the code behaves exactly as upstream when you do not set them.

### 7. Verify and plot

```bash
python ../tools/verify.py runs/<dir>/sum.jsonl   # every round must report PASS
python ../tools/plot.py                          # -> figures/
```

---

## Key results

Environment: 6-core VM, 8 GB RAM. Absolute times are **not** comparable to the paper
(40-core Xeon E5-2660 v3); all ratios below are measured within this environment.

| Quantity | Paper | This work | Note |
|---|---|---|---|
| Server reconstruction (1K clients, 16K dim) | 2.30 s | 2.65 s | 89 % of it is pure-Python ECC |
| Server inbound traffic per round | ≈ same | 76.8 MB vs 82.3 MB (BBGLR) | "fewer round trips, similar volume" |
| Per-client uplink | ≈ same | 75.0 KB vs 80.4 KB | |
| DKG (60 decryptors, 4 steps) | < 10 s | 7.52 s | |
| Training accuracy (MNIST, 128 clients) | ≈ plaintext | 90.62 % vs 90.51 % (plaintext) | after fixing the reference bug |
| Speedup, **uniform** timeout (δ matched) | — | **2.00×** | = round-trip ratio 6/3 |
| Speedup, **paper's** asymmetric budget | 3× | **3.79×** (3.32× incl. setup) | consistent with 3× |

Two results are not in the paper:

* **Reconstruction cost scales strictly linearly with the number of dropout-affected mask
  pairs**: `t ≈ 17.47 ms × n_dec_targets`, R² = 1.000 over 16 rounds. The cost is independent
  of the cryptographic primitive and depends only on *dropouts × neighbours*.
* **The encoding precision has a feasible window `8 ≤ m ≤ 18`.** Below m = 8 the training
  accuracy degrades (m = 6 loses 8 points, m = 4 collapses); above m = 18 the uint32
  accumulation overflows **silently**.

> **On the 3× claim.** The speedup is dominated by the *timeout budget*, not by the
> implementation. With every step waiting the same 25 s the ratio is pinned at the 3-vs-6
> round-trip ratio (2×); with the paper's asymmetric budget (Flamingo 16 s/round, BBGLR
> 65 s/round) it rises to 3.79×. **A speedup number without a stated timeout budget is not
> comparable.**

---

## What this repository is *not*

* Not a reimplementation of the protocol — it patches and measures the authors' code.
* Not a security proof: the security and dropout-resilience claims are theorems in the paper;
  this work only checks functional correctness (the aggregate must equal the plaintext sum).
* CIFAR100 was **not** run. Extrapolating the measured scaling law, 500K-dim vectors would need
  ≈ 0.55 s per mask pair, ≈ 3.6 min per round, ≈ 9–10 h for 150 rounds, plus ≈ 80 MB of masks
  per client — beyond this machine. The figure is deliberately omitted rather than estimated.

---

## 中文说明

本仓库是对 Flamingo（CRYPTO 2023）实验部分的复现产物，包含：一份**一键补丁器**
（上游代码在当前依赖下跑不通，且有两个会改变结论的缺陷）、一套**测量与绘图工具**、
以及**完整的实验记录**（`docs/REPORT.md` 为正式报告，`docs/REPRO.md` 为逐项复现过程）。

复现要点：

1. **先标定超时**。上游 `param.py` 里的 10 s 是作者机器上的值，本机同样 10 s 会掉线 4.3%，
   需按 δ≈1% 重新标定为 25 s。注意上游第 1 轮的报告等待被硬编码为 2 s（补丁 R3 已修）。
2. **先修回传缺陷再谈精度**。上游服务端回传全局模型时传数组引用，客户端之间共享权重，
   等价于串行训练，会让加密版精度虚高约 6 个百分点（见 `docs/FINDINGS.md`）。
3. **加速比必须声明超时口径**。统一超时下 2.00×，论文的不等预算下 3.79×，两者都对。
4. 报告所有耗时均在本机测得，绝对值不可与论文的 40 核机器比较。

---

## License and attribution

The protocol implementation, simulation kernel (ABIDES), and all original source files belong
to their respective authors. This repository only contains patches, tooling, and documentation;
it does not redistribute upstream code. See [`NOTICE.md`](NOTICE.md) for the exact list of
modifications and the upstream citation.
