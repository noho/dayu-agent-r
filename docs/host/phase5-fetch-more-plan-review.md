# Host P5 Fetch More Plan Review

## 结论

原始 review 结论：有条件通过。

Revised P5 plan 的主线已经准确表达用户刚刚确认的目标：模型在同一个 run 内先通过 LLM tool calling 调用
`huge_echo`，Host ToolRuntime 按 `ToolTruncateSpec` 截断并把 LLM 可理解的
`truncation.next_action="fetch_more"` / `fetch_more_args={cursor, scope_token, limit?}` 注入 tool result；
`fetch_more` 作为最小 framework tool 暴露给模型；模型再发起普通 `fetch_more` tool call，Engine 只按普通
tool call 处理，Host ToolExecutor / ToolRuntime 拥有 cursor、scope、runtime facts 与路由。

P5 plan、migration plan 与 design 的新增 P5 路径总体守住了“不是第二轮 memory、不是 smoke 脚本代调
Host public fetch_more、不是完整 ToolRegistry 治理”的边界。但原始 review 当时判断文档包仍有两处旧口径冲突，
建议在进入实现前修正，避免 implementation Agent 或后续 P5.5 review 误读。

修复后状态：两个 finding 已完成文档修正，并在下方保留原始 evidence 供追溯；当前条件项已清零，可进入复核通过确认。

## Findings

### P1 重要：[已修复] `design.md` 仍保留 scope_token Engine 边界的 P2 旧口径，和 P5 LLM-facing hint 冲突

修复状态：已在 `docs/host/design.md` 的 ToolRuntime 补读边界段改成阶段化口径：P2 Host public handle 不写入
EventLog / memory / 日志 / smoke 输出；P5 LLM-facing truncated tool result 可短期携带
`truncation.fetch_more_args.scope_token`，仅用于同一 run 内 framework `fetch_more` tool call；Engine 仍只透传普通
tool result JSON / tool args，不拥有或解释 token。

修复前原证据：

- `docs/host/design.md` 原 ToolRuntime 补读边界段写明 `scope_token` 只通过非 EventLog handle 交付，且不进入
  `RunEvent`、Engine 侧投影或日志。
- 同一文件的 P5 目标路径又要求 Engine 注入给模型的截断 tool result
  包含 LLM-readable truncation hint，并包含
  `truncation.fetch_more_args = {cursor, scope_token, limit?}`。
- OLD 明确只把 `next_action` 与 `fetch_more_args` 投影给 LLM；`project_for_llm()` 只保留这两个可执行字段，
  见 `/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:226`、`:277-337`。
- OLD `fetch_more` schema 说明模型必须直接使用最近一次截断结果里的
  `truncation.fetch_more_args.cursor` 与 `scope_token`，见
  `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:250-285`。

影响：

P5 需要向 LLM 暴露可执行补读参数；`scope_token` 不进 EventLog、memory、日志、README 示例和 smoke 输出是对的，
但如果不限定为 P2 当前旧状态，会诱导实现继续把 token 从 LLM-facing tool result
里拿掉。这样模型即使看到 `next_action=fetch_more`，也无法按 framework tool schema 成功补读。

建议：

把 `design.md:898-901` 改成带阶段限定的表述：P2 的 Host public handle 不把 `scope_token` 写入 EventLog /
日志 / memory；P5 的 LLM-facing truncated tool result 可以短期携带 `fetch_more_args.scope_token`，仅用于同一
run 内模型发起 framework `fetch_more`。同时明确该 token 仍不得进入 RunEvent、memory projection、smoke 日志或
文档示例。

### P2 中：[已修复] `phase5_5-early-scan.md` 仍把 LLM-facing `fetch_more` 描述为后续缺口，并残留 Host public 补读成功口径

修复状态：已在 `docs/host/phase5_5-early-scan.md` 的结论、缺口表、P5/P5.5 建议和阻塞分类中同步为 revised
P5 口径：LLM-facing framework `fetch_more` 已由 revised P5 承接，P5 主用例必须是模型经 Engine tool loop
发起 framework `fetch_more`；Host public `fetch_more_tool_result()` 只作为底层边界和 terminal 后 negative path。

