# WU-CM-01 PR Deferred Risk Controller Adjudication

## 裁决

- Gate: WU-CM-01 PR deferred risk reconciliation
- Source artifacts:
  - `docs/reviews/wu-cm-01-pr-review-controller-adjudication.md`
  - `docs/reviews/wu-cm-01-pr-rereview-controller-adjudication.md`
  - `docs/host/issues-implementation-control.md`
- Verdict: D-1 / D-2 / D-4 / D-5 不再 deferred，进入等待实施指令状态。
- Implementation status: 暂停；经用户下一步指令后再修改代码和测试。

本轮只裁决，不实施。以下裁决基于代码核对，不把 WU-CM-01 扩展为新的 public package contract 变更。

## D-1 `memory.py` / `context_fallback.py` 缺少 `__all__`

裁决：accepted for immediate cleanup。

动机成立。`dayu.host.memory` 与 `dayu.host.context_fallback` 不是一次性脚本，而是 Host 内部 typed contract / helper 模块；当前多处 Host 生产代码与测试直接 import 其中稳定符号。缺少模块级 `__all__` 不会改变运行行为，但会让 wildcard import 和导出审计暴露内部 helper、私有 protocol 或私有常量，后续容易产生 public surface 漂移。

实施边界：

- 为 `dayu/host/memory.py` 与 `dayu/host/context_fallback.py` 增加模块级 `__all__`。
- `__all__` 只包含当前模块稳定 typed contracts、常量和 public helper；不得导出 `_MemoryItemWithId` 或其它下划线 helper。
- 不修改 `dayu.host.__all__`，不把 memory / fallback 符号提升到包根 Service-facing public namespace。
- 在 `tests/host/test_package_exports.py` 增加模块级导出白名单测试。

## D-2 `CompactionAttemptRejected` string category / decision

裁决：accepted；改为 `StrEnum`。

动机成立。`CompactionAttemptRejected.failure_category` 与 `next_policy_decision` 当前是自由 `str`，虽然生产路径只从模块内常量写入，但 dataclass 边界没有阻止错误字符串进入 attempt rejected event payload。该风险属于 typed cleanup，不是 schema 或 public package contract 变更。

实施边界：

- 在 `dayu/host/compaction_operation.py` 引入 `StrEnum` 类型，例如 failure category enum 与 next policy decision enum。
- `CompactionAttemptRejected` 字段类型改为对应 enum。
- 内部 `_attempt_rejected()` 与日志使用 enum；写入 `context_events` payload 时显式使用 `.value`，保持 EventLog payload 字符串值不变。
- 若 enum 成为 exported dataclass 字段类型，应纳入 `compaction_operation.__all__`，避免导出 dataclass 暴露未导出的类型。
- 不改变 `dayu/host/context_events.py` payload builder / validator 的 JSON contract。
- 测试需同时断言 typed enum 字段和 EventLog payload 仍是既有字符串。

## D-4 `slice1` 诊断常量命名

裁决：accepted。

动机成立。`dayu/host/compact_material.py` 中 `_INITIAL_POLICY_DIGEST = "slice1-initial-policy"` 与 `_INITIAL_REASON_* = "slice1_*"` 是 module-private 诊断 / selection 说明值，不影响外部 contract；但把实施切片名写进稳定诊断字符串会让后续 review 与排障误把历史 slice 当作语义 owner。

实施边界：

- 将 module-private 常量值改为语义命名，例如 initial compact material / current anchor / trace material / evidence material / previous compacted view / answer material。
- 同步更新相关 docstring 中的 “Slice 1 初始 ...” 表述为语义描述。
- 不在本项中引入真实 policy digest 派生逻辑；`_INITIAL_POLICY_DIGEST` 是否应由 policy 派生是另一项设计问题，不借 D-4 扩 scope。
- 测试只断言新诊断值不含 `slice1`，不把具体字符串过度绑定为外部 contract。

## D-5 测试覆盖增强

裁决：accepted；补“该有”的测试，不重复已有覆盖。

代码核对结果：

- large evidence chunk 已由 `tests/host/test_compact_material.py::test_single_large_evidence_block_is_chunked_under_same_provenance` 覆盖。
- deterministic fallback selection / rendering 已由 `tests/host/test_run_input_builder.py` 覆盖。
- proactive / reactive compaction failure fallback 与 fallback hard-budget fail-closed 已由 `tests/host/test_dispatch_scheduler.py` 覆盖。
- unknown / stale / current-input-anchor quality rejection 已由 `tests/host/test_compaction_contract.py` 覆盖。
- memory snapshot + checkpoint CAS rollback 已由 `tests/host/test_durable_concurrency_matrix.py` 覆盖。

需要补的测试：

- quality gate：补缺失的 section / schema 边界直测，至少覆盖 missing source label 与诊断 label cross-section 或等价当前未覆盖分支。
- repair integration：补真实 durable store 上的 memory projection catch-up / rebuild 测试，证明不是只靠 `_FakeTransactionRunner`。
- concurrency adjacent：补 memory catch-up 与 memory snapshot write 同事务边界或并发相邻场景，证明 checkpoint / snapshot 不会部分推进。

非目标：

- 不新增 real LLM / provider / timeout 慢测。
- 不把 GitHub Issue #80 的长期 evaluation 全量完成塞进本次 cleanup。
- 不为了覆盖率造重复 smoke。

## Required Validation

经用户确认进入实施后，至少运行：

```bash
source .venv/bin/activate
pytest tests/host/test_package_exports.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_memory_repair.py \
  tests/host/test_durable_concurrency_matrix.py \
  -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

若实际修改触及 dispatch / engine ingest fallback 事件写入，还必须追加对应 `tests/host/test_dispatch_scheduler.py` 目标用例。
