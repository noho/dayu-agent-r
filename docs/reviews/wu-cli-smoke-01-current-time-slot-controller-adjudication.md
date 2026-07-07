# WU-CLI-SMOKE-01 current_time scene slot controller adjudication

- 日期：2026-07-07
- Work unit：WU-CLI-SMOKE-01 context slot / scene tool filtering follow-up
- Gate：implementation review / fix / re-review
- Controller：AgentController
- 实现 Agent：AgentCodex
- Review Agents：AgentMiMo、AgentDS

## 用户意图

- `prompt`、`interactive`、`wechat` 同时使用 `get_current_time` 工具和 `{{current_time}}` context slot。
- 除 compact 外，其它所有 scene 都使用 `{{current_time}}`。
- 只有 `prompt`、`interactive`、`wechat` 暴露 `get_current_time` 工具。
- `conversation_compaction` 及 compaction user template 不引入 `current_time`。

## Artifact

- Implementation / fix：`docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md`
- Review：`docs/reviews/wu-cli-smoke-01-current-time-slot-review-mimo.md`
- Review：`docs/reviews/wu-cli-smoke-01-current-time-slot-review-ds.md`
- Re-review：`docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-mimo.md`
- Re-review：`docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-ds.md`
- F04 re-review：`docs/reviews/wu-cli-smoke-01-current-time-slot-f04-rereview-mimo.md`
- F04 re-review：`docs/reviews/wu-cli-smoke-01-current-time-slot-f04-rereview-ds.md`

## 裁决

### MiMo review

- 结论：Pass。
- Finding：无实质性问题。
- Controller decision：accepted pass。

### DS review

- F01：测试夹具中的 `context_slot_values={}` 与 interactive manifest 新增 required `current_time` 不一致。
  - Decision：accepted as commit-scope requirement。
  - 理由：当前工作区已包含对应测试夹具修复；必须随本 slice 一起 stage / commit，否则 committed 状态测试会失败。
- F02：`prompt` 有意排除 download / preprocess / upload 长事务工具，但配置文档未显式说明。
  - Decision：accepted。
  - 修复：`dayu/config/README.md` 已说明 `prompt` 是单轮问答 scene，不暴露长事务工具；对话触发长事务使用 `interactive` 或 `wechat`。
- F03：conversation memory smoke scene 不声明 / 不渲染 `fins_default_subject` 是正确设计，但缺少显式回归断言。
  - Decision：accepted。
  - 修复：`tests/runtime/test_scene_assets_migration.py` 新增显式测试覆盖两个 conversation memory smoke scenes。
- F04：`_first_contract_content_line_index` 未跳过 `{{current_time}}`。
  - Decision：accepted。
  - 修复：测试 helper 现在同时跳过 `{{fins_default_subject}}` 与 `{{current_time}}`，docstring 更新为 context slot 占位符语义。

## 验证

Controller 复跑：

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q
```

- 结果：20 passed，3 个 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py
```

- 结果：70 passed，3 个 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
```

- 结果：102 passed，3 个 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
```

- 结果：91 passed，3 个 `edgar` deprecation warnings。

Codex / Controller 在 fix 后复跑：

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py -q
```

- 结果：17 passed。

```bash
source .venv/bin/activate && pyright
```

- 结果：0 errors, 0 warnings, 0 informations。

```bash
git diff --check
```

- 结果：通过，无输出。

真实 provider smoke：

```bash
source .venv/bin/activate && dayu-cli --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-current-time-slot/prompt.log \
  prompt --label wu-cli-smoke-current-time-slot \
  "请调用 get_current_time 工具确认当前时间，然后用一句话回答当前时间。"
```

- 结果：exit 0。
- Provider：`mimo` / `mimo-v2.5-pro`。
- HTTP：debug log 记录 status 200。
- 工具证据：debug log 记录 `tool_name=get_current_time`，Host ToolRuntime accepted completed tool fact。
- Final answer：`当前时间是2026年7月7日星期二19:10:40（北京时间）。`
- Log：`workspace/tmp/wu-cli-smoke-01-current-time-slot/prompt.log`。

## Controller conclusion

Accepted。当前改动满足用户意图：

- 所有非 compact packaged scenes 都声明并渲染 required `current_time`。
- `conversation_compaction` 与 `conversation_compaction_user.md` 不引入 `current_time`。
- 只有 `prompt`、`interactive`、`wechat` 通过 `utils` tag 暴露 `get_current_time`。
- `prompt`、`interactive`、`wechat` 同时具备 `{{current_time}}` context slot 和 `get_current_time` 工具。
- `interactive` 入口已补 `current_time` slot，仍不注入 `fins_default_subject`。
- conversation memory smoke utilities 已补透传 `fins_awaiting_runtime`，关闭同源 assembly bug。

## Residual risk

- 真实 smoke 验证了 `prompt` 下 `get_current_time` 可调用；其它 scene 的 `current_time` context slot 由资产 / ScenePrepare 测试覆盖，未逐一跑真实 provider。
- 后续新增非 compact scene 时必须同步 manifest `current_time` slot、scene placeholder 与所有 ScenePrepare 调用方；现有 scene asset migration 测试会捕获遗漏。
