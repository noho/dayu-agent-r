# Plan Re-Review: Host Public Conversation Memory Scenario Smoke

- Reviewer: mimo
- Review target: fix artifact `docs/reviews/gateflow-plan-fix-public-memory-scenario-smoke-codex-20260526.md` applied to `docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- Prior reviews: MiMo `gateflow-plan-review-public-memory-scenario-smoke-mimo-20260526.md`, DS `gateflow-plan-review-public-memory-scenario-smoke-ds-20260526.md`
- Date: 2026-05-26
- Gate: plan re-review

## Verdict

**PASS** — 所有 MiMo F-01..F-05 和 DS N1..N5 已充分处理，无新 blocking issue。Plan 可进入 implementation。

## Finding Status Mapping

### MiMo Findings

| Finding | Fix Status | Re-Review Verdict | Evidence |
|---|---|---|---|
| F-01: ticker 字段与现有 smoke 不一致 | implementation guidance | **RESOLVED** | §7 新增 schema rationale，说明 ticker 用于 A/E 场景证券代码漂移验证；新旧 smoke 使用不同 scene id / provider id / tool name，无冲突 |
| F-02: MockFinanceMemoryTool 命名不一致 | implementation guidance | **RESOLVED** | §7 新增命名 rationale，说明 Memory 命名表达多数据集多场景；最小 smoke 保持原命名 |
| F-03: E 场景 pressure 来源未指定 | implementation guidance | **RESOLVED** | §8.E 明确 tool-enabled pressure（L01/L05/L09/L13/L17/L21 的 `include_pressure=true`）和 user prompt pressure（L08/L16/L24 的 `<auto_user_pressure>`），两类同源 `context_budget_policy` |
| F-04: --long-rounds 边界测试不完整 | implementation guidance | **RESOLVED** | §6 收紧为 `20..25`；§12 要求覆盖 20/25 success、19/26/0/-1 fail closed |
| F-05: README 5.3 节号重编号 | implementation guidance | **RESOLVED** | §14 明确 5.3→5.4 顺延及后续同级小节机械更新 |

### DS Findings

| Finding | Fix Status | Re-Review Verdict | Evidence |
|---|---|---|---|
| N1: --suite all session continuity 未细化 | 已修复 | **RESOLVED** | §5 明确 core/long/all 均在单个 `open_host` lifecycle 内；all 使用 `(*core_specs, *long_specs)` 拼接共享 session/watcher/tool instance；§12 增加纯函数 spec 拼接测试 |
| N2: C2 长输入文本生成方法未指定 | 已修复 | **RESOLVED** | §8.C2 新增 `_BYD_LONG_INPUT_TARGET_CHARS`、三个 anchor 常量、`_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS`、`_build_byd_long_input()` 确定性生成规则；§12 要求长度/anchor/幂等测试 |
| N3: E 组 25 轮 prompt 未提供 | 已修复 | **RESOLVED** | §8.E 新增完整 L01-L25 prompt specs 表格，包含常量名、tool/pressure 策略、固定 prompt 文本；`_LONG_ROUND_TEMPLATES` 必须为 `Final`；`_select_long_templates(round_count)` 的 L(N-1)+L25 规则明确 |
| N4: calls_by_key 追踪未用于断言 | 已修复 | **RESOLVED** | §7 明确 calls_by_key 为 observability、不参与 hard pass/fail；每轮可打印短摘要、最终打印完整 per-key 分布；未知 key 使用 `_UNKNOWN_FACT_KEY`；§12 增加格式测试 |
| N5: _assert_round_result 单签名不足以分发 | 已修复 | **RESOLVED** | §11 新增 `RoundSpec` 数据驱动字段（`hard_answer_contains`、`hard_answer_forbidden`、`soft_answer_contains`、`expected_tool_calls_after_round`）；断言拆分为 `_assert_terminal_ok` / `_assert_tool_count` / `_assert_answer_contains` / `_observe_soft_answer_contains` 四个 helper；`_assert_round_result` 只能按 RoundSpec 组合 helper，禁止 label-based 分支 |

## Fix Quality Assessment

### 公共 API 边界保持检查

- ✅ §5 调用流未引入任何新的 private API 调用
- ✅ §7 mock tool 仍通过 `ToolsDiscovery` + `manual-smoke` tag 注入
- ✅ §2 non-goals 未放松
- ✅ 禁止读取列表（§5 禁止运行期读取）未缩小

### 现有最小 smoke 非修改保持检查

- ✅ §4 禁止修改 `utils/smoke_host_public_conversation_memory.py` 未改变
- ✅ §7 schema rationale 明确新旧 tool 独立，不做 shared helper extraction
- ✅ §15 residual risks 保持"不抽取 shared helper"裁决

### 新增内容一致性检查

- ✅ §5 suite 编排描述与 §12 测试要求一致（纯函数 spec 拼接）
- ✅ §6 `--long-rounds 20..25` 范围与 §8.E `_select_long_templates` 的 L(N-1)+L25 规则一致
- ✅ §7 calls_by_key observability 描述与 §9 soft observations 表一致
- ✅ §11 RoundSpec 字段与断言 helper 拆分描述一致
- ✅ §8.E L01-L25 prompt specs 表格中 tool/pressure 标注与 §8.E pressure 来源描述一致

### 新增 Blocking Issue 检查

**无新增 blocking issue。**

Fix artifact 只更新 plan 文本和新增 fix artifact，未修改生产代码、测试或 README。所有变更都是对 plan 规格的细化和补充，未引入架构变更或新的约束冲突。

## Residual Advisory Notes

以下不属于 findings，仅为 implementation worker 的补充提醒：

1. §8.E L01-L25 的 `<auto_user_pressure>` 占位符在实现时应替换为 `_compact_pressure_padding(options, label=<label>)` 调用，plan 已在 §8.E pressure 来源段落说明。
2. §6 `--long-rounds` 的 20..25 范围比旧 plan 更窄（原为 min 20 无上限），implementation worker 的 argparse 应同时检查上限。
3. §12 测试计划条目较多，implementation worker 应确保 S3 测试文件不膨胀为 God test file；可按 CLI/assembly/mock-tool/pressure/normalization 分组。
