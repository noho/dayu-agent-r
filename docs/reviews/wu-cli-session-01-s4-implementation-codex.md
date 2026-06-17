# WU-CLI-SESSION-01 S4 Implementation - Codex

日期：2026-06-16

## 变更摘要

- 新增 `dayu-cli session` 命令 parser，包含 `list` / `resume` / `purge` 二级命令；S4 仅实现 `list` 与 `purge`，`resume` 固定 parser shape 并返回 not implemented。
- 新增 `dayu.cli.commands.session.run_session_command`，通过 `prepare_entrypoint_runtime(...)` 与 `open_host(...)` 打开 Host，只调用 Host public `list_sessions()` / `purge_session(...)`。
- `session list` 复用 S3 `render_session_list(...)`，不展示 Attempt、execution、payload ref、digest 等内部治理字段。
- `session purge` 支持 `--session-id` 或 `--label + --kind prompt|interactive`，强制 `--yes`，不会自动 close / cancel；label selector 先通过 `list_sessions()` 按 slot truth 解析，再调用 `purge_session(...)`。
- purge Host 错误映射为用户可读 stderr；`INVALID_STATE` 明确说明 purge 需要 closed Session 且所有 Run 已终态，并说明 CLI 不自动 close/cancel；label selector 的 TOCTOU 错误包含原始 selector、resolved session_id、Host code/message。
- 修复 blocker：`session` 不是现有 prompt manifest，`session list/purge` 的 runtime assembly carrier 改用已有 `prompt` scene；Host 调用上下文仍使用 CLI session operation 语义。删除易被误用的 public `CLI_SESSION_SCENARIO` 常量，避免把 session 命令误认为拥有独立 LLM scene。
- 补充 session CLI 测试，覆盖 parser help、list 输出、purge by session id、purge by label、缺 `--yes`、`INVALID_STATE`、TOCTOU 错误和 purge 成功输出。
- 补充 fake runtime request capture，断言 `session list/purge` 的 `EntrypointRuntimeRequest.scene_id == "prompt"`，且包含 `prompt.json` 所需的 `fins_default_subject` / `base_user` slots。
- 按 `tests/README.md` 边界同步 CLI 测试事实。

## 修改文件

- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `dayu/cli/host_context.py`
- `dayu/cli/commands/session.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_session_command.py`
- `tests/README.md`
- `docs/reviews/wu-cli-session-01-s4-implementation-codex.md`

## 验证结果

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_session_command.py -q`
  - 通过：47 passed
  - 备注：仅有既有 `edgar` deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：0 errors, 0 warnings, 0 informations
  - 备注：pyright 提示有新版本可用。
- `git diff --check`
  - 通过

## README 检查结论

本 slice 修改并新增了 CLI tests，`tests/README.md` 明确要求新增测试事实同步；已按其测试手册职责更新 `tests/cli/` 覆盖范围说明。未写用户手册，也未声称 S5 resume 已实现。

## 残余风险

- `session purge --label` 的 list-resolve 与 purge 之间仍存在计划允许的 TOCTOU；S4 已在错误输出中保留 selector、resolved session_id 与 Host code/message，最终状态仍以 Host purge precondition 为真源。
- `session resume` 仅固定 parser shape，执行逻辑留给 S5。
- S4 未实现 JSON output、pagination、resume/list/purge 以外能力，也未读取 Host durable internals。
- S4 的 Host opener runtime assembly 复用 `prompt` manifest 只是 carrier，不表示 session 命令会提交 prompt Run 或具备 LLM scene 语义。
