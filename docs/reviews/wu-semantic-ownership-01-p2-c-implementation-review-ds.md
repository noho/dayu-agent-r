# WU-SEMANTIC-OWNERSHIP-01 P2-C Implementation Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation code review
- Accepted plan: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Accepted plan commit: `256cda50`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-controller-validation.md`

本轮只 review，不修改文件，不 commit，不 push，不进入 fix/implementation。

## Review Method

- 核查 `git diff 256cda50` 中所有生产、测试、utils 变更。
- 源码扫描旧名残留、新名一致性、`AgentPolicy(...)` 构造点 explicit prompt。
- 复现 8 个 broad suite 失败并逐条核对分类。
- 逐项检查 task file 中的 review focus 列表。

## Finding Checklist

### 1. Engine AgentPolicy 是否真的不再拥有 fallback_prompt / continuation_prompt 的 LLM-facing 默认文本

**通过。** 直接证据：

- `dayu/engine/contracts/agent_policy.py` 中 `_DEFAULT_FALLBACK_PROMPT` 与 `_DEFAULT_CONTINUATION_PROMPT` 已删除（diff 行 -29 至 -35）。
- `fallback_prompt: str` 与 `continuation_prompt: str` 改为无默认必填字段（diff 行 +54-55）。
- `__post_init__` 保留非空校验（行 82-85），但不包含任何默认文本生成逻辑。
- `rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests` 结果：Engine contract 中零命中。剩余命中仅在 `dayu/runtime/config_loader.py`（配置层真源），符合预期。

### 2. Runtime assembly rename 是否完整

**通过。** 直接证据：

| 旧名 | 新名 | 残留扫描 |
|---|---|---|
| `AgentPolicyDefaults` | `AgentPolicyBaseline` | `rg` 零命中 |
| `code_default` | `base_policy` | `rg` 零命中 |
| `_SOURCE_CODE_DEFAULT` | `_SOURCE_RUNTIME_BASE` | `rg` 零命中 |
| `"code_default"` | `"runtime_base"` | `rg` 零命中 |
| `_agent_policy_defaults_from_config(...)` | `_agent_policy_baseline_from_config(...)` | `rg` 零命中 |

所有旧名在 `dayu/`、`tests/`、`utils/`（`--glob '*.py'`）中均为零命中。`__all__` 导出已同步更新（`dayu/runtime/assembly.py:957`）。`AgentPolicyBaseline` docstring（行 161-165）明确说明它是 runtime assembly baseline，不是 Engine contract 默认值，也不是 LLM-facing prompt 文本真源。

所有调用点已迁移：`dayu/service/host_assembly.py`（import、`base_policy=`、`_agent_policy_baseline_from_config`）、`tests/runtime/test_assembly_helpers.py`（import、`_agent_policy_baseline()`、`base_policy=`）。

### 3. Ordinary / compactor / durable restore / Service override 路径是否仍完整传入 prompt

**通过。** Propagation audit 结果：

- **Ordinary path**（`dayu/service/host_assembly.py:628-633`）：`merge_agent_policy_config(base_policy=_agent_policy_baseline_from_config(...))` → `MergedAgentPolicyConfig`（含 `fallback_prompt`、`continuation_prompt`）→ `_agent_policy_from_merged(...)`（行 1699-1708）显式传入 `fallback_prompt=config.fallback_prompt` 和 `continuation_prompt=config.continuation_prompt`。
- **Per-run override path**（`_agent_policy_with_run_overrides`，行 1663-1688）：`fallback_prompt` 可选覆盖（`run_overrides.fallback_prompt` 或 fallback 到 `baseline.fallback_prompt`）；`continuation_prompt` 始终来自 baseline（`baseline.continuation_prompt`，行 1682）。`ServiceRunOverrides`（行 189-208）不含 `continuation_prompt` 字段 — 符合 plan 设计。
- **Compactor path**（`_compactor_agent_policy_from_scene_inputs`，行 1000-1027）：scene `agent_policy` 必填校验覆盖 `fallback_prompt`（行 1012-1013）和 `continuation_prompt`（行 1014-1015），缺字段 fail fast；显式传入 `AgentPolicy(fallback_prompt=override.fallback_prompt, continuation_prompt=override.continuation_prompt)`。
- **Durable restore path**（`agent_policy_from_json`，`_execution_config_projection.py:399-424`）：通过 `required_json_text` 显式读取两个 prompt 字段；`agent_policy_json`（行 375-396）显式序列化两个字段。双向均已完整。
- 下游无"补默认"行为：`AgentPolicy.__post_init__` 只做非空校验（`ValueError`），不生成文本；Engine fallback/continuation 状态机只读取已传入字段。

### 4. tests/host/public_smoke_support.py 是否显式传 prompt

**通过。** `tests/host/public_smoke_support.py:910-911` 显式传入 `fallback_prompt="test fallback prompt"` 和 `continuation_prompt="test continuation prompt"`。这些 prompt 只作为该 fixture 构造点的显式测试输入，未抽取为可跨测试导入的 module-level 默认真源。

### 5. tests/engine/test_agent_phase3_tool_call.py 是否正确覆盖

**通过。** 测试迁移对照 plan 要求逐项验证：

| Plan 要求 | 实现 | 行号 |
|---|---|---|
| 不再断言默认 prompt 存在 | 旧 `test_contract_fields_are_explicit` 已删除，不再有 `assert policy.fallback_prompt`（无参数版本） | — |
| 缺 prompt → TypeError | `test_agent_policy_prompt_fields_are_required`：`pytest.raises(TypeError, match="fallback_prompt")` 和 `match="continuation_prompt"` | 826-839 |
| 显式 prompt acceptance | `test_agent_policy_accepts_explicit_prompt_fields`：断言 `policy.fallback_prompt == _TEST_FALLBACK_PROMPT` 和 `policy.continuation_prompt == _TEST_CONTINUATION_PROMPT` | 798-814 |
| 非文本默认独立保留 | `fallback_mode` 和 `max_consecutive_failed_tool_batches` 断言保留在 explicit prompt acceptance test 中 | 810-811 |
| 空白 prompt → ValueError | `test_agent_policy_rejects_invalid_values` 中所有 negative test 显式传入非空 prompt；空白 `fallback_prompt` 测试仍覆盖 `ValueError` | 847-902 |

### 6. 所有 production/tests/utils AgentPolicy 构造点是否显式传 prompt

**通过。** 双重证据：

- **pyright：** `0 errors, 0 warnings, 0 informations`。`AgentPolicy` 的 `fallback_prompt` 和 `continuation_prompt` 是必填无默认字段，任何遗漏都会导致类型错误。
- **AST 扫描：** `rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'` 共命中约 60 个构造点。仅有的 deliberate negative test 是 `tests/engine/test_agent_phase3_tool_call.py:837,839` 两行，分别用 `pytest.raises(TypeError)` 包裹 `AgentPolicy(**without_fallback_prompt)` 和 `AgentPolicy(**without_continuation_prompt)`。

