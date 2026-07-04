# Code Review

## Scope

- Mode: current changes (未提交 workspace diff)
- Branch: `phase/wu-wait-03-issue-92`
- Base: accepted plan commit `6be72997`
- Review agent: AgentDS
- Gate: code review
- Work unit: WU-WAIT-03 / GitHub issue-92
- Slice: Slice 1 - Host Lifecycle Contract And Poller Diagnostics
- Accepted plan: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Implementation artifact: `docs/reviews/wu-wait-03-slice1-implementation-codex.md`
- Output file: `docs/reviews/wu-wait-03-slice1-code-review-ds.md`
- Review date: 2026-07-03

### Included scope

- `dayu/host/wait_adapter.py` — lifecycle contract types, `WaitPollAdapter.abandon_wait` return type change, `_abandon_cancelled_wait` mapping, `_last_outcome_for_lifecycle_result`, `_MarkWaitRecordAbandonedOperation` update
- `dayu/host/durable/state.py` — `WaitPollLastOutcome.ABANDON_UNSUPPORTED` / `ABANDON_NOOP` 新增, `mark_wait_record_poll_abandoned` 参数化
- `dayu/host/durable/schema.py` — `HOST_SCHEMA_VERSION` 19, `poll_last_outcome` CHECK allowlist 新增
- `tests/host/test_wait_adapter_polling.py` — adapter fake 更新, applied/unsupported/noop/CAS conflict/shutdown 测试
- `tests/host/test_wait_poller_runtime.py` — adapter fake 返回类型更新
- `tests/host/test_wait_cancel_late_result.py` — 确认行为不变（未修改）
- `tests/host/test_wait_record_state.py` — enum codec roundtrip, abandon marker 参数化测试
- `tests/host/test_durable_schema.py` — schema version 断言更新, CHECK allowlist 断言
- `tests/host/test_open_host_runtime.py` — `_ReadyPollAdapter.abandon_wait` 返回类型更新
- `docs/reviews/wu-wait-03-slice1-implementation-codex.md` — implementation artifact（作为参考，不 review 其内容）

### Excluded scope

- `docs/host/issues-implementation-control.md` — controller bookkeeping，不属于 Slice 1 code review target
- `dayu/fins/ingestion/wait_adapter.py` — Plan 明确归入 Slice 2；仅作为跨 Slice 类型一致性检查的参考
- `dayu/fins/ingestion_runtime.py` — Slice 2 scope
- `tests/fins/` — Slice 2 scope

### Parallel review coverage

无。本次 review 为单 reviewer 全量走读。

---

## Findings

### 1-未修复-中-FinsIngestionWaitPollAdapter 未适配新 abandon_wait 返回类型

