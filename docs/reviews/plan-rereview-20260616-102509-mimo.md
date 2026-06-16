# Plan Fix Re-Review: WU-CLI-FINS-OBS-01 Replacement Plan

- **Review target**: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- **上一轮 review**: `docs/reviews/plan-review-20260616-100941.md`（AgentMiMo）、`docs/reviews/plan-review-20260616-101040.md`（AgentDS）
- **Re-review 方法**: 逐项验证上一轮高/中风险 findings 是否已被修复
- **Reviewer**: AgentMiMo
- **Timestamp**: 2026-06-16T10:25:09+08:00

## 上一轮 Findings 修复状态

### 高严重度

| Finding | 描述 | 修复状态 | 验证证据 |
|---|---|---|---|
| P001 | sync-to-async bridge gap in Slice C | **已修复** | Plan lines 177-187 新增完整的 Async 与取消裁决章节，明确 native async 优先、`to_thread`/producer thread 只能作为有界内部 bridge、bridge 必须是 implementation detail、best-effort cancellation 限制、大量 bridge 时停止并重新评估。Slice C 停止条件（line 484）也明确"如果实现需要大量 `asyncio.to_thread`、producer thread 或共享 bridge state 才能成立，停止并重新评估 adapter async 化"。 |
| P003 | Slice C→D sequencing creates circular dependency risk | **已修复** | Plan lines 283-294 新增 D0 作为 contract-only checkpoint，插入在 C 之前。顺序变为 A → B → **D0**（lightweight handle contract）→ C（runtime implementation，可安全删除 job store）→ D（tools/wait adapter 迁移）。Slice C 前置条件（line 444-445）明确"Slice D0 已固定 lightweight observation handle contract、observation source 生命周期和 Host restart / runtime crash 收口语义"。循环依赖被消除。 |
| DS-001 | lightweight observation handle 欠规格 | **已修复** | Plan lines 189-281 新增完整的 Lightweight observation handle 最小 typed contract，包括：`FinsObservationHandle` dataclass、`FinsObservationStatus` enum（PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/LOST）、`FinsObservationPollErrorKind` enum（TRANSIENT_UNAVAILABLE/PERMANENT_NOT_FOUND/PERMANENT_CORRUPT_HANDLE）、`FinsObservationSnapshot` dataclass、`FinsObservationRuntime` protocol（含 `start_observed_*`、`poll_observation`、`cancel_observation`、`abandon_observation`）。API 语义、terminal 映射、transient 处理、abandon 语义、cancel 语义、durable mini-design 触发条件全部明确。 |

### 中严重度

| Finding | 描述 | 修复状态 | 验证证据 |
|---|---|---|---|
| P002 | FinsEvent schema 欠规格 | **已修复** | Plan lines 116-175 新增完整的 FinsEvent 最小 typed contract，包括 `FinsEventType` enum、`FinsResultStatus` enum、`FinsOperationKind` enum、`FinsErrorKind` enum、`FinsEventDetail`/`FinsProgress`/`FinsResultSummary`/`FinsEvent` dataclass 定义，以及详细的字段规则（PROGRESS/RESULT 约束、exit code 映射、details 限制、document_label 语义）。完全 code-generation-ready。 |
| P004 | Cancellation propagation to runtime underspecified | **已修复** | Plan lines 177-187 的 Async 裁决明确：取消通过 operation-scoped `CancellationToken` / cancellation checker 传播；bridge 不能证明强取消语义；blocking call 无检查点时只能 best-effort。Slice A 步骤 6（line 315-316）要求"取消应通过 async iterator 关闭 / task cancellation / operation-scoped cancellation token 传播到 runtime"。Slice C 停止条件覆盖了 blocking bridge 场景。 |
| DS-002 | Slice A/C sequencing 依赖缺口 | **已修复** | Plan lines 283-294 新增明确的 ownership 规则："Slice A owns：`FinsEvent` typed contract、Service direct `AsyncIterator[FinsEvent]` boundary、Service-facing runtime protocol。Slice A 可以用 fake runtime 完成 Service tests；不得删除 runtime job store，不得设计 observation source。" 以及 "Slice C owns：`dayu.fins` runtime implementation 收敛，实现 Slice A 的 direct stream protocol"。line 294 明确"禁止 A、C 两个 slice 同时临场设计 `ingestion_runtime.py` 的同一层 API"。 |
| DS-003 | Slice C→D 循环依赖 | **已修复** | 同 P003，D0 checkpoint 消除了循环依赖。Slice C 前置条件（line 444-445）明确要求 D0 先完成。Slice C 步骤 3（line 454）要求"删除前必须确认 Slice D0 的 observation source 已能支撑 wait adapter poll/resolve/abandon"。 |
| DS-004 | wait adapter 崩溃恢复缺口 | **已修复** | Plan lines 193-194 的默认裁决明确："本 WU 不因 CLI direct 引入 durable handle。Tool awaiting 默认使用 process-local lightweight observation source；它不保证 Host 重启或 runtime crash 后恢复未完成 Fins ingestion。Host restart / runtime crash 后，如果 wait adapter 无法通过 observation source 找回 handle，必须把该 wait resolve 为 `LOST`，不得无限 pending。" D0 步骤 3（line 403）也要求"明确默认 observation source 是 process-local registry，不 durable。Host restart / runtime crash 后找不到 handle 时，wait adapter 必须 resolve LOST"。durable mini-design 触发条件（lines 276-281）明确了何时需要升级。 |
| DS-006 | 测试缺口汇总 | **已修复** | Plan 在各 slice 预期测试中补充了全部缺失场景：stream no-result（Slice A line 324、Slice B line 372）、cancel race（Slice B line 373）、poll transient/permanent failure（Slice D lines 527-528）、storage boundary（Slice C line 467）、redaction/leakage guard（Slice A line 325、Slice B line 376、Slice C line 469）、wait adapter 状态转换（Slice D line 526）、blocking bridge limitation（Slice C line 468、Slice D line 529）。 |

