# Host Public Conversation Memory Scenario Smoke — Plan Re-Review — DS — 2026-05-26

## Gate

当前 gate：plan re-review。
Review targets：
- Updated plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- Fix artifact：`docs/reviews/gateflow-plan-fix-public-memory-scenario-smoke-codex-20260526.md`
- Prior DS review：`docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-ds-20260526.md`
- Prior MiMo review：`docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-mimo-20260526.md`

Reviewer：AgentDS。

## Scope

Re-review only。验证 Codex plan-fix 对 DS N1-N5 和 MiMo F-01-F-05 的修复是否充分。不扩大到 implementation review、不修改 plan/code/tests/README、不进入其它 gate。

## DS N1-N5 逐项验证

### N1：`--suite all` session continuity 机制 → RESOLVED

- **修复位置**：Plan §5 新增 "Suite 编排必须统一在一个 Host lifecycle 中完成" 段。
- **修复内容**：明确 core/long/all 都在单次 `open_host` 内执行；`all` 使用 `(*core_specs, *long_specs)` 拼接，共享 session/watcher/tool instance；"不得拆成两次 open_host，也不得依赖 --reuse-session 在两个 Host block 之间恢复 continuity"。
- **测试覆盖**：§12 新增 "suite all 编排函数...纯函数 spec 拼接单测覆盖"。
- **结论**：RESOLVED。方案明确选择了单次 open_host 拼接方案，比原 plan 建议的方案 (a) 更严格且消除了实现歧义。

### N2：C2 长输入文本生成方法 → RESOLVED

- **修复位置**：Plan §8.C 轮次 2 段。
- **修复内容**：
  - 定义 `_BYD_LONG_INPUT_TARGET_CHARS: Final[int] = 12_000`
  - 定义三个 anchor 常量：`_BYD_LONG_INPUT_HEAD_ANCHOR`、`_BYD_LONG_INPUT_MIDDLE_ANCHOR`、`_BYD_LONG_INPUT_TAIL_ANCHOR`
  - 定义 `_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS: Final[tuple[str, ...]]`，4 段固定中文披露风格文本
  - `_build_byd_long_input()` 确定性构造规则：head anchor → 重复模板段落 → middle anchor 插入中部附近 → tail anchor 追加 → 截断/补齐到 8,000-15,000
- **测试覆盖**：§12 增加长度范围检查、三个 anchor 各出现一次、连续调用一致性。
- **结论**：RESOLVED。生成规则完全确定且可验证，消除了 N2 的可复现性风险。

### N3：E 组长会话 25 轮 prompt → RESOLVED

- **修复位置**：Plan §8.E 新增 "固定 25 轮 prompt specs" 表。
- **修复内容**：
  - L01-L25 完整表格，每行包含 label/常量名、tools/pressure 策略、固定 prompt 文本
  - 定义 `_LONG_ROUND_TEMPLATES: Final[tuple[LongRoundTemplate, ...]]` 和 `LongRoundTemplate` 字段（label、prompt、tool_enabled、metric、include_tool_pressure、include_user_pressure、hard_contains、hard_forbidden）
  - `_select_long_templates(round_count)` 按 L01..L(N-1)+L25 选择，确保最终 recap 始终执行
  - E 场景 pressure 来源显式化：tool-enabled pressure 在 L01/L05/L09/L13/L17/L21；user prompt pressure 在 L08/L16/L24
  - 所有 no-tool 轮次 `hard_forbidden` 包含 5 个 core suite markers 防止跨 suite 漂移
  - L07 显式要求不引用 core suite 公司
- **测试覆盖**：§12 增加 `_select_long_templates(20)` / `_select_long_templates(25)` 边界测试。
- **结论**：RESOLVED。这是所有 finding 中最大幅度的 plan 增强。25 轮 prompt 全部指定为 Final 常量，不再需要 implementation worker 临场发明，彻底消除了 N3 的 Medium severity 可复现性风险。

### N4：`calls_by_key` 追踪用途 → RESOLVED

