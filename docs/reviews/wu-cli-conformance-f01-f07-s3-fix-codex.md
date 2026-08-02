# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Code-review Fix 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S3 / F03 — graceful cancel and escape sequences`
- Gate：`code review -> fix`
- Entry HEAD：`fc1b494694e585e46e688fecdf76036abee50ade`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- 状态：`FIX COMPLETE — next: controller-dispatched independent dual re-review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3-fix-codex.md`

本 fix 严格消费以下两路 review 与总控裁决，不执行自我 deep review，也不替代后续
MiMo/DS 独立 re-review：

- `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-mimo.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-ds.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-controller-adjudication.md`

## 动机、owner 与 scope

总控已接受 production 设计。直接代码事实是：`TtyRunningKeyMonitor._read_loop()` 在
deadline 已 armed 的情况下若下一轮 fd readable，但 `os.read()` 返回 `b""`，会立即
return；这正落实 accepted plan §5.2(9) 和 §5.3 的 EOF/close owner contract：teardown
不能为了清空 parser 调用 flush，不能把 pending Escape 合成为 cancel。

因此 DS-F01 不成立为 production defect，真实缺口只是 owner test 没有覆盖
“armed deadline + readable EOF”这条分支。本 fix 不改变 parser、decoder、deadline、
typed action、Host cancel/terminal 或 outer cleanup 设计。

本轮实际修改严格只有：

- `tests/cli/test_run_keys.py`
- `docs/reviews/wu-cli-conformance-f01-f07-s3-fix-codex.md`

production、其它 tests、plan、oracle/scenario、registry、design 与 README 均未修改；
未 stage、commit、push 或操作 PR。

## Required fix

在 `tests/cli/test_run_keys.py` 增加确定性 owner test
`test_reader_readable_eof_wins_over_armed_deadline_without_flush`：

1. 第一轮 scripted `select` 返回 readable，`os.read` 返回 standalone `b"\x1b"`，使
   public parser 接收一次 feed 且 deadline armed；
2. 第二轮 clock 精确推进 `0.1s`，`select` 同时返回 readable，`os.read` 返回 EOF
   `b""`；
3. recording public parser 断言 resolution kinds 精确为 `["feed"]`，证明没有 flush；
4. queue action 精确为空，证明 EOF/close 不投递 action、不合成 `CANCEL_RUN`。

测试只扩展现有 `_RecordingVt100Parser` 的 resolution-kind 记录，不建立第二 parser、
不读取 production private state，也不通过 fake 改写 owner 语义。

## Review findings 裁决与 fix 最终状态

下表不重新评审 finding，只落实
`wu-cli-conformance-f01-f07-s3-code-review-controller-adjudication.md` 的逐项裁决。
`最终状态` 对 accepted/rejected findings 使用 Gateflow 固定状态；被总控判定无反例、
错误 scope 或错误 contract 的项记为 `证据失效`。

| 来源 / finding | 总控裁决 | Required action | Fix 最终状态 |
|---|---|---|---|
| MiMo：无实质 finding | `accepted` | 无 production fix；保留其九项 pass evidence | 无 finding，状态不适用 |
| DS-F01：readable EOF + deadline | `rejected-as-code-defect; accepted-as-test-gap` | 不改 production；增加 armed deadline + readable EOF 零 flush/零 action test | `已修复`；production defect 论证为 `证据失效` |
| DS-F02：exit-after-closeout + queued follow-up | `rejected-with-reason` | 无；review 正文已证明 normal path 正确，且引用非 S3 contract | `证据失效` |
| DS-F03：terminal/accepted 同轮 | `rejected-with-reason` | 无；三种 `FIRST_COMPLETED` 集合均已正确收敛 | `证据失效` |
| DS-F04：second signal 保持 CANCELLING | `rejected-with-reason` | 无；正文证明符合 second Ctrl+C intent-only contract | `证据失效` |
| DS-F05：non-TTY outer trim | `rejected-with-reason` | 无；非 S3 引入且 TTY/non-TTY 语义一致 | `证据失效` |
| DS-F06：cleanup-only error 传播 | `rejected-with-reason` | 无；正文证明 primary-vs-cleanup 传播正确 | `证据失效` |
| DS-F07：`_pending_submit` 防御恢复测试 | `rejected-for-current-slice` | 无；没有证据证明 F03 diff 破坏该 contract | `证据失效` |

