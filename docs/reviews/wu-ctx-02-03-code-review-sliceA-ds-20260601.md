# WU-CTX-02 + WU-CTX-03 Slice A Code Review — DS

- Gate: WU-CTX-02 + WU-CTX-03 implementation Slice A code review
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Accepted plan commit: `9d89db3`
- Implementation artifact: `docs/reviews/wu-ctx-02-03-implementation-sliceA-codex-20260601.md`
- Review artifact: `docs/reviews/wu-ctx-02-03-code-review-sliceA-ds-20260601.md`
- Reviewer: AgentDS
- Review scope: Slice A only — 默认 policy / config / model 对齐

## Review Scope

Target files reviewed (working tree diff vs HEAD):

- `dayu/host/context_policy.py` — `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` 2→5
- `dayu/config/execution_profiles.json` — 四个 packaged profile 的 `max_compaction_attempts_per_operation` 3→5
- `dayu/config/prompts/manifests/conversation_compaction.json` — `default_model_id` 从 high-spec 改为 `deepseek-v4-flash`
- `tests/host/test_context_policy.py` — 新增 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION == 5` 断言
- `tests/runtime/test_config_loader.py` — 新增全 profile attempt budget 遍历断言 + standard-256k 单独断言
- `tests/runtime/test_scene_assets_migration.py` — 新增 scene ↔ profile compactor model 一致性测试
- `tests/service/test_host_assembly.py` — 新增 assembled policy attempt budget == 5 断言

Not in scope (not changed, not reviewed):

- `dayu/service/host_assembly.py` production logic（未修改；既有一致性映射无需改动）
- `dayu/host/context_events.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 等 Slice B-E 范围文件
- README 文件（检查后确认无需更新）

## Review Method

1. 逐文件核对 diff 与 approved plan §7 Slice A 的 exact allowed changes、stop conditions、non-goals。
2. 验证全链路一致性：`DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` → execution profiles → Service assembly → Host options。
3. 验证场景模型变更只触及 `conversation_compaction`，不误改普通 scene、不引入 scene inheritance 防御。
4. 验证测试覆盖真实 package defaults、service assembly 与 scene/profile 一致性。
5. 检查类型安全、中文 docstring、`Any`/`object`/魔法数字与架构分层。
6. 检查是否越界修改 schema / public API / Service request shape。
7. 搜索旧值残留（stale `2`/`3` hardcoded 未随常量更新）。
8. 运行受影响测试与 pyright 类型检查。

## Per-File Verification

### dayu/host/context_policy.py

- L22: `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 5` ✅
- 该常量被两处使用：
  - `default_context_budget_policy()` 默认参数 (L169-L171) ✅
  - `context_budget_policy_from_threshold_tokens()` 默认参数 (L211-L213) ✅
- `ContextBudgetPolicy.__post_init__` 调用 `_require_positive_int` 校验该字段 (L107-L112) ✅
- 未新增字段、未改变 public API、未改变 schema ✅
- 中文 docstring 完整；无 `Any`/`object`/魔法数字 ✅

### dayu/config/execution_profiles.json

- `standard-256k` L23: `"max_compaction_attempts_per_operation": 5` ✅
- `standard-1m` L91: `"max_compaction_attempts_per_operation": 5` ✅
- `wechat-256k` L159: `"max_compaction_attempts_per_operation": 5` ✅
- `wechat-1m` L227: `"max_compaction_attempts_per_operation": 5` ✅
- 四个 profile 的 `compactor_baseline.model_id` 原本均为 `"deepseek-v4-flash"`，未修改 ✅
- 未新增 profile、未新增字段、未修改 schema ✅

### dayu/config/prompts/manifests/conversation_compaction.json

- L11: `"default_model_id": "deepseek-v4-flash"` ✅
- `"extends": []` 未被修改；其他 scene manifest 未引用 `conversation_compaction` 作为继承源 ✅
- 未修改 `agent_policy`、`tool_selection`、`fragments`、`context_slots` 等其他字段 ✅
- 只改了 compactor scene，未误改普通 scene 的 high-spec 默认模型 ✅

### tests/host/test_context_policy.py

- L23: `assert DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION == 5` ✅
- L24-L27: 保留原有断言 `policy.max_compaction_attempts_per_operation == DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` ✅
- L34-L51: 现有测试仍显式传递 `max_compaction_attempts_per_operation=2` 并验证校验逻辑——这是显式覆盖值测试，与默认值变更无关 ✅
- L82: `max_compaction_attempts_per_operation=3` 直接构造 `ContextBudgetPolicy`——显式测试值 ✅

### tests/runtime/test_config_loader.py

