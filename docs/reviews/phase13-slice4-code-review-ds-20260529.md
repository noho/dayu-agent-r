# Phase 13 Slice 4 Code Review — AgentDS

## Gate

Phase 13 Slice 4 code review：`Public Outbox Read / Drain API And Offline Smoke`。

## 审查范围

- 相对 HEAD 的未提交 diff：`dayu/host/api.py`、`dayu/host/__init__.py`、`dayu/host/open_host.py`、`dayu/host/read_api.py`、`dayu/host/README.md`、`tests/host/test_public_outbox_api.py`、`tests/host/test_public_offline_outbox_smoke.py`、`tests/host/test_package_exports.py`、`tests/host/test_open_host_runtime.py`、`docs/host/implementation-control.md`。
- Implementation artifact：`docs/reviews/phase13-slice4-implementation-codex-20260529.md`。
- 设计真源：`docs/host/design.md`。
- Accepted plan：`docs/host/phase13-audit-tool-trace-outbox-plan.md`。
- 未 diff 但被 Slice 4 依赖的 Slice 3 artifact：`dayu/host/outbox.py`（528 行，无变更）。

## 审查方法

逐条对照 plan 中 Slice 4 的 exact changes / validation rules / 禁止列表，并做 adversarial failure pass（构造反例、边界条件、并发窗口）。不修改文件，不 commit，不 push。

---

## Verdict：PASS

无 blocking finding。23 个 Slice 4 测试全绿，pyright 对变更文件 0 error（仅 3 个预存的 pytest import resolution 环境 noise）。Slice 4 严格只做 additive public Outbox read/drain API，未触碰任何禁止清单。

---

## 逐项审查

### 1. Public API 是否只是 additive read_outbox_terminal_items / drain_outbox_terminal_items

**证据**：
- `Host` Protocol 仅新增 `read_outbox_terminal_items(session_id, request)` 和 `drain_outbox_terminal_items(session_id, request)` 两个方法（api.py:3152-3182）。
- `OpenHostOptions` 无任何字段变更（`git diff HEAD -- dayu/host/api.py | grep OpenHostOptions` 仅命中 `__all__` 中的字面量字符串，未命中任何字段新增）。
- 全仓 `grep -i "wait_final_answer\|get_run_result\|timeline.replay\|payload.reader\|payload_reader" dayu/host/` 无命中。
- 新增 public 类型严格限定为 plan 规定集合：`OutboxTerminalCursor`、`OutboxTerminalItem`、`OutboxTerminalItemsBatch`、`ReadOutboxTerminalItemsRequest`、`DrainOutboxTerminalItemsRequest`、`OutboxTerminalItemState`、`OutboxProjectionStatus` 及两个常量。
- `OutboxSummary` 预存于 Slice 3，Slice 4 未修改其定义。

**结论**：通过。未加入 `OpenHostOptions` 字段、`wait_final_answer`、`get_run_result`、payload reader、timeline replay。

### 2. public read/drain 是否只复用 Slice 3 durable outbox helper 和 projection consumer

**证据**：
- `_ReadOutboxTerminalItemsOperation`（read_api.py:436-465）只调用 `_read_outbox_terminal_items_after`（`dayu.host.durable.outbox` 的 Slice 3 helper），不自行实现查询、identity 推导、watermark 推进。
- `_DrainOutboxTerminalItemsOperation`（read_api.py:468-501）只调用 `_drain_outbox_terminal_items`（同一个 Slice 3 helper），不自行实现 drain state transition。
- item identity / idempotency key 推导完全在 `dayu/host/outbox.py:build_outbox_terminal_item_identity` 中，public 层不重建。
- `catch_up_outbox_terminal_projection`（Slice 3）被 `_catch_up_outbox_terminal_projection_best_effort` 直接调用，public 层不重新实现 `ProjectionRunner` loop。

**结论**：通过。不重复实现 identity / query / drain / watermark 逻辑。

### 3. read/drain 是否先校验 session，error 风格是否一致

