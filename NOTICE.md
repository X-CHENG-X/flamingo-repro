# NOTICE

## 上游代码归属

本仓库**不包含**上游协议实现与仿真内核的源代码，只包含补丁、工具与文档。
使用前需自行获取上游代码：

- **Flamingo / PPFL**：论文 *Flamingo: Multi-Round Single-Server Secure Aggregation with
  Client Dropouts*（CRYPTO 2023）作者开源的 PPFL 代码库。
- **ABIDES**：*ABIDES: Towards High-Fidelity Neural Market Simulation* 的离散事件仿真内核，
  随上游代码一同分发。

上游代码的著作权归其各自作者所有，遵循其原始许可。本仓库的补丁与工具仅为复现用途，
不改变上游许可。

## 本仓库对上游的修改清单

全部改动均可由 `patches/apply_all.py` 幂等应用，规则编号与文件一一对应。

| 规则 | 文件 | 改动 | 性质 |
|---|---|---|---|
| R1 | `util/param.py` | 9 个等待超时改为可由 `WB_WT_*` 环境变量覆盖（未设置时与上游完全一致） | 可配置化 |
| R2 | `util/param.py` | `root_seed` 可由 `FLAMINGO_ROOT_SEED` 固定（未设置时随机） | 可复现性 |
| R3 | `agent/flamingo/SA_ServiceAgent.py` | 首轮硬编码的 2 s 等待改为 `param.wt_flamingo_report` | **缺陷修复**（见 FINDING-4） |
| R4 | 4 个 agent 文件 | `partial_fit` 改关键字传参 | 依赖兼容（FINDING-5） |
| R5 | 2 个 service agent | 回传全局模型改为发送数组副本 | **缺陷修复**（见 FINDING-1） |
| R6 | 4 个 agent 文件 | `to_timedelta64()` 改 `pd.Timedelta(...).value` 并加非负下限 | 依赖兼容（FINDING-5） |
| R7 | 2 个 config 文件 | `fetch_data` 指定本地缓存目录 | 环境适配（FINDING-5） |

## 未修改的部分

- 协议逻辑、密码学原语、图生成、掩码构造均未改动。
- 仿真内核的时间推进与延迟模型未改动（Kernel 仅在测量时临时插桩，测量后已还原）。

## 引用

```bibtex
@inproceedings{flamingo2023,
  title     = {Flamingo: Multi-Round Single-Server Secure Aggregation with Client Dropouts},
  booktitle = {Advances in Cryptology -- CRYPTO 2023},
  year      = {2023}
}
```
