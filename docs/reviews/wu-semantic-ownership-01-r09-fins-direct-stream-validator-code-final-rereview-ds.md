# WU-SEMANTIC-OWNERSHIP-01 / R09 第二轮完整累计 Code Re-Review（AgentDS Final）

## 1. Gate 身份与目标锁

- **身份**：同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R09` 的第二轮完整累计 code re-review；不是新 WU、issue 或 feature。
- **审查目标**：完整 12-path cumulative target，不是只看 README 两行增量。
- **Authority 顺序**：`AGENTS.md` → `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` → `docs/fins/design.md` → `docs/host/design.md` → `docs/engine/design.md` → `docs/tool/design.md` → `docs/ui/design.md` → `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md` → 全部 R09 review/adjudication/fix/controller-validation artifacts。
- **Controller 最新 validation**：`docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-controller-validation.md`，verdict `PASS / READY_FOR_SECOND_DUAL_COMPLETE_CUMULATIVE_CODE_REREVIEW`。

### 1.1 Immutable Target Locks

| lock | value |
|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` |
| 12-path manifest SHA-256 | `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` |
| canonical cumulative binary diff SHA-256 | `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e` |
| Fins README SHA-256 | `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76` (791 lines) |
| staged tree | empty |

### 1.2 12-Path Manifest Content Locks

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |
| `dayu/fins/README.md` | 791 | `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76` |

以上 12 个 content locks 全部与 Controller fix validation 及两路 rereview 锁定值完全一致。

## 2. 实际检查范围

### 2.1 逐文件走读覆盖

每个 12-path target 均已完成完整逐文件走读：

| Path | 覆盖状态 | 走读重点 |
|---|---|---|
| `dayu/fins/direct_stream.py` | **covered** | 完整 261 行状态机、`__anext__`/`aclose`/`terminal_result`/`_raise_primary_after_close`/`_close_source_once`/`_finish_clean_exhaustion` |
| `dayu/fins/direct_events.py` | **covered** | `EVENT_AFTER_RESULT` enum 新增、typed error 构造器、leakage guards 不变 |
| `dayu/fins/ingestion_runtime.py` | **covered** | `download`(L2145-2182)、`preprocess`(L2184-2220)、`upload`(L2222-2259)、`_run_direct_stream`(L2702-2769)、`_run_direct_stream_producer`(L2771-2801) |
| `dayu/service/fins_direct.py` | **covered** | 完整 467 行：protocol、全部 public methods、`_preprocess`、删除确认 |
| `dayu/cli/commands/fins.py` | **covered** | 完整 1057 行：`_run_fins_direct_command_async`、`_raise_primary_after_fins_stream_close`、`_wait_for_terminal_handling_sigint`、`_consume_fins_direct_events`、全部 stream openers |
| `tests/fins/test_fins_direct_stream.py` | **covered** | 完整 742 行：18 个 owner tests、real generator fixture、observation state |
| `tests/fins/test_fins_ingestion_runtime.py` | **covered** | 回归 tests、旧 runtime checker tests 已删除 |
| `tests/service/test_fins_direct.py` | **covered** | 完整 720 行：Service identity/provenance tests、fake runtime 使用 real generator |
| `tests/cli/test_fins_commands.py` | **covered** | 完整 1803 行：CLI owner close tests、provenance tests、presentation tests |
| `dayu/fins/README.md` | **covered** | 完整 791 行：component tree(L439-440)、exact signatures(L192-194)、direct stream contract(L513) |
| `dayu/service/README.md` | **covered** | 完整 42 行：L15 描述 `ValidatedFinsEventStream` pass-through、L35 描述 Fins validator 唯一 ownership |
| `tests/README.md` | **covered** | L149 Service boundary、L196 Fins validator owner tests |

### 2.2 逐审查维度覆盖

