# Code Re-Review

## Scope

- Mode: current changes (code re-review — 仅验证 accepted findings 修复)
- Branch: `phase/wu-wait-03-issue-92`
- Review agent: AgentDS
- Gate: code re-review
- Work unit: WU-WAIT-03 / GitHub issue-92
- Slice: Slice 1
- Original review artifact: `docs/reviews/wu-wait-03-slice1-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-wait-03-slice1-fix-codex.md`
- Output file: `docs/reviews/wu-wait-03-slice1-code-rereview-ds.md`
- Review date: 2026-07-03

### Included scope

仅验证 controller accepted findings 的修复状态，不扩大 scope：

- `dayu/host/wait_adapter.py` — `__all__` 导出、`_last_outcome_for_lifecycle_result` TypeError 文案
- `tests/host/test_wait_adapter_polling.py` — cancelled + missing adapter 测试、`_poller_with_resolver` 类型注解
- `dayu/fins/ingestion/wait_adapter.py` — 确认 Fins adapter 未被 Slice 1 修改
- `docs/host/issues-implementation-control.md` — 确认仅为 bookkeeping 更新

### Excluded scope

- 原始 DS review 中未被 controller accepted 的 findings（无此类 findings，所有 5 个均被 accepted 或 deferred）
- Fins/Engine/Service 越界检查（仅验证无越界变更）
- 新 correctness regression 扫描（仅验证无新增 regression）

---

## Accepted Finding Verification

### Finding DS F2 / MiMo F2: 新增 lifecycle 类型未加入 `__all__`

