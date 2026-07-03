# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-wait-03-issue-92`
- Base: `main` (accepted plan commit: `6be72997`)
- Output file: `docs/reviews/wu-wait-03-slice1-code-review-mimo.md`
- Included scope:
  - `dayu/host/wait_adapter.py` — lifecycle typed contract、abandon_wait 返回类型、outcome 映射
  - `dayu/host/durable/state.py` — WaitPollLastOutcome 新枚举值、mark_wait_record_poll_abandoned 参数化
  - `dayu/host/durable/schema.py` — CHECK 约束新值、schema version 19
  - `tests/host/test_wait_adapter_polling.py` — fake adapter 更新、新增 unsupported/noop/CAS 测试
  - `tests/host/test_wait_poller_runtime.py` — fake adapter 更新
  - `tests/host/test_wait_record_state.py` — enum roundtrip、parameterized abandon marker 测试
  - `tests/host/test_durable_schema.py` — schema version、CHECK 断言
  - `tests/host/test_open_host_runtime.py` — fake adapter 返回类型更新
  - `docs/reviews/wu-wait-03-slice1-implementation-codex.md` — implementation artifact
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — controller bookkeeping 脏改，不属于 Slice 1 code review target
  - `tests/host/test_wait_cancel_late_result.py` — 无修改，plan 明确要求保持不变
- Parallel review coverage: 无

## Findings

### 1-未修复-严重-FinsIngestionWaitPollAdapter.abandon_wait 返回类型与 Protocol 不兼容

- **入口/函数**: `FinsIngestionWaitPollAdapter.abandon_wait`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:140`
- **输入场景**: 任何被取消的 wait record 被 Host poller claim 后，调用 `adapter.abandon_wait(record)` 时
- **实际分支**: `abandon_wait` 方法返回 `None`
- **预期行为**: 按 `WaitPollAdapter` Protocol，`abandon_wait` 应返回 `WaitExternalJobLifecycleResult`（`WaitExternalJobLifecycleApplied | WaitExternalJobLifecycleUnsupported | WaitExternalJobLifecycleNoop`）
- **实际行为**: 方法签名声明 `-> None`，方法体中 handle 为 None 时直接 `return`（返回 None），正常路径也不返回任何值
- **直接证据**:
  - Protocol 声明：`dayu/host/wait_adapter.py:199-208` — `def abandon_wait(self, wait_record: WaitRecordRow) -> WaitExternalJobLifecycleResult`
  - Production adapter：`dayu/fins/ingestion/wait_adapter.py:140` — `def abandon_wait(self, wait_record: WaitRecordRow) -> None`
  - Poller 调用点：`dayu/host/wait_adapter.py:984` — `lifecycle_result = adapter.abandon_wait(record)`
  - Outcome 映射：`dayu/host/wait_adapter.py:1005` — `_last_outcome_for_lifecycle_result(lifecycle_result)` 会因 `None` 命中 `raise TypeError`
- **影响**: 当 Fins adapter 实际接入 `WaitPollAdapterRegistry` 后（Slice 2 或生产装配），poller 调用 `abandon_wait` 返回 `None`，`_last_outcome_for_lifecycle_result` 抛出 `TypeError`，被外层 `except Exception` 捕获后写入 `ABANDON_ERROR` backoff。这意味着 Fins adapter 的 abandon 永远被视为 transient error 并无限重试，永远无法达成 terminal lifecycle marker。**这是一个 correctness defect**：Fins cancelled wait 将永远无法写入 `poll_abandoned_at`，poller 会持续 claim 该 wait 直到 shutdown。
- **建议改法和验证点**:
  - 在 Slice 2 中按 plan 更新 `FinsIngestionWaitPollAdapter.abandon_wait` 返回类型。
  - 当前 Slice 1 应在 implementation artifact 中明确标注此为已知 Slice 2 scope，且 production 路径尚未接入 `WaitPollAdapterRegistry`（当前只有 `WaitAdapterRegistry` binding，`WaitPollAdapterRegistry` 尚未在 service 层装配）。
  - 验证：pyright 当前不报错是因为 `FinsIngestionWaitPollAdapter` 未被显式标注为 `WaitPollAdapter`，且未被传入 `WaitPollAdapterRegistration.adapter`。但一旦接入，pyright 会报 structural type error。
- **修复风险（低）**: Slice 2 已 plan 此修改，风险在于 Slice 1 merge 后、Slice 2 完成前如果有人提前接入 Fins adapter 到 poll adapter registry。
- **严重程度（高）**: 这是 Protocol 契约违反。虽然当前 production 路径尚未接入，但它是 Slice 1 改动引入的 contract debt，且 implementation artifact 未明确标注此风险。

### 2-未修复-低-新增 lifecycle 类型未导出至 __all__

- **入口/函数**: `dayu/host/wait_adapter.py` 模块级 `__all__`
- **文件(行号)**: `dayu/host/wait_adapter.py:1541-1565`
- **输入场景**: 外部模块尝试 `from dayu.host.wait_adapter import WaitExternalJobLifecycleResult` 时
- **实际分支**: `__all__` 列表中无新增 lifecycle 类型
- **预期行为**: `WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleUnsupported`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult` 作为 `WaitPollAdapter.abandon_wait` 返回类型的组成部分，应出现在 `__all__` 中
- **实际行为**: 这些类型不在 `__all__` 中，但可被 import（Python `__all__` 不阻止 import，只影响 `from module import *` 和 IDE 自动补全）
- **直接证据**: `dayu/host/wait_adapter.py:1541-1565` — `__all__` 列表无 lifecycle 类型；test 文件已成功 import（`tests/host/test_wait_adapter_polling.py:31-35`）
- **影响**: 不影响 correctness，但影响 discoverability 和 contract 声明完整性。Adapter implementor 可能找不到这些类型。
- **建议改法和验证点**: 在 `__all__` 中添加 `"WaitExternalJobLifecycleAction"`、`"WaitExternalJobLifecycleApplied"`、`"WaitExternalJobLifecycleUnsupported"`、`"WaitExternalJobLifecycleNoop"`、`"WaitExternalJobLifecycleResult"`。
- **修复风险（低）**: 纯声明性修改。
- **严重程度（低）**: 不影响运行时行为。