| 维度 | 覆盖状态 | 核心证据路径 |
|---|---|---|
| validator 唯一 owner | **verified** | `direct_stream.py` 独占全部三种 protocol error、terminal availability、raw source lifecycle |
| exactly-one-and-last RESULT | **verified** | 状态机 OPEN→RESULT_BUFFERED→RESULT_YIELDED→CLOSED；duplicate/event-after 作为 primary error 关闭 source |
| 关闭/异常/取消优先级 | **verified** | `_raise_primary_after_close` primary identity 不变，cleanup failure 作为 `__cause__` |
| CLI/Service/Runtime consumer 生命周期 | **verified** | CLI `_raise_primary_after_fins_stream_close` + success path `aclose()`；Service 纯 pass-through |
| typed errors | **verified** | 三种 enum literal 只在 `direct_events.py` 定义 + `direct_stream.py` decision |
| provenance | **verified** | `process_filing/material` → runtime always `PREPROCESS`；tests 用 `is` 断言 |
| LLM-facing projection | **verified** | CLI 不 import enum、不读取 `reason.value`、只展示 `exc.message` |
| README | **verified** | exact signatures、component tree、Service/tests README 全部同步 |
| 测试真实性 | **verified** | 全部使用 real `async def` generator + `_RawStreamObservation`/`closed_streams` |
| 安全保留 | **verified** | leakage guards、cancellation、queue backpressure、storage containment 无一修改 |
| deferred scope | **verified** | Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9、R10-R12 零 diff |

### 2.3 Owner/Propagation Scans

```text
# Scan 1: deleted patterns (expected zero)
_exensure_result_event          → 0 hits in Service/CLI/tests
_direct_operation_kind          → 0 hits in CLI
"Fins direct Service stream..." → 0 hits

# Scan 2: protocol error construction in Service/CLI (expected zero)
raise FinsDirectStreamProtocolError → 0 hits in Service/CLI
FinsDirectStreamProtocolErrorKind   → 0 hits in Service/CLI (only in direct_events.py + direct_stream.py)
reason.value                        → 0 hits in Service/CLI

# Scan 3: enum literal location (expected: only direct_events.py + direct_stream.py)
MISSING_RESULT     → direct_events.py:84 + direct_stream.py:209 only
DUPLICATE_RESULT   → direct_events.py:85 + direct_stream.py:143 only
EVENT_AFTER_RESULT → direct_events.py:86 + direct_stream.py:149 only
```

零 violations。

## 3. Prior Findings 精确关闭复核

### 3.1 R09-CR-F01（HIGH）— CLI stream owner 确定性关闭

**状态**：`closed-and-verified`

**直接证据**：

- `dayu/cli/commands/fins.py:246-253`：`_run_fins_direct_command_async` 的异常路径通过 `_raise_primary_after_fins_stream_close`（L255-272）确定性关闭 stream，成功路径通过 L251 `await stream.aclose()` 确定性关闭。
- `_raise_primary_after_fins_stream_close`（L255-272）：关闭失败作为 primary 的显式 `__cause__`（L271），不覆盖 primary identity。
- 测试覆盖：
  - `test_cli_stream_owner_preserves_consumer_error_and_cleanup_cause`（L1172）：log/render 失败 → primary identity + `__cause__ is close_error` + `closed_streams == 1`
  - `test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause`（L1215）：外部 task cancel → `__cause__ is close_error` + `closed_streams == 1`
  - `test_cli_stream_owner_sigint_local_exit_closes_once`（L1317）：SIGINT 本地退出 → `closed_streams == 1`
  - `test_cli_stream_owner_sigint_close_failure_propagates_without_primary`（L1355）：SIGINT + close fail → close error identity + `closed_streams == 1`
  - `test_cli_event_task_drain_deduplicates_same_primary_close_cause`（L1285）：self-cause 去重 → `cleanup_error is None` + `__cause__ is None` + `__context__ is None`

**Controller F01 self-cause/context follow-up**：`_cancel_and_drain_fins_event_task`（L669-697）精确实现了 primary/cleanup 去重（L687-696），测试 `test_cli_event_task_drain_deduplicates_same_primary_close_cause` 覆盖 self-cause 场景。

### 3.2 R09-CR-F02（MEDIUM）— 测试 fake cast

**状态**：`closed-and-verified`

**直接证据**：

