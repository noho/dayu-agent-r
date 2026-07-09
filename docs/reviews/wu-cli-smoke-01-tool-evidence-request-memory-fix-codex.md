# WU-CLI-SMOKE-01 Tool Evidence Request Memory Fix

## 动机确认

问题成立。`TOOL_RESULT_ACCEPTED` 的 raw tool outcome 可能只有 `{"total":0,"documents":[]}` 这类低语义结果；如果 Conversation Memory 只投影结果，不带对应 request / query 语义，后续 LLM 无法判断这是哪个查询的结果，也容易把结果误用于错误任务。

同时，总控裁决成立：`TOOL_AWAITING` 是 Host / ToolRuntime 等待治理事实，不属于 LLM-facing memory schema；有无 awaiting 机制不能改变第二轮 memory 语义。

## Root Cause

直接代码证据：

- `dayu/host/memory.py` 原先在 `_selected_evidence_text` 中只读取 `accepted_tool_raw_outcome_text_from_payload(event.payload)`，因此 accepted tool evidence 缺少 request / query 语义。
- `dayu/host/tool_runtime.py` 已在 `TOOL_CALL_REQUESTED` payload 中保存 `semantic_query_text` / `semantic_query_payload_ref`，且 `TOOL_RESULT_ACCEPTED` 的 accepted evidence envelope 已包含 `tool_call_requested_event_ref`、工具名、tool call id 和 arguments digest。
- `dayu/host/payload_resolution.py::tool_call_request_atoms(transaction, request_row)` 已提供 digest-checked request atom 读取能力。

根因是 Memory projection 在处理 `TOOL_RESULT_ACCEPTED` 时没有回读对应 `TOOL_CALL_REQUESTED` request atom，导致 LLM-facing evidence item 只剩 raw result，不自解释。正确边界不是把 query 正文复制进 `TOOL_RESULT_ACCEPTED` envelope，而是在 projection 阶段通过 envelope 中的 request 引用回读已校验的 LLM-safe query 语义。

## 实现

- 保持 `AcceptedEvidenceToolQuery` 只承载 request event ref 与 digest，不复制完整 `semantic_query_text`，避免破坏冷热 payload/ref digest 边界。
- 在 durable memory projection 中新增 `_MemoryProjectionPayloadView`，把 digest-checked result payload 与 LLM-safe `evidence_query_text` 作为 typed projection input 传给纯 memory projector。
- `TOOL_RESULT_ACCEPTED` projection 现在：
  - 从 accepted evidence envelope 取得 `tool_call_requested_event_ref`。
  - 读取对应 `TOOL_CALL_REQUESTED` row。
  - 校验同 session、run、attempt、execution、event type、tool name、tool call id 和 arguments digest。
  - 通过 `tool_call_request_atoms(...)` 读取 `semantic_query_text`。
  - 将工具名、query 文本与 `raw_tool_outcome` 合并为自解释 memory evidence。
- `semantic_query_text` 缺失时直接返回低信号文本 `查询语义不可用；参数未安全展开。`。Memory projection 不根据 raw tool arguments 合成 LLM-facing request / query 语义。
- `TOOL_AWAITING` 仍不进入 memory event filter，也不产生 LLM-facing memory。
- 更新 `dayu/host/README.md` 与 `tests/README.md`，记录 request atom 回读语义。

## 测试

新增/更新覆盖：

- ambiguous raw outcome 仍能在 memory text 中携带 request/query 语义。
- durable memory projection 从 `TOOL_CALL_REQUESTED` row 回读 semantic query。
- 无 semantic query 时直接低信号降级，不泄露 ticker、arguments、event id、tool call id、payload/artifact/digest/wait/awaiting/poll/cancel 等内部或参数语义。
- unsafe 参数在无 semantic query 时同样低信号降级，不泄露 secret、本地路径或参数 key。
- `TOOL_AWAITING` 不进入 memory filter。
- result envelope 不携带 `query_text`，防止 query 正文复制进热 payload。

## Review Fix

总控裁决要求 F1 不 deferred：`TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED` 不能只按 session/event type/tool/digest 同源，还必须按 run / attempt / execution 同源。已在 `_tool_result_query_text` 中补充 `run_id`、`attempt_id`、`execution_id` 全量一致校验；任一不一致时返回 `查询语义不可用；参数未安全展开。`，不回读 request query。

补充测试：

- 参数化覆盖 `run_id`、`attempt_id`、`execution_id` 任一错配时 fail-safe，不泄露 request query、request event id、result event id、tool call id 或错配执行 id。
- 覆盖 `tool_call_requested_event_ref=None` 时 fail-safe，不读取同事务中存在但未被 envelope 引用的 request row。
- DS re-review 裁决后，生产边界收敛为只使用 digest-checked `TOOL_CALL_REQUESTED.semantic_query_text`；删除 arguments fallback，不再用参数子串黑名单猜测 LLM-facing query。
- 参数化覆盖剩余 fail-early 分支代表样例：request row 不存在、session mismatch、event class 非 canonical、event type 非 `TOOL_CALL_REQUESTED`、request atom 解析失败、tool call id mismatch、tool name mismatch、arguments digest mismatch。
- Final re-review 后，低信号 query 文本收敛到 `dayu.host.memory.ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 单一常量；durable projection 与测试复用该真源，避免 LLM-facing 文本在多个生产模块漂移。

Review fix 验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py -q
source .venv/bin/activate && pyright
```

结果：

- `79 passed`
- `pyright` 0 errors

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
source .venv/bin/activate && pyright
git diff --check
```

结果：

- `311 passed`
- `pyright` 0 errors
- `git diff --check` 通过

## 剩余风险

- 无 `semantic_query_text` 时不再从 raw arguments 生成 query，可能牺牲少量参数连续性，但边界更清晰：request/query semantic 的生产真源只来自 `TOOL_CALL_REQUESTED.semantic_query_text`。
- 本修复只处理 Conversation Memory 的 accepted evidence projection；compact material 已有独立 request atom 回读路径，本次未扩展其 fallback 文本策略。
