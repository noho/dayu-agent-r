# Code Review — current_time Context Slot 对齐修正

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-slot-review-ds.md`
- Included scope:
  - `dayu/config/prompts/manifests/*.json` — 所有 packaged scene manifest 的 `context_slots` 与 `tool_selection` 变更
  - `dayu/config/prompts/scenes/*.md` — 所有 scene prompt fragment 的 `{{current_time}}` 渲染
  - `dayu/config/prompts/base/tools.md` — `get_current_time` 条件块
  - `dayu/cli/commands/interactive.py` — interactive CLI 入口 `current_time` slot 注入
  - `dayu/cli/commands/prompt.py` — prompt CLI 入口 context slot 构造迁移到 `build_entrypoint_context_slot_values`
  - `dayu/service/scene_context.py` — entrypoint context slot 文本生成模块
  - `dayu/service/entrypoint_runtime.py` — `EntrypointRuntimeRequest.context_slot_values` typed 接受 `JsonValue` 映射
  - `dayu/runtime/scene_prepare.py` — context slot 渲染、条件块过滤
  - `dayu/tools/utils/provider.py` — `get_current_time` 工具定义（`utils` + `time` tags）
  - `tests/runtime/test_scene_assets_migration.py` — `current_time` source placement / 渲染顺序 / 工具暴露 invariant
  - `tests/runtime/test_scene_prepare.py` — 条件块与工具选择测试
  - `tests/service/test_entrypoint_runtime.py` — scene context helper / thinking 投影测试
  - `tests/service/test_entrypoint_runtime_interactive_path.py` — interactive runtime 真实 manifest 装配测试
  - `tests/cli/test_interactive_command.py` — interactive CLI 行为测试
  - `tests/cli/test_prompt_command.py` — prompt CLI 行为测试
  - `tests/service/test_host_assembly.py` — Host assembly 测试夹具
  - `utils/smoke_host_public_conversation_memory.py` — smoke 装配 `current_time` 与 `fins_awaiting_runtime` 补正
  - `utils/smoke_host_public_conversation_memory_scenarios.py` — 同上
  - `utils/smoke_host_public_multiturn.py` — `base_user` 清理
  - `dayu/config/README.md` — `current_time` slot 文档
  - `tests/README.md` — 测试覆盖事实更新
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md` — Codex 自述 artifact
- Excluded scope:
  - `dayu/fins/`, `dayu/host/`, `dayu/engine/` 的其它改动（FMP resolver、Host API、Engine ingest 等），这些属于 `WU-CLI-SMOKE-01` 的其它 slice，不在本次 `current_time` 对齐 scope 内
  - `docs/reviews/` 下的其它历史 review artifact
- Parallel review coverage: 无，单 reviewer 全量走读

## Findings

### F01-未修复-中-stale test context_slot_values 与 interactive manifest 新增 required current_time 不一致

- **入口/函数**: `_prepare_interactive_runtime` (helper) / `test_interactive_label_reuses_host_slot_and_fills_context_slots` (test) / `test_interactive_runtime_uses_real_manifest_required_slots` (test)
- **文件(行号)**:
  - `tests/cli/test_interactive_command.py:1809` — helper 传递 `context_slot_values={}`
  - `tests/cli/test_interactive_command.py:700` — 断言 `context_slot_values == {}`
  - `tests/service/test_entrypoint_runtime_interactive_path.py:327` — helper 传递 `context_slot_values={}`
- **输入场景**: interactive manifest 新增 required `current_time` context slot 后，任何传入 `context_slot_values={}` 的 `ScenePrepare` 调用都会因缺 required slot 抛出 `ScenePrepareError`
- **实际分支**: `dayu/runtime/scene_prepare.py:1050-1051` — `_render_fragment_content` 遍历 `context_slots`，`slot.required and slot.name not in context_slot_values` 命中，抛出 `ScenePrepareError("required context slot missing: current_time")`
- **预期行为**: 测试夹具应提供 `{CURRENT_TIME_SLOT: "..."} ` 使 `ScenePrepare` 正常完成装配
- **实际行为**: 已 committed 的测试代码传入 `context_slot_values={}`，会导致 `prepared_entrypoint_runtime` 调用在 `ScenePrepare` 阶段失败
- **直接证据**:
  - `dayu/config/prompts/manifests/interactive.json:64-69` — 声明 `{"name": "current_time", "value_type": "string", "required": true}`
  - `dayu/runtime/scene_prepare.py:1049-1051` — required slot 缺值时抛出 `ScenePrepareError`
  - committed `tests/cli/test_interactive_command.py:1809` — `context_slot_values={}`
  - committed `tests/service/test_entrypoint_runtime_interactive_path.py:327` — `context_slot_values={}`
- **影响**: committed 状态下 `tests/cli/test_interactive_command.py` 和 `tests/service/test_entrypoint_runtime_interactive_path.py` 中所有通过 `_prepare_interactive_runtime` 走的测试均会因 `ScenePrepareError` 失败，而非测试业务逻辑
- **建议改法和验证点**: 工作区中 UNSTAGED 的修改 (`tests/cli/test_interactive_command.py:1809` 改为 `{_CURRENT_TIME_SLOT: _CURRENT_TIME_TEXT}`，`tests/cli/test_interactive_command.py:700-701` 改为验证 `current_time` slot key 与时区文本，`tests/service/test_entrypoint_runtime_interactive_path.py` 对应 helper 同理) 已正确修复此问题。需将这些 unstaged 修改 stage 并 commit
- **修复风险（低）**: 仅修改测试夹具文本值，不改变生产逻辑
- **严重程度（中）**: 测试夹具与 manifest 契约不一致，导致相关测试在 committed 状态下不可运行

### F02-未修复-低-prompt scene manifest 缺少 fins-download 和 fins-preprocess tag 选择但 prompt.md 中不含相应工具指引条件块

- **入口/函数**: `ScenePrepare.prepare` → `_select_tools` → `_filter_condition_blocks`
- **文件(行号)**:
  - `dayu/config/prompts/manifests/prompt.json:20-22` — `tool_tags_any: ["fins-read", "web", "utils"]`
  - `dayu/config/prompts/base/tools.md:67-81` — `<when_tool start_fins_download>` 与 `<when_tool start_fins_preprocess>` 条件块
- **输入场景**: prompt scene 装配时，`tool_tags_any` 不含 `fins-download` 和 `fins-preprocess`
- **实际分支**: `_select_tools` 不通过 tag 匹配到 `start_fins_download` / `start_fins_preprocess`；`_filter_condition_blocks` 因 `selected_tool_names` 不含这两个工具名，正确剔除对应条件块
- **预期行为**: prompt scene 不应暴露财报下载/预处理长事务工具，这是合理的设计选择（prompt 是单轮问答场景，不应在 LLM 推理中触发长事务）
- **实际行为**: 工具不会被选中，条件块被正确过滤；行为正确，但属于"依赖条件块过滤而非 manifest tag 声明"来实现排除
- **直接证据**:
  - `dayu/config/prompts/manifests/prompt.json:20-22` — 无 `fins-download` / `fins-preprocess` tags
  - `dayu/config/prompts/manifests/interactive.json:20-22` — 有 `fins-download` / `fins-preprocess`（对照）
  - `tests/runtime/test_scene_assets_migration.py:570-598` — `test_prompt_prepared_output_filters_long_transaction_guidance` 验证条件块被过滤
- **影响**: 无运行时错误。此处标记为低严重度，是因为 prompt 不暴露下载/预处理工具是 design intent 的一环，但 manifest 注释和文档未显式说明 prompt scene 为何有意排除这两个 tag
- **建议改法和验证点**: 非 bug，无需修代码。可在 `dayu/config/README.md` 的 scene manifest 工具选择说明中补充一句"prompt scene 是单轮问答场景，不暴露长事务（download/preprocess/upload）工具"
- **修复风险（低）**: 仅文档补充
- **严重程度（低）**: 设计意图未显式文档化，但不影响运行时正确性

### F03-未修复-低-smoke conversation memory manifest 不声明 fins_default_subject 但 scene md 也不渲染 {{fins_default_subject}}，对齐正确但缺少显式测试覆盖

- **入口/函数**: `test_current_time_slot_is_rendered_by_non_compact_scenes` / scene manifest
- **文件(行号)**:
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` — `context_slots: [current_time]` 无 `fins_default_subject`
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json` — 同上
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md` — 只有 `{{current_time}}`，无 `{{fins_default_subject}}`
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md` — 同上
- **输入场景**: conversation memory smoke scenes 是仅用于测试的内部场景，不需要 `fins_default_subject`
- **实际分支**: manifest 不声明 `fins_default_subject` slot，scene md 不渲染 placeholder，`ScenePrepare` 不会因缺 slot 报错
- **预期行为**: 行为正确 — smoke scene 只消费 `current_time`，不消费 `fins_default_subject`
- **实际行为**: 行为正确
- **直接证据**: 上述 manifest 文件与 scene md 文件
- **影响**: 无运行时错误。标记为低严重度是因为 `test_current_time_slot_is_rendered_by_non_compact_scenes` 测试通过 `_required_context_slot_values(manifest)` 自动为需要 `fins_default_subject` 的 manifest 补值，conversation memory manifest 不声明 `fins_default_subject`，因此测试路径正确跳过了 subject slot 检查
- **建议改法和验证点**: 可选：在 `test_scene_assets_migration.py` 中新增一个显式断言，验证 conversation memory smoke manifest 不声明 `fins_default_subject`，以防止未来误加
- **修复风险（低）**: 仅测试补充
- **严重程度（低）**: 当前行为正确，但缺少回归防护

## Open Questions

1. **compaction scene 的 `conversation_compaction_user.md`**: 当前 `test_current_time_slot_is_rendered_by_non_compact_scenes` 显式检查了 `conversation_compaction_user.md` 不含 `{{current_time}}`，但该文件不是 scene fragment（它是 user prompt template，由 execution profile 的 `compactor_baseline.user_prompt_template_path` 引用）。`ScenePrepare` 不会加载此文件，因此该检查属于防御性验证而非契约验证。当前实现正确，无风险。

2. **`prompt.json` 不声明 `fins_default_subject` 为 optional 时的含义**: 当前 `prompt.json` 将 `fins_default_subject` 声明为 `required: true`，但 `build_entrypoint_context_slot_values` 在没有 ticker 时返回空字符串 `""`。这意味着即使没有 ticker，slot 也会被填充（只是内容为空），因此 `ScenePrepare` 不会因缺 slot 报错。这是有意设计——空字符串是合法的 slot 值，LLM 收到的上下文行只是空行。此行为已在 `test_scene_context_formats_subject_and_current_time` 中测试。无风险。

## Residual Risk

- **R1 — unstaged test fixes 未 commit**: `tests/cli/test_interactive_command.py` 和 `tests/service/test_entrypoint_runtime_interactive_path.py` 的 unstaged 修改是 committed 测试能通过的必要条件。当前 committed 状态下这些测试会因缺 `current_time` slot 值而失败。**必须 stage 并 commit 这些修改**。

- **R2 — 真实 provider CLI smoke 未覆盖**: Codex artifact 明确标注"未跑真实 provider CLI smoke；本次是 scene slot contract 与 packaged prepare/CLI/service 测试修正"。当前时间工具 (`get_current_time`) 和 context slot (`{{current_time}}`) 的端到端交互（同一 turn 内 LLM 先看到 slot 文本、再调用 `get_current_time` 工具的行为）未在自动化测试中覆盖。建议在真实环境 smoke 中增加一条验证：prompt scene 下 LLM 能同时消费 `{{current_time}}` 文本和调用 `get_current_time` 工具，且不产生矛盾。

- **R3 — 后续新增 scene 的 required current_time 约束**: `current_time` 现在是除 compact 外所有 scene 的 required slot。后续新增非 compact scene 时必须同步：① manifest 声明 required `current_time`、② scene md 在契约正文后渲染 `{{current_time}}`、③ 所有 ScenePrepare 调用方提供 `current_time` 值。这是 process risk，当前代码中已通过 `test_current_time_slot_is_rendered_by_non_compact_scenes` 提供了自动化回归检测（遍历所有 manifest 并断言），降低了此风险。

- **R4 — `current_time` 文本格式为 LLM-facing 中文 Markdown，不是机器可解析格式**: `dayu/service/scene_context.py:79-95` 的 `current_time()` 函数生成的是人类可读的中文时间文本（如 `# 当前时间\n现在是 2026年7月7日 23:08（Asia/Shanghai，星期二）。`）。LLM 可通过此文本理解当前时间，但如果后续需要程序化时间比较或时间戳运算，此格式不适用。当前设计已通过 `get_current_time` 工具提供结构化时间输出（含 `iso` 字段），因此 context slot 文本仅用于 LLM 初始时间感知，此分配合合理。无当前风险。

## Conclusion

**Pass** — 无阻断性问题。

`current_time` context slot 对齐修正的实现与设计意图一致：

- 除 `conversation_compaction` 外，所有 packaged scene manifest 均声明 required `current_time`，对应 scene md 均在执行契约正文之后渲染 `{{current_time}}`
- `prompt`、`interactive`、`wechat` 三个 scene 通过 `"utils"` tag 继续暴露 `get_current_time` 工具；其它 scene 仅通过 context slot 获得当前时间，不暴露工具
- `current_time` 和 `fins_default_subject` 同时存在时，`current_time` 在前、`fins_default_subject` 在后，不打断 scene 执行契约
- 所有 ScenePrepare 调用方（CLI prompt/interactive、smoke utilities）均提供 `current_time` 值
- `base_user` 已从所有源码中清除
- conversation memory smoke utilities 的 `fins_awaiting_runtime` 补正正确，与 `smoke_host_public_multiturn.py` 对齐
- README 变更符合 CLAUDE.md 触发规则
- pyright 0 errors，`git diff --check` 通过

**当前未 commit 的工作区修改（F01）必须 stage 并 commit**，以修复测试夹具与 manifest 契约的不一致。
