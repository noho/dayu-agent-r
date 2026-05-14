# Gateflow Plan Review - Host P4 Public API Command Path

- **review agent**: AgentDS
- **review target**: `docs/host/phase4-public-api-command-path-plan.md`
- **review date**: 2026-05-14
- **review type**: adversarial plan review (handoff-ready gate)

## 结论

accepted

无 blocking finding。plan 是 handoff-ready 且 code-generation-ready，implementation agent 不需要重新设计任何 public contract、错误结构、EventLog cursor 语义、cancel 子集边界或 deferred function 行为。

以下 findings 均为 non-blocking observation / clarification，不阻塞进入 implementation。

---

## Finding 1 (non-blocking observation) — `cancel_session_runs` 未显式校验 Session 存在性

**位置**: plan §5 Slice P4-S3 "Exact changes" 中 `cancel_session_runs` 实现描述。

**观察**: plan 描述 "In one write transaction, read all non-terminal runs for the session"，但未显式说明应先校验 Session 存在。若 Session 不存在，读出的 non-terminal run 列表为空，按当前 plan 语义将走入 "record session-scope idempotency with Session result ref and no created event"，而非返回 `NOT_FOUND`。

**影响**: 调用方用不存在的 session_id 调用 `cancel_session_runs` 时会静默成功，与 `cancel_run` 对不存在的 run_id 返回 `NOT_FOUND` 不一致。

**建议**: implementation 时在读取 non-terminal runs 前先校验 Session 存在，缺失时返回 `HostApiError(NOT_FOUND)`。plan 无需修改，但 implementation agent 应在 S3 completion report 中说明该决策。

---

## Finding 2 (non-blocking observation) — `cancel_session_runs` promotion 禁用需要专门的 batch 路径

**位置**: plan §5 Slice P4-S3 "Exact changes" 与 stop conditions。

**观察**: 当前 `HostAdmissionService.cancel_run` 在释放 active slot 后自动触发 `promote_after_release`（`admission.py:464-468`）。plan 明确要求 `cancel_session_runs` "Do not trigger queue promotion during session-scope cancel"。这意味着 implementation 不能简单循环调用 `cancel_run`，需要新增 internal batch cancel 方法，或通过参数控制跳过 promotion。

plan 的 stop condition 已经覆盖此风险："Stop if existing low-level transition helpers cannot batch the supported subset without promotion side effects"。这是正确的防御性设计。

**建议**: implementation agent 应在 `admission.py` 中新增 internal `cancel_session_runs_subset` 方法，直接操作 durable transition helpers 而不走 `cancel_run` 的 commit 后 promotion 路径。当前 `cancel_queued_in_transaction` 和 `cancel_predispatch_starting_in_transaction` 本身不触发 promotion，promotion 是在 `HostAdmissionService.cancel_run` 外层做的，因此技术上可行。

---

## Finding 3 (non-blocking observation) — `HostCommandHandle` close 后行为未完全定义

**位置**: plan §3 "Host Handle / Factory / Facet" 与 §5 Slice P4-S2 tests。

**观察**: plan 要求 "calls after close fail predictably"，但未指定失败的具体错误码。合理的语义是 close 后所有操作返回 `INVALID_STATE` 或专用 `HANDLE_CLOSED` 错误码。当前 `HostApiErrorCode` 没有 `HANDLE_CLOSED` 成员。

**建议**: implementation 时可选择两种路径：(a) 使用 `INVALID_STATE` 表达 handle 已关闭，message 说明原因；(b) 新增 `HostApiErrorCode.HANDLE_CLOSED`。两种都可接受，但必须在 S2 completion report 中明确选择并保持所有 public function 一致。

---

## Finding 4 (non-blocking observation) — `dayu/host/command.py` 与 `dayu/host/read_api.py` 职责边界存在模糊地带

**位置**: plan §2 与 §5 slices。

**观察**: plan 将 `get_session` 放在 `read_api.py`（S2），`get_run` 也放在 `read_api.py`（S4），但 `cancel_run` 和 `cancel_session_runs` 放在 `command.py`（S3）。读/写分离是合理的，但以下场景需要注意：

- `cancel_run` 包含 idempotent replay 时本质是读+写，属于 command。
- `get_run`/`get_session` 是纯读，属于 read_api。
- `stream_run_events` 是纯读，属于 read_api。

边界清晰，但 implementation agent 需注意 `read_api.py` 中的函数需要访问 `HostCommandHandle` 的私有 durable store 引用。plan 已明确 handle "may hold private references"，read_api 函数通过 handle 参数访问这些引用。

**建议**: 无修改建议，implementation agent 只需确保 `read_api.py` 不直接 import durable 模块，而是通过 handle 的私有属性访问。

