# Gateflow S2 accepted finding 限定 fix — `wu-cli-interactive-02-conformance-fixes`

## Gate 与状态

- 当前 gate：S2 `fix`
- Finding：`S2-CR-005`
- Finding severity：低
- Finding decision：`accepted`
- Fix status：`已修复`，等待独立 re-review 确认
- 裁决依据：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-rereview2-adjudication-20260801-183315.md`
- 本 artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-fix-20260801-183822.md`
- 下一 gate：S2 `re-review`

本 artifact 只记录限定 fix，不执行 review，不宣称 S2 或 S2-CR-005 已通过 re-review；本轮不
commit、不 push、不进入 S3。

## Scope

本限定 fix 只新增：

- `tests/cli/test_interactive_command.py` 中一个 driver owner test 及其有界 phase barrier helper；
- 本唯一时间戳 fix artifact。

没有修改 production、README、design、registry、oracle 或任何既有 artifact。没有采纳已被
Controller rejected 的 finding 2，也没有增加 seam、fallback、production 注释或兼容分支。

## Owner 动机与第一性原理判断

S2-CR-005 的动机成立。`_drive_interactive_tty_repl` 是 interactive invocation 内
`deferred_exit_code`、current terminal 收口和 sole queued promotion 的唯一语义 owner。当前 Run
为 `LOST` 时，它应先保存 `EXIT_FAILURE`；若已有 accepted sole queued follow-up，则必须复用同一
submit/terminal waiter 将其提升为 current，等 queued canonical terminal 后才返回先前保存的失败码。

原测试只分别证明了无 queued 的 LOST fatal 路径，以及 success/cancel 与 queued 的组合；它们不能
同源证明 LOST 与 queued promotion 同时发生时 deferred failure 不会提前退出或丢失 queued。因此应在
driver owner boundary 补确定性组合测试，而不是修改已具备正确分支的 production。

本 finding 不要求证明 Host durable Run/Attempt 的 nonterminal/terminal 生命周期；现有 controlled
Host 只用于证明 driver 的 accepted queue、promotion、terminal wait 与最终退出组合，不把 fake
冒充真实 Host durable state owner。

## Exact test

新增：
`test_interactive_lost_waits_accepted_sole_queue_terminal_before_failure`

测试复用 `_ControlledInteractiveHost`、`_ScriptedComposer`、submit event-loop barrier 与 Host
terminal barrier，精确证明：

1. composer 依次提交文本 `current` 与 `queued`；
2. 两个请求均为 `FollowupBehavior.QUEUE`，且 `target_run_id is None`；
3. submit count 到达 2 后，sole queued 已 accepted，再向 current `run-1` 发布 `LOST`；
4. composer 第二次进入 `RUNNING` 是 queued 已被 driver promotion 的确定性观测点；
5. queued terminal 发布前 driver 尚未退出；
6. `run-2` terminal 收口后最终返回 `EXIT_FAILURE`；
7. 全程只有两个 submit、没有重复 submit，也没有任何 cancel request。

新增 `_wait_for_phase_call_count` 只按最多 1,000 个 event-loop ticks 检查 owner state；它使用
`asyncio.sleep(0)` 让出调度，不使用固定时长 sleep 作为 barrier。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 新增 test

```text
pytest -q -x tests/cli/test_interactive_command.py::test_interactive_lost_waits_accepted_sole_queue_terminal_before_failure
```

结果：`1 passed, 3 warnings`。

### S2 focused

```text
pytest tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_run_keys.py \
  tests/cli/test_runtime_display.py \
  tests/cli/test_interactive_run_view.py \
  tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q -x
```

结果：`141 passed, 3 warnings`。

### Prompt / Fins regressions

```text
pytest -q -x tests/cli/test_prompt_command.py tests/cli/test_fins_commands.py
```

结果：`92 passed, 3 warnings`。

上述 warnings 均为既有 edgartools deprecated-module warnings。

### Full-repository pyright

```text
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 只提示有可用的新版本，不是项目诊断。

### Affected-file lint / format / diff

- `ruff check tests/cli/test_interactive_command.py`：`All checks passed!`
- `ruff format --check tests/cli/test_interactive_command.py`：`1 file already formatted`
- `git diff --check -- tests/cli/test_interactive_command.py`：通过
- 新增测试与 helper 核对：没有固定时长 sleep barrier；没有 `STEER`、cancel 或额外 submit 路径。

## Docs decision

本轮只补 test owner evidence，没有用户可见行为、命令、参数、工作流、分层或 production contract
变化；同时限定边界明确禁止修改 README/design/registry/oracle。因此不更新 README 或其它稳定
文档，本 fix artifact 是唯一新增 durable record。

## Finding 状态

- `S2-CR-005`：`已修复`，等待 re-review；不得在本 artifact 中判定 review pass。
- rejected finding 2：保持 rejected，未修改。
- blocking open question：无。

## Residual risk 与未覆盖项

- 真实 Host durable Run/Attempt 的 nonterminal/terminal 状态不由本 fake 测试证明；这是明确的
  owner boundary，不属于 S2-CR-005 要求。分类：保留给真实 Host / integration owner evidence，
  本轮不伪造、不扩 scope。
- Windows 真实 console 原生 SIGINT delivery 仍由 platform validation owner 覆盖；本 finding
  没有修改该边界。
- S3-S6 尚未进入，分类为 later approved slices；本轮没有实施或宣称关闭。
- 未分类 residual risk：无。

## Completion status

S2-CR-005 的限定 test fix 与要求的验证已完成。下一 gate 固定为 S2 `re-review`；本轮不 commit、
不 push、不进入 S3。