- **Controller decision**: accepted
- **Required action**: 添加 `WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleUnsupported`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult` 到 `__all__`
- **验证结果**: **已修复**
- **直接证据**:
  - `dayu/host/wait_adapter.py:1548-1552`: 五个 lifecycle 类型已按字母序插入 `__all__` 列表
  - 类型顺序: `WaitExternalJobLifecycleAction`（line 1548）、`WaitExternalJobLifecycleApplied`（line 1549）、`WaitExternalJobLifecycleNoop`（line 1550）、`WaitExternalJobLifecycleResult`（line 1551）、`WaitExternalJobLifecycleUnsupported`（line 1552）
  - 与同模块已有导出惯例一致（`WaitPollResult`、`WaitPollReady` 等均已在 `__all__` 中）

---

### Finding DS F3: cancelled + missing adapter 路径缺少专门测试

- **Controller decision**: accepted
- **Required action**: 添加 focused test：构造 cancelled wait + 空 adapter registry，验证 `adapter_errors=1`、`abandoned=0`、`poll_last_outcome=MISSING_ADAPTER`、`poll_abandoned_at is None`、retryable
- **验证结果**: **已修复**
- **直接证据**:
  - `tests/host/test_wait_adapter_polling.py:722-767`: 新增 `test_cancelled_poll_wait_missing_adapter_stays_retryable`
  - Line 743: 使用空 `WaitPollAdapterRegistry(())` 构造 registry
  - Line 754: `assert result.adapter_errors == 1` — 记录 adapter 错误（非 abandoned）
  - Line 755: `assert result.abandoned == 0` — 不增加 abandoned 计数
  - Line 756: `assert "wait poll adapter not registered; retrying cancelled" in caplog.text` — 正确的 warning 日志
  - Line 760: `assert updated_wait_record.poll_abandoned_at is None` — 不写 terminal marker
  - Line 761: `assert updated_wait_record.poll_claim_id is None` — claim 已释放
  - Line 762-763: `poll_next_observe_at is not None` + `poll_backoff_attempt == 1` — retryable
  - Line 764: `assert updated_wait_record.poll_last_outcome is WaitPollLastOutcome.MISSING_ADAPTER` — 正确 outcome
  - Line 765: `assert updated_wait_record.poll_last_error_code == "missing_adapter"` — 正确 error code
  - 测试构造流程: seed waiting run → cancel run → 用空 registry 构造 poller → poll_once → 验证所有断言

---

### Finding DS F4: `_last_outcome_for_lifecycle_result` TypeError 错误消息歧义

- **Controller decision**: accepted
- **Required action**: 将 defensive TypeError message 改为区分 "unknown type"（编程错误）与 "unsupported lifecycle action"（正常业务语义）
- **验证结果**: **已修复**
- **直接证据**:
  - `dayu/host/wait_adapter.py:1372`: `raise TypeError("unknown wait external job lifecycle result type")`
  - 使用 "unknown" 而非 "unsupported"，与 `WaitExternalJobLifecycleUnsupported` 正常结果清晰区分
  - 函数 docstring（line 1363）明确写 `:raises TypeError: lifecycle result 类型不属于封闭联合时抛出。` — 语义准确

---

### Finding DS F5: `_poller_with_resolver` 参数类型过窄

- **Controller decision**: accepted
- **Required action**: 将 resolver 参数类型从 `_NoResolveResolver` 改为 `WaitResolvePort`
- **验证结果**: **已修复**
- **直接证据**:
  - `tests/host/test_wait_adapter_polling.py:1142`: `resolver: WaitResolvePort` — 已使用 Protocol 类型
  - 对比同文件 `_poller` 函数（line 1103-1119）使用 `lifecycle_gate: WaitPollLifecycleGate | None` Protocol 类型，风格一致
  - `WaitResolvePort` 已在 line 45 从 `dayu.host.wait_adapter` import

---

### Finding DS F1 / MiMo F1: FinsIngestionWaitPollAdapter 未适配新 abandon_wait 返回类型

- **Controller decision**: deferred-with-owner（Owner: WU-WAIT-03 Slice 2）
- **Required action**: Slice 1 不得修改；Slice 2 必须完成
- **验证结果**: **未修复（符合预期）**
- **直接证据**:
  - `dayu/fins/ingestion/wait_adapter.py:140`: `def abandon_wait(self, wait_record: WaitRecordRow) -> None:` — 仍返回 `None`
  - `git diff --name-only` 确认 `dayu/fins/` 下无任何文件变更
  - Slice 1 fix artifact 明确记录此 finding 为 "deferred-with-owner to Slice 2"

---

## Cross-Cutting Verification

### 无新 correctness regression

- `dayu/host/wait_adapter.py` 的 diff 仅涉及: 新 lifecycle 类型定义、`WaitPollAdapter.abandon_wait` Protocol 签名变更、`_MarkWaitRecordAbandonedOperation` 新增 `last_outcome` 字段、`_abandon_cancelled_wait` success path 调用 `_last_outcome_for_lifecycle_result` 映射、`__all__` 导出、TypeError 文案修改
- `_abandon_cancelled_wait` 的 missing adapter 分支（line 964-981）和 adapter exception 分支（line 985-1004）未修改，仍使用 `release_with_backoff` 且不写 `poll_abandoned_at`
- `_last_outcome_for_lifecycle_result` 为纯函数，无副作用，三个 `isinstance` 分支覆盖封闭联合全部成员
- 所有 test adapter fake（`_SequenceAdapter`、`_AbandonValueErrorThenNotReadyAdapter`、`_AbandonClaimStealingAdapter`、`_CloseGateDuringAbandonAdapter`、`_StaticLifecycleAdapter`、`_ReadyPollAdapter`、`_SequenceAdapter` in test_wait_poller_runtime、`_BlockingReadyAdapter`）均已更新 `abandon_wait` 返回 `WaitExternalJobLifecycleResult`
- `mark_wait_record_poll_abandoned` 新增 `last_outcome` keyword-only 参数，默认值为 `WaitPollLastOutcome.ABANDONED`，向后兼容

### 无 Fins/Engine/Service 越界

- `git diff --name-only` 变更文件列表:
  - `dayu/host/durable/schema.py` — Host durable 层
  - `dayu/host/durable/state.py` — Host durable 层
  - `dayu/host/wait_adapter.py` — Host adapter 层
  - `tests/host/test_durable_schema.py` — Host 测试
  - `tests/host/test_open_host_runtime.py` — Host 测试
  - `tests/host/test_wait_adapter_polling.py` — Host 测试
  - `tests/host/test_wait_poller_runtime.py` — Host 测试
  - `tests/host/test_wait_record_state.py` — Host 测试
  - `docs/host/issues-implementation-control.md` — 控制文档
- 无 `dayu/fins/**`、`dayu/engine/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/runtime/**` 文件变更
- `dayu/host/wait_adapter.py` 的 import 仅依赖 `dayu/host/durable/`（同层 durable 模块），无跨层反向依赖

### 无 control doc 误改

- `docs/host/issues-implementation-control.md` 的 diff 仅涉及:
  - gate 状态更新: `accepted-plan` → `re-review`
  - implementation status 追加 Slice 1 fix 完成记录
  - next entry point 更新为 re-review gate 派发说明
  - 详细状态段追加 Slice 1 implementation/code-review/fix gate 历史记录
- 均为 bookkeeping 更新，无结构性变更，无 design doc 引用变更

---

## Open Questions

无。

---

## Residual Risk

1. **Fins adapter Slice 2 依赖**: `FinsIngestionWaitPollAdapter.abandon_wait` 仍返回 `None`。Slice 2 必须按 plan 定义的映射规则更新返回类型并补齐 Fins 测试 + pyright。当前 Slice 1 不受影响。
2. **Schema version bump 无迁移**: 已有 v18 数据库无法与新 schema 共存。Plan 声明不需要 legacy-db 兼容性，此风险已在原始 review 中记录。
3. **测试运行验证**: 本 re-review 仅做静态代码验证，未重新运行测试。Fix artifact 记录的测试通过数（35 + 60 + 31, pyright 0 errors）来自 AgentCodex 和 Controller 的独立运行验证，可作为可信证据。

---

## Verdict

**Pass**

- Blocking findings: **0**
- Accepted findings 修复状态:
  - 已修复: 4（DS F2/MiMo F2 `__all__`, DS F3 cancelled+missing adapter test, DS F4 TypeError 文案, DS F5 `_poller_with_resolver` 类型）
  - 未修复（符合预期）: 1（DS F1/MiMo F1 Fins adapter, deferred-with-owner to Slice 2）
  - 部分修复: 0
  - 证据失效: 0
- 无新 correctness regression
- 无 Fins/Engine/Service 越界
- 无 control doc 误改
- **可进入 accepted slice commit gate**