---

## Finding 5 (non-blocking observation) — `stream_run_events` limit 语义与直觉不一致

**位置**: plan §3 "Stream Constants" 与 §8 risk。

**观察**: plan 将 `limit` 定义为 "maximum number of global EventLog rows scanned"，而非 "maximum number of returned target Run events"。这意味着即使调用方请求 limit=100，如果 EventLog 中有大量其他 Run 的事件，可能返回 0 条目标 Run 事件就推进 cursor。

plan 的 risk section 已正确识别此问题："This is the only bounded way to satisfy the design requirement that empty filtered results can advance next_cursor without unbounded scans." 并指出 Phase 8 可增加 read-model API。

**建议**: 该设计是正确的，但 `stream_run_events` 的 docstring 必须清晰说明 limit 是 scan window size 而非 result count。implementation agent 应在 Host README 中显式记录此语义。

---

## Finding 6 (non-blocking observation) — `FollowupSnapshot` plan shape 与 design.md §12 的细微表述差异

**位置**: plan §3 "FollowupSnapshot" vs design.md §12 follow-up 语义。

**观察**: plan 定义的 `FollowupSnapshot` 字段列表为:
- `accepted_input_ref`, `behavior`, `accepted_run_id`, `accepted_run_status`, `current_cursor`, `queued_run_id`, `target_run_id`

design.md §11 行为矩阵描述为 "结果用 `accepted_run_id` + `accepted_run_status` 表达"。但 design.md 未逐字段列出 FollowupSnapshot 的完整字段表。plan 的形状与 design fix (P4-D1) 的修复结论一致。

**建议**: 无修改建议。implementation agent 在 S1 替换 `FollowupSnapshot` 时应以 plan 的字段表为准。

---

## Finding 7 (non-blocking observation) — `HostCommandHandleOptions` 字段与 `HostDurableStoreOptions` 存在语义重复

**位置**: plan §3 "Host Handle / Factory / Facet" 与 §8 risk。

**观察**: plan 的 `HostCommandHandleOptions` 包含 `db_path`、`sqlite_busy_timeout_seconds`、`sqlite_write_busy_retry_count` 等字段，这些与内部 `HostDurableStoreOptions` 高度重叠。plan 明确要求 "Factory maps this public options dataclass into internal HostDurableStoreOptions"，并识别为 non-blocking risk。

**建议**: implementation agent 应在 `command.py` 中实现单一的 `_to_durable_options()` 映射函数，确保公共 options 和内部 options 不产生两套默认值。plan risk section 已覆盖此点。

---

## 对齐验证

### design.md 关键章节对齐

| design.md 要求 | plan 对齐状态 |
|---|---|
| §10.1 Host handle 是 composition root，不是 god object | plan §3 明确 handle 持有私有依赖，不暴露公共属性 |
| §11 Phase 4 behavior matrix | plan §4 逐行对齐，完整实现/子集/deferred 语义一致 |
| §11 `FollowupSnapshot.accepted_run_id`/`accepted_run_status` | plan §3 完整定义并附加 validation rules |
| §11 `HostApiError.detail` typed union, no god bag | plan §3 定义 `SteerConflictDetail` + `HostApiErrorDetail` alias |
| §11 `stream_run_events` EventLog cursor truth | plan §3 明确全局 `event_sequence` 为唯一 truth |
| §13 EventLog cursor contract, empty result `next_cursor` | plan §3 完整覆盖 |
| §22 `cancel_session_runs` Phase 4 subset | plan §4/§5 明确只做 queued/pre-dispatch STARTING |
| §22 Phase 5/7/11 deferred owner | plan §4 behavior matrix + §8 risk 显式列出 |

### controller adjudication 对齐

| adjudication 要求 | plan 对齐状态 |
|---|---|
| Phase 4 plan 以 design.md behavior matrix 为硬边界 | plan §4 完整复制 behavior matrix |
| 不得扩大 scope 到 Engine/ToolRuntime/Projection 等 | plan §1 Non-goals 明确列出所有排除项，每 slice 有 non-goals |
| `cancel_session_runs` 子集 + Phase 5/7/11 deferred owner | plan §4 + §8 risk 显式追踪 |
| `FollowupSnapshot.accepted_run_id`/`accepted_run_status` | plan §3 完整定义 |

### 当前代码现实对齐

