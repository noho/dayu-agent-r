# WU-CLI-SMOKE-01 current_time scene slot fix

- 执行人：AgentCodex
- 日期：2026-07-07
- 范围：current_time scene context slot 与 get_current_time 工具暴露规则修正
- 约束：不修改 Host/Engine 状态机、durable schema、Fins storage 协议；不 commit、不 push、不创建 issue/PR

## 动机

`current_time` 展开为完整 Markdown 块：

```markdown
# 当前时间
现在是 ...
```

因此它和 `fins_default_subject` 一样，不能放在 scene H1 下打断执行契约。用户明确要求除 compact scene 外所有 scene 都通过 context slot 获得当前时间；只有 `prompt`、`interactive`、`wechat` 继续额外暴露真实 `get_current_time` 工具。该问题基于当前 manifest/scene 与 Service 入口事实成立，需要修正。

## 改动

- 更新 `dayu/config/prompts/manifests/*.json`：
  - 除 `conversation_compaction` 外，所有 packaged scene manifest 均声明 required string `current_time` context slot。
  - `prompt`、`interactive`、`wechat` 保留 `"utils"` tag，因此继续暴露 `get_current_time`。
  - 其它 scene 不新增 `"utils"` tag，仅通过 `current_time` context slot 获得当前时间。
  - `conversation_compaction` 保持无 `current_time`。
- 更新 `dayu/config/prompts/scenes/*.md`：
  - 除 `conversation_compaction.md` / `conversation_compaction_user.md` 外，所有 scene 都在主要执行契约正文之后渲染独立行 `{{current_time}}`。
  - 同时存在 `{{current_time}}` 和 `{{fins_default_subject}}` 的 scene，顺序为 `current_time` 在前、`fins_default_subject` 在后。
- 更新入口和 utility path：
  - `dayu/cli/commands/interactive.py` 现在为 interactive scene 注入 `current_time`，仍不注入 `fins_default_subject`。
  - `utils/smoke_host_public_multiturn.py`、`utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_conversation_memory_scenarios.py` 的 packaged scene prepare 请求补 `current_time`。
  - compactor scene prepare 仍使用空 context slot map，符合 compact 排除规则。
- 更新测试：
  - `tests/runtime/test_scene_assets_migration.py` 新增 current_time source placement invariant、ScenePrepare 展开后 system prompt 顺序 invariant、以及 `get_current_time` 只在 prompt/interactive/wechat 暴露的 invariant。
  - 补齐 service、CLI、Host assembly 测试夹具中的 required `current_time`。
  - 保留既有 `fins_default_subject` placement invariant。
- 更新 README：
  - `dayu/config/README.md` 记录 `current_time` slot 与 `get_current_time` 工具暴露边界。
  - `tests/README.md` 更新 interactive/current_time 与 scene asset migration 覆盖事实。

## 验证

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py
```

- 结果：63 passed。

```bash
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
```

- 结果：102 passed，3 个来自 `edgar` 依赖的 deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
```

- 结果：91 passed，3 个来自 `edgar` 依赖的 deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py
```

- 结果：7 passed，3 个来自 `edgar` 依赖的 deprecation warnings。

```bash
source .venv/bin/activate && pyright
```

- 结果：0 errors, 0 warnings, 0 informations。
- 附带提示：pyright 有新版本可用。

```bash
git diff --check
```

- 结果：通过，无输出。

## 同源 utility reconstruction bug

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

- 总控复跑时曾出现 5 failed，直接证据为 `compose_open_host_options(...)` 在 `_fins_wait_activation_registry_from_provider_configs(...)` 抛出 `ValueError: Fins wait activation registry requires shared runtime`。
- 根因：`utils/smoke_host_public_conversation_memory.py` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 在为内置 smoke tool 重建 `ServiceDiscoveredTools` 时透传了 provider configs 和 tool bundle，但漏传 `discovered.fins_awaiting_runtime`。当 awaiting provider configs 存在时，Host assembly 需要同一个 shared runtime。
- 修复：两个 utility 的 `ServiceDiscoveredTools(...)` 返回补 `fins_awaiting_runtime=discovered.fins_awaiting_runtime`，对齐已正确处理的 `utils/smoke_host_public_multiturn.py`。
- 验证：复跑该命令通过，20 passed。

## 真实 provider smoke

总控在 review / re-review 全部通过后补跑真实 prompt smoke：

```bash
source .venv/bin/activate && dayu-cli --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-current-time-slot/prompt.log \
  prompt --label wu-cli-smoke-current-time-slot \
  "请调用 get_current_time 工具确认当前时间，然后用一句话回答当前时间。"
```

- 结果：命令 exit 0。
- Provider：`mimo` / `mimo-v2.5-pro`。
- HTTP：debug log 记录两次 runner call 均返回 status 200。
- 工具：debug log 记录 `tool_name=get_current_time`，Host ToolRuntime accepted completed tool fact。
- Final answer：`当前时间是2026年7月7日星期二19:10:40（北京时间）。`
- 证据文件：`workspace/tmp/wu-cli-smoke-01-current-time-slot/prompt.log`。

## 风险与未覆盖

- 真实 provider CLI smoke 已覆盖 `prompt` scene 下 `get_current_time` 工具可用并可完成调用；该 smoke 不单独证明每个非 compact scene 的 `current_time` 文本都进入 system prompt，后者由 scene asset migration 与 ScenePrepare 测试覆盖。
- `current_time` 对非 compact scene 现为 required slot；后续新增 scene 时，如果不是 compact scene，需要同时声明 manifest slot、渲染 scene placeholder，并在所有 ScenePrepare 调用方补值。

## DS review accepted low findings fix

### 本次补充修复

- F02：在 `dayu/config/README.md` 的 prompts scene manifest 说明中补充 `prompt` scene 边界：`prompt` 是单轮问答 scene，不暴露 download / preprocess / upload 这类长事务工具；需要模型在对话中触发 download / preprocess 时使用 `interactive` 或 `wechat` scene。
- F03：在 `tests/runtime/test_scene_assets_migration.py` 新增 `test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot`，显式断言 `smoke_host_public_conversation_memory` 与 `smoke_host_public_conversation_memory_scenarios` manifest 不声明 `fins_default_subject`，且对应 scene md 不渲染 `{{fins_default_subject}}`。
- F04：在 `tests/runtime/test_scene_assets_migration.py` 更新 `_first_contract_content_line_index`，除 `{{fins_default_subject}}` 外也跳过 `{{current_time}}`，并将中文 docstring 从“默认主体占位符”扩展为“context slot 占位符”语义。
- F01：不做额外代码修复；DS review 指出的 unstaged 测试夹具修改仍必须随本 slice 一起提交，否则 committed 测试状态会与 interactive manifest 的 required `current_time` 不一致。

### 本次验证

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py -q
```

- 结果：17 passed。

```bash
source .venv/bin/activate && pyright
```

- 结果：0 errors, 0 warnings, 0 informations。
- 附带提示：pyright 有新版本可用。

```bash
git diff --check
```

- 结果：通过，无输出。

### 剩余风险

- F01 依赖当前工作区已有 unstaged 测试夹具修复被纳入同一个 slice commit；本任务按约束未 stage、commit、push。
