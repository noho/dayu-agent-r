# WU-CLI-01 / CLI-01-S4 Implementation Review Controller Adjudication

## 裁决

Pass-with-fix。

S4 的主目标是迁移旧 `interactive` 的业务逻辑与用户可见语义，并适配当前 Host public contracts / API；不是迁移旧 `interactive_ui.py` 或旧 label registry。两路 review 均确认主路径和架构边界成立，但 DS 提出两个 low finding，其中输入态 Ctrl-C 缺少测试覆盖直接落在 accepted plan 的“按实现测试固定”要求上，因此进入 low-fix。

## Review 输入

- Implementation report: `docs/reviews/wu-cli-01-s4-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-cli-01-s4-implementation-review-mimo.md`
- AgentDS review: `docs/reviews/wu-cli-01-s4-implementation-review-ds.md`

## 通过项

- `interactive` 只通过 `EntrypointRuntimeRequest(scene_id="interactive")`、Service helper、`open_host(...)` 与 Host public API 触达 Host；未直接构造 Engine request，未访问 Host durable/internal，未读取 Fins storage。
- CLI / Service 边界清晰：CLI 负责 REPL 输入、signal、stdout/stderr、exit code、Host context/id；Service helper 仍不依赖 CLI，可被后续 WeChat / GUI 复用。
- `--label`、`--new-session`、`--ticker`、`--model-name`、execution overrides 与 unsupported legacy flags 的映射符合 accepted plan。
- 多轮状态机符合 S4：两轮同 session，每轮新的 Host request id / submit client request id，每轮独立 watcher attach/close 与 terminal wait state。
- SIGINT cancel 语义符合 S4：运行态第一次 Ctrl-C 发 typed Host cancel；第二次 Ctrl-C 本地 130；同一轮 cancel id 稳定；等待 run id 阶段 submit 先完成/失败不误映射为 130。
- Terminal policy 符合 S4：`SUCCEEDED` 继续；`FAILED` / `CANCELLED` 继续；`LOST` / Service fatal 退出 1。

## Accepted Findings

- S4-IMPL-F01：输入态 Ctrl-C 行为缺少明确测试覆盖。当前实现选择退出当前 command 并返回 130；accepted plan 明确要求“按实现测试固定”，因此需要补测试。
- S4-IMPL-F02：运行态 SIGINT task cleanup 存在分支和 finally 重复 cancel / await 的代码异味。功能正确但增加状态机阅读负担，应低风险清理。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q`：63 passed；`interactive.py` 88%，`host_context.py` 99%，`output.py` 83%，`arg_parsing.py` 100%，`main.py` 94%。
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q`：82 passed。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## 下一步

AgentCodex low-fix gate。