- **修复位置**：Plan §7 Callable 行为段。
- **修复内容**：
  - 明确 "calls_by_key 不参与 hard pass/fail；它是 observability 计数"
  - 定义 per-key 格式 `SMOKE TOOL_CALLS_BY_KEY maotai_revenue=1 cmb_nim=1 ...`
  - 最终 summary 必须打印完整 per-key 调用分布
  - 未知 key 使用 `_UNKNOWN_FACT_KEY` 常量
  - `RoundSpec` 新增 `print_calls_by_key: bool` 字段控制打印
- **测试覆盖**：§12 增加 `calls_by_key` 累计与 `SMOKE TOOL_CALLS_BY_KEY ...` 格式测试。
- **结论**：RESOLVED。从 dead tracking code 升级为有明确定义和测试覆盖的 observability 机制。

### N5：断言 helper dispatch → RESOLVED

- **修复位置**：Plan §11 `RoundSpec` 字段 + 断言策略段。
- **修复内容**：
  - `RoundSpec` 明确字段：`hard_answer_contains`、`hard_answer_forbidden`、`soft_answer_contains`、`expected_tool_calls_after_round`、`print_calls_by_key`
  - 断言策略拆分为四个独立 helper：`_assert_terminal_ok`、`_assert_tool_count`、`_assert_answer_contains`、`_observe_soft_answer_contains`
  - `_assert_round_result` 只能组合 helper，按 `RoundSpec` 数据驱动，"不允许按 label 写长分支"
  - "确需少量特殊行为时，优先增加 RoundSpec 字段，不在 helper 内新增业务分支"
- **结论**：RESOLVED。原 plan 的单一 `_assert_round_result(result, tool, expected_tool_calls)` 签名已被替换为数据驱动的 `_assert_round_result(result, tool, spec)` + 组合 helper，消除了 N5 的巨型 if-elif 风险。

---

## MiMo F-01-F-05 逐项验证

### F-01：mock tool schema ticker 字段 → RESOLVED

- **修复位置**：Plan §7 "命名与 schema rationale" 段。
- **修复内容**：明确 ticker 是 intentional design，用于 A/E 场景验证证券代码不漂移；两个 smoke 使用不同 scene id/provider id/tool name，不冲突。
- **结论**：RESOLVED。

### F-02：`MockFinanceMemoryTool` 命名 → RESOLVED

- **修复位置**：Plan §7 "命名与 schema rationale" 段。
- **修复内容**：`Memory` 命名表达多数据集/多场景 public memory 行为；最小 smoke 保持原 `MockFinanceFactTool` 命名。
- **结论**：RESOLVED。

### F-03：E 场景 auto pressure padding 来源 → RESOLVED

- **修复位置**：Plan §8.E pressure 来源显式段。
- **修复内容**：tool-enabled pressure 在 L01/L05/L09/L13/L17/L21 由 `include_pressure=true` 返回 `pressure_blob`；user prompt pressure 在 L08/L16/L24 由 `_compact_pressure_padding(options, label=<label>)` 提供。
- **结论**：RESOLVED。

### F-04：`--long-rounds` 边界测试 → RESOLVED

- **修复位置**：Plan §6 CLI 设计 + §12 测试计划。
- **修复内容**：`--long-rounds` 范围收紧为 `20..25`；§12 覆盖 20/25 success、19/26/0/-1 fail closed、20 轮时 L25 作为最终 recap。
- **结论**：RESOLVED。比原建议更完整（增加了 `--long-rounds 26` 上限检查）。

### F-05：README 5.3 节号重编号 → RESOLVED

- **修复位置**：Plan §14 README / Docs 决策。
- **修复内容**：明确 "现有 5.3 Engine provider smoke 需要同步顺延为 5.4，后续同级小节编号一并机械更新，避免 README 目录/引用出现重复编号"。
- **结论**：RESOLVED。

---

## 新增潜在问题检查

### 检查 1：E 场景 tool metric 与 fixed facts table 的匹配规则

