# wu-cli-interactive-02 aggregate finding fix

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：aggregate deepreview finding fix
- Branch：`codex/interactive-oracle`
- Base：`main`
- Finding source：
  `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-deepreview-adjudication-20260802.md`
- Fix scope：仅 `AGG-A01`、`AGG-A02`、`AGG-A03`、`AGG-A04`
- Decision：`4 fixed / 0 partial / 0 deferred / 0 unclassified`
- Artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-fix-codex-20260802.md`
- Next entry point：aggregate deepreview re-review

## Scope and owner decision

四项 finding 均由代码直接证据证明成立，且 owner 清晰：

1. `AGG-A01` 的语义 owner 是 `dayu/cli/session_execution.py` 中 invocation
   级 interactive active-turn 生命周期。non-TTY whole-batch 已创建
   `_InteractiveActiveTurn`，但此前只等待 `active.submit_task`，没有消费已经
   安装的 `CliSigintMonitor`。
2. `AGG-A02` 的语义 owner是同一模块的 TTY REPL 状态机；
   `TOGGLE_ACTIVITY` 是显示事件，此前却越界写入 `exit_intent` 与
   `idle_interrupt_revision`。
3. `AGG-A03` 的生产 owner 是
   `begin_compaction_terminal_commit_in_transaction` 与
   `HostTransactionRunner` 的真实 `BEGIN IMMEDIATE` transaction。生产 CAS
   无缺陷，本 finding 只缺确定性竞争证明。
4. `AGG-A04` 的语义 owner 是
   `dayu/engine/contracts/runner_identity.py` 的共享非空文本 validator；此前
   validator 把 owner 名硬编码为 `RunnerRequestIdentity`，导致成功 response
   identity 的错误消息归属错误。

本 fix 没有新增锁、CAS、Host 关闭路径、兼容分支、schema 字段、wire 字段、
adapter fallback 或新调度框架，也没有修改 design、oracle、scenario、README
或既有 review/adjudication artifact。

## Changed files

### Production owner

- `dayu/cli/session_execution.py`
  - 把 invocation `CliSigintMonitor` 传入两个 non-TTY whole-batch 调用点。
  - 新增 non-TTY active-turn terminal wait loop，复用现有
    `_InteractiveAcceptedRunState`、single `cancel_reason`、
    `_request_interactive_cancel` 与 `_start_interactive_cancel_task`。
  - 第一次 SIGINT 只登记一次 graceful cancel；pre-accept 时保留 canonical
    submit waiter，等待 exact accepted Run id 后再启动 canonical cancel waiter。
  - 第二次 SIGINT 只登记 terminal 后返回 `130`；第三次及后续信号不重复发
    cancel。正常 SIGINT 路径始终等待 submit/cancel canonical terminal，随后
    render、推进 cursor，并由 invocation 外层关闭 monitor、display 与
    attachment。
  - `TOGGLE_ACTIVITY` 只调用 display toggle，不再写 exit/idle/cancel state。
  - `_request_interactive_cancel` 的 composer 参数只为 non-TTY 变为显式可选；
    TTY 行为保持原样。
- `dayu/engine/contracts/runner_identity.py`
  - 共享非空 validator 增加显式 `owner_name` 参数。
  - request 与 successful response 分别传入自己的稳定 owner 名；schema、
    dataclass 字段、构造参数与 wire shape 不变。

### Owner-level tests

- `tests/cli/test_interactive_command.py`
  - 证明 non-TTY pre-accept 单次 SIGINT 不取消 submit、不留 orphan，acceptance
    后只发一次 graceful cancel，并按 CANCELLED batch terminal contract 返回。
  - 证明 non-TTY 第二次 SIGINT 后仍等待 Host terminal 与本地 cleanup，再返回
    `130`；第三次不重复 cancel，canonical cancel waiter 未被取消。
  - 证明 Ctrl+T 不清除既有 idle exit pending；既有 active Ctrl+T 显示测试与
    active Ctrl+C lifecycle regression 同时复验。
- `tests/host/test_compaction_terminal.py`
  - 两个 thread-owned 真实 SQLite connection 共用同一 DB 和 production
    `HostTransactionRunner`。
  - winner 在同一 transaction 取得 permit 后由 barrier 暂停；loser 的 SQLite
    trace 明确观察到它已尝试执行 `BEGIN IMMEDIATE`，且在 winner 提交前 future
    未完成。
  - winner 提交唯一 `CONTEXT_COMPACTED` 后，loser 得到
    `CompactionTerminalClosed(COMPACTED)`；fresh owner read 与 EventLog inventory
    都证明 terminal row 恰好一条，未追加 loser 的 failed terminal。
  - 未修改 production compaction owner、锁或 CAS。
- `tests/engine/contracts/test_runner_identity.py`
  - request 空文本错误精确等于
    `RunnerRequestIdentity.<field> must be non-empty`。
  - response provider/model 空文本错误精确等于
    `SuccessfulRunnerResponseIdentity.<field> must be non-empty`。
  - 既有 dataclass field-set 断言继续固定 request/response wire shape。

## Controller correction closure

实现过程中一次 `ruff format` 对既有 wrapping 产生了范围外 churn。根据
controller correction，已只用 `apply_patch` 恢复所有非 A01-A04 必需触及的
既有行格式；没有使用 checkout、reset 或 stash。最终 code/test diff：

- normal：`5 files changed, 646 insertions(+), 23 deletions(-)`；
- whitespace-insensitive：`5 files changed, 645 insertions(+), 22 deletions(-)`。

两者只相差新增代码自身的一行 wrapping；`runner_identity.py` 最终只修改
validator owner 参数与直接调用，`test_compaction_terminal.py` 的既有
helpers/rows/wrapping 均未重排。恢复后没有再次运行 formatter。

## Validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Post-correction focused verification

```bash
pytest \
  tests/cli/test_interactive_command.py::test_interactive_non_tty_single_sigint_crosses_acceptance_barrier_without_orphan \
  tests/cli/test_interactive_command.py::test_interactive_non_tty_second_sigint_waits_terminal_then_returns_130_and_third_is_noop \
  tests/cli/test_interactive_command.py::test_interactive_ctrl_t_preserves_existing_idle_interrupt_intent \
  tests/cli/test_interactive_command.py::test_interactive_ctrl_t_toggles_without_cancel \
  tests/cli/test_interactive_command.py::test_interactive_ctrl_c_first_cancels_second_exits_and_third_is_noop \
  tests/host/test_compaction_terminal.py::test_two_competing_terminal_writers_commit_exactly_one_canonical_terminal \
  tests/engine/contracts/test_runner_identity.py::test_runner_request_identity_rejects_empty_text_fields \
  tests/engine/contracts/test_runner_identity.py::test_successful_response_identity_rejects_empty_provider_or_model \
  -q
