# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S2 Implementation — AgentCodex

## Gate result

- Gate：S2 — OpenAI Tool Identity And Terminal Protocol Normalization
- Status：`implementation-complete`
- Accepted baseline：R3-B plan `d1cdfca4`；S1 `791ed144`
- Scope：仅修改 S2 获准的 4 个 OpenAI adapter production modules、5 个获准测试文件，并新增计划指定的 identity-conflict 测试文件
- Stop：本 artifact 完成后停止；未 commit、未进入 S3、未请求 code review

## First-principles / owner decision

问题动机成立。Tool-call identity、provider terminal shape 与 non-stream arguments wire shape 都在 OpenAI adapter 首次获得完整 provider fact；若 parser/aggregator 在这里合并冲突 identity、推断 `TOOL_CALLS` 或接受 dict arguments，Agent/Host 已无法在不重新解释 provider wire protocol 的情况下恢复可信语义。因此：

- `ToolCallAggregator` 是 index/id/position binding 与 conflict validation 的唯一 owner；
- `_choice_policy.py` 是 stream/non-stream 共用 terminal-shape 规则的唯一 owner；
- SSE/non-stream parser 只在 owner validation 通过后投影 completed/done，不在 caller/downstream 修复；
- non-stream parser 在 transport boundary 只接受 string `function.arguments`，不保留 generic compatibility。

## Production changes

### `dayu/engine/runners/openai/tool_call_aggregator.py`

- 显式 native index 仅接受非 bool、非负 `int`；`-1/-2/True/1.5/"0"` 均记录 fatal `tool_call_invalid_index`，且不回落到 id/synthetic routing。
- 保留 missing index + non-empty id 的 synthetic identity；仅允许 synthetic partial 首次迁移到尚未占用的 native target。
- index、id、position 统一经过 `_resolve_index()` 的 binding/conflict 校验后才写 partial、id table 或 position table。
- position 只服务无 index/id 且已有无歧义 binding 的 continuation；显式 strong identity 在同一数组位置发生变化时把该位置标为 ambiguous，后续 position-only fragment 不再猜测归属。
- synthetic -> occupied target、same id -> two native indices、same native index -> two ids 全部 fatal `tool_call_identity_conflict`。
- 删除旧 partial merge；冲突 delta 在 name/arguments/provider state 写入前返回，不会生成拼接后的 partial。

### `dayu/engine/runners/openai/_choice_policy.py`

- 新增 stream/non-stream terminal wrapper，共用唯一私有 `_validate_terminal_shape()`。
- 成功 response 必须有显式 mapped finish reason，并满足 `has_tool_calls` 当且仅当 finish reason 为 `TOOL_CALLS`。
- missing/null 使用既有 transport-specific missing code；shape mismatch 使用新增 `sse_tool_calls_finish_reason_mismatch` / `non_stream_tool_calls_finish_reason_mismatch`。

### `dayu/engine/runners/openai/sse_parser.py`

- 原始 tool-call dict 先交 aggregator 校验，使显式非法 index 不会在 typed coercion 时被静默丢弃。
- 只有 aggregator 返回 resolved identity 才投影 delta event；position routing不能绕过 conflict owner。
- finalize 在任何 successful completed event 前调用共用 terminal policy；删除 parser 直接强制 `FinishReason.TOOL_CALLS` 的成功赋值。
- identity/terminal fatal 均不产出 `RunnerToolCallsCompletedData` / `RunnerContentCompletedData`，以 protocol error(s) 后唯一 `RunnerDone(ERROR)` 收口。

### `dayu/engine/runners/openai/non_stream_parser.py`

- 在 completed event 前执行共用 terminal policy，`RunnerDone` 直接消费已校验的 provider finish fact。
- 删除 `Mapping` arguments coercion；dict/list/number/bool/null/missing 全部 fatal `tool_call_arguments_not_string`。
- string 仍由 aggregator 校验 JSON；invalid JSON string 保持 `tool_call_arguments_invalid_json`，可解析但非 object 的 string 保持 `tool_call_arguments_not_object`。

## Test changes / negative matrix