**证据**：
- `read_outbox_terminal_items` 和 `drain_outbox_terminal_items` 均先调用 `host._run_read(_RequireSessionExistsOperation(...))` 校验 session 存在（read_api.py:203, 231）。
- `_RequireSessionExistsOperation` 复用已有的 `_require_session_exists` helper，与 `get_session`、`session_live_event_start_cursor`、`read_session_host_events_after` 错误消息与 error code 完全一致：`HostApiError(code=NOT_FOUND, message="Session not found", retryable=False)`。
- closed handle → `HostClosedError`，与所有 handle 方法一致。
- drain idempotency conflict 由 Slice 3 `_drain_outbox_terminal_items` → `record_idempotent_operation` → `HostIdempotencyConflictError`，经 `HostCommandHandle._run_write` → `_map_durable_error` 映射为 `HostApiError(code=IDEMPOTENCY_CONFLICT)`，与 `retry_run`、`resolve_wait` 等现有幂等保护路径一致（command.py:761）。
- request 参数越界校验通过 dataclass `__post_init__` 抛出 `ValueError` / `TypeError`，与 `HostStreamCursor`、`HostEvent` 等现有类型的校验风格一致。

**结论**：通过。

### 4. best-effort catch-up 与 projection_status CAUGHT_UP/LAGGED/FAILED 的语义正确性

**证据**：
- `_read_outbox_projection_state`（read_api.py:616-666）的判定顺序：catchup_error → FAILED → failure row → FAILED → checkpoint < latest_event_sequence → LAGGED → else CAUGHT_UP。
- LAGGED 判定条件：`checkpoint_cursor.event_sequence < _latest_event_sequence(transaction)`，两者均在同一个 read transaction 内读取，一致性有保证。
- 测试 `test_public_outbox_reports_lagged_then_catches_up` 验证了 catch-up 未运行时空结果对应 LAGGED（`lagged.projection_status is OutboxProjectionStatus.LAGGED` 且 `lagged.items == ()`），后续正常 catch-up 后变为 CAUGHT_UP（`caught_up.projection_status is OutboxProjectionStatus.CAUGHT_UP`）。该测试也验证了 LAGGED 不会将空结果误判为"无遗漏"——调用方通过 `projection_status` 区分。
- catch-up failure 不吞掉 durable corruption：`catch_up_outbox_terminal_projection` 内部通过 `ProjectionRunner` 在发生可恢复错误时写 `projection_failure` row，`_read_outbox_projection_state` 会读取该 row 并返回 FAILED。`_catch_up_outbox_terminal_projection_best_effort` 的 `except Exception` 只捕获 catch-up 函数无法自行记录 failure row 的意外异常（如 transaction runner 初始化失败），并将摘要暴露在 batch 的 `projection_error_code` / `projection_error_message` 中。

**adversarial check**：catch-up 在 read transaction 外部运行（read_api.py:204），read transaction 内重新读取 checkpoint 和 latest_event_sequence。catch-up 与 read 之间存在写入竞态窗口——新 terminal event 可能在 catch-up 完成后、read transaction 前写入，导致 read transaction 内 checkpoint < latest 从而被判定为 LAGGED。这是设计的预期行为：下一次 read 会再次 best-effort catch-up 并获取最新 item。不存在数据丢失风险。

**结论**：通过。

### 5. drain 只写 Outbox projection queue/idempotency row

**证据**：
- `_DrainOutboxTerminalItemsOperation` 的写入路径只有 `_drain_outbox_terminal_items`（Slice 3 durable helper），该 helper 的职责是更新 Outbox item 的 `item_state` 列和记录 `drain_request_id` 的 idempotency row。
- 测试 `test_offline_read_and_idempotent_drain_do_not_write_eventlog` 显式对比 drain 前后的 `_eventlog_count`，断言 `after_drain_eventlog_count == before_drain_eventlog_count`。
- 该测试还验证了 replay drain 返回相同 item id（幂等），并且 drain 后的 item 状态为 `DRAINED`。
- drain 的 docstring 和 README 均声明"不写 EventLog，不更新 Run / Attempt"、"不表达 channel delivery success"。

