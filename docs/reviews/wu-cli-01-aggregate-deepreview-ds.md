# WU-CLI-01 Aggregate Deepreview

## Scope

- **Mode**: current changes (aggregate of accepted implementation slices)
- **Branch**: `phase/host-ui-implementation`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-cli-01-aggregate-deepreview-ds.md`
- **Review date**: 2026-06-14
- **Included scope**: WU-CLI-01 S1–S7 accepted implementation commits (`52db520c`, `52bc7032`, `4b28bbe5`, `b784ff5b`, `48a97942`, `0f08a13c`, `35db913e`) plus accepted plan commit `de99831f`，对应 files 为主要代码路径 `dayu/cli/`, `dayu/service/entrypoint_runtime.py`, `dayu/service/host_assembly.py`, `dayu/service/fins_direct.py`, `dayu/runtime/location.py`, `dayu/fins/upload_batch.py`，以及相关 tests 与 README 更新。
- **Excluded scope**: 旧 `dayu-agent` 代码实现；未纳入本 WU 的命令 (`write`, `host`, `sessions`, `runs`, `cancel`, `conv`)；已明确 deferred-with-owner 的 residual risk items (`WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-08`)；review artifact 文风或已 rejected finding；非本轮 scope 的 Host/Engine 内部实现。

### 裁决标准重申

本 WU 迁移旧 `dayu-agent` CLI / Fins 命令的**业务语义、用户可见行为、参数面和 cancel 语义**，并适配当前新的 Service boundary、Fins runtime 与 Host public contracts / API。它不是迁移旧代码实现。不因为没有搬旧 write workflow、旧 host management、旧 provider interactive、旧 migrations、旧 label registry 或旧 Fins helper 实现而给 finding。

### Aggregate review method

本 review 对 S1–S7 全部 accepted slices 做跨 slice 集成走读，而不是重审各 slice 已裁决的单项 finding。主线路径覆盖：

- CLI parser → runner → Service/Host/Fins helper → output/exit code/cancel
- prompt / interactive 全链路：ConfigLoader → ScenePrepare → ToolsDiscovery → Service assembly → Host public API
- Fins direct 全链路：CLI arg → Service helper → Fins runtime → poll/cancel → terminal mapping
- `upload_filings_from`：CLI arg → Fins typed batch helper → CLI 脚本渲染
- `init`：CLI arg → workspace bootstrap → 配置复制 → reset 白名单
- state/cancel/race/error mapping 跨 prompt/interactive/Fins direct

每条路径按真实执行入口逐行走读；findings 必须来自同一执行链路上的直接证据。

---

## Findings

### 1. 未修复-中-`_close_watcher` 在 task cancellation 穿透 finally 时无法保证 drain_task 回收

- **入口/函数**: `submit_entrypoint_turn_and_wait` / `cancel_entrypoint_run_and_wait` → `_close_watcher`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:534-548`
- **输入场景**: 外层 task（prompt 或 interactive 的 submit_task、cancel_task）在 `submit_entrypoint_turn_and_wait` 的 `finally` 块执行期间被取消；`CancelledError` 尚未被 raise，在 `_close_watcher` 的第一个 `await watcher.aclose()`（L543）处被 raise。
- **实际分支**: `_close_watcher` 中 `await watcher.aclose()` 抛出 `CancelledError` → 函数提前退出 → `drain_task.cancel()`（L544）与 `await drain_task`（L545-548）不会执行。
- **预期行为**: `finally` 块中的清理应保证 `drain_task` 被 cancel 并回收，且 `watcher.aclose()` 在 cancelled context 下不应阻断下游资源回收。
- **实际行为**: `drain_task` 未被显式 cancel，仍在后台运行。`watcher.aclose()` 本身也因 `CancelledError` 未完成（底层连接可能未正常关闭）。`drain_task` 最终靠 watcher iterator 结束或 GC 回收，但这是一个无时间保证的软回收。
- **直接证据**:
  - L543 `await watcher.aclose()` 是 `_close_watcher` 中的第一个 `await` 点。若调用方 task 已被 cancel，pending `CancelledError` 在此处 raise。
  - L544 `drain_task.cancel()` 在 L543 之后，不在任何 try/finally 保护下。
  - 调用方（`submit_entrypoint_turn_and_wait` L431-432、`cancel_entrypoint_run_and_wait` L497-498）的 `finally` 块中直接 `await _close_watcher(...)`，也没有对 `_close_watcher` 自身做 cancellation shield。
  - prompt 命令中 `_submit_prompt_turn_handling_sigint` L376 `submit_task.cancel()` 可触发此路径；interactive 中 `_cancel_and_await_task` 同理。
