# WU-CM-01-F02 Slice 5 Implementation Artifact

## Gate

- gate：implementation
- work unit：WU-CM-01-F02 Compact evidence query readability quality closeout
- slice：Slice 5 Compact Evidence Query Readability
- agent：Codex
- status：implemented
- artifact path：`docs/reviews/wu-dur-obs-cm-closeout-slice5-implementation-codex.md`

## Scope

本次 implementation 只修改允许范围内文件：

- `dayu/host/compaction_evidence.py`
- `tests/host/test_compaction_operation.py`
- `dayu/host/README.md`
- `tests/README.md`

未修改 compact candidate output schema，未实现 Slice 6 prompt rewrite，未实现 Slice 7 public smoke closeout。

## First-Principles Judgment

该 slice 动机成立。`EvidenceReadableItem.tool_name` 已承担工具身份，但旧 `query_text` 仅输出 `tool_call_id=...`，不能告诉 compactor “该 evidence 为什么被调用、参数是什么”。在买方财报分析 Agent 中，这会迫使 LLM 从工具结果内容反推查询意图，违反 durable truth 同源约束。

正确修复不应猜 prompt、不应从工具结果内容推断 query，也不应把 Host refs / digests 投影给 LLM。Slice 1 已提供 `TOOL_CALL_REQUESTED` durable request atoms；本 slice 的最小实现是由 accepted evidence envelope 的 `tool_call_requested_event_ref` 回读该 atom，经 digest / tool identity 同源校验后渲染 bounded query text。

## Implementation Summary

- `_readable_query_text()` 改为读取 `TOOL_CALL_REQUESTED` durable request atom：
  - 通过 `tool_call_requested_event_ref` 读取 request event。
  - 复用 `tool_call_request_atoms()` 读取 inline / descriptor arguments 与 optional semantic query，并复用其 descriptor kind / digest 校验。
  - 校验 request atoms 的 `tool_call_id`、`tool_name`、`normalized_arguments_digest` 与 accepted evidence envelope 同源。
- query 渲染策略：
  - 优先使用 durable `semantic_query_text`。
  - 否则渲染有界 canonical arguments JSON，文本前缀为 `工具参数: `。
  - query_text 不重复 tool identity，不包含 tool_call_id、EventLog id、payload ref、digest 或 cursor。
  - 长文本通过 `_READABLE_QUERY_TEXT_MAX_CHARS` 与 `[truncated_query_text]` 截断，避免把长 arguments 反复注入每个 chunk。
- limited-signal 策略：
  - request ref 缺失、request event 缺失、atom 不可验证或 evidence/request 不同源时，输出结构化业务中性文本：`状态=limited_signal；原因=...；说明=...`。
  - limited-signal 文本不暴露 Host 内部 refs / digests。
- chunking 行为：
  - chunk label 仍由 compact material pack 负责。
  - 同一 evidence 被拆成 `E1.1` / `E1.2` / `E1.3` 时，各 chunk 复用同一 base query_text，chunk ordinal 不进入 query_text。

## Tests

新增或更新的 focused coverage：

- durable arguments fallback：selected evidence query_text 从 `TOOL_CALL_REQUESTED` arguments atom 渲染 canonical arguments JSON，不再输出 `tool_call_id=...`。
- semantic query priority：存在 durable semantic query 时优先输出该业务可读 query。
- missing durable atom limited-signal：缺 request atom 时输出结构化 limited-signal，且不包含 tool call id 或 event id。
- chunking same-source：同一 durable request 被 chunk 后，各 chunk query_text 稳定一致，chunk ordinal 只存在于 prompt-local label。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
  - result：49 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - result：0 errors, 0 warnings, 0 informations
  - note：pyright reported an available version update only
- `git diff --check`
  - result：passed

## README Sync Decision

- `dayu/host/README.md` 已同步：说明 compact evidence `query_text` 消费 `TOOL_CALL_REQUESTED` durable request atom，semantic query 优先，arguments fallback，缺失时 limited-signal，不退化为裸 tool call id。
- `tests/README.md` 已同步：测试覆盖清单补充 accepted evidence query_text 消费 durable tool-call request atoms。

## Residual Risks

- fixed in current slice：旧 `query_text` 退化为裸 `tool_call_id=...` 的 production path 已修复。
- fixed in current slice：缺失 durable request atom 的静默退化已替换为 structured limited-signal。
- fixed in current slice：chunked evidence 复用 base query_text 已有 focused test 覆盖。
- covered by later approved slice：Slice 6 prompt rewrite 仍需让 compactor prompt 更明确地区分 `tool_name`、`query_text` 与 limited-signal 文本。
- covered by later approved slice：Slice 7 public smoke closeout 仍需覆盖完整 public smoke 质量验收。

## Completion Status

status：implemented
