# Phase 1.5 Log / Runner Diagnostics 迁移计划

本文件是 Phase 1.5 的唯一计划真源，位于 `docs/engine/phase1_5-plan.md`。Phase 1.5 插入在 Phase 1 Runner 与 Phase 2 Agent loop 之间，必须先在 `docs/engine/migration-plan.md` 中作为正式阶段落地。

## Context（为什么要做）

Phase 1 已完成 OpenAI-compatible Runner 的协议归一与终态收口（`AsyncOpenAIRunner`、`SSEParser`、`retry_policy`、`error_classifier`、`http_client`、`non_stream_parser`），但 Runner runtime 完全没有日志：provider 请求、retry 决策、HTTP 错误、协议错误、cancellation、close、SSE `[DONE]`、usage 等运行时边界全部静默。Phase 2 要把 RunnerEvent 提升为 EngineEvent 并接入 Agent loop —— 在那之前必须给 Runner 装上诊断能力，否则 Phase 2 出现 SSE 卡流、provider 503、解码失败等问题都无法定位。

GitHub issue #6 已经把「SSE idle heartbeat / idle timeout」明确挂在 Log 迁移之后再做：idle heartbeat 本质是「chunk 级 idle 触发可观测信号」，没有统一 logger 边界就只能塞进事件契约（污染 RunnerEvent）或裸 print，两者都违反架构约束。

Phase 1.5 的目标是：

1. 引入唯一的 logger 装配入口，作为 Engine 之外可复用的运行时诊断基础设施。
2. 按 OLD 行为给 Phase 1 Runner 补齐运行时边界日志（不改协议契约、不污染事件 data）。
3. 在 Runner byte iterator 层落地 chunk 级 idle timeout + heartbeat 日志，关闭 issue #6。
4. 把 Phase 1.5 写入 `docs/engine/migration-plan.md`，作为 Phase 2 的前置条件。

## 1. Review / 阅读范围

### NEW
- `AGENTS.md`
- `docs/engine/design.md`（搜索 `log/heartbeat/idle`：仅 1 处提到 OLD `AsyncOpenAIRunnerRunningConfig` 承载 `stream_idle_timeout/heartbeat`，未承诺迁移）
- `docs/engine/migration-plan.md`（Phase 0–6 总控未单列 Log 迁移阶段；Phase 1.5 必须正式插入）
- `docs/engine/phase1-runner-old-new-review.md`（第 1 轮）
- `docs/engine/phase1-runner-old-new-round2-review.md` §16.1：明确 idle heartbeat 留待 Phase 2 / Log 迁移完成后再做
- `docs/engine/phase1_5-plan-review.md`（本计划上一轮 review）
- `docs/code_review.md`
- `dayu/engine/runners/openai/{runner,sse_parser,retry_policy,error_classifier,http_client,non_stream_parser,reasoning_protocol,tool_call_aggregator,xml_tag_extractor,cancellation_helpers,payload}.py`
- `dayu/engine/contracts/{runner_events,runner_spec}.py`
- `tests/README.md`、`tests/engine/test_import_boundary.py`、`tests/engine/runners/openai/*`

### OLD 强参考源
- `~/workspace/dayu-agent/dayu/log.py`
- `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `~/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `~/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`
- `~/workspace/dayu-agent/dayu/engine/xml_extractor.py`
- `~/workspace/dayu-agent/dayu/engine/README.md`
- `~/workspace/dayu-agent/tests/engine/test_sse_parser.py`（含 `test_parse_stream_cancels_pending_task_on_early_close`、`test_parse_stream_outer_task_cancel_cleans_inflight_next_chunk_task` 等关键 task 清理回归）

### 仓库现状
- 当前不存在 `dayu/README.md`、`dayu/engine/README.md`，仅根 `README.md` 与 `tests/README.md`。
- GitHub issue #6 仍 OPEN。

## 2. OLD Log 证据摘要

OLD logger 入口：`dayu/log.py` 的 `Log` 单例类 + `LogLevel` + `set_level_from_flags`，是「全局基础设施」。OLD Runner 与 SSE parser 在 runtime 边界各处通过 `Log.{debug,info,warn,error}` 记录诊断信息。

按 Runner runtime 边界归类（async_openai_runner.py 行号为证据）：

| 边界 | 行号 | OLD level | 字段 | 是否值得迁移 |
| --- | --- | --- | --- | --- |
| aiohttp 缺失 | 543 | error | 静态文案 | 否（NEW 已强依赖 aiohttp） |
| Runner 初始化 | 558,568 | verbose | model/endpoint/timeout/idle params | 仅迁一行 DEBUG 指纹（endpoint+model+max_retries+supports_*） |
| 默认 / 调用级 extra payload | 709,1044 | debug | bag keys | 否（NEW 不允许 bag） |
| 工具执行 | 753–934 | debug/warn/info | tool name/args/latency | 否（Runner 不再执行工具，Phase 3 Host 负责） |
| 模型不支持流式 / 工具 | 1037,1069 | warn | — | 否（NEW 由 `RunnerSpec` / payload 收口，无运行时降级） |
| HTTP POST 发起 | 1093 | debug | endpoint+attempt | 是 |
| HTTP 200 | 1115 | debug | attempt | 是 |
| Content-Type 路由 | 1123,1137 | debug | content_type | 是 |
| HTTP 非 200 不可重试 | 1196 | warn | error_code+http_status+attempt | 是（**不**记 body preview） |
| HTTP 非 200 决定重试 | 1213 | info | error_code+http_status+attempt+sleep+retry_after_used | 是 |
| HTTP 非 200 重试耗尽 | 1233 | error | error_code+http_status+attempt+max_retries | 是 |
| 未知 HTTP 状态 | 1247 | warn | http_status | 是 |
| 超时重试 | 1266 | info | attempt+sleep | 是 |
| 超时耗尽 | 1285 | error | timeout_seconds+attempt+max_retries | 是 |
| 网络异常重试 / 耗尽 | 1299,1318 | info/error | exc_type+attempt | 是（不记 str(exc) 全文） |
| 资源 cleanup 失败 | 1332,1356,1372 | error/warn | exc_type | 是 |
| SSE 协议错误 | 1438 | error | error_type | 是（message 已进 RunnerProtocolErrorData） |
| SSE 缺 `[DONE]` | 1459 | warn | full_content_len/n_tool_calls | 是 |
| SSE 全空 choices | 1475 | error | error_type | 是 |
| 工具调用未收 `[DONE]` | 1490,1493 | warn/error | — | 否（已被强类型事件吞掉） |
| 退避 delay 计算 | 1870–1880 | debug | retry_after/delay | 是（在 retry sleep 决策处补 DEBUG） |