所有 accepted finding 均已有 fix 状态；不存在 `未修复` 或 `部分修复` finding。

## Open questions / residual risks 裁决

| 来源 | 总控 disposition | 当前状态 / owner |
|---|---|---|
| DS-OQ01 / RR01：paste late continuation 与 EOF | `classified` | EOF test gap fixed in current slice；0.1s late continuation 为 accepted terminal residual，由 later approved S8 real PTY evidence 覆盖 |
| DS-OQ02：thread start restore | `evidence-valid/pass` | 既有 owner test 已覆盖；无需修改 |
| DS-OQ03：多个 Ctrl+T | `rejected-as-risk` | 每个 typed toggle 按输入顺序投递是直接语义；无需修改或新增文档承诺 |
| DS-OQ04：Ctrl+D | `rejected-out-of-scope` | reviewer 已证明符合既有 composer 行为；不是 F03 finding |
| DS-RR02：`_pending_submit` | `rejected-for-current-slice` | 同 DS-F07；不扩张本 slice |
| DS-RR03：CANCELLING 期间 Enter | `rejected-out-of-scope` | 引用了错误的非 S3 contract；本 fix 不重新裁决 queued-submit 语义 |

Residual risk 均已分类：当前唯一 accepted test gap 已在本 fix 修复；真实终端分块、
ESC/Alt 固有 ambiguity 与不同 timing 继续由 later approved S8 evidence 覆盖。没有
unclassified residual risk 或 blocking open question。

## Validation

### 单文件 owner test

```bash
source .venv/bin/activate
pytest -q tests/cli/test_run_keys.py
```

结果：`26 passed in 0.08s`。

### 四文件 focused suite 与 coverage

```bash
source .venv/bin/activate
pytest -q \
  tests/cli/test_run_keys.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py \
  --cov=dayu.cli.run_keys \
  --cov=dayu.cli.session_execution \
  --cov=dayu.cli.composer \
  --cov-report=term-missing
```

结果：`183 passed, 3 warnings in 11.31s`；warnings 均为 `edgar` 依赖的既有
deprecation warning。单文件 coverage：

- `dayu/cli/run_keys.py`：`190 statements / 13 missing / 93%`
- `dayu/cli/session_execution.py`：`665 statements / 82 missing / 88%`
- `dayu/cli/composer.py`：`370 statements / 35 missing / 91%`

三者分别通过 `coverage report --include=<exact-file> --fail-under=80`。

### Pyright

- focused production/test allowlist：`0 errors, 0 warnings, 0 informations`；工具另行提示
  可升级 pyright `1.1.409 -> 1.1.411`，不属于类型错误。
- 全仓 `python -m pyright`：`0 errors, 0 warnings, 0 informations`；同一非失败版本提示。

### Integrity 与 frozen registry

- `git diff --check`：通过。
- 两个 registry 的 `python -m json.tool`：通过。
- `docs/cli_ci_oracles.json` SHA-256：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json` SHA-256：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- 两个 registry 的 working-tree status 与 staged path 均为空；Git index 整体为空。

## Docs decision

本 fix 只补 owner test，不改变用户可见入口、运行时 contract、分层或排障方式。用户
明确禁止修改 README/design，accepted plan 也把 aggregate 文档同步留给 S8；因此不
修改 README、design、registry 或 frozen evidence。

## Completion 与下一入口

总控唯一 required test fix、全部 finding disposition 记录和 validation 已完成。工作树
保持未 staged；未 commit、push 或操作 PR。按用户指令在此停止，不执行自我 deep
review。下一合法入口为总控另行派发的 MiMo/DS 两路独立 re-review。
