# 复现中发现的上游实现缺陷

本文件记录复现过程中定位到的五类问题。前两类会**改变实验结论**，后三类属于依赖演进
导致的失效。每类都给出机制、证据与最小复现方式。

---

## FINDING-1 全局模型回传传递数组引用，导致串行训练（严重）

**位置**：`agent/flamingo/SA_ServiceAgent.py`、`agent/google_malicious/SA_ServiceAgent.py`
（两个参考实现都有此问题）

**现象**：加密聚合版本的训练准确率显著高于明文 FedAvg，MNIST 上为 96.3% vs 90.5%。

**机制**：

```python
# 服务端
self.sendMessage(id, Message({... "coefs": mlp.coefs_, "ints": mlp.intercepts_, ...}))

# 客户端
self.global_coefs = msg.body['coefs']
mlp.coefs_ = self.global_coefs.copy()      # list.copy() —— 浅拷贝
```

`list.copy()` 只复制了列表，其中的 numpy 数组仍是同一批对象。因此所有客户端与
服务端共享同一批权重数组；而 scikit-learn 的优化器对参数作**原地更新**。
结果是：任一客户端完成本地训练后，其余客户端持有的"上一轮模型"已被改写，
每轮实际上变成了**串行训练**，等价于把所有客户端的数据合并训练，精度自然虚高。

**证据**（同一次运行内，服务端"发送前"与客户端"收到时"的权重标准差）：

| 轮次 | 服务端发出 | 客户端收到 |
|---|---|---|
| 1 | 0.00452 | 0.06362 |
| 2 | 0.04600 | 0.04870 |
| 3 | 0.06206 | 0.06251 |

改为发送副本后，三轮完全一致（0.00458 / 0.00963 / 0.01655），
准确率同时回落：

| | 修复前 | 修复后 | 明文基线 |
|---|---|---|---|
| 第 2 轮 | 94.9% | 70.2% | 75.9% |
| 第 10 轮 | **96.30%** | **90.62%** | 90.51% |

**修复**：`patches/apply_all.py` 规则 R5

```python
"coefs": [c.copy() for c in mlp.coefs_],
"ints":  [i.copy() for i in mlp.intercepts_],
```

**影响**：不修此缺陷会得出"安全聚合提升精度"的错误结论。若要与明文基线比较精度，
必须先修，否则该比较无效。

**最小复现**：在客户端 `receiveMessage` 与训练前各打印一次权重标准差，
同一次运行内两者不一致即可确认。

---

## FINDING-2 BBGLR 参考实现不具备掉线容错（严重）

**位置**：`agent/google_malicious/SA_ClientAgent.py:receiveMessage`

**现象**：客户端掉线率达到约 4% 以上时，BBGLR 在**第 1 轮**即终止：

```
ValueError: mi_bytes is None.
```

**机制**：某客户端的掩码份额未在等待窗口内到达时，服务端未收集到其 `mi_bytes`，
代码没有对应的容错分支，直接抛出异常退出。

**证据**（n=1024，同一服务器、不同等待时间）：

| 等待 | 掉线率 | 结果 |
|---|---|---|
| 5 s | 9.18% | 第 1 轮崩溃 |
| 10 s | 4.30% | 第 1 轮崩溃 |
| 25 s | 0.98% | 正常，10 轮全部完成 |

**影响**：无法在低超时下取得 BBGLR 的求和精度 τ，也就无法复现论文 Fig.8b/8d 的
对比曲线。本复现的 τ 对比因此只有 BBGLR 在 25 s 下的单点。

**说明**：该阈值与本机延迟分布有关（本机 5 s 即对应 9.18% 掉线，而论文 10 s 才对应
1%）。不能据此断言 BBGLR 在论文环境中同样失效，但可以确定其鲁棒性依赖"近乎无掉线"。

---

## FINDING-3 BBGLR 的 ACK 请求携带全部客户端向量

**位置**：`agent/google_malicious/SA_ServiceAgent.py:collection`

```python
self.sendMessage(id, Message({"msg": "REQ_ACK", ..., "alive_set": self.user_vectors}))
```

`alive_set` 本应是存活客户端的**标识列表**，实际传入的是 `self.user_vectors` 整个字典，
即把 971 个客户端的完整向量（单条约 62 MB）发给每一个客户端，单轮总出向约 60 GB。

**影响**：BBGLR 的出向通信量失去比较意义。本复现的通信量对比只比较了入向。

---

## FINDING-4 首轮报告等待被硬编码为 2 秒

**位置**：`agent/flamingo/SA_ServiceAgent.py:initialize`（两个分支写法不同）

```python
self.setWakeup(currentTime + pd.Timedelta('2s'))     # 后续轮次才用 param.wt_flamingo_report
```

**影响**：只跑单轮（`-i 1`）的实验实际使用 2 s 超时，本机对应掉线率 **15.92%**，
而非参数表里的 10 s。初次复现时观察到的"异常高掉线"即源于此。

**修复**：规则 R3，改为 `param.wt_flamingo_report`，使首轮与后续轮次一致。

---

## FINDING-5 依赖版本演进导致的失效调用

| 问题 | 现象 | 修复（规则） |
|---|---|---|
| `partial_fit(X, y, classes)` 位置传参 | scikit-learn 1.7 将 `sample_weight` 插到 `classes` 之前，类别数组被当作样本权重，抛 `classes must be passed on the first call to partial_fit` | 改为关键字传参（R4，4 处） |
| `int(timedelta.to_timedelta64())` | 新版 numpy 下抛 `TypeError: int() argument must be ... not 'datetime.timedelta'` | `int(pd.Timedelta(...).value)`（R6） |
| 虚拟机墙钟回跳 | 上述差值为负，`Kernel.setAgentComputeDelay` 拒绝：`Requested computation delay must be non-negative` | 加 `max(0, ...)`（R6） |
| `pmlb.fetch_data` 直连 GitHub | 网络不可达，抛 `requests.exceptions.ConnectionError` | 指定 `local_cache_dir`（R7，两处配置） |
| PKI 硬编码 512 | `-n 1024` 时缺密钥文件 | `pki_extend.py` |
| `util/param.py` 变量名拼写 | fedlearn 分支写作 `wt_google_recontruction`（少一个 s），按正常拼写设置的环境变量不生效 | R1 同时兼容两种拼写 |

---

## 附：这些缺陷对结论的影响

| 缺陷 | 不修会得出的错误结论 |
|---|---|
| FINDING-1 | "安全聚合把精度从 90.5% 提升到 96.3%" |
| FINDING-2 | "BBGLR 在 5–10 s 等待下无数据"（误以为是协议特性，实为实现崩溃） |
| FINDING-3 | "BBGLR 出向通信量是 Flamingo 的一万倍" |
| FINDING-4 | "本机掉线率远高于论文，环境不可比"（实为单轮实验的口径错误） |