OLD `sse_parser.py` 关键证据：

- `_get_stream_idle_heartbeat_sec`（line 395）从 `running_config` 读 heartbeat 周期；`stream_idle_timeout` 是分离参数。
- `parse_stream` 主循环（line 240–306）：跨循环复用 `pending_chunk_task = create_task(__anext__())`；`asyncio.wait({pending, cancellation_waiter}, timeout=heartbeat)`；cancellation 命中 → 取消 pending task → 抛 `EngineCancelledError`，**优先于** idle；timeout 命中 → 仅 `Log.debug` 心跳，**不**抛 idle 异常、**不**生成事件。
- 其余 Log 调用：`saw_choice / multi-choices warning / finish_reason / length / content_filter / tool_calls=None / tool_calls 非列表 / tool_call delta / 末尾残留` 等大多对应 NEW 已经覆盖的 `RunnerProtocolErrorData`，仅保留极少数纯诊断 warn。

OLD 测试证据（必须迁入 NEW 测试计划）：

- `test_parse_stream_cancels_pending_task_on_early_close`（test_sse_parser.py:718）：generator `aclose()` 必须取消 in-flight `__anext__` task。
- `test_parse_stream_outer_task_cancel_cleans_inflight_next_chunk_task`（test_sse_parser.py:799）：外层 `Task.cancel()` 必须不留悬空 read task。

### 协议事实 vs 实现细节

- **协议事实（已是 RunnerEvent）**：`HTTP error code/status/message/attempt/retried`、`protocol error type/message`、`usage`、`done finish_reason` —— log 只复述，不再建第二条真源。
- **诊断辅助（仅 log）**：endpoint、attempt 序号、retry sleep 决策、SSE idle 等待秒数、cancel 触达点、Runner 初始化指纹。
- **不应迁移**：tool 执行相关、模型降级路径、`default_extra_payloads`、`request_id`（NEW 由 Agent/Host 在 EngineEvent 提升时再补）。

## 3. NEW Log 边界判断

硬约束：

1. Log 不是 EngineEvent / RunnerEvent 契约；任何 log 字段不得回流进 `RunnerEventData` / `EngineEventData` / metadata。
2. Engine Runner 仍不得 import Host / Service / UI / fins / trace / ToolExecutor / ToolRegistry。
3. Engine 不得 `import dayu.runtime.log`；只能 `import logging`。Engine Runner **允许** `import dayu.runtime.cancellation`（层中立 runtime 工具）。
3a. `dayu.runtime` 是公共运行时基础设施包，**不得** import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`；后续公共 runtime 能力（重试、idle、deadline、observability）一律优先放在 `dayu.runtime`，避免各层自行实现一套。
4. Logger 不读财报文件、不接触 fins storage。
5. **不记录 provider response body preview**、完整 messages、payload、headers、tool arguments、prompt 片段；只记录 `body_size_bytes`、JSON error type 这类不含敏感载荷的字段。
6. 一律使用参数化 logging（`_LOGGER.info("provider retry status=%s attempt=%s", status, attempt)` 形式），禁止 f-string 拼接昂贵对象或敏感内容。`extra=` 仅用于受控字段名。
7. Log 失败永远不影响 Runner 主路径（不在 Runner 中 try/except log）。
8. Logger 测试默认静默：测试只在 `caplog` 中断言关键诊断字段与级别上下界，不锁日志条数与精确文案。

## 4. 推荐模块结构

### 决策

- 新增公共运行时基础设施包 **`dayu/runtime/`**，本期落地两件事：
  - `dayu/runtime/log.py` —— 唯一 logger 装配入口。
  - `dayu/runtime/cancellation.py` —— 层中立 cancellation wait / race helper（idle wait、retry sleep、HTTP 等阻塞边界共用）。
- `dayu.runtime` 不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，是这些层的下游基础设施。
- Engine Runner 一律使用 stdlib `logging.getLogger(__name__)`，**不** import `dayu.runtime.log`；但**允许** import `dayu.runtime.cancellation`。
- Host / CLI 装配 logger 时 import `dayu.runtime.log.configure`；CLI flag 解析使用 `dayu.runtime.log.set_level_from_flags`。
- 不复用 OLD `Log` 单例 god object，不暴露 `Log.debug/info/warn/error` 别名（否则就是兼容 wrapper）。

### `dayu/runtime/log.py` 接口

```
LogLevel(IntEnum):
    DEBUG = 10
    INFO  = 20
    WARN  = 30
    ERROR = 40

configure(
    *,
    level: LogLevel,
    third_party_overrides: Mapping[str, LogLevel] | None = None,
    configure_root: bool = False,
) -> None

