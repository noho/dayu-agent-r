# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan Re-Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: plan re-review
- Fixed plan: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-controller-adjudication.md`
- Original reviews:
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-ds.md`

## Re-Review Methodology

逐项对比 controller adjudication 的 accepted findings 与 fixed plan 的实际内容；对每个 finding 做源码交叉验证确保 plan claims 可执行；检查 fix 是否引入回归或新的 material blocker。

---

## Accepted Findings Verification

### P2C-PLAN-F01: `AgentPolicyDefaults` / `code_default` 命名与 docstring cleanup

**要求**: runtime assembly naming/docstring cleanup 从条件性建议改为硬性要求，明确 before/after 命名。

**Fixed plan 实际内容** (Exact Implementation Decisions §3, lines 109-115):

- "必须执行以下 before / after 改名，不做旧名兼容 wrapper、alias 或 re-export"
- `AgentPolicyDefaults` → `AgentPolicyBaseline`
- `code_default` 参数名 → `base_policy`
- `_SOURCE_CODE_DEFAULT` → `_SOURCE_RUNTIME_BASE`
- source 字符串 `"code_default"` → `"runtime_base"`
- `_agent_policy_defaults_from_config(...)` → `_agent_policy_baseline_from_config(...)`
- `AgentPolicyBaseline` docstring 必须说明它是 "runtime assembly merge fallback / baseline values，来源于 config loader 或显式 assembly input，不是 Engine contract defaults，也不是 LLM-facing prompt 文本真源"

**源码交叉验证**:
- `dayu/runtime/assembly.py:39`: `_SOURCE_CODE_DEFAULT: Final[str] = "code_default"` — 需改为 `_SOURCE_RUNTIME_BASE: Final[str] = "runtime_base"`
- `dayu/runtime/assembly.py:160-180`: `class AgentPolicyDefaults` docstring "Agent policy 代码默认值" — 需改为 `AgentPolicyBaseline`
- `dayu/runtime/assembly.py:468`: `code_default: AgentPolicyDefaults` 参数 — 需改为 `base_policy: AgentPolicyBaseline`
- `dayu/service/host_assembly.py:629`: `code_default=_agent_policy_defaults_from_config(...)` — 需改为 `base_policy=_agent_policy_baseline_from_config(...)`
- `dayu/service/host_assembly.py:1622`: `def _agent_policy_defaults_from_config(` — 需改名

**结论**: **已修复**。改名方案已从条件性建议变为硬性必做项，before/after 命名完全明确，docstring 要求具体。

---

### P2C-PLAN-F02: `tests/host/public_smoke_support.py` 显式迁移与禁止跨测试默认真源

**要求**: 显式列出该文件为迁移目标，fixture prompt 值显式传入且不可抽成可跨测试导入的默认真源。

**Fixed plan 实际内容**:

- Affected Files → Tests (line 89): 在 Host direct fixtures 中显式列出 `tests/host/public_smoke_support.py`
- Exact Implementation Decisions §7 (lines 133-134): "`tests/host/public_smoke_support.py` 是显式迁移目标：其 ordinary run baseline 的 `AgentPolicy(...)` 必须传入显式 `fallback_prompt=` 和 `continuation_prompt=`。这些 prompt 只能作为该 fixture 构造点的显式测试输入，不能抽成可跨测试导入的默认真源。"
- Exact Implementation Decisions §7 (line 131): 统一 helper guardrail — "helper 必须 file-local 或 function-local，不得放到 `conftest.py`，不得被其它测试模块 import 为共享默认真源，不得放到生产代码或作为 compatibility default"

**源码交叉验证**:
- `tests/host/public_smoke_support.py:908-913`: 当前构造 `AgentPolicy(max_iterations=..., continuation_max_attempts=..., allow_tool_calls=..., tool_execution_timeout_seconds=...)` 省略了 `fallback_prompt=` 和 `continuation_prompt=` — 确认该构造点在 P2-C 后必触发 `TypeError`

**结论**: **已修复**。文件已显式列出，迁移要求具体，guardrail 覆盖了跨测试默认真源风险。

---

### P2C-PLAN-F03: `test_contract_fields_are_explicit` 具体迁移

**要求**: 指定文件路径与测试名，明确 rename/split、TypeError 测试、显式 prompt acceptance test、非文本默认断言处置、空白 prompt ValueError 覆盖。

**Fixed plan 实际内容** (Exact Implementation Decisions §7, lines 134-139):

- 指定目标: `tests/engine/test_agent_phase3_tool_call.py::test_contract_fields_are_explicit`
- "不再断言默认 prompt 存在"
- "将缺少 prompt 的行为改成 `TypeError` 测试，例如拆出或重命名为 `test_agent_policy_prompt_fields_are_required`：分别覆盖缺 `fallback_prompt` 和缺 `continuation_prompt`"
- "增加或保留显式 prompt 构造 / 保留测试，例如 `test_agent_policy_accepts_explicit_prompt_fields`：断言传入的 `fallback_prompt`、`continuation_prompt` 原样保留"
- "`fallback_mode=AgentFallbackMode.FORCE_ANSWER` 与 `max_consecutive_failed_tool_batches=2` 是非文本默认；这些断言可独立保留，或放入显式 prompt acceptance test，但不得再借省略 prompt 来验证"
- "空白 prompt 的 `ValueError` 仍由 invalid values 测试覆盖；迁移这些 negative test 的其它字段时必须显式传入非空 prompt，避免缺字段 `TypeError` 掩盖空白值校验"

