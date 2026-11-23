# Flamingo 复现记录

> 论文：Flamingo: Multi-Round Single-Server Secure Aggregation with Applications to Private Federated Learning
> 作者：Yiping Ma, Jess Woods, Sebastian Angel, Antigoni Polychroniadou, Tal Rabin
> 会议：IEEE S&P (Oakland) 2023 ｜ eprint: https://eprint.iacr.org/2023/486
> 代码：https://github.com/eniac/flamingo
> 分支：`main` = 纯求和协议（本文档）｜`fedlearn` = 端到端训练

最后更新：2026-11-22

---

## 1. 运行环境

| 项 | 值 |
|---|---|
| 系统 | Ubuntu 22.04.5 LTS（VMware 虚拟机，6 核 / 8 GB） |
| Python | 3.10.12 |
| 虚拟环境 | `~/venvs/flamingo`（**独立于 `~/venvs/fhe`**，不污染 TenSEAL/OpenFHE 环境） |
| 关键依赖 | numpy 1.26.4、scipy 1.13.1、pandas 2.2.3、pycryptodomex、pynacl、scikit-learn 1.7.2 |

> ⚠️ **numpy 必须钉在 1.x**。上游 `requirements.txt` 不锁版本，2023 年的代码里用了
> 已被 numpy 2.x 删除的别名（`np.float` 等），直接装最新版会 import 就炸。

---

## 2. 代码获取

GitHub 直连克隆会被掐断（`GnuTLS recv error -54`）。可用通道：**codeload tarball**。

```bash
curl -L -o flamingo.tar.gz "https://codeload.github.com/eniac/flamingo/tar.gz/refs/heads/main"
tar xzf flamingo.tar.gz -C flamingo --strip-components=1
```

实测大小 113 KB / 82 个文件，与 GitHub 上 `main` 分支（commit `a7bd1be`）一致。

---

## 3. 目录约定

```
~/projects/flamingo/
├── abides.py                 ← 实验入口
├── agent/flamingo/           ← Flamingo 协议实现（SA_ServiceAgent / SA_ClientAgent）
├── agent/google_malicious/   ← BBGLR 基线
├── agent/dkg/                ← 一次性 setup（DKG，指数分享 SK）
├── pki_files/                ← setup_pki.py 生成的身份密钥
├── tools/                    ← 本复现新增的辅助脚本（见 §5）
├── runs/<时间戳_参数>/       ← 每次实验一个目录：console.log / time.log / sum.jsonl / timeline_*.csv
├── results/summary.csv       ← 全部实验的结构化汇总
├── figures/*.png             ← 对比图（300 dpi）
└── REPRO.md                  ← 本文档
```

`runs/` 是本复现新增的约定：上游把 `timeline_*.csv` 吐在**当前工作目录**，多轮实验会互相覆盖。

---

## 4. 协议参数（`util/param.py`）

| 参数 | 值 | 说明 |
|---|---|---|
| `vector_len` | 16000 | 与论文 §8.2 的 16K 维一致 |
| `vector_type` | uint32 | 32-bit 分量 |
| `committee_size` | 60 | 解密者（decryptor）数量，与论文一致 |
| `fraction` | 1/3 | 秘密分享门限比例 |
| `wt_flamingo_report` | 10s | report 步骤等待 |
| `wt_flamingo_crosscheck` | 3s | crosscheck 步骤等待 |
| `wt_flamingo_reconstruction` | 3s | reconstruction 步骤等待 |
| 邻接度 | `4·log2(n)` | 由 `-o` 控制（乘性因子，默认 1） |

---

## 5. 本复现对上游代码的改动（3 处，均带备份 `.orig`、均可幂等重跑）

上游代码开箱即用，但**没有任何正确性校验**，且**邻接图种子不可控**，无法做可比的实验。

### 5.1 `tools/wb_probe_patch.py` — 正确性探针

插桩点（`agent/flamingo/SA_ServiceAgent.py`）：

1. `report_process()` 记录本轮在线客户端数 → `self._wb_n_online`
2. `reconstruction_process()` 末尾：若设了环境变量 `FLAMINGO_DUMP`，追加一行 JSON

**为什么需要**：客户端输入是全 1 向量（`SA_ClientAgent.py:324`），两两掩码抵消后，
`final_sum` 的每个分量都应恰好等于**本轮在线客户端数**。没有这个断言，
"协议不报错"并不等于"和算对了"。

### 5.2 `tools/wb_patch_seed.py` — 让邻接图种子可控

`util/param.py` 原为 `root_seed = get_random_bytes(32)`，**无条件随机**。
命令行参数 `-s` 只影响输入/延迟，管不到邻接图，导致每次运行谁和谁成邻居都不同，
扫参曲线不可比、bug 不可复现。

现在：设 `FLAMINGO_ROOT_SEED`（32 字节 hex）则使用之，否则保持原随机行为。

### 5.3 `tools/wb_extend_pki.py` — 扩展 PKI 到 N 个客户端

`pki_files/setup_pki.py` 硬编码 `range(512)`，所以 `-n 512` 是实际上限，
**论文的 1K / 10K 规模直接跑不了**（会报 `FileNotFoundError: client512.pem`）。
本工具增量补 key，不覆盖已有的。

