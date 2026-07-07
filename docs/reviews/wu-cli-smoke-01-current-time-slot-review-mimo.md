# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-current-time-slot-review-mimo.md
- Included scope: current_time context slot 对齐修正相关改动
- Excluded scope: 无关的功能改动
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 验证详情

#### 1. 所有非 compact scene manifest 声明 required current_time，scene md 渲染 {{current_time}}，prompt/interactive/wechat 通过 utils tag 暴露 get_current_time

**manifest 检查结果：**
- `audit.json`: context_slots 包含 `current_time` (required: true) ✅
- `confirm.json`: context_slots 包含 `current_time` (required: true) ✅
- `decision.json`: context_slots 包含 `current_time` (required: true) ✅
- `fix.json`: context_slots 包含 `current_time` (required: true) ✅
- `infer.json`: context_slots 包含 `current_time` (required: true) ✅
- `interactive.json`: context_slots 包含 `current_time` (required: true) ✅
- `overview.json`: context_slots 包含 `current_time` (required: true) ✅
- `prompt.json`: context_slots 包含 `current_time` (required: true) ✅
- `regenerate.json`: context_slots 包含 `current_time` (required: true) ✅
- `repair.json`: context_slots 包含 `current_time` (required: true) ✅
- `smoke_host_public_conversation_memory.json`: context_slots 包含 `current_time` (required: true) ✅
- `smoke_host_public_conversation_memory_scenarios.json`: context_slots 包含 `current_time` (required: true) ✅
- `smoke_host_public_multiturn.json`: context_slots 包含 `current_time` (required: true) ✅
- `wechat.json`: context_slots 包含 `current_time` (required: true) ✅
- `write.json`: context_slots 包含 `current_time` (required: true) ✅
- `conversation_compaction.json`: context_slots 为空 ✅ (compact scene 不应有 current_time)

**scene md 检查结果：**
- `audit.md`: 包含 `{{current_time}}` (line 18) ✅
- `confirm.md`: 包含 `{{current_time}}` (line 18) ✅
- `decision.md`: 包含 `{{current_time}}` (line 28) ✅
- `fix.md`: 包含 `{{current_time}}` (line 21) ✅
- `infer.md`: 包含 `{{current_time}}` (line 23) ✅
- `interactive.md`: 包含 `{{current_time}}` (line 8) ✅
- `overview.md`: 包含 `{{current_time}}` (line 21) ✅
- `prompt.md`: 包含 `{{current_time}}` (line 8) ✅
- `regenerate.md`: 包含 `{{current_time}}` (line 22) ✅
- `repair.md`: 包含 `{{current_time}}` (line 18) ✅
- `smoke_host_public_conversation_memory.md`: 包含 `{{current_time}}` (line 9) ✅
- `smoke_host_public_conversation_memory_scenarios.md`: 包含 `{{current_time}}` (line 10) ✅
- `smoke_host_public_multiturn.md`: 包含 `{{current_time}}` (line 8) ✅
- `wechat.md`: 包含 `{{current_time}}` (line 8) ✅
- `write.md`: 包含 `{{current_time}}` (line 22) ✅
- `conversation_compaction.md`: 不包含 `{{current_time}}` ✅
- `conversation_compaction_user.md`: 不包含 `{{current_time}}` ✅

**utils tag 暴露检查：**
- `prompt.json`: tool_tags_any 包含 `"utils"` ✅
- `interactive.json`: tool_tags_any 包含 `"utils"` ✅
- `wechat.json`: tool_tags_any 包含 `"utils"` ✅
- 其他 scene: tool_tags_any 不包含 `"utils"` ✅

**直接证据：**
- `tests/runtime/test_scene_assets_migration.py:377-409`: `test_current_time_slot_is_rendered_by_non_compact_scenes` 验证所有非 compact scene 声明并渲染 current_time
- `tests/runtime/test_scene_assets_migration.py:624-648`: `test_get_current_time_tool_is_selected_only_for_interactive_prompt_scenes` 验证只有 prompt/interactive/wechat 暴露 get_current_time 工具

#### 2. 非 prompt/interactive/wechat scene 没有因 tag selection 暴露 get_current_time

**检查结果：**
- audit, confirm, decision, fix, infer, overview, regenerate, repair, write, smoke_* 的 tool_tags_any 不包含 `"utils"`
- 只有 prompt, interactive, wechat 的 tool_tags_any 包含 `"utils"`

**直接证据：**
- `tests/runtime/test_scene_assets_migration.py:624-648`: 测试验证非 prompt/interactive/wechat scene 不暴露 get_current_time