修复前原证据：

- `docs/host/phase5_5-early-scan.md` 原结论段已承认后续 P5 plan 修订为恢复最小 framework `fetch_more`
  tool 与 truncation hint。
- 但原缺口表仍写
  “LLM-facing `fetch_more` schema / `fetch_more_args` projection” 来源仍按早期 P2/P5 非目标处理，当前判断和
  建议归属仍把它放在后续 phase。
- 原 P5 必须进入项仍保留旧的 Host public 预终态补读说法，没有表达
  P5 success path actor 必须是模型发起的 LLM `fetch_more` tool call。
- Revised P5 plan 已在 `docs/host/phase5-plan.md:24-40`、`:95-121`、`:137-164`、`:650-658`
  明确恢复 LLM-facing hint、framework `fetch_more` schema，并要求测试不能用
  `harness.fetch_more_tool_result()` 替代 success path。

影响：

这不是 P5 主 plan 的阻断问题，但会让 P5.5 / 后续总控读到相反结论：一边说 P5 已承接模型自主补读，另一边又说
LLM-facing framework 补读仍被留给 P5.5/P6。更严重的是，旧的 Host public 预终态补读口径会把
脚本代补读口径留在 review 证据里，削弱“模型不发 fetch_more tool call 就必须失败”的验收要求。

建议：

更新 `phase5_5-early-scan.md`：把该缺口表项标为“已由 revised P5 承接，P5.5 只需复核是否落地”；把 P5 必须进入项改为
“pre-terminal model-initiated framework `fetch_more` via Engine tool loop”。Host public
`fetch_more_tool_result()` 只能描述为 framework tool 路由复用的底层边界和 terminal 后 negative path，不能作为 P5
success path actor。

## 复核范围

- 已复核：
  - `docs/host/phase5-plan.md`
  - `docs/host/design.md`
  - `docs/host/migration-plan.md`
  - `docs/host/phase5-tool-declaration-plan-review.md`
  - `docs/host/phase5_5-early-scan.md`
- OLD 对照：
  - `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py`
  - `/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py`
  - `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py`
  - `/Users/leo/workspace/dayu-agent/tests/engine/test_truncation_manager.py`
- 当前 NEW 辅助对照：
  - `dayu/contracts/tool_schema.py`
  - `dayu/host/_tool_runtime.py`
  - `tests/host/test_phase2_tool_runtime_truncation.py`

## 已确认通过项

- Revised P5 plan 准确表达“同一 run 内多次 LLM tool calling”：`huge_echo` -> truncated tool result hint ->
  framework `fetch_more` -> final answer，不是第二轮 memory，也不是 Host-side continuation。
- P5 plan 保留 OLD 多策略截断要求：`text_chars`、`text_lines`、`list_items`、`binary_bytes`，
  以及 `target_field` / `field_path`。
- P5 plan 明确只恢复最小 framework `fetch_more` schema、LLM-facing truncation hint 与 Host ToolRuntime 路由，
  不引入完整 ToolRegistry、权限治理、middleware、重复调用治理或 Service catalog。
- Engine / Host 边界清楚：Engine 只看到普通 `huge_echo` / `fetch_more` tool call 与普通 tool result；
  Host owns cursor、scope token、single-use、TTL、lineage、runtime facts 与 routing。
- P5 plan 的测试和 smoke acceptance 已明确：如果模型没有发出 `fetch_more` tool call，而由脚本直接调用
  `harness.fetch_more_tool_result()` 代补读，必须判失败。

## 建议

1. 先修正文档冲突，再进入实现；尤其是 `scope_token` 的“LLM-facing 可见”和“EventLog / memory / 日志不可见”
   必须写成两个不同边界。
2. 后续 code review 必须直接查 fake provider / real-provider smoke：success path 是否真的出现模型发起的
   `fetch_more` tool call，以及该 call 是否经过 Engine tool loop 与 Host ToolRuntime framework route。
3. P5.5 后续只复核 revised P5 是否落地，不应再把 LLM-facing `fetch_more` 当作未安排的新 phase。

## 复核结论

通过。两个条件项已修复，无新增 finding。