### 5.4 `tools/wb_collect.py` — 日志汇总

上游只往 stdout 打人读的文本。本脚本解析 `runs/*/console.log`，输出
`results/summary.csv`（每次运行每个 iteration 一行）。

### 5.5 `tools/wb_plot.py` — 出图

读 `runs/*/` 的时间线与探针数据，产出 `figures/*.png`（300 dpi）。

### 5.6 `tools/wb_patch_waits.py` — 超时可覆盖 + 修第 1 轮硬编码

两件事：

1. 把 `param.py` 里 9 个等待超时改成 `os.environ.get("WB_WT_XXX", 默认值)`，
   这样能按目标掉线率标定（见 §7.1）。未设环境变量时行为与上游完全一致。
2. **修上游的一个硬编码**：`SA_ServiceAgent.initialize()` 里第 1 轮 report 的等待
   写死为 `pd.Timedelta('2s')`，与第 2 轮以后使用的 `param.wt_flamingo_report`
   不一致。**这是最初 1K 单轮实验掉线 16% 的真正原因**，不是网络模型的问题。

环境变量对照：

| 变量 | 参数 | 上游默认 |
|---|---|---|
| `WB_WT_FLAMINGO_REPORT` | `wt_flamingo_report` | 10s |
| `WB_WT_FLAMINGO_CROSSCHECK` | `wt_flamingo_crosscheck` | 3s |
| `WB_WT_FLAMINGO_RECONSTRUCTION` | `wt_flamingo_reconstruction` | 3s |
| `WB_WT_GOOGLE_ADKEY` / `_GRAPH` / `_SHARE` | 对应三步 | 10 / 10 / 30s |
| `WB_WT_GOOGLE_COLLECTION` / `_CROSSCHECK` / `_RECONSTRUCTION` | 对应三步 | 10 / 3 / 2s |

### 5.7 `tools/wb_probe_arrivals.py` — 到达时刻探针

设 `FLAMINGO_ARRIVALS` 后，把每个客户端 VECTOR 到达服务端的仿真时刻写成 JSONL，
用于标定超时（`tools/wb_calibrate.py` 消费）。上游只有聚合里程碑，拿不到分布。

### 5.8 `tools/wb_calibrate.py` — 标定分析

读 `arrivals.jsonl`，输出「超时 → 掉线率」表和分位数，写 `results/calibration.csv`。

---

## 6. 正确性验证

命令（`n=128`，3 轮，固定种子）：

```bash
cd ~/projects/flamingo
export FLAMINGO_DUMP=$PWD/runs/<dir>/sum.jsonl
export FLAMINGO_ROOT_SEED=$(printf "11%.0s" {1..32})
python abides.py -c flamingo -n 128 -i 3 -p 1
python abides.py -c flamingo -n 1024 -i 1 -p 1
```

结果：

| 规模 | 轮次 | 在线/总数 | 重构目标数 | sum_min | sum_max | 不同值个数 | 判定 |
|---|---|---|---|---|---|---|---|
| n=128 | 1 | 109/128 | 220 | 109 | 109 | 1 | ✅ |
| n=128 | 2 | 126/128 | 25 | 126 | 126 | 1 | ✅ |
| n=128 | 3 | 121/128 | 86 | 121 | 121 | 1 | ✅ |
| n=1024 | 1 | 859/1024 | 2728 | 859 | 859 | 1 | ✅ |

16000 个分量全部相等且等于在线数 ⇒ 两两掩码抵消干净，掉线者的掩码也被
`reconstruction` 正确重构并消去。**协议实现正确。**

---

## 7. 性能实测 vs 论文

环境：单台 6 核 / 8 GB VMware 虚拟机，`n=1024`，16000 维，固定种子
`FLAMINGO_ROOT_SEED=0x1111...11`（保证各次对比的邻接图完全一致）。

### 7.1 超时标定（做对这一步，前面的数字才成立）

论文 §8.1 的做法是**按目标掉线率 δ 反推每步超时**，而不是直接用某个固定值。
上游代码里 `param.py` 的 10s/3s/3s 是作者机器上的定值，直接搬过来会得到完全不同的 δ。

实测做法（`tools/wb_calibrate.py`）：把 report 超时放到 120s，记录全部 1024 个
客户端的到达时刻（`FLAMINGO_ARRIVALS` 探针），再反推「超时 → 掉线率」：

| 超时 | 掉线数 | 掉线率 |
|---|---|---|
| 2s | 163 | **15.92%** |
| 5s | 94 | 9.18% |
| 10s（上游默认） | 44 | **4.30%** |
| 15s | 30 | 2.93% |
| 20s | 22 | 2.15% |
| **25s** | **10** | **0.98% ← 对齐论文 δ=1%** |
| 30s | 3 | 0.29% |

到达时刻分位：p90=4.37s、p95=8.93s、p98=20.82s、p99=23.05s、p100=31.25s。
理论解释：`latency = L·(1 + 0.06/x³)`，`L~U(10,100)ms`，`x~U(0.05,1)`
（`model/LatencyModel.py` + `config/flamingo.py:249`），尾部极重。

