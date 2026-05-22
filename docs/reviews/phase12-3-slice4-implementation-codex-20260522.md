# Phase 12.3 Slice 4 Implementation Report

执行 Agent：AgentCodex  
日期：2026-05-22  
范围：aggregate validation / residual sweep / README sync  
结论：SLICE_COMPLETE

## 动机判断

本 Slice 的动机成立。P12.3 的 root cause 不是 Engine usage 链路缺失，而是 P12.1 / P12.2 后默认配置、Service assembly、Host usage durable association 与文档说明需要聚合验证，确保旧 execution profile 间接引用、默认 runner hint 输出 token cap、usage config override 和旧 `standard` profile id 不再作为当前可用路径残留。

本轮没有修改 production module，没有修改 Host public API、Engine Agent loop 状态机或 Host durable state machine。

## 修改内容

- `dayu/config/README.md`：删除当前 schema 说明中直接列旧 execution profile 字段名的句子，改为只描述当前接受的内嵌 `agent_policy` 与 baseline 结构，以及历史结构会 fail fast。
- `README.md`：把 Host public 多轮 smoke 示例的 execution profile 从 `standard` 改为 `standard-256k`；删除 workspace `models.json` 示例中 runner option hint 的 `max_tokens` 字段。
- `docs/reviews/phase12-3-slice4-implementation-codex-20260522.md`：记录 Slice 4 验证、扫描解释、README 决策与 residual risk 分类。

## 旧字段扫描

执行命令：

```bash
rg -n "agent_policy_profiles|agent_policy_profile_id|runner_option_hints.*max_tokens|usage_enabled|collect_usage|include_usage|supports_usage" dayu tests docs README.md
```

解释：

- `dayu/config/` 默认 JSON、`dayu/runtime/`、`dayu/service/` 没有 `agent_policy_profiles` / `agent_policy_profile_id` 命中。
- `tests/runtime/test_config_loader.py` 中的 `agent_policy_profiles` / `agent_policy_profile_id` 只用于旧 schema negative tests，符合判定规则。
- `docs/host/*discussion*`、`docs/host/phase12*.md` 与 `docs/reviews/*.md` 的命中属于历史 discussion、phase plan 或 review artifact，用于记录旧设计、裁决和验证证据。
- `include_usage` 命中位于 Engine OpenAI payload implementation、Engine tests、Engine README 与 Engine design/历史 artifact。当前生产实现仍只在 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时写入 `stream_options.include_usage=True`，不在 config schema 中提供 override。
- `usage_enabled` / `collect_usage` / `supports_usage` 没有进入 production config schema；相关命中均为 design / plan / review 中的负面约束说明或历史讨论。
- `runner_option_hints.*max_tokens` 在 production config / README 当前示例中已清除。更宽的 `max_tokens` 扫描显示剩余命中只属于 `RunnerCallOptions` public explicit override、Service 默认映射断言 `max_tokens=None`、旧字段 negative tests、Engine OpenAI explicit payload mapping tests 与 Engine contract 文档。

额外 residual sweep：

```bash
rg -n -e "--execution-profile-id standard\b" -e "execution_profile_id=\"standard\"" -e "\"standard\"" README.md dayu/config dayu/runtime dayu/service tests/runtime tests/service
rg -n "\"max_tokens\"|max_tokens" dayu/config dayu/runtime dayu/service tests/runtime tests/service tests/engine dayu/engine README.md
```

结果：

- 当前用户手册示例已使用 `--execution-profile-id standard-256k`。
- `dayu/config/execution_profiles.json` 只包含 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`，没有 `standard` compatibility alias。
- README 的 workspace model 示例不再包含 runner hint `max_tokens`。

## JSON Smoke

```bash
source .venv/bin/activate && python -m json.tool dayu/config/models.json >/dev/null
source .venv/bin/activate && python -m json.tool dayu/config/execution_profiles.json >/dev/null
```

结果：两条命令均通过。

## Focused Tests

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
```

结果：56 passed。

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q
```

结果：62 passed。

```bash
source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q
```

结果：15 passed。

```bash
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_import_boundary.py tests/engine/test_weak_typing_guard.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

结果：34 passed。

## Pyright

```bash
source .venv/bin/activate && python -m pyright dayu/runtime dayu/service dayu/host dayu/engine tests/runtime tests/service tests/host tests/engine
```