- **观察**：E 场景 L01/L05/L09/L13/L17/L21 使用 `topic=long_session_profile` + 不同 `metric` 值（`midea_revenue_profile`、`midea_margin_profile` 等）。Fixed facts 表只有 `midea_long_session` 一条记录，`topic/metric` 列为 `long_session_profile`。Mock tool 需要能够将这些不同的 `metric` 值匹配到同一条 `midea_long_session` 事实。
- **评估**：Plan §7 已规定 mock tool "只接受固定测试数据集；未知 company/ticker/topic/metric 返回成功 JSON 中的 known=false"。Implementation worker 可按 `topic` 或 `key` 匹配，而非要求 `metric` 精确相等。这是合理的实现细节，不是 plan 缺陷。
- **结论**：不需要 plan-level fix。Implementation worker 在实现 mock tool 时应确保 `topic=long_session_profile` 的调用都返回 `midea_long_session` 事实，`metric` 不同值不影响匹配。

### 检查 2：No-tool 轮次 hard_forbidden 未覆盖 tool-enabled 轮次

- **观察**：§8.E 规定 "所有 no-tool 轮次的 hard_forbidden 至少包含 core suite 的关键 markers"。但 tool-enabled 轮次（L01/L05/L09/L13/L17/L21）不在此列。如果 LLM 在 tool-enabled 回答中意外引用 core suite 数值，可能不会被捕获。
- **评估**：Tool-enabled 轮次都查询 美的集团 数据，且 L07 为 no-tool 轮次并显式要求不引用 core suite 公司。L25 最终 constraints recap 会捕获 美的集团 专属 marker 的存在和 core markers 的缺失。风险极低。
- **结论**：不需要 plan fix。如 implementation worker 认为有必要，可在 tool-enabled 轮次的 `LongRoundTemplate.hard_forbidden` 中同样加入 core markers——这属于实现裁量空间。

### 检查 3：Public API 边界与现有 smoke 保护

- **验证**：Plan fix 未修改 §2 non-goals、§4 禁止修改列表、§5 禁止读取列表、§15 residual risks。Suite 编排新增的对 `open_host` 和 `ensure_session` 的使用仍在 Public API 范围内。
- **结论**：Public API 边界和现有 smoke 保护不变。

---

## Final Status Mapping

### DS Findings

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| N1: suite all continuity | Low | RESOLVED | §5 单次 open_host 拼接 + §12 测试 |
| N2: C2 long input generation | Low | RESOLVED | §8.C `_build_byd_long_input()` 确定性规则 + §12 测试 |
| N3: E long suite prompts | Medium | RESOLVED | §8.E L01-L25 完整表格 + `LongRoundTemplate` + §12 测试 |
| N4: calls_by_key unused | Low | RESOLVED | §7 observability 语义 + `RoundSpec.print_calls_by_key` + §12 测试 |
| N5: assertion dispatch | Low | RESOLVED | §11 `RoundSpec` 完整字段 + 四 helper 拆分 + 数据驱动约束 |

### MiMo Findings

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| F-01: ticker schema diff | Advisory | RESOLVED | §7 schema rationale |
| F-02: class naming | Advisory | RESOLVED | §7 命名 rationale |
| F-03: E pressure source | Advisory | RESOLVED | §8.E pressure 来源显式段 |
| F-04: long-rounds boundary | Advisory | RESOLVED | §6 `20..25` + §12 测试 |
| F-05: README renumbering | Advisory | RESOLVED | §14 顺延说明 |

### 新发现问题

无 blocking 或 non-blocking 新 finding。

---

## Verdict

**PASS** — Plan fix 正确且完整。

10 个 finding（DS N1-N5 + MiMo F-01-F-05）全部 RESOLVED。N3（原 Medium severity）的修复尤其显著：25 轮 L01-L25 的完整 prompt 表、`LongRoundTemplate` 类型字段、pressure 来源显式化、跨 suite anti-drift 的 `hard_forbidden` 规则——使 E 场景从 "implementation worker 临场发明" 升级为 "plan 完整指定"。

Plan 可以进入 implementation gate（S1）。

## Artifact Path

`docs/reviews/gateflow-plan-rereview-public-memory-scenario-smoke-ds-20260526.md`