生产构造点（4 个）全部显式传 prompt：
- `dayu/service/host_assembly.py:1018`（compactor）
- `dayu/service/host_assembly.py:1663`（per-run override）
- `dayu/service/host_assembly.py:1699`（merged config → Engine）
- `dayu/host/_execution_config_projection.py:408`（durable restore）

### 7. README 触发是否满足

**通过。**

- `dayu/engine/README.md`：已更新（行 173），新增说明 `fallback_prompt` 与 `continuation_prompt` 是调用方已经解析好的必填文本，Engine 不提供 LLM-facing prompt 默认值。变更准确、简洁，不对 Engine README 的目标读者引入实现细节。
- `dayu/config/README.md`：已检查，无需更新（它已说明 execution profile `agent_policy` 和默认 fallback prompt 的配置职责）。
- `tests/README.md`：已检查，无需更新（本实现未新增共享 cross-file fixture 或改变测试目录职责）。
- 根 `README.md`、`dayu/README.md`：触发条件不满足（无用户可见 workflow、分层关系、装配方式变化）。

### 8. Broad suite 8 个失败分类复核

**通过。** Controller 分类准确，逐条复现确认：

| # | 测试 | 失败根因 | P2-C 相关？ | 证据 |
|---|---|---|---|---|
| 1 | `tests/engine/test_package_exports.py::test_engine_all_matches_expected_set` | pre-existing extra exports `RunnerInputToolCallProjection`、`RunnerInputMessageProjection` | 否 | 断言比较 `EXPECTED_EXPORTS` 静态集合，与 AgentPolicy 无关 |
| 2 | `tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts` | pre-existing extra export `HostThinkingView` | 否 | 同类型静态 export 集合检查 |
| 3 | `tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary` | pre-existing extra export `HostThinkingView` | 否 | 同上 |
| 4 | `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes` | OpenAI runner idle heartbeat debug log 未触发 | 否 | 失败在 runner stream idle 行为，不涉及 AgentPolicy；P2-C 未修改任何 runner 文件 |
| 5 | `tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked` | pre-existing extra field `input_projection` on `IterationStartedData` | 否 | 静态 dataclass fields 快照检查，与 AgentPolicy 无关 |
| 6 | `tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run` | resume guidance text 断言失败 | 否 | P2-C 对文件的唯一变更是添加 explicit prompt 字段（行 696-697）。失败断言在校验 `resume_request.messages` 中的 guidance text（行 343-351），该文本由 Host resume input builder 生成，不依赖 AgentPolicy prompt 字段。AgentPolicy 的 fallback/continuation prompt 只在 Engine fallback/continuation 状态机中消费，不在等待恢复路径中 |
| 7 | `tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs[cancelling]` | durable CHECK constraint `status NOT IN ('cancelling', 'cancelled')` 冲突 | 否 | 文件未被 P2-C 修改；失败是 durable schema/constraint 问题 |
| 8 | `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | `RunInputMaterialBlock.readable_source_text must be str` TypeError | 否 | 已接受的 umbrella residual；失败在 compact material source projection，与 AgentPolicy prompt 默认无关 |

**结论：** 8 个 broad 失败均不是 P2-C 引入或应在 P2-C 修复。所有失败都是 pre-existing 或属于已接受的 umbrella residual。

## Propagation Audit

```
Config Source (execution_profiles.json / compactor scene)
  → ConfigLoader.AgentPolicyConfig（含 fallback_prompt、continuation_prompt）
    → _agent_policy_baseline_from_config(...) → AgentPolicyBaseline
      → merge_agent_policy_config(base_policy=...) → MergedAgentPolicyConfig
        → _agent_policy_from_merged(...) → AgentPolicy(fallback_prompt=..., continuation_prompt=...)
          → Host OrdinaryRunExecutionBaseline.agent_policy / CompactorRunnerBaseline.compactor_agent_policy
            → Host effective execution config snapshot（agent_policy_json / agent_policy_from_json）
              → AgentRunRequest.agent_policy
                → Engine fallback / continuation 状态机 → LLM user message
