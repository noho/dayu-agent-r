# WU-CTX-02 + WU-CTX-03 Slice A code review

## Gate / Slice

- Gate: WU-CTX-02 + WU-CTX-03 code review。
- Slice: A — 默认 policy / config / model 对齐。
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。
- Implementation artifact: `docs/reviews/wu-ctx-02-03-implementation-sliceA-codex-20260601.md`。
- Reviewer: MiMo。
- Review date: 2026-06-01。

## Diff 范围

7 个文件变更（3 个生产文件、4 个测试文件），无新增文件。

| 文件 | 变更类型 |
|---|---|
| `dayu/host/context_policy.py` | 常量 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` 2→5 |
| `dayu/config/execution_profiles.json` | 4 个 profile 的 `max_compaction_attempts_per_operation` 3→5 |
| `dayu/config/prompts/manifests/conversation_compaction.json` | `default_model_id` high-spec→`deepseek-v4-flash` |
| `tests/host/test_context_policy.py` | 新增常量值断言 |
| `tests/runtime/test_config_loader.py` | 新增 profile 级和遍历级 attempt budget 断言 |
| `tests/runtime/test_scene_assets_migration.py` | 新增 scene/profile compactor model 一致性测试 |
| `tests/service/test_host_assembly.py` | 新增 assembled policy attempt budget 断言 |

## Findings

### F-01: execution profiles 全量对齐 5 — PASS

**严重性**: info
**位置**: `dayu/config/execution_profiles.json` L23, L91, L159, L227

四个 packaged profile（standard-256k, standard-1m, wechat-256k, wechat-1m）的 `context_budget_policy.max_compaction_attempts_per_operation` 均从 3 改为 5。逐一核对，无遗漏、无误改。

### F-02: Host fallback 默认常量对齐 5 — PASS

**严重性**: info
**位置**: `dayu/host/context_policy.py` L22

`DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` 从 2 改为 5。Host fallback 默认值与 packaged profile 默认值现在一致，均等于 5。

### F-03: conversation_compaction scene default model 对齐 flash-tier — PASS

**严重性**: info
**位置**: `dayu/config/prompts/manifests/conversation_compaction.json` L11

`default_model_id` 从 `mimo-v2.5-pro-thinking-plan`（high-spec）改为 `deepseek-v4-flash`（flash-tier）。与四个 packaged profile 的 `compactor_baseline.model_id` 一致。`extends` 为空数组，无 scene inheritance 链需要防御。

### F-04: 未误改普通 scene 或引入 scene inheritance 防御 — PASS

**严重性**: info

diff 只触及 `conversation_compaction.json`，未修改其它 scene manifest。plan 的 non-goal 明确"不新增 scene inheritance 防御测试"，实现遵守。

### F-05: test_context_policy.py 常量断言 — PASS（附 note）

**严重性**: info
**位置**: `tests/host/test_context_policy.py` L23

新增 `assert DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION == 5` 断言，确保常量值不被意外回退。该断言使用字面量 5 而非从 config 派生的 cross-reference，这是合理的——测试目的就是锁定常量值本身。

### F-06: test_config_loader.py 双重覆盖 — PASS

**严重性**: info
**位置**: `tests/runtime/test_config_loader.py` L303-306, L324-327

两处断言：
1. 对 `standard-256k` 单独断言 `max_compaction_attempts_per_operation == 5`。
2. 遍历所有 profile 断言同一值。

`_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5` 消除了魔法数字。双重覆盖既验证了默认 profile 的具体值，又验证了全量一致性。

### F-07: test_scene_assets_migration.py scene/profile 一致性测试 — PASS

**严重性**: info
**位置**: `tests/runtime/test_scene_assets_migration.py` L256-278

新增 `test_conversation_compaction_default_model_matches_default_profile_compactor` 测试，从 packaged JSON 读取 `default_execution_profile_id`，定位默认 profile 的 `compactor_baseline.model_id`，断言 scene manifest 的 `default_model_id` 与其一致。测试直接读取包内配置文件，不依赖 typed view，覆盖了 raw JSON 一致性路径。

`_load_package_execution_profiles()` 辅助函数有完整中文 docstring，返回 `Mapping[str, JsonValue]`，类型正确。

### F-08: test_host_assembly.py assembled policy 断言 — PASS

**严重性**: info
**位置**: `tests/service/test_host_assembly.py` L165-170

在已有 `test_compose_open_host_options_uses_runtime_tuning_from_config` 测试中追加断言，验证 assembled `context_budget_policy.max_compaction_attempts_per_operation == 5`。`_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5` 消除魔法数字。

### F-09: 无 schema / public API / Service request shape 变更 — PASS

**严重性**: info

三处生产变更均为值替换：
- JSON 数值字段 3→5
- JSON 字符串字段模型名替换
- Python 模块级常量值 2→5

未新增/删除/重命名字段、未改变 `ContextBudgetPolicy` dataclass 结构、未改变 execution profile schema、未改变 `open_host(options)` 或 `SubmitFollowupRequest` 接口。

### F-10: 无类型 / docstring / Any / object / 架构分层问题 — PASS

**严重性**: info

所有变更文件：
- `context_policy.py`: 仅改常量值，签名和 docstring 不受影响。
- `execution_profiles.json`: 纯 JSON 值变更。
- `conversation_compaction.json`: 纯 JSON 值变更。
- 测试文件: 新增的辅助函数 `_load_package_execution_profiles()` 有完整中文 docstring，返回类型 `Mapping[str, JsonValue]`，无 `Any` 或 `object`。`Final[int]` 类型注解正确。

无魔法数字——测试中使用 `Final` 常量 `_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION`，生产代码中使用具名常量 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION`。