### 低严重度（附带验证）

| Finding | 描述 | 修复状态 |
|---|---|---|
| P005 | Stream no-result edge case lacks runtime guarantee | **已修复** — Slice C 步骤 5（line 456）明确"runtime direct stream 必须保证每次正常业务完成产出唯一 `RESULT`。adapter/runner 异常可以转成 `RESULT(status=FAILURE)` 或抛出显式异常；不得静默 StopAsyncIteration"。 |
| P006 | Test gaps for wait adapter lightweight handle | **已修复** — Slice D 预期测试（lines 526-529）覆盖了全部状态转换和 failure 分类。 |
| DS-005 | FinsEvent contract 欠规格 | **已修复** — 同 P002。 |
| DS-007 | Slice E README sync 时机问题 | **已修复** — 各 slice 新增了 README 触发章节和"Slice 完成时必须记录 README impact assessment"要求。 |
| DS-008 | 非目标边界潜在漂移 | **已修复** — Slice B 步骤 6（line 364）明确"运行中 content/token streaming 仍是非目标，owner 是 `WU-CLI-FINS-OBS-01-R5`；不得新增、修改或删除 streaming 相关断言来扩大本 WU"。 |

## 重点验证区域逐项结论

### 1. FinsEvent contract 是否足够 code-generation-ready

**结论：是。**

Plan lines 116-175 提供了完整的 typed contract：4 个 enum（`FinsEventType`、`FinsResultStatus`、`FinsOperationKind`、`FinsErrorKind`）、4 个 frozen dataclass（`FinsEventDetail`、`FinsProgress`、`FinsResultSummary`、`FinsEvent`）、详细的字段规则（PROGRESS/RESULT 约束、exit code 映射、details 安全限制、document_label 语义）。Implementation agent 可以直接从 plan 文本生成代码，无需自行设计 schema。

### 2. Async 裁决是否正确

**结论：是。**

Plan lines 177-187 建立了清晰的优先级层次：
- 首选：native async / cooperative async execution
- 受限允许：`asyncio.to_thread` / producer thread 作为 runtime 内部有界 bridge
- Bridge 约束：implementation detail、bounded queue/lifecycle、best-effort cancellation、不得固化为架构
- 停止条件：大量 bridge 时重新评估 adapter async 化

`to_thread` / producer thread 被正确定位为有界内部 bridge，不是目标设计。取消语义通过 operation-scoped `CancellationToken` 传播，blocking call 无检查点时明确声明 best-effort 限制。

### 3. Slice A/C ownership 是否清楚

**结论：是。**

Plan lines 283-294 建立了明确的 handoff 规则：
- Slice A owns：FinsEvent contract + Service-facing runtime protocol + Service AsyncIterator boundary
- Slice C owns：runtime implementation 收敛，实现 Slice A 的 direct stream protocol
- 禁止 A、C 同时临场设计同一层 API
- Slice A 可用 fake runtime 完成 Service tests，不得删除 runtime job store

### 4. Slice D0/C/D sequencing 是否消除了循环依赖

**结论：是。**

D0 被插入在 C 之前，作为 contract-only checkpoint：
- D0 定义 lightweight handle contract、observation source 生命周期、recovery 语义
- C 的前置条件要求 D0 已完成
- C 删除 job store 前必须确认 D0 的 observation source 已能支撑 wait adapter
- 如果 D0 发现需要 durable mini-design，C 不能删除旧 job store

旧 review 的"C 先删 job store → D 发现需要 durable state → 需要回滚"的死锁路径被消除。