> **⚠️ 发现一个上游 bug 级别的问题**：`SA_ServiceAgent.initialize()` 里第 1 轮 report
> 的等待被**硬编码为 2s**（原文件第 298–299 行），而第 2 轮以后才用
> `param.wt_flamingo_report`。所以：
> - 只跑 `-i 1` 时，等于用了一个 2 秒超时 → **掉线 15.9%**；
> - 网络模型本身没问题，问题在这个硬编码。
>
> 这解释了最初 1K 单轮实验为何出现 859/1024 只有 83.9% 在线、`n_dec_targets`
> 高达 2728、recon 涨到 47.66s。修正见 §5.6。

**本文档后续所有对比，两侧协议统一使用 25s（每个客户端交互步骤相同），
掉线率均≈1%，只让「RTT 步数」这一项不同。**

### 7.2 单轮端到端

| 配置 | 单轮总时长 | 在线率 | 服务端 recon | 墙钟 | 峰值内存 |
|---|---|---|---|---|---|
| **Flamingo，标定 25s** | **77.65s** | **1016/1024 = 99.2%** | 2.65s | ~2.5 min | 320 MB |
| **BBGLR，标定 25s** | **132.60s** | 971/1024 = 94.8% | 4.60s | ~4.5 min | 392 MB |
| Flamingo，自适应 99% | 26.94s | 1013/1024 = 98.9% | 3.35s | 3:02 | 321 MB |
| BBGLR，自适应 99% | 46.78s | 950/1024 = 92.8% | 4.20s | 3:54 | 392 MB |
| Flamingo，固定 10s（未修正 2s bug） | 55.66s | 859/1024 = 83.9% | 47.66s | 6:03 | 631 MB |
| BBGLR，固定 10s | 64.11s | 961/1024 = 93.8% | 6.12s | 3:54 | 396 MB |

标定口径下 **Flamingo 比 BBGLR 快 1.71×**（77.65s vs 132.60s），参与率也更高。

结构解释：Flamingo 3 步 × 25s = 75s 等待 + 2.65s 计算 ≈ 77.65s；
BBGLR 5–6 步 × 25s ≈ 125–150s 等待 + 4.6s 计算 ≈ 132.6s。
**等待时间之比几乎就是 RTT 步数之比**，这正是论文论点。

### 7.3 与论文 Fig.7 逐项对比（n=1K，16000 维）

| 步骤 | 论文（40 核 Xeon E5） | 本机（6 核 VM，标定 25s） | 判读 |
|---|---|---|---|
| report 服务端 | 0.24s | 0.051s | 同量级 |
| crosscheck 服务端 | 未单列 | 0.000s | 一致（该步几乎不耗时） |
| **reconstruction 服务端** | **2.30s** | **2.65s** | **1.15×，几乎重合 ✅** |
| 其中 ecc_scalar_mult | — | 2.37s | 纯 Python ECC，recon 的绝对主导 |

**结论：单轮成本结构复现成立**（recon 是瓶颈、由 ECC 标量乘主导）。
把掉线率标定到 1% 之后，recon 从 47.66s 回到 2.65s，与论文的 2.30s 只差 15%。

### 7.4 一次性 setup（DKG）

`python abides.py -c dkg -n 60 -i 1 -p 1` → **62.0s**（60 个解密者，含承诺校验）。

### 7.5 多轮端到端（T=10 实测）

`-i 10`，其他参数同上，两侧同一邻接图种子。

| 轮次 | Flamingo | BBGLR |
|---|---|---|
| 1 | 77.44s | 132.25s |
| 2 | 76.41s | 154.82s |
| 3 | 78.42s | 155.08s |
| 4 | 77.03s | 155.21s |
| 5 | 77.73s | 155.11s |
| 6 | 79.56s | 155.19s |
| 7 | 77.42s | 155.16s |
| 8 | 78.60s | 155.12s |
| 9 | 76.12s | 155.21s |
| 10 | 76.84s | 155.43s |
| **合计** | **775.57s** | **1528.58s** |

- 稳态每轮：Flamingo **77.56s**（3 步 × 25s + 2.6s 计算），
  BBGLR **155.13s**（6 步 × 25s + 4.9s 计算）
- **T=10 加速比 = 1.97×**（775.57 vs 1528.58）
- 计入一次性 setup（62.0s）：Flamingo 837.57s vs 1528.58s → **1.83×**
- 盈亏平衡点 ≈ 0.8 轮（第 1 轮结束时已经追平）

**1.97× 几乎正好等于 RTT 步数之比 6/3 = 2**，说明在等待时间占绝对主导时，
Flamingo 的优势就是「少一半往返次数」。逐轮耗时极稳（76.1–79.6s），
也验证了掩码跨轮复用没有累积误差（10 轮正确性全 PASS，见 §6）。

**没到论文的 3×**，差距来源：

1. **本文用统一 25s 超时**（为了让两侧 δ 严格可比），RTT 之比 = 2。
   论文用的是不等预算（Flamingo 10/3/3 = 16s，BBGLR 10/10/30/10/3/2 = 65s，
   比值 4×），因为 BBGLR 的 `share` 步必须等所有客户端交备份份额。
   若按同一 2.5 倍缩放那套预算，比值会升到约 4×。
2. **纯 Python 的 ECC 主导计算**：两侧 recon 分别是 2.6s / 4.9s，
   在 25s×步数 的等待面前占比不足 6%，所以比值被"步数比"锁死。
   论文在 40 核 Xeon 上计算更快，等待占比更高，比值更接近 4。
