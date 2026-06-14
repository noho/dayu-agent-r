# PR 141 re-review controller adjudication

## Gate

- gate: PR re-review
- PR: https://github.com/noho/dayu-agent-r/pull/141
- fix artifact: `docs/reviews/pr-141-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/pr-141-rereview-mimo.md`
  - `docs/reviews/pr-141-rereview-ds.md`

## Controller decision

pass。

## Finding status

- PR-RV-F01：已修复。
  - 新增 `dayu/cli/agent_entrypoint.py`，在 CLI UI adapter 层内抽取 prompt / interactive 共享 helper。
  - `prompt.py` / `interactive.py` 已移除重复 workspace / config 解析、文本校验、execution override 映射、
    unsupported option 检测和 SIGINT monitor 定义。
  - 用户可见行为、exit code、cancel 语义、unsupported flag fail-fast 与 Host public API path 未改变。
- PR-RV-F03：已修复。
  - `_normalize_system_exit_code` docstring 不再声称可能抛出 `ValueError`。

## New findings

无。

## Deferred status

- PR-RV-F02 保持 deferred-with-owner，归入 `WU-CLI-01-RR-06` 后续 signal / cancel adapter work。

## Validation

Controller 复核：

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q`：62 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli -q`：94 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Residual risks

- `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-10` 均有 owner / destination。
- 无 unclassified residual risk。

## Next gate

Accepted PR review commit，然后 push 到 PR 141。
