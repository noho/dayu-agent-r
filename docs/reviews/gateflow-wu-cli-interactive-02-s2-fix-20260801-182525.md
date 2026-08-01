# Gateflow S2 accepted finding fix — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：S2 `fix`
- Finding：`S2-CR-004`
- Finding severity：高
- Finding decision：`accepted`
- Fix status：`已修复`，等待独立 re-review 确认
- Controller adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-rereview-adjudication-20260801-181605.md`
- Next gate：`re-review`
- Artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-fix-20260801-182525.md`

## Scope

本轮只修改：

- `dayu/cli/agent_entrypoint.py`
- `tests/cli/test_interactive_command.py`
- 本 fix artifact

明确未修改 CR-002/003 harness、此前 rejected low findings、Host 生产代码、README、design、
registry、oracle；未进入 S3，未 commit 或 push。

## First-principles judgment and owner

S2-CR-004 动机成立，严重性判断准确。

直接代码事实是：同步 fallback 原先把 `self.notify` 直接安装给 `signal.signal`，而
`notify()` 会在同步 Python signal handler 的调用栈内立即增加 `count` 并调用
`asyncio.Event.set()`。`asyncio.Event` 是事件循环拥有的同步原语；当前代码没有
“`Event.set()` 自动转为 `call_soon_threadsafe`”这一契约，因此不能依赖 CPython 偶然实现
把同步 handler 的重入风险判定为安全。

该语义的唯一 owner 是 `dayu.cli.agent_entrypoint.CliSigintMonitor` 的安装、通知与恢复
边界。interactive consumer 只消费 `count` / `wait_next()`，不应增加 fallback 或重算。

## Owner fix

### 同步 handler 调度边界

- ASYNCIO 模式仍由 `loop.add_signal_handler(SIGINT, self.notify)` 安装，行为不变。
- SYNCHRONOUS fallback 改为安装私有同步 handler；该 handler 不接触
  `asyncio.Event`、`Future` 或 `count`，唯一通知动作是
  `loop.call_soon_threadsafe(self.notify)`。
- `notify()` 仍是事件循环内计数与 event 唤醒的唯一 owner，因此直接测试 monitor 的既有
  调用契约和 ASYNCIO 模式均保持不变。

### 安装与恢复状态

- 调用 `signal.signal` 暴露新同步 handler 前，先完整发布
  `SYNCHRONOUS + captured loop + previous handler`，保证新 handler 一旦可调用即可取得同一
  loop。
- `signal.signal` 安装抛出异常时，立即回滚为
  `NONE + loop=None + previous_handler=None`，随后原样传播 primary error。
- SYNCHRONOUS `close()` 从同一 owner state 恢复 previous handler；恢复成功后与 ASYNCIO
  路径一样清为 `NONE` 并释放 loop / previous 引用。
- 重复 `close()` 继续沿既有 `NONE` 路径成为幂等 no-op；没有采纳此前 rejected 的显式
  early-return low finding。

### 文档

`CliSigintMonitor` 类 docstring 已准确说明 asyncio handler 优先、同步 handler fallback，
以及 fallback 只把通知线程安全地投递回同一事件循环。没有其它重构。

## Tests added

- `test_interactive_sync_sigint_handler_defers_notification_to_loop`
  - 在 `signal.signal` 安装点断言 SYNCHRONOUS mode、loop、previous handler 已完整可见；
  - 先让 `wait_next(0)` 进入等待，再直接调用 installed synchronous handler；
  - handler 返回后、event loop 再次执行前断言 `count == 0` 且 waiter 未完成；
  - 随后断言 `wait_next` 恰好收到一次通知并返回 `1`；
  - 断言 previous handler 恢复、loop 引用清理，第二次 `close()` 不重复恢复。
- `test_interactive_sync_sigint_install_failure_rolls_back_state`
  - 强制同步 `signal.signal` 安装失败；
  - 断言异常原样传播，mode / loop / previous handler 回滚为完整 NONE 状态；
  - 断言失败后的 `close()` 安全。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### S2-CR-004 focused

新同步调度、安装失败回滚、startup fallback、active 三次 SIGINT、直接 notify、ASYNCIO
handler 恢复共 6 项：

```text
6 passed, 3 warnings
```

warnings 均来自既有 edgartools deprecated modules。

### Prompt / Fins regression

```text
pytest -q -x tests/cli/test_prompt_command.py tests/cli/test_fins_commands.py
```

结果：`92 passed, 3 warnings`。

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

结果：`140 passed, 3 warnings`。

### Full-repository type check

全仓 `pyright`：

```text
0 errors, 0 warnings, 0 informations
```

仅有 pyright 自身存在新版本的提示，不是项目诊断。

### Branch coverage

用上述 S2 focused 集合执行 `coverage run --branch`，结果仍为
`140 passed, 3 warnings`：

| 文件 | Stmts | Miss | Branch | BrPart | Coverage |
|---|---:|---:|---:|---:|---:|
| `dayu/cli/agent_entrypoint.py` | 121 | 18 | 24 | 6 | 82% |

满足单文件 `>=80%` 要求；没有加入 pragma、no-cover 或 omit 绕过。

### Lint / format / diff / compile

- 当前 S2 的 9 个 modified production/test files：`ruff check` 全部通过。
- 同一 9 个文件：`ruff format --check` 报告 `9 files already formatted`。
- `git diff --check`：通过。
- `python -m compileall -q dayu/cli tests/cli
  tests/service/test_entrypoint_runtime_interactive_path.py`：通过。

### Safety scan

- 当前 diff 扫描 AWS access key、长 `sk-` token、Authorization Bearer、private-key header
  与长 API-key assignment：零命中。
- `agent_entrypoint.py` diff 扫描 `Any`、`object`、`getattr`、`hasattr`、coverage pragma 与
  `noqa`：零命中。
- 同步 handler 不读取或输出 payload，不访问 Event/Future，不打印环境变量或 secret。

## README / stable docs decision

本轮只修复 CLI 内部 signal 调度安全边界，没有用户可见命令、参数、工作流、输出通道、
分层关系或安装方式变化；同时 Controller 明确禁止修改 README/design/registry/oracle，因此不
更新这些文档。本 fix artifact 是本 gate 唯一新增 durable record。

## Residual risk and uncovered areas

- Windows 真实 console 的原生 SIGINT delivery 本机未验证；同步 fallback 的内部调度、状态
  发布、失败回滚与恢复已由确定性 owner tests 覆盖。分类：assigned to Windows CI / platform
  validation owner，不阻塞本轮 re-review。
- S3-S6 尚未进入，继续由 later approved slices 覆盖；本轮没有实施或宣称关闭这些范围。
- S2-CR-004 owner contract 内没有未分类 residual risk，也没有 blocking open question。

## Completion status

S2-CR-004 的 owner fix、测试与要求的验证均已完成。本 artifact 不执行 review，不宣称
re-review pass，不提交或推送。下一 gate 固定为 `re-review`。