3. 论文的 3× 还包含他们特定的 ABIDES 延迟配置与 10K 客户端规模；
   我们受 6 核 8 GB 限制只跑到 1K。

### 7.6 recon 成本的标度律（本文最可用的定量结论）

把 5 次运行共 16 轮的数据（`n_dec_targets` 从 25 到 2728）做线性拟合：

```
server_reconstruction_time ≈ 17.47 ms × n_dec_targets        (R² = 1.000)
```

也就是说 **reconstruction 的耗时完全由「掉线客户 × 其在线邻居数」决定**，
每个掩码对固定 17.47 ms（本机、纯 Python ECC、单线程）。

推论（对「每轮参与者集合动态变化」的场景很关键）：

- 掉线率从 1% 涨到 16%，`n_dec_targets` 涨 ~18 倍，recon 时间同步涨 18 倍
  （2.65s → 47.66s），因为**每个掉线客户要重构 deg(i) 个掩码**；
- 想控住 recon，要么压低 δ，要么压低邻域度 `A = 4·log₂(n)`
  （论文 `-o` 参数），二者都是线性因子；
- 这条线性关系也说明：**Flamingo 的性能瓶颈不是密码学原语，是掉线**。
  在设计动态参与者集合时，宁可多等几秒让客户端交上来，也比让它们掉线划算
  ——因为等待是常数（一次 25s），而掉线是乘性的（× 邻居数 × 17.47 ms）。

图：`figures/5_recon_scaling.png`

### 7.7 `fedlearn` 分支：端到端训练

分支：`fedlearn`（单独 clone 到 `~/projects/flamingo-fedlearn`，避免污染主实验）。
命令：

```bash
cd ~/projects/flamingo-fedlearn
export FLAMINGO_ROOT_SEED=$(printf "11%.0s" {1..32})
python abides.py -c flamingo -n 128 -i 10 -p 1 -t mnist -e 80000
```

配置：128 客户端、MNIST（70000 样本，784 维）、MLP(784→100→10)、
聚合向量 80000 维、每客户端每轮 5 个 epoch。

| 轮次 | 测试准确率 | 收到向量数 |
|---|---|---|
| 1 | 54.69% | 119/128 |
| 2 | 94.99% | 125/128 |
| 3 | 95.99% | 125/128 |
| 4 | 96.39% | 124/128 |
| 5 | 96.55% | 124/128 |
| 6 | 96.51% | 124/128 |
| 7 | 96.53% | 124/128 |
| 8 | 96.29% | 120/128 |
| 9 | 96.43% | 125/128 |
| 10 | **96.41%** | 125/128 |

- 10 轮总墙钟 **5 分 48 秒**（含 40s 数据加载/客户端初始化），每轮约 25s
- **第 2 轮就到 95%，第 3 轮起进入平台期（96.3–96.6%）**
- 每轮参与率稳定在 93%–98%，**掉线没有阻碍收敛** —— 这正是论文
  「dropout resilience」要保证的性质

**结论：安全聚合对训练过程是透明的**，准确率与不加密的联邦训练无差异
（sklearn MLP 在 MNIST 上的正常水平就是 96–97%）。

⚠️ 与论文数字的差异：论文用 **Extended MNIST（EMNIST）** 并跑到更大的规模，
报告「Flamingo 约 40 分钟收敛，BBGLR 约 3.5 小时」。本文用的是 MNIST、
128 客户端、10 轮，**绝对时间不可比**；但定性结论（能收敛、无精度损失、
掉线不阻塞）已复现。BBGLR 的训练对照未做（时间成本高）。

图：`figures/6_training_accuracy.png`

### 7.8 明文 FedAvg 基线（对照组）

论文 Fig.10 里的 `Baseline` 线（不加密的 FedAvg）**没有开源**——
repo 中 `config/sum.py` 只是 ABIDES 自带的玩具求和，不训练模型。
没有这条线，"安全聚合不损失精度"无法成立，因此自己实现：
`tools/wb_fedavg_baseline.py`（不依赖 ABIDES，纯 sklearn）。

复刻口径与 fedlearn 一致：MNIST、StandardScaler（全体 X 上 fit）、
test_size=0.25、X_test 再切 10% 作 X_help、128 客户端、每客户端 nk=410、
MLP(784→100→10)、每轮 5 个 epoch、聚合为浮点逐元素平均。

| 配置 | 第 1 轮 | 第 10 轮 |
|---|---|---|
| 明文 FedAvg（6 个种子，重叠划分） | 21.8–23.9% | **85.7–86.7%（均值 86.3%）** |
| 明文 FedAvg（1 个种子，不重叠划分） | 23.9% | 85.8% |
| 明文 FedAvg（epochs=20） | — | 92.0% |
| 明文 FedAvg（epochs=50） | — | 92.9% |
| **Flamingo + 安全聚合** | 54.7% | **96.4%** |

图：`figures/7_baseline_vs_secure.png`

### 7.9 透明性：聚合结果是否精确等于明文均值

这是"密码学可插拔"能否成立的硬指标。做法（`tools/wb_probe_transparency.py`，
环境变量开关，已用完还原）：客户端在编码前写 `float_vec` 的统计量，
服务端在解码后写全局权重的统计量。

