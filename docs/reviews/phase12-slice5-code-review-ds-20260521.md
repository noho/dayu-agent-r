# Phase 12 Slice 5 Code Review — AgentDS

## Verdict: BLOCKED

Blocking finding count: 0. 原因见 F1（高优先级，需回应用户 handoff 意图）与 F2（中优先级，需确认或修复）。非阻塞 findings 见 F3–F6。

## 审查范围

- 当前未提交 Slice 5 diff：`dayu/config/prompts/`（14 manifest + 18 prompt fragment）、`tests/runtime/test_scene_assets_migration.py`、`dayu/config/README.md`、`docs/host/implementation-control.md` gate 更新。
- 审查基准：`docs/host/design.md` 的 ScenePrepare / Scene manifest 设计约束；`dayu/runtime/scene_prepare.py` 当前实现。

## 验证执行

| 验证项 | 命令 | 结果 |
|---|---|---|
| 迁移资产装配测试 | `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` | 28 passed |
| import boundary + typing guard | `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 8 passed |
| pyright | `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| git diff --check | clean | 通过 |

## 逐项检查结论

### 1. Schema 保真度

- 全部 14 manifest 声明 `schema_version: 1`，字段名、类型均符合 `_parse_manifest` 期望。
- `model.default_name` 全部 concrete scene 显式声明，符合设计（设计 line 95: "model 必须由 concrete scene 显式声明"）。
- `conversation.mode` 映射正确：`interactive`/`prompt_mt`/`wechat` → `"interactive"`；其余 → `"ordinary"`。
- `tool_selection.mode` 使用允许的枚举值（`all`/`none`/`select`），`tool_names`/`tool_tags_any` 均为有效 JSON array。
- `fragments` 无旧 `type` 字段，每条含 `id`/`path`/`order`/`required`。
- `context_slots` 每条含 `name`/`value_type: "string"`/`required`。
- `runtime: {}` 产生合法 `SceneRuntimeHints(runner_hint_id=None, agent_hint_id=None)`。
- `extends` 全部为 `[]` — 无多继承/循环继承风险。

**结论：manifest schema 保真度通过。**

### 2. Fragment 引用完整性

- Manifest 直接引用的 fragment 文件全部存在于 `dayu/config/prompts/base/`（4 个）与 `dayu/config/prompts/scenes/`（14 个）= 18 个。
- 每个 manifest 的 fragment `path` 解析后均不逃逸 `prompt_asset_root`（测试已覆盖 `_assert_fragment_paths_exist_under_prompt_root`）。
- `base/agents.md`、`base/fact_rules.md`、`base/soul.md`、`base/tools.md` 四个 base fragment 被多个 manifest 共享引用，符合复用设计。

**结论：fragment 引用完整性通过。**

### 3. 禁止资产泄漏

- `dayu/config/prompts/tasks/` 不存在。
- `dayu/config/prompts/base/directories.md` 不存在（测试断言 `test_migrated_prompt_assets_exclude_forbidden_legacy_files` 已覆盖）。
- 无 `*.contract.yaml` / `*.contract.yml` 文件。
- 无未被 manifest 直接引用的 `.md` 文件（所有 18 个 fragment 均被至少一个 manifest 引用）。

**结论：资产泄漏检查通过。**

### 4. 旧字段移除理由

- `model.allowed_names`：已删除。`scene_prepare.py` 的 `_parse_model_hints` 不消费该字段；设计线 83/85 将模型 allow-list 职责置于 Service / config mapping owner。如该约束仍是产品需求，需在模型配置或 Service 层显式设计后接入。
- `runtime.agent.max_iterations` / `runtime.runner.tool_timeout_seconds`：未映射为 `runner_hint_id`/`agent_hint_id`。当前 `execution_profiles.json` 没有精确对应 hint id；旧 raw patch dict 放入 manifest 违反设计禁止 extra payload 的约束。`runtime: {}` 是 Schema 合法的最窄表示。

**结论：删除 old bag fields 理由成立，符合设计约束。**

### 5. Host 接口不变

- Slice 5 只新增 `dayu/config/prompts/` 资产文件与迁移测试。未修改 `dayu/host/` 下任何文件，未变动 Host 公开接口签名的参数、类型或行为语义。
- 设计 line 105："Phase 12 不修改 Host 公开接口"。已满足。

