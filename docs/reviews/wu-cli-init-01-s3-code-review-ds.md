# WU-CLI-INIT-01 S3 Code Review (DS)

## Gate metadata

- **Work unit**: `WU-CLI-INIT-01`
- **Slice**: `S3 — Package defaults 与 Service compactor assembly`
- **Reviewer**: DS (独立审查)
- **Date**: 2026-07-30 16:03 CST
- **Base ref**: `9e6cde82`
- **Diff scope**: 未提交 S3 改动（6 files, +534/−29）
- **Output file**: `docs/reviews/wu-cli-init-01-s3-code-review-ds.md`
- **Accepted plan**: `docs/reviews/wu-cli-init-01-plan-codex.md`（S3 部分）
- **Implementation artifact**: `docs/reviews/wu-cli-init-01-s3-implementation-codex.md`

## Scope

- Mode: current changes (relative to `9e6cde82`)
- Branch: `ci/pr-179-first-ci-readiness`
- Reviewed files:
  - `dayu/config/execution_profiles.json`
  - `dayu/config/prompts/manifests/conversation_compaction.json`
  - `dayu/service/host_assembly.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/service/test_host_assembly.py`
  - `tests/cli/test_init_catalog.py`
- Parallel review coverage: 无（DS 独立逐链路走读）

## Verdict

**PASS**

无 material defect。S3 改动在其 owner boundary 内完整兑现了 accepted plan 的冻结语义：三个 selection 各取正确 hints/baseline/override；family 校验在 secret resolution 前且不泄漏 secret/endpoint/ref；generic `ValueError` 与 Service 既有错误所有权一致；package MIMO-only 与 workspace DeepSeek-only 测试真实证明单 credential；runner hints/compactor prompt 行为保留；配置的 context-window 自洽。

以下 findings 按严重度排列。一个严重度为"中"、其余两个严重度为"低"，均不影响 S3 frozen semantics 的正确性。

## Findings

### 1-FROZEN-[中]-`test_explicit_1m_profile_with_256k_model_fails_fast` 的 compactor 装配分支在 family check 前无法到达

- **入口/函数**: `compose_open_host_options` → `_require_matching_model_families`
- **文件(行号)**: `tests/service/test_host_assembly.py:2838`
- **输入场景**: `test_explicit_1m_profile_with_256k_model_fails_fast` 测试。profile=standard-1m，run_baseline.model_id="ollama"，custom compactor scene model_id="ollama"，scene_model_hints=None。覆盖 `execution_baseline` 作为 compactor 来源的场景。
- **实际分支**: 在 `_require_matching_model_families` 执行前（line 637），`validate_execution_profile_context_window` 对 `compactor_selection` 的校验（line 633-636）已因 ollama 的 262144 < 1,000,000 抛出 `RuntimeAssemblySelectionError`。
- **预期行为**: 对于 `scene_model_hints=None` 且 execution_baseline/compactor_baseline 为 ollama 的场景，要么先触发 family check 再触发 context window check，要么至少测试覆盖两笔检查的先后顺序证明不受影响。
- **实际行为**: context window check 总是先触发，family check 不可达。功能上不产生错误（因为 context window fail-fast 是正确的），但该测试不能有效证明 family check 和 context window check 之间没有隐式顺序依赖。
- **直接证据**: `host_assembly.py:629-636` 的 `validate_execution_profile_context_window` 在 `_require_matching_model_families`（line 637）之前执行；`assembly.py:413-420` 在 `model.context_window_tokens < profile.min_context_window_tokens` 时立即 raise。
- **影响**: 功能性无影响——两种检查的正确性独立得到其他测试覆盖（family mismatch 由 `test_compactor_family_mismatch_fails_before_host_options_without_secret_leak` 覆盖，context window fail-fast 由本测试和现有 coverage 覆盖）。仅影响本特定测试对两笔检查顺序的联合覆盖广度。
- **建议改法和验证点**: 维持现状，在 review 中记录为 documented residual。若未来需要联合覆盖这两笔检查的交错，需构造一个 family 不同、但两个模型都通过 context window check 的场景。当前 package Mimo 模型 context_window_tokens=1,048,576 对所有四个 profile 兼容，无法在包内构造该场景。
- **修复风险（低）**: 不修；仅记录。
- **严重程度（中）**: 不影响 correctness，但本测试的 compactor 装配分支在 family check 前不可达，属于测试覆盖面的一个小盲区。功能正确性由其他独立测试覆盖。

### 2-FROZEN-[低]-`primary_default_selection` 与 `ordinary_selection` 的求值位置间无中间状态污染风险，但诊断输出不包含 primary_default 特征