- L26: `_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5` ✅
- L303-L306: 新增 `standard_256k.context_budget_policy.max_compaction_attempts_per_operation == 5` 断言 ✅
- L324-L327: 新增全 profile 遍历断言，覆盖 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m` ✅
- 全 profile 遍历断言位于既有循环内，不引入额外测试函数；循环内已有 `continuation_prompt` 与 `max_consecutive_failed_tool_batches` 断言，新增断言风格一致 ✅

### tests/runtime/test_scene_assets_migration.py

- L117-L128: 新增 `_load_package_execution_profiles()` helper，遵循既有 `_load_manifest` 风格 ✅
- L256-L278: 新增 `test_conversation_compaction_default_model_matches_default_profile_compactor()` ✅
  - 读取 `conversation_compaction.json` manifest → 取 `model.default_model_id` ✅
  - 读取 `execution_profiles.json` → 取 `default_execution_profile_id` → 取对应 profile 的 `compactor_baseline.model_id` ✅
  - 断言两者一致 ✅
  - 未断言非默认 profile 的 compactor baseline 一致性（符合 plan 范围：只要求默认 profile 对齐）✅
- 中文 docstring 完整，包含 `:returns:` 与 `:raises AssertionError:` ✅

### tests/service/test_host_assembly.py

- L74: `_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5` ✅
- L165-L169: 新增 assembled policy 断言 ✅
  - `context_budget_policy is not None` 前置守卫 ✅
  - `context_budget_policy.max_compaction_attempts_per_operation == 5` ✅
  - 测试使用 `execution_profile_id="standard-256k"`，验证 Service assembly 将 packaged profile 的 `max_compaction_attempts_per_operation: 5` 正确映射到 `OpenHostOptions.context_budget_policy` ✅

## Invariant Verification

| 不变量 | 状态 | 证据 |
|--------|------|------|
| Host fallback 默认 `max_compaction_attempts_per_operation == 5` | ✅ | `context_policy.py:22`；`test_context_policy.py:23` |
| 包内四个 execution profiles 均为 `max_compaction_attempts_per_operation == 5` | ✅ | `execution_profiles.json` 四处；`test_config_loader.py:324-327` 遍历断言 |
| Service assembly 使用默认 packaged profile 装配出的 Host policy 为 5 | ✅ | `host_assembly.py:467-469` 从 profile 映射；`test_host_assembly.py:167-169` |
| `conversation_compaction` scene default model 与默认 execution profile compactor model 一致 | ✅ | `conversation_compaction.json:11` == `execution_profiles.json:12`；`test_scene_assets_migration.py:278` |
| 未改变普通 scene 默认模型 | ✅ | 无其他 scene manifest 被修改 |
| 未新增 high-spec allow-list | ✅ | 无新增 allow-list 配置或逻辑 |
| 未新增 scene inheritance 防御测试 | ✅ | plan non-goal 明确不新增 |
| 未改变 config schema、public API 或 Service public request shape | ✅ | 无 schema/public API diff |
| `dayu.runtime` 不 import 上层模块 | ✅ | runtime test 文件只读取 typed view，不引入 Host/Service/Engine |
| 未引入旧兼容逻辑 | ✅ | 无兼容性 re-export/wrapper/facade |

## Stale Value Search

搜索全仓库 `compaction_attempts.*[23][^0-9]|[^0-9][23][^0-9].*compaction_attempt` 命中：

| 文件 | 行 | 值 | 分类 |
|------|------|-----|------|
| `tests/service/test_host_assembly.py` | 874 | `3` | workspace overlay fixture，测试不对此字段断言；值为覆写 fixture filler |
| `tests/host/test_dispatch_scheduler.py` | 3306, 3354 | `2` | 显式传参 `default_context_budget_policy(max_compaction_attempts_per_operation=2)`；显式测试值 |
| `tests/runtime/test_config_loader.py` | 130 | `2` | `_execution_profile_record()` 测试 fixture；用于覆盖/继承测试的构造值 |
| `tests/host/test_context_policy.py` | 39, 82 | `2`, `3` | 显式传参测试值；验证自定义 budget 的校验逻辑 |

结论：生产代码无旧值残留。全部命中均为测试 fixture 或显式测试传参，不受默认值变更影响。

## Validation Results

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q` | 74 passed in 0.35s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings

### F1 [Low] Workspace overlay fixture 使用 `max_compaction_attempts_per_operation: 3`

**文件**: `tests/service/test_host_assembly.py:874`

**证据**: `_write_execution_profile_overlay` helper 的 inline JSON 中 `max_compaction_attempts_per_operation: 3`，该值恰好等于旧 packaged profile 默认值。调用该 fixture 的测试（`test_truncation_manager_enabled_is_derived_from_execution_profile`、`test_explicit_1m_profile_with_256k_model_fails_fast`）不对此字段做断言。

**影响**: 无功能影响。但 fixture 值为旧默认值的巧合会使未来读者误以为该值有特殊语义。若将来新增 workspace override 测试需要验证此字段的覆盖行为，可能因 fixture 值与新 package default (5) 差距过小而不够显眼。

