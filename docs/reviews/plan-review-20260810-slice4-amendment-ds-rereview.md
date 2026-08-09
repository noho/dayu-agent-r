# Plan Review — Slice 4 Amendment Re-review（AgentDS 独立路）

## 元信息

- **Review 目标**：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`（修订后）
- **Base plan**：`docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6 / Slice 4 / §9
- **Stop evidence**：`docs/gateflow/wu-cli-download-01-slice4-amendment-evidence-20260810-060259.md`
- **原 AgentDS review**：`docs/reviews/plan-review-20260810-061438.md`（结论 FAIL，6 findings + 3 OQ）
- **Review 类型**：adversarial plan re-review（AgentDS 独立路）
- **Reviewer**：AgentDS
- **Timestamp**：2026-08-10 06:27 UTC
- **Artifact path**：`docs/reviews/plan-review-20260810-slice4-amendment-ds-rereview.md`
- **HEAD**：`399a686f8113fb39c014b98938cfaf0d0d525b3e`

## Review Posture

本 re-review 验证原 AgentDS review 的 6 个 findings 与 3 个 open questions 是否在修订后的 amendment 中被真正关闭，
同时从 first principles 检查修订是否引入新的 seam、owner drift、过度设计或不可执行规格。

## 修订概要

修订后的 amendment 相对原版做了以下结构性变更（均直接对应原 findings）：

| 原 finding | 修订内容 | 位置 |
|---|---|---|
| F1（严重，glue seam） | `sec_download_persistence.py` 加入 allowlist；删除 prepared callable / replay wrapper / `DownloadFilesStream` adapter；persistence 直接消费 `prefetch_files_stream` + 单一 materializer | §3.1, §5.2, §11 |
| F2（中，type overlap） | 废弃单一 `PrefetchedDownloaderEvent` dataclass，改为四个模块私有 discriminated variants（`_PrefetchStarted` / `_PrefetchedFile` / `_PrefetchSkipped` / `_PrefetchFailed`），每个携带互斥字段 | §4.1 |
| F3（中，request-identity validation owner） | 整个 prepared callable 与 replay contract 删除；persistence 不再接收二次 request 输入 | §5.2, §11 |
| F4（中，test matrix 不可证明） | 新增显式 `SpyBatchRepository`/`SpyStoreFile` 接口、cancel-after-prefetch Event 策略、race barrier 序列 | §7.2, §7.3 |
| F5（低，provider 调用计数冗余） | runtime 只断言端到端结果与 transaction 时序；direct call 归属由 owner test + rg + AST + 人工 review 覆盖 | §7.2, §11 |
| F6（低，repair/overwrite 语义混淆） | 新增 required `allow_not_modified: bool` 独立于 `overwrite_existing`；repair 强制 `False` | §4.2, §6.5 |
| OQ-1（identity equality 标准） | 随 prepared callable 删除 | §11 |
| OQ-2（persistence 修改范围） | `sec_download_persistence.py` 进入 allowlist；§5.2 精确描述修改 | §3.1, §5.2 |
| OQ-3（AST gate 范围） | §8 的 `rg` 枚举明确包含 `_execute_sec_request` | §8 |

## 逐项 Closure 验证

### Finding 1（严重，glue seam）→ **已关闭**

修订后的 §3.1 将 `dayu/fins/pipelines/sec_download_persistence.py` 加入 production allowlist。§5.2 定义 `persist_rejected_filing_artifact` 的新流程为：

```text
persist_rejected_filing_artifact
  -> 完整消费 prefetch_files_stream（无 batch、无 storage callback）
  -> cancellation checkpoint
  -> begin_batch(ticker)（真实 batch）
  -> 逐个调用唯一 materialize_prefetched_event
  -> commit/rollback
```

prepared callable、replay wrapper、request-identity replay validation、`DownloadFilesStream` Protocol 匹配全部删除。§10 明确"不保留 prepared callable、captured-data replay、request-identity replay validation 或匹配旧 `DownloadFilesStream` 签名的 adapter"。§11 裁决记录确认"allowlist 增加 `sec_download_persistence.py`；由 `persist_rejected_filing_artifact` 直接 prefetch 再用真实 batch materialize；删除 prepared/replay 设计"。