### F-11: README docs decision — PASS

**严重性**: info

implementation artifact 记录的 docs decision 为不更新 README。理由：
- `dayu/config/README.md`: 未硬编码旧 `max_compaction_attempts_per_operation` 值或旧 compactor 模型。
- `tests/README.md`: 本次是在既有测试层内增加一致性断言，未新增测试层级或运行方式。

此 decision 合理。AGENTS.md 触发规则要求"只更新 README 中与当前代码不一致的部分"，当前 README 无不一致。

### F-12: 测试验证 — PASS

**严重性**: info

```
74 passed in 0.35s
```

implementation artifact 记录的 pyright 结果为 0 errors, 0 warnings, 0 informations。已独立验证测试通过。

## Conclusion

**PASS — 无 blocker。**

Slice A 实现正确、完整地落地了 approved plan 第 7 节 Slice A 的全部要求：

1. Host fallback 默认 `max_compaction_attempts_per_operation` 对齐为 5。
2. 四个 packaged execution profiles 的同名字段对齐为 5。
3. `conversation_compaction` scene default model 对齐为 flash-tier（`deepseek-v4-flash`），与默认 profile compactor model 一致。
4. 四个测试文件新增/更新的断言覆盖了 package defaults、service assembly 和 scene/profile 一致性三条路径。
5. 未越界改 schema、public API、Service request shape 或 scene inheritance 语义。

## Residual Risks

| Risk | 说明 | 处理 |
|---|---|---|
| 后续 slices 依赖 | Slice B-E 的 payload 补足、fallback 实现和 E2E 测试尚未实现，当前常量对齐是前置条件。 | 由后续 slice 覆盖，非本 slice 风险。 |
| workspace config 覆盖 | 测试只验证包内默认配置，workspace 覆盖配置可能使用旧值 3 或 2。 | 运行时 ConfigLoader 合并逻辑已由 runtime 测试覆盖；workspace 覆盖是用户主动行为，不在包内默认一致性范围内。 |

## Test Gaps

Slice A 范围内无未覆盖的测试缺口。所有 plan 要求的断言均已实现：

- [x] 常量值断言（test_context_policy.py）
- [x] 默认 profile 具体值断言（test_config_loader.py）
- [x] 全量 profile 一致性遍历断言（test_config_loader.py）
- [x] scene/profile compactor model 一致性断言（test_scene_assets_migration.py）
- [x] assembled policy 断言（test_host_assembly.py）

## Artifact 路径

`docs/reviews/wu-ctx-02-03-code-review-sliceA-mimo-20260601.md`
