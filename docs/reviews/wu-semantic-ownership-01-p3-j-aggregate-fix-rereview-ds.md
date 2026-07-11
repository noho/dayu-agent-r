# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Fix Re-Review — AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `0bc75a5b`
- Re-review target: `P3-J-AGG-F01` only
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-deepreview-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-controller-validation.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-rereview-ds.md`
- Included scope: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/durable/read_model.py`, all affected `tests/host/` files
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无

## Verification: Producer → Durable Row → SQLite Write → SQLite Read → Tests

### Producer / Owner Boundary

`dayu.host.queue_policy.RunQueuePolicy` (`dayu/host/queue_policy.py:13-18`) 是唯一 queue policy owner。`parse_run_queue_policy()` 和 `serialize_run_queue_policy()` 是仅有的解析/序列化入口。

### 1. Public Request Text Boundary（不会退化）

`StartRunRequest.queue_policy: str` 保留为文本 (`dayu/host/api.py:1800`)，`__post_init__` 通过 `parse_run_queue_policy(self.queue_policy)` 做 owner 级校验 (`dayu/host/api.py:1819`)。Admission 层 `_admit_start_run()` 在 `dayu/host/admission.py:531` 调用 `parse_run_queue_policy(request.queue_policy)` 将文本转为 typed value。

public text boundary 是有意保留的文本边界，不会把 raw string 泄漏到 durable layer。✅

### 2. Direct Upstream Create Input Boundary

三类 Create input 均已 typed：

- `CreateQueuedRunInput.queue_policy: RunQueuePolicy` (`run_transition.py:153`)
- `CreateAcceptedRunInput.queue_policy: RunQueuePolicy` (`run_transition.py:189`)
- `CreateRunningRunInput.queue_policy: RunQueuePolicy` (`run_transition.py:236`)

`_validate_common_create_input()` 使用 `isinstance(queue_policy, RunQueuePolicy)` (`run_transition.py:5969`) 做类型守卫，不再用 parse-then-discard 字符串校验。

`_run_accepted_event_request()` 在 `run_transition.py:3002` 使用 `serialize_run_queue_policy(request.queue_policy)` 直接序列化 typed value，不再有 `parse → serialize` 重复工序。✅

### 3. Durable Row

`RunRow.queue_policy: RunQueuePolicy` (`state.py:287`)，已从 `str` 改为 typed。✅

### 4. SQLite Write

`insert_run()` 在 `state.py:2702` 写入 `run.queue_policy.value`，序列化仅发生在 persistence boundary 一次。✅

### 5. SQLite Read / Decode

`_decode_run_queue_policy()` 返回 `RunQueuePolicy` (`state.py:1187`, 返回注记 `-> RunQueuePolicy`)。实现：读取原始文本 → `parse_run_queue_policy(raw_policy)` → 返回 typed value (`state.py:1198`)。异常路径返回 `HostRowDecodeError`。✅

### 6. Durable Validation

`_validate_run_for_insert()` 使用 `isinstance(run.queue_policy, RunQueuePolicy)` (`state.py:5263`) 做类型级别校验，比 parse-then-discard 更精确、更清晰。✅

### 7. RunResultRow Terminal Status

`RunResultRow.terminal_status: RunStatus` 在 `read_model.py:61` 已经是 typed。

`_validate_run_result()` 现在调用 `_validate_run_result_terminal_status(row.terminal_status)` (`read_model.py:323`)，不再用 serializer 返回值丢弃的方式校验。

新增的 `_validate_run_result_terminal_status()` (`read_model.py:484-494`) 是显式 typed validation helper：检查 `isinstance(status, RunStatus)` 和 `is_terminal_run_status(status)`。

`serialize_run_result_terminal_status()` (`read_model.py:472-481`) 现在先调用 `_validate_run_result_terminal_status(status)` 再做 `.value` 返回。validation 语义从 serializer 中分离，serializer 只负责文本化。✅

### 8. Test Coverage

新增测试 `test_run_row_queue_policy_decodes_to_owner_type` (`test_state_schema.py:818-844`)：从 SQLite 写入 → 读取 `RunRow` → 断言 `row.queue_policy is RunQueuePolicy.QUEUE`，完整覆盖 SQLite 文本 → typed value 的往返。

所有 15 个受影响测试文件的 fixture 均从 `queue_policy="queue"` 迁移到 `queue_policy=RunQueuePolicy.QUEUE`，无 fixture masking。✅

### 9. 回归扫描

- `rg 'serialize_run_queue_policy\(parse_run_queue_policy' dayu/host/` → 无结果。重复解析/序列化已在 durable ownership path 完全消除。
- `rg 'queue_policy:\s*str\b' dayu/host/durable/` → 无结果。durable 层不再有 str-typed queue_policy。
- `rg 'AdmissionPolicy' dayu/ tests/` → 无结果。遗留 AdmissionPolicy 已删除，无残留引用。
- `rg 'row\.queue_policy|run\.queue_policy' dayu/host/` → 仅 `insert_run()` 的 `.value` 序列化和 `_validate_run_for_insert()` 的 `isinstance` 检查。无下游消费者从 raw field 反推语义。

### 10. Baseline-known Failures

`test_dispatch_scheduler.py::test_proactive_compaction_recovery_tier2_degrades_previous_view` 和 `test_reactive_compact_request_uses_latest_previous_view` 仍失败，与 controller validation 记录一致（snapshot_damaged → dispatched=0）。这两个测试在 pre-fix commit `0bc75a5b` 同样失败，属于 compaction previous-view 的预存问题，与 queue_policy / terminal_status 数据路径无关。✅ 排除。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `dayu/host/admission.py:4655-4656` 在 idempotency key 计算中仍然使用 `serialize_run_queue_policy(parse_run_queue_policy(...))`。这是 digest 计算的 canonicalization（输入是 `StartRunRequest.queue_policy: str`），不是 durable row 重复校验，不违反 owner boundary。但若未来 `RunQueuePolicy` 新增成员，该 digest 计算应在文档或测试中明确其 canonicalization 行为。
- `test_dispatch_scheduler.py` 两个预存 compaction previous-view 失败仍未修复，不在本次 fix scope 内。

## Completion Report

- **Result**: PASS
- **Material findings**: 无
- **Validation reviewed**: producer → durable row → SQLite write → SQLite read → tests 全链路已走通，public text boundary 保留文本但不泄漏 raw string 到 durable layer，AgentCodex 无 fixture masking，pyright 0 errors，全部受影响测试 470+ 通过。
- **Residual risk**: 仅 idempotency digest canonicalization 和预存 dispatch scheduler 失败，均不阻塞本次 fix。
