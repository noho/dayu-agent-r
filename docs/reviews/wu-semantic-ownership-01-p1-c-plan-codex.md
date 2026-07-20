# WU-SEMANTIC-OWNERSHIP-01 P1-C Plan Delivery - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-C`
- Gate: implementation plan only
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- Umbrella status: not final closeout. P1-C 后仍需 P2-A、P2-B、P2-C 与后续 full-repository deepreview。

## Motivation Check

动机仍成立，但 severity 需要精确限定为 P1。

直接证据：

- `dayu/config/prompts/scenes/conversation_compaction_user.md` 仍要求 compactor 输入 `trace_kind=user_visible_run_state`，并要求输出 `evidence_kind=tool_result|tool_source_text|accepted_evidence_material`。
- `dayu/runtime/tool_call_projection.py` 仍由 runtime 提供 Host-governance 默认 LLM 文案：“工具调用已被宿主取消。”和“不要把本次取消视为业务失败...”。
- `dayu/fins/tools/download_tools.py`、`upload_tools.py`、`preprocess_tools.py` 仍在 ToolFailedOutcome message 中写“未进入等待状态”。
- `dayu/fins/tools/fins_tools.py` 与 `read_runtime_helpers.py` 仍在 cancellation hint 中写“后续调度”。
- `dayu/host/tool_duplicate_governance.py` 的 duplicate awaiting fanout 默认消息仍写“等待状态 / 等待结果”，但当前初步路径显示 awaiting fanout 分支直接返回 prior awaiting outcome，message 主要进入 duplicate decision / diagnostic；plan 要求 implementation 先确认是否进入 LLM context。
- Plan review controller adjudication 后，`dayu/host/run_input.py` 中 `_memory_evidence_fact_message()` 与 fallback codec 的 `evidence_kind=...` 渲染已升级为 S1 确定性 cleanup 项，因其进入 `SystemMessage`，不再等待 S0 判定。

严重性判断：

- 这是 LLM-facing semantic ownership 问题，不是当前已知 durable correctness 问题，因此 P1 合理。
- “等待工具结果返回”本身不必 blanket delete；当它只表达长事务工具稍后返回结果且不要求模型理解 Host wait governance 时，可以保留或轻微业务化。

## Owner Boundary Decisions

- Compaction LLM-facing schema owner：Host compaction / compact material boundary。Host 可以保留 typed validation，但不能把 internal enum 原样交给 LLM 分类。
- Fins tool schema/outcome owner：Fins tool callable / tool definition。失败和取消文案应在工具 owner 边界改成业务可读文本，不在 Host projection 下游掩盖。
- Runtime cancelled helper owner：runtime 只拥有层中立 outcome 构造能力，不拥有 Host-governance LLM 文案；调用方负责提供业务可读 message/hint。
- Accepted-result projection owner：沿用 P1-A `accepted_result_projection.py`，P1-C 不重写 query/status/source/result truth。
- Lifecycle/cancel durable owner：沿用 P1-B Host lifecycle/cancel contract，P1-C 不改 durable truth。

## Plan Shape

主计划切为 4 个 slice：

- S0：root-cause confirmation 与 exposure classification，覆盖 duplicate REUSE / HINT / HARD_STOP / REQUIRE_JUSTIFICATION / DURABLE_MISSING 进入 `ToolFailedOutcome` 的路径，并用 litmus test 区分“等待工具结果返回”这类合法行为说明与治理泄漏。
- S1：compaction LLM-facing schema cleanup，包含 `run_input.py` memory `evidence_kind=...` 确定性清理、Host derivation 策略选择、旧 compact artifact 无兼容读取策略。
- S2：Fins / runtime / Doc / Web / tool outcome 文案 cleanup，包含 `ToolBusinessCancelled` optional fallback/docstring、Doc/Web “宿主取消”、Fins/Doc/Web cancellation hint 一致性。
- S3：validation、README decisions、propagation audit，并增加 P1-A accepted-result projection contract preservation scan。

该切分避免扩大到 P2-A/P2-B/P2-C，也避免用文案掩盖 P1-A/P1-B typed contracts。

## Validation Baseline

Plan 要求 implementation 后运行：

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
source .venv/bin/activate && rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
source .venv/bin/activate && pyright
git diff --check
```

## README Decisions

Plan 中已列明 README 触发规则：

- `dayu/host/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`、`tests/README.md` 必须按实际修改检查。
- 根 `README.md` 与 `dayu/README.md` 默认不触发，除非 implementation 改变用户可见 workflow 或分层/装配边界。

## Current Turn Validation

本轮只新增 plan 文档，未实现 P1-C，未修改生产代码或测试。按计划产出后的本轮验证只需检查文档 diff：

- `git diff --check`

Plan review fix turn 只更新 plan / delivery / fix artifact，仍不实现代码、不运行 implementation tests。

## Residual Risks for Implementation

- `evidence_kind` 如仍作为 durable compact candidate typed value 存在，implementation 必须保证它不再由 LLM 分类，也不在 LLM-facing rendering 中泄漏内部 enum。
- `run_input.py` memory `evidence_kind=...` 已确认 LLM-facing，implementation 不得再把它列为待判定项。
- duplicate awaiting fanout message 当前是否 LLM-facing 需要 S0 用代码路径和 scan 确认；REUSE / HINT / HARD_STOP / REQUIRE_JUSTIFICATION / DURABLE_MISSING 则必须按 `ToolFailedOutcome` 可能路径分类，不得仅凭字符串存在就改行为。
- cancellation 文案必须同时覆盖 Fins / Doc / Web；若不抽取共享中性 helper/constant，implementation artifact 必须做一致性审计。
- `poll` / `adapter` 在内部 docstring、runtime config 或 tests 中可能是精确内部术语；implementation scan 必须分类，不应为了清 grep 改坏内部可维护性。
