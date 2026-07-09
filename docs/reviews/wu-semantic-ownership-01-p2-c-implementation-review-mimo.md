# WU-SEMANTIC-OWNERSHIP-01 P2-C implementation review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-controller-validation.md`
- Accepted plan commit: `256cda50`

## Review method

Reviewer 阅读了 accepted plan、implementation artifact、controller validation、完整 diff (`git diff 256cda50`)、所有变更的 production / test / utils 文件、Engine design doc 和 Host design doc。逐项核查 review focus 中列出的八个维度。

## Review Focus Findings

### 1. Engine AgentPolicy 是否不再拥有 fallback_prompt / continuation_prompt 的 LLM-facing 默认文本

**结论：PASS。**

`dayu/engine/contracts/agent_policy.py` diff 确认：

- `_DEFAULT_FALLBACK_PROMPT` 与 `_DEFAULT_CONTINUATION_PROMPT` 已物理删除。
- `fallback_prompt: str` 和 `continuation_prompt: str` 改为无默认必填字段（位于 `fallback_mode` 和 `max_consecutive_failed_tool_batches` 默认字段之前，dataclass 字段排序正确）。
- `__post_init__` 保留 `continuation_prompt.strip() == ""` 和 `fallback_prompt.strip() == ""` 的 ValueError 校验。
- `_DEFAULT_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES` 保留，因为它是非 LLM-facing 文本默认。

`rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests` 确认 Engine contract 中不再有 prompt 默认；剩余命中为 `dayu/runtime/config_loader.py` 的 config 层常量，属于 execution profile 真源。

### 2. Runtime assembly rename 是否完整

**结论：PASS。**

`rg -n "AgentPolicyDefaults|code_default|_SOURCE_CODE_DEFAULT" dayu/ tests/ utils/ --glob '*.py'` 返回空结果。完整 rename 清单：

| 旧名 | 新名 | 文件 |
|---|---|---|
| `AgentPolicyDefaults` | `AgentPolicyBaseline` | `dayu/runtime/assembly.py`, `dayu/service/host_assembly.py`, `tests/runtime/test_assembly_helpers.py` |
| `code_default` (参数名) | `base_policy` | `dayu/runtime/assembly.py` (6 处), `dayu/service/host_assembly.py` (3 处), `tests/runtime/test_assembly_helpers.py` (5 处) |
| `_SOURCE_CODE_DEFAULT` | `_SOURCE_RUNTIME_BASE` | `dayu/runtime/assembly.py` |
| source 字符串 `"code_default"` | `"runtime_base"` | `dayu/runtime/assembly.py` |
| `_agent_policy_defaults_from_config` | `_agent_policy_baseline_from_config` | `dayu/runtime/assembly.py`, `dayu/service/host_assembly.py` |
| `__all__` 导出 | `AgentPolicyBaseline` | `dayu/runtime/assembly.py` |

`AgentPolicyBaseline` docstring 已更新，明确它是 "runtime assembly 基线值"，不是 Engine contract 默认值，也不是 LLM-facing prompt 文本真源。

### 3. Ordinary / compactor / durable restore / Service override 路径是否仍完整传入 prompt

**结论：PASS。**

- **Ordinary path**: `dayu/service/host_assembly.py:628` 的 `merge_agent_policy_config(base_policy=_agent_policy_baseline_from_config(execution_profile.agent_policy), ...)` 经 execution profile -> merge -> `_agent_policy_from_merged(config)` -> `AgentPolicy(fallback_prompt=config.fallback_prompt, continuation_prompt=config.continuation_prompt, ...)` 传入。
- **Per-run override path**: `dayu/service/host_assembly.py:1663` 的 `_agent_policy_with_run_overrides(...)` 从 baseline 取 prompt，`run_overrides.fallback_prompt` 非空时覆盖，`continuation_prompt` 不可 per-run 覆盖（来自 baseline）。
- **Compactor path**: `dayu/service/host_assembly.py:1012-1027` 显式校验 `override.fallback_prompt` 和 `override.continuation_prompt` 非空后传入 `AgentPolicy(...)`。
- **Durable restore path**: `dayu/host/_execution_config_projection.py:408-427` 的 `agent_policy_from_json(...)` 使用 `required_json_text(value, field_name="fallback_prompt")` 和 `required_json_text(value, field_name="continuation_prompt")` 显式读取并传入。

