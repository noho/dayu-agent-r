# WU-CLI-SMOKE-01 Tool Evidence Request Memory Controller Adjudication

## Scope

GitHub Issue #176：Conversation Memory 中 `TOOL_RESULT_ACCEPTED` 的 LLM-facing evidence 必须带足够 request / query 语义，使 raw tool outcome 在下一轮可解释、可复用。

## Controller Decision

- `TOOL_AWAITING` 是 Host / ToolRuntime 等待治理事实，对模型不可见；不得进入 Conversation Memory。
- `TOOL_RESULT_ACCEPTED` 的 memory evidence 必须通过 accepted evidence envelope 回读对应 `TOOL_CALL_REQUESTED` request atom。
- `semantic_query_text` 是 Conversation Memory 的唯一 request / query 语义真源。缺失时输出低信号文本，不从 raw tool arguments 合成 LLM-facing query。
- request/result pairing 必须 fail-closed：session、run、attempt、execution、event class/type、tool call id、tool name、normalized arguments digest 任一不一致，都不回读 request query。
- DS final re-review 提到的低信号文本重复常量已收敛到 `dayu.host.memory.ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。

## Review Results

- AgentMiMo final re-review: PASS, no findings.
- AgentDS final re-review: PASS. Low finding for duplicate low-signal text was fixed by the controller; design line about compact evidence arguments fallback is outside this Conversation Memory follow-up and remains owned by future compact/material cleanup if needed.

## Validation

- `pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py -q` -> 87 passed.
- `pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q` -> 323 passed.
- `pyright` -> 0 errors.
- `git diff --check` -> passed.