**直接证据**：修订版 §3.1 列出 `sec_download_persistence.py`；§5.2 不再出现 "prepared callable"、"DownloadFilesStream 匹配"、"request-identity" 字样；§10 non-goals 明确排除。

**验证结论**：原 prepared callable / compat seam 设计已完全从 amendment 中删除。persistence owner 直接调用 concrete typed API 而非经过翻译层。**Closure 成立**。

### Finding 2（中，type overlap）→ **已关闭**

修订后的 §4.1 将原单一 `PrefetchedDownloaderEvent` dataclass（含 10 个字段，7 个与 `DownloaderEvent` 重叠）替换为四个模块私有的 discriminated variants：

```python
_PrefetchStarted   # kind="started", descriptor only
_PrefetchedFile     # kind="prefetched", descriptor + http_status + content
_PrefetchSkipped    # kind="skipped", descriptor + 304 reason
_PrefetchFailed     # kind="failed", descriptor + safe reason/error
```

`_` 前缀标记为模块私有，不 re-export。§4.1 还规定"若 implementation 发现单个 variant 或共享字段仍无法在类型构造时封闭互斥约束，必须继续拆成更窄的 typed variants；禁止退回一个包含多个 optional state 字段的大 dataclass"。

`DownloaderEvent` 保持现有公开类型不变。§4.3 定义显式映射表，单一 `materialize_prefetched_event` 负责所有投影，消除"两个类型间的隐式映射"。

**直接证据**：修订版 §4.1 的四个 dataclass 定义（L90-123）；§4.3 的映射表（L170-175）。

**验证结论**：不再有一个与 `DownloaderEvent` 字段高度重叠的单一 dataclass。Discriminated variants 按 transport outcome 切分，每个只携带该 outcome 的专属字段。映射由单一 owner 实现。**Closure 成立**。

### Finding 3（中，request-identity validation owner）→ **已关闭**

原 prepared callable 内的 request-identity equality 校验随整个 callable 删除。修订后的 §5.2 废弃了 `DownloadFilesStream` Protocol 作为 persistence 的依赖注入点，改为 "直接、typed、具体参数"。persistence 直接接收 `prefetch_files_stream`（或等价 concrete dependency），不经过任何中间 adapter。

不再存在"二次 request 输入"或"比较传入参数与预取 request facts"的语义——persistence 只消费当前轮产生的 prefetch stream，不持有或重放历史 request。

**直接证据**：修订版 §5.2（L208-229）不在任何位置出现 "request-identity"、"equality"、"exact match"、"replay" 等字样；§11 裁决记录确认"整个 replay contract 与 request equality 校验删除；persistence 直接消费当前调用产生的 typed stream，不存在二次 request 输入"。

**验证结论**：原 ownership 漂移（downloader 校验 caller 的 request）的根因已随着 prepared callable 一起消除。**Closure 成立**。

### Finding 4（中，test matrix 不可证明）→ **已关闭**

修订版 §7 做了三方面改进：

1. **§7.2（rejected persistence tests）**：定义 `SpyBatchRepository`（记录 `begin/commit/rollback` 与调用序号）、`SpyStoreFile`（记录 `(sequence, batch_token, name, payload_sha256)`）。给出 cancel-after-prefetch 的确定性策略：fake prefetch 在返回最后一个 event 后设置 `prefetch_returned` Event 并等待 test-owned `release_prefetch_return`；测试线程观察到 `prefetch_returned` 后主动设置 cancel flag，再释放 generator 返回。这样 cancel 发生在 prefetch 完成和 `begin_batch` 之间，无需 production hook 或 sleep。

2. **§7.3（Phase A/B race 与 corruption matrix）**：显式指定 barrier 序列：
   - 同 target 双 overwrite：`phase_a_classified` Barrier → `prefetch_complete` Barrier → `a_committed` Event 释放 writer B
   - 三轮 revision churn：`round_n_prefetched` Event → `round_n_published` Event 控制 writer/controller 交替
   - 不同 target union：`prefetch_complete` Barrier → `a_committed` Event
   - ordering spies：断言 `prefetch_complete < begin < staged_classify < first_store < commit`