- **入口/函数**: `compose_open_host_options` → `_assembly_diagnostics`
- **文件(行号)**: `dayu/service/host_assembly.py:605-611`, `dayu/service/host_assembly.py:1717-1778`
- **输入场景**: 任意合法 assembly 请求。
- **实际分支**: `primary_default_selection` 求值后只用于 family check，其 `model_id` 和 `runner_option_hint_id` 不进入 `ServiceOpenHostAssemblyDiagnostics`；diagnostics 的 `model_id` / `compactor_model_id` 来自 `ordinary_selection` / `compactor_selection`（line 1757, 1761）。
- **预期行为**: diagnostics 无义务暴露 primary_default_selection；它只是 durable truth anchor，不是 effective execution 选择。
- **实际行为**: 符合 design（plan Section 5 明确 primary default 只用于 family check）。外部 observer 无法从 diagnostics 区分 "primary/compactor 同源"与"primary/compactor 不同源但刚好没有 mismatch check"。
- **直接证据**: `ServiceOpenHostAssemblyResult` 已暴露 `ordinary_selection` 与 `compactor_selection`（line 375-376），但未暴露 primary default。plan Section 5 table 的语义 owner 列为 runtime family identity helper，不要求 UI/observability 投影。
- **影响**: 运维排障时需通过 ordinary_selection 反推 primary default（当 model_source != run_override 时 ordinary = primary default），增加一点推理负担。不影响 correctness。
- **建议改法和验证点**: 可选在 `ServiceOpenHostAssemblyResult` 或 diagnostics 中增加 `primary_default_model_id` 字段。属于 enhancement，非 S3 blocking。
- **修复风险（低）**: 不修。
- **严重程度（低）**: observability gap，不影响 correctness。

### 3-FROZEN-[低]-DeepSeek compactor hint 的 temperature=0.4 不再使用，不存在残留引用但无 regression guard

- **入口/函数**: `dayu/config/models.json` 中 `deepseek-v4-flash.runtime_hints.runner_option_hints.conversation_compaction`
- **文件(行号)**: `dayu/config/models.json`（未修改）；`tests/service/test_host_assembly.py:451,474`
- **输入场景**: DeepSeek 模型的 `conversation_compaction` hint（temperature=0.4）现在仅在 workspace 通过 init 显式选 DeepSeek 后 compactor 仍为 DeepSeek 的场景中使用。若未来 S4/S5 引入 bug 导致 workspace DeepSeek 投影时 compactor 仍为 Mimo，该 hint 会静默不被选中而无报错。
- **实际分支**: 测试 `test_workspace_projected_family_assembles_without_package_mimo_key` 在 line 474 断言 compactor temperature=0.4（DeepSeek hint），正确覆盖了 workspace DeepSeek 场景。但该断言只是集成测试的一部分，没有独立的 "DeepSeek conversation_compaction hint 仍存在并可被选中" 的 regression guard。
- **预期行为**: DeepSeek `conversation_compaction` hint 作为 provider-specific asset，应在 DeepSeek 被选为 compactor 时生效。
- **实际行为**: 当前正确。但 DeepSeek hint 的 regression guard 仅由一处的集成断言间接提供，没有 focused unit test。
- **直接证据**: `tests/service/test_host_assembly.py:474` 的 `assert compactor_options.compactor_runner_options.temperature == 0.4`。
- **影响**: 低概率——DeepSeek catalog entry 是显式保留的 production asset，不会误删。仅当 `models.json` 中 DeepSeek 的 `conversation_compaction` hint 被意外修改/删除时，无 focused test 直接失败。
- **建议改法和验证点**: 维持现状。显式 DeepSeek provider asset 的分类处置已在 plan inventory（Section S3 pre-change inventory）中明确为"保留"。该 hint 的值正确性属于 provider config 的 owner contract，不属于 S3 scope。
- **修复风险（低）**: 不修。
- **严重程度（低）**: 间接覆盖，probabilistic regression risk。

## Verification

### 测试结果

```
pytest tests/runtime/test_config_loader.py \
  tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q

244 passed in 2.51s
```

### Pyright

```
pyright dayu/service/host_assembly.py \
  tests/runtime/test_config_loader.py tests/service/test_host_assembly.py \
  tests/cli/test_init_catalog.py

0 errors, 0 warnings, 0 informations
```

### 冻结语义逐项验证