```

每一层均显式传入 prompt，无下游"补默认"行为。

## Old Name / Default Text Scan

```
rg -n "AgentPolicyDefaults|code_default|_SOURCE_CODE_DEFAULT|_agent_policy_defaults_from_config" dayu/ tests/ utils/ --glob '*.py'
→ (zero hits)

rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests
→ dayu/runtime/config_loader.py:41 (config-layer default, expected)
→ dayu/runtime/config_loader.py:923 (config-layer helper, expected)
→ Engine contract: zero hits
```

## Finding List

无 material finding。

## Conclusion

**pass**

实现精准执行 accepted plan，无 drift、无 omission、无 regression：

- Engine `AgentPolicy` 的 LLM-facing prompt 文本默认已物理删除，`fallback_prompt` 与 `continuation_prompt` 为必填字段。
- Runtime assembly 旧名全部清理（`AgentPolicyDefaults` / `code_default` / `_SOURCE_CODE_DEFAULT` / `_agent_policy_defaults_from_config`），新名一致（`AgentPolicyBaseline` / `base_policy` / `_SOURCE_RUNTIME_BASE` / `_agent_policy_baseline_from_config`）。
- Ordinary / compactor / durable restore / Service override 四条路径均完整传入 prompt，下游无"补默认"。
- 所有 production / tests / utils `AgentPolicy(...)` 构造点显式传入 prompt（pyright 0 errors 为硬证据）。
- `tests/host/public_smoke_support.py` 显式传 prompt，未引入跨测试默认真源。
- `tests/engine/test_agent_phase3_tool_call.py` 完整覆盖缺 prompt TypeError、显式 prompt acceptance、空白 prompt ValueError。
- README 触发已满足（`dayu/engine/README.md` 已更新）。
- Broad suite 8 个失败均非 P2-C 引入或应在 P2-C 修复；分类准确。

## Residual Risks / Open Questions

- Broad suite 8 个失败仍是 current-branch validation risk，需在 umbrella final closeout 前由对应 owner 处理。
- `utils/smoke_host_public_awaiting_entrypoint.py` 不在本 WU 变更列表中但其 `AgentPolicy(...)` 构造已显式传 prompt（行 981-982）；该脚本不属于 production owner，但若其被其它 smoke 流程引用，需确认调用方不会因 contract 收紧而受影响。
- `ServiceRunOverrides` 仍不支持 per-run `continuation_prompt` override — 这是 plan 明确的设计决策，非 bug，但若后续 product 需求要求 per-run continuation prompt 定制，需单独 WU。

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-ds.md`