没有在任何下游路径中发现重新补默认的行为。

### 4. tests/host/public_smoke_support.py 是否显式传 prompt，且没有新增跨测试默认真源

**结论：PASS。**

`tests/host/public_smoke_support.py:910-911` 新增 `fallback_prompt="test fallback prompt"` 和 `continuation_prompt="test continuation prompt"`。这些值是该构造点的显式测试输入，未抽成可跨测试导入的共享常量或 helper。

### 5. tests/engine/test_agent_phase3_tool_call.py 是否正确覆盖缺 prompt TypeError、显式 prompt acceptance、空白 prompt ValueError

**结论：PASS-with-findings (F01)。**

- **显式 prompt acceptance**: `test_agent_policy_accepts_explicit_prompt_fields` 正确断言 `policy.fallback_prompt == _TEST_FALLBACK_PROMPT` 和 `policy.continuation_prompt == _TEST_CONTINUATION_PROMPT`，同时保留 `fallback_mode` 和 `max_consecutive_failed_tool_batches` 的非文本默认断言。
- **缺 prompt TypeError**: `test_agent_policy_prompt_fields_are_required` 正确覆盖缺 `fallback_prompt` 和缺 `continuation_prompt` 两种情况，用 `pytest.raises(TypeError, match="...")` 包裹。
- **空白 prompt ValueError**: invalid values 测试已更新，所有非空字段测试都显式传入 `_TEST_FALLBACK_PROMPT` 和 `_TEST_CONTINUATION_PROMPT`，避免 TypeError 掩盖 ValueError。

**Finding F01**: `continuation_prompt` 的空白测试只覆盖 `" "` (单 space)，没有像 `fallback_prompt` 那样用循环覆盖 `("", "   ", "\n\t")`。代码逻辑上 `" ".strip() == ""` 与 `"".strip() == ""` 走同一条 ValueError 路径，功能正确；但测试对称性不足。详见 Finding F01。

### 6. 所有 production/tests/utils AgentPolicy 构造点是否显式传 prompt

**结论：PASS。**

`rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'` 扫描了所有构造点。pyright 0 errors 验证了所有非 deliberate negative test 构造点都显式传入了 `fallback_prompt` 和 `continuation_prompt`。唯一的故意省略是 `tests/engine/test_agent_phase3_tool_call.py` 中的 `AgentPolicy(**without_fallback_prompt)` 和 `AgentPolicy(**without_continuation_prompt)`，被 `pytest.raises(TypeError)` 包裹。

### 7. README 触发是否满足

**结论：PASS。**

- `dayu/engine/README.md` 已更新，说明 `fallback_prompt` 与 `continuation_prompt` 是调用方已经解析好的必填文本，Engine 不提供 LLM-facing prompt 默认值。
- `dayu/config/README.md` 已检查，无需更新（已说明 execution profile `agent_policy` 和 compactor scene `agent_policy` 的 prompt 所有权）。
- `tests/README.md` 已检查，无需更新（未新增共享测试 fixture 或改变测试目录职责）。

### 8. 宽测试 8 个失败分类

**结论：PASS。8 个失败均为 non-P2-C residual。**