- `tests/fins/test_fins_direct_stream.py:40-74`：`_controlled_raw_stream` 是真实 `async def ... -> AsyncGenerator[FinsEvent, None]`，支持 `GeneratorExit`（L67-69）和 `finally`（L71-74）。
- `tests/cli/test_fins_commands.py:417-442`：`_FakeFinsDirectService._raw_stream` 是真实 `async def ... -> AsyncGenerator[FinsEvent, None]`，含 `finally`（L439-442）和取消 cause chaining（L434-438）。
- `tests/service/test_fins_direct.py:165-182`：`_FakeIngestionRuntime._raw_stream` 是真实 `async def ... -> AsyncGenerator[FinsEvent, None]`，含 `finally`（L181-182）。
- 所有三处均使用 production `ValidatedFinsEventStream` 构造器，无 `cast()` 绕过类型契约。

### 3.3 R09-CR-F03（MEDIUM）— 真实 generator finally/cancellation 因果链

**状态**：`closed-and-verified`

**直接证据**：

- `tests/fins/test_fins_direct_stream.py`：全部 18 个 owner tests 使用 `_controlled_raw_stream`（真实 async generator），通过 `_RawStreamObservation` 独立 typed state 验证：
  - `generator_exit_calls`：验证 `GeneratorExit` 注入（duplicate/event-after/close 路径）
  - `finally_calls`：验证 `finally` 执行
  - `next_calls`：验证迭代次数
- 显式/repeated close tests（L566-628）验证 at-most-once 语义。
- cleanup failure chaining tests（L425-494）验证 `primary.__cause__ is close_error`。

### 3.4 R09-CR-F04（LOW）— Fins README exact signatures

**状态**：`closed-and-verified`

**直接证据**：

- `dayu/fins/README.md:192-194`：
  ```
  - `def download(...) -> ValidatedFinsEventStream`
  - `def preprocess(...) -> ValidatedFinsEventStream`
  - `def upload(...) -> ValidatedFinsEventStream`
  ```
  三个 exact signatures 已从旧 `AsyncIterator[FinsEvent]` 更新为 `ValidatedFinsEventStream`。

### 3.5 R09-RR-F01（LOW）— Fins main-component map

**状态**：`closed-and-verified`

**直接证据**：

- `dayu/fins/README.md:439-440`：
  ```
  ├── direct_events.py          # direct 事件、类型化协议错误与结果契约所有者
  ├── direct_stream.py          # ValidatedFinsEventStream 恰好一个且最后一个 RESULT 校验所有者
  ```
  精确两个 R09 stable owner 模块，未扩成所有顶层文件流水账。

## 4. Findings

### 本轮新发现

**未发现实质性问题。**

经过对全部 12 个 target 文件逐行走读、完整状态机路径审查、adversarial failure pass（consumer error、外部取消、SIGINT、cleanup failure、repeated close、premature terminal_result read、empty stream、result-then-error）、semantic ownership drift pass、以及 owner/propagation scans 后，未发现任何 material defect。

### 逐项确认清单