3. **Spy 接口已定义**：`SpyBatchRepository` 至少记录 `begin/staged_classify/commit/rollback/release`；`SpyStoreFile` 记录首次 callback 与 payload digest。不再需要 implementation agent 自行设计 spy。

**直接证据**：修订版 §7.2 L281-283 的 cancel-after-prefetch Event 策略；§7.3 L288-293 的 barrier 序列。

**验证结论**：原 review 指出的"cancel timing 无精确控制""spy 接口未定义""barrier placement 未指定"三个缺口均已用具体策略填补。测试矩阵现在是 code-generation-ready 的。**Closure 成立**。

### Finding 5（低，provider 调用计数冗余）→ **已关闭**

修订版 §7.2 明确"runtime 只断言端到端 artifact、events 与 transaction 结果，不断言冗余 provider 调用次数"。§11 裁决表确认"runtime 只断言 rejected artifact 端到端结果与 transaction 时序；direct call 归属由 owner test、rg、AST 与人工 review 覆盖"。

**直接证据**：修订版 §7.2 L280；§11 L405。

**验证结论**：冗余的运行时 provider 调用计数验证已从 spec 中删除。**Closure 成立**。

### Finding 6（低，repair/overwrite 语义混淆）→ **已关闭**

修订版 §4.2 新增 required `allow_not_modified: bool` 作为 `prefetch_files_stream` 的 transport 参数：

- `True`：允许 conditional request，可能产生 304 skip
- `False`：强制 unconditional transport，不接受 304

§4.2 明确：
- "repair target 无论原请求 `overwrite_existing` 为何都必须传 `False`，取得完整 replacement"
- "Phase B policy 仍只使用原始 `overwrite_existing`"
- "`allow_not_modified` 是 required transport 参数，不是 request-level `overwrite_existing` 的别名"

§6.5 进一步规定："transport 的 `allow_not_modified` 绝不覆盖或替代该 policy 值"。

**直接证据**：修订版 §4.2 L151-156；§6.5 L239。

**验证结论**：transport 层面的 conditional/unconditional 决策（`allow_not_modified`）与 policy 层面的 apply/skip 决策（`overwrite_existing`）已完全解耦。repair 语义通过 `allow_not_modified=False` 机制表达，不与 request-level overwrite 混淆。**Closure 成立**。

### OQ-1（request-identity equality 定义）→ **已解决**

原 OQ 随 prepared callable 删除而不再适用。修订后的 persistence 不接收任何 "第二次 request input"，因此不存在 request-identity equality 的定义问题。

### OQ-2（persistence 修改范围）→ **已解决**

修订版 §3.1 将 `sec_download_persistence.py` 加入 allowlist。§5.2 描述精确修改范围：`persist_rejected_filing_artifact` 改为直接接收 `prefetch_files_stream`，先 prefetch 再 `begin_batch`，然后调用单一 materializer。修改限于该函数的调用流程，不改变 rejected file results、failure summary、meta、validator 语义。

### OQ-3（AST gate 范围）→ **已解决**

修订版 §8 的 `rg` 枚举命令明确包含 `_execute_sec_request`：

```bash
rg -n "_http_download(_if_modified)?\(|_execute_sec_request\(|begin_batch\(|commit_batch\(|rollback_batch\(" ...
```

AST 脚本的范围也明确覆盖"所有 `_http_download`、`_http_download_if_modified`、`_execute_sec_request` 调用点被完整列出并输出供人工复核"。

## 用户指定重点审查

### 1. Persistence owner 边界

修订版将 `sec_download_persistence.py` 加入 allowlist，该文件是 storage callback 构造、rejected artifact transaction、rejected meta/failure summary、commit/rollback 的现有 owner（见 §2 L53）。新增职责是：接受 `prefetch_files_stream` 并先完整消费（锁外），再进入 batch 用唯一 materializer 写 storage。这与其现有 "rejected artifact transaction owner" 身份一致——prefetch → materialize 流程是其 transaction 的前置步骤，不构成 owner creep。

`sec_downloader.py` 仍拥有 `materialize_prefetched_event`（prefetch variant → callback → `DownloaderEvent` 映射），persistence 只是调用它。映射逻辑不在 persistence 中重复。