```

结果：`12 passed, 3 warnings in 1.50s`。warnings 均来自既有 `edgar` deprecated
imports。

```bash
ruff check \
  dayu/cli/session_execution.py \
  dayu/engine/contracts/runner_identity.py \
  tests/cli/test_interactive_command.py \
  tests/engine/contracts/test_runner_identity.py \
  tests/host/test_compaction_terminal.py
```

结果：`All checks passed!`。本次 correction 后未运行 `ruff format`。

```bash
pyright \
  dayu/cli/session_execution.py \
  dayu/engine/contracts/runner_identity.py \
  tests/cli/test_interactive_command.py \
  tests/engine/contracts/test_runner_identity.py \
  tests/host/test_compaction_terminal.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Affected regression and per-file coverage

```bash
pytest \
  tests/cli/test_interactive_command.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/host/test_compaction_terminal.py \
  tests/engine/contracts/test_runner_identity.py \
  --cov=dayu.cli.session_execution \
  --cov=dayu.host.compaction_terminal \
  --cov=dayu.engine.contracts.runner_identity \
  --cov-report=term-missing --cov-fail-under=0 -q
```

结果：`185 passed, 3 warnings in 8.80s`。

| Production file | Coverage |
|---|---:|
| `dayu/cli/session_execution.py` | 86% |
| `dayu/engine/contracts/runner_identity.py` | 95% |
| `dayu/host/compaction_terminal.py` | 84% |
| Total | 87% |

