# Code Review

## Scope

- Mode: current changes (未提交 workspace diff)
- Branch: `phase/wu-wait-03-issue-92`
- Base: accepted Slice 1 commit `4e661cee`
- Review agent: AgentDS
- Gate: code review
- Work unit: WU-WAIT-03 / GitHub Issue #92
- Slice: Slice 2 — Fins Adapter/Runtime Mapping And Provider-focused Tests
- Accepted plan: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Implementation artifact: `docs/reviews/wu-wait-03-slice2-implementation-codex.md`
- Output file: `docs/reviews/wu-wait-03-slice2-code-review-ds.md`
- Review date: 2026-07-03

### Included scope

- `dayu/fins/ingestion/wait_adapter.py` — `FinsIngestionWaitPollAdapter.abandon_wait` 返回类型更新为 `WaitExternalJobLifecycleResult`，corrupt token / missing / LOST / non-transient error / TRANSIENT_UNAVAILABLE 映射实现，新增 `_observation_error_reason` 辅助函数
- `tests/fins/test_fins_ingestion_tools.py` — `_FakeObservationRuntime` 扩展（`cancel_errors`、`abandon_errors`），adapter abandon_wait 测试更新及新增 5 个测试
- `tests/fins/test_fins_ingestion_runtime.py` — 新增 `_BlockingArtifactUploadRunner` 测试辅助类，新增 2 个 runtime 级 abandon 测试
- `docs/reviews/wu-wait-03-slice2-implementation-codex.md` — implementation artifact（作为参考，不 review 其内容）

### Excluded scope

- `docs/host/issues-implementation-control.md` — controller bookkeeping 脏改，不属于 Slice 2 code review target
- `dayu/host/wait_adapter.py` — Slice 1 已 review 并通过 controller adjudication，Slice 2 不修改
- `dayu/host/durable/state.py`、`dayu/host/durable/schema.py` — Slice 1 scope
- `tests/host/` — Slice 1 scope（Host focused tests）

### Parallel review coverage

无。本次 review 为单 reviewer 全量走读。

---

## Findings

### 1-未修复-中-缺少 cancel_observation 非临时错误路径的测试覆盖