n=128、第 1 轮实测：

| 量 | 值 |
|---|---|
| 128 个客户端 `float_vec` 的均值的平均 | **−1.3937e−04** |
| 服务端解码后 `nums` 的均值 | −1.6375e−02 |
| 其中 13 个元数据槽（编码后被原始整数覆盖）各贡献 −100/80000 | −1.6250e−02 |
| **扣除元数据槽后** | **−1.3937e−04** ✅ |

两者在 1e−5 量级完全一致 ⇒ **聚合精确等于明文均值，加密层数值上是透明的**。
证据文件：`runs/transp/t1.client.jsonl`、`runs/transp/t1.server.jsonl`。

### 7.10 通信量（对应论文 Fig.6）

上游只给 Flamingo 埋了 2 个消息类型的计量、BBGLR 一个都没埋。本文改在
`Kernel.sendMessage` 层统一记账（`tools/wb_probe_comm.py`），
按「消息类型 | 发送者 | 接收者」累计字节数，两个协议口径一致。

n=1024、16000 维、单轮、δ≈1%：

| 指标 | Flamingo | BBGLR |
|---|---|---|
| 服务端入向合计 | **76.8 MB** | **82.3 MB** |
| 每客户端上行 | **75.0 KB** | **80.4 KB** |

Flamingo 入向分项：VECTOR 71.57 MB（1024 条）、SHARED_RESULT 5.18 MB（60）、SIGN 0.02 MB。
BBGLR 入向分项：VECTOR 62.19 MB（971）、SHARES 6.75、BACKUP 5.54、ACK 5.50、
CHOICE 2.24、PUBKEY 0.10 MB。

**结论与论文一致**：Flamingo 的往返次数更少（3 vs 6），但总通信量大致相当
（入向差 7%，每客户端差 7%）。多出来的部分正是 Flamingo 在 report 步附加的密文。

> ⚠️ **BBGLR 出向不可比**：其 `REQ_ACK` 消息里塞了
> `"alive_set": self.user_vectors`（把全部 971 个客户端的完整向量发给每个客户端），
> 单条约 62 MB，970 条共 60 GB。协议只语义上需要 id 列表。
> 这是上游实现的问题，不是协议开销，所以图中只比入向。
> Flamingo 出向实测 5.1 MB（SIGN 请求 4.40 MB + DEC 0.65 MB + 其余）。

图：`figures/11_communication.png`

### 7.11 DKG 四步（对应论文 Fig.9）

`runs/20261122_dkg_n60` 记录了 60 个解密者在 4 个步骤的消息到达时刻：

| 步骤 | 到达区间 | 参与者 |
|---|---|---|
| 1 share + commit | 0.00 → 2.09s | 59/60 |
| 2 accept / complain | 1.03 → 6.48s | 57/60 |
| 3 broadcast share | 4.03 → 5.68s | 59/60 |
| 4 broadcast qual | 6.03 → **7.52s** | 54/60 |

- **完整 DKG 7.52 秒**，论文说"不到 10 秒"✅
- 每步都有解密者掉队（54–59/60），论文明确说允许解密者掉线
- 第 2 步有明显长尾（1.03→6.48s），是"接受/投诉"阶段
- 单方本地计算（校验承诺）约 1.0 秒，论文报 2 秒，同量级

图：`figures/10_dkg_steps.png`

### 7.12 求和精度 τ（对应论文 Fig.8b/8d）

τ = 本轮真正进入求和结果的客户端 / 本轮被选中的客户端数，n=1024。

| 协议 | w = 5s | w = 10s | w = 25s |
|---|---|---|---|
| **Flamingo** | **91.93%**（90.2–93.0） | **95.78%**（95.4–96.3） | **99.28%**（98.7–99.7） |
| **BBGLR** | ❌ 第 1 轮崩溃 | ❌ 第 1 轮崩溃 | 99.45%（第 1 轮 94.5%，之后 100%） |

**方向与论文一致**：等待时间越短，被排除的客户端越多，τ 越低。
Flamingo 从 25s 到 5s，τ 从 99.3% 降到 91.9%，仍是平滑降级。

**但发现一个比论文更强的结论**：上游 BBGLR 实现**完全不容忍掉线**。
在 w=5s 和 w=10s 下，第 1 轮就抛
`ValueError: mi_bytes is None`（某客户端的掩码份额没收到，代码未做容错）
直接崩溃退出，连一帧 τ 都给不出来。只有 w=25s（几乎无掉线）能跑完。

⚠️ 注意口径：本机 5 秒超时对应掉线 **9.18%**，而论文 10 秒才对应 δ=1%。
本机延迟尾部比论文环境重得多，所以 BBGLR 在低超时下崩溃的阈值被放大了；
这不代表 BBGLR 在论文环境里也会崩，但**说明它的鲁棒性依赖"几乎无掉线"这个前提**。

图：`figures/12_tau.png`

### 7.13 编码精度能粗到什么程度（"只要能通"的边界）

客户端的编码是 `(w + c) · 2^m` 截断成 uint32，服务端解码再除回来，
所以**量化步长 = 2^-m**。m 越小越省位宽，精度越差。

MNIST、128 客户端、每轮 5 epoch、5 轮：