set_level_from_flags(
    *, log_level: str | None, debug: bool, verbose: bool, info: bool, quiet: bool
) -> LogLevel
```

> `verbose=True` 在 `set_level_from_flags` 中映射到 `LogLevel.DEBUG`（OLD `VERBOSE=15` 暂不保留；将来若 CLI 出现明确消费方再补一档，由用户单独确认）。

### `dayu/runtime/cancellation.py` 接口

把现有 `dayu/engine/runners/openai/cancellation_helpers.py` 中的 `await_or_cancel` 与 `_poll_cancellation` / `_cancel_task_and_wait` 内部辅助迁出到 `dayu.runtime.cancellation`，并为 idle wait 场景补一个**带超时**的 race helper，避免 Runner 与未来 Host / Service 各自再实现一套。

公共 API 一律返回**封闭联合**结果，不抛公共取消异常（覆盖 review B2 / I1）：

```
@dataclass(frozen=True, slots=True)
class WaitCompleted(Generic[T]):
    """pending awaitable 正常完成。"""
    value: T

@dataclass(frozen=True, slots=True)
class WaitCancelled:
    """cancellation token 命中。"""
    reason: str | None  # token.cancel_reason()

@dataclass(frozen=True, slots=True)
class WaitTimedOut:
    """timeout 命中（仅 wait_for_or_cancel 可能返回）。"""
    elapsed_seconds: float

WaitOutcome = WaitCompleted[T] | WaitCancelled | WaitTimedOut

async def await_or_cancel(
    awaitable: Awaitable[T], *,
    token: CancellationToken,
    poll_interval_seconds: float = 0.05,
) -> WaitCompleted[T] | WaitCancelled

