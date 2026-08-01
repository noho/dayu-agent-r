# Gateflow S1 implementation — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：`implementation`
- Slice：`S1`，仅 F01-F04
- Accepted plan commit：`34127db4`
- Accepted plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- Branch：`codex/interactive-oracle`
- 状态：implementation 完成，等待 `implementation review`
- 本次未执行 review、commit、push 或 PR 操作。

## Scope

本次只修改 S1 允许的七个 CLI production owner、五个直接 owner test 文件，并新增本 implementation artifact。没有进入 F05-F13，也没有修改 S6 registry、oracle、README、design 或冻结 review artifact。

### Modified production files

- `dayu/cli/arg_parsing.py`
- `dayu/cli/host_context.py`
- `dayu/cli/session_identity.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`

### Modified owner tests

- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

## Contract implemented

### F01 — Agent surface 不再接受显式 config

- prompt/interactive parser 改用不含 `--config` 的 command parent；各自 help 与 command-local parser surface 均不再暴露该参数。
- command-aware parser validation 在任何 runtime/Host/Session 动作前拒绝 root-before-command 的 prompt、interactive 和 session resume 显式 config 绕行。
- prompt/interactive runtime preparation 不再读取或解析 `args.config_dir`，统一向 Service request 传 `explicit_config_dir=None`。
- session list/purge 与其它非 Agent runtime command 的既有 config 能力保留。

### F02 — interactive 不再接受 ticker

- interactive help/parser、command conversion、invocation identity 与 context request 均移除 ticker/FMP 环境读取；interactive invocation 固定 `ticker=None`。
- `session resume --mode interactive` 在 runtime prepare 前明确拒绝共享 parser 上的 `--ticker`。
- prompt 与 prompt-mode resume 的 ticker 行为保留。

### F03 — 唯一 durable alias owner

- 唯一 namespace 为 `scope="cli.agent"`、`slot_key="cli.agent.<label>"`；唯一 label owner 为 `cli_label_slot_key()` / `slot_ref_for_cli_label()`。
- prompt、interactive、session list/purge/resume 机械复用同一映射。
- 删除 `CliSessionLabelKind`、`session --kind`、双 namespace 常量/helper 与全部 production 直接消费者。
- 没有读取、迁移、回退或兼容 `cli.prompt.*` / `cli.interactive.*`；旧 slot 仅按普通未知 slot 投影为 `OTHER`。
- 无 label prompt 保持 one-shot fresh；无 label interactive 每次 invocation 保持 fresh。

### F04 — exact Session 与 memory owner evidence

- 新增真实 `CLI -> Service -> Host -> Engine worker request` 路径的四种 labeled 顺序：prompt→prompt、prompt→interactive、interactive→prompt、interactive→interactive。
- 每种顺序直接断言两个 Host/runner snapshot 的 exact `session_id` 相同，并从第二轮 `AgentRunRequest.messages` 断言第一轮 User/Assistant memory 与第二轮 User input；没有从最终 CLI answer 猜测复用结果。
- prompt/interactive 无 label 各连续执行两次，直接断言 exact `session_id` 不同且第二轮 runner input 不含第一轮 memory。
- 删除生产测试中把 README 当前文字当作已实现 interactive ticker contract 的过宽 claim；稳定 registry/docs 留待 S6。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Static and formatting checks

```text
python -m compileall -q dayu/cli tests/cli tests/service/test_entrypoint_runtime_interactive_path.py
python -m ruff check <7 production files> <5 modified owner test files>
git diff --check
```

结果：全部通过；ruff 为 `All checks passed!`，diff whitespace 检查零错误。

### Focused owner tests

```text
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

最终结果：`573 passed, 3 warnings in 8.58s`。warnings 均来自 edgartools deprecated module，不是本 slice 新增失败或告警。

### Integration smoke and affected regression

```text
pytest tests/service/test_entrypoint_runtime_interactive_path.py -q \
  -k 'labeled_agent_surfaces_share_exact_session or unlabeled_agent_invocations_use_fresh_session'
```

结果：`6 passed, 3 deselected`；覆盖四种 labeled surface 顺序与 prompt/interactive 两种 unlabeled fresh 路径。

```text
pytest tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

结果：`77 passed`。

