# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main` (staged changes relative to branch HEAD)
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-mimo.md`
- Included scope: Slice 1 durable tool-call request atoms implementation + control doc gate bookkeeping. Staged diff of 11 files: `dayu/host/durable/schema.py`, `dayu/host/tool_runtime.py`, `dayu/host/engine_ingest.py`, `dayu/host/payload_resolution.py`, `dayu/host/README.md`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_durable_schema.py`, `tests/README.md`, `docs/host/issues-implementation-control.md`.
- Excluded scope: design.md changes (committed in Slice 0), review artifact (implementation codex), unstaged changes.
- Parallel review coverage: 无

## Review Method

沿真实代码路径走读：`ToolFactAcceptCandidate` -> `_tool_call_requested_event_request` -> `_tool_call_request_payload_plan` -> `PayloadStore().write_sqlite_payload` / inline -> `EventLog.append_event`；以及读取路径 `tool_call_request_atoms` -> `_read_arguments_json` / `_read_semantic_query` -> `ToolCallRequestAtoms`。逐条检查 digest 同源、冷热分离阈值、descriptor kind、fail-closed、事务边界、类型严格性。

## Findings

### 1-NB-[低]-storage kind 字符串常量在两个模块重复定义

- **入口/函数**: `tool_runtime.py` 与 `payload_resolution.py` 的模块级常量
- **文件(行号)**: `dayu/host/tool_runtime.py:200-204` 与 `dayu/host/payload_resolution.py:22-29`
- **输入场景**: 任何修改 `inline_json` / `payload_descriptor` / `absent` / `inline_text` 字符串值的维护者
- **实际分支**: 两个模块各自定义了 `_ARGUMENTS_STORAGE_INLINE_JSON`、`_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR`、`_SEMANTIC_QUERY_STORAGE_ABSENT`、`_SEMANTIC_QUERY_STORAGE_INLINE_TEXT`、`_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR` 共 5 个同值常量
- **预期行为**: 按 CLAUDE.md "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"，公共字符串常量应有单一真源
- **实际行为**: 写入端（`tool_runtime.py`）和读取端（`payload_resolution.py`）各自独立定义相同常量
- **直接证据**: `tool_runtime.py:200` 定义 `_ARGUMENTS_STORAGE_INLINE_JSON = "inline_json"`；`payload_resolution.py:22` 定义 `_ARGUMENTS_STORAGE_INLINE_JSON = "inline_json"`
- **影响**: 当前值一致，无行为差异。但未来修改 storage kind 字符串时需同步两处，遗漏会导致写入的 kind 值无法被读取端识别，表现为 `HostDurableError("tool call arguments storage kind is invalid")`
- **建议改法和验证点**: 将 5 个 storage kind 常量移入 `dayu/host/durable/schema.py`（与 `TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` 同模块），两端 import 同一真源。验证：grep 确认无残留本地定义
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Checks Performed

以下逐项检查均通过，未发现实质性问题：

1. **accepted arguments 与 normalized_arguments_digest 同源**: `_tool_call_request_payload_plan` 第 3341 行校验 `arguments_payload_digest != candidate.call.normalized_arguments_digest` 时抛异常；`_accepted_arguments_digest` 使用 `sha256_digest_json({"arguments": dict(arguments)})`，与 `_normalized_arguments_digest` -> `_accepted_arguments_digest(call.arguments)` 使用同一 canonical preimage。读取端 `tool_call_request_atoms` 第 136 行再次校验 `arguments_payload_digest != normalized_digest`，第 143 行校验 `sha256_digest_json(arguments_json) != arguments_payload_digest`。三重校验链完整。

2. **inline_json vs payload_descriptor 阈值与 fail-closed**: 写入端第 3349 行 `arguments_size_bytes <= transaction.payload_inline_threshold_bytes` 决定 inline/descriptor；读取端第 236-257 行严格 dispatch `_ARGUMENTS_STORAGE_INLINE_JSON` / `_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR`，其它值 `raise HostDurableError`。descriptor 路径先校验 descriptor kind（`_validate_descriptor_kind`），再校验 payload digest（`sqlite_payload_object`），最后校验 size bytes。fail-closed。

3. **semantic query 独立于 semantic_input_digest**: `_semantic_query_payload_plan` 从 `candidate.call.semantic_query_text` 取值，与 `semantic_input_digest`（来自 `candidate.idempotency.semantic_input_digest`）完全独立。缺失时 `storage_kind="absent"` 并校验无 text/ref/digest 残留。digest 使用 `sha256_digest_json({"semantic_query_text": query_text})` 计算，与 `semantic_input_digest` 使用不同 preimage。

