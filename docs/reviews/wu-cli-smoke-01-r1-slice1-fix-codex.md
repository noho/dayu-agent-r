# WU-CLI-SMOKE-01-R1 Slice 1 Fix Codex

## Gate / Status

- Work unit: `WU-CLI-SMOKE-01-R1`。
- Gate: Slice 1 code review fix。
- Finding: `DS-F03`（accepted）。
- Status: `fix-complete-stop`；等待 AgentMiMo / AgentDS narrow re-review。
- Artifact path: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`。

## Scope

- 仅为 `CliThinkingRenderer.close()` 已成立的 owner contract 补直接回归保护：关闭后再次调用 `record()` 不向 stderr 追加输出。
- 不修改生产代码、公共 contract、design、plan、控制文档或已有 implementation / review / adjudication artifact。
- 不进入 Slice 2，不执行 commit、push、PR 或 review。

## Changed Files

- `tests/cli/test_thinking_renderer.py`：新增 `test_thinking_renderer_suppresses_records_after_close`。
- `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`：记录本 fix gate 的范围、断言、验证与停止状态。

## Direct Owner-level Assertion

- 测试直接构造 `CliThinkingRenderer`，并复用现有 `_thinking()` helper 产生 public `EntrypointThinking` DTO；没有新增 fake owner、兼容分支或下游补偿。
- 首次 `record()` 后精确断言 stderr 为 `Thinking: 正在分析收入变化`，证明 renderer 处于可输出状态。
- 调用 `close()` 后，以全新 `dedupe_key`、更大的 `runtime_sequence` 和不同文本再次调用 `record()`；最终断言 stderr 与关闭前完全相同。由此排除 dedupe 与乱序过滤掩盖结果，直接证明 close owner contract。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_thinking_renderer.py -q`
  - 结果：通过，`9 passed, 3 warnings`。
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - 结果：通过，`90 passed, 3 warnings`。
- `source .venv/bin/activate && pyright`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - 结果：通过，exit code `0`，无输出。
- pytest warnings 均来自 `.venv` 内 `edgar` 依赖的既有 `DeprecationWarning`；pyright 另提示可升级版本，不影响本 gate 结果。

## README Decision

- 已阅读 `tests/README.md` 的维护约定与 README 更新边界。
- 本次只在既有 `tests/cli/` thinking renderer 测试层补一个直接 contract case，没有新增测试层级、运行方式或维护规则，也没有改变读者工作流。
- Decision: 不修改 `tests/README.md`；其余 README 亦未触发。

## Propagation Audit

- Production owner: `CliThinkingRenderer` 的 `close()` / `record()` 行为未修改。
- Host public contract: 未修改。
- Service DTO: 未修改；测试只复用现有 public `EntrypointThinking`。
- CLI output contract: 未修改；仅增加对既有关闭语义的回归断言。
- Design、plan、implementation / review / adjudication artifact 与控制文档：未修改。

## Residual Risk

- `DS-F03`：已由直接 owner-level 测试覆盖，本 fix scope 内无未分类 residual risk。
- `DS-F02` 仍按 controller adjudication 归属 Slice 2；本 gate 不进入、不重分类该项。
- 外部依赖 deprecation warnings 与 pyright 版本提示不由本次 test-only 变更引入。

## Stop Status

- 最终 `git diff --check` 与白名单审计已完成；本 fix gate 到此停止，等待 narrow re-review。
- 不 commit、不 push、不创建 PR、不执行 review、不进入 Slice 2。