- **入口/函数**: `WaitPollAdapter.abandon_wait` Protocol → `FinsIngestionWaitPollAdapter.abandon_wait`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:140`
- **输入场景**: Slice 2 实施前任何代码路径将 `FinsIngestionWaitPollAdapter` 实例传入 `WaitPollAdapterRegistry`（该 registry 的 `adapter` 字段类型为 `WaitPollAdapter`）
- **实际分支**: `FinsIngestionWaitPollAdapter.abandon_wait(...) -> None` — 返回类型仍为 `None`，而 Protocol 现在要求 `-> WaitExternalJobLifecycleResult`
- **预期行为**: Protocol 的实现者应返回 `WaitExternalJobLifecycleResult`（applied / unsupported / noop 之一）
- **实际行为**: 返回 `None`，与 Protocol 类型签名不兼容
- **直接证据**:
  - `dayu/host/wait_adapter.py:199-209`: `WaitPollAdapter.abandon_wait` Protocol 签名声明返回 `WaitExternalJobLifecycleResult`
  - `dayu/fins/ingestion/wait_adapter.py:140`: `def abandon_wait(self, wait_record: WaitRecordRow) -> None:` — 仍为旧签名
  - `dayu/fins/ingestion/wait_adapter.py:98`: `class FinsIngestionWaitPollAdapter:` — 未显式声明实现 `WaitPollAdapter` Protocol
  - 当前 production 代码中 `FinsIngestionWaitPollAdapter` 未被任何 `WaitPollAdapterRegistry` 构造引用（仅 test 文件使用），故 pyright 未捕获此结构性子类型不兼容
- **影响**: 当前无运行时影响（Fins adapter 未在生产路径注册）；但存在 Slice 2 实施前的类型不一致风险——若有人在 Slice 2 前将 Fins adapter 注册到 `WaitPollAdapterRegistry`，pyright 会报告类型错误。这不属于 Slice 1 的 bug，但属于跨 Slice contract drift 风险。
- **建议改法和验证点**: Plan 已将 Fins adapter 更新归入 Slice 2，本 finding 建议在 Slice 2 实施时作为第一项完成，确保 `abandon_wait` 返回类型更新为 `WaitExternalJobLifecycleResult` 并按 plan 中定义的映射规则（valid handle → ABANDON, corrupt token → NOOP, missing observation → NOOP, TRANSIENT_UNAVAILABLE → re-raise）实现。验证点：`pyright` 在 Slice 2 完成后零错误。
- **修复风险（低）**: Slice 2 中按 plan 规范修改即可
- **严重程度（中）**: 当前无运行时影响，但属于 Slice 边界的类型契约不一致
- **裁决建议**: accepted — 属于 Slice 2 scope 的已知 deferred work；Slice 1 review 记录此风险但不 block

---

### 2-未修复-中-新增 lifecycle 类型未加入 `__all__` 导出列表

- **入口/函数**: 模块级 `__all__`
- **文件(行号)**: `dayu/host/wait_adapter.py:1541-1565`
- **输入场景**: 外部 adapter 实现者（如 Slice 2 的 Fins adapter、未来 provider adapter）通过 `from dayu.host.wait_adapter import ...` 导入 lifecycle 类型
- **实际分支**: `__all__` 列表中缺少以下类型：
  - `WaitExternalJobLifecycleAction`
  - `WaitExternalJobLifecycleApplied`
  - `WaitExternalJobLifecycleUnsupported`
  - `WaitExternalJobLifecycleNoop`
  - `WaitExternalJobLifecycleResult`
- **预期行为**: 与同模块中 `WaitPollResult`、`WaitPollReady`、`WaitPollNotReady`、`WaitPollLost` 等同样被外部 adapter 实现者使用的类型一致，应加入 `__all__`
- **实际行为**: 未在 `__all__` 中声明，使用 `from dayu.host.wait_adapter import *` 时不可见
- **直接证据**:
  - `dayu/host/wait_adapter.py:1541-1565`: `__all__` 列表含 `WaitPollResult`, `WaitPollReady`, `WaitPollNotReady`, `WaitPollLost` 但不含新的五个 lifecycle 类型
  - `tests/host/test_wait_adapter_polling.py:30-35`: 测试文件显式按名 import 这些类型（绕过 `__all__`），所以测试不受影响
  - `dayu/fins/ingestion/wait_adapter.py`（Slice 2 目标）将需要 import `WaitExternalJobLifecycleResult` 等类型
- **影响**: `import *` 使用者无法获取这些类型；当前测试使用显式 import 绕过，但对外部 adapter 实现者造成不一致的 API 暴露面
- **建议改法和验证点**: 在 `__all__` 中添加五个新类型，按字母序插入。验证点：`python -c "from dayu.host.wait_adapter import *; assert 'WaitExternalJobLifecycleResult' in dir()"`
- **修复风险（低）**: 纯导出声明修改，不影响运行时行为
- **严重程度（中）**: 不影响 correctness，但属于 public API 暴露面不一致，违反模块内已有惯例
- **裁决建议**: accepted — 建议在 Slice 1 收尾或 Slice 2 开始时修复

---

### 3-未修复-低中-cancelled + missing adapter 路径缺少专门测试覆盖

- **入口/函数**: `WaitPoller._abandon_cancelled_wait`
- **文件(行号)**: `dayu/host/wait_adapter.py:964-981`
- **输入场景**: cancelled wait 被 poller claim，但对应的 `adapter_key` 在 `WaitPollAdapterRegistry` 中未注册
- **实际分支**: `adapter is None` → log warning → `release_with_backoff(outcome=MISSING_ADAPTER)` → return `(0, 1, backoff_result, 0)`
- **预期行为**: 与 waiting path 的 missing adapter 行为一致：写 `MISSING_ADAPTER` backoff，不写 `poll_abandoned_at`，允许重试
- **实际行为**: 代码逻辑正确（与 waiting path 对称），但无专门测试覆盖此路径
- **直接证据**:
  - `dayu/host/wait_adapter.py:964-981`: cancelled path 的 missing adapter 分支
  - `tests/host/test_wait_adapter_polling.py:687-718`: `test_missing_poll_adapter_registration_logs_warning` — 使用 WAITING 状态的 seed，仅覆盖 `poll_once` 主循环中 line 844-859 的 missing adapter 路径
  - 搜索全部测试文件，未找到 cancelled + missing adapter 组合的测试
- **影响**: 代码逻辑当前正确（与 waiting 路径对称），但缺少回归保护。若未来有人修改 cancelled path 的 missing adapter 处理，可能引入 bug 而测试不会失败
- **建议改法和验证点**: 添加测试：构造 cancelled wait + 空 adapter registry，验证 `_abandon_cancelled_wait` 返回 `adapter_errors=1`（非 `abandoned`），`poll_last_outcome=MISSING_ADAPTER`，`poll_abandoned_at IS NULL`
- **修复风险（低）**: 纯测试增量
- **严重程度（低中）**: 代码当前正确，但测试覆盖缺口降低长期 maintainability
- **裁决建议**: accepted — 建议在 Slice 1 或 Slice 2 测试增强时补充

---

### 4-未修复-低-`_last_outcome_for_lifecycle_result` TypeError 错误消息歧义

- **入口/函数**: `_last_outcome_for_lifecycle_result`
- **文件(行号)**: `dayu/host/wait_adapter.py:1372`
- **输入场景**: 调用方传入不属于 `WaitExternalJobLifecycleResult` 联合类型的对象（仅可能在编程错误或类型检查绕过时发生）
- **实际分支**: 三个 `isinstance` 检查全部失败 → `raise TypeError("unsupported wait external job lifecycle result")`
- **预期行为**: 错误消息应清楚表明"未知/非法类型"，而非使用 "unsupported" 一词
- **实际行为**: 错误消息中的 `"unsupported"` 与枚举成员 `WaitExternalJobLifecycleUnsupported` 在语义上可混淆。阅读日志的运维人员可能将 TypeError 误解为"adapter 返回了 Unsupported 结果但处理出错"，而实际含义是"传入了不在封闭联合中的未知类型"
- **直接证据**: `dayu/host/wait_adapter.py:1372`
- **影响**: 仅在编程错误时触发，影响诊断效率但非 correctness 问题
- **建议改法和验证点**: 改为 `f"unknown lifecycle result type: {type(lifecycle_result).__name__}"` 以区分 "unsupported lifecycle action"（正常业务语义）和 "unknown type"（编程错误）
- **修复风险（低）**: 仅修改错误消息字符串
- **严重程度（低）**: 防御性代码，仅影响异常诊断
- **裁决建议**: accepted — 可在任意时间低成本修复

---

### 5-未修复-低-测试辅助函数 `_poller_with_resolver` 参数类型过窄

- **入口/函数**: `_poller_with_resolver`
- **文件(行号)**: `tests/host/test_wait_adapter_polling.py:1089-1119`
- **输入场景**: 未来测试需要传入其他 `WaitResolvePort` 实现（非 `_NoResolveResolver`）
- **实际分支**: 函数签名 `resolver: _NoResolveResolver` 将参数类型绑定到具体类
- **预期行为**: 应使用 Protocol 类型 `WaitResolvePort` 以保持灵活性
- **实际行为**: 类型过窄，但不影响当前测试
- **直接证据**: `tests/host/test_wait_adapter_polling.py:1089` — `resolver: _NoResolveResolver`；对比同文件中 `_poller` 函数（line 1054）使用 `WaitPollLifecycleGate | None` Protocol 类型
- **影响**: 仅测试代码，不影响 production correctness。未来测试需传入其他 resolver 实现时需修改类型注解
- **建议改法和验证点**: 改为 `resolver: WaitResolvePort`
- **修复风险（低）**: 测试代码类型注解修改
- **严重程度（低）**: 仅测试代码，不影响生产行为
- **裁决建议**: accepted — 可在任意时间低成本修复

---

## Positive Observations（非 findings，不要求修复）

以下方面经逐行走读确认正确：

1. **Typed lifecycle contract 严格性**: 三个 dataclass（`WaitExternalJobLifecycleApplied`, `WaitExternalJobLifecycleUnsupported`, `WaitExternalJobLifecycleNoop`）均为 `frozen=True, slots=True`，字段类型严格（`WaitExternalJobLifecycleAction`, `str | None`, `str`），`__post_init__` 校验完整，中文 docstring 完整。`WaitExternalJobLifecycleResult` 为封闭 TypeAlias 联合。无 `Any`、`object`、untyped。

2. **`mark_wait_record_poll_abandoned` 参数化**: 新增 `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED` keyword-only 参数，默认值保持向后兼容。CAS 谓词（`poll_claim_id = ?`, `status = ?`, `poll_abandoned_at IS NULL`）不变。所有三个 terminal outcome 均写入 `poll_abandoned_at` 防止 re-claim，正确。

3. **Schema 一致性**: `WaitPollLastOutcome` StrEnum 新增两值，schema CHECK allowlist 同步新增，schema version 18→19。`serialize_wait_poll_last_outcome` / `deserialize_wait_poll_last_outcome` 通过 `_serialize_str_enum` / `_deserialize_str_enum` 自动处理新值，无需改动。Row validation 通过 enum 成员集校验，自动接受新值。

4. **`_abandon_cancelled_wait` 分支正确性**:
   - shutdown gate re-check（line 961）：防御性二次检查，防止 gate 在 line 831 和 line 961 之间关闭
   - missing adapter（line 964-981）：log warning + MISSING_ADAPTER backoff，retryable，不写 `poll_abandoned_at`
   - adapter exception（line 985-1004）：log warning + ABANDON_ERROR backoff，retryable，不写 `poll_abandoned_at`
   - typed success（line 1005-1018）：映射 lifecycle_result → `last_outcome`，CAS write，UPDATED → `(1,0,0,0)`，CAS_LOST → `(0,0,1,0)`
   - 返回值 `(abandoned, adapter_errors, claim_conflicts, shutdown_skipped)` 在调用方正确累加

5. **不调用 resolve_wait**: `_abandon_cancelled_wait` 全程不引用 `self._resolver`，不调用 `resolve_wait`。cancelled wait 的 lifecycle path 与 resolve path 完全隔离。

6. **Host cancel state machine 不变**: `cancel_run` / `cancel_session_runs` / `cancel_waiting_run_in_transaction` 未修改。`test_cancel_run_cancels_waiting_run_without_resume_attempt` 和 `test_late_result_after_cancel_writes_bounded_diagnostic` 行为不变（late result 仍被拒绝并写 `WAIT_LATE_RESULT_REJECTED` diagnostic）。

7. **测试覆盖充分**: Plan 要求的测试全覆盖：
   - ✅ applied: `test_cancelled_poll_wait_is_abandoned_once_without_resolve`（含 lifecycle_result 类型断言）
   - ✅ unsupported: `test_cancelled_poll_wait_unsupported_marks_terminal_without_resolve`（含 `_NoResolveResolver` 验证）
   - ✅ noop: `test_cancelled_poll_wait_noop_marks_terminal_without_resolve`（含 `_NoResolveResolver` 验证）
   - ✅ exception retry: `test_failed_cancelled_wait_abandon_is_retried_next_poll`
   - ✅ shutdown/CAS: `test_cancelled_abandon_success_marks_abandoned_when_close_gate_closes`
   - ✅ CAS conflict (applied): `test_abandon_cas_conflict_leaves_cancelled_wait_retryable`
   - ✅ CAS conflict (unsupported/noop): `test_terminal_abandon_cas_conflict_leaves_cancelled_wait_retryable`（参数化）
   - ✅ late result: `test_late_result_after_cancel_writes_bounded_diagnostic`（未修改，验证不变）
   - ✅ enum roundtrip: `test_wait_poll_terminal_outcome_codecs_roundtrip_new_values`
   - ✅ schema validation: `test_wait_record_table_and_indexes_are_created`（CHECK allowlist 断言），`test_host_schema_version_is_query_index_version`
   - ✅ abandon marker 参数化: `test_poll_abandon_success_marks_row_and_clears_claim` 覆盖全部三个 outcome

8. **无过度设计**: 改动只涉及协议层新类型（3 个 dataclass + 1 个 TypeAlias + 1 个 StrEnum）、现有函数参数化（1 个 keyword-only 默认参数）、枚举值新增（2 个 StrEnum 成员）。无新 table、新 column、新 runtime、新 registry、新 watchdog。

9. **无反向依赖**: `dayu/host/wait_adapter.py` 只依赖 `dayu/host/durable/state.py` 和 `dayu/host/durable/transaction.py`（同层 durable 模块），不依赖 Engine/Service/UI/Fins。

---

## Open Questions

1. **Schema version bump 对已有数据库的影响**: Plan 明确声明 "this work unit starts from the current schema as truth and does not need legacy-db compatibility"。 Implementation artifact 记录 "Existing databases with schema version 18 are not compatibility-migrated in this slice"。确认：这是否意味着已有 v18 数据库在打开时会因 schema version mismatch 被拒绝？如果是，是否有文档告知用户需要重建数据库？此问题不影响 review verdict，但建议在 Slice 2 或 release note 中明确。

---

## Residual Risk

1. **Fins adapter Slice 2 依赖**: FinsIngestionWaitPollAdapter 的 `abandon_wait` 返回类型尚未更新（Finding 1）。Slice 2 必须完成此更新，且 pyright 在 Slice 2 完成后必须零错误。

2. **cancelled + missing adapter 路径无测试**: Finding 3 记录。当前代码逻辑正确，但缺少回归保护。

3. **Provider-specific lifecycle semantics**: Host 只记录 applied / unsupported / noop 诊断分类。具体 provider 的 cancel vs revoke vs abandon 语义差异由 adapter 自行处理，Host 不做区分。这是 plan 的 intentional design choice，非实现缺陷。

4. **Schema version bump 无迁移**: Plan 声明不需要 legacy-db 兼容性。已有 v18 数据库无法与新 schema 共存。

5. **Poller disabled 部署**: 未配置 production poller 的部署不会执行 external lifecycle 动作。Host cancellation correctness 由 durable state machine 保证，不依赖 poller。这是 plan 中记录的 residual risk，非 Slice 1 引入的新风险。

---

## Verdict

**Pass-with-findings**

- Blocking findings: **0**
- Non-blocking findings: **5**（1 个中、1 个中、1 个低中、2 个低）
- 所有 finding 均不影响 Slice 1 的 correctness / stability 目标
- Typed lifecycle contract 严格、测试覆盖充分、cancel state machine 不变、resolve_wait 不被 cancelled path 调用
- Finding 1（Fins adapter 类型不一致）是跨 Slice contract drift，属于 Slice 2 scope