**依赖方向**：`sec_download_persistence.py` → `sec_downloader.py`（导入 `_PrefetchEvent`、`materialize_prefetched_event`），符合 "persistence 消费 downloader" 的既有方向。

**验证**：修订版 §2 L53 的 owner 表；§5.2 的调用流程。

**结论**：persistence owner 边界清晰，无职责泄露或 owner drift。

### 2. Private discriminated prefetch contract

四个 `_` 前缀 dataclass 的互斥约束：

| Variant | `content` | `reason_code` | `error` | `http_status` |
|---|---|---|---|---|
| `_PrefetchStarted` | — | — | — | —（在 descriptor 中） |
| `_PrefetchedFile` | 非空 `bytes` | — | — | `int` |
| `_PrefetchSkipped` | — | `"not_modified"` | — | `int`（304） |
| `_PrefetchFailed` | — | `str` | `str` | `int \| None` |

§4.1 规定 `started/skipped/failed` 不得用 `content=None` 模拟另一 variant；`prefetched` 不得用 optional reason/error 形成 god bag。四个 variant 按 `kind` discriminator 做 exhaustive matching，pyright 可验证。

**潜在问题**：`_PrefetchEvent` 类型别名被 `sec_download_persistence.py` 消费——`_` 前缀标记为模块私有，但 Python 不强制此约定。这是有意的权衡：`_` 前缀表达 "这些类型不是 public API，consumer 应将其视为 opaque"，而 persistence 的确只将它们传递给 `materialize_prefetched_event`，不做 internal inspection。

**结论**：discriminated variants 设计自洽。`_` 前缀跨模块消费是 pragmatic Python 惯例，不是架构缺陷。

### 3. Repair unconditional 语义

§4.2 的 `allow_not_modified` 参数直接解决了原 review 的 Finding 6。关键语义链路：

1. `prefetch_files_stream(allow_not_modified=False)` → 强制走 unconditional HTTP path（`_http_download`），不发送 `If-None-Match`/`If-Modified-Since` header
2. Repair target 在 workflow 层传 `allow_not_modified=False`，无论 `overwrite_existing` 原值
3. Phase B policy 仍使用原始 `overwrite_existing` 决定 apply/skip
4. §6.6 进一步约束：即使 same-identity latest entry 完整，repair 也不得接受 304 复用损坏 physical file——304 仅在非 repair 且 same-identity latest entry 验证通过时复用

**结论**：transport 语义与 policy 语义完全解耦。Repair unconditional 的语义通路可证明。

### 4. Deterministic barriers 可执行性

§7.2 的 cancel-after-prefetch 策略：

```text
1. fake prefetch stream 在 yield 最后一个 event 后：
   a. 设置 prefetch_returned Event
   b. 等待 test-owned release_prefetch_return Event
2. 测试线程观察到 prefetch_returned
3. 测试线程设置 canonical cancel flag
4. 测试线程释放 release_prefetch_return
5. fake prefetch generator 返回（return，非 yield）
6. persist_rejected_filing_artifact 在 begin_batch 前的 cancellation checkpoint 观察到 cancel
7. 断言 begin/callback/commit/rollback 均为 0
```

此策略的关键设计决策是：cancel 发生在 prefetch 完成（generator 已返回）和 `begin_batch` 之间的调用栈间隙——fake prefetch stream 的 Event 机制让测试可以精确在这个间隙设置 cancel flag。不需要 production hook：cancellation checkpoint 是 `persist_rejected_filing_artifact` 既有的 `_raise_if_cancelled` 调用（`sec_download_persistence.py:325-339`）。修订版 §5.2 在 `prefetch_files_stream` 消费后、`begin_batch` 前增加了一个 cancellation checkpoint。

§7.3 的 race barrier 序列同样依赖于确定性的 barrier/Event 协调。每个 writer 在 Phase A classification、prefetch complete、commit 等关键点通过 barrier 等待测试释放，测试精确控制 interleaving。

**潜在注意**：同 target 双 overwrite test 要求 "B 的首个 staged classification 观察 revision 变化，`SpyStoreFile` 证明旧 payload callback 为 0"——这要求 `SpyStoreFile` 能区分"B 旧 prefetch 的 payload"和"B 新 prefetch 的 payload"。修订版未指定 payload identity 的区分方法（按 digest？按 round 标记？）。这是测试实现细节，不影响 contract。