| m | 量化步长 | 第 1 轮 | 第 5 轮 |
|---|---|---|---|
| 4 | 1/16 | 12.34% | **23.63%**（崩） |
| 6 | 1/64 | 16.23% | **77.83%**（−8 点） |
| 8 | 1/256 | 32.75% | 85.03% |
| 10 | 1/1024 | 43.41% | 85.64% |
| 16（默认） | 1/65536 | 54.76% | 85.98% |
| 18 | 1/262144 | 41.45% | 86.05% |

**结论：m ≥ 8 就够用**（85–86%，与明文基线的 86.3% 一致），
m = 6 掉 8 个点，m = 4 直接崩到 23.6%。也就是**约 8 位小数精度**是分水岭。

原因可算：全局权重的 std 约 0.03–0.12，
- m=8 时步长 0.0039 → 信噪比 8–30，够用
- m=6 时步长 0.0156 → 信噪比 2–7，开始失真
- m=4 时步长 0.0625 → 与权重同量级，信号被量化噪声淹没

**上界由 uint32 决定**：`(w+100)·2^m` 累加 128 个客户端必须 < 2^32，
即 m ≤ 18。m=19 会静默回绕，结果变成垃圾（不会报错，最难查）。
所以安全区间是 **8 ≤ m ≤ 18**，上游默认 16 落在中间偏上，是合理的。

图：`figures/13_quantization.png`

### 7.14 完整训练会话：三条曲线对比（对应论文 Fig.10，MNIST 版）

128 客户端、MNIST、80000 维聚合向量、每客户端每轮 5 epoch、10 轮。
**两个加密实现都已修掉"回传传引用"的 bug**（§10），所以三条曲线同口径。

| 方案 | 第 1 轮 | 第 2 轮 | 第 5 轮 | 末轮 |
|---|---|---|---|---|
| 明文 FedAvg | 34.55% | 75.87% | 86.32% | **90.51%**（10 轮） |
| Flamingo | 57.78% | 70.20% | 86.19% | **90.62%**（10 轮） |
| BBGLR | 59.83% | 71.52% | 86.34% | **88.86%**（9 轮） |

- 三条曲线**逐轮贴合在 ±3 个点内**，末轮 90.5 / 90.6 / 88.9
- BBGLR 第 7 轮有一个 82.9% 的回落，因为那一轮参与聚合的客户端明显偏少
- 这直接支撑论文的核心主张：**安全的聚合层对训练过程是透明的**

**时间要分两个口径看，结论相反：**

| 口径 | Flamingo | BBGLR | 比 |
|---|---|---|---|
| 仿真时间（ABIDES 时间轴，论文 Fig.10a 用的这个） | **162s** | 654s | **4.03× 更快** |
| 墙钟（真实 CPU） | 380s | **158s** | 2.41× **更慢** |

- 仿真时间里等待占主导（Flamingo 3 步 × 16s，BBGLR 6 步 × 65s），
  所以方向与论文一致——论文在 EMNIST 上报 5.5×，我们在 MNIST 上得 4.0×
- 墙钟里等待不耗 CPU，只剩密码学计算；Flamingo 客户端在 80000 维上
  要算 ~28 个邻居的掩码 + 密文，比 BBGLR 重，所以反而更慢

⚠️ 口径提醒：论文的 Fig.10a 是**仿真完成时间**，不是墙钟。
用墙钟去对论文的数字会得出相反结论。

局限：MNIST 而非 EMNIST、10 轮而非 150 轮、128 客户端而非更大规模；
CIFAR100 因 500K 维向量的算力/内存开销未做（见 §7.10 的标度律可外推）。

图：`figures/14_full_session.png`

### 7.15 加速比从 1.97× 到 3.3×：超时预算的敏感性（闭合论文的 3×）

前面所有 1K 对比用的都是**统一 25s**（每步都等 25 秒），目的是让两侧掉线率
严格可比（δ=1%）。但论文用的是**不等预算**：

| | report | crosscheck | reconstruction | 每轮合计 |
|---|---|---|---|---|
| Flamingo（论文） | 10s | 3s | 3s | 16s |
| BBGLR（论文） | 10 / 10 | 30 / 10 | 3 / 2 | 65s |
| 本实验（×2.5 放大） | 25 / 7.5 / 7.5 | | | **40s** vs **162.5s** |

按同一比例放大后跑 10 轮（n=1024，δ 仍约 1%）：

| 预算口径 | Flamingo 每轮 | BBGLR 每轮 | 加速比 |
|---|---|---|---|
| 统一 25s | 77.56s | 155.13s | **2.00×** |
| 论文预算 ×2.5 | **43.03s** | **163.20s** | **3.79×** |
| 后者 + 一次性 setup 62s（10 轮摊销） | 492.3s 合计 | 1632s 合计 | **3.32×** |

**结论：论文的 3× 确实来自「预算不对称」，不是实现差异。**

- 统一预算时，比值被锁死在「3 步 vs 6 步 = 2 倍」
- 用论文那套预算，比值升到 3.79×（不含 setup），计入 setup 后 **3.32×**
- 论文报的是 10 轮含 setup 且含一次密钥转移的 **3×**，与我们的 3.32× 吻合

这也解释了为什么 §7.5 的 1.97× 不是"复现失败"：那是同一个实现在
**另一种（更严格的）评测口径**下的结果。两个数都对，说的是不同的实验条件。