- 新增 `tests/engine/runners/openai/test_tool_call_identity_conflicts.py`：覆盖 5 个非法 native index、synthetic positive、same-id/same-index positive、synthetic -> empty target、synthetic -> occupied target、same-id/two-index、same-index/two-id、position positive 后的两类 conflict，以及 controller 指定的 A/native0 + B/synthetic + position-routed fragment + occupied target 反例。
- 反例明确断言没有 `lookupdelete`、arguments/provider state 没有跨 identity 合并、无 successful completed、fatal 在唯一 `RunnerDone(ERROR)` 前。
- 迁移 `test_sse_tool_call_stream.py` 与 `test_non_stream_response.py` 的旧 forcing expectations：bool index、tool calls + STOP、missing tool-call finish 现在均断言 owner-level fatal。
- 迁移 `test_old_protocol_parity_regressions.py`：dict/list/number/bool/null/missing arguments 全部拒绝；补齐 invalid JSON string 与 JSON list/number/bool/null string 的既有 fatal 分类。
- 扩展 `test_stream_non_stream_terminal_parity.py`：tool calls + STOP/LENGTH/CONTENT_FILTER、content + TOOL_CALLS、content/tool shape 的 missing/null 均验证两条 transport fail closed，且 completed event 不先于错误出现。

## Validation

最终验证均在 `source .venv/bin/activate` 后执行：

- controller 指定 node：`pytest tests/engine/runners/openai/test_tool_call_identity_conflicts.py::test_position_routed_conflict_fails_closed_without_merge -q` → `1 passed`
- S2 plan focused matrix（8 files）→ `109 passed`
- 额外完整 OpenAI adapter suite：`pytest tests/engine/runners/openai -q` → `302 passed`
- `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`
- `git diff --check` → pass，无输出

## Source scans

### Exact zero-result scans

- arguments compatibility：`isinstance(arguments, Mapping)` / `json.dumps(dict(arguments))` / `dict arguments preserved` → 无结果
- parser direct forcing：`done_finish_reason = FinishReason.TOOL_CALLS` / `finish = FinishReason.TOOL_CALLS` → 无结果
- partial merge：旧 name / arguments / id merge expressions → 无结果
- 四个 production owner module 的 `OLD` / compatibility flag 人工复核 → 无 production compatibility branch

### `FinishReason.TOOL_CALLS` semantic classification

Scan 仅命中 `_choice_policy.py` 两处：

1. `_FINISH_REASON_MAP` 中 `"tool_calls": FinishReason.TOOL_CALLS`：显式 provider wire mapping；
2. `_validate_terminal_shape()` 中 `finish_reason is FinishReason.TOOL_CALLS`：共用 fail-closed presence/mismatch 比较。

`sse_parser.py` 与 `non_stream_parser.py` 零命中；不存在 parser 直接赋值、默认或推断成功 `TOOL_CALLS`。

## README / design trigger decision

- `dayu/engine/` 与 `tests/` 修改分别命中 `dayu/engine/README.md`、`tests/README.md` 触发规则；plan 已明确两者和 `docs/engine/design.md` 必须在 R3-B implementation 后同步。
- S2 gate 的 allowed documentation 仅为本 implementation artifact；统一 design/README 同步属于计划中的 S3/aggregate documentation closure。本 gate 不提前修改 README/design，避免跨 slice 扩 scope。
- Host、根 README、`dayu/README.md`、Fins/Config README 不触发：Host durable/ingest、分层、安装/CLI/用户工作流和对应 production owner均未变化。

## Unchanged scope

- 未修改 Agent、Host、contracts/runtime schema、error classifier、Runner identity、HTTP/retry、provider marker、Service/CLI/Fins/Web/Documents。
- 未删除合法 synthetic identity 或无歧义 position continuation。
- 未新增 provider capability flag、provider list、compatibility shim、Host repair 或 caller-side fallback。
- 未修改未获准测试；`test_protocol_error.py`、`test_event_flow_ordering.py` 仅作为 focused matrix 验证目标运行。
- 未 commit、未 push、未进入 S3、未请求 code review。

## Residual risk

无新增未分类 residual。计划已接受的“synthetic delta preview 使用负内部 key”保持不变，并由现有/新增矩阵覆盖；若未来要改变公开 delta index contract，必须进入独立 Engine contract WU，不能由 Host 修复。
