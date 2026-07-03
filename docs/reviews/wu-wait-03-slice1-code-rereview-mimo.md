# WU-WAIT-03 Slice 1 Code Re-Review

## Scope

- Work unit: WU-WAIT-03 / GitHub issue-92
- Gate: Slice 1 code re-review
- Review agent: AgentMiMo
- Re-review date: 2026-07-03T11:38:39+08:00
- Source artifacts:
  - Controller adjudication: `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-wait-03-slice1-fix-codex.md`
  - Original review (MiMo): `docs/reviews/wu-wait-03-slice1-code-review-mimo.md`
  - Original review (DS): `docs/reviews/wu-wait-03-slice1-code-review-ds.md`
- Re-review boundary: only verify controller accepted findings; no scope expansion; no code/test/doc modification

## Accepted Finding Verification

### F2 — __all__ 未导出新增 lifecycle 类型（MiMo F2 / DS F2）

- **裁决**: accepted
- **状态**: ✅ 已修复
- **证据**: `dayu/host/wait_adapter.py:1541-1570` — `__all__` 列表已包含全部 5 个 lifecycle 类型：
  - `WaitExternalJobLifecycleAction`（line 1548）
  - `WaitExternalJobLifecycleApplied`（line 1549）
  - `WaitExternalJobLifecycleNoop`（line 1550）
  - `WaitExternalJobLifecycleResult`（line 1551）
  - `WaitExternalJobLifecycleUnsupported`（line 1552）
- **验证**: 按字母序插入，与已有 `WaitPollResult`、`WaitPollReady` 等同级，无遗漏。

### DS F3 — cancelled wait + missing adapter 路径缺少专门测试

- **裁决**: accepted
- **状态**: ✅ 已修复
- **证据**: `tests/host/test_wait_adapter_polling.py:722-767` — 新增 `test_cancelled_poll_wait_missing_adapter_stays_retryable` 测试。
- **断言覆盖**:
  - `adapter_errors=1`（line 755）
  - `abandoned=0`（line 756）
  - `poll_abandoned_at is None`（line 760）
  - `poll_last_outcome is WaitPollLastOutcome.MISSING_ADAPTER`（line 764）
  - `poll_last_error_code == "missing_adapter"`（line 765）
  - `poll_claim_id is None`（line 761）— claim 已释放
  - `poll_next_observe_at is not None`（line 762）— retryable
- **验证**: 测试使用空 `WaitPollAdapterRegistry(())`、`_NoResolveResolver()`，确认 cancelled path 不调用 `resolve_wait`。

### DS F4 — `_last_outcome_for_lifecycle_result` TypeError 文案歧义

- **裁决**: accepted
- **状态**: ✅ 已修复
- **证据**: `dayu/host/wait_adapter.py:1372` — TypeError 消息改为 `"unknown wait external job lifecycle result type"`。
- **对比**: 原文为 `"unsupported wait external job lifecycle result"`，与 `WaitExternalJobLifecycleUnsupported` 枚举成员语义混淆。新文案使用 "unknown" 明确表示编程错误（传入封闭联合之外的类型），与正常业务语义 `ABANDON_UNSUPPORTED` 无歧义。

### DS F5 — `_poller_with_resolver` resolver 参数类型过窄

- **裁决**: accepted
- **状态**: ✅ 已修复
- **证据**: `tests/host/test_wait_adapter_polling.py:1138-1168` — `_poller_with_resolver` 函数签名 line 1143: `resolver: WaitResolvePort`。
- **对比**: 原签名为 `resolver: _NoResolveResolver`，绑定到具体测试类。新签名使用 Protocol 类型 `WaitResolvePort`，与同文件 `_poller` 函数（line 1103-1135）使用 `WaitPollLifecycleGate | None` 的惯例一致。

### FinsIngestionWaitPollAdapter return type（MiMo F1 / DS F1）

- **裁决**: deferred-with-owner（Slice 2）
- **状态**: ℹ️ 按裁决 deferred，Slice 1 不修复
- **证据**: `dayu/fins/` 未被修改（`git diff --name-only` 无 fins 文件）。Fix artifact 明确记录此 deferred finding 与 owner。
- **确认**: Slice 1 改动未引入新的 Fins 越界依赖。

## Regression & Boundary Verification

### Correctness regression

- 无新增 regression。Fix 改动仅涉及 `__all__` 导出声明、TypeError 消息文案、测试辅助函数类型注解、新增测试。不涉及 production 逻辑路径、状态机、schema 或 durable 写入。

### Fins/Engine/Service 越界

- 无越界。`git diff --name-only` 显示未提交改动仅涉及 `dayu/host/wait_adapter.py`、`dayu/host/durable/schema.py`、`dayu/host/durable/state.py`、`tests/host/test_*.py`、`docs/host/issues-implementation-control.md`。其中 `schema.py`、`state.py`、`test_durable_schema.py`、`test_wait_record_state.py`、`test_wait_poller_runtime.py`、`test_open_host_runtime.py` 的改动来自 Slice 1 原始实现，非本次 fix 引入。

### Control doc 误改

- `docs/host/issues-implementation-control.md` 在 `git diff --name-only` 中出现，但此文件被 MiMo 和 DS review 均明确排除在 code review scope 之外（controller bookkeeping），且本次 fix artifact 记录 "did not modify control doc"。此为 Slice 1 原始实现阶段的 controller bookkeeping 更新，非 fix 引入。

## Verdict

**pass**

- Blocking findings: **0**
- Non-blocking findings: **0**
- 所有 4 项 controller accepted findings 均已修复，证据完整
- Deferred Fins adapter finding 按裁决保持 deferred-with-owner to Slice 2
- 无新 correctness regression、无越界改动、无 control doc 误改
- 可进入 accepted slice commit gate
