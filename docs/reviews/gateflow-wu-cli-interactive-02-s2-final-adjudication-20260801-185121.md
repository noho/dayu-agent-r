# Gateflow S2 最终 re-review 裁决 — `wu-cli-interactive-02-conformance-fixes`

## Gate 状态

- 当前 gate：S2 `re-review`
- 审查基线：`HEAD` 相对当前未提交 S2 workspace diff
- AgentMiMo 最终 artifact：`docs/reviews/code-review-20260801-184358.md`
- AgentDS 最终 artifact：`docs/reviews/code-review-20260801-184804.md`
- Controller 结论：`PASS`
- Finding 计数：两路均为 0 个新 finding
- 下一 gate：创建 accepted S2 commit；工作树恢复干净后进入 S3。

## Controller 独立裁决

Controller 已完整读取两份最终 artifact，并重新核对新增 CR005 test、S2 production 状态机、
CR004 signal owner fix 与真实 Host integration；没有把 reviewer 的 PASS 直接当作通过结论。

### S2-CR-005

`test_interactive_lost_waits_accepted_sole_queue_terminal_before_failure` 先等待两个
`QUEUE,target_run_id=None` 请求 accepted，再向 current 发布 `LOST`；composer 第二次进入
`RUNNING` 直接证明 sole queued 已被 promote，queued terminal 前 driver 未结束，terminal 后只
返回保存的 `EXIT_FAILURE`。请求文本、数量、behavior、target 与无 cancel 均有直接断言。barrier
只使用 bounded event-loop ticks，没有固定时长 sleep；fake 只证明 CLI driver owner contract，
没有宣称 durable Host/Attempt 事实。Finding 关闭。

### S2-CR-004

同步 `signal.signal` fallback 只通过捕获 loop 的 `call_soon_threadsafe(self.notify)` 投递；安装点前
完整发布 mode/loop/previous，安装异常回滚，close 从同一状态恢复并清理。最终测试修改没有触碰
production，也没有回归该边界。Finding 关闭。

### F05-F09

- F05：Ctrl+J 与 exact xterm Shift+Enter 插入 LF，普通 Enter 提交；真实 POSIX PTY 同时证明
  exact sequence 与 terminal mode restore。
- F06：non-TTY 从首 byte 到真实 EOF 一次读取，newline 规范化、blank 零 Run、非空单 Run、
  literal `0x04` 数据与非法 UTF-8 稳定脱敏错误均由 owner tests 覆盖。
- F07：standalone Escape 在 active acceptance 前后进入同一 graceful cancel；CSI、Alt、paste
  sequence 不因 ESC prefix 误取消。
- F08：composer Ctrl+C 与 OS SIGINT 共用 single cancel / exit-after-cancel lifecycle；startup、
  pre-accept、active、重复信号与 canonical terminal/cleanup 均有直接证据。
- F09：draft/cursor/type-ahead 保留，active Enter 只创建 sole QUEUE，terminal/Enter 双序恰好一次，
  cancel/LOST 后 accepted queue 均先收口再退出；真实 CLI→Service→Host→worker→SQLite integration
  证明 current/queued Run 与 Attempt 无非终态残留。

## Findings 最终状态

| Finding | 决策 | 最终状态 |
|---|---|---|
| S2-CR-001 unsupported asyncio signal API 缺少同步 fallback | accepted | fixed + re-reviewed |
| S2-CR-002 真实 PTY 依赖固定 sleep且未证明 ordinary Enter | accepted | fixed + re-reviewed |
| S2-CR-003 fake Host 手工 terminal且 stage claim 过宽 | accepted | fixed + re-reviewed |
| S2-CR-004 同步 handler 直接触碰 asyncio Event | accepted | fixed + re-reviewed |
| S2-CR-005 LOST + accepted sole QUEUE 组合缺少直接测试 | accepted | fixed + re-reviewed |
| generation、重复分支、宽联合类型、exit-after SIGINT waiter 等低项 | rejected | 保持 rejected |
| `_pending_submit` 解释性注释建议 | rejected | 保持 rejected |

没有 open finding，没有 accepted-but-unfixed finding。

## 最终 validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

- 两路 reviewer 各自重跑 S2 focused：`141 passed`；prompt/Fins：`92 passed`；pyright 0。
- Controller 独立 affected regression：
  `coverage run --branch -m pytest tests/cli tests/service/test_entrypoint_runtime_interactive_path.py -q`
  → `1113 passed, 7 skipped, 3 warnings`。
- modified production branch coverage：
  `agent_entrypoint.py 82%`、`interactive.py 90%`、`composer.py 92%`、
  `run_keys.py 91%`、`session_execution.py 84%`；均达到 `>=80%`。
- warnings 均为既有 edgartools deprecated-module warnings；7 skip 为既有平台/capability 条件。
- 受影响文件 ruff/format、`git diff --check`、compileall 与 secret/credential pattern scan 已通过；
  没有 `Any`/`object`/`getattr`/`hasattr` 或 coverage suppression 增量。

## Docs decision 与 residual risk

- S2 用户可见 CLI 文档、registry、oracle 与 scenario 的一致性更新按 accepted plan 固定在 S6，
  避免未生成真实 evidence 前写入正式 scenario；当前不机械提前同步。
- 已分类 residual：Windows 真实 console 的 native SIGINT delivery 归 platform validation owner；
  POSIX真实 PTY与同步 fallback owner contract 已覆盖，不阻塞 S2。
- S3-S6 尚未进入，归各自 approved slice，不是 S2 未分类风险。
- 未分类 residual risk：无。

## Decision

S2 达到 accepted slice commit 条件。只在最终静态检查仍通过且 staging scope 精确包含本 S2
production/tests/artifacts 时提交；不 push。提交后自动进入 S3 F10。