**结论：Host 边界不变，通过。**

### 6. 导入与类型边界

- `tests/runtime/test_scene_assets_migration.py` 仅 import `dayu.contracts.JsonValue` 与 `dayu.runtime.scene_prepare` 公开符号。无 `dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins` 导入。
- pyright 0 errors。

**结论：导入边界通过。**

### 7. 文档准确性

- `dayu/config/README.md` 新增 `prompts/` 目录结构表、职责说明与排除资产范围声明，与当前文件布局一致。
- `docs/host/implementation-control.md`：gate 位置已从 "Slice 5 implementation" 更新为 "Slice 5 code review"，下一 gate 记录为 "Slice 5 accepted local commit 或 Slice 5 fix"，追加当前 Slice 5 implementation 事实摘要与 controller 本地复跑结果。

**结论：文档更新准确。**

## Findings

### F1 (HIGH) — `{{slot_name}}` 占位符在所有 prompt fragment 中完全缺失

**位置：**
- 全部 `dayu/config/prompts/base/*.md` 与 `dayu/config/prompts/scenes/*.md`（18 个文件）
- 对应 manifest 声明：13/14 manifest 的 `context_slots`（`infer.json` 例外，仅声明 `fins_default_subject` 一个 slot）

**事实：**
`grep '\{\{.*\}\}' dayu/config/prompts/` 返回零结果。13 个 manifest 声明了必需 `context_slots`（`fins_default_subject`、`base_user`），但没有任何 `.md` fragment 包含 `{{fins_default_subject}}` 或 `{{base_user}}` 占位符。ScenePrepare 的 `_render_fragment_content` 会校验 slot 名称、注入值、并最终检查残留未解析占位符 — 所有这些步骤在无占位符时均为 no-op，`system_messages` 输出不包含任何注入的 context 值。

**影响：**
`context_slots` 声明与 fragment 内容之间存在语义断层。ScenePrepare 装配成功（测试通过），但 context 值从未实际注入系统消息。端到端使用时，模型将看不到 `fins_default_subject`（公司名称等）或 `base_user`（用户上下文），可能产出无上下文锚点的响应。

**建议：**
1. 若 fragment 内容需要上下文注入：在对应的 scene fragment（如 `scenes/infer.md`）或 base fragment（如 `base/fact_rules.md`）中插入 `{{fins_default_subject}}` 占位符，位置由业务 prompt 设计决定。
2. 若当前 slice 的 fragment 内容尚未设计上下文注入位置：将 `context_slots` 中的 `required` 改为 `false`，或暂时在需要注入前将 `context_slots` 声明为空数组。当前声明为 `required: true` 但从不消费的 slot 构成误导性契约。

### F2 (MEDIUM) — `base/tools.md` 残留旧 `<when_tag>` 条件标记

**位置：** `dayu/config/prompts/base/tools.md:27–84`

**事实：**
迁移的 `tools.md` 包含 9 个旧 `dayu-agent` 的条件 include 标记：
```
<when_tag doc> ... </when_tag>
<when_tag fins> ... </when_tag>
<when_tag ingestion> ... </when_tag>
<when_tag web> ... </when_tag>
<when_tool get_current_time> ... </when_tool>
```
ScenePrepare v1 不解释这些标记 — 它们会以文字形式出现在装配后的 `system_messages` 中。设计 line 81 明确："Service 不应二次解释 fragments"。

**影响：**
`<when_tag>` 与 `</when_tag>` 会作为可见文本进入 LLM 系统消息，可能被模型误解为指令或格式要求，也可能干扰模型对真实指令的理解。

**建议：**
1. 若这些标记是有意保留以供未来下游 processor 处理：需在 manifest 或文档中注释其用途与处理责任方，且需确认是否存在对应 post-processor 计划。
2. 若本不应残留：从 `tools.md` 删除所有 `<when_tag>`/`</when_tag>`/`<when_tool>`/`</when_tool>` 标记行，保留标记内的正文内容。

### F3 (LOW) — 无真实 manifest 使用 `extends` 继承

**位置：** 全部 14 manifest 均声明 `extends: []`。

**事实：**
ScenePrepare 的 `_resolve_scene` 实现了单继承解析、循环检测与 fragment 去重合并。但这些逻辑从未被真实资产触发 — 所有 14 个 scene manifest 都是根 manifest。`extends` 功能在 `test_scene_prepare.py` 单元测试中有覆盖，但缺乏真实资产的集成验证。

