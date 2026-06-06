# Code Review — WU-CM-01-F04 Proactive Compaction Manifest-producing Test Seam Closeout

## Scope

- Mode: current changes (phaseflow gate review)
- Branch: phaseflow/host-issues
- Base: main
- Output file: docs/reviews/wu-cm-01-f04-code-review-ds.md
- Included scope:
  - `tests/host/test_dispatch_scheduler.py` — diff vs main（test seam migration + manifest assertions）
  - `docs/reviews/wu-cm-01-f04-implementation-codex.md` — implementation artifact 一致性检查
- Excluded scope:
  - 生产代码 `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py` — 只读验证，不修改
  - `docs/host/issues-implementation-control.md` — gate bookkeeping，除非与 scope 矛盾
  - reactive compaction test seam — 不在本 work unit 范围
  - `tests/host/test_compaction_operation.py`、`tests/host/test_engine_ingest_mapping.py` — 既有的 prepared manifest seam 参考
- Parallel review coverage: 无

## Branch / Diff Summary

当前 branch 与 main 的差异仅涉及 `tests/host/test_dispatch_scheduler.py`（以及 `docs/host/issues-implementation-control.md` 的 gate bookkeeping，本轮忽略）。变更包括：

1. 新增 `_PreparedManifestProactiveCompactor` 基类（继承 `FakeContextCompactor`），实现 `CompactorProposalPreparedCompactor` runtime-checkable protocol 的两个方法。
2. `_TransactionReadableCompactor`、`_QualityRejectOnceCompactor`、`_RequestCapturingCompactor`、`_RaisingCompactor` 全部迁移到 prepared seam，继承 `_PreparedManifestProactiveCompactor`。
3. `_StaleMutatingCompactor` 保留 legacy `compact()` seam，不迁移。
4. 8 个 proactive accepted/rejected test 补 `_assert_accepted_payload_has_proposal_manifest` / `_assert_rejected_payload_has_proposal_manifest` 断言。
5. 新增 `_proposal_compactor_agent_request`、`_events_for_run_by_type`、`_assert_accepted_payload_has_proposal_manifest`、`_assert_rejected_payload_has_proposal_manifest` 辅助函数。
6. 新增 imports：`runner_role_sequence_digest`、`SystemMessage`、`conversation_compact_input_vnext_from_material_pack`、`CompactorProposalRunInput`。

## 走读链路

### 主链路：proactive compaction → manifest record → event payload

1. `HostDispatchScheduler._execute_proactive_compaction` 构造 `CompactionRequest` → 调用 `run_compaction_operation`
2. `run_compaction_operation` (`compaction_operation.py:507`) → `_prepare_compactor_proposal` (`compaction_operation.py:735`)
3. `_prepare_compactor_proposal` 执行 `isinstance(compactor, CompactorProposalPreparedCompactor)` (`compaction_operation.py:749`)
4. 若 True → `compactor.prepare_compactor_proposal_run_input(...)` → `_record_compactor_proposal_manifest(...)` → `compactor.run_prepared_compactor_proposal(...)`
5. 返回的 `_CompactorProposalAttempt.proposal_manifest_reference` 最后写入 `CONTEXT_COMPACTED` payload 的 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest`（`dispatch.py:1669-1670`），或 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 的 `proposal_manifest_ref` / `proposal_manifest_digest`（`dispatch.py:2017-2018`）

### 验证点

- `CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol（`compaction_operation.py:133-134`），`isinstance` 判断依赖方法签名存在性。
- `_PreparedManifestProactiveCompactor` 的方法签名与 protocol 严格对齐：参数名、类型、返回类型均一致。
- 旧 `_StaleMutatingCompactor` 仅继承 `FakeContextCompactor`（只有 `compact()`），不通过 `isinstance` 检查，走 legacy 路径。其在 `_run_compactor_proposal_attempt` 中 `proposal_manifest_reference=None`，stale check 在 `_required_compactor_manifest_ref` 之前收口为 `CONTEXT_COMPACTION_FAILED`——不受影响。

## Findings

### 1-未修复-低-`_RequestCapturingCompactor.requests` 与父类 `prepared_requests` 属性语义重叠