- **影响**: 在 SIGINT → cancel submit_task → finally → `_close_watcher` 这条热路径上，若 `CancelledError` 恰好在 finally 块中的 `watcher.aclose()` 处落地，drain_task 和 watcher 的资源回收不完整。绝大多数情况下 `aclose()` 会成功（watcher 底层是 async generator，`aclose()` 不会阻塞），因此实际触发窗口很窄。但一旦触发，drain_task 会继续尝试从已半关闭的 watcher 读取事件，可能产生无谓的异常日志或短暂的资源占用。
- **建议改法和验证点**: 在 `_close_watcher` 内部用 `try: await watcher.aclose()` + `finally: drain_task.cancel(); await drain_task (suppress CancelledError)` 结构保证 drain_task 清理不受 `watcher.aclose()` 异常影响。或在调用方对 `_close_watcher` 使用 `asyncio.shield()` 阻止 cancellation 穿透。验证：构造 fake watcher 的 `aclose()` 在被 cancel 的 task 中抛出 `CancelledError`，断言 drain_task 仍被 cancel 并回收。
- **修复风险（低）**: 改动限制在 `_close_watcher` 内部，不改变对外语义。需确认 `asyncio.shield` 或 nested try/finally 不会吞掉应传播的非取消异常。
- **严重程度（中）**: 影响 prompt/interactive 取消路径的资源确定性回收；触发窗口窄但属于 finally cleanup 的结构性脆弱。

### 2. 未修复-低-`sigint_monitor.install()` 在 try 块之外，异常路径泄漏 signal handler

- **入口/函数**: `_submit_prompt_turn_handling_sigint` / `_submit_interactive_turn_handling_sigint` / `_wait_for_terminal_handling_sigint`
- **文件(行号)**:
  - `dayu/cli/commands/prompt.py:339`（`install()` 在 try L366 之前）
  - `dayu/cli/commands/interactive.py:460`（`install()` 在 try L487 之前）
  - `dayu/cli/commands/fins.py:540`（`install()` 在 try L545 之前）
- **输入场景**: `install()` 成功注册 signal handler 后，`asyncio.create_task(...)` 或 `observed_sigint_count` 赋值期间抛出异常（极端情况如 MemoryError）。
- **实际分支**: 异常在 try 块之前发生，`finally` 块中的 `sigint_monitor.close()` 不会执行。
- **预期行为**: signal handler 应在所有可能提前退出的路径上被移除。
- **实际行为**: `loop.add_signal_handler(signal.SIGINT, ...)` 保持注册，后续 SIGINT 会被 monitor 的 event 机制捕获但调用方已退出。由于 monitor 实例随函数栈帧销毁，`self._event` 被 GC，后续 SIGINT 触发 `notify()` 时可能访问已析构的 event 对象并抛出难以诊断的错误。
- **直接证据**: 三处命令的 `install()` 调用均在 try 块之前，`close()` 均在 finally 块中，中间存在 `asyncio.create_task` 调用。
- **影响**: 极端异常场景下 signal handler 泄漏；正常流程不受影响。
- **建议改法和验证点**: 将 `install()` 移入 try 块第一行，或将 `close()` 从 finally 提升为涵盖 install-to-close 全段的 context manager (`try: install(); ... finally: close()`)。验证：mock `asyncio.create_task` 在 install 后抛异常，断言 `remove_signal_handler` 被调用。
- **修复风险（低）**: 纯结构调整，不改变成功路径语义。
- **严重程度（低）**: 触发条件极端（`asyncio.create_task` 几乎不失败），但属于 defensive cleanup 的常规缺口。