| 冻结语义 | 验证方法 | 结论 |
|---|---|---|
| compactor 与 durable 主默认同 provider/provider_model/endpoint/credential_ref | `test_package_sixteen_manifests_share_mimo_token_plan_family` + `test_package_execution_profile_baselines_share_mimo_token_plan_family` + `test_static_choice_compactor_projection_shares_ordinary_family`（参数化 13 choices） | ✅ |
| thinking/temperature/stream 可不同 | Mimo thinking 只写 extends，temperature=0.3（Mimo hint）≠ DeepSeek 的 0.4；两者 stream 均为 False | ✅ |
| `--model/-m` 只覆盖本次主 Run | `test_package_defaults_use_only_mimo_and_isolate_cross_family_run_override`：override 后 `ordinary_selection.model_id==deepseek-v4-flash` 但 `compactor_selection` 不变 | ✅ |
| 未 init 的 package defaults 同族且不要求第二套 credential | `test_package_defaults_use_only_mimo_and_isolate_cross_family_run_override` 只传 `MIMO_PLAN_API_KEY`，成功完成 assembly | ✅ |
| workspace init 后同样成立 | `test_workspace_projected_family_assembles_without_package_mimo_key` 只传 `DEEPSEEK_API_KEY`，assembly 成功且 ordinary/compactor family 同源 | ✅ |
| 三个 selection 各取对 hints/baseline/override | `primary_default_selection`（no override）、`ordinary_selection`（with override）、`compactor_selection`（compactor scene hints + compactor baseline, no override） | ✅ |
| family 校验在 secret resolution 前且不泄漏 | `_require_matching_model_families` 在 line 637，`_compose_options` 在 line 647；mismatch 测试断言 endpoint/credential 不在错误消息中 | ✅ |
| generic ValueError 与 Service 既有错误所有权一致 | `_require_matching_model_families` raise plain `ValueError`；`compose_open_host_options` 中大量使用 `ValueError`（unsupported worker backend、missing secret 等），同类错误用同类类型 | ✅ |
| package MIMO-only 与 workspace DeepSeek-only 证明单 credential | 两个 focused tests（见上） | ✅ |
| runner hints/compactor prompt 保留 | compactor hint id 保持 `conversation_compaction`；agent_policy 字段未变；fragment/path 未变 | ✅ |
| context-window 自洽 | `mimo-v2.5-pro-plan` context_window_tokens=1,048,576；对所有 profile 的 min（256k=262,144, 1m=1,000,000）均满足；`context_budget_policy` 与 `memory_projection_policy` 均使用 `ordinary_selection.model.context_window_tokens` | ✅ |

### Pre-change DeepSeek inventory 处置

- package-default owner：`execution_profiles.json` 8 个 baseline ref + `conversation_compaction.json` manifest → 已迁移 ✅
- 偶然默认断言：`test_host_assembly.py` 旧 compactor 断言 → 已迁移 ✅
- 显式 DeepSeek catalog / provider-specific production asset（`models.json`、`init_catalog.py`、`smoke_async_agent_providers.py`、`config/README.md`）→ 保留 ✅
- 显式 DeepSeek fixture / provider contract（各类测试）→ 保留，环境变量从单 `DEEPSEEK_API_KEY` 扩展为 `_host_assembly_env()` 以同时提供 Mimo key ✅

### 未修改的文件

以下 plan S3 允许范围外的文件均未被本 slice 修改（由 `git diff --stat` 与 `rg` 确认）：
- `dayu/config/models.json`（DeepSeek catalog 保留）
- `dayu/cli/init_catalog.py` 的 DeepSeek choice 条目
- `utils/smoke_async_agent_providers.py`
- `dayu/config/README.md`
- 所有显式 DeepSeek fixture/contract 测试文件

## Open Questions

无。所有 blocking questions 已在 accepted plan 中冻结。

## Residual Risk

1. **测试 `test_explicit_1m_profile_with_256k_model_fails_fast` 的 compactor 分支不可达**：见 Finding 1-FROZEN。context window check 总是在 family check 前触发，该测试不能联合覆盖两笔检查的先后顺序。不影响 correctness——两笔检查的正确性由其他独立测试覆盖。不会阻止 merge。

2. **DeepSeek `conversation_compaction` hint 无 focused regression guard**：见 Finding 3-FROZEN。该 hint 仅由一处集成断言间接覆盖。DeepSeek catalog 是 production asset，删除风险很低。

3. **S4/S5/S6 未执行**：managed transaction 的 no-follow TOCTOU、versioned publication manifest、15-row real provider matrix、README 更新均未完成。但这些在 accepted plan 中已分配给 S4-S6，不归属 S3 residual risk。

4. **九个既有测试的 env 变更**：从 `{"DEEPSEEK_API_KEY": _API_KEY}` 改为 `_host_assembly_env()`（同时提供 MIMO_PLAN_API_KEY）。这些测试仍显式选择 DeepSeek ordinary，但 compactor 现在需要 Mimo credential。若未来有人误删 `MIMO_PLAN_API_KEY` 从 `_host_assembly_env()`，这些测试会因 missing env 失败。这属于测试 helpers 的正常演化，不构成 regression risk。

## Full pyright

```
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```