**结论**：barrier/Event 策略是确定性的，可执行。无需 sleep 或 production hook。

### 5. Static gate 可执行性

修订版 §8 将 static gate 从"AST/call-graph 形式化证明不可达"降级为四类证据组合：

1. `rg` 枚举所有定义与调用点，逐项分类
2. Python AST 脚本检查 syntax-level 不变量（`workspace/tmp/wu_cli_download_01_slice4_static_gate.py`）
3. full pyright 验证 typed variants、Protocol implementers、签名
4. 人工 call-graph review 将每条路径展开到 provider/PDF/Docling 与 begin/commit/rollback 边界

§8 诚实声明："任何单项都不能单独声称形式化证明 Python 动态调用图不可达"；"若因动态 dispatch 或独立 Protocol implementer 而无法根据 rg + AST + pyright + 人工展开建立可信调用链，触发 stop condition；不得把 best-effort 结果写成形式化不可达"。

AST 脚本的 5 条检查（L316-321）均可用 Python `ast` 标准库实现：检查函数签名的 parameter annotation 和 body 内的 `Call`/`Name`/`Attribute` 节点。不要求完整程序分析。

**结论**：static gate 的定义诚实且可执行。四类证据互补，不声称单类证据形式化完备。

### 6. Malformed sha256 strict error

§6.1 明确规定：

- `sha256` 非字符串、空串或不满足 canonical 64 位十六进制结构 → **结构错误**，沿现有 strict storage error 路径立即失败
- 不降级为 `DIGEST_MISMATCH`、`REPAIR_REQUIRED`、`UNKNOWN` 或 repair fallback
- 只有结构合法的 expected sha256 与实际 physical bytes 摘要不同 → `DIGEST_MISMATCH` → `REPAIR_REQUIRED`
- identity/meta 其它结构损坏同样严格失败；不做字符串解析兜底，不放宽 snapshot/read/commit validator

§12 stop condition 进一步规定："malformed sha256 被归类为 repair/UNKNOWN 而非 strict 结构错误" 即停止。

**结论**：malformed sha256 的边界定义精确，与 repair classification 完全隔离。strict error 路径复用存储层既有机制。

### 7. 无新 seam / owner drift

逐 owner 验证：

| Owner | 原职责 | 修订后新增 | Drift? |
|---|---|---|---|
| `sec_downloader.py` | HTTP transport, retry, throttle, 304, cancel, `DownloaderEvent`, `StoreDownloadedFile` Protocol | `prefetch_files_stream`, `_PrefetchEvent` variants, `materialize_prefetched_event` | 否。均在 SEC file download 关注点内 |
| `sec_download_persistence.py` | `StoreDownloadedFile` callback 构造, rejected artifact transaction, file results/failure summary/meta/validator, `persist_rejected_filing_artifact` | prefetch→batch orchestrator（在 `persist_rejected_filing_artifact` 内） | 否。仍为 rejected artifact persistence owner；prefetch 是其 transaction 的前置 |
| `sec_download_filing_workflow.py` | Phase A/B identity-first orchestration | — | 无变化 |
| Storage repository | published/staged identity, integrity classification, physical facts | — | 无变化 |
| CN pipeline | PDF/Docling transport, CN workflow | — | 无变化 |

不新增 capability Protocol、compat alias、wrapper/facade、factory、builder 或中间层。`materialize_prefetched_event` 是 `sec_downloader.py` 内的纯函数（prefetch variant + callback → `DownloaderEvent`），不构成独立模块或新 abstraction layer。

**结论**：无新 seam，无 owner drift。

## 未覆盖的 Residual Observations

以下不是 findings，不构成 PASS/FAIL 判断依据，仅作为 implementation 阶段值得注意的点：

1. **`materialize_prefetched_event` 的 `store_file`/`batch` 参数对 3/4 variants 无实际使用**：函数签名接受 `StoreDownloadedFile` 和 `BatchToken`，但只有 `_PrefetchedFile` 分支实际使用它们。这是 discriminated dispatch 的自然结果，不构成设计缺陷。implementation 可在 docstring 中说明哪些 variants 使用哪些参数。