### 3. 未修复-低-`cancel_entrypoint_run_and_wait` 在 run 已终态时依赖纯 outbox 路径且无超时保护

- **入口/函数**: `cancel_entrypoint_run_and_wait` 初始 `get_run` 已终态分支
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:459-469`
- **输入场景**: `cancel_entrypoint_run_and_wait` 被调用时，目标 Run 已在 Host 侧进入终态（`get_run` 返回 `SUCCEEDED/FAILED/CANCELLED/LOST`）。
- **实际分支**: L459 `_is_terminal_run_status` 为 True → L460 创建空 `queue` → L461 调用 `_wait_for_terminal` → `_wait_for_terminal` 中 `_drain_available_watcher_items` 在空 queue 上立刻返回 None → `get_run` 再确认终态 → `_read_outbox_terminal` 用 `OutboxTerminalCursor(event_sequence=0)` 做初始游标开始扫描 outbox。
- **预期行为**: 应能从 outbox 读取到目标 Run 的 terminal item 并返回；若 outbox projection 持续 `LAGGED` 或 `FAILED`，应在合理时间内向上报告错误。
- **实际行为**: 若 outbox projection 持续 `LAGGED`，`_read_outbox_terminal` 返回 None，`_wait_for_terminal` 的外层循环 `sleep(poll_interval_seconds)` 后重试，无上限。调用方（CLI prompt/interactive）未对 `cancel_entrypoint_run_and_wait` 施加 `asyncio.wait_for` 超时。若 outbox projection worker 永久卡住，该调用永久阻塞。
- **直接证据**:
  - L460 空 queue 路径不 attach watcher，因此 `_wait_for_terminal` 中 live event 分支永远不命中。
  - `_read_outbox_terminal` L742-751：`projection_status == LAGGED` 时返回 None（非错误），外层 while True 循环继续。
  - `_wait_for_terminal` L595 `await sleep(poll_interval_seconds)` 之后无退出条件，形成无限循环。
  - `cancel_entrypoint_run_and_wait` docstring L452-453 声明 caller-owned timeout，但在 prompt `_submit_prompt_turn_handling_sigint` L381 和 interactive `_cancel_run_waiting_for_terminal_or_second_sigint` L636 的调用点均无 `asyncio.wait_for`。
- **影响**: 在 outbox projection 故障的罕见场景下，prompt/interactive 的 SIGINT 取消路径永久阻塞（而非报错退出）。不影响 outbox projection 正常工作的场景。
- **建议改法和验证点**: 在 `_wait_for_terminal` 或 `cancel_entrypoint_run_and_wait` 的空-queue 分支加入最大重试次数或总超时；或在 CLI 层对 cancel 等待施加 `asyncio.wait_for`。验证：fake outbox 持续返回 `LAGGED` 且 `has_more=False`，断言在 N 次重试后抛出 `EntrypointRuntimeError` 或超时退出。
- **修复风险（低）**: 需与 caller-owned timeout 的现有契约保持一致；CLI 层施加超时比修改 Service helper 更不侵入。
- **严重程度（低）**: 需要 outbox projection 故障同时 cancel 路径被触发；双重罕见条件叠加才触发。是 caller-owned timeout 契约在当前 CLI 调用点的未兑现，而非数据一致性问题。

### 4. 未修复-低-`_optional_stripped_text` 在 CLI 三命令与 Fins batch 模块中独立重复实现，语义细节不一致

- **入口/函数**: `_optional_stripped_text`（四个独立定义）
- **文件(行号)**:
  - `dayu/cli/commands/prompt.py:541-552` — 空/空白时 raise `CliCommandUsageError`
  - `dayu/cli/commands/interactive.py:811-822` — 空/空白时 raise `CliInteractiveUsageError`
  - `dayu/cli/commands/fins.py:752-765` — 空/空白时静默返回 `None`
  - `dayu/fins/upload_batch.py:350-363` — 空/空白时静默返回 `None`
- **输入场景**: 用户传入空白字符串作为可选参数值（如 `--filing-date "   "`）。
- **实际分支**: prompt/interactive 命令中：`value.strip() == ""` → raise usage error → exit 2。fins 命令和 upload_batch 中：`value.strip() == ""` → 返回 `None`（静默忽略）。
- **预期行为**: 同一类可选文本参数的校验语义应一致，或至少有明确的分层理由。
- **实际行为**: 同一 CLI 进程中，prompt 命令的 `--fallback-prompt "  "` 报 usage error exit 2，而 fins 命令的 `--filing-date "  "` 静默忽略。用户无法预判哪个参数会报错、哪个会忽略。
- **直接证据**: 四个文件的函数体逐行比对：prompt.py L550-552 和 interactive.py L820-822 对空白字符串 raise，fins.py L762-764 和 upload_batch.py L360-362 对空白字符串返回 None。
- **影响**: 用户可见行为不一致（usage error vs 静默忽略）；未来若需统一校验语义，需在四处同步修改。
- **建议改法和验证点**: 将 `_optional_stripped_text` 提取到 `dayu/cli/` 公共 helper 或 `dayu.runtime`，统一"空字符串 → 报错"或"空字符串 → None"的语义。若各命令对空白字符串的处理确有合理差异，应显式注释说明。S6 已通过 `FINS_UPLOAD_FILE_SUFFIXES` 的收敛证明了公共常量的可行性（suffix allowlist），文本处理同理。
- **修复风险（低）**: 只改变错误处理行为；若统一为"空字符串 → usage error"，可能影响 fins 命令的向后兼容（以前静默忽略的现在报错）。
- **严重程度（低）**: 不造成数据错误或状态不一致，仅影响用户可见的校验行为一致性。

---

## Open Questions

1. **prompt 命令第二次 SIGINT 行为未在 plan 中明确定义**：当前实现中 prompt 命令第一次 SIGINT 后 close monitor 再调用 `cancel_entrypoint_run_and_wait`；此时 signal handler 已移除，第二次 SIGINT 走 Python 默认 `KeyboardInterrupt` → 被 `run_prompt_command` 外层 catch 退出 130。Host cancel request 已发出，但 terminal wait 被中断。是否需要像 interactive 一样为 prompt 提供第二次 SIGINT 本地退出的语义并打印 run id？当前残量风险登记中未见此条目。

2. **`cancel_entrypoint_run_and_wait` 初始 `get_run` 终态分支使用的 `session_id` 可能为 stale**：L457 `run_snapshot = await host.get_run(request.run_id)` 返回的 `session_id` 用于 L463 的 `_wait_for_terminal`。若 Run 在获取 snapshot 后、进入 `_wait_for_terminal` 前被 Host 侧迁移到另一个 session（极端边界场景），outbox read 可能找不到该 Run 的 terminal item。此场景在当前 Host 设计中是否可能发生需要 Host owner 确认。

3. **`upload_filings_from` 的 `--material-forms` 空列表行为**：当前 `generate_upload_batch_plan` 对空 `material_forms` 仅使用默认 filing forms 做识别，不会尝试识别 material 文件。若用户提供了 `--material-forms "10-K"`（Fins batch plan L181 用 material pattern 先在文件上匹配），同一文件可能同时匹配 filing pattern 和 material pattern。由于 material 匹配优先（L168-178 先检查 material），该文件会被归为 material。这是否为预期的优先级策略，plan 中未定义。

---

## Residual Risk

以下风险在当前 WU 中未被消除，需要明确 owner 和后续动作。所有项目均已在 `docs/host/ui-implementation-control.md` 的 Residual Risk 表中登记，此处做 aggregate 确认。

### 行为 parity 类（deferred-with-owner）

| ID | 风险描述 | Owner | 状态 |
|---|---|---|---|
| WU-CLI-01-RR-01 | `--infer` alias inference 当前无 approved Fins boundary | Fins owner | deferred-with-owner |
| WU-CLI-01-RR-02 | `--ci` process snapshot 当前无公共 contract | Fins / tooling owner | deferred-with-owner |
| WU-CLI-01-RR-04 | `upload_filings_from` 文件识别规则可能依赖旧 Fins helper | Fins owner | deferred-with-owner |
| WU-CLI-01-RR-05 | `--thinking`/`--no-thinking` 不是独立布尔开关 | Config / Service owner | deferred-with-owner |
| WU-CLI-01-RR-07 | `upload_filing --action delete` 需 Fins runtime 支持 | Fins runtime owner | deferred-with-owner |

### cancel / signal 类（deferred-with-owner）

| ID | 风险描述 | Owner | 状态 |
|---|---|---|---|
| WU-CLI-01-RR-06 | Fins job cancel 协作式，长事务可能不及时检查 cancel；无 `add_signal_handler` 平台无法提供 durable cancel UX | Fins runtime owner; CLI runtime / cross-platform signal adapter owner | deferred-with-owner |

### observability / UX 类（deferred-with-owner）

| ID | 风险描述 | Owner | 状态 |
|---|---|---|---|
| WU-CLI-01-RR-03 | 旧 debug / trace / duplicate governance flags 无 Host public per-run contract | Host / Service owner | deferred-with-owner |
| WU-CLI-01-RR-08 | `SUCCEEDED` direct command 输出未展示 `result_summary` | CLI / Fins product owner | deferred-with-owner |

### 本轮 aggregate review 新增（低危，建议在后续 CLI hardening 中处理）

| 风险描述 | 影响 | 建议 owner |
|---|---|---|
| `_close_watcher` cancellation 穿透导致 drain_task 非确定性回收（Finding 1） | SIGINT 取消路径上资源回收不完整 | Service owner |
| signal handler install 在 try 外（Finding 2） | 极端异常下 signal handler 泄漏 | CLI owner |
| `cancel_entrypoint_run_and_wait` 纯 outbox 路径无超时（Finding 3） | outbox projection 故障时永久阻塞 | Service owner |
| `_optional_stripped_text` 四份实现语义不一致（Finding 4） | 空白参数校验行为不一致 | CLI owner |

### 测试覆盖缺口（无 owner 残量）

- `dayu/cli/output.py` 覆盖率 88%：`render_prompt_terminal_result` 中 `FAILED` 路径（L68-69）有一个测试覆盖，但 `LOST` 路径的 `cancel_reason` 非 None 分支（L66-67）仅在 mock 中覆盖。非阻塞，现有覆盖已满足 >=80% 门槛。
- `cancel_entrypoint_run_and_wait` 的初始 get_run 已终态 + 空 queue + 纯 outbox 路径在测试中有覆盖（`test_cancel_entrypoint_run_and_wait.py` 中相关用例），但 outbox `FAILED` projection 在该路径上的测试依赖 mock 抛出 `EntrypointRuntimeError`——正确性已验证。
- prompt command 第二次 SIGINT 行为未测试：当前没有 test case 构造"第一次 SIGINT 后、cancel_terminal_wait 期间第二次 SIGINT"场景。非阻塞——当前行为是 KeyboardInterrupt 穿透退出 130。

### 未覆盖的集成路径

以下集成路径在当前测试中未被端到端覆盖（非阻塞，属于已知的 smoke / 集成测试分离原则）：

- 真实 ConfigLoader → ScenePrepare → ToolsDiscovery → Host open 全链路 smoke：仅在 `test_entrypoint_runtime.py` 中 mocked。
- 真实 Fins runtime job start → poll → cancel 全链路：仅在 `test_fins_direct.py` 中 mocked。
- 真实 `init` → `ConfigLoader.load(workspace_config_dir=...)` 验证：`test_init_command.py` 中有覆盖（验证生成的 config 可被加载）。
- 多轮 interactive 中 host session 跨轮复用：`test_entrypoint_runtime_interactive_path.py` 中 mocked 覆盖。

---

## 覆盖范围和未覆盖范围

### 已覆盖

- CLI parser → runner → Service/Host/Fins helper → output/exit code 的完整主链路（mocked Host / Fins runtime）
- prompt / interactive ConfigLoader → ScenePrepare → ToolsDiscovery → Service assembly → Host public API 调用顺序
- Host watcher attach-before-submit 时序
- Fast terminal race（submit 前 terminal 已在 watcher queue）
- Outbox fallback 路径（watcher 无 terminal → `get_run` 终态 → outbox read）
- SIGINT after accepted run → typed `CancelRunRequest` → terminal wait
- Interactive 第二次 SIGINT 本地退出
- Fins direct cancel：第一次 SIGINT → `request_cancel` + 继续 poll；第二次 SIGINT → 本地退出 + 打印 job id
- `upload_filings_from` 目录扫描、识别、脚本生成、空目录报错
- `init` workspace bootstrap、overwrite、reset 白名单、symlink containment、部分复制原子性
- 所有 unsupported legacy flags fail fast（不静默忽略）
- Import boundary：CLI 和 Service 层不导入 `dayu.engine`、`dayu.fins.storage`、Host internals
- pyright：0 errors
- 测试覆盖率：`dayu/cli/` 整体 90%+，`dayu/service/entrypoint_runtime.py` 97%，`dayu/service/fins_direct.py` 92%，`dayu/fins/upload_batch.py` 97%
- README 更新按 AGENTS.md 触发规则执行

### 部分覆盖

- Outbox projection `FAILED` 在 cancel 路径（`cancel_entrypoint_run_and_wait` + 已终态 + 纯 outbox）上的行为：测试通过 mock 验证了 `EntrypointRuntimeError` 抛出——但该路径中的 `_read_outbox_terminal` while True 无限循环（projection `LAGGED`）未在测试中触发超时保护（因为超时是 caller-owned）。
- prompt 命令第二次 SIGINT 路径：无显式测试，行为由 Python 默认 KeyboardInterrupt 语义定义。

### 未覆盖（无 owner 残量）

- 真实网络 / 真实 LLM provider / 真实 SEC 下载的端到端 smoke：按 plan 属于手动或外部依赖 smoke，不在常规 CI 中。
- `cancel_entrypoint_run_and_wait` + outbox `LAGGED` 无限循环的 timeout 保护：caller-owned 但 caller 未兑现。已在 Finding 3 中记录。
- `_close_watcher` cancellation 穿透场景：已在 Finding 1 中记录。

---

## 总评

WU-CLI-01 七个 slice 的集成整体符合 accepted plan 的架构裁决与边界约束：

- CLI 保持 UI adapter 边界，prompt/interactive 全链路经 `ConfigLoader → ScenePrepare → ToolsDiscovery → Service assembly → Host public API`，未直接构造 Engine request 或读取 Host internals。
- Service helper（`entrypoint_runtime`、`fins_direct`）不含 CLI stdout/stderr/argparse/signal handler，可复用于未来 WeChat / GUI。
- Fins direct commands 走 approved Service/Fins boundary，不伪装 Host run，不散落读取 Fins storage，支持 durable cancel。
- `upload_filings_from` 通过 Fins typed batch helper 生成结构化 plan，CLI 只渲染脚本，不启动 job。
- `init` 只做 current-schema filesystem bootstrap，不生成旧 schema、不执行旧 migrations，reset 白名单 + symlink containment + 原子复制防线完整。
- Unsupported legacy flags 统一 fail fast。
- cancel/race 处理精心，watcher attach-before-submit、outbox fallback、SIGINT after accepted run、第二次 SIGINT 的交互语义均按 plan 实现。
- pyright 0 errors，测试覆盖率满足要求，README 更新按触发规则执行。

四项新 finding（一项中危、三项低危）均属结构性防御缺口（cancellation cleanup、signal handler 泄漏、outbox 超时保护、文本校验重复），不构成当前 ship-gate 阻塞，但建议在后续 Service/CLI hardening 中收敛。