全部修改 production files 均达到单文件 `>=80%` 目标；A03 没有修改 Host
production owner，但仍记录其 owner coverage。

### Full type, compile, diff and secret checks

```bash
pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
python -m compileall -q \
  dayu/cli/session_execution.py \
  dayu/engine/contracts/runner_identity.py \
  tests/cli/test_interactive_command.py \
  tests/engine/contracts/test_runner_identity.py \
  tests/host/test_compaction_terminal.py
git diff --check
git diff --name-only
git status --short
```

结果：compileall 与 `git diff --check` 通过；tracked diff 精确只有本 artifact
上方列出的五个 allowed code/test files。status 中三份 pre-existing untracked
aggregate review/adjudication artifacts 保持未修改。

```bash
! git diff -- <five-allowed-code-test-files> | \
  rg -n '(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|Authorization:[[:space:]]*Bearer|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|BEGIN[[:space:]]+(RSA|EC|OPENSSH|DSA)?[[:space:]]*PRIVATE KEY)'
```

结果：exit `0`，即新增 tracked diff 对 AWS access-key、provider token、
Authorization/Bearer 与 private-key header 形态均为零命中。没有打印环境变量
值、provider secret 或用户 payload。

## Docs decision

- 根 README 已描述 interactive canonical terminal 等待与 second-Ctrl+C
  exit-after-cancel 契约；本 fix 让 non-TTY active Run 符合既有契约，没有改变
  命令、参数、默认通道、文件位置或工作流，因此不更新。
- Engine README 已描述 `SuccessfulRunnerResponseIdentity` 的既有字段与 wire
  contract；A04 只修错误 owner 文本，不改变该 contract，因此不更新。
- tests README 没有新增测试层级；只补 owner-level cases，因此不更新。
- `dayu/host` production 未修改，Host README 不触发。
- 用户明确禁止修改 README、design、oracle、scenario 与既有 artifact；未发现
  必须越过该边界的直接证据。

## Finding status and residual risks

| Finding | Fix status | Evidence |
|---|---|---|
| `AGG-A01` | 已修复 | pre-accept single SIGINT、double/third SIGINT、canonical waiter 与 cleanup tests；affected suite；pyright |
| `AGG-A02` | 已修复 | toggle 不再写状态；idle pending 与 active display/cancel regression tests |
| `AGG-A03` | 已修复 | 两真实 writer 的 `BEGIN IMMEDIATE` barrier competition；winner permit、loser closed、单 terminal inventory |
| `AGG-A04` | 已修复 | request/response 两类 exact owner-message tests；wire field-set 不变 |

- 四项 accepted finding 均分类为 `fixed in current slice`。
- G01-G07、formal interactive scenarios 与外部 provider smoke 的可复跑性仍按
  aggregate adjudication 分类为 `assigned to later work unit`；本 fix 未修改。
- 当前没有 deferred finding、未分类 residual risk 或 blocking open question。
- aggregate re-review 尚未由独立 reviewer 执行；这是 Gateflow 的下一个 gate，
  不是本 fix owner 可自行宣布通过的结果。

## Completion status

- Aggregate finding fix：完成。
- Validation：通过。
- Commit/push/PR：未执行；遵守用户明确禁止。
- Stash/checkout/reset/rebase：未执行。
- Stop point：按用户要求停在 fix artifact 完成；next entry point 为独立
  aggregate deepreview re-review。
