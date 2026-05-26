# Plan Review: Host Public Conversation Memory Scenario Smoke

- Reviewer: mimo
- Review target: `docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- Date: 2026-05-26
- Gate: plan review

## Verdict

**PASS** — 无 blocking findings。Plan handoff-ready，可以进入 implementation。

## Finding F-01 [advisory] Mock tool schema ticker 字段与现有 smoke 不一致

- Severity: advisory
- Location: plan §7 Mock Tool Schema 与 `utils/smoke_host_public_conversation_memory.py:98-111`
- Evidence: 新 schema 要求 `company`, `ticker`, `period`, `topic`, `metric`, `include_pressure` 六个 required 字段。现有最小 smoke 的 `MockFinanceFactTool` schema 只有 `company`, `period`, `topic`, `metric`, `include_pressure` 五个字段，无 `ticker`。新旧 mock tool 同用 `manual-smoke` tag 但 schema 不一致。
- Impact: 不阻塞，但 implementation worker 应注意新旧 tool schema 差异不会导致 scene tool selection 冲突，因为两个 scene 使用不同 scene id、不同 provider id。
- Recommendation: implementation worker 在新脚本的 docstring 中注明新旧 mock tool 的 schema 差异是 intentional design，非遗漏。

## Finding F-02 [advisory] Implementation type 命名 `MockFinanceMemoryTool` 与现有 `MockFinanceFactTool` 不一致

- Severity: advisory
- Location: plan §11 Implementation Structure
- Evidence: plan 提议新类名为 `MockFinanceMemoryTool`，但现有最小 smoke 使用 `MockFinanceFactTool`。两者职责相同（返回确定性 mock 财报事实），仅数据集不同。命名不一致可能增加阅读成本。
- Impact: 不阻塞。命名差异可接受，因为 plan 明确禁止 shared helper extraction。
- Recommendation: implementation worker 在新脚本模块 docstring 中简要说明命名选择理由。

## Finding F-03 [advisory] E 场景 auto pressure padding 来源未显式指定

- Severity: advisory
- Location: plan §8.E 长会话稳定性
- Evidence: plan 写"每 5-7 轮插入一次 auto pressure padding"，但未显式指定 padding 来源是用户 prompt 文本还是 tool `include_pressure=true` 返回的 `pressure_blob`。D 场景 d1 显式指定 `include_pressure=true`，C 场景用用户长文本。E 场景混合了 tool-enabled 和 tool-disabled 轮次。
- Impact: 不阻塞。Implementation worker 有足够的 pattern（D 场景 d1 的 tool pressure + C 场景的 user text pressure）来决定 E 场景的 pressure 策略。
- Recommendation: implementation worker 对 E 场景 tool-enabled 轮次使用 `include_pressure=true`，tool-disabled 轮次使用 user text padding，并在 `_long_round_specs` 中显式编码此策略。

## Finding F-04 [advisory] `--long-rounds 19` fail closed 测试覆盖不完整

- Severity: advisory
- Location: plan §12 Testing Plan
- Evidence: plan 测试计划覆盖 `--long-rounds 19` fail closed，但未覆盖 `--long-rounds 20` succeed、`--long-rounds 0` fail closed、负数输入等边界。
- Impact: 不阻塞。核心边界（低于最小值 fail closed）已覆盖。
- Recommendation: implementation worker 可选补充 `--long-rounds 20` succeed 和 `--long-rounds 0` fail closed 测试。

## Finding F-05 [advisory] README 5.3 节号重编号影响

- Severity: advisory
- Location: plan §14 README / Docs 决策
- Evidence: plan 在 README 5.2 之后新增 5.3 场景 smoke。现有 5.3 是 Engine provider smoke，将被推到 5.4。Plan 未显式提及重编号。
- Impact: 不阻塞。README 节号重编号是机械操作，implementation worker 在更新 README 时自然会处理。
- Recommendation: implementation worker 更新 README 时同步调整后续节号。

## Coverage 评估

| 旧文档场景 | Plan 覆盖 | 分类 |
|---|---|---|
| A. pinned_state 演进与抗漂移 | §8.A 4 轮 | public proxy（主体/期间/口径/值 anti-drift） |
| B. 追问连续性 | §8.B 3 轮 | public proxy（代词/指代 follow-up） |
| C. 单轮极长输入 | §8.C 3 轮 | public proxy（长输入后追问连贯） |
| D. compaction 与 confirmed_facts | §8.D 4 轮 | public proxy（跨轮事实一致性 + pressure） |
| E. 长会话稳定性 | §8.E 25 轮 | public proxy（session open + tool count + constraints recap） |

Plan 对每个场景都诚实标注了"不直接证明内部结构"的边界，并指向 Host unit/integration tests 作为内部语义覆盖的 owner。

## Public API 边界检查

- ✅ 只使用 `ensure_session`, `submit_followup`, `watch_session_events`, `get_session`, `get_run`
- ✅ 不读取 `.dayu/host/dayu_host.db`、EventLog、memory projection、compact payload
- ✅ 不读取 `pinned_state`、`confirmed_facts` 内部字段
- ✅ `SessionSnapshot` 无 public memory 字段，plan 正确识别此约束
- ✅ Mock tool 通过 `ToolsDiscovery` + `manual-smoke` tag 注入，与现有 smoke pattern 一致

## 项目约束检查

- ✅ 严格类型：plan 提议所有类型使用 `dataclass(frozen=True, slots=True)`、`StrEnum`、无 `Any`/`object`
- ✅ 中文 docstring：plan §11 要求所有模块、类、函数提供中文 docstring
- ✅ 不改生产路径：plan §4 禁止修改 `dayu/host/**`、`dayu/fins/**`、`dayu/engine/**`、`dayu/runtime/**`
- ✅ 现有最小 smoke 保护：plan §4 禁止修改 `utils/smoke_host_public_conversation_memory.py`
- ✅ utils 无覆盖率要求：plan §12 只新增 assembly test，不为 smoke 脚本本身要求覆盖率
- ✅ 场景矩阵使用 `frozenset()` 禁用工具，与现有 smoke pattern 一致

## Implementation Slices 评估

- S1（新脚本）：文件范围清晰，completion signal 合理（py_compile + 无 Host private import）
- S2（scene asset）：manifest + prompt + migration test 更新，completion signal 合理
- S3（assembly tests）：独立测试文件，不依赖真实 LLM
- S4（README 同步）：文档更新，触发规则正确

Slices 无文件交叉，可独立实现和验证。

## 总结

Plan 质量高，结构完整，对旧文档 A-E 场景的覆盖分类诚实且合理。Public API 边界约束严格，项目编码约束明确。Advisory findings 均为实现细节层面的澄清建议，不构成 handoff 阻塞。
