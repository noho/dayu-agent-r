# Code Review — current_time Context Slot F02/F03 闭环复查

## Scope

- Mode: current changes (re-review of Codex F02/F03 fix closure)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-ds.md`
- Included scope:
  - `dayu/config/README.md` — F02 文档边界说明（unstaged 补充）
  - `tests/runtime/test_scene_assets_migration.py` — F03 显式断言新建 + current_time tool/slot invariant 测试（unstaged 补充）
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` — context_slots 声明
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json` — context_slots 声明
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md` — placeholder 渲染
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md` — placeholder 渲染
  - 所有 scene manifest 的 `context_slots` 与 `tool_tags_any`（作为 invariant 验证基线）
- Excluded scope:
  - F01（stale test context_slot_values）已在上一轮 DS review 中确认，本次不重复审查
  - `dayu/fins/`、`dayu/host/`、`dayu/engine/` 的其它改动
  - `docs/reviews/` 下的历史 review artifact
- Parallel review coverage: 无，单 reviewer 全量走读
- Previous review artifacts:
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-review-ds.md` — 上一轮 DS review（F01/F02/F03）
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-review-mimo.md` — 上一轮 MiMo review
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md` — Codex fix artifact

## User Intent 基线

1. `prompt` / `interactive` / `wechat` 同时使用 `get_current_time` 工具和 `{{current_time}}` context slot
2. 除 `conversation_compaction` 外，其它所有 scene 都使用 `{{current_time}}`
3. 只有 `prompt` / `interactive` / `wechat` 暴露 `get_current_time` 工具

## Findings

### 复查结论：F02 闭环 — Pass

- **检查项**: `dayu/config/README.md` 是否清楚说明 prompt 是单轮问答 scene，不暴露 download / preprocess / upload 长事务工具，interactive / wechat 才用于对话中触发长事务。
- **直接证据**:
  - `dayu/config/README.md:216`（unstaged）: `prompt 是单轮问答 scene，不暴露 download / preprocess / upload 这类长事务工具；需要模型在对话中触发 download / preprocess 时，使用 interactive 或 wechat scene。`
  - `dayu/config/README.md:218`（unstaged）: `只有 prompt、interactive 与 wechat manifest 通过 "utils" tag 选择 get_current_time 工具，使模型在需要实时刷新时间时可以主动调用工具；其它 scene 即使需要当前时间，也只消费 current_time context slot，不通过 "utils" tag 暴露该工具。`
  - `dayu/config/README.md:214`（unstaged）: 说明了 `current_time` 是 LLM-facing 文本，不等同于工具暴露。
- **判定**: 文档边界完整、清晰、可执行。F02 闭环。

### 复查结论：F03 闭环 — Pass

- **检查项**: `tests/runtime/test_scene_assets_migration.py` 是否有显式断言，conversation memory smoke manifest 不声明 `fins_default_subject`，scene md 不渲染 `{{fins_default_subject}}`。
- **直接证据**:
  - `tests/runtime/test_scene_assets_migration.py:383-391`（unstaged）: `test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot` 显式断言：
    ```python
    assert not _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT), scene
    assert _FINS_DEFAULT_SUBJECT_PLACEHOLDER not in scene_content, scene
    ```
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json`: `context_slots: [{"name": "current_time", "value_type": "string", "required": true}]` — 无 `fins_default_subject`
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`: 同上
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md`: 仅 `{{current_time}}`（line 9），无 `{{fins_default_subject}}`
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`: 仅 `{{current_time}}`（line 10），无 `{{fins_default_subject}}`
  - 常量 `_CONVERSATION_MEMORY_SMOKE_SCENES`（`tests/runtime/test_scene_assets_migration.py:78-83`）精确枚举两个 smoke scene。
- **判定**: F03 闭环。显式断言存在，与 manifest/scene 文件事实一致，形成有效回归防护。

### F04-未修复-低-`_first_contract_content_line_index` 未跳过 `{{current_time}}` 占位符