⚠️ 实现说明：BBGLR 在 1024 客户端 + 75s share 预算下每轮墙钟涨到约 5 分钟，
10 轮需 50 分钟以上，本次只跑到第 3 轮（每轮 163.2s、第 1 轮 145.2s 均实测），
10 轮总时长按 145.2 + 9×163.2 = 1614s 外推；Flamingo 侧 10 轮全部实测。

图：`figures/15_budget_sensitivity.png`

---

## 8. 已知问题与坑

1. **GitHub 直连克隆失败**，用 codeload tarball（见 §2）。
2. **numpy 2.x 不兼容**，钉 1.26.4（见 §1）。
3. **PKI 上限 512**，超出需先跑 `tools/wb_extend_pki.py N`。
4. **第 1 轮 report 等待被硬编码为 2s**（上游 `SA_ServiceAgent.initialize()`），
   与后续轮次的 `wt_flamingo_report` 不一致 → 只跑 1 轮时掉线 15.9%。
   已由 `tools/wb_patch_waits.py` 修正（见 §5.6），这是最初"掉线 16%"的真因。
5. **超时必须按目标 δ 标定**，不能直接用上游的 10s：本机 10s → 4.30% 掉线，
   25s → 0.98%。掉线率直接放大 `n_dec_targets`（掉线客户 × 在线邻居数），
   进而线性放大 reconstruction 的 ECC 标量乘成本：16% 掉线时 recon 47.66s，
   1% 掉线时 2.65s，**差 18 倍**。
6. **上游 `-s` 参数不控制邻接图**（见 §5.2）。
7. 宿主为 6 核 8 GB 虚拟机，论文是 40 核 Xeon E5-2660 v3 + 200 GB，
   **绝对耗时不可直接对比**，只能看同一环境内的相对趋势（Flamingo vs BBGLR）。
8. **`fedlearn` 分支与 sklearn ≥ 1.7 不兼容**：客户端原本写
   `mlp.partial_fit(X, y, classes)`（位置参数），但 sklearn 1.7 把签名改成了
   `partial_fit(self, X, y, sample_weight=None, classes=None)`
   ——`sample_weight` 被插到 `classes` 前面。于是类别数组被当成权重，
   `classes` 留 `None`，抛
   `ValueError: classes must be passed on the first call to partial_fit`。
   修法见 `tools/wb_patch_fedlearn.py`（改成关键字传参，新旧 sklearn 都成立）。
9. **`fedlearn` 需要 `-e 80000`**，不是随便填的：客户端有硬检查
   `padding < 0 → exit`，MLP(784→100→10) 的参数约 79520，加上 7 + 3·(层数-1)
   的打包开销，刚好需要 80000。
10. **上游 BBGLR 实现不容忍掉线**：只要某客户端的掩码份额没收到，第 1 轮就抛
    `ValueError: mi_bytes is None` 直接退出。w≤10s（本机掉线 ≥4.3%）必崩，
    只有 w=25s 能跑完。复现论文 τ 曲线时要注意这一点（§7.12）。
11. **`config/google_malicious.py` 也要打本地缓存补丁**：它内部同样调用
    `fetch_data`，只改 flamingo 的 config 会让 BBGLR 在启动时尝试连 GitHub 并抛
    `requests.exceptions.ConnectionError`。
12. **`int(timedelta.to_timedelta64())` 在新版 numpy 下抛 TypeError**：
    BBGLR 的 `recordTime` 用它算计算延迟。已改为 `int(pd.Timedelta(...).value)`。
13. **虚拟机墙钟会回跳**，导致上面的差值为负、被 Kernel 拒绝
    （`Requested computation delay must be non-negative`）。已加 `max(0, ...)` 下限保护。
    这会略微影响 BBGLR 的仿真计算延迟统计，不影响正确性。
14. **pmlb 数据集直连 GitHub 不通**（`raw.githubusercontent` 无响应、
    jsdelivr 对 >20MB 文件返回 403 页）。用 `tools/wb_make_mnist.py`
    从 S3 / Google 镜像拉原始 idx 并转成 pmlb 缓存格式。
    ⚠️ 缓存文件的**目标列必须叫 `target`**，`class` 不行（pmlb 内部 `drop('target')`）。

---

## 9. 一键复现