#### 3. current_time 的放置在 scene contract 后，且和 fins_default_subject 同时存在时顺序为 current_time 后 fins_default_subject

**检查结果：**
- 所有 scene md 中，`{{current_time}}` 都在 `{{fins_default_subject}}` 之前
- 顺序：scene contract -> current_time -> fins_default_subject

**直接证据：**
- `tests/runtime/test_scene_assets_migration.py:455-499`: `test_prepared_current_time_does_not_interrupt_scene_contract` 验证 current_time 不插入到执行契约正文之前，且在 fins_default_subject 之前

#### 4. 所有调用 ScenePrepare 或构造 packaged scenes 的代码和测试都提供 current_time

**检查结果：**
- `dayu/cli/commands/interactive.py:102-107`: `_interactive_context_slot_values()` 返回 `{CURRENT_TIME_SLOT: current_time()}`
- `utils/smoke_host_public_conversation_memory.py:552`: `context_slot_values={CURRENT_TIME_SLOT: current_time()}`
- `utils/smoke_host_public_multiturn.py`: 包含 current_time
- `utils/smoke_host_public_conversation_memory_scenarios.py`: 包含 current_time
- 测试中都有 current_time

**直接证据：**
- `dayu/cli/commands/interactive.py:102-107`: `_interactive_context_slot_values()` 实现
- `tests/runtime/test_scene_prepare.py`: 测试中使用 current_time

#### 5. conversation memory smoke utilities 保留 fins_awaiting_runtime 的修正必要、正确、没有扩散架构风险

**检查结果：**
- `utils/smoke_host_public_conversation_memory.py:636`: `fins_awaiting_runtime=discovered.fins_awaiting_runtime`
- 修正必要：Host assembly 需要同一个 shared runtime
- 修正正确：对齐已正确处理的 `utils/smoke_host_public_multiturn.py`
- 无扩散架构风险：仅在 smoke utility 中使用

**直接证据：**
- `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md:80-89`: Codex artifact 记录了 fins_awaiting_runtime 修正的根因和验证

#### 6. README 变更符合 AGENTS.md 触发规则

**检查结果：**
- `dayu/config/README.md`: 更新了 utils-tools provider 和 current_time slot 说明 ✅
  - 触发规则：`dayu/config/` 修改 -> 检查并按需更新 `dayu/config/README.md`
- `tests/README.md`: 更新了测试覆盖说明 ✅
  - 触发规则：`tests/` 修改 -> 检查并按需更新 `tests/README.md`
- `README.md`: 更新了 CLI 参数说明 ✅
  - 触发规则：用户可见 CLI 命令参数变化 -> 检查并按需更新根目录 `README.md`

#### 7. 测试覆盖和 pyright 证据足够

**检查结果：**
- pyright: 0 errors, 0 warnings, 0 informations ✅
- git diff --check: 通过，无输出 ✅
- pytest affected suites: 已通过 ✅
  - `tests/runtime/test_scene_assets_migration.py`: 63 passed
  - `tests/runtime/test_scene_prepare.py`: 包含 current_time 测试
  - `tests/service/test_entrypoint_runtime.py`: 包含 scene_context 测试
  - `tests/cli/test_prompt_command.py`: 包含 current_time 测试
  - `tests/cli/test_interactive_command.py`: 包含 current_time 测试

## Open Questions

无。

## Residual Risk

1. **后续新增 scene 时需要同步修改**：如果新增非 compact scene，需要同时：
   - 在 manifest 中声明 required `current_time` context slot
   - 在 scene md 中渲染 `{{current_time}}`
   - 在所有 ScenePrepare 调用方补值
   - 这是已知风险，在 `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md:94` 中已记录

2. **interactive/wechat scene 没有 fins_default_subject**：这是设计意图，因为 interactive 和 wechat 是多轮对话场景，不需要预设财报主体。但需要确保后续不会意外引入。

## Conclusion

**Pass** - 未发现实质性问题。

当前改动正确实现了 current_time context slot 对齐修正：
1. 所有非 compact scene 都通过 context slot 获得当前时间
2. 只有 prompt/interactive/wechat 通过 utils tag 暴露 get_current_time 工具
3. current_time 放置在 scene contract 后，且在 fins_default_subject 之前
4. 所有 ScenePrepare 调用方都提供 current_time
5. smoke utility 的 fins_awaiting_runtime 修正正确
6. README 变更符合触发规则
7. 测试覆盖充分，pyright 验证通过