2. **`_PrefetchEvent` types 跨模块边界**：persistence 导入 `_` 前缀类型，在 Python 中是 convention 而非强制。persistence 只传递这些类型给 `materialize_prefetched_event`，不做 introspection。如果 implementation 阶段 persistence 开始做 variant introspection（如 `isinstance(event, _PrefetchedFile)`），这会成为新的 semantic ownership 问题——但当前 amendment 不要求这么做。

3. **`allow_not_modified` 与 `overwrite_existing` 在 rejected artifact 路径的映射**：rejected artifact 无 repair 概念，其 `overwrite` 参数应机械转换为 `allow_not_modified=not overwrite`（与 §5.1 的 `download_files_stream` 转换一致）。amendment 在 §5.1 描述了此转换但未在 §5.2 的 rejected 路径重复声明。implementation 阶段应注意此映射。

4. **fake prefetch stream 的 cancellation checker 行为**：§7.2 的 cancel-after-prefetch 策略需要 fake prefetch 在其 checkpoints 检查 cancellation checker，且 cancel flag 仅在 prefetch 完成后才变为 True。这要求 fake prefetch stream 内部有 checkpoint 调用，且 test 能控制 cancel flag 的切换时机。实现可行但需注意 fake 实现与真实 `prefetch_files_stream` 的 checkpoint 位置一致。

## Open Questions（本轮新增）

无。原 OQ-1/2/3 均已解决。本轮未发现需要澄清的新 open question。

## Residual Risks

| # | 风险 | 分类 | 来源 | 建议跟踪 |
|---|---|---|---|---|
| RR-1 | `rg + AST + pyright + 人工 review` 四类证据中任一不充分（如动态 dispatch 导致 call graph 不可信）会触发 §12 stop condition | 实现风险 | §8 | 若触发，不降级 gate 要求；产出新 evidence 回到 plan fix |
| RR-2 | 同 target 双 overwrite test 的旧/新 prefetch payload identity 区分方法未指定 | 测试设计 | §7.3 | implementation 阶段按 round 标记或 payload digest 区分；不要求 amendment 层面指定 |
| RR-3 | `DownloadFilesStream` Protocol 删除后，是否有其他模块隐性依赖该 Protocol | 回归风险 | §5.2 | implementation 阶段 `rg` 枚举所有 `DownloadFilesStream` 引用；若仅被 `persist_rejected_filing_artifact` 使用，安全删除 |
| RR-4 | `materialize_prefetched_event` 在 downloader 内是 module-level function 还是 `SecDownloader` method | 实现细节 | §4.3 | amendment 未强制，留 implementation agent 决定。module-level function 更利于 testability 和减少 `SecDownloader` 的 method 数量（`SecDownloader` 已有 7 个公开方法 + 33 个工具函数） |
| RR-5 | OS/file lock 永久 I/O 卡死 | 平台风险 | 原 review RR（保持） | 仍 assigned to later WU；当前禁止业务 timeout |

## Final Conclusion

**PASS**

所有 6 个原 findings 均已通过修订后的 amendment 关闭，3 个 open questions 已解决。修订版的：

- **Scope**：最小且充分——仅增加 `sec_downloader.py` 和 `sec_download_persistence.py` 到 production allowlist，不触及 base plan 其他文件
- **Prefetch contract**：模块私有 discriminated variants 设计自洽，互斥语义在类型构造时封闭
- **Materializer**：单一 `materialize_prefetched_event` 拥有 variant → callback → `DownloaderEvent` 完整映射，消费者不复刻映射逻辑
- **Repair semantics**：`allow_not_modified` 与 `overwrite_existing` 完全解耦，repair 强制 unconditional transport
- **Persistence owner**：`persist_rejected_filing_artifact` 直接 orchestrate prefetch → batch → materialize，无 prepared callable / replay adapter / `DownloadFilesStream` matching
- **Deterministic tests**：Spy 接口、barrier 序列、cancel-after-prefetch Event 策略全部具体化
- **Static gate**：四类证据组合，诚实声明不声称形式化不可达
- **Malformed sha256**：strict structure error，不入 repair classification/fallback
- **无新 seam / owner drift**

该 amendment 现在是 code-generation-ready 的，可以交给 implementation agent。
