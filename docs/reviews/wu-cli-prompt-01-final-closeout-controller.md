# WU-CLI-PROMPT-01 Final Closeout

## Gate

- Work unit：`WU-CLI-PROMPT-01`
- Gate：final closeout
- Controller target：`a629cc84`
- Frozen oracle：`cli.prompt.core-execution@1`
- Verdict：`pass`

## Scope 与冻结输入

- 实现只覆盖已确认的六项 prompt findings，以及 durable submit/caller cancellation
  交接所必需的公共 Service owner 与直接受影响的 shared interactive 验证。
- `init`、独立 process/interactive/context-compaction 语义、Host credential 持久化、
  force-answer/Tool Trace owner 差异、文件系统竞态和事务回滚均未纳入实现。
- `docs/cli_ci_oracles.json` SHA-256 为
  `a25fd728f50f4d3f70197c19b514781c95c56c7f9d96d7c1f5642e217826a77d`；
  `docs/cli_ci_scenarios.json` SHA-256 为
  `ae5523b1d1c229fda46fa3b792c1b4bb7608e12e474bc948bcd96adae01596d4`。
  两个 frozen registry 相对 work-unit base `c9e9faa1` 均无修改。

## Owner-level Closeout

1. cancelled UI 由 `dayu.cli.output` 统一投影为用户可理解文案；Host typed reason
   继续只作为 durable/diagnostic fact。
2. prompt 重复中断由 `dayu.cli.session_execution` 合并为一次 Host cancel 并等待
   canonical terminal；`dayu.service.entrypoint_runtime` 的 acceptance barrier 保证 caller
   cancellation 不能丢失 durable accepted Run，也不能在 Host 明确 rejected 时被后到错误
   覆盖。
3. `dayu.cli.__main__` 与 `dayu.cli.agent_entrypoint` 共同拥有 startup/teardown signal
   lifecycle；公开 console/module 入口共用同一 bootstrap 与 130 exit owner。
4. `dayu.cli.arg_parsing` 拥有完整 logging invocation grammar；
   `dayu.runtime.log` / `log_levels` 拥有 ordinary threshold 与 stream admission。
5. `dayu.cli.errors` / `dayu.cli.main` 在 primary operation 前区分 usage 与日志目的地
   resource failure，缺失父目录 exit 1 且不创建路径。
6. `dayu.cli.arg_parsing.parse_cli_args` 在 argparse 前拒绝 surrogateescape argv，输出
   ASCII-safe 脱敏错误并 exit 2。

没有引入字符串黑名单、兼容 shim、`getattr`/`hasattr` fallback、sleep、CLI 假终态、
SQLite 补写、下游重算或 frozen expected-behavior 修改。

## Tests 与 Coverage

- 全部受影响测试：`1301 passed, 7 skipped, 3 warnings`；三条 warning 均来自第三方
  edgar 弃用提示。
- owner coverage 集合：`172 passed`；`dayu.cli.session_execution` 82%，
  `dayu.service.entrypoint_runtime` 87%。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

## Frozen Real CLI Evidence

最终 target `a629cc84` 的 affected frozen exact replay：

- root：`/Users/leo/workspace/.dayu-cli-ci/prompt-postfix-final2-20260731T125305Z-a629cc84`
- scenarios：321/321 passed，`focused-real-pass`，failures 0
- exit distribution：`47×0 / 1×1 / 261×2 / 12×130`
- observed behavior SHA-256：
  `c132e68dab0e29049845a5c6545ac49bc703cff5fd90f447d235f577713ecabd`
- adjudication SHA-256：
  `e48373e9d2b2c05f2da6343806970d21e0176540e91237b63c15bc1e5b0f92f0`
- binding file SHA-256：
  `09da056dabf5d92e24e0ed163992d21ad0d1c79674a7a16cc35f1355a35acb4b`

所有 accepted cancellation Run/attempt 均为 `cancelled`，包含 canonical
`ATTEMPT_CANCELLED` / `RUN_CANCELLED`；Host instance stopped，runtime lane claim 为 0。
startup/pre-Run、parser misuse、invalid UTF-8 与 missing log parent 场景均未创建不应存在的
业务状态。

默认匿名日志与 P62 实际默认路径补充证据：

- root：`/Users/leo/workspace/.dayu-cli-ci/prompt-postfix-log-supplement-20260731T124500Z-5c33a1dc`
- 17/17 exact invocation；16/16 memory capture；P62 actual owner boundary passed
- report SHA-256：
  `0f82d1846b7b77bc8da392a89323f157589b9f5df964999b74722141f25e96fc`
- binding SHA-256：
  `e5ce51275471394787a88e39550ba901cb7df32a51911048e5713ae223892b9d`
- captured-memory aggregate SHA-256：
  `a23a8241d9559aa8c36d1ddc6097f6ea441e9c97870107f639abddbe36b66e6a`

该补充证据以 observation-only Darwin unlink interposer 复制产品真实匿名
`TemporaryFile` bytes，并通过 exact-byte、nonmatch、missing-input 与 wrong-threshold controls；
不改变 argv、runtime logger 或 unlink 结果。它绑定 `5c33a1dc`，而后续 `a629cc84` 只修改
Service admission、其测试和 tests README；logging/resource owner 文件未变，且最终 321 replay
已在 `a629cc84` 再次通过。

## Reviews 与 PR Scope

- Final independent deepreview：`docs/reviews/code-review-20260731-205900.md`，
  SHA-256 `7e55325fb1729de5c608a62620f0d50e402a397972013cbe18766a0539590e7b`；
  verdict `pass`，无 blocking finding。
- Draft PR #189 已从 `main` retarget 到显式 stacked base
  `codex/prompt-oracle-baseline`（`c9e9faa1`），PR diff 不再混入先前 Fins production work unit。

## Residual Risk

- 匿名默认日志的真实进程 observer 是 Darwin-specific；跨平台 admission 由同一 runtime
  owner tests 覆盖。成功路径没有自然产生 warning/error/critical 正向记录，这三个等级的
  record admission 由 owner-level 单元测试覆盖。
- OS 已创建进程但 Python 尚未执行任何项目 bytecode 的瞬时窗口不由纯 Python owner 控制；
  frozen installed-console 最早 0.05 秒场景及全部 startup scenarios 已通过。若未来把 accepted
  measurement 扩展到 pre-bytecode 窗口，应由 native launcher/distribution 新 work unit 负责；
  当前不扩大范围。
- Draft PR 使用 stacked base；合并前必须先落地该 prerequisite，或在 prerequisite 进入目标分支
  后重新 retarget 并复核 diff identity。

## Final Decision

六项 implementation findings 均已在唯一 owner boundary 修复；frozen expected behavior 未改，
受影响测试、真实 CLI 状态/副作用、完整 pyright、diff check 与独立 deepreview 全部通过。
Gateflow final closeout：`pass`。
