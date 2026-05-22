# Phase 12.3 Slice 4 Code Review

审查 Agent：AgentMiMo  
日期：2026-05-22  
审查范围：Slice 4 aggregate sweep 未提交 diff  
结论：**PASS**

## 1. Verdict

Slice 4 aggregate validation / residual sweep / README sync 实现正确，无 blocking finding。当前 diff 改动符合 plan 判定规则，旧字段扫描解释可信，README 已同步更新。

## 2. Diff Summary

当前未提交改动（2 files changed, 2 insertions, 4 deletions）：

| 文件 | 改动 |
|---|---|
| `README.md` | smoke 示例 execution profile 从 `standard` 改为 `standard-256k`；删除 runner option hint 中的 `max_tokens` |
| `dayu/config/README.md` | 将直接列出旧字段名的句子改为只描述当前接受的内嵌结构与 fail-fast 行为 |

## 3. 重点检查项

### 3.1 README 示例迁移

**检查项**：README 当前示例是否已迁移为 standard-256k，runner hint 示例是否不再写 max_tokens。

**结论**：PASS

- `README.md:967`：smoke 示例已使用 `--execution-profile-id standard-256k`。
- `README.md:1108-1119`：workspace model 示例 runner_option_hints 只包含 `temperature`、`top_p`、`stream`，无 `max_tokens`。
- `dayu/config/README.md:67`：明确说明"只包含 `temperature`、`top_p` 与 `stream`"，且"默认配置不提供输出 token cap"。

### 3.2 dayu/config/README.md Schema 说明

**检查项**：是否只描述当前 schema，不再把旧 schema 字段作为当前说明残留。

**结论**：PASS

- `dayu/config/README.md:95`：改为"配置只接受上述内嵌 `agent_policy` 与 baseline 结构；历史 catalog、间接引用或全局 runner/agent hint 结构出现在配置中都会加载失败。"
- 不再直接列出旧字段名 `agent_policy_profiles`、`agent_policy_profile_id`、`runner_options_profiles`、`runner_hints`、`agent_hints`，避免被扫描识别为当前 README 残留。

### 3.3 Artifact 旧字段扫描解释

**检查项**：artifact 中旧字段扫描解释是否符合 plan 判定规则，没有掩盖 production schema/default config/README 中的真实残留。

**结论**：PASS

复跑扫描命令验证：

```bash
rg -n "agent_policy_profiles|agent_policy_profile_id|runner_option_hints.*max_tokens|usage_enabled|collect_usage|include_usage|supports_usage" dayu tests docs README.md
```

命中分析：

| 命中类型 | 位置 | 判定 |
|---|---|---|
| `include_usage` | `dayu/engine/runners/openai/_types.py:35`, `payload.py:13,358`, `README.md:135`, `contracts/runner_spec.py:238-239`, tests | Engine OpenAI payload implementation / tests / docs，受 `stream=True` + `supports_stream_usage=True` 门控，符合 plan |
| `include_usage` | 历史 artifact (`docs/engine/phase1*.md`, `docs/reviews/*.md`) | 设计/plan/review 历史记录，非 production |
| `agent_policy_profiles` / `agent_policy_profile_id` | `tests/runtime/test_config_loader.py:594-600,713-725` | 旧 schema negative tests，符合 plan 判定规则 |
| `agent_policy_profiles` / `agent_policy_profile_id` | `docs/` 目录下大量文件 | 历史 discussion、phase plan、review artifact，非 production |
| `usage_enabled` / `collect_usage` / `supports_usage` | `docs/` 目录下 | 设计/plan/review 中的负面约束说明或历史讨论 |

**额外 residual sweep 验证**：

```bash
rg -n --execution-profile-id standard\b README.md dayu/config dayu/runtime dayu/service tests/runtime tests/service
```

结果：无命中。当前用户手册示例已使用 `standard-256k`。

```bash
rg -n "max_tokens" dayu/config/models.json
```

结果：无命中。models.json 中 runner_option_hints 已清除 `max_tokens`。