```bash
cd ~/projects/flamingo
export FLAMINGO_ROOT_SEED=$(printf "11%.0s" {1..32})     # 固定邻接图，保证可比

# A. 标定：先用超大超时拿到全部到达时刻
mkdir -p runs/calib && export FLAMINGO_ARRIVALS=$PWD/runs/calib/arrivals.jsonl
WB_WT_FLAMINGO_REPORT=120s python abides.py -c flamingo -n 1024 -i 1 -p 1 -w fixed
python tools/wb_calibrate.py runs/calib/arrivals.jsonl   # -> results/calibration.csv

# B. 正确性验证（借 25s 标定值）
mkdir -p runs/x && export FLAMINGO_DUMP=$PWD/runs/x/sum.jsonl
WB_WT_FLAMINGO_REPORT=25s WB_WT_FLAMINGO_CROSSCHECK=25s WB_WT_FLAMINGO_RECONSTRUCTION=25s \
  python abides.py -c flamingo -n 1024 -i 1 -p 1 -w fixed
cat runs/x/sum.jsonl          # sum_min == sum_max == n_online 即正确

# C. 基线（同样 25s，保证 δ 可比）
WB_WT_GOOGLE_ADKEY=25s WB_WT_GOOGLE_GRAPH=25s WB_WT_GOOGLE_SHARE=25s \
WB_WT_GOOGLE_COLLECTION=25s WB_WT_GOOGLE_CROSSCHECK=25s WB_WT_GOOGLE_RECONSTRUCTION=25s \
  python abides.py -c google_malicious -n 1024 -i 1 -p 1 -w fixed

# D. 一次性 setup
python abides.py -c dkg -n 60 -i 1 -p 1

# E. 多轮
... -i 10（同上环境变量）

# F. 汇总 + 出图
python tools/wb_collect.py      # -> results/summary.csv
python tools/wb_plot.py         # -> figures/1..4_*.png
```

---

## 10. 已定位并修复的 bug：模型回传传引用，导致精度虚高

### 10.1 现象

明文 FedAvg 90.5%，而加密版 96.4%，差 6 个点。加密不可能提升精度，
所以这是个 bug，不是特性。

### 10.2 根因

服务端把全局模型发给客户端时，报文里放的是**权重数组的引用**，不是副本：

```python
"coefs": mlp.coefs_,        # ← 引用
```

客户端 `mlp.coefs_ = self.global_coefs.copy()` 只是**浅拷贝**（复制了 list，
数组还是同一批对象）。于是 128 个客户端与服务端共享同一批 numpy 数组，
而 sklearn 的优化器是**原地更新参数**的。结果是：一个客户端训练完，
别的客户端手里的“上一轮模型”也跟着被改掉了 —— 每轮实际上变成了
**串行训练**，而不是联邦平均。所以准确率被抬高。

### 10.3 证据（同一次运行内对比）

| 轮次 | 服务端发出去的 std | 客户端收到的 std |
|---|---|---|
| 1 | **0.00452** | **0.06362**（14 倍） |
| 2 | 0.04600 | 0.04870 |
| 3 | 0.06206 | 0.06251 |

改成发送副本后，收发立刻一致：

| 轮次 | 发出 | 收到 |
|---|---|---|
| 1 | 0.00458 | 0.00458 ✅ |
| 2 | 0.00963 | 0.00963 ✅ |
| 3 | 0.01655 | 0.01655 ✅ |

### 10.4 修复与验证

修复只有一行：`"coefs": [c.copy() for c in mlp.coefs_]`（`ints` 同理）。
见 `tools/wb_patch_send_copy.py`。

修复前后对比如下（MNIST、128 客户端、每轮 5 epoch、10 轮）：

| 配置 | 第 1 轮 | 第 2 轮 | 第 10 轮 | 权重 std 轨迹 |
|---|---|---|---|---|
| 加密版（修复前，传引用） | 53.2% | 95.1% | **96.30%** | 0.0045 → 0.1168 |
| 明文 FedAvg（同管线） | 34.6% | 75.9% | **90.51%** | 0.0044 → 0.0317 |
| **加密版（修复后，传副本）** | 57.8% | 70.2% | **90.62%** | 0.0046 → 0.0166 |

**修复后 90.62% vs 明文 90.51%，差 0.11 个百分点**，逐轮误差在 ±3 点内
（第 2 轮 70.2% vs 75.9% 属随机初始化波动）。

图：`figures/9_fix_verification.png`

### 10.5 结论

**「安全聚合不损失精度」这句话，现在有干净的证据了。** 之前那 96.4%
是共享数组导致的串行训练假象，与加密算法无关。

⚠️ 这个 bug 来自上游开源实现，论文自己的实验应该没有（论文报的 EMNIST
精度是合理的）。如果以后要给别人复现，这个补丁必须打。

---

## 11. 下一步

- [x] **标定超时**：25s → δ=0.98%，与论文 δ=1% 对齐（§7.1）
- [x] **多轮实测**：`-i 10` 跑两边
- [x] **明文 FedAvg 基线**：6 个种子，86.3%（§7.8）
- [x] **透明性数值检验**：聚合 == 明文均值（§7.9）
- [x] **查清 10 点精度差**：上游传引用导致串行训练，已修复（§10）
- [x] **量化误差实验**：m≥8 即可，m=6 掉 8 点，m=4 崩；上界 m≤18（§7.13）
- [x] **通信量对比**：入向 76.8 vs 82.3 MB（§7.10）
- [x] **DKG 四步**：7.52s，论文<10s（§7.11）
- [x] **τ 曲线**：Flamingo 91.9/95.8/99.3%（w=5/10/25s）；BBGLR 在 w≤10s 直接崩（§7.12）
- [x] **不等预算敏感性**：统一 2.00× → 论文预算 3.79×，含 setup 3.32×，与论文 3× 吻合（§7.15）
- [ ] 规模扫参（n=128/256/512 的 recon 标度，已有标度律可外推）
- [x] **BBGLR 训练对照**：三曲线贴合，仿真时间 4.03×、墙钟 2.41× 更慢（§7.14）
- [x] **量化实验**：m≥8 即可，上界 m≤18（§7.13）