```text
pytest tests/cli tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

结果：`1148 passed, 7 skipped`。随后只新增一个不改 production 语义的 lifecycle owner coverage test；该文件最终单独复跑结果为 `53 passed`，最终 S1 focused suite 为 `573 passed`。

### Type checking

```text
python -m pyright dayu/ tests/ utils/
```

最终结果：`0 errors, 0 warnings, 0 informations`；无新增或扩散类型错误。

### Removed contract and safety scans

以下 production 查询均零命中（`rg` exit 1）：

```text
rg -n 'PROMPT_SESSION_SCOPE|INTERACTIVE_SESSION_SCOPE|PROMPT_SLOT_KEY_PREFIX|INTERACTIVE_SLOT_KEY_PREFIX|CliSessionLabelKind|prompt_slot_key|interactive_slot_key' dayu/cli
rg -n 'cli\.(prompt|interactive)(\.|"|$)' dayu
rg -n -- '--kind' dayu/cli
rg -n -- '--config' dayu/cli/commands/prompt.py dayu/cli/commands/interactive.py dayu/cli/session_execution.py
rg -n -- '--ticker' dayu/cli/commands/interactive.py dayu/cli/session_execution.py
rg -n 'args\.config_dir|resolve_explicit_config_dir' dayu/cli/commands/prompt.py dayu/cli/commands/interactive.py dayu/cli/session_execution.py
rg -n 'args\.ticker|_interactive_ticker|_resume_interactive_ticker' dayu/cli/commands/interactive.py dayu/cli/session_execution.py
```

parser/help/position-specific removed-argument evidence由 `test_agent_help_omits_removed_parameters`、`test_agent_surfaces_reject_config_in_every_parser_position`、`test_interactive_rejects_removed_ticker_and_session_kind` 提供；非 Agent config 与 prompt ticker 的正向保留用例同时通过。

新增 production diff 对 `Any`、`object`、`getattr`、`hasattr` 的扫描零命中。新增 diff 对 AWS key、`sk-` token、Authorization Bearer 与 Bearer token 形态的扫描零命中；未打印环境变量值，未发现 secret 泄漏。

## Coverage

命令：

```text
COVERAGE_FILE=workspace/tmp/.coverage-s1-implementation coverage erase
COVERAGE_FILE=workspace/tmp/.coverage-s1-implementation coverage run --branch -m pytest \
  tests/cli tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
COVERAGE_FILE=workspace/tmp/.coverage-s1-implementation coverage run --append --branch -m pytest \
  tests/cli/test_prompt_command.py -q
COVERAGE_FILE=workspace/tmp/.coverage-s1-implementation coverage json \
  -o workspace/tmp/s1-implementation-coverage.json --pretty-print
```

coverage JSON 的逐文件 `percent_covered`：

| Production file | Branch coverage |
|---|---:|
| `dayu/cli/arg_parsing.py` | 99.48% |
| `dayu/cli/host_context.py` | 97.87% |
| `dayu/cli/session_identity.py` | 100.00% |
| `dayu/cli/session_execution.py` | 82.05% |
| `dayu/cli/commands/prompt.py` | 92.42% |
| `dayu/cli/commands/interactive.py` | 88.71% |
| `dayu/cli/commands/session.py` | 82.11% |

全部修改 production file 均达到 `>=80%`。

## Docs decision

README 触发条件虽被 CLI public contract 命中，但 accepted plan 与 controller 明确把 registry/oracle/README/design 的稳定同步冻结到 S6。本 slice 因此没有修改这些文档；只新增本 gate artifact，并在测试中移除会倒逼未实现旧 contract 的过宽 README claim。

## Residual risk

- 本 artifact 只证明 S1/F01-F04；F05-F13、PTY/non-TTY 重构、recovery、compaction 与 S6 registry/docs/真实场景证据均未实施，也未被本 slice 宣称关闭。
- 旧 `cli.prompt.*` / `cli.interactive.*` durable slot 不会被新 alias 读取或迁移，这是 accepted no-compat contract；已有旧 slot 会显示为 `OTHER`。
- 本地测试的 7 个 skip 属于既有平台/capability 条件；本 S1 无新增 skipped contract case。
- 尚未执行独立 implementation review；本 artifact 不包含 review 结论。

## Next

`implementation review`。本执行在该 gate 前停止，不 commit、不 push。