- **入口/函数**: `_first_contract_content_line_index`
- **文件(行号)**: `tests/runtime/test_scene_assets_migration.py:256-273`
- **输入场景**: 若未来 scene 在 H1 标题后、执行契约正文前放置 `{{current_time}}`（违反当前设计意图但语法合法），该函数会把 `{{current_time}}` 行当作首个执行契约正文行返回。
- **实际分支**: 函数在 `for` 循环中跳过空行（`continue`）、`#` 开头的标题行（`continue`）、`{{fins_default_subject}}`（`continue`），但遇到 `{{current_time}}` 时不命中任何 `continue`，在第 272 行 `return index` 直接返回。
- **预期行为**: 函数应跳过所有 context slot placeholder，包括 `{{current_time}}`，使返回值为真正的执行契约正文首行。
- **实际行为**: 当前所有 scene 的 `{{current_time}}` 都在执行契约正文之后，因此函数当前行为正确，未触发错误。但语义不完整——当 `_placeholder_line_indexes` 已在 line 241 被重构为接受参数化 placeholder 时，`_first_contract_content_line_index` 未同步更新以跳过新增的 `_CURRENT_TIME_PLACEHOLDER`。
- **直接证据**:
  - `tests/runtime/test_scene_assets_migration.py:270`: 只跳过 `_FINS_DEFAULT_SUBJECT_PLACEHOLDER`，不跳过 `_CURRENT_TIME_PLACEHOLDER`
  - `tests/runtime/test_scene_assets_migration.py:241-253`: `_placeholder_line_indexes` 已参数化，但同类函数 `_first_contract_content_line_index` 未同步
- **影响**: 当前无运行时错误，无测试失败。风险为 latent fragility：若后续 scene 的 `{{current_time}}` 被意外放在 contract 正文之前，该函数会返回错误行号，导致 placement assertion 的语义偏差（`test_current_time_slot_is_rendered_by_non_compact_scenes:417` 的 `current_index > _first_contract_content_line_index(lines)` 会在该场景下变成 `index > index` → False，测试正确失败但根因混淆）。
- **建议改法和验证点**: 在 `_first_contract_content_line_index` 的跳过条件中增加 `if stripped == _CURRENT_TIME_PLACEHOLDER: continue`，与 `_FINS_DEFAULT_SUBJECT_PLACEHOLDER` 对称。同时更新函数 docstring 中"非默认主体占位符"为"非 context slot 占位符"。
- **修复风险（低）**: 仅增加一个 `continue` 条件，不改动任何测试断言或生产逻辑。
- **严重程度（低）**: 当前行为正确，仅防御性编程不足；不影响任何现有测试通过。

## User Intent 整体验证

### 1. 所有非 compact scene 声明 required current_time，scene md 渲染 {{current_time}}

- 16 个 packaged manifest 中，15 个声明 required `current_time` context slot（`conversation_compaction` 除外，其 `context_slots: []`）
- 对应 15 个 scene md 均在执行契约正文之后渲染 `{{current_time}}`
- 验证测试: `test_current_time_slot_is_rendered_by_non_compact_scenes`（line 394）遍历所有 manifest 并逐条断言
- **结论: ✅ 满足**

### 2. 只有 prompt / interactive / wechat 暴露 get_current_time 工具

- `prompt.json`: `tool_tags_any: ["fins-read", "web", "utils"]`
- `interactive.json`: `tool_tags_any: ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
- `wechat.json`: `tool_tags_any: ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
- 其他 13 个 manifest 的 `tool_tags_any` 不含 `"utils"`（包括 3 个 mode=none 的 scene）
- `get_current_time` 工具注册 tags: `{"utils", "time"}`
- 验证测试: `test_get_current_time_tool_is_selected_only_for_interactive_prompt_scenes`（line 641）遍历所有 manifest 并通过 `ScenePrepare` 真实装配验证
- **结论: ✅ 满足**

### 3. current_time 放置在 scene contract 后，且和 fins_default_subject 同时存在时 current_time 在前