| 当前代码状态 | plan 处理 |
|---|---|
| `api.py` `HostApiErrorCode` 缺少 `UNSUPPORTED_OPERATION` | S1 新增 |
| `api.py` `HostApiError` 缺少 `detail` 参数 | S1 新增 |
| `api.py` `FollowupSnapshot` 强制 `queued_run_id` | S1 替换为 accepted-run 形状 |
| `admission.py` 有 internal `start_run`/`cancel_run`/`submit_followup_queue` | S3 wire 到 public facade |
| `admission.py` 无 `cancel_session_runs` | S3 新增 internal 方法 |
| `event_log.py` 有 `read_events_after(cursor, limit)` | S4 复用，必要时加 narrow reader |
| `state.py` 有 Session/Run/Attempt readers | S2/S3 新增 non-terminal run listing 等 helper |

---

## 切片评估

| Slice | 粒度 | 依赖 | 风险 |
|---|---|---|---|
| P4-S1 Public Types | 合适，纯类型变更无状态迁移 | 无 | 低 |
| P4-S2 Session APIs | 合适，依赖 S1 类型 | S1 | 低，stop condition 覆盖好 |
| P4-S3 Run/Cancel | 合适但最复杂，依赖 S2 handle | S1, S2 | 中，cancel_session_runs batch 路径 + promotion 禁用 |
| P4-S4 Read/Stream/Deferred | 合适，依赖 S3 | S1, S2, S3 | 低，terminal summary 提取有限制 |

切片顺序正确，依赖关系清晰。S3 是最大切片但不可避免，因为 run admission、cancel、session-scope cancel 共享同一 admission service 和 durable transition。

---

## 测试覆盖评估

plan 指定的测试覆盖以下关键场景:

- public API idempotency replay（每个 mutating 函数）
- idempotency conflict（同 key 不同 digest）
- race condition（API-level first-committer-wins）
- `cancel_session_runs` 不跨 Session 泄漏
- `cancel_session_runs` 遇到 unsupported 状态时 all-or-nothing
- `stream_run_events` empty result cursor 推进
- `stream_run_events` limit 校验
- deferred functions 返回 `UNSUPPORTED_OPERATION` 且不写 EventLog
- handle close 后操作失败

未显式覆盖但可接受:
- `cancel_session_runs` 与并发的 `start_run` 竞态（由 admission CAS 层覆盖，API 层测试可在现有 `test_admission_multiprocess.py` 模式上扩展）

---

## 反模式检查

| 检查项 | 结果 |
|---|---|
| God object / god dataclass | 未发现。`HostCommandHandle` 是 concrete class with private deps，不是 god bag |
| 无结构 payload / metadata bag | 未发现。plan 多处显式禁止 |
| 兼容 wrapper / re-export | 未发现。plan §6 显式禁止 |
| 反向依赖 (Host -> Engine/Fins/Service/UI) | 未发现。plan §6 显式禁止 |
| `hasattr`/`getattr` dispatch | plan §6 显式禁止 |
| 过度设计 (future-proofing) | 未发现。deferred functions 都返回 stable unsupported |
| 魔法数字 | plan S1 要求 stream constants 为模块级常量 |
| 把显式参数塞进 extra payload | plan §6 显式禁止 |

---

## 残余风险

1. **`cancel_session_runs` batch 路径可能需要新增低层 transition helper**：当前 `cancel_queued_in_transaction` 和 `cancel_predispatch_starting_in_transaction` 是单 Run 操作。batch 场景下需要在同一 transaction 内对多个 Run 调用这些 helper，需要注意 idempotency scope 和 EventLog append 的 ordering。plan 的 stop condition 已覆盖。

2. **`stream_run_events` 的 `HostEventView` 映射**：plan 说 "Do not expose policy decision JSON, reason JSON or full payload JSON through HostEventView"，但当前 `HostEventView` 只有 `payload_ref`/`payload_digest` 没有 `payload_json`，所以自然满足。但 implementation 需要确认 EventLog row 到 `HostEventView` 的映射不泄露内部列。

3. **`get_run` terminal summary 提取**：plan 说 "derive from terminal event payload if summary refs exist, otherwise use status with summary_ref=None"。当前 terminal closeout 通过 `CloseoutAttemptTerminalInput` 传入 `terminal_summary_ref`/`terminal_summary_digest`，这些值存储在 EventLog payload_json 中。从 EventLog 提取需要解析 JSON，存在结构化解析失败的风险。plan 的 stop condition 已覆盖。

---

## 总结

plan 严格对齐所有真源：design.md behavior matrix、controller adjudication、Phase 4 design fix conclusions。切片粒度合适，文件 ownership 清晰，测试覆盖 idempotency/race/deferred unsupported。未发现过度设计、god object、无结构 payload、兼容 wrapper 或反向依赖。

implementation agent 可以直接按 slice 顺序实施，无需重新设计。上述 7 个 non-blocking observations 供 implementation agent 在 completion report 中参考和说明。