- **入口/函数**: `FinsIngestionWaitPollAdapter.abandon_wait` → except 分支
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:180-188`
- **输入场景**: `cancel_observation(handle)` 抛出 `FinsObservationPollError`，且 `error_kind` 为非 `TRANSIENT_UNAVAILABLE`、非 `PERMANENT_NOT_FOUND` 的稳定错误（如 `PERMANENT_CORRUPT_HANDLE`）
- **实际分支**: `except FinsObservationPollError as exc:`（line 180）→ `if exc.error_kind is ... TRANSIENT_UNAVAILABLE: raise`（line 181）→ 不匹配 → `if exc.error_kind is ... PERMANENT_NOT_FOUND:`（line 183）→ 不匹配 → 落入 `return WaitExternalJobLifecycleNoop(reason=_observation_error_reason(exc.error_kind))`（line 187-188）
- **预期行为**: 与 abandon_observation 非临时错误相同：返回 `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`，且不应继续调用 `abandon_observation`
- **实际行为**: 代码逻辑正确——cancel 失败时跳过 abandon，返回 NOOP。但此路径无专门测试覆盖
- **直接证据**:
  - `dayu/fins/ingestion/wait_adapter.py:170`: `snapshot = _run_async_observation(self.runtime.cancel_observation(handle))` 在 try 块内
  - `dayu/fins/ingestion/wait_adapter.py:180-188`: except 块处理 cancel 错误
  - `tests/fins/test_fins_ingestion_tools.py:1729-1751`: `test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop` 只使用 `abandon_errors` 触发 abandon_observation 的错误，不使用 `cancel_errors`
  - `tests/fins/test_fins_ingestion_tools.py:1754-1776`: `test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises` 使用 `cancel_errors` 但只测 `TRANSIENT_UNAVAILABLE`（re-raise 路径）
  - Plan `docs/host/wu-wait-03-external-job-lifecycle-plan.md:225`: 要求覆盖 "Non-transient observation error during cancel or abandon"
  - 注：当前生产环境 `FinsIngestionRuntime.cancel_observation` 实际不抛出 `FinsObservationPollError`（缺失 handle 时返回 LOST snapshot），故此路径在当前生产代码中不可达；但 Protocol 契约允许任意 `FinsObservationRuntime` 实现抛出该异常，测试应覆盖契约边界
- **影响**: 代码逻辑当前正确（cancel 错误与 abandon 错误走同一个 except 块，分支结构对称），但缺少回归保护。若未来有人修改 except 块内的分支优先级或条件判断，cancel 路径可能被意外改变而测试不会失败
- **建议改法和验证点**: 新增测试：构造 `cancel_errors` 中含 `PERMANENT_CORRUPT_HANDLE` 的场景，验证 `abandon_wait` 返回 `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`，不调用 `abandon_observation`（`runtime.abandoned_handles == ()`）。验证点：`pytest tests/fins/test_fins_ingestion_tools.py -q`
- **修复风险（低）**: 纯测试增量，不修改生产代码
- **严重程度（中）**: plan 明确要求的测试场景未完整覆盖，但当前代码逻辑正确且生产路径不受影响

---

## Positive Observations（非 findings，不要求修复）

以下方面经逐行走读确认正确：

### 1. Slice 1 deferred finding 关闭

Slice 1 review（`docs/reviews/wu-wait-03-slice1-code-review-ds.md` Finding 1）记录 `FinsIngestionWaitPollAdapter.abandon_wait` 返回类型仍为 `None`，与 `WaitPollAdapter` Protocol 不兼容。本 slice 已完成：

- `abandon_wait` 签名改为 `-> WaitExternalJobLifecycleResult`（`wait_adapter.py:150-153`）
- 所有返回路径均返回 typed result：`WaitExternalJobLifecycleApplied`（line 176）或 `WaitExternalJobLifecycleNoop`（lines 166-168, 172-174, 184-186, 187-188）
- pyright 验证零错误（implementation artifact 记录）
- Fins focused tests 全部通过（125 passed）

**裁决：deferred finding 已关闭。**

### 2. valid handle 的 cancel → abandon → ABANDON applied 链路

- `wait_adapter.py:170`: 先调用 `cancel_observation(handle)` 获取 snapshot
- `wait_adapter.py:171-174`: 若取消后 snapshot 为 `LOST`，返回 NOOP 并跳过 abandon（正确：observation 已不存在，无需释放）
- `wait_adapter.py:175`: 调用 `abandon_observation(handle)` 释放 process-local handle
- `wait_adapter.py:176-179`: 返回 `WaitExternalJobLifecycleApplied(action=ABANDON, message=...)`
- 测试 `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation`（tools test line 1656）完整验证此链路：断言 `result.action is ABANDON`、`cancelled_handles`、`abandoned_handles`、后续 poll 返回 Lost

**注意**：当前 FinsIngestionRuntime 的 `cancel_observation` + `abandon_observation` 存在轻微冗余——`abandon_observation` 内部也会调用 `record.cancellation_state.request_cancel()`（`ingestion_runtime.py:2368`），与显式 `cancel_observation` 调用构成双重取消请求。但这是 idempotent 操作，不引入 correctness 问题。

### 3. corrupt token / missing / LOST / non-transient error / TRANSIENT_UNAVAILABLE 映射

逐路径验证：

| 场景 | 代码路径 | 返回值 | 测试 |
|---|---|---|---|
| corrupt token → `_handle_from_wait_record` 返回 None | line 165-168 | `NOOP("invalid_observation_handle")`，不调用 runtime | `test_...abandon_corrupt_token_is_noop` ✅ |
| observation missing → cancel 内部 poll 抛 PERMANENT_NOT_FOUND | line 183-186 | `NOOP("observation_missing")`，不调用 abandon | `test_...abandon_missing_observation_is_noop` ✅ |
| cancel 返回 LOST snapshot | line 171-174 | `NOOP("observation_missing")`，不调用 abandon | `test_...abandon_lost_snapshot_is_noop` ✅ |
| abandon 抛 PERMANENT_NOT_FOUND | line 183-186 | `NOOP("observation_missing")` | 同上 missing test（间接覆盖） ✅ |
| abandon 抛其他非临时错误 | line 187-188 | `NOOP("observation_error:<kind>")` | `test_...abandon_non_transient_error_is_noop` ✅ |
| TRANSIENT_UNAVAILABLE | line 181-182 | re-raise | `test_...abandon_transient_unavailable_re_raises` ✅ |

所有 plan 要求的映射均已实现并通过测试。与 plan 的唯一偏差：测试仅覆盖 `abandon_observation` 的非临时错误，未覆盖 `cancel_observation` 的非临时错误（见 Finding 1）。

### 4. lifecycle result message 不泄漏 ID

- `_ABANDON_APPLIED_MESSAGE`（line 100-102）为常量字符串，不含任何格式化参数
- `_ABANDON_REASON_INVALID_OBSERVATION_HANDLE`（line 97）为常量
- `_ABANDON_REASON_OBSERVATION_MISSING`（line 98）为常量
- `_observation_error_reason`（line 378-386）只使用 `error_kind.value`（enum 稳定值），不含 handle id
- 测试 `test_...abandon_cancels_and_cleans_observation`（line 1673）显式断言 `"finsobs_" not in result.message`

**确认：lifecycle result message 不泄漏 Host wait id、adapter key、tool call id 或 observation handle id。**

### 5. prepared observation cancel + abandon before activation

Runtime 测试 `test_abandon_cancelled_prepared_observation_releases_handle_before_activation`（runtime test line 2218）覆盖：

- prepared observation → cancel_observation（返回 CANCELLED）→ abandon_observation（释放 handle）→ activate_observation（应 no-op 或静默失败）→ poll_observation（返回 LOST）
- 断言 `executor.operations == []`：取消后 activation 不提交后台执行器
- 断言 `polled.status is LOST`：handle 已释放

**确认：prepared observation cancel + abandon 后不会 submit 到 executor，handle 已释放。**

### 6. submitted observation abandon best-effort cooperative cancel + 保留 storage artifacts

Runtime 测试 `test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts`（runtime test line 2241）覆盖：

- 使用 `_BlockingArtifactUploadRunner`：先写入源文档到 Fins storage（`artifact_written` event），再阻塞等待 `allow_finish`
- 测试流程：prepare → activate → 后台线程启动 executor → 等待 artifact 写入 → abandon_observation → 释放 blocker → 线程收口
- 断言 `runner.cancellation_checks == (True,)`：upload runner 检测到取消信号
- 断言 `polled.status is LOST`：handle 已从 process-local registry 释放
- 断言 `source_meta["ingest_method"] == "upload"`：已写入 Fins storage 的源文档 artifact 完整保留

**确认：abandon 是 best-effort cooperative cancel，不删除已持久化的业务产物。**

### 7. 未误改 Fins durable job schema / Host contract / Engine/Service/UI/runtime/config/prompt/tool schema

- `dayu/fins/ingestion/wait_adapter.py` 仅修改 `abandon_wait` 方法和新增 `_observation_error_reason` 辅助函数
- 未修改 `dayu/fins/ingestion_runtime.py`（仅测试文件使用其 API）
- 未修改 `dayu/host/` 下任何文件（lifecycle contract 类型在 Slice 1 已引入）
- 未修改 `dayu/engine/`、`dayu/service/`、`dayu/ui/`、`dayu/runtime/`、`dayu/config/`
- 新增 import（`WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult`）均来自 Host wait_adapter 模块的稳定 `__all__` 导出（Slice 1 fix 后）

**确认：无越权修改。**

### 8. 类型签名和 import 正确性

- `abandon_wait` 返回类型 `WaitExternalJobLifecycleResult` 与 `WaitPollAdapter` Protocol（`dayu/host/wait_adapter.py:199-209`）一致
- 所有 lifecycle 类型 import 均被实际使用：`WaitExternalJobLifecycleAction`（构造 Applied）、`WaitExternalJobLifecycleApplied`（返回值）、`WaitExternalJobLifecycleNoop`（返回值）、`WaitExternalJobLifecycleResult`（返回类型注解）
- `WaitExternalJobLifecycleUnsupported` 未被 import——正确，Fins adapter 不返回 Unsupported
- pyright 报告 0 errors, 0 warnings, 0 informations
- `_FakeObservationRuntime` 为 `@dataclass`（test_tools.py line 428），新增字段 `cancel_errors` 和 `abandon_errors` 类型为 `dict[str, FinsObservationPollError] | None = None`，由 dataclass __init__ 正确处理
- `_BlockingArtifactUploadRunner` 新增 import `SourceDocumentRepositoryProtocol` 来自 Fins storage 公开接口，类型使用正确

**确认：类型签名和 import 均正确。**

### 9. README/docs 触发决策

- Implementation artifact（line 83-87）记录已按触发规则读取 `dayu/fins/README.md` 和 `tests/README.md` 的 Agent 更新约束，决策不更新 README
- 判断依据：本次是既有 Fins wait adapter 边界内的 Host lifecycle result mapping，不改变 Fins package 的稳定对外入口或架构边界；tests 不新增测试层级或维护约定
- 此决策合理：按照 CLAUDE.md 的 README 触发规则，"dayu/fins/ 修改 → 检查并按需更新 dayu/fins/README.md"，检查后判断无需更新是正确的。同理 tests README

**确认：README 非更新决策合理。**

### 10. `_observation_error_reason` 自适应设计

`_observation_error_reason`（line 378-386）使用 `error_kind.value` 拼接 reason 字符串，而非硬编码 switch。当 `FinsObservationPollErrorKind` 新增成员时，该函数可自适应生成新 reason，无需同步修改。这符合 CLAUDE.md "编写规则时优先自适应实现" 的约束。

---

## Open Questions

无。

---

## Residual Risk

1. **cancel_observation 非临时错误路径无测试**：见 Finding 1。当前生产 runtime 的 `cancel_observation` 不抛出 `FinsObservationPollError`，故此路径在生产代码中不可达；但 Protocol 契约层面缺少覆盖。

2. **cancel 成功但 abandon 失败的 handle 残留**：当 `cancel_observation` 成功但 `abandon_observation` 因非临时错误失败时，adapter 返回 NOOP，Host 停止重试。此时 observation 已被 cancel（状态已修改）但未被 abandon（未从 process-local registry 移除）。handle 残留到进程重启。这是 plan 明确接受的 best-effort 语义，process-local leak bounded by process lifetime，不是 correctness 缺陷。

3. **cancel + abandon 双重取消请求**：adapter 先调用 `cancel_observation` 再调用 `abandon_observation`，而真实 `FinsIngestionRuntime.abandon_observation` 内部也会调用 `record.cancellation_state.request_cancel()`（`ingestion_runtime.py:2368`），导致取消请求被发出两次。这是 idempotent 操作，不影响 correctness，但属于轻微冗余。

4. **Host TRANSIENT_UNAVAILABLE re-raise → ABANDON_ERROR backoff 路径**：此路径的端到端行为由 Host focused tests（`tests/host/test_wait_adapter_polling.py`）覆盖，不在 Slice 2 scope。当前 Fins adapter 正确 re-raise，Host 侧行为在 Slice 1 已验证。

5. **Poller disabled 部署**：未配置 production poller 的部署不会执行 external lifecycle 动作。Host cancellation correctness 由 durable state machine 保证，不依赖 poller。此风险在 plan 中已记录，非本 slice 引入。

---

## Verdict

**Pass**

- Blocking findings: **0**
- Non-blocking findings: **1**（1 个中）
- Slice 1 deferred finding（abandon_wait 返回类型）已关闭
- 所有 plan 要求的映射（corrupt token / missing / LOST / non-transient error / TRANSIENT_UNAVAILABLE / valid handle ABANDON applied）均已正确实现并通过测试
- prepared observation cancel + abandon before activation 和 submitted observation cooperative cancel + storage artifact preservation 均有 runtime 级测试覆盖
- 无 ID 泄漏、无 schema 误改、无 Host contract 变更、无越权修改
- pyright 零错误，125 个 Fins focused tests 全部通过
- 唯一的 material finding（Finding 1）是测试覆盖缺口，不阻塞 merge
