# Gateflow S1 accepted finding fix — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：S1 `implementation review -> fix`
- Slice：S1，仅修复 `S1-CR-001`
- Accepted plan commit：`34127db4`
- Accepted plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s1-implementation-20260801-154645.md`
- Code review artifacts：
  - `docs/reviews/code-review-20260801-155214.md`
  - `docs/reviews/code-review-20260801-155610.md`
- Adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s1-code-review-adjudication-20260801-155756.md`
- Fix time：2026-08-01 16:06:01 CST
- 状态：accepted finding fix 完成；等待独立 `re-review`

## Scope 与第一性原理判断

`S1-CR-001` 成立，严重性评估为低且准确。直接代码证据是
`build_parser() -> _register_session_command() -> _register_session_resume_action()`
把含 `--config` 的 action runtime parent 传给 `resume` leaf；同一参数随后又被
`_reject_disallowed_explicit_config()` 对最终 `session resume` 路由无条件拒绝。
因此 help/parser surface 与执行 contract 分裂，根因不是 command runner、runtime config
解析或展示层问题。

显式参数可达性的唯一语义 owner 是 `dayu.cli.arg_parsing`。本次只在该 owner boundary
拆分 session action parent 装配，并在直接 owner test 中补齐 contract；没有在下游增加
fallback、兼容分支或二次校验。

### Fix changed files

- `dayu/cli/arg_parsing.py`
- `tests/cli/test_arg_parsing.py`
- 本 artifact

没有修改两份 reviewer artifact、adjudication、accepted plan 或 implementation artifact。

## Exact fix

1. `_register_session_command()` 显式接收 action common/runtime 两个 parent：
   - `session list`、`session purge` 继续使用含 `--config` 的 runtime parent；
   - `session resume` 改用不含 `--config` 的 common parent。
2. 保留 session command 自身的 runtime parent，以及
   `_reject_disallowed_explicit_config()` 的最终路由校验：
   - `--config X session resume ...`：root scope 接受后由最终 leaf 校验以 usage error 2 拒绝；
   - `session --config X resume ...`：command scope 接受后由最终 leaf 校验以 usage error 2 拒绝；
   - `session resume ... --config X`：resume leaf 不注册该参数，由 argparse 以 usage error 2 拒绝。
3. 测试补齐：
   - `session resume --help` 不含 `--config`；
   - resume 的 root、command、action 三个参数位置全部 fail closed；
   - session list/purge 的 root、command、action 三个参数位置都保留既有 config 正向映射。

三个 resume 位置都在 command runner、runtime、Host 或 Session 动作前退出，没有静默忽略。

## Finding closure

### S1-CR-001 — 已修复

- Help absence：已由真实 `build_parser()` help 测试证明。
- Resume rejection：root/command 位置由现有 command-aware validation 拒绝，action 位置由
  不含 config 的 resume leaf parser 拒绝；均为 `SystemExit(2)`。
- Non-Agent regression：session list/purge 在 command/action 位置继续把显式值投影到
  `ParsedCliArgs.config_dir`，root 位置也保持不变。
- Owner boundary：只修改 session action parent 选择；没有删除或事后篡改 argparse action。

## Scope boundary preserved

- 没有修改 `--ticker` shared parser；prompt-mode resume 继续允许 ticker，interactive-mode
  resume 的既有 runtime 前拒绝保持不变。
- 没有重构 `--mode` 或把 mode 提升为新子命令。
- 没有进入 F05-F13、S2-S6、registry、oracle、README 或 design。
- 没有新增旧参数、旧 namespace 或旧 schema 的兼容逻辑。
- 没有 commit、push 或创建 PR。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Tests

```text
pytest tests/cli/test_arg_parsing.py -q
```

结果：`439 passed, 3 warnings`。

```text
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

完整 S1 focused 结果：`576 passed, 3 warnings`。

coverage 使用完整 CLI/affected Service regression 后追加 prompt owner test：

- 主回归：`1152 passed, 7 skipped, 3 warnings`；
- 追加 owner test：`53 passed, 3 warnings`。

warnings 均来自 edgartools deprecated module；7 个 skip 属于既有平台/capability 条件，
本 fix 没有新增 skip 或 warning。

### Type、format 与 diff

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `python -m compileall -q dayu/cli tests/cli tests/service/test_entrypoint_runtime_interactive_path.py`：通过。
- `python -m ruff check` 对 7 个 S1 production 文件与 5 个 owner test 文件：
  `All checks passed!`。
- `git diff --check`：通过。

### Branch coverage

coverage artifact：`workspace/tmp/s1-cr-001-fix-coverage.json`。

| Production file | Branch coverage |
|---|---:|
| `dayu/cli/arg_parsing.py` | 99.48% |
| `dayu/cli/host_context.py` | 97.87% |
| `dayu/cli/session_identity.py` | 100.00% |
| `dayu/cli/session_execution.py` | 82.05% |
| `dayu/cli/commands/prompt.py` | 92.42% |
| `dayu/cli/commands/interactive.py` | 88.71% |
| `dayu/cli/commands/session.py` | 82.11% |

全部 S1 modified production files 均达到 `>=80%`。

### Safety 与旧引用检查

- 新增 production/test diff 对 AWS key、`sk-` token、Authorization Bearer 与长 Bearer
  token 形态的 secret scan：零命中。
- production 中旧 prompt/interactive scope、prefix、kind enum、slot helper：零命中。
- production 中旧 `cli.prompt.*` / `cli.interactive.*` namespace：零命中。
- `dayu/cli` 中 `--kind`：零命中。
- prompt/interactive/session execution 中 removed config 读取与解析：零命中。
- interactive/session execution 中 removed ticker 读取与 helper：零命中。

## Docs decision

按项目 README 触发规则检查了根 `README.md` 与 `tests/README.md` 的职责边界。根 README
当前仍有待 S6 收敛的旧全局 config 描述，tests README 也仍投影整个 S1-S6 变更前的测试事实；
accepted plan 已明确把 registry/oracle/README/design 的稳定同步冻结到 S6，且本次用户禁止进入
S6，因此本 fix 不修改 README。该决定不把旧文档当作当前 parser 真源。

## Residual risk 与 uncovered areas

- README/registry/oracle 的稳定投影尚未同步：`covered by later approved slice`（S6）。
- F05-F13 尚未实施且未由本 fix 验证：`covered by later approved slice`（S2-S6）。
- 本地回归中的既有平台/capability skips 未在本机转化为跨平台实证：
  `assigned to later work unit`；不影响本 finding 的 argparse owner contract。
- 旧 `cli.prompt.*` / `cli.interactive.*` durable slot 按 accepted no-compat contract 不迁移；
  这是冻结 non-goal，不是本 fix 新增风险。

没有 unclassified residual risk，没有 blocking open question。

## Completion 与 next gate

- Completion status：`accepted finding fix complete`。
- Finding status：`S1-CR-001 = 已修复`。
- Next entry point：`re-review`。
- Artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s1-fix-20260801-160601.md`。
- Commit / push / PR：均未执行。
