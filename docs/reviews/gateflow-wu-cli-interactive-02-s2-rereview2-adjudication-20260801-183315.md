# Gateflow S2 第二次 re-review 裁决 — `wu-cli-interactive-02-conformance-fixes`

## Gate 状态

- 当前 gate：S2 `re-review`
- 审查基线：`HEAD` 相对当前未提交 S2 workspace diff
- AgentMiMo artifact：`docs/reviews/code-review-20260801-183015.md`
- AgentDS artifact：`docs/reviews/code-review-20260801-183143.md`
- Controller 结论：`FIX_REQUIRED`
- 下一 gate：S2 `fix`
- 本 gate 不 commit、不 push、不进入 S3。

## 独立证据复核

Controller 没有把两路 reviewer 的 PASS 直接当作通过结论，已重新读取 CR004 production
diff、owner tests、两份完整 review artifact，并独立运行同步 fallback 的 startup、active、
direct notify、deferred notify 与 install rollback 五项测试，结果 `5 passed`。

CR004 的 owner 修复成立：同步 `signal.signal` handler 只调用捕获 loop 的
`call_soon_threadsafe(self.notify)`；`SYNCHRONOUS + loop + previous handler` 在安装点前完整
发布；安装异常回滚；`close()` 从同一状态恢复并清理。MiMo 对 Ctrl+J 测试使用了不准确的
测试名，但对应直接测试实际存在且通过，不改变代码结论，也不形成 finding。

## Findings 裁决

### S2-CR-005 — accepted / 低 / F09 LOST terminal 与 sole QUEUE 组合缺少 owner test

- 来源：AgentDS finding 1。
- 直接证据：`dayu/cli/session_execution.py` 在 current terminal 为 `LOST` 时先保存
  `deferred_exit_code=EXIT_FAILURE`，若已有 sole queued follow-up 则先 promote 并等待其
  canonical terminal，之后才返回 deferred failure；现有 LOST 测试只有无 queued 的单轮路径。
- 动机裁决：成立。F09 冻结语义要求 queued follow-up 在“当前 Run terminal 后”恰好执行一次，
  没有排除 LOST；这一分支同时包含 deferred fatal exit，不能只由成功/cancel组合间接证明。
- 修复边界：只在 `tests/cli/test_interactive_command.py` 增加确定性 owner-level test；不得修改
  production、README、design、registry 或 oracle。
- 必须证明：current `LOST` 后已 accepted 的 sole `QUEUE,target_run_id=None` 恰好执行一次；
  queued terminal 收口前 driver 不退出；收口后最终 exit code 为 `EXIT_FAILURE`；无重复 submit、
  无取消 queued Run、无非终态残留。优先复用现有 controlled Host/barrier，不增加新 seam。

### AgentDS finding 2 — rejected / 非 finding

- reviewer 自己的直接代码分析已证明 `_pending_submit` 不承载 draft durability，draft/cursor 由
  `_remember_document` 真源保存；该标记只保护 `accept_submit()` 前置条件。
- 没有 correctness、stability 或 maintainability failure；新增解释性注释不是冻结目标要求，
  在本 work unit 中会产生无收益改动，因此不采纳。

### AgentMiMo findings

- 无实质 finding。

## Validation 与 residual risk

- AgentMiMo：S2 focused `140 passed`，prompt/Fins `92 passed`，pyright 0，ruff/format通过，
  `agent_entrypoint.py` branch coverage 82%。
- AgentDS：S2 focused `140 passed`，pyright 0；其两个低项均由 Controller 逐项裁决。
- Controller CR004 focused：`5 passed, 3 warnings`；warnings 为既有 edgartools deprecation。
- 已分类 residual：Windows 真实 console 原生 SIGINT delivery 仍归 platform validation owner；
  POSIX owner contract 与真实 PTY 已覆盖。S3-S6 尚未进入，归后续 approved slices。
- 未分类 residual risk：无。

## Decision

S2 暂不验收。先由 AgentCodex 仅补 S2-CR-005 的测试证据，再由 AgentMiMo、AgentDS 对完整 S2
diff 同时独立 re-review；双路结论仍需 Controller 再裁决。
