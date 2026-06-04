# WU-CM-01 Deferred Risk Cleanup Plan

## Gate

- Work unit: WU-CM-01 PR deferred risk cleanup
- Scope: D1 / D2 / D4 / D5
- Design source: `docs/host/design.md`
- Controller adjudication: `docs/reviews/wu-cm-01-pr-deferred-risk-controller-adjudication.md`
- Decision: accepted plan; implement without commit / push per user instruction.

## 目标与成功信号

本轮只关闭 WU-CM-01 PR deferred risks D1 / D2 / D4 / D5。

成功信号：

- `dayu.host.memory` 与 `dayu.host.context_fallback` 有模块级 `__all__` 白名单，且不导出下划线 helper。
- `CompactionAttemptRejected.failure_category` 与 `next_policy_decision` 收紧为 `StrEnum`，EventLog payload 仍输出既有字符串值。
- `compact_material` 初始 material 诊断值与相关 docstring 不再暴露 `slice1`。
- 补齐当前边界缺失测试：模块导出白名单、缺失 source label typed/schema 边界、真实 durable memory repair catch-up、memory snapshot 与 checkpoint 同事务提交。
- 指定 pytest、pyright 与 `git diff --check` 通过。

## 非目标与边界

- 不扩展 GitHub Issue #80 长期 evaluation。
- 不新增 public package root contract，不修改 `dayu.host.__all__`。
- 不把 `_INITIAL_POLICY_DIGEST` 扩展为真实 policy digest 派生设计。
- 不重复已有 large evidence chunk、fallback path、CAS rollback 覆盖。
- 不 commit，不 push，不创建或更新 PR。

## 代码证据

- `dayu/host/memory.py` 与 `dayu/host/context_fallback.py` 暴露稳定 typed contract/helper，但此前没有模块级 `__all__`。
- `dayu/host/compaction_operation.py` 的 `CompactionAttemptRejected` 两个字段此前为自由 `str`。
- `dayu/host/compact_material.py` 的 `_INITIAL_POLICY_DIGEST` 与 `_INITIAL_REASON_*` 诊断值此前含 `slice1`。
- `tests/host/test_memory_repair.py` 原有 repair 测试主要使用 fake ProjectionRunner；`tests/host/test_durable_concurrency_matrix.py` 原有 snapshot + checkpoint 覆盖偏重 CAS rollback。

## 实施切片

### Slice 1: public surface / typed cleanup

- 修改 `dayu/host/memory.py`、`dayu/host/context_fallback.py`，增加模块级 `__all__`。
- 修改 `dayu/host/compaction_operation.py`，新增 `CompactionFailureCategory` 与 `CompactionNextPolicyDecision`，并纳入 `compaction_operation.__all__`。
- 修改 `dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py`，在 EventLog reason / payload 边界显式使用 enum `.value`。
- 修改 `dayu/host/compact_material.py`，清理 `slice1` 诊断值和相关 docstring。

### Slice 2: focused tests / docs

- 更新 `tests/host/test_package_exports.py`，断言 memory 与 context fallback 模块级导出白名单。
- 更新 `tests/host/test_compaction_operation.py`，断言 rejected dataclass 字段为 enum 且 payload 仍为既有字符串。
- 更新 `tests/host/test_compaction_contract.py`，补缺失 source label typed/schema 边界与初始 selection 诊断不含 `slice1`。
- 更新 `tests/host/test_memory_repair.py`，在真实 durable store 上验证 memory catch-up 写 snapshot / checkpoint。
- 更新 `tests/host/test_durable_concurrency_matrix.py`，补 snapshot 与 checkpoint 同事务正向提交。
- 检查 `dayu/host/README.md` 与 `tests/README.md`，只同步稳定测试说明。

## 验证

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_memory_repair.py tests/host/test_durable_concurrency_matrix.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

## 风险

- `MISSING_SOURCE_LABEL` 的部分 quality checker 分支在当前 typed dataclass 边界已 fail-fast；测试应覆盖真实 schema/typed 边界，不伪造非法对象。
- 本轮新增模块级 `__all__` 是模块导出审计，不提升到 `dayu.host` 包根。
