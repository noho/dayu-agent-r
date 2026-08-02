# WU-CLI-CONFORMANCE-F01-F07 S4/F04 Code-review Fix

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S4 / F04`
- Gate：`code-review fix follow-up`
- Entry HEAD：`25400fbadcdb2768b3a0d5b9834f2ad727de659f`
- 裁决输入：
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-ds.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-controller-adjudication.md`
- 状态：`FIX IMPLEMENTED — 等待两路独立 re-review`

## Root cause 与 owner

问题成立。`_InteractiveSessionAttachmentController` 是 CLI invocation 内 attachment
生命周期引用的 owner；旧实现只在底层 close await 成功后提交 `_closed/current` 状态，
因此 close 抛错时仍保留一个已经尝试关闭、可能部分关闭的 attachment 引用。后续 cleanup
或 mutation 会再次 close 同一对象，违背 exactly-once attempt 与 close-before-open 偏序。

修复保持 Host registry 为 access mode 唯一 owner，不修改 Host production、attachment mode、
composer 或 typed error contract。controller 只在自己的 owner boundary 内先提交本地状态，
再等待底层资源操作。

## Finding 逐项状态

| 来源 / finding | 裁决 | 修复后状态 | 证据 |
|---|---|---|---|
| MiMo-1 / DS-3：`close()` 失败后可再次 close | accepted | `fixed` | `close()` 在任何 await 前设置 `_closed=True`，take-and-clear `current`；底层异常对象原样传播，第二次调用 no-op。新增 exactly-once/state/exception test。 |
| MiMo-2 / DS-1：refresh close 失败留下 stale current | accepted | `fixed` | refresh 在 await close 前 take-and-clear；失败保持 `refresh_required=True`，不 open，outer/future close 不会 double-close；下一次显式 mutation 直接 fresh open。 |
| MiMo-3：close/refresh failure 测试缺口 | accepted | `fixed` | 新增四个 controller owner tests，覆盖 close attempt count、await 前状态、异常 identity、no premature open、close/open failure 与 fresh retry。 |
| DS-2：typed enum 应改用 `==` | rejected-with-reason | `no production change / contract locked` | `reason`、`actual_mode` 继续使用 enum identity 匹配；新增裸字符串被 typed detail owner 拒绝的反例 test，未增加 loose parsing。 |
| MiMo residual：queued + READ_ONLY 独立 test | rejected-as-required-fix | `no action` | 裁决确认当前 mutation waiting 阶段不读取 composer，本 fix 不扩张 slice。 |
| S8 real two-process / PTY risk | classified | `deferred to approved S8` | 本 fix 不改变既有分类，也不生成 S8 evidence。 |

## 实现结果

### Terminal close

`_InteractiveSessionAttachmentController.close()` 现在先提交 terminal 状态，再交出当前
attachment：

1. 已 terminal 时立即 no-op；
2. 在首个 await 前设置 `_closed=True`；
3. take-and-clear `current`；
4. 对交出的 attachment 只发起一次 shielded close；
5. close 的 `BaseException` 不包装、不吞掉，保持原对象向上传播。

因此底层 close 成功、失败或 caller 被取消后，controller 都不会再次把同一对象当成可关闭
current。

### Refresh close/open

`attachment_for_mutation()` 的 refresh 路径在 close await 前 take-and-clear 旧 current。
只有旧 attachment 完整 close 后才调用 `open_fresh()`：

- close 失败：异常原样传播，`current=None`、`refresh_required=True`，本次不 open；
- 调用方随后显式 mutation：旧对象不再 close，只发起 fresh open；
- fresh open 失败：异常原样传播，`current=None`、`refresh_required=True`；
- 再下一次显式 mutation：重新 fresh open；
- fresh open 成功后才发布新 current 并清除 refresh 标记。

未增加后台 poll、后台 retry、原地 promotion 或字符串错误分派。

## 新增 owner tests

`tests/cli/test_interactive_command.py` 新增：

- `test_attachment_controller_close_failure_is_terminal_and_attempted_once`
  - close callback 观察到 await 前 `current=None`、`_closed=True`；
  - 原异常对象传播；
  - 后续 close no-op，旧 attachment 恰好一次 close attempt。
