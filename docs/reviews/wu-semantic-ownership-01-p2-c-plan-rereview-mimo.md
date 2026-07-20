# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan Re-Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: plan re-review
- Plan artifact (fixed): `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-fix-codex.md`
- Original reviews:
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-controller-adjudication.md`

## Review Target

复核 controller accepted plan findings 是否已在 fixed plan 中修复。不重复已关闭或非 material 风险。

## Accepted Findings Verification

### P2C-PLAN-F01: AgentPolicyDefaults / code_default naming cleanup

**Controller 要求**: 必须将 runtime assembly naming/docstring cleanup 设为硬性 requirement，明确 before/after naming。

**Fixed plan 核查**:

Plan Decision 3 (lines 109-115) 已将 cleanup 从条件性建议改为硬性 implementation decision，明确五项 before/after 改名：

| Before | After |
|--------|-------|
| `AgentPolicyDefaults` | `AgentPolicyBaseline` |
| `code_default` 参数名 | `base_policy` |
| `_SOURCE_CODE_DEFAULT` | `_SOURCE_RUNTIME_BASE` |
| source 字符串 `"code_default"` | `"runtime_base"` |
| `_agent_policy_defaults_from_config(...)` | `_agent_policy_baseline_from_config(...)` |

Plan 要求 `AgentPolicyBaseline` docstring 说明它是 "runtime assembly merge fallback / baseline values，来源于 config loader 或显式 assembly input，不是 Engine contract defaults，也不是 LLM-facing prompt 文本真源"。

**状态: 已修复**

### P2C-PLAN-F02: tests/host/public_smoke_support.py explicit migration

**Controller 要求**: 显式列出 `tests/host/public_smoke_support.py` 作为 migration target，fixture prompt 值必须显式且不得导出为 shared default source。

**Fixed plan 核查**:

- Plan line 89 "Tests: Host direct fixtures" 显式列出 `tests/host/public_smoke_support.py`。
- Plan Decision 7 (line 133) 要求该 fixture 的 ordinary run baseline `AgentPolicy(...)` 必须显式传入 `fallback_prompt=` 和 `continuation_prompt=`，且 "这些 prompt 只能作为该 fixture 构造点的显式测试输入，不能抽成可跨测试导入的默认真源"。
- 统一 helper guardrail (line 131): "helper 必须 file-local 或 function-local，不得放到 `conftest.py`，不得被其它测试模块 import 为共享默认真源"。

**状态: 已修复**

### P2C-PLAN-F03: test_contract_fields_are_explicit concrete migration

**Controller 要求**: 指定 file path 和 expected test split / rename。

**Fixed plan 核查**:

Plan Decision 7 (lines 134-139) 指定：

- 迁移目标: `tests/engine/test_agent_phase3_tool_call.py::test_contract_fields_are_explicit`
- 不再断言默认 prompt 存在
- 缺 prompt → `TypeError` 测试（拆出或重命名为 `test_agent_policy_prompt_fields_are_required`，分别覆盖缺 `fallback_prompt` 和缺 `continuation_prompt`）
- 显式 prompt acceptance test（`test_agent_policy_accepts_explicit_prompt_fields`）：断言传入文本原样保留
- 非文本默认断言可独立保留或放入显式 prompt acceptance test
- 空白 prompt `ValueError` 仍由 invalid values 测试覆盖，其它字段必须显式传入非空 prompt 避免 `TypeError` 掩盖值校验

**状态: 已修复**

## Guardrails Verification

### P2C-PLAN-G01: utils/ scan coverage

Post-scan acceptance (plan line 163-164) 已扩展为 `rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'`。Proposed files (line 216) 已包含 `utils/**`。

**状态: 已修复**

### P2C-PLAN-G02: test_agent_phase2.py in focused checks

Focused checks (plan line 161) 已包含 `tests/engine/test_agent_phase2.py`。

**状态: 已修复**

## New Material Findings

无新 material findings。

Re-review 过程中检查了 fixed plan 全文，未发现 controller adjudication 未覆盖的新 material blocker。Plan 的 owner boundary、non-goals、design alignment、propagation audit、slice decision、validation commands 均未因 fix 引入新风险。

## Conclusion

**pass**

Controller accepted findings P2C-PLAN-F01、P2C-PLAN-F02、P2C-PLAN-F03 均已在 fixed plan 中修复，guardrails P2C-PLAN-G01、P2C-PLAN-G02 已落实。Plan 保持 code-generation-ready，无新 material findings。

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-p2-c-plan-rereview-mimo.md`