**影响：**
若后续新增子 scene 利用继承时变更 `_resolve_scene` 行为，当前无集成测试保护。不阻塞当前 slice。

### F4 (INFO) — `capability_tags` 与 `scene` 字段语义重叠

**位置：** 全部 14 manifest 的 `capability_tags` 仅包含与 `scene` 字段相同的单一 id。

**事实：**
设计 line 91："`capability_tags` 用于 Service workflow 或未来 skill 按能力引用 scene"。当前每个 manifest 的 `capability_tags` 就是 `[scene_id]`，与 `scene` 字段值一致，尚未提供超出 scene id 的分类/分组语义。这对 v1 有效，但不增加信息量。

**影响：**
不阻塞当前 slice。workflow/skill orchestration 引入后可追加更细分的能力标签。

### F5 (LOW) — 迁移测试仅覆盖 happy path

**位置：** `tests/runtime/test_scene_assets_migration.py:131–164`

**事实：**
`test_all_migrated_scene_assets_prepare_successfully` 对所有 manifest 使用 fake 工具目录和预构造 context slot 值走通完整装配。测试验证了 schema 解析、fragment 加载、context slot 注入与工具选择。但未覆盖：required fragment 缺失、未知 tool_name in select mode、context slot value 缺失等错误路径。这些错误路径在 `test_scene_prepare.py` 中有单元级覆盖，故不阻塞。

**建议：**
考虑增加一个迁移级负面测试：例如声明一个不存在的 fragment 路径并验证 ScenePrepare 抛出 ScenePrepareError。

### F6 (INFO) — `conversation_compaction` 使用 `model.default_name: "mimo-v2.5-pro-thinking-plan"` 但未声明 tool_selection

**位置：** `dayu/config/prompts/manifests/conversation_compaction.json:18-23`

**事实：**
`conversation_compaction` 的 `tool_selection.mode` 为 `"none"`，编译操作不使用业务工具。这是正确的。但 `model.default_name` 使用 `"mimo-v2.5-pro-thinking-plan"`（包含 thinking），而 compaction 通常不需要深度推理。这不影响正确性（hint 由 Service 映射），但提示需确认 compaction 场景是否需要 thinking model profile。

## 残余风险

1. **`{{slot_name}}` 注入真空**（同 F1）：迁移的 fragment 内容与 manifest context_slot 声明之间存在未闭合的语义环。后续端到端集成必须解决此问题，否则 context 值永不进入系统消息。
2. **`<when_tag>` 标记可见性**（同 F2）：若 base/tools.md 按原样装配为 system message，旧标记将作为文本泄露给模型。
3. **温度 profile 语义未映射**：manifest 中的 `temperature_profile` 值（如 `"infer"`、`"write"`、`"audit"`、`"interactive"` 等）由 Service / execution profile 解释为 `RunnerCallOptions`。当前 `execution_profiles.json` 中尚无与这些 profile id 对应的条目，需后续 Service 侧补齐映射。本 slice 的 `runtime: {}` 不影响正确性。
4. **旧 `allowed_names` 删除后无替代**：目前没有机制对模型做 allow-list 约束。如仍为产品需求，需在模型配置层或 Service 层显式设计。

## 总体评估

- Schema 保真度：14/14 manifest 符合 ScenePrepare schema v1，字段类型、必需性、枚举值均正确。
- Fragment 完整性：18/18 manifest 直接引用的 fragment 文件存在且路径不逃逸 root。
- 资产泄漏：无 tasks/、contract、未引用模板等禁止资产。
- 类型/导入边界：pyright 0 errors；边界测试通过；无越层依赖。
- 旧字段删除：`allowed_names` 与 raw runtime patch 的移除符合设计约束与编码规范。
- 文档：README 与控制文档更新准确反映当前状态。

阻塞项（F1/F2）均为语义/内容级别，不涉及 Schema 格式错误或类型/边界违规。F1 需用户裁决：当前 fragment 是否需要插入 `{{slot_name}}` 占位符，或 context_slots 的 required 声明是否需要调整。F2 需确认 `<when_tag>` 标记的迁移策略：保留作下游处理，或删除以得到干净系统消息。