**结论**：通过。

### 6. live watch 去重与 offline smoke 覆盖

**证据**：
- `test_live_first_seen_ids_filter_outbox_duplicate`：live-first attach → watch 获取 terminal → Outbox read 带 `seen_terminal_event_ids=(terminal.event_id,)` → 返回空 items → 无 seen ids 的 unfiltered read 返回该 item。证明 `terminal_event_id` = `dedupe_key` 的对齐关系，且 seen ids 能正确过滤。
- `test_drain_first_second_read_covers_live_attach_window`：drain-first → open live watch → 在 watch 期间 submit 第二个 followup → live 获取 terminal → 第二次 Outbox read（after=drain 的 next_cursor，seen ids 包含 live terminal id）→ items 为空，但 `scanned_watermark >= live_terminal.event_sequence`。证明 Outbox read 确实扫到了该 terminal 但通过 seen ids 过滤了，且 drain-first + second-read 覆盖了 live attach 窗口。
- `watch_session_events` 签名未改：仍不接受 cursor 参数，仍为 live-only。去重协议完全在 Service 层通过 `terminal_event_id` / `dedupe_key` 对齐完成。

**结论**：通过。drain-first / live-first attach 窗口均有覆盖。

### 7. final_answer 残余风险控制

**证据**：
- `_final_answer_from_outbox_json`（read_api.py:744-782）只解析 Outbox row 中的 `final_answer_json` 列——该列由 Slice 3 projection consumer 在构建 row 时从 terminal EventLog inline payload 填充。
- Slice 4 未新增任何 payload reader、未新增 payload descriptor 查询路径、未新增 `get_run_result` 或 `wait_final_answer` 方法。
- 测试 `test_offline_read_and_idempotent_drain_do_not_write_eventlog` 验证了 SUCCEEDED item 携带 `terminal_summary_ref` 和 `terminal_summary_digest`（来自 Outbox row，不是从 payload 实时读取），但未直接验证 `final_answer` 字段——这与 plan 中"final_answer 只在 terminal EventLog payload 已携带内联 final answer 字段时返回"的设计一致。
- `_validate_outbox_terminal_payload` 对 final_answer 的校验是宽松的：SUCCEEDED 时允许 `final_answer=None`，这与文档的"可能为 None"一致。
- Implementation artifact 的 Residual Risks 已正确记录此行风险。

**结论**：通过。未新增 payload reader，未用 final answer 文本做 identity，未把 summary ref 伪装成 payload。

### 8. README 是否只描述当前已实现稳定 API

**证据**：
- README diff 中新增内容：outbox read/drain 的 behavior 描述、projection status caveats、dedup 协议、"projection 失败只影响各自派生能力"边界说明。
- 未出现"未来"、"计划中"、"后续版本"、"TODO"、"暂不支持"等未来设计表述。
- 描述与当前代码行为一致：read 不写 EventLog、不改变 item drain state；drain 只更新 projection queue state；`projection_status != CAUGHT_UP` 时空结果不可解释为无遗漏。

**结论**：通过。

### 9. 编码规范检查

**证据**：
- 中文 docstring：全部新增类、函数、方法均有完整中文 docstring，含参数、返回值、异常说明。
- 严格类型：新增 dataclass 字段无 `Any` / `object`。`read_api.py` 中的 `cast()` 用法均为 JSON 解析后的类型窄化（`cast(JsonValue, json.loads(...))`），与文件内已有 helper 风格一致。
- 无 `hasattr` / `getattr`：`grep hasattr\|getattr dayu/host/read_api.py` 和 `dayu/host/api.py`（outbox 新增区域）均无命中。
- 无魔法字符串扩散：`_PAYLOAD_FIELD_TERMINAL_STATUS`、`OUTBOX_TERMINAL_CONSUMER_ID`、`DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE` 等均为模块级常量或枚举成员；`HostApiErrorCode.IDEMPOTENCY_CONFLICT` 复用已有枚举值。
- 无 God class / function：read 和 drain 各由独立 dataclass operation 承载，projection state 提取为独立 helper，职责清晰。