| 检查项 | 结果 | 关键证据 |
|---|---|---|
| validator 是三种 protocol error 唯一构造 owner | **pass** | `direct_stream.py:142-153` 独占 `DUPLICATE_RESULT`/`EVENT_AFTER_RESULT`；`direct_stream.py:209-213` 独占 `MISSING_RESULT` |
| exactly-one-and-last RESULT 由唯一 owner 判定 | **pass** | 状态机 OPEN→RESULT_BUFFERED→RESULT_YIELDED→CLOSED；clean EOF 才 yield buffered RESULT（`_finish_clean_exhaustion` L194-218） |
| 关闭优先级：primary error > cleanup failure | **pass** | `_raise_primary_after_close` L220-240：primary 始终是最终传播对象，cleanup failure 作为 `__cause__` |
| 异常优先级：upstream error/cancel 原 object 传播 | **pass** | `__anext__` L128-129：`except BaseException as primary_error` → `_raise_primary_after_close` |
| 取消优先级：不覆盖 business terminal | **pass** | producer generic exception → bounded failure RESULT 保留（`_run_direct_stream_producer` L2791-2799） |
| CLI 确定性关闭全部路径 | **pass** | 正常/异常/SIGINT/local-exit 四条路径全部覆盖 `aclose()`（见 §3.1） |
| Service 纯 pass-through | **pass** | 全部 public methods 直接 `return self._runtime.xxx(...)`，无包装 |
| CLI 不 import enum / 不读 `reason.value` | **pass** | `fins.py:47` 只 import `FinsDirectStreamProtocolError` class；`fins.py:200-202` 只 catch + `exc.message` |
| provenance：process_filing/material → PREPROCESS | **pass** | runtime `preprocess` 始终传 `FinsOperationKind.PREPROCESS`（L2206-2219）；Service alias 不替换 |
| `terminal_result` 只在 clean exhaustion 后可读 | **pass** | `direct_stream.py:190-192`：`_clean_exhaustion` guard + module-owned safe message |
| raw source close at most once | **pass** | `_source_close_attempted` guard（L255-258） |
| 测试使用真实 async generator | **pass** | 三处 fake 全部 `async def ... -> AsyncGenerator[FinsEvent, None]`（见 §3.2） |
| 旧 runtime checker tests 已删除 | **pass** | `test_direct_stream_missing_result_raises_protocol_error` 等三个旧 node 已不在 test file 中 |
| 旧 `_ensure_result_event` 已删除 | **pass** | `fins_direct.py` 零命中 |
| 旧 `_direct_operation_kind` 已删除 | **pass** | `fins.py` 零命中 |
| README exact signatures 已更新 | **pass** | 三个 exact signatures → `ValidatedFinsEventStream`（见 §3.4） |
| README component tree 已补 | **pass** | `direct_events.py` + `direct_stream.py` 两项（见 §3.5） |
| Service/tests README 已同步 | **pass** | Service README L15/L35；tests README L149/L196 |
| 安全保留无退化 | **pass** | leakage guards、cancellation、queue backpressure、storage containment 零 diff |
| deferred scope 无进入 | **pass** | Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9、R10-R12 零 diff |
| full pyright | **pass** | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff | **pass** | 9 changed Python files `All checks passed!` |
| `git diff --check` | **pass** | 零输出 |
| R09 affected aggregate tests | **pass** | `161 passed, 3 existing warnings` |

### 关于 `assert result is not None`（direct_stream.py:134）的说明

本语句不是 finding。`FinsEvent.__post_init__`（`direct_events.py:339-341`）已验证 `RESULT` 事件必有 `result`。validator 内的 `assert` 只是该 typed invariant 的局部重述，用于帮助静态分析器和读者理解控制流。当前没有产生错误业务结果的反例，不需要修改 validator。

## 5. Open Questions

无。

## 6. Residual Risk

- **Issue 175**（Fins thread-backed 长事务不可物理取消）：仍归 Issue 175。R09 的取消/关闭保证不发布 synthetic terminal 和 late queue event，但不迁移 executor。该风险不是 R09 accepted finding。
- **Python async generator `aclose()` 语义**：`_run_direct_stream` raw bridge 的 `finally` 块在 `aclose()`（GeneratorExit）和正常耗尽时均会执行 `cancellation_state.request_cancel()`。该行为依赖 Python async generator 的标准 `aclose()` → GeneratorExit → `finally` 语义，属于语言级保证。

## 7. 最终 Verdict

**PASS — ZERO MATERIAL FINDING**

R09 完整 12-path cumulative target 经过逐文件走读、完整状态机路径审查、adversarial failure pass、semantic ownership drift pass、owner/propagation scans 以及全部 prior finding closure 复核后，未发现任何 material defect。

Fins validator（`ValidatedFinsEventStream`）是 exactly-one-and-last RESULT 的唯一 owner；Service 与 CLI 是纯机械 consumer；typed errors、provenance、primary/cleanup cause chaining、deterministic close、LLM-facing presentation、README synchronization、test authenticity、security retention 和 deferred scope 全部满足 accepted plan 与 Controller adjudication 的合同要求。

全部 4 个 original findings（R09-CR-F01..F04）和 1 个 rereview finding（R09-RR-F01）均已精确关闭。无新增 finding。

## 8. Artifact 记录

| 属性 | 值 |
|---|---|
| 输出文件 | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-final-rereview-ds.md` |
| 行数 | 本 artifact 正文行数（不含元数据） |
| SHA-256 | 待外部计算 |
| 最终 verdict | `PASS / ZERO MATERIAL FINDING` |
| 审查时间 | 2026-07-17 17:00 CST |