**源码交叉验证**:
- `tests/engine/test_agent_phase3_tool_call.py:796-809`: `test_contract_fields_are_explicit` 当前构造 `AgentPolicy(...)` 省略 prompt 字段，并在 lines 808-809 断言 `policy.fallback_prompt` 和 `policy.continuation_prompt` 为 truthy — 确认该测试当前验证的正是 P2-C 要消除的 Engine 默认行为
- `tests/engine/test_agent_phase3_tool_call.py:812-865`: `test_agent_policy_rejects_invalid_values` 已覆盖空白 prompt ValueError（lines 831-838 空白 continuation_prompt，lines 857-865 空白 fallback_prompt）— 确认迁移后 negative test 的其他字段需显式传入非空 prompt

**结论**: **已修复**。迁移规格具体到测试名、拆分方案、正向/负向覆盖和与其他测试的交互。

---

## Guardrails Verification

### P2C-PLAN-G01: Post-scan 包含 `utils/`

**Fixed plan 实际内容** (Post-scan acceptance, line 163):
```
rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'
```

**结论**: **已修复**。`utils/` 已加入扫描范围。

---

### P2C-PLAN-G02: Focused validation 包含 `test_agent_phase2.py`

**Fixed plan 实际内容** (Focused checks, line 161):
```
pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/contracts/test_agent_run.py
```

**结论**: **已修复**。`tests/engine/test_agent_phase2.py` 已加入 focused check。

---

## Core Direction Preservation Check

Fixed plan 仍保持 controller adjudication 的核心要求：

- Engine 物理移除 LLM-facing prompt text defaults（Decision 1） ✓
- 不把 Engine 默认替换为 config 文本（Decision 2） ✓
- Ordinary Run prompt 默认由 execution profile 产生 ✓
- Compactor prompt 由 compactor scene required `agent_policy` 产生 ✓
- Runtime assembly 只合并 caller/config 已给出的 baseline ✓
- Host/durable projection/Engine/LLM message 都消费同一条已解析 policy 路径 ✓
- 不新增 compatibility alias、default wrapper、test-only default helper 或 re-export（Non-goals） ✓
- 不切 implementation slices（Slice Decision） ✓

---

## New Material Blocker Check

未发现新的 material blocker。具体检查项：

1. **Fix 未引入回归**: 所有 fix 均为增加 specificity（mandatory naming、explicit file list、concrete test spec），未改变 plan 的核心方向、owner boundary 或 scope boundary。
2. **改名方案可执行**: `_agent_policy_defaults_from_config` 在 `dayu/service/host_assembly.py:1622`，已列入 affected production files；所有需改名的符号均在 `dayu/runtime/assembly.py` 和 `dayu/service/host_assembly.py` 中，plan 均覆盖。
3. **测试迁移无遗漏**: 51 个 test 构造点 + 4 个 production 构造点 + utils/ 扫描全覆盖。
4. **`test_agent_policy_rejects_invalid_values` 迁移注意**: 该测试中部分 `AgentPolicy(...)` 构造省略了 prompt 字段（如 line 817-823 未传 fallback_prompt/continuation_prompt），P2-C 后必触发 `TypeError` 而非 `ValueError`。Plan decision 7 已覆盖："迁移这些 negative test 的其它字段时必须显式传入非空 prompt，避免缺字段 `TypeError` 掩盖空白值校验"。
5. **`AgentPolicyDefaults` 在 `__all__` 中**: `dayu/runtime/assembly.py:953` 的 `__all__` 导出 `"AgentPolicyDefaults"` — implementation 需同步更新为 `"AgentPolicyBaseline"`。此细节 plan 未显式提及，但不构成 material blocker：改名是全面 requirement，`__all__` 更新属于改名的自然组成部分，且 pyright 会捕获导出名不一致。

---

## Completion Report

- **conclusion**: `pass`
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-rereview-ds.md`

### Final Status per Accepted Finding

| Finding ID | 状态 | 说明 |
|-----------|------|------|
| P2C-PLAN-F01 | 已修复 | `AgentPolicyDefaults`/`code_default` naming cleanup 已从条件性建议改为硬性必做项，before/after 命名完全明确，docstring 要求具体 |
| P2C-PLAN-F02 | 已修复 | `tests/host/public_smoke_support.py` 已显式列为迁移目标，fixture prompt 显式传入要求与 guardrail 完整 |
| P2C-PLAN-F03 | 已修复 | `test_contract_fields_are_explicit` 迁移规格具体到文件名、测试名、拆分方案、正向/负向覆盖 |
| P2C-PLAN-G01 | 已修复 | Post-scan `rg` 命令已包含 `utils/` |
| P2C-PLAN-G02 | 已修复 | Focused check 已包含 `tests/engine/test_agent_phase2.py` |

### New Material Findings

无。

### Residual Notes (non-blocking)

- `dayu/runtime/assembly.py:953` 的 `__all__` 中 `"AgentPolicyDefaults"` 需同步改为 `"AgentPolicyBaseline"` — 属于 F01 改名的自然延伸，pyright 会兜底。
- `test_agent_policy_rejects_invalid_values` 中多个 `AgentPolicy(...)` 构造点省略 prompt 字段（lines 817-823, 825-830, 832-838, 841-846, 849-855），implementation 迁移时需为每个构造点显式传入非空 prompt，否则 `TypeError` 会在 `ValueError` 断言前触发。Plan decision 7 已覆盖此注意点。
