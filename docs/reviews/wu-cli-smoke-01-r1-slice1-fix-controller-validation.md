# WU-CLI-SMOKE-01-R1 Slice 1 Fix Controller Validation

## Scope

- Finding: accepted DS-F03。
- Fix artifact: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`。
- Fix files: `tests/cli/test_thinking_renderer.py` 与 fix artifact；无生产代码 fix。
- Validation profile: supplemental control `test-harness-low`。

## Direct Validation

- 新测试先证明 renderer 可输出，再调用 `close()`，随后使用新 `dedupe_key`、更大的 `runtime_sequence` 与不同文本调用 `record()`，最后断言 stderr 未变化；去重和乱序分支不能掩盖 close contract。
- `source .venv/bin/activate && pytest tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`：`99 passed, 3 warnings`。
- `source .venv/bin/activate && pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：pass，无输出。
- warnings 均来自既有 `edgar` dependency deprecation，不是本 fix 引入。

## README / Propagation / Residual

- README decision: no update；测试层级、运行入口与维护规则均未变化。
- Propagation audit: Host public contract、Service DTO、CLI production output 与其它测试未被本 fix 修改。
- DS-F03: fix evidence complete，待 AgentMiMo / AgentDS narrow re-review final closure。
- DS-F02: 继续归属 Slice 2。
- Baseline residual: none。

## Decision

`ready-for-code-rereview`。不得在 re-review 前 commit 或进入 Slice 2。
