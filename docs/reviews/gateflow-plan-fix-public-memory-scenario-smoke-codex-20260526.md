# Plan Fix: Host Public Conversation Memory Scenario Smoke

- Gate：plan fix
- Worker：Codex
- Source plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- DS review：`docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-ds-20260526.md`
- MiMo review：`docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-mimo-20260526.md`
- Date：2026-05-26

## Scope

本次 fix 只更新 plan artifact，并新增本 fix artifact。未修改生产代码、smoke 脚本、测试、README；未提交、未推送、未进入其它 gate。

## Accepted Findings / Guidance

### DS N1：`--suite all` session continuity 机制未细化

- Status：已修复。
- Plan update：在 §5 明确 `core`、`long`、`all` 都必须在单个 `open_host` lifecycle 内执行；`all` 使用 `(*core_specs, *long_specs)` 拼接并共享同一个 session、watcher 和 tool instance。
- Validation point：§12 增加 suite all 纯函数 spec 拼接测试要求，避免 implementation 选择两次 open/ensure。

### DS N2：C2 长输入文本生成方法未指定

- Status：已修复。
- Plan update：在 §8.C2 增加 `_BYD_LONG_INPUT_TARGET_CHARS`、三个 anchor 常量、`_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS` 和 `_build_byd_long_input()` 的确定性生成规则。
- Validation point：§12 要求测试长度范围、三个 anchor 各出现一次、连续调用输出完全一致。

### DS N3：E 组长会话 25 轮 prompt 未提供

- Status：已修复。
- Plan update：在 §8.E 增加固定 25 轮 long prompt specs，包含 L01-L25 的常量名、工具/pressure 策略和固定 prompt 文本；明确 `_LONG_ROUND_TEMPLATES` / `LongRoundTemplate` 必须是 `Final` 固定 specs。
- Validation point：§12 要求 `_select_long_templates(20)` 与 `_select_long_templates(25)` 的边界行为测试。

### DS N4：`calls_by_key` 追踪被设计但未用于任何断言

- Status：已修复。
- Plan update：在 §7 明确 `calls_by_key` 是 observability，不参与 hard pass/fail；每轮可打印短摘要，最终必须打印完整 per-key 调用分布；未知 key 使用 `_UNKNOWN_FACT_KEY`。
- Validation point：§12 增加 `calls_by_key` tracked session 累计与 `SMOKE TOOL_CALLS_BY_KEY ...` 摘要格式测试。

### DS N5：断言 helper 容易退化为巨型 if/elif

- Status：已修复。
- Plan update：在 §11 明确 `RoundSpec` 字段包含 `hard_answer_contains`、`hard_answer_forbidden`、`soft_answer_contains`、`expected_tool_calls_after_round` 等，并拆分 `_assert_terminal_ok`、`_assert_tool_count`、`_assert_answer_contains`、`_observe_soft_answer_contains`。`_assert_round_result` 只能按 `RoundSpec` 数据组合 helper，不允许 label-based 巨型分支。
- Validation point：implementation review 应检查断言逻辑是否数据驱动。

### MiMo F-01：Mock tool schema ticker 字段与现有 smoke 不一致

- Status：已处理为 implementation guidance。
- Plan update：§7 增加 schema rationale，说明新 schema 多 required `ticker` 是 intentional design，用于 A/E 场景验证证券代码不漂移；新旧 smoke 使用不同 scene id、provider id 和 tool name，不会冲突。

### MiMo F-02：`MockFinanceMemoryTool` 命名与现有 `MockFinanceFactTool` 不一致

- Status：已处理为 implementation guidance。
- Plan update：§7 增加命名 rationale，说明 `Memory` 命名用于表达多数据集、多场景 public memory 行为；最小 smoke 保持原命名，不做 shared helper extraction。

### MiMo F-03：E 场景 auto pressure padding 来源未显式指定

- Status：已处理为 implementation guidance。
- Plan update：§8.E 明确 tool-enabled pressure 来自 L01/L05/L09/L13/L17/L21 的 `include_pressure=true` tool `pressure_blob`；user prompt pressure 来自 L08/L16/L24 的 `<auto_user_pressure>`；两者同源使用 `OpenHostOptions.context_budget_policy`。

### MiMo F-04：`--long-rounds` 边界测试覆盖不完整

- Status：已处理为 implementation guidance。
- Plan update：§6 将 `--long-rounds` 收紧为 `20..25`；§12 要求覆盖 20/25 success，19/26/0/-1 fail closed，以及 20 轮选择 L25 作为最终 recap。

### MiMo F-05：README 5.3 节号重编号影响

- Status：已处理为 implementation guidance。
- Plan update：§14 明确新增 5.3 场景 smoke 后，现有 5.3 Engine provider smoke 顺延为 5.4，后续同级小节编号一并机械更新。

## Validation Performed

- 已重新阅读更新后的 plan 关键段落：§5、§6、§7、§8.C、§8.E、§9、§11、§12、§13、§14。
- 本 gate 是 docs-only plan fix，未运行 Python tests 或 pyright。
- 文档空白校验通过：`git diff --check -- docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md docs/reviews/gateflow-plan-fix-public-memory-scenario-smoke-codex-20260526.md`。

## Residual Risks

- `pinned_state`、episode 数量、compact material 内容仍不可由 public smoke 直接断言；计划继续把这些归属给 Host memory / compaction 单元与集成测试。
- LLM 仍可能不遵守可选 assertion line；计划已要求 hard / soft 分层，并把核心最终轮 marker/value 作为硬断言。
- Long suite 真实运行成本和 provider rate limit 风险仍存在；计划默认 `core`，`long/all` 由 operator 显式运行。

## Stop Status

Plan fix scope complete。无 Blocking Questions For Controller。
