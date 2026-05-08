# Host P5 huge_echo Plan Note

## 总控决策

用户二次人工 review 后，P5 smoke tool 目标改为 `huge_echo`。旧 `double_echo` 临时方向废弃；相关
`utils` 局部 smoke helper、测试与 review 不能作为当前通过证据。

当前 P5 plan 必须按以下口径修订并待复审：

- 手工 smoke 主路径真实使用 `mimo-v2.5-pro-plan` provider，向模型发送 prompt，并由模型通过 LLM tool calling
  调用 `huge_echo`。
- `huge_echo` 由公共 `@tool(..., truncate=ToolTruncateSpec(...))` 声明 schema、executor binding、Host truncate
  spec 与 display metadata。
- `huge_echo` 默认返回足够大的文本；辅助测试可覆盖足够大的 list / JSON wrapper，确保 ToolRuntime truncate
  稳定触发。
- tool calling 必须走 `ToolRuntimeToolExecutor -> InMemoryToolRuntime -> huge_echo executor`，truncate / cursor /
  fetch_more facts 必须由真实 Host ToolRuntime 产生。
- 成功 `fetch_more` 必须通过 Host public `get_tool_fetch_more_handle` / `fetch_more_tool_result`，并发生在 owner run
  terminal 前；真实模型若过早 final，harness 必须 gating 后先补读再允许 terminal。
- P5 integration 测试可以使用 fake provider 覆盖不可联网路径；手工 smoke 缺 `MIMO_PLAN_API_KEY` 或 provider
  配置时必须 clear failure，不能把 fake 当成功。
