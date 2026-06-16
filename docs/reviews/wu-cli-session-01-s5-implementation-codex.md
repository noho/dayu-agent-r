# WU-CLI-SESSION-01 S5 Implementation - Codex

日期：2026-06-16

## 变更摘要

- 实现 `dayu-cli session resume`：
  - `--session-id` selector 通过 Host public `get_session(...)` 校验目标存在且为 `OPEN`。
  - `--label + --kind prompt|interactive` selector 通过 Host public `list_sessions()` 按 S3 slot truth 精确匹配，找不到不创建。
  - 解析到 `CLOSED` Session 返回 usage error，不 submit。
- `session.py` 只负责 selector resolution、mode 校验和路由；不复制 prompt / interactive 的 submit、watch、cancel 业务路径。
- `prompt.py` 抽出 existing-session 窄入口，复用 prompt runtime assembly、run overrides、SIGINT cancel 和 terminal render；默认 `prompt` 入口仍先 create / ensure，再复用该入口执行。
- `interactive.py` 抽出 existing-session 窄入口，复用 interactive runtime assembly、REPL、每轮 watcher、SIGINT cancel 和 terminal render；默认 `interactive` 入口仍先 create / ensure，再复用该入口执行。
- `session resume --mode prompt` 要求 positional prompt；`--mode interactive` 拒绝 positional prompt。
- selector resolve 后 submit 前发生并发 close / purge 时，Host submit precondition 仍是最终 truth；错误输出包含原始 selector、resolved session_id、Host code/message。
- `session resume` parser 增加 `--ticker`，与 prompt / interactive 的业务上下文槽位行为对齐。

## 修改文件

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/README.md`
- `docs/reviews/wu-cli-session-01-s5-implementation-codex.md`

## 验证结果

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q`
  - 通过：57 passed
  - 备注：仅有既有 `edgar` deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：0 errors, 0 warnings, 0 informations
  - 备注：pyright 提示有新版本可用。
- `git diff --check`
  - 通过
- 额外验证：`source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py -q`
  - 通过：35 passed

## README 检查

本 slice 修改了 CLI 测试事实：`session resume` 已从 S4 not-implemented 变为真实执行路径，并新增 prompt / interactive existing-session helper 覆盖。已按 `tests/README.md` 的测试手册职责小幅更新 `tests/cli/` 覆盖范围说明。未修改用户手册或控制文档。

## 残余风险

- `session resume --label` 的 list-resolve 与 submit 之间仍存在计划允许的 TOCTOU；S5 已在 submit HostApiError 输出中保留原始 selector、resolved session_id 与 Host code/message，最终状态仍以 Host submit precondition 为真源。
- `session resume` 不是 Host wait-resume，不恢复旧 Agent / Runner / Attempt；它只在已有 OPEN Session 上提交新的 queued follow-up。
- S5 未新增 `get_session_by_label`、未实现 steer、未改变 prompt / interactive 默认 anonymous 与 label 行为。