## Open Questions

- 无。

## Residual Risk

1. **Fins adapter 未更新**: `FinsIngestionWaitPollAdapter.abandon_wait` 返回类型仍为 `None`。当前 production 路径尚未通过 `WaitPollAdapterRegistry` 接入（`build_fins_wait_adapter_registry` 返回 `WaitAdapterRegistry`，不是 `WaitPollAdapterRegistry`），所以不会在当前 runtime 触发。Slice 2 已 plan 更新。风险是 Slice 1 merge 后、Slice 2 完成前如果有人提前装配 Fins adapter 到 poll adapter registry。
2. **Schema version 19 无兼容迁移**: 按项目 schema 变更约束，本 slice 按全新 schema 起库处理，不做旧库兼容读取。已有 schema 18 的数据库需要重新初始化。
3. **`test_wait_cancel_late_result.py` 未修改**: Plan 要求保持不变，当前 diff 确认无修改。该测试覆盖 cancel 后 late result 只写一次 `WAIT_LATE_RESULT_REJECTED` diagnostic 且不创建 resume Attempt，行为未被本次改动影响。

## Review 结论

- **Verdict**: pass-with-findings
- **Blocking findings**: 1（Fins adapter 返回类型 Protocol 不兼容 — 严重程度高但当前 production 路径未接入，属于 Slice 2 scope debt）
- **Non-blocking findings**: 1（`__all__` 未导出新增类型 — 低严重程度）
- **Residual risks**: 3 项（见上）
- **Implementation artifact 评估**: `docs/reviews/wu-wait-03-slice1-implementation-codex.md` 内容准确，validation 命令和结果与实际一致。但未明确标注 Fins adapter 返回类型 Protocol 不兼容这一已知 debt。