- **入口/函数**: `_RequestCapturingCompactor.__init__` 与 `prepare_compactor_proposal_run_input`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:625-660`
- **输入场景**: 任何使用 `_RequestCapturingCompactor` 的 test
- **实际分支**: `__init__` 中 `self.requests: list[CompactionRequest] = []` 覆盖了父类 `_PreparedManifestProactiveCompactor.__init__` 中的 `self.prepared_requests: list[CompactionRequest] = []`；两个属性类型相同但语义不同（一个由 `_RequestCapturingCompactor.prepare_compactor_proposal_run_input` 写入，一个由父类同名方法写入）。
- **预期行为**: 两个属性在逻辑上等价（同一 prepare 调用中先后 append 同一 request），测试断言只读 `self.requests`，无功能 bug。
- **实际行为**: 同一 request 被同时 append 到 `self.requests`（行 654）和 `self.prepared_requests`（行 655-659 的 `super()` 调用内行 439），数据重复存储。
- **直接证据**: 行 635 `self.requests: list[CompactionRequest] = []` 声明了与行 419 `self.prepared_requests: list[CompactionRequest] = []` 同类型但不同名的属性；行 654 与行 439 在同一调用栈中分别 append。
- **影响**: 若未来有人基于 `self.prepared_requests` 添加断言（合理，因为是父类公开属性），可能观察到与 `self.requests` 完全相同的值而产生困惑。当前无功能影响。
- **建议改法和验证点**: 可选：让 `_RequestCapturingCompactor` 不声明独立的 `self.requests`，改为别名 `self.requests = self.prepared_requests`，或仅用父类 `prepared_requests`。验证：运行 `test_proactive_compaction_uses_selected_material_not_session_start_range` 和 `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`。
- **修复风险（低）**: 仅影响两个 test 的内部断言路径。
- **严重程度（低）**: 不阻塞 merge，可 deferred。

## Protocol Signature 对齐验证

逐方法比对 protocol 定义（`compaction_operation.py:137-167`）与实现（`test_dispatch_scheduler.py:422-487`）：

| Protocol 方法 | Protocol 签名 | 实现签名 | 对齐 |
|---|---|---|---|
| `prepare_compactor_proposal_run_input` | `(self, request: CompactionRequest, cancellation_token: CancellationToken, *, compaction_operation_id: str \| None, compaction_attempt_number: int) -> CompactorProposalRunInput` | 完全一致 | ✓ |
| `run_prepared_compactor_proposal` | `async (self, prepared_input: CompactorProposalRunInput) -> ConversationCompactOutputVNext` | 完全一致 | ✓ |

`CompactorProposalPreparedCompactor` 为 `@runtime_checkable` Protocol，`isinstance` 检查依赖方法名与签名匹配，上述实现可正确触发 manifest recorder 路径。验证通过。

## 测试语义保留验证

逐 compactor 验证原测试语义在迁移后是否完整保留：

| Compactor | 原语义 | 迁移后 | 保留 |
|---|---|---|---|
| `_TransactionReadableCompactor` | `compact()` 中通过独立读事务读 Run | `run_prepared_compactor_proposal()` 中先 `run_read(read_run_by_id)` 再 `super()` | ✓ — 独立读事务在 proposal run 阶段执行，调用时序不变 |
| `_RequestCapturingCompactor` | `compact()` 中 `self.requests.append(request)` | `prepare_compactor_proposal_run_input()` 中 `self.requests.append(request)` | ✓ — request 在 prepare 阶段捕获，语义等价（proactive path 中 request 在进入 operation 前已冻结） |
| `_QualityRejectOnceCompactor` | 首次 `compact()` 返回带 diagnostic 的 candidate，第二次返回 clean candidate | `run_prepared_compactor_proposal()` 中首次通过 `replace(candidate, diagnostics=...)` 返回 rejection，第二次返回 clean | ✓ — quality rejection 语义不变；`self.calls` 通过父类 `run_prepared_compactor_proposal` 的 `self.calls += 1` 正确递增 |
| `_RaisingCompactor` | `compact()` 直接抛 `RuntimeError` | `run_prepared_compactor_proposal()` 中 `fail_run=True` 抛 `RuntimeError` | ✓ — 语义升级为 post-manifest failure，manifest 在抛异常前已记录（`compaction_operation.py:756-771`），rejected payload 可携带 manifest ref/digest |
| `_StaleMutatingCompactor` | legacy `compact()`，在返回前写 Run 失败 | 不变 | ✓ — 不迁移，不通过 `isinstance(CompactorProposalPreparedCompactor)`，走 legacy `compact()` 路径 |

## Manifest Assertion 验证

| Assertion Helper | 断言字段 | 格式要求 | 对应 payload builder |
|---|---|---|---|
| `_assert_accepted_payload_has_proposal_manifest` | `accepted_proposal_manifest_ref`、`accepted_proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头且为 str；digest 为非空 str | `build_context_compacted_payload` (`context_events.py:310-311`) |
| `_assert_rejected_payload_has_proposal_manifest` | `proposal_manifest_ref`、`proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头且为 str；digest 为非空 str | `build_context_compaction_attempt_rejected_payload` (`context_events.py:595-596`) |

所有断言直接访问 payload 的业务字段名，不依赖 `RUNNER_CALL_INPUT_ASSEMBLED` 计数或 event 序号——符合 plan 中"不加入脆弱计数断言"的要求。验证通过。

## 排除项验证

| 排除项 | 原因 | 当前状态 |
|---|---|---|
| `_StaleMutatingCompactor`（`test_compaction_stale_result_does_not_write_compacted_event`） | stale check 在 accepted guard 前收口为 `CONTEXT_COMPACTION_FAILED`，不触发 manifest guard | 仍使用 legacy `compact()`，不实现 prepared protocol |
| `test_pre_start_governance_proactive_count_limit_blocks_second_compact` | count limit 在 compaction operation 前 fail closed | 仍使用 `FakeContextCompactor()`（行 4354） |
| `test_pre_start_governance_corrupted_compact_count_fails_closed` | corrupted count 在 compaction operation 前 fail closed | 仍使用 `FakeContextCompactor()`（行 4400） |
| reactive tests | 不在 proactive seam closeout 范围；已有独立 prepared manifest seam 覆盖 | 仍使用 `FakeContextCompactor()`（行 4507, 4604, 4681） |

所有排除项经逐行确认，不存在遗漏的 proactive accepted/rejected path。验证通过。

## Architecture Boundary 检查

- 无生产代码变更。`dayu/host/dispatch.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_events.py` 均未修改。
- 无 schema 变更、无 public interface 变更、无 Engine contract 变更。
- 测试 seam 实现 `CompactorProposalPreparedCompactor` protocol，依赖该 protocol 的 `@runtime_checkable` 特性——这是已有 public contract，非新增耦合。
- 新增 imports 均来自已有 public 模块（`dayu.engine.contracts.*`、`dayu.host.compaction_operation`、`dayu.host.compact_material`），无跨层穿透引用。

## Adversarial Failure Pass

| 攻击面 | 检查结果 |
|---|---|
| 空 prepared request（`_latest_prepared_request` 返回 None） | 有 `AssertionError` 守卫（行 497-498），不会静默传递 None 到 `FakeContextCompactor.compact()` |
| `_RaisingCompactor` 失败时序 | `_record_compactor_proposal_manifest`（`compaction_operation.py:756`）在 `run_prepared_compactor_proposal`（行 764）之前执行，manifest 已持久化后再抛异常——rejected payload 可正确携带 manifest ref |
| `_QualityRejectOnceCompactor` 多次 prepare/run 间 `_prepared_request` 污染 | 每次 `prepare_compactor_proposal_run_input` 都覆写 `self._prepared_request`（行 440），`run_prepared_compactor_proposal` 读取最新值——时序正确 |
| `FakeContextCompactor` 仍被用于 proactive accepted test | 仅在排除项 test 中使用（count limit / corrupted count / reactive），这些路径在 compaction operation 前或走不同路径，不触发 manifest guard |
| `_RaisingCompactor` 仅用于 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | grep 确认仅行 4190 一处使用 |
| 未覆盖的 proactive compactor injection | 逐行 grep 所有 compactor 注入点（含 `FakeContextCompactor()`、`_RequestCapturingCompactor` 等 7 个类名），确认迁移清单完整 |

## Open Questions

无。

## Validation Reviewed

Implementation artifact 报告以下验证已通过：

1. `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"` → 8 passed, 54 deselected
2. 3 个 focused tests 单独运行 → 3 passed
3. `pyright` → 0 errors, 0 warnings, 0 informations

