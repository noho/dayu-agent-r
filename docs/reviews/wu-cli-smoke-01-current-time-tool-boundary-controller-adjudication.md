# WU-CLI-SMOKE-01 Current Time Tool Boundary Controller Adjudication

## 范围

- Work unit: WU-CLI-SMOKE-01 current-time / `get_current_time` 语义边界修正
- 用户裁决：`prompt` 默认只用 `{{current_time}}`，不暴露 `get_current_time`；`interactive` / `wechat` 同时保留 `{{current_time}}` 和 `get_current_time`，并用 LLM-facing 文本明确边界。

## Agent 产物

- AgentCodex implementation artifact: `docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-fix-codex.md`
- AgentCodex plan / self-review artifacts:
  - `docs/reviews/plan-review-20260707-214653.md`
  - `docs/reviews/code-review-20260707-215217.md`
  - `docs/reviews/code-review-20260707-215256.md`
- AgentMiMo review: `docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-review-mimo-20260707-215634.md`
- AgentDS review: `docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-review-ds.md`

## Controller 裁决

- MiMo: Pass，无实质性问题。
- DS Finding 01: 建议补充 `fins_default_subject` 展开测试。裁决为不阻断、不需要本轮 fix；当前 `tests/runtime/test_scene_assets_migration.py` 已有 `test_fins_default_subject_slot_is_rendered_by_declaring_scenes` 与 `test_prepared_fins_default_subject_does_not_interrupt_scene_contract` 覆盖全 scene 声明、占位符和展开后 system prompt 顺序。
- DS Finding 02: 提到 `infer` 历史工具变更。裁决为不属于本轮 uncommitted diff；本轮没有修改 `infer.json`、`write.json`、`confirm.json`、`regenerate.json` 或 `repair.json`，且当前用户裁决只要求修正 `prompt` / `interactive` / `wechat` 的时间工具边界。

## Controller 验证

- `pytest tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - 结果：`179 passed`
- `python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：pass
- manifest 直接检查：
  - `prompt`: `["fins-read", "web"]`
  - `interactive`: `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
  - `wechat`: `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
- 真实环境 prompt smoke:
  - 命令：`dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-time-boundary/prompt.log prompt ... --label wu-cli-smoke-time-boundary --ticker V`
  - run id: `run-f92ba15e942a403eac24f0578f90a244`
  - provider/model: `mimo` / `mimo-v2.5-pro`
  - HTTP: 200
  - `tool_schema_count`: 11
  - `tool_call_count`: 0
- Tool Trace resolver 断言：
  - `# 当前时间` 存在。
  - `# 当前分析对象` 存在。
  - `V（Visa Inc.）` 存在。
  - selected tool schema snapshot 不含 `get_current_time`。
  - tool trace rows 不含工具调用。
  - `called_get_current_time=False`。

## 结论

本轮语义边界修正通过。`prompt` 已只使用静态 `current_time` 文本，不再暴露或调用 `get_current_time`；`interactive` / `wechat` 继续保留工具，并由 LLM-facing 文本限定调用条件。

## Residual Risk

- 用户在 `prompt` 中要求“等待后再确认时间”时，模型只能基于对话开始时给出的当前时间回答，不能重新获取工具调用时刻。这是本轮裁决的预期取舍。
- 历史 review artifacts 可能描述旧行为，不作为当前配置真源。
