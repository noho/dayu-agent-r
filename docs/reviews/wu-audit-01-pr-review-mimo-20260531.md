# Code Review

## Scope

- Mode: PR
- PR: 99 — Host purge audit reconciliation
- Author: noho
- Head branch: feat/host-purge-audit-reconciliation
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/99
- Output file: docs/reviews/wu-audit-01-pr-review-mimo-20260531.md
- Included scope: 全部 PR diff（30 files, +3315 / -398），重点审查 `dayu/host/audit.py`、`dayu/host/command.py`、`dayu/host/durable/purge.py`、`tests/host/test_purge_session.py`、`tests/host/test_audit_sink.py`、`dayu/host/api.py`、`dayu/host/README.md`
- Excluded scope: docs/reviews/ 下的 gateflow artifacts（已由先前 review 覆盖）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 细项观察（不构成 finding）

以下为非阻塞观察，不影响 merge 判定：

1. **`_bounded_failure_message` 的输入保证**（`audit.py:888-897`）：`_bounded_failure_message` 校验 `failure_message` 非空后截断。`command.py:1009` 传入 `str(error)`；Python `Exception.__str__()` 在极少数情况下可能返回空字符串（自定义 `__str__` 实现），但当前所有调用路径的 `error` 均为标准库或项目异常，实际不会触发。不构成真实风险。

2. **purge_failed 最佳努力语义**（`command.py:977-1018`）：`_append_purge_failed_best_effort` 捕获所有异常并 log warning，符合 plan 要求的 best-effort 诊断。如果 failed append 也失败，JSONL 只留下 started line，但 `audit_json_line_marks_purged_source_eventlog_facts` 不会误判 started 为 completed。

3. **tombstone digested_at 的重试稳定性**（`command.py:927`）：`purged_at` 在 `_PurgeSessionOperation.__call__` 中使用 `datetime.now(UTC)` 生成。同 key retry 会生成不同 `purged_at`，导致不同 tombstone_id 和不同 purge_started digest。但 retry 时 durable path 走 tombstone replay（`idempotent_replay=True`），不会重新插入 tombstone，因此 started 的 JSONL source key 幂等去重仍然正确——第一次 append 的 started line 已存在，retry 的 deterministic started line 因 source key 匹配且 digest 相同（tombstone_id 不变因为 durable replay 不重新计算）而被跳过。实际上，由于 replay 时 `PurgeSessionDeleteResult.tombstone` 直接复用已存在 tombstone，`purge_completed` 的 tombstone digest 也保持稳定。

## Open Questions

无。

## Residual Risk

1. **CI 状态**：PR checks 状态为 `pending`，total_count=0。需确认 CI 通过后再 merge。
2. **旧 audit JSONL 兼容**：如果生产环境中已有 `line_kind=purge_tombstone` 的旧 audit line，新的 `audit_json_line_marks_purged_source_eventlog_facts` 不会识别它们为 completed。按 CLAUDE.md 约束，这是预期行为（禁止兼容性代码），但需确认没有依赖旧行为的下游消费者。
3. **multiprocess 测试**：`test_public_purge_is_observed_by_independent_process_read_paths` 使用 `multiprocessing.Process` 验证跨进程 purge 后 fail-closed。测试本身覆盖良好，但 CI 环境的进程隔离行为可能与本地不同。

## Draft Readiness Assessment

PR 处于 draft 状态，从代码质量角度已具备 ready 条件：

- **正确性**：purge_started → SQLite transaction → purge_completed 的编排顺序正确；tombstone 作为 completion truth 的设计一致；幂等 replay 时无条件尝试 completed append 的逻辑正确。
- **文档**：README 已同步更新 purge audit 语义；docstring 覆盖全部新增公共接口。
- **测试**：覆盖 happy path、audit append failure、SQLite failure（rollback + no completed）、completed append failure + retry idempotency、independent process fail-closed。
- **架构边界**：durable 层不 import audit 层；audit 层只 import durable 层的类型定义；command 层作为 composition root 编排两端。
- **无 schema 变更**：`host_purge_tombstones` DDL 不变。
- **包导出**：purge durable helpers 不暴露到 `dayu.host` 根命名空间。