**建议**: 将 fixture 中 `max_compaction_attempts_per_operation` 改为一个明显不同于 package default 的值（如 `7`），或添加注释说明 "workspace override 值，与 package default 无关联"。非阻塞，仅提升可维护性。

## Tests Reviewed

| 测试 | 覆盖点 | 评估 |
|------|--------|------|
| `test_default_context_budget_policy_sets_compaction_attempt_budget` | 默认常量 == 5，policy 携带正确值 | ✅ 新增常量级断言作为 canary |
| `test_default_runtime_config_files_load_as_typed_views` (新增断言) | standard-256k 单独断言 + 全 profile 遍历断言 attempt budget == 5 | ✅ 覆盖所有 4 个 packaged profile |
| `test_conversation_compaction_default_model_matches_default_profile_compactor` | scene ↔ 默认 profile compactor model 一致性 | ✅ 新增，覆盖完整对齐路径 |
| `test_compose_open_host_options_uses_runtime_tuning_from_config` (新增断言) | Service assembly 后 Host policy 为 5 | ✅ cover Service→Host 映射链路 |

### 未覆盖但由后续 slice 覆盖

- 非默认 profile 的 compactor model 与 scene 一致性（非 Slice A 需求）
- Service assembly 使用非默认 profile 时的 attempt budget（非 Slice A 需求；assembled policy 始终从 profile 读取，若 profile 值不对则 config loader 测试会捕获）
- `context_budget_policy_from_threshold_tokens` 默认值路径（使用同一常量，对齐自动成立）

## Hard Constraint Verification

| 约束 | 状态 | 证据 |
|------|------|------|
| 不改 schema / public API / Service request shape | ✅ | 无 schema/public API diff |
| 不新增 config schema 字段 | ✅ | 只改已有字段值 |
| 不出现 `Any`/`object`/无类型签名 | ✅ | pyright 0 errors |
| 中文 docstring 完整 | ✅ | 新增函数 `_load_package_execution_profiles` 有完整 docstring |
| 无魔法数字 | ✅ | `_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5` 是命名常量 |
| 不反向依赖 | ✅ | runtime test 只读 typed view，不 import Host/Service/Engine |
| 不做兼容逻辑 | ✅ | 无 re-export/wrapper/facade |
| `dayu.runtime` 不依赖上层 | ✅ | `test_config_loader.py` 与 `test_scene_assets_migration.py` 都只在 runtime 层 |

## Docs Decision

按 AGENTS.md 触发规则检查：

- **`dayu/config/README.md`**: 修改了 `dayu/config/` 下的 execution_profiles.json 与 conversation_compaction.json。README §execution_profiles 只描述 profile 结构与字段语义，未写死具体 `max_compaction_attempts_per_operation` 值或 `conversation_compaction` 默认模型 ID。无需更新。
- **`tests/README.md`**: 修改了 `tests/` 下测试文件。README 的测试分层描述是功能性的（"config loader: 覆盖...typed view 加载"），不列举具体测试函数或断言值。未新增测试层级、运行方式或维护规则。无需更新。
- 其他 README: 不触发（`dayu/host/README.md` 需等 Slice B-E 涉及 fallback/dispatch 实质变更后再检查）。

结论：当前无需 README 更新。与 implementation artifact 决策一致。

## Residual Risks

| 风险 | 归属 | 说明 |
|------|------|------|
| 非默认 profile 的 compactor model 与 scene 默认 model 可能未来分歧 | Slice B-E 或后续 WU | 当前四个 profile 的 compactor model 一致为 `deepseek-v4-flash`；若后续 profile 差异化 compactor model，需补跨 profile 一致性测试 |
| `context_budget_policy_from_threshold_tokens` 无独立默认值路径测试 | 非当前 WU | 该函数使用同一模块常量作为默认值，对齐自动成立；但无测试直接构造该函数并断言默认 attempt budget |
| 连续 overflow / compact failure E2E 覆盖 | Slice B-E | 由 approved plan 后续 slices 覆盖，Slice A 不提前实现 |

## Conclusion

**Pass** — 无 blocking finding。

Slice A 改动精确、范围最小、对齐完整。三端（Host fallback 默认、packaged execution profiles、Service assembled policy）的 `max_compaction_attempts_per_operation` 已全部对齐为 5。`conversation_compaction` scene default model 已从 high-spec 改为 flash-tier，与默认 execution profile compactor baseline 一致。未越界修改普通 scene、schema、public API 或 Service request shape。测试覆盖了 package defaults、全 profile 遍历、Service assembly 映射和 scene/profile 一致性。pyright 零错误。

1 个 low-severity finding (F1)，建议非阻塞改进 workspace overlay fixture 值。无 blocking questions for controller。

**Findings count**: 1 (F1, Low)

**Blocking questions**: 无