- `test_attachment_controller_refresh_close_failure_retries_with_fresh_open`
  - close 失败时 `current=None`、refresh 保持、open count 为零；
  - 下一次 mutation 不 double-close，只 fresh open。
- `test_attachment_controller_refresh_never_opens_before_close_completes`
  - 用显式 close barrier 证明 close 未完成时 open count 始终为零；
  - close 完整完成后才 open。
- `test_attachment_controller_open_failure_keeps_refresh_for_fresh_retry`
  - open 异常原样传播；
  - 状态保持 `None/refresh=true`；
  - 下一次 mutation 再次 fresh open，旧 attachment 不重复 close。
- `test_session_mutation_detail_rejects_raw_string_enum_values`
  - `reason` 与 `actual_mode` 的裸字符串不能通过 typed detail owner；
  - CLI 不通过 StrEnum `==` 提供下游兼容。

既有真实 Host 双 attachment、same-label owner、Run/EventLog durable count、stable request id、
accepted terminal、EOF 与 outer cleanup tests 保持不变并随 focused suite 通过。

## 验证

### 定向 regression

```bash
source .venv/bin/activate
pytest -q tests/cli/test_interactive_command.py \
  -k 'attachment_controller or session_mutation_detail_rejects_raw_string_enum_values or interactive_read_only'
```

结果：`7 passed, 71 deselected, 3 warnings`。

### Focused pytest 与单文件 coverage

```bash
source .venv/bin/activate
pytest \
  tests/cli/test_run_keys.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py \
  tests/host/test_session_attachment_registry.py \
  -q \
  --cov=dayu.cli.session_execution \
  --cov-report=term-missing
```

结果：`209 passed, 3 warnings in 11.70s`。warnings 均来自既有 `edgar` 依赖
deprecation。`dayu/cli/session_execution.py` 为 `774 statements / 102 missing / 87%`，
满足单文件 `>=80%`。

### Pyright

- focused allowlist：
  `pyright dayu/cli/session_execution.py tests/cli/test_interactive_command.py tests/host/test_session_attachment_registry.py`
  → `0 errors, 0 warnings, 0 informations`。
- full：`python -m pyright` → `0 errors, 0 warnings, 0 informations`。

### Diff、allowlist、index 与 frozen truth

- `git diff --check`：通过。
- tracked diff 仅有原 S4 三个 Python allowlist 文件：
  - `dayu/cli/session_execution.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/host/test_session_attachment_registry.py`
- 本次新增 artifact：
  `docs/reviews/wu-cli-conformance-f01-f07-s4-fix-codex.md`。
- index：为空；未 stage、commit、push 或操作 PR。
- frozen `docs/cli_ci_oracles.json` SHA-256：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- frozen `docs/cli_ci_scenarios.json` SHA-256：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- `docs/cli_ci.md` SHA-256：
  `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`。
- `docs/host/design.md` SHA-256：
  `7bd4059f7f4c43dcc9e6ab1e7a650c950c9724283d568137c3d98f6e4be127a0`。
- working file SHA-256：
  - `dayu/cli/session_execution.py`：
    `20ac23aa2f461f1f8c9feee18ae370ffb2dcf8277efd45bf32b772f8e0592c0a`
  - `tests/cli/test_interactive_command.py`：
    `209f316e938f734959cee26999127541e3f58d0cbff330b46808a9167fd545a0`
  - `tests/host/test_session_attachment_registry.py`：
    `0ccbded6ece8ffdf3efa942340859619787b2da3dde04572900b99720d7da066`

## Docs 与风险

用户明确限制本 fix 只能新增本 artifact，故 README、design、registry 与既有 review /
implementation artifacts 均未修改。修复没有要求改变 Host contract，也没有发现 frozen F04
oracle/scenarios 与 Host design truth 冲突。

剩余已分类风险只有裁决指定由 S8 收敛的真实双进程 PTY/OS 调度 evidence；本 implementation
fix gate 无 blocker。下一入口是两路独立 re-review，本 Agent 不在本轮自我 review。