本轮未重新运行验证。理由：本 gate 为 code review gate，仅审查代码正确性与一致性；implementation gate 已完成 focused validation。若需重新运行，见下方 Residual Risk。

## Residual Risk

- **全量 test suite 未运行**：implementation gate 仅运行了 focused/selected tests（8+3 pass）。`tests/host/test_dispatch_scheduler.py` 包含 ~100+ test，其余测试（含 reactive/recovery/duplicate/stale 等）未被 focused validation 覆盖。虽然变更仅限 proactive seam migration，理论上不应影响其他测试，但未经验证。
- **`tests/host/test_compaction_operation.py` 未运行**：该文件包含 prepared manifest seam 的 reference implementation 和测试。本轮未验证迁移后的 test_dispatch_scheduler 与 test_compaction_operation 之间的 seam 一致性。
- **`_RequestCapturingCompactor` 属性冗余**：Finding 1 描述的低严重度问题，不阻塞 merge，但建议 future cleanup 时统一。
- **reactive test seam 后续对齐**：reactive tests 仍使用 `FakeContextCompactor()`，虽然不在本 work unit 范围，但若未来 reactive manifest contract 升级，需类似迁移。

## Verdict

**pass-with-findings** — 1 non-blocking low-severity finding（属性语义重叠）。核心实现正确：prepared compactor protocol 正确触发 manifest recorder，所有 migrated compactor 保留了原测试语义，manifest assertions 直接断言 payload 字段而非脆弱计数，无生产代码变更，无架构违规。