async def wait_for_or_cancel(
    pending: asyncio.Task[T], *,
    token: CancellationToken,
    timeout_seconds: float | None,
    poll_interval_seconds: float = 0.05,
) -> WaitOutcome[T]
```

要点：

- **task ownership 不同**：
  - `await_or_cancel` **拥有**对 `awaitable` 的所有权——内部用 `asyncio.ensure_future(awaitable)` 把它包成 target task；token 命中时**必须** `target.cancel()` 并 `await` 直至 target task done（吞掉 `asyncio.CancelledError`），再返回 `WaitCancelled`，**禁止**留下后台运行的 target task。awaitable 抛异常时同样保证 target task 已 done。
  - `wait_for_or_cancel` **不拥有** `pending` task：调用方（idle wait 中要跨循环复用 readany task）保留所有权，helper 仅负责 race，不取消 pending；调用方按返回的 `WaitOutcome` 自行决定下一步是否取消 pending（idle 路径的 finally 清理由调用方实现）。
- 内部 cancellation watcher / poller task：两个 helper 在退出前**必须**清理自己创建的 watcher / poller task（pending 完成、token 命中、awaitable 抛异常、timeout、outer cancel 任一路径），不留泄漏。
- 不新增公共取消异常：cancellation 与 timeout 通过封闭结果分支表达；调用方按分支翻译为各自层内部信号。
- cancellation 优先：cancellation 与 timeout 同时命中时 `wait_for_or_cancel` 返回 `WaitCancelled`，不返回 `WaitTimedOut`。
- outer task cancel：`asyncio.CancelledError` 必须**透传**，runtime helper 不吞，确保 `Task.cancel()` 在调用栈任意位置仍生效。
- `_RunnerInterrupted` **不**迁入 `dayu.runtime`：它是 Runner 私有控制流信号，仍留在 `dayu/engine/runners/openai/cancellation_helpers.py`；Runner 看到 `WaitCancelled` 后**自行**抛 `_RunnerInterrupted` 走原终态路径，不污染 Engine 公共契约。

### Logger ownership 规则（覆盖 review I1 / I2）

- `configure()` 默认**只**配置 `logging.getLogger("dayu")` 这个 namespace logger：
  - 设置该 logger 的 level 与 handler。
  - 把该 logger 的 `propagate=False`（避免重复打到 root，避免污染 caplog）。
  - 安装一个 `dayu` 自有 stdout/stderr handler；handler 用唯一 marker 字段标识，重复 `configure()` 时**先移除自有 marker handler 再重新安装**，保证幂等且不堆叠。
  - 不动 root logger，不动其它非 `dayu.*` 应用 logger。
- `configure_root=True` 才允许配置 root logger（仅供 CLI 入口需要 fall-through 时显式选择，默认 False）。
- `third_party_overrides` 只对显式列出的 logger name 生效，仅设置 level，不挂 handler。
- `set_level_from_flags(...)` 解析 CLI flag → 调 `configure(level=..., third_party_overrides=...)`；返回最终 level。

caplog 协作策略（区分两类测试，覆盖 review I2）：

- **未 configure 的 Runner logging 行为测试**（绝大多数 Runner / SSE / idle / no-body-preview 测试）：测试**不**调用 `configure()`，`dayu.*` logger 保持 stdlib 默认 `propagate=True`，pytest `caplog` 在 root 级即可捕获 `dayu.engine.runners.openai.*` 记录。这是 §8 中所有 Runner / SSE 测试的默认前提。
- **`configure()` 自身行为测试**：测试调用 `configure()` 后 `dayu` logger 已 `propagate=False`，root caplog **默认抓不到** `dayu` 记录；测试**显式**对 `dayu` logger 设置 `caplog.set_level(level, logger="dayu")` 或断言自有 marker handler 输出，**不**依赖 root 默认捕获。
- 测试只断言关键诊断字段与级别上下界，不锁日志条数与精确文案（review S2）。

### Engine 侧约定

- 每个 Engine runtime 模块顶部：
  ```
  import logging
  from typing import Final
  _LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
  ```
- logger 名天然为 `dayu.engine.runners.openai.runner` 等模块路径。
- 不引入 `MODULE` 常量、不写自定义 prefix；调用方一律 `_LOGGER.<level>("...", *args, extra=...)`。
- Engine Runner 中现有 `from dayu.engine.runners.openai.cancellation_helpers import await_or_cancel` 改为 `from dayu.runtime.cancellation import await_or_cancel, wait_for_or_cancel, WaitCompleted, WaitCancelled, WaitTimedOut`；`_RunnerInterrupted` 仍由 `cancellation_helpers.py` 持有并由 Runner 在看到 `WaitCancelled` 后翻译。

### 架构测试

- `tests/engine/test_logger_import_boundary.py`：断言 `dayu/engine/**` 不 `import dayu.runtime.log`、不 `from dayu.runtime.log import ...`，只允许 `import logging`；同时断言**允许** `from dayu.runtime.cancellation import ...`。
- `tests/runtime/test_runtime_module_boundary.py`：断言 `dayu/runtime/**` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `tests/runtime/test_runtime_log_no_engine_import.py`：单独锁定 `dayu.runtime.log` 不反向 import 上层。
- `tests/runtime/test_runtime_cancellation_no_engine_import.py`：单独锁定 `dayu.runtime.cancellation` 不反向 import 上层。

## 5. Runner 日志补齐清单

按 NEW 边界，不重复 RunnerEvent 已经表达的字段，**不**记 response body preview / 完整 exception text。日志 level 仅给出**边界建议**，测试不锁定精确 level（review S2）：

| 边界 | 模块 | 建议 level | 字段 | 备注 |
| --- | --- | --- | --- | --- |
| Runner 构造 | `runner.py:__init__` | DEBUG | endpoint, max_retries, default_timeout, supports_streaming, supports_tool_calling, supports_stream_usage | 一次性指纹 |
| `call` 启动 | `runner.py:_call_impl` 入口 | DEBUG | endpoint, stream(options.stream), n_messages, n_tools | 不打印 messages 内容 |
| HTTP POST 发起 | `runner.py:_do_attempt` | DEBUG | endpoint, attempt, body_size_bytes | body 不入 log |
| HTTP 200 | `_do_attempt` 200 分支 | DEBUG | attempt, content_type | 与 SSE/JSON 路由对齐 |
| HTTP 非 200 不可重试 | `_call_impl` 捕获 `_AttemptFailedTerminal` | INFO/WARN | error_code, http_status, attempt | message 已进事件，不重复 |
| HTTP 非 200 决定重试 | `_call_impl` retry 决策 ok | INFO | error_code, http_status, attempt, sleep_seconds, retry_after_used(bool) | |
| HTTP 非 200 重试耗尽 | `_call_impl` retry 决策 fail | WARN/ERROR | error_code, http_status, attempt, max_retries | |
| 网络 / 超时异常 | `_do_attempt` aiohttp.ClientError / TimeoutError | INFO（重试）/ WARN/ERROR（耗尽） | exc_type, attempt | 不记 str(exc) 全文 |
| SSE `[DONE]` | `sse_parser.py` | DEBUG | total_chunks, full_content_len, n_tool_calls, has_usage | |
| Usage 收到 | `sse_parser.py` | DEBUG | prompt/completion/total tokens | |
| SSE 协议错误 | `sse_parser.py` | WARN/ERROR | error_type | message 已进 RunnerProtocolErrorData |
| SSE 缺 `[DONE]` | `sse_parser.py` 终态 | INFO/WARN | full_content_len, n_tool_calls | OLD `1459` |
| 非流式响应解析失败 | `non_stream_parser.py` | WARN/ERROR | reason | |
| Cancellation 命中 | `cancellation_helpers.await_or_cancel` | DEBUG | operation_name | DEBUG 即可，避免取消刷屏 |
| `_RunnerInterrupted` 捕获 | `runner.py:_call_impl` | DEBUG/INFO | attempt | 一次性 |
| `close()` | `runner.py:close` | DEBUG | — | 幂等 |
| Retry sleep | `runner.py:_call_impl` | DEBUG | sleep_seconds, attempt, retry_after_used | OLD `1870-1880` |
| **SSE idle heartbeat** | `runner.py:_iter_response_bytes_with_idle` | DEBUG/INFO | endpoint, attempt, idle_total_seconds | **不要 WARNING**，避免长流式正常等待刷 warn（review S1） |
| **SSE idle hard timeout** | `runner.py:_iter_response_bytes_with_idle` | WARN | endpoint, attempt, idle_total_seconds, idle_timeout_seconds | 紧随其后由 Runner 收口为 `_AttemptFailedRetriable(TIMEOUT)` |

不补：

- 任何 tool execution 相关日志（Phase 3 由 Host 负责）。
- `request_id` 字段（Runner 不发明）。
- payload / headers / response body preview 完整内容。

## 6. Idle heartbeat / Idle timeout 设计草案（issue #6）

### 实现位置（覆盖 review B3）

放在 **Runner 层**：在 `dayu/engine/runners/openai/runner.py` 把现有 `_iter_response_bytes` 拆为：

- `_iter_response_bytes_no_idle(response)` —— 当前实现保持不动，作为 idle 禁用路径。
- `_iter_response_bytes_with_idle(response, attempt)` —— 新增，跨循环复用 pending task + heartbeat / hard idle timeout。

`SSEParser` 保持纯 parser，不接 cancellation token、不抛 retry 异常。Runner 通过 `_select_byte_iterator(response, attempt)` 在 `_do_attempt` 内部按 spec 字段决定走哪条迭代器，再传入 `SSEParser.parse(...)`。这样：

- Runner 仍然是 cancellation token / `_AttemptFailedRetriable` / attempt 的唯一持有者。
- SSE parser 不反向 import Runner 私有异常，不形成循环依赖。

### `RunnerSpec` 字段语义（覆盖 review B4）

新增两个字段，类型与默认值如下：

```
stream_idle_timeout_seconds: float | None = None
stream_idle_heartbeat_seconds: float | None = None
```

合法值规则（在 `RunnerSpec.__post_init__` 中校验，由 contract tests 保证）：

- 二者均为 `None` → idle 完全禁用，走 `_iter_response_bytes_no_idle`。
- `stream_idle_timeout_seconds` 必须为正数（`> 0`）。
- `stream_idle_heartbeat_seconds` 为正数且 `<= stream_idle_timeout_seconds`。
- 允许 **timeout-only**（heartbeat=None, timeout 已设置）：此时 Runner 用 `wait_step = stream_idle_timeout_seconds` 作为单段等待，触发即视为 hard timeout，不发心跳 log。
- 不允许 **heartbeat-only**（heartbeat 已设置但 timeout=None）：构造期 `ValueError`。
- 负数 / 0 / `heartbeat > timeout` 一律构造期拒绝。

### 控制流伪代码

idle wait 直接复用 `dayu.runtime.cancellation.wait_for_or_cancel`，由它统一承担「pending vs cancellation vs timeout」三方 race，Runner 只承担「翻译为 `_RunnerInterrupted` / `_AttemptFailedRetriable` / 继续等」三件事。

```
from dayu.runtime.cancellation import (
    wait_for_or_cancel, WaitCompleted, WaitCancelled, WaitTimedOut,
)

async def _iter_response_bytes_with_idle(
    self, response: aiohttp.ClientResponse, attempt: int
) -> AsyncIterator[bytes]:
    timeout = self._spec.stream_idle_timeout_seconds  # 已保证 > 0
    heartbeat = self._spec.stream_idle_heartbeat_seconds  # 可能为 None
    wait_step = heartbeat if heartbeat is not None else timeout
    idle_total = 0.0
    pending: asyncio.Task[bytes] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(response.content.readany())
            outcome = await wait_for_or_cancel(
                pending, token=self._token, timeout_seconds=wait_step,
            )
            match outcome:
                case WaitCancelled():
                    raise _RunnerInterrupted()
                case WaitTimedOut():
                    idle_total += wait_step
                    if idle_total >= timeout:
                        _LOGGER.warning(
                            "sse idle timeout endpoint=%s attempt=%s "
                            "idle_total=%.1f timeout=%.1f",
                            self._spec.endpoint, attempt, idle_total, timeout,
                        )
                        raise _AttemptFailedRetriable(
                            error_code=RunnerHTTPErrorCode.TIMEOUT,
                            http_status=None,
                            message_text="SSE idle timeout",
                            retry_after_seconds=None,
                        )
                    _LOGGER.debug(
                        "sse idle heartbeat endpoint=%s attempt=%s idle_total=%.1f",
                        self._spec.endpoint, attempt, idle_total,
                    )
                    continue
                case WaitCompleted(value=chunk_bytes):
                    try:
                        # pending 已 done；result() 用于让 task 异常自然抛出
                        chunk = pending.result()
                    except StopAsyncIteration:
                        return
                    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                        raise _AttemptFailedRetriable(
                            error_code=classify_exception(exc),
                            http_status=None,
                            message_text=type(exc).__name__,
                            retry_after_seconds=None,
                        ) from exc
                    pending = None
                    idle_total = 0.0
                    if not chunk:
                        return
                    yield chunk
    finally:
        # 覆盖 generator aclose / 外层 cancel / 双 await 泄漏
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending
```

要点：

- **取消优先**：cancellation 命中必须先 cancel pending → 抛 `_RunnerInterrupted`，**不**走 `_AttemptFailedRetriable`，与现有路径一致（生成器自然终止，不补 RunnerDoneData）。
- **正常 chunk 重置**：`idle_total=0` 在 chunk 到达后重置。
- **finally 清理**：generator `aclose()` / 外层 `Task.cancel()` 时 pending task 必须取消并 await，对齐 OLD `test_parse_stream_*` 回归。
- **timeout 复用 retry**：`_AttemptFailedRetriable(TIMEOUT)` 由 Runner retry loop 决策；与 HTTP timeout 同路径，不增加事件类型。
- **不依赖 SSEParser 取消语义**；SSE parser 保持纯 parser。

### 事件契约

不新增任何 `RunnerEventType` / `EngineEventType`；不新增公共异常（包括 `dayu.runtime` 层）。idle timeout 转换为 `RunnerHTTPErrorData(error_code=TIMEOUT, http_status=None, message="SSE idle timeout", attempt=...)` + `RunnerDoneData(ERROR)` 收口（耗尽时）；可重试时按 retry policy 自然进入下一 attempt。`dayu.runtime.cancellation` 用封闭联合表达 cancel / timeout，不抛公共取消异常。

## 7. 禁止事项

- 禁止把 log 字段塞进 `RunnerEvent.data` / `EngineEvent.data` / metadata。
- 禁止新增 `RunnerEventType` / `EngineEventType`（idle timeout 复用 `TIMEOUT`）。
- 禁止新增公共异常表达 cancel / idle timeout 边界（包括 Engine / Runner / `dayu.runtime` 任一层）：用现有 `_RunnerInterrupted`、`_AttemptFailedRetriable` 与 `dayu.runtime.cancellation` 的封闭联合结果类型；私有异常不得跨 `runners/openai/` 子树外。
- 禁止 `SSEParser` 反向 import Runner 私有异常或 token；idle 必须由 Runner 持有。
- 禁止 Engine 反向 import Host / Service / UI / fins / trace / ToolExecutor / ToolRegistry / `dayu.fins.storage`。
- 禁止 Engine `import dayu.runtime.log`；只能 `import logging`。Engine Runner 允许 import `dayu.runtime.cancellation`。
- 禁止 `dayu.runtime.*` 反向 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- 禁止 logger 在 import 时副作用配置 root logger / handler。
- 禁止 `Any` / `object` / 裸 dict 公共接口。
- 禁止把 OLD `Log` 单例机械搬运为 NEW 兼容 wrapper（包括 `Log.debug` 别名）。
- 禁止 `request_id` 字段在 Runner 层出现。
- 禁止 idle heartbeat 触发任何 Host 状态机或工具执行。
- 禁止把 provider response body preview / 完整 exception 文本 / messages / headers 写入 log。
- 禁止 f-string 直接拼接日志参数；统一参数化 logging。

## 8. 测试计划

新增 / 更新测试（沿用现有 `_factories.py` / `_fakes.py` / `_sse_helpers.py`）。原则：测稳定边界与诊断字段是否出现，**不**锁日志精确级别与精确条数（review S2）。

### Runtime 基础设施
- `tests/runtime/test_log_configure.py`：
  - `configure()` 幂等：连续两次调用不重复挂 handler（统计自有 marker handler 数 = 1）。
  - 默认不修改 root logger（root handlers 不变）。
  - `configure_root=True` 才修改 root，且对应路径有测试。
  - `third_party_overrides={"httpx": LogLevel.WARN}` 只影响该 logger，不挂 handler。
  - `set_level_from_flags` 五路分支返回值。
  - caplog 与 `dayu.engine.*` logger 协作正常。
- `tests/runtime/test_runtime_log_no_engine_import.py`：`dayu.runtime.log` 不 import 上层。
- `tests/runtime/test_runtime_cancellation_no_engine_import.py`：`dayu.runtime.cancellation` 不 import 上层。
- `tests/runtime/test_runtime_module_boundary.py`：`dayu/runtime/**` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `tests/runtime/test_cancellation_await_or_cancel.py`：迁移现有 `tests/engine/runners/openai/` 中针对 `await_or_cancel` 的等价测试到 runtime 层；token 命中返回 `WaitCancelled`、awaitable 异常透传、awaitable 完成返回 `WaitCompleted`、内部 watcher / poller task 在所有路径不泄漏、外层 `Task.cancel()` 透传 `asyncio.CancelledError`；**target task ownership 测试**：token 命中后 helper 内部包装的 target task 必须 `.done()` 为 True 且不再运行（用一个会写入侧信道的长 awaitable 验证：cancel 后侧信道不再被写入），覆盖非 idle 阻塞路径不留后台 task。
- `tests/runtime/test_cancellation_wait_for_or_cancel.py`：cancellation 与 timeout 同时命中时返回 `WaitCancelled`（cancellation 优先）；纯 timeout 返回 `WaitTimedOut(elapsed_seconds=...)`；pending 命中返回 `WaitCompleted(value=...)`；**pending task ownership 测试**：cancellation / timeout 命中时 `pending.done()` 仍为 False（helper 不取消 pending，跨循环复用契约成立）；内部 watcher task 在 pending completed / timeout / cancelled / outer cancel 四种路径均清理；外层 `Task.cancel()` 透传 `asyncio.CancelledError`；`T=None` 时 `WaitCompleted(value=None)` 与 `WaitTimedOut` 不混淆。

### Engine 边界
- `tests/engine/test_logger_import_boundary.py`：`dayu/engine/**` 不 `import dayu.runtime.log`、不 `from dayu.runtime.log import ...`，但**允许** `from dayu.runtime.cancellation import ...`。

### Runner 诊断
- `tests/engine/runners/openai/test_runner_logging_http_error.py`：4xx 不可重试 / 5xx 重试耗尽场景下，对应 logger（`dayu.engine.runners.openai.runner`）出现包含 `error_code` / `attempt` 字段的日志记录；不断言精确 level，只断言 `>= INFO`。
- `tests/engine/runners/openai/test_runner_logging_retry.py`：429+Retry-After 决定重试 → 出现包含 `retry_after_used` / `sleep_seconds` / `attempt` 字段的诊断记录。
- `tests/engine/runners/openai/test_runner_logging_protocol_error.py`：SSE 协议错误 → 至少一条记录含 `error_type`；RunnerEvent 流仍按现有契约产出。
- `tests/engine/runners/openai/test_runner_logging_cancellation.py`：cancellation 命中 → `await_or_cancel` 出现 DEBUG 记录、`_call_impl` 出现一次取消捕获记录；RunnerEvent 流自然终止。
- `tests/engine/runners/openai/test_runner_logging_close.py`：`close()` 触发记录；不强求次数。
- `tests/engine/runners/openai/test_runner_logging_no_body_preview.py`：构造非 200 + body 含敏感串，断言任何 `dayu.engine.*` 日志记录 `getMessage()` 与 `args` **不包含** body 串。

### SSE Idle（issue #6）
- `tests/engine/runners/openai/test_sse_idle_disabled.py`：`stream_idle_*=None` → 走 `_iter_response_bytes_no_idle`，行为与现状完全一致（用现有 fake stream 直接复用 Phase 1 测试断言）。
- `tests/engine/runners/openai/test_sse_idle_heartbeat.py`：fake stream 在 heartbeat 周期内无 chunk → 多条 idle heartbeat DEBUG/INFO 记录但**不**触发 timeout；正常 chunk 到达后 idle 计时重置。
- `tests/engine/runners/openai/test_sse_idle_timeout.py`：纯 idle 超过 `stream_idle_timeout_seconds` → `RunnerHTTPErrorData(TIMEOUT)` + `RunnerDoneData(ERROR)`，含 attempt 字段。
- `tests/engine/runners/openai/test_sse_idle_timeout_only.py`：heartbeat=None, timeout 已设置 → wait_step = timeout，超时直接 hard timeout，无 heartbeat log。
- `tests/engine/runners/openai/test_sse_idle_cancel_wins.py`：idle 等待中 token cancel → `_RunnerInterrupted` 优先；无 timeout 事件、无悬空 task。
- `tests/engine/runners/openai/test_sse_idle_retry.py`：idle timeout 视为可重试，retry 后下一 attempt 成功 → 最终 RunnerEvent 序列为成功路径，前一个 attempt 的 idle log 出现。
- `tests/engine/runners/openai/test_sse_idle_pending_task_cleanup_on_aclose.py`：generator `aclose()` 在 idle 等待中触发 → pending readany task 被取消，无 `Task was destroyed but it is pending!` warning（迁自 OLD `test_parse_stream_cancels_pending_task_on_early_close`）。
- `tests/engine/runners/openai/test_sse_idle_pending_task_cleanup_on_outer_cancel.py`：外层 `Task.cancel()` 在 idle 等待中触发 → pending task 干净清理（迁自 OLD `test_parse_stream_outer_task_cancel_cleans_inflight_next_chunk_task`）。

### 契约 / 防回流
- `tests/engine/contracts/test_runner_spec_idle_fields.py`：`RunnerSpec` 字段集合包含两个新字段；非法值（负数 / 0 / `heartbeat > timeout` / heartbeat-only）构造期 `ValueError`；`None+None` 合法。
- `tests/engine/runners/openai/test_runner_event_no_log_pollution.py`：断言 `RunnerEventData` 各子类无 `log_*` / `idle_*` / `heartbeat_*` 字段。
- 现有 `test_runner_only_emits_runner_event.py` / `test_no_extra_payload_bag.py` 不变。

### 验收
- `pytest tests/contracts tests/engine -q` 全绿。
- `pyright` 无新增 / 扩散错误。
- `caplog` 能在测试中捕获 `dayu.engine.runners.openai.*` 日志，不需调 `configure()`。

## 9. README / docs 同步判断

**Phase 1.5 不修改任何 README**。

- 不新建 `dayu/README.md`、`dayu/engine/README.md`。
- 不修改根 `README.md`、`tests/README.md`。
- 仅修改 `docs/` 下的迁移计划真源：`docs/engine/migration-plan.md`（必须更新，见 §10 Q1 与 §11 步骤 1），以及本计划文件 `docs/engine/phase1_5-plan.md`。
- README 同步统一推迟到 Phase 6（`docs/engine/migration-plan.md` 已规划「文档同步与阶段收口」），按届时真实代码事实一次性同步，避免 Phase 1.5 与 Phase 6 重复维护。
- 在 PR 描述中显式说明：本期未修改 README，全部以代码 + 测试 + `docs/engine/phase1_5-plan.md` 为事实真源。

## 10. 待总控和用户确认的问题

1. **Phase 1.5 写入总控**：是否确认 Phase 1.5 必须写入 `docs/engine/migration-plan.md` 的阶段总览表与详细计划，并把 Phase 2 前置条件改为 Phase 1 + Phase 1.5？（推荐：是。）
2. **`RunnerSpec` 增字段**：是否接受在 `RunnerSpec` 中新增 `stream_idle_timeout_seconds` / `stream_idle_heartbeat_seconds`？非法值是构造期拒绝、配置 adapter 拒绝，还是 Runner 初始化拒绝？（推荐：构造期 `ValueError`，由 contract tests 锁定。）
3. **Idle 实现位置**：是否确认 idle 逻辑放在 Runner byte iterator 层（`_iter_response_bytes_with_idle`），SSEParser 保持纯 parser？（推荐：是。）
4. **`dayu/README.md` / `dayu/engine/README.md` / `tests/README.md` / 根 `README.md`**：Phase 1.5 已锁定**全部 README 不修改、不新建**，统一推迟到 Phase 6 文档同步阶段。本项无需用户进一步选择。
5. **`LogLevel.VERBOSE=15`**：暂不保留；`set_level_from_flags` 中 `verbose=True` 映射到 `LogLevel.DEBUG`。如未来 CLI 出现明确消费方需要中间档位，再单独由用户确认是否引入。
6. **`dayu.runtime.cancellation` 结果类型**：采用封闭联合 `WaitCompleted[T] | WaitCancelled | WaitTimedOut`，不再保留 `OperationCancelled` 公共异常；与「禁止新增公共取消异常」一致。

## 11. 实施步骤草案

1. **更新总控**：在 `docs/engine/migration-plan.md` §4 阶段总览表中新增 Phase 1.5 行，并新增「Phase 1.5 详细计划」章节；把 Phase 2 前置条件改为 `Phase 1 + Phase 1.5`。
2. 落地 `dayu/runtime/__init__.py`、`dayu/runtime/log.py`（`LogLevel`(DEBUG/INFO/WARN/ERROR) + `configure` + `set_level_from_flags`）、`dayu/runtime/cancellation.py`（迁出 `await_or_cancel` + 新增 `wait_for_or_cancel` + 封闭联合 `WaitCompleted` / `WaitCancelled` / `WaitTimedOut`，**不**新增公共取消异常）；加 `tests/runtime/*` 边界与功能测试，含 watcher / pending task 清理与 outer cancel 透传；pyright 通过。
3. 加 `tests/engine/test_logger_import_boundary.py`：先红后绿（含「禁止 import `dayu.runtime.log`、允许 import `dayu.runtime.cancellation`」两条断言）。
4. `RunnerSpec` 扩展 `stream_idle_timeout_seconds` / `stream_idle_heartbeat_seconds` 字段，附 `__post_init__` 校验；加 `tests/engine/contracts/test_runner_spec_idle_fields.py`。
5. 更新 Runner / SSEParser / non_stream_parser 加 `_LOGGER` + 日志清单实现；`dayu/engine/runners/openai/cancellation_helpers.py` 收缩为只持有 `_RunnerInterrupted` 私有信号（**不**保留 `await_or_cancel` 转发，避免兼容 wrapper），Runner 改为直接 `from dayu.runtime.cancellation import await_or_cancel, wait_for_or_cancel, WaitCompleted, WaitCancelled, WaitTimedOut` 并在调用处把 `WaitCancelled` 翻译为 `_RunnerInterrupted`；不改任何已存事件契约。
6. Runner 拆出 `_iter_response_bytes_no_idle` / `_iter_response_bytes_with_idle`，按 §6 实现 chunk 级 idle timeout + heartbeat；保证 cancellation 优先与 finally 清理。
7. 新增日志 / idle 测试集（清单见 §8）；运行 `source .venv/bin/activate && pytest tests/contracts tests/engine -q` 全绿。
8. `pyright` 全量；不允许新增/扩散错误。
9. 同步 `docs/engine/migration-plan.md`：把 Phase 1.5 行写入阶段总览表与详细计划。**不修改任何 README**（根 README / `tests/README.md` / 不新建 `dayu/README.md` / 不新建 `dayu/engine/README.md`）。
10. 在 PR 描述中关闭 GitHub issue #6，说明 idle 字段位置、cancellation 优先策略、不污染事件契约，并显式说明本期不动 README。

## 12. 停止条件

- Phase 1.5 已写入 `docs/engine/migration-plan.md`。
- Engine Runner 全部 runtime 边界已挂上 logger，关键诊断字段在 `caplog` 测试中可见。
- SSE idle timeout / heartbeat 行为已通过 §8 列出的全部测试，包括 timeout-only、disabled、cancel wins、retry、heartbeat 周期、aclose / outer cancel 清理。
- `RunnerEvent` / `EngineEvent` 契约无 log 字段污染（`test_runner_event_no_log_pollution.py` 等绿）。
- Engine 只 import stdlib `logging`，不 import `dayu.runtime.log`；允许 import `dayu.runtime.cancellation`（`test_logger_import_boundary.py` 绿）。
- `dayu.runtime.log.configure()` 幂等、默认不污染 root logger / pytest caplog（`test_log_configure.py` 绿）。
- `dayu.runtime.*` 不反向 import 上层（`test_runtime_module_boundary.py` / `test_runtime_log_no_engine_import.py` / `test_runtime_cancellation_no_engine_import.py` 绿）。
- 日志中无 provider response body preview / 完整 exception text / messages / headers / tool arguments（`test_runner_logging_no_body_preview.py` 绿）。
- pyright 无新增 / 扩散错误。
- README 已按 §9 决策保持不变（不修改、不新建）。
- review Agent 未发现新增反向依赖、god object、`Any`/`object` 逃逸或事件契约污染。
- GitHub issue #6 可关闭。

## Verification

```bash
source .venv/bin/activate
pytest tests/contracts tests/engine -q
pyright
```

并人工核对：

- `rg "import dayu.runtime.log" dayu/engine` → 无结果。
- `rg "from dayu.runtime.log" dayu/engine` → 无结果。
- `rg "from dayu.runtime.cancellation" dayu/engine/runners/openai` → 命中 Runner 的 `await_or_cancel` / `wait_for_or_cancel` / `WaitCompleted` / `WaitCancelled` / `WaitTimedOut` 导入站点。
- `rg "import dayu\\.(engine|host|service|ui|fins)" dayu/runtime` → 无结果。
- `rg "log_|heartbeat_|idle_" dayu/engine/contracts/runner_events.py` → 无结果（事件契约无 log 字段）。
- `rg "stream_idle_" dayu/engine/contracts/runner_spec.py` → 命中 §6 列出的两个字段。
- `rg "_LOGGER" dayu/engine/runners/openai` → 覆盖 §5 全部边界。

## 关键文件清单（实施时修改）

- 新增：`dayu/runtime/__init__.py`、`dayu/runtime/log.py`、`dayu/runtime/cancellation.py`。
- 新增：`tests/runtime/test_log_configure.py`、`tests/runtime/test_runtime_module_boundary.py`、`tests/runtime/test_runtime_log_no_engine_import.py`、`tests/runtime/test_runtime_cancellation_no_engine_import.py`、`tests/runtime/test_cancellation_await_or_cancel.py`、`tests/runtime/test_cancellation_wait_for_or_cancel.py`。
- 新增：`tests/engine/test_logger_import_boundary.py`（同时锁「禁止 import `dayu.runtime.log`、允许 import `dayu.runtime.cancellation`」两条断言）。
- 修改：`dayu/engine/contracts/runner_spec.py`（追加两个可选字段 + `__post_init__` 校验）。
- 修改：`dayu/engine/runners/openai/runner.py`、`sse_parser.py`、`non_stream_parser.py`。
- 修改：`dayu/engine/runners/openai/cancellation_helpers.py` 收缩为只持有 `_RunnerInterrupted` 私有信号；`await_or_cancel` / `_poll_cancellation` / `_cancel_task_and_wait` 迁出到 `dayu/runtime/cancellation.py`，原文件**不**保留转发 wrapper。
- 迁移：`tests/engine/runners/openai/` 中现有针对 `await_or_cancel` 的等价测试随实现迁到 `tests/runtime/test_cancellation_*.py`，原位置只保留 Runner 集成层断言。
- 新增：`tests/engine/contracts/test_runner_spec_idle_fields.py`。
- 新增：`tests/engine/runners/openai/test_runner_logging_*.py`（5 个）、`test_sse_idle_*.py`（7 个）、`test_runner_event_no_log_pollution.py`。
- 同步：`docs/engine/migration-plan.md`（必须）；本计划 `docs/engine/phase1_5-plan.md` 即唯一计划真源。
- **不修改、不新建任何 README**：根 `README.md` / `tests/README.md` 不动；不新建 `dayu/README.md` / `dayu/engine/README.md`；README 同步统一推迟到 Phase 6。
