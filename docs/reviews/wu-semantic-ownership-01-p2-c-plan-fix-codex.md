# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: plan review fix
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Fix owner: AgentCodex
- Plan decision after fix: `ready`

本次只修改 plan artifact，并新增本 fix artifact。未修改生产代码、测试、README、控制文档，未进入 implementation。

## First-principles Judgment

Accepted findings 的动机成立。P2-C 的根问题是 LLM-facing fallback / continuation prompt 文本存在 Engine contract 与 execution profile 双真源。若 plan 仍允许 runtime assembly 使用 `code_default` / `AgentPolicyDefaults` 这类命名，或遗漏 Host public smoke fixture、具体 contract test 迁移和扫描 guardrail，implementation 仍可能把 prompt 默认误读为代码层事实。因此这些不是单纯文案偏好，而是 owner boundary 可执行性缺口。

修复边界应落在 plan：当前 gate 只要求使 implementation plan decision-ready，不应改生产代码或测试。

## Fixed Findings

### P2C-PLAN-F01

Finding: `AgentPolicyDefaults` / `code_default` 命名和 docstring cleanup 不能留给 implementation 自行判断。

Fix:

- 将 runtime assembly cleanup 从条件性建议改为硬性 implementation decision。
- 明确 before / after 命名：
  - `AgentPolicyDefaults` -> `AgentPolicyBaseline`
  - `code_default` -> `base_policy`
  - `_SOURCE_CODE_DEFAULT` -> `_SOURCE_RUNTIME_BASE`
  - source 字符串 `"code_default"` -> `"runtime_base"`
  - `_agent_policy_defaults_from_config(...)` -> `_agent_policy_baseline_from_config(...)`
- 要求 `AgentPolicyBaseline` docstring 明确它是 runtime assembly merge baseline，不是 Engine contract default，也不是 LLM-facing prompt 文本真源。

### P2C-PLAN-F02

Finding: plan 未显式列出 `tests/host/public_smoke_support.py`，且测试 fixture 可能形成跨测试默认真源。

Fix:

- 在 affected tests 中显式列出 `tests/host/public_smoke_support.py`。
- 在 test migration decision 中要求该 fixture 的 ordinary run baseline `AgentPolicy(...)` 必须显式传入 `fallback_prompt=` 和 `continuation_prompt=`。
- 明确这些 prompt 只能作为该 fixture 构造点的显式测试输入，不得抽成可跨测试导入的默认真源。
- 增加统一 helper guardrail：测试 helper 必须 file-local 或 function-local，不得放 `conftest.py`，不得被其它测试模块 import。

### P2C-PLAN-F03

Finding: `tests/engine/test_agent_phase3_tool_call.py::test_contract_fields_are_explicit` 迁移不够具体。

Fix:

- 指定迁移目标文件和测试名。
- 要求不再断言默认 prompt 存在。
- 要求用缺 `fallback_prompt` / 缺 `continuation_prompt` 的 `TypeError` 测试表达 prompt 字段必填。
- 要求显式 prompt acceptance test 断言传入文本原样保留。
- 明确非文本默认断言可独立保留，或放入显式 prompt acceptance test。
- 明确空白 prompt 的 `ValueError` 仍由 invalid values 测试覆盖，且其它字段必须显式传入非空 prompt，避免 `TypeError` 掩盖值校验。

## Implementation Guardrails Added

- Post-scan acceptance 扩展为：

```bash
rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'
```

- Focused engine tests 增加：

```bash
tests/engine/test_agent_phase2.py
```

- `utils/**` 加入 proposed files / scan boundary；若存在省略 prompt 的 smoke script，应在脚本内显式传入 prompt，不新增跨脚本默认真源。

## Owner Boundary Confirmation

Plan 仍保持核心方向：

- Engine 删除 LLM-facing prompt text defaults。
- Ordinary Run prompt 默认由 execution profile 产生。
- Compactor prompt 由 compactor scene required `agent_policy` 产生。
- Runtime assembly 只合并 caller / config 已给出的 baseline，不拥有 Engine default。
- Host / durable projection / Engine / LLM message 都消费同一条已解析 policy 路径派生出的 prompt。

## Validation

本 gate 仅改文档。执行：

```bash
git diff --check
```

结果：PASS，exit code 0，无 whitespace error 输出。

## Open Questions

无阻塞问题。