4. **PayloadStore 写入同事务**: `_tool_call_request_payload_plan` 接收 `transaction: HostTransaction` 参数，`PayloadStore().write_sqlite_payload(transaction, ...)` 将 descriptor 写入同一事务。`_tool_call_requested_event_request` 由 `DefaultHostToolFactAcceptPort.accept_tool_fact` 调用，该方法在同一个 `transaction_runner.run_write` 回调内完成 `append_event` + descriptor 写入。同事务保证。

5. **ToolAcceptCall.accepted_arguments optional default**: 默认 `None`；`_required_accepted_arguments` 在 `None` 时抛 `HostPayloadReferenceError`。生产路径 `_tool_fact_accept_candidate` 和 `_tool_fact_reuse_accept_candidate` 均显式传入 `call.arguments`。`__post_init__` 中仅在 `accepted_arguments is not None` 时校验 digest 一致性，允许 fake ack 测试省略。设计意图合理，fail-closed 在写入时。

6. **tool_call_request_atoms 类型严格与 fail-closed**: 返回 `ToolCallRequestAtoms` frozen dataclass，所有字段类型明确（`str`、`Mapping[str, JsonValue]`、`str | None`）。不使用 `Any`、`object` 或无类型参数。每个校验失败点抛 `HostDurableError`，无静默降级路径。

7. **Engine preview 仍是 diagnostic**: `engine_ingest.py` 第 4247-4249 行新增 `common["normalized_arguments_digest"] = sha256_digest_json({"arguments": data.arguments})` 仅写入 preview payload（`EventClass.PREVIEW`），不写入 canonical EventLog。preview 不成为 truth。

8. **Tool Trace 测试验证大参数不展开**: `test_tool_trace_does_not_inline_large_tool_call_arguments` 写入 payload descriptor（`arguments_storage_kind="payload_descriptor"`），append `TOOL_CALL_REQUESTED` 事件，运行 trace，断言 cold JSONL 中包含 `arguments_digest` 但不包含 `"x" * 128`（即大参数正文未展开）。测试有效。

9. **README 准确性**: `dayu/host/README.md` 新增行描述 `TOOL_CALL_REQUESTED` accepted request atom、冷热分离与 descriptor kind，与实现一致。`tests/README.md` 更新覆盖描述，包含 request atom 测试、Engine preview digest 和大参数 descriptor 边界。无未来计划。

10. **未越界实现 Slice 2-7**: 未修改 `dayu/host/run_input.py`、`dayu/host/tool_trace.py`、`dayu/host/compaction_evidence.py`、`dayu/host/llm_compaction.py`、`dayu/engine/` 下任何文件。未引入 `RUNNER_CALL_INPUT_ASSEMBLED` event type 或 runner-call manifest。`docs/host/design.md` 改动已在 Slice 0 commit 83cf38d8 中。

## Open Questions

无。

## Residual Risk

- `ToolAcceptCall.accepted_arguments` 对 fake ack 低层测试允许缺省。若未来有新调用方构造 `ToolAcceptCall` 时遗漏 `accepted_arguments`，会在写入 `TOOL_CALL_REQUESTED` 时才失败（`HostPayloadReferenceError`），而非构造时。当前所有生产路径均已显式传入，风险可控。
- Tool Trace 当前只验证大参数正文不展开；新增 atom 的 hot projection signal（如 `arguments_storage_kind`、`arguments_payload_ref`）未在本 slice 验证是否进入 trace hot row，属于后续 OBS 范围。
- Compact evidence 的 `query_text` 消费尚未接入 `tool_call_request_atoms()`，属于后续 Slice 5。

## Completion Report

- artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-mimo.md`
- verdict: **pass-with-findings**
- blocking findings: 0
- non-blocking findings: 1（storage kind 常量重复定义，低严重度）
- tests considered: `test_toolruntime_accept_barrier.py`（117 tests 含 4 个新增 request atom 测试）、`test_engine_ingest_mapping.py`、`test_tool_trace_projection.py`（含新增大参数 descriptor 测试）、`test_durable_schema.py`（含新增 descriptor kind 稳定性测试）、`test_toolruntime_executor.py`（23 回归测试）
- residual risks / open questions: 见上方 Residual Risk 节