- 所有 scene md 中 `{{current_time}}` 均在执行契约正文之后
- 同时有 `{{fins_default_subject}}` 的 scene（如 prompt），顺序为 `{{current_time}}` → `{{fins_default_subject}}`
- 验证测试: `test_prepared_current_time_does_not_interrupt_scene_contract`（line 472）通过真实 `ScenePrepare` 装配后验证 system_prompt 中块顺序
- **结论: ✅ 满足**

### 4. 新增测试与已有 helper/类型约束一致

- `_placeholder_line_indexes` 重构为接受 `placeholder` 参数，向后兼容（所有原有调用点更新为传入 `_FINS_DEFAULT_SUBJECT_PLACEHOLDER`）
- `_required_context_slot_values` 不变，自动为所有 required slot 补测试值
- `_fake_tool_catalog` 注册 `get_current_time` with tags `{"utils", "time"}`，与生产 tool_discovery 对齐
- 新增常量 `_CURRENT_TIME_SLOT`、`_CURRENT_TIME_PLACEHOLDER`、`_CURRENT_TIME_TITLE`、`_CURRENT_TIME_MARKDOWN`、`_CONVERSATION_MEMORY_SMOKE_SCENES`、`_TIME_TOOL_SCENES` 均为 `Final` 类型，命名与已有常量风格一致
- 新增测试函数均使用已有 helper（`_iter_manifest_paths`、`_load_manifest`、`_manifest_declares_context_slot`、`_scene_fragment_path`、`_placeholder_line_indexes`、`_first_contract_content_line_index`、`_last_non_empty_line_index`、`_required_context_slot_values`、`_fake_tool_catalog`），无重复实现
- 无脆弱路径或过度耦合（F04 为防御性不足，非耦合问题）
- **结论: ✅ 一致**

### 5. 无新增阻断问题

- pyright: 0 errors, 0 warnings, 0 informations
- `git diff --check`: 通过
- `pytest tests/runtime/test_scene_assets_migration.py -q`: 17 passed
- F01（unstaged test fixture fix）仍需随本 slice commit，已在上一轮 DS review 明确
- **结论: ✅ 无新增阻断问题**

## Open Questions

无。

## Residual Risk

- **R1 — F01 依赖 unstaged 修复纳入 commit**: `tests/cli/test_interactive_command.py` 和 `tests/service/test_entrypoint_runtime_interactive_path.py` 的当前 committed 状态仍包含 `context_slot_values={}`（与 interactive manifest 的 required `current_time` 不一致）。这些修复在工作区中以 unstaged 形式存在，必须 stage 并纳入本 slice commit。
- **R2 — 真实 provider CLI smoke 未覆盖**: Codex artifact 已标注"未跑真实 provider CLI smoke"。`get_current_time` 工具与 `{{current_time}}` context slot 在同一 turn 内同时存在时 LLM 的行为未经过端到端验证。
- **R3 — 后续新增 scene 的 required current_time 约束**: 已在上一轮 DS review 中记录。当前 `test_current_time_slot_is_rendered_by_non_compact_scenes` 提供了自动化回归检测。

## Conclusion

**Pass** — F02 和 F03 均已闭环。无新增阻断问题。

- **F02**: `dayu/config/README.md` 清楚说明 `prompt` 是单轮问答 scene，不暴露长事务工具；`interactive`/`wechat` 才用于对话中触发长事务。
- **F03**: `test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot` 显式断言 conversation memory smoke manifest 不声明 `fins_default_subject`，scene md 不渲染 `{{fins_default_subject}}`。
- **F04**（低严重度）: `_first_contract_content_line_index` 未跳过 `{{current_time}}` 占位符，当前行为正确但防御性不足。
- 整体 user intent 满足：所有非 compact scene 有 `{{current_time}}`，只有 prompt/interactive/wechat 暴露 `get_current_time`，当前时间放置在 scene contract 后。
- 新增测试与已有 helper 一致，无脆弱耦合路径。
- F01 的 unstaged 测试夹具修复仍需随本 slice commit。