结果：0 errors, 0 warnings, 0 informations。

## Diff Check

```bash
git diff --check
```

结果：通过。

## README 决策

- `dayu/config/README.md`：已更新。原因是当前 schema 说明直接列出旧字段名，容易被扫描识别为当前 README 残留；改为只描述新 schema 接受范围与 fail-fast 行为。
- `README.md`：已更新。原因是用户手册 smoke 示例仍使用旧 `standard` profile id，workspace model 示例仍给 runner hint 写 `max_tokens`，均与当前 schema 不一致。
- `dayu/host/README.md`：不更新。当前文本只写 Host usage observation / durable projection 事实，没有把 Engine usage parsing 写成 Host 职责。
- `dayu/engine/README.md`：不更新。当前文本只写 Engine Runner `supports_stream_usage` 门控与流式 payload 行为，没有写 Host budget 决策。
- `tests/README.md`：不更新。当前文本已覆盖 runtime config、Service assembly、Host usage observation / Context Budget 与 Engine OpenAI usage tests；本轮未新增测试层级或运行方式。
- `dayu/README.md`：不更新。分层关系、装配方式与稳定术语未变。

## Residual Risks

| 分类 | 项目 | 处理 |
|---|---|---|
| fixed | `dayu/config/README.md` 当前说明直接列旧 execution profile 字段名 | 已改为新 schema 结构说明，不再复述旧字段名 |
| fixed | 根 README smoke 示例使用旧 `standard` profile id | 已改为 `standard-256k` |
| fixed | 根 README workspace model 示例在 runner hint 中写 `max_tokens` | 已删除，示例只保留 `temperature`、`top_p`、`stream` |
| fixed | Slice 3 review 提到的 smoke test 旧 `standard` profile id 残留 | Slice 3 fix 已修复；本轮 focused tests 与额外扫描复核通过 |
| later phase-work unit | 真实 Service / UI / workflow 尚未接入 execution profile 业务选择 | 仍按 P12.3 non-goal 归后续 Service / UI workflow integration；不得用 compatibility alias 代替显式选择 |
| later phase-work unit | 如未来需要输出 token cap | 必须作为 provider adapter / public contract 独立设计，不回到默认 `models.json.runtime_hints.runner_option_hints` |
| later phase-work unit | `wechat-*` profiles 当前与 `standard-*` 共享 baseline | 当前没有已确认业务差异，保持独立 profile id；后续由业务 profile tuning work unit 按证据调整 |
| existing issue | 历史 discussion、phase plan、review artifact 和 design/control 负面约束说明仍会被 broad regex 命中 | 不属于 production schema / default config / current README usable examples；本 Slice 不改写历史 artifact 或设计真源措辞 |
| requiring user decision | 无当前 Slice 4 blocker；仅当要求设计真源和总控文档也完全避免出现旧字段名/usage override 名称时需要用户裁决 | 当前用户允许修改范围不包含 `docs/host/design.md` 与 `docs/host/implementation-control.md`；若要求 literal zero current-doc hits，需要单独授权文档措辞清理 |

## Fix Addendum: P12.3-S4-F1

结论：FIX_COMPLETE / SLICE_COMPLETE。

Controller 裁决接受 `README.md` 中 runner option hint 说明残留旧 `max_tokens` 语义为当前窄修复项。

修复内容：

- `README.md` 的模型参数说明已改为：`runtime_hints.runner_option_hints` 只承载 temperature、`top_p` 与 stream。
- 同一句明确 `max_tokens` 不在默认模型 hint 中配置，只保留给显式 per-run 或 provider adapter override。
- 未修改 production code、schema、tests、design/control doc、Host public surface 或 Engine public surface。

验证：

```bash
git diff --check
rg -n "max tokens|runtime_hints.runner_option_hints.*max_tokens|max_tokens.*runtime_hints.runner_option_hints" README.md dayu/config/README.md
```

结果：`git diff --check` 通过；targeted README scan 对根 `README.md` 已无冲突命中。`dayu/config/README.md:67` 的命中是 false positive：该行明确写明 runner option hints 只包含 `temperature` / `top_p` / `stream`，并说明 `RunnerCallOptions.max_tokens` 只保留给显式 override，语义正确，不需要修改，也不再列为阻塞。