```bash
rg -n "agent_policy_profiles|agent_policy_profile_id" dayu/config/execution_profiles.json
```

结果：无命中。execution_profiles.json 已删除旧字段。

### 3.4 Usage Override 相关词

**检查项**：usage override 相关词是否没有进入 config schema，include_usage 是否仅在 Engine OpenAI gate 语义内。

**结论**：PASS

- `usage_enabled`、`collect_usage`、`supports_usage` 未出现在 `dayu/config/` 下任何文件。
- `include_usage` 仅出现在 Engine OpenAI payload 实现（`dayu/engine/runners/openai/payload.py:358`），受 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 门控。
- `dayu/config/README.md` 未提及 usage override 相关配置。

### 3.5 README 同步完整性

**检查项**：是否有应当同步但未同步的 README，或 README 越界写未来计划/过程状态。

**结论**：PASS

按 CLAUDE.md README 触发规则检查：

| README | 触发条件 | 决策 | 理由 |
|---|---|---|---|
| `dayu/config/README.md` | config 修改 | 已更新 | schema 说明已同步 |
| `README.md` | 项目级使用方式变化 | 已更新 | smoke 示例和 workspace 示例已同步 |
| `dayu/host/README.md` | host 修改 | 不更新 | 当前文本只写 Host usage observation / durable projection 事实，未过期 |
| `dayu/engine/README.md` | engine 修改 | 不更新 | 当前文本只写 Engine Runner `supports_stream_usage` 门控行为，未过期 |
| `tests/README.md` | tests 修改 | 不更新 | 当前文本已覆盖 runtime config、Service assembly、Host usage observation 与 Engine OpenAI usage tests |
| `dayu/README.md` | 分层关系变化 | 不更新 | 分层关系、装配方式与稳定术语未变 |

所有 README 未写未来计划、过程状态或版本记录。

### 3.6 验证命令覆盖度

**检查项**：验证命令是否足够覆盖 P12.3 聚合风险。

**结论**：PASS

复跑所有验证命令：

| 命令 | 结果 |
|---|---|
| `python -m json.tool dayu/config/models.json >/dev/null` | OK |
| `python -m json.tool dayu/config/execution_profiles.json >/dev/null` | OK |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 56 passed |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 62 passed |
| `pytest tests/engine/test_config_models.py tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` | 15 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_import_boundary.py tests/engine/test_weak_typing_guard.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 34 passed |
| `python -m pyright dayu/runtime dayu/service dayu/host dayu/engine tests/runtime tests/service tests/host tests/engine` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

验证命令覆盖了：
- JSON 格式 smoke
- Config loader / assembly / Service assembly 测试
- Host usage observation 测试
- Engine config / usage 测试
- Import boundary / weak typing guard 测试
- Pyright 类型检查
- Whitespace check

## 4. Blocking Findings

无 blocking finding。

## 5. Non-blocking Observations

无 non-blocking observation。

## 6. Residual Risks

按 implementation artifact 分类：

| 分类 | 项目 | 验证 |
|---|---|---|
| fixed | `dayu/config/README.md` 当前说明直接列旧 execution profile 字段名 | 已改为新 schema 结构说明 ✓ |
| fixed | 根 README smoke 示例使用旧 `standard` profile id | 已改为 `standard-256k` ✓ |
| fixed | 根 README workspace model 示例在 runner hint 中写 `max_tokens` | 已删除 ✓ |
| later phase-work unit | 真实 Service / UI / workflow 尚未接入 execution profile 业务选择 | 按 P12.3 non-goal 归后续 |
| later phase-work unit | 如未来需要输出 token cap | 必须作为 provider adapter / public contract 独立设计 |
| later phase-work unit | `wechat-*` profiles 当前与 `standard-*` 共享 baseline | 保持独立 profile id，后续按证据调整 |
| existing issue | 历史 discussion、phase plan、review artifact 仍会被 broad regex 命中 | 非 production schema / default config / current README |

## 7. 结论

Slice 4 aggregate sweep 改动正确，README 已同步，旧字段扫描解释可信，验证命令覆盖充分。**PASS**。
