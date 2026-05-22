# Phase 12.1 Slice 4 Re-Review

## Scope

- **Mode**: re-review（验证 controller-adjudicated accepted findings 修复）
- **Branch**: docs/phase12-design-discussion
- **Base**: main
- **Output file**: docs/reviews/phase12-1-slice4-rereview-ds-20260521.md
- **Implementation artifact**: docs/reviews/phase12-1-slice4-implementation-codex-20260521.md（含 fix addendum）
- **Controller adjudication**: docs/reviews/phase12-1-slice4-code-review-controller-adjudication-20260521.md
- **Prior reviews**: AgentMiMo（PASS）、AgentDS（PASS + 2 residual risks → accepted findings）
- **Re-review scope**:
  - `dayu/engine/provider_extensions.py` — P12.1-S4-F1 修复位置
  - `dayu/runtime/assembly.py` — P12.1-S4-F2 修复位置
  - `tests/engine/test_provider_extension_config_adapter.py` — F1 补充测试
  - `tests/runtime/test_assembly_helpers.py` — F2 补充测试
- **Excluded scope**: pre-existing dirty files（`README.md`、`utils/smoke_host_public_multiturn.py`）及未变更文件

## Verdict: PASS

两个 accepted findings 均已正确修复，无新 blocker。

## Fixed Findings Verification

### P12.1-S4-F1: provider extension contract error wrapping 不一致 — 已修复

- **入口/函数**: `_parse_openai_reasoning` / `_parse_mimo_thinking`
- **文件(行号)**: `dayu/engine/provider_extensions.py:115-118`、`dayu/engine/provider_extensions.py:211-220`
- **修复内容**: 两处 contract 构造均已通过 `_wrap_contract_error` lambda 包裹，与其余 4 个 parser 保持一致。
- **直接证据**:
  - `_parse_openai_reasoning`（行 115-118）：`return _wrap_contract_error(lambda: OpenAIReasoningExtension(reasoning_effort=effort), context=context)`
  - `_parse_mimo_thinking`（行 211-220）：`return _wrap_contract_error(lambda: MimoThinkingExtension(enabled=...), context=context)`
- **测试验证**: `test_provider_extension_dsl_wraps_openai_and_mimo_contract_errors`（`test_provider_extension_config_adapter.py:151-172`）通过 monkeypatch 将 `OpenAIReasoningExtension` 和 `MimoThinkingExtension` 替换为抛出 `ValueError` 的工厂函数，确认两条路径均将 `ValueError` 转换为 `ProviderExtensionConfigError`（match `"invalid field combination"`）。
- **修复风险（低）**: 修改仅改变异常包装路径，不影响正常解析行为；两个 contract 当前均无 `__post_init__`，无行为回归风险。

### P12.1-S4-F2: fallback mode 双真源 — 已修复

- **入口/函数**: `_FALLBACK_MODES` 常量定义
- **文件(行号)**: `dayu/runtime/assembly.py:69-71`
- **修复内容**: `_FALLBACK_MODES` 现在从 `SceneAgentFallbackMode` 枚举值派生，不再手写重复字面量。
- **直接证据**:
  - `assembly.py:69-71`：`_FALLBACK_MODES: Final[frozenset[str]] = frozenset(mode.value for mode in SceneAgentFallbackMode)`
  - 真源 `SceneAgentFallbackMode`（`scene_prepare.py:108-112`）定义 `FORCE_ANSWER = "force_answer"` 和 `RAISE_ERROR = "raise_error"`
  - 消费点 `_validate_fallback_mode`（`assembly.py:837-847`）和 `parse_agent_policy_override_config`（`assembly.py:360`）均使用同一个 `_FALLBACK_MODES`
- **测试验证**: `test_parse_agent_policy_override_accepts_scene_fallback_enum_values`（`test_assembly_helpers.py:125-134`）遍历 `SceneAgentFallbackMode` 全部成员，确认 runtime override parser 接受所有 scene enum 值。
- **修复风险（低）**: 当前枚举值与旧手写字面量完全一致（`"force_answer"` / `"raise_error"`），无行为变化。

## New Blockers

无。

## Tests Run

| 命令 | 结果 |
| --- | --- |
| `pytest tests/engine/test_provider_extension_config_adapter.py -q` | 7 passed |
| `pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 18 passed |
| `python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | pass |

测试数量相比初版 review（6 + 17 = 23）增加到（7 + 18 = 25），新增 2 个 focused test 分别验证 F1 和 F2 修复。

## Residual Risk

- 与初版 review 一致的长期维护责任：未来新增 `ProviderRequestExtension` union 成员时需同步扩展 dispatch、README 与测试矩阵；未来 `SceneAgentFallbackMode` 新增枚举成员时，`_FALLBACK_MODES` 会自动同步（已通过派生消除双真源风险）。
- Service composition helper（runtime config → `RunnerSpec` / `RunnerCallOptions` / Engine `AgentPolicy` 映射）仍延后到 Slice 5，不在本次 re-review 范围内。
