# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Fix - AgentCodex

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate deepreview accepted-finding fix
- Accepted finding: `P3-J-AGG-F01`
- Status: 已修复

## First-Principles 判断

finding 成立。`queue_policy` 的合法集合与解析/序列化 owner 已在 `dayu.host.queue_policy.RunQueuePolicy`，但 durable `RunRow.queue_policy` 仍暴露为 `str`，会让后续消费者重新承担 owner 校验或误把 SQLite 文本当作 durable typed contract。正确修复边界是 durable state codec 与其直接上游创建输入，而不是下游 consumer fallback。

`RunResultRow.terminal_status` 已是 `RunStatus` typed surface，但 `_validate_run_result()` 通过丢弃 `serialize_run_result_terminal_status()` 返回值完成校验，语义不清晰。正确修复边界是 read model row validation helper。

## Changed Files

- `dayu/host/durable/state.py`
  - `RunRow.queue_policy` 改为 `RunQueuePolicy`。
  - `_decode_run_queue_policy()` 返回 `RunQueuePolicy`。
  - `insert_run()` 在 SQLite 写入边界使用 `run.queue_policy.value`，移除 `parse -> serialize` 重复处理。
  - `_validate_run_for_insert()` 改为显式校验 `RunQueuePolicy` 类型。
- `dayu/host/durable/run_transition.py`
  - `CreateAcceptedRunInput`、`CreateQueuedRunInput`、`CreateRunningRunInput` 及公共创建校验的 `queue_policy` 改为 `RunQueuePolicy`。
  - `_run_accepted_event_request()` 对 typed policy 只在 EventLog payload 文本边界序列化一次。
  - 该文件是 `RunRow` 的直接上游创建边界；为保持 typed durable row contract 与 pyright 一致必须同步收紧。
- `dayu/host/durable/read_model.py`
  - 新增 `_validate_run_result_terminal_status()`。
  - `_validate_run_result()` 使用显式 validation helper；serializer 只负责序列化文本。
- `tests/host/`
  - 新增 `test_run_row_queue_policy_decodes_to_owner_type()`，断言 SQLite 文本读取后 `RunRow.queue_policy is RunQueuePolicy.QUEUE`。
  - 直接构造 `RunRow` 或低层 `Create*RunInput` 的 fixture 改为 `RunQueuePolicy.QUEUE`。
  - public request 仍保留文本 `"queue"`，因为 public input boundary 仍接收文本并在 Host owner 解析。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_state_schema.py::test_run_row_queue_policy_decodes_to_owner_type tests/host/test_durable_schema.py::test_host_runs_queue_policy_check_uses_owner_values tests/host/test_projection_read_model.py::test_read_model_python_validation_rejects_unknown_terminal_status`
  - Result: passed, `3 passed in 0.32s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Source Scan / Propagation Audit

- Typed surface scan:
  - `dayu/host/durable/state.py:287`: `queue_policy: RunQueuePolicy`
  - `dayu/host/durable/state.py:1187`: `_decode_run_queue_policy(...) -> RunQueuePolicy`
  - `dayu/host/durable/run_transition.py`: three low-level create input rows use `queue_policy: RunQueuePolicy`
- Duplicate weak-contract scan:
  - No `serialize_run_queue_policy(parse_run_queue_policy(...))` remains in durable state / transition owner path.
  - `insert_run()` writes `run.queue_policy.value` exactly once at the SQLite boundary.
  - Remaining `parse_run_queue_policy(request.queue_policy)` occurrences are public/admission text-input boundary handling, not durable row revalidation.
- Fixture scan:
  - Direct `RunRow` / low-level `Create*RunInput` fixtures now pass `RunQueuePolicy.QUEUE`.
  - Remaining `queue_policy="queue"` test occurrences are public request fixtures and intentionally stay textual.

## README Decision

`dayu/host/README.md` update constraint was read. The README already documents Host queue policy owner values and fresh schema CHECK. This fix tightens implementation typing at the durable row boundary without changing public API, user workflow, architecture boundary, or stable developer-facing behavior that the README does not already cover. README update not needed.

## Residual Risk

- No blocking residual risk.
- `dayu/host/durable/run_transition.py` changed beyond the initially listed core files because it is the direct upstream constructor boundary for `RunRow`; leaving it as `str` would preserve the weak contract and fail pyright once `RunRow.queue_policy` is typed.
- Public request fields remain textual by design; they are still parsed by the Host queue policy owner before durable admission persists a Run.

## Stop Condition

Implementation report written here. No commit, push, PR, merge, or re-review gate was performed.
