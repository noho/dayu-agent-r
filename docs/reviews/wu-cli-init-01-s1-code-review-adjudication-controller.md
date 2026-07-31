# WU-CLI-INIT-01 S1 Code Review Adjudication

## Gate metadata

- Gate：`code review / fix / re-review`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S1 — CLI public parser contract`
- Base：`aadcd2de`
- implementation artifact：
  `docs/reviews/wu-cli-init-01-s1-implementation-codex.md`
- review artifacts：
  - `docs/reviews/code-review-20260730-145346.md`（AgentDS）
  - `docs/reviews/code-review-20260730-145516.md`（AgentMiMo）
- Artifact path：
  `docs/reviews/wu-cli-init-01-s1-code-review-adjudication-controller.md`

## Findings adjudication

### DS-01 — init 两种 `--config` 位置的 argparse 文案不同

- status：`rejected-with-reason`
- severity：低
- 理由：
  - accepted contract 要求 `init --help` 不展示 `--config`，并要求
    `init --config PATH` 与 `--config PATH init` 都由 parser owner exit 2；当前实现和
    tests 已精确满足。
  - command 后位置由 init subparser 报 unknown option，command 前位置先由顶层
    runtime parser 接受全局 option、再按已解析 command 报 init-specific error。这是
    两个真实 parser 层级的如实诊断，不是错误状态或语义漂移。
  - 顶层 usage 展示 `--config` 对其它 runtime commands 是正确 public contract；
    为强行统一文案而给 init 注册隐藏/拒绝 action，会让业务语义上不存在的参数重新进入
    init parser surface，并增加无必要特例。
- re-review：无需代码变更；两路 exit 2、init help absence 与非 init 正向行为的现有
  证据保持有效。

### DS-02 — prompt 缺少 `model_id` 精确断言

- status：`证据失效`
- severity：低
- 理由：`tests/cli/test_prompt_command.py` 的
  `test_prompt_command_outputs_fast_live_terminal_and_converts_requests` 已在当前
  第 1005 行断言
  `captured_requests[0].assembly_overrides.model_id == _MODEL_ID`。该断言是既有测试
  内容，因此没有出现在本 slice diff，但它直接覆盖 reviewer 声称缺失的 contract。
- re-review：无需代码变更；prompt、interactive、session 三个真实 surface 都有
  `ServiceAssemblyOverrides.model_id` 精确断言。

### AgentMiMo

- status：`pass`
- findings：无实质性问题。

## Fix / re-review status

- accepted findings：无。
- fix：`not required`。
- code changes after review：无。
- re-review：Controller 沿 parser 与 session preparation 的同一数据链复核两项
  finding 证据；DS-01 rejected，DS-02 evidence invalidated。
- blocking open questions：无。

## Residual risks

- S2-S6 尚未实施。
  - classification：`covered by later approved slice`
- S1 owner boundary 内无 unclassified residual risk。

## Controller validation

- focused tests：`211 passed`。
- affected-scope pyright：`0 errors, 0 warnings, 0 informations`。
- affected-scope ruff：`All checks passed!`。
- `git diff --check`：通过。

## Gate decision

- code review：`pass`
- fix：`not required`
- re-review：`pass`
- next entry point：`accepted slice commit`
