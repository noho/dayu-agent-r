# WU-TOOLS-01-F01-02-R3 Plan Review Controller Adjudication

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-review-ds.md`
- Controller decision: enter plan fix gate

## 总体裁决

两路 review 均确认 R3 动机成立、范围正确、Host / Engine / runtime / tools 分层方向正确，且 F08 与 CI pipeline / smoke work 已被正确排除。

Plan 当前不能直接进入 accepted plan gate。原因不是架构方向错误，而是若直接交给 implementation agent，仍需要在错误类型、取消控制流、参数校验 helper、并发锁共享和测试迁移上现场补设计。因此进入 plan fix gate。

## Finding 裁决

| ID | 来源 | Finding | 裁决 | 理由 | Fix 要求 |
|---|---|---|---|---|---|
| PF-01 | MiMo 01 / DS F5 | `ToolBusinessError`、`ToolArgumentError`、`FileAccessError` 的替换类型和目标模块未定义 | accepted | 错误类型是 native callable 的核心边界；若不先收敛，Doc / Web / Fins 会各自发明不一致的错误层级或跨包依赖。 | 在 plan 中增加旧类型到新类型 / 新位置 / outcome 投影的迁移表；区分通用参数校验错误、通用业务失败、领域本地错误和取消 outcome。 |
| PF-02 | DS F2 | 取消语义在“抛私有异常”和“直接返回 outcome”之间未收敛 | accepted | `ToolCallable` 已允许直接返回 `ToolCancelledOutcome`；若保留抛异常路径，仍可能被 ToolRuntime 或本地 catch 归一为 failed outcome。 | plan 明确选择直接返回 `ToolCancelledOutcome(reason=host_cancelled)`，不以私有取消异常作为跨 helper / callable 的主路径。 |
| PF-03 | MiMo 02 / DS F4 | per-provider `asyncio.Lock` 创建和共享机制未指定 | accepted | 当前 legacy adapter 的 `SERIAL_PER_PROVIDER` 是生产行为；native migration 必须保留同一 provider 内共享一把锁的语义。 | plan 明确 lock 由每个 `build_*_tool_definitions(...)` 创建，并传入 / 闭包捕获到该 provider 的所有 callable；参数校验后、进入阻塞业务逻辑前获取。 |
| PF-04 | MiMo 03 | native callable 的配置闭包、context token 提取和 sync business 调用模板未描述 | accepted | 后续有 16 个以上 callable；若没有模板，implementation 会产生风格和取消边界不一致。 | plan 增加代表性 callable 模板：闭包捕获配置、校验参数、读取 `context.cancellation_token`、检查取消、获取 provider lock、`asyncio.to_thread` 执行业务、返回 outcome。 |
| PF-05 | MiMo 04 / DS F1 / DS F3 | Slice 0 参数校验 helper API 和范围不够精确，且有过度设计风险 | accepted | helper 是后续 slice 的基础；API 不明确会造成连锁返工，范围过宽又会变成新框架。 | plan 给出 helper 函数签名草案、typed success/failure 结果字段、固定 `invalid_argument` 失败码；校验范围从现有 adapter 行为和三类工具实际 schema 倒推，禁止实现无当前需求的 JSON Schema 高级特性。 |
| PF-06 | MiMo 05 | legacy adapter 测试删除前，path projection 与 concurrency 等生产行为的等价覆盖不清楚 | accepted | 测试必须随实现边界迁移；不能因为删除 adapter 测试而丢掉生产行为覆盖。 | plan 明确 `tests/tools/test_legacy_tool_adapter.py` 中哪些行为由 Slice 0/1/2/3 覆盖，哪些 adapter-only 测试可删除。 |
| PF-07 | DS F6 | Fins 测试 fixture 从 legacy discovery 迁移到 native builder 的路径不够具体 | accepted | Fins tests 当前经 `discover_tools` / legacy adapter 获取 definitions；fixture 不迁移会导致测试编译或语义覆盖失败。 | plan 在 Slice 3 增加测试 fixture helper 迁移要求，确保 Fins 测试不再调用 legacy collector / adapter。 |
| PF-08 | DS F7 | Web live smoke 未运行时的未覆盖场景记录不足 | accepted | deterministic pytest 可以覆盖核心行为，但真实网络 / Playwright fallback 风险需要在 slice closeout 中显式记录。 | plan 要求 Slice 2 若不运行 live smoke，必须记录未覆盖场景和 owner；能运行本地 fixture 模式时优先运行。 |
| PF-09 | DS F8 | `ToolCancelledOutcome.meta` 构造规格不足 | accepted | cancelled / failed / completed outcome 的 meta 一致性影响 trace 和 LLM-readable tool result 质量。 | plan 明确 `host_cancelled_outcome(...)` 接收或构造 `ToolResultMeta`，测试断言 meta 存在且不泄露治理字段。 |

## 下一步

进入 plan fix gate，由 AgentCodex 只修改 plan artifact，并新增 fix artifact：

- 更新 `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- 新增 `docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`

修复完成后进入 plan re-review gate，由 AgentMiMo 与 AgentDS 聚焦 PF-01 到 PF-09 的修复状态。

## Residual Risk

当前没有未分类 residual risk。所有 review finding 均已接受并归入 plan fix gate。
