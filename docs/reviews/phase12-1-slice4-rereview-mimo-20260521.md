# Phase 12.1 Slice 4 Re-Review

## Scope

- Mode: re-review of accepted findings P12.1-S4-F1 / F2
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Gate: Slice 4 code review fix verification
- Output file: `docs/reviews/phase12-1-slice4-rereview-mimo-20260521.md`
- Controller adjudication: `docs/reviews/phase12-1-slice4-code-review-controller-adjudication-20260521.md`
- Implementation artifact (with fix addendum): `docs/reviews/phase12-1-slice4-implementation-codex-20260521.md`

## Verdict

**PASS**

## Fixed Findings Verification

### P12.1-S4-F1: `_parse_openai_reasoning` 与 `_parse_mimo_thinking` 的 contract error wrapping

- **要求**: 两个解析函数必须通过 `_wrap_contract_error` 构造 Engine typed contract。
- **验证结果**: 已修复。
- **直接证据**:
  - `dayu/engine/provider_extensions.py:115-118` — `_parse_openai_reasoning` 现在通过 `_wrap_contract_error(lambda: OpenAIReasoningExtension(reasoning_effort=effort), context=context)` 返回。
  - `dayu/engine/provider_extensions.py:211-220` — `_parse_mimo_thinking` 现在通过 `_wrap_contract_error(lambda: MimoThinkingExtension(enabled=...), context=context)` 返回。
  - 与其它四个解析函数（`_parse_anthropic_thinking` L137、`_parse_deepseek_thinking` L184、`_parse_gemini_thinking` L258、`_parse_qwen_thinking` L290）的 wrapping 模式一致。
- **测试覆盖**: `test_provider_extension_dsl_wraps_openai_and_mimo_contract_errors`（`tests/engine/test_provider_extension_config_adapter.py:151-172`）通过 monkeypatch 模拟未来 OpenAI / MiMo contract `ValueError`，验证两条路径均统一转换为 `ProviderExtensionConfigError`。

### P12.1-S4-F2: `_FALLBACK_MODES` 从枚举派生

- **要求**: `_FALLBACK_MODES` 必须从 `SceneAgentFallbackMode` 枚举派生，不得手写字面量集合。
- **验证结果**: 已修复。
- **直接证据**: `dayu/runtime/assembly.py:69-71` — `_FALLBACK_MODES: Final[frozenset[str]] = frozenset(mode.value for mode in SceneAgentFallbackMode)`，从枚举成员动态派生。
- **测试覆盖**: `test_parse_agent_policy_override_accepts_scene_fallback_enum_values`（`tests/runtime/test_assembly_helpers.py:125-134`）遍历全部 `SceneAgentFallbackMode` 枚举成员，确认 `parse_agent_policy_override_config` 接受每个值。

## New Blockers

无。

## Tests Run

| 命令 | 结果 |
| --- | --- |
| `pytest tests/engine/test_provider_extension_config_adapter.py -q` | 7 passed |
| `pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 18 passed |
| `python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime` | 0 errors, 0 warnings |
| `git diff --check` | pass |

## Residual Risks

- 无新增 residual risk。两个修复均为窄范围一致性改善，不改变 public behavior，不引入新依赖或新边界。
- Provider DSL helper 未来新增 `ProviderRequestExtension` union 成员时仍需同步扩展 helper、README 与测试矩阵，该风险已在原 implementation artifact 中归类为长期维护责任，不阻塞当前 slice。