### 5. Lightweight observation handle typed contract、poll/cancel/abandon API、terminal/error 映射、durability/recovery 裁决是否足够

**结论：是。**

Plan lines 189-281 提供了完整的规格：
- **Typed contract**：`FinsObservationHandle`（handle_id, operation_kind, created_at）、`FinsObservationStatus`（6 值 enum）、`FinsObservationPollErrorKind`（3 值 enum）、`FinsObservationSnapshot`（handle, status, message, result, error_kind, retry_after_seconds）
- **Runtime protocol**：`FinsObservationRuntime` 含 `start_observed_download/preprocess/upload`、`poll_observation`、`cancel_observation`、`abandon_observation`
- **Terminal/error 映射**：SUCCEEDED→Completed、FAILED→Failed、CANCELLED→Cancelled、LOST/PERMANENT_NOT_FOUND/PERMANENT_CORRUPT_HANDLE→Lost；TRANSIENT_UNAVAILABLE→保持 pending 重试
- **Durability 裁决**：默认 process-local，Host restart/runtime crash 后 resolve LOST；durable mini-design 有明确触发条件（cross-process/cross-restart 需求）和最小 schema 约束
- **Abandon 语义**：释放 observation record 但不删除 storage 产物
- **Cancel 语义**：触发 operation-scoped token，blocking call 无检查点时 best-effort

### 6. 测试清单是否覆盖全部要求场景

**结论：是。**

| 测试场景 | 覆盖位置 |
|---|---|
| Stream no-result | Slice A line 324、Slice B line 372、测试迁移计划 line 594 |
| Cancel race | Slice B line 373 |
| Poll transient/permanent failure | Slice D lines 527-528 |
| Storage boundary | Slice C line 467 |
| Redaction/leakage guard | Slice A line 325、Slice B line 376、Slice C line 469 |
| Wait adapter 状态转换 | Slice D line 526 |
| Blocking bridge limitation | Slice C line 468、Slice D line 529 |
| Handle token parse/corrupt | Slice D0 line 411 |
| Host restart/runtime crash LOST | Slice D0 line 412、Slice D line 528 |

## 新引入的风险检查

Re-review 过程中检查了 plan 修改是否引入新风险：

1. **D0 增加了实施步骤**：D0 是 contract-only checkpoint，不涉及 runtime implementation 变更，风险可控。
2. **FinsObservationRuntime protocol 增加了 3 个 start_observed_* 方法**：这些方法的 request 类型（`FinsDownloadRequest` 等）已在现有代码中存在，无新 risk。
3. **Durable mini-design 触发条件**：条件清晰（cross-process/cross-restart 需求），且 plan 明确要求"先停下裁决"，不会被 implementation agent 绕过。

未发现新引入的 material risk。

## Residual Risks

上一轮的 residual risks 状态：

| Risk | 状态 |
|---|---|
| RR-001 Sync-to-async bridge 可能需要 executor 重构 | **已缓解** — Async 裁决明确了 bridge 策略和停止条件 |
| RR-002 Lightweight handle 设计可能需要 minimal durable row | **已缓解** — 默认 process-local + LOST 收口，durable 触发条件明确 |
| RR-003 旧 FinsIngestionJobEventType 与新 FinsEvent 并存 | **仍存在但低风险** — Slice A 步骤 4 要求移除旧 Service public direct path 依赖，Slice C 移除旧 job store。旧 enum 在被替换的路径上自然消亡。 |
| RR-004 UI output redaction 未系统性覆盖 | **仍存在** — Plan 各 slice 要求基本 leakage guard 测试，但系统性 redaction policy 仍 deferred 到 `WU-CLI-FINS-OBS-01-R3`。 |
| RR-005 Prompt/interactive streaming 仍为 deferred | **仍存在** — Slice B 明确保护终态输出、不扩大 streaming，deferred owner `WU-CLI-FINS-OBS-01-R5`。 |

## Final Re-Review Conclusion

**结论：`pass`**

上一轮两份 review 共识别 4 个高严重度 + 5 个中严重度 findings，当前 plan 已全部修复。6 个重点验证区域均通过：

1. FinsEvent contract 完整 code-generation-ready ✓
2. Async 裁决正确，native/cooperative async 优先，to_thread/producer thread 为有界内部 bridge ✓
3. Slice A/C ownership 清楚，禁止同时临场设计 ✓
4. D0/C/D sequencing 消除了循环依赖 ✓
5. Lightweight observation handle typed contract 完整，poll/cancel/abandon API、terminal/error 映射、durability/recovery 裁决足够 ✓
6. 测试清单覆盖 stream no-result、cancel race、poll transient/permanent failure、storage boundary、redaction、wait adapter 状态转换、blocking bridge limitation ✓

Plan 可以进入 implementation gate。