| 失败测试 | 分类 | 直接证据 |
|---|---|---|
| `test_engine_all_matches_expected_set` | pre-existing | extra exports `RunnerInputMessageProjection`, `RunnerInputToolCallProjection` 来自非 P2-C 变更 |
| `test_host_all_matches_current_public_contracts` | pre-existing | extra export `HostThinkingView` 来自非 P2-C 变更 |
| `test_api_all_stays_request_snapshot_boundary` | pre-existing | same `HostThinkingView` |
| `test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes` | pre-existing | 未触及 P2-C 变更文件 |
| `test_iteration_started_runner_input_signal_fields_are_locked` | pre-existing | extra field `input_projection` 来自非 P2-C 变更 |
| `test_local_awaiting_tool_manual_resolve_resumes_run` | non-P2-C | 失败断言关于 wait-resume guidance text，不涉及 AgentPolicy prompt 默认 |
| `test_purge_session_durable_rejects_non_terminal_runs[cancelling]` | pre-existing | durable CHECK constraint fixture issue，文件未被 P2-C 触及 |
| `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | umbrella residual | 已记录的 accepted evidence compact material source projection 问题 |

无 P2-C 引入或应在 P2-C 修复的失败。

## Findings

### F01: continuation_prompt 空白测试覆盖不对称

- **严重性**: LOW
- **Entry / function**: `tests/engine/test_agent_phase3_tool_call.py::test_agent_policy_rejects_invalid_values`
- **文件 / 行**: `tests/engine/test_agent_phase3_tool_call.py`，continuation_prompt 空白测试段
- **触发输入**: `continuation_prompt=""` 或 `continuation_prompt="   "` 或 `continuation_prompt="\n\t"`
- **实际分支**: 测试只覆盖 `continuation_prompt=" "` (单 space)；缺少 `""` 和 `"\n\t"` 的显式覆盖
- **预期行为**: 与 `fallback_prompt` 空白测试对称，应用循环覆盖 `("", "   ", "\n\t")` 三种情况
- **实际行为**: `" "` 测试通过，功能正确；但 `""` 没有被显式测试
- **直接证据**: `tests/engine/test_agent_phase3_tool_call.py:865-873` 只有一个 `continuation_prompt=" "` case，而 `:896-905` 有 `for invalid_fallback_prompt in ("", "   ", "\n\t")` 循环
- **影响**: 低。`AgentPolicy.__post_init__` 中 `continuation_prompt.strip() == ""` 对 `""` 和 `" "` 走同一条 ValueError 路径，功能正确。但缺少 `""` 的显式测试意味着如果未来 `__post_init__` 校验逻辑变更，空字符串路径可能无回归保护。
- **修复方向**: 在 `test_agent_policy_rejects_invalid_values` 中为 `continuation_prompt` 增加与 `fallback_prompt` 对称的循环测试
- **阻塞性**: 非阻塞。功能正确，测试覆盖有基本保护，可作为后续 cleanup。

## Propagation Audit

P2-C 实现的 propagation 路径验证：

1. **Config source**: `execution_profiles.json` / compactor scene 提供 prompt 文本 → ConfigLoader 校验字段存在 → `AgentPolicyConfig` 持有 prompt
2. **Runtime assembly**: `AgentPolicyBaseline` / `base_policy` 命名表示 runtime merge baseline → `merge_agent_policy_config(...)` 按优先级合并 → `MergedAgentPolicyConfig` 持有 resolved prompt
3. **Service assembly**: `_agent_policy_from_merged(config)` → `AgentPolicy(fallback_prompt=config.fallback_prompt, continuation_prompt=config.continuation_prompt, ...)` → 完整 typed policy
4. **Host durable projection**: `agent_policy_to_json(...)` / `agent_policy_from_json(...)` 读写完整 prompt 字段 → 不补默认
5. **Engine**: `AgentPolicy` 要求显式 prompt 字段 → `__post_init__` 校验非空 → fallback / continuation 状态机使用已传入的 prompt 追加 user message

每一处语义一致，无 "显示正确但持久化错误" 或 "trace 正确但 memory 错误" 的风险。

## Residual Risks / Open Questions

1. **F01 对称性 gap**: `continuation_prompt` 空白测试覆盖不足，非阻塞，建议后续 cleanup 补齐。
2. **宽测试 8 个 residual**: 已分类为 non-P2-C，但仍是当前分支 validation risks，需在 umbrella closeout 前处理。
3. **外部调用方 contract 收紧**: 直接实例化 `AgentPolicy(...)` 的外部调用方若省略 prompt 会从运行时默认变成 `TypeError`。这是期望的 contract 收紧，不做兼容。

## Conclusion

**pass-with-findings**

P2-C 实现正确完成了 plan 中的所有 mandatory items：

- Engine `AgentPolicy` 不再拥有 LLM-facing prompt 文本默认值
- Runtime assembly rename 完整，无残留
- 所有 production / test / utils 构造点显式传入 prompt
- Service ordinary / compactor / durable restore / override 路径完整传入 prompt
- README 已按触发规则更新
- 宽测试 8 个失败已分类为 non-P2-C residual

唯一 finding (F01) 是 `continuation_prompt` 空白测试覆盖不对称，严重性 LOW，非阻塞。

artifact path: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-mimo.md`