**结论**：通过。

---

## 非阻塞观察

### NB-1 — `_catch_up_outbox_terminal_projection_best_effort` 的 `except Exception` 过于宽泛

- **位置**：read_api.py:596-613
- **现象**：`catch_up_outbox_terminal_projection` 内部已有自己的 structured failure row 写入（通过 `ProjectionRunner`），但外围的 `except Exception` 会捕获任何从该函数逃逸的异常（包括 transaction runner 初始化失败、数据库 I/O 错误等），并将异常类型名和消息字符串化写入 `_OutboxCatchupError`。
- **影响**：结构化异常类型（如 `HostDurableError`）丢失，Service 调用方只能看到 `projection_error_code="HostDurableError"` 字符串，无法程序化区分 transient I/O failure 和 durable schema corruption。
- **当前缓解**：两类 failure 都会导致 `projection_status=FAILED`；已有的 Outbox items 仍然可读。`ProjectionRunner` 的内部失败已经写入 structured failure row（会被 `read_projection_failure` 读取），外围 catch 只覆盖连 failure row 都无法写入的极端情况。
- **建议**：当前形式不构成 bug，但如果未来需要 programmatic 错误分类，可将 `_OutboxCatchupError` 的 `error_code` 改为 enum 或 structured error type。

### NB-2 — 测试 `test_public_offline_outbox_smoke.py` 直接 import `dayu.host.durable.outbox` 和 `dayu.host.durable.schema`

- **位置**：test_public_offline_outbox_smoke.py:23-24（`from dayu.host.durable.schema import TABLE_EVENT_LOG`）、test_open_host_runtime.py:54（`from dayu.host.durable.outbox import read_outbox_terminal_items_after`）
- **现象**：smoke 测试直接依赖 durable 内部模块来验证 EventLog count 和 Outbox projection row。
- **影响**：这些测试需要 white-box 访问 durable 层来证明"不写 EventLog"和"close flush 写入 Outbox row"。这些是 smoke 测试的合理诉求，但增加了测试与内部实现的耦合。
- **建议**：当前可接受——smoke 测试需要自证明的验证能力。未来如果 durable schema 变更，这些测试需要同步更新。

### NB-3 — `test_public_outbox_api.py` 未覆盖 `seen_terminal_event_ids` 超过 `HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT` 的边界

- **位置**：test_public_outbox_api.py
- **现象**：测试覆盖了 limit=0、limit > max_limit、重复 seen ids、负游标四种参数越界，但未测试 seen ids 数量超额。
- **影响**：`_validate_outbox_read_page_fields` 中有 `len(seen_terminal_event_ids) > HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT` 的校验逻辑（api.py:3021-3024），但缺少对应的测试覆盖。
- **建议**：低优先级补充——该路径的逻辑与 limit 越界同质，风险极低。

---

## 与 Implementation Artifact 的一致性

Implementation artifact 中所声称的 scope、changed files、validation results、coverage notes 和 residual risks 与代码实际状态一致：

- 23 passed 复现通过。
- changed files 列表准确。
- Non-goals 声明（无 `OpenHostOptions` 字段、无 `wait_final_answer`、无 payload reader、无 timeline replay）与 diff 一致。
- Residual risks 的 final_answer 依赖 inline payload 的限制已正确记录。

---

## 风险汇总

| 风险 | 等级 | 处置 |
|------|------|------|
| catch-up 异常类型扁平化 | 低 | 允许；已有 failure row 兜底，字符串化不丢信息 |
| 测试对 durable 内部模块的依赖 | 低 | 接受；smoke 测试需要自证明能力 |
| seen ids 最大长度边界未测试 | 极低 | 可后续补充 |
| catch-up 与 read 之间的写入竞态产生 LAGGED 假阳性 | 预期行为 | 非 bug；下一次 read 自动修复 |

---

## Gate 推进判断

Slice 4 实现严格遵循 plan 的 exact changes、禁止列表和 validation rules。无 blocking finding。建议 controller gate 从 `Phase 13 Slice 4 code review` 推进到下一阶段。
