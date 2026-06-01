# WU-DUR-01-02 Slice 3 Code Review - MiMo

## Reviewed Target

- **Diff**: `git diff main -- tests/host/test_durable_concurrency_matrix.py tests/README.md`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`（Slice 3 section）
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice3-codex-20260601.md`

## Conclusion

pass

## Findings

未发现实质性问题。

逐项审查结果：

### Idempotency same scope/key/same digest multiprocess

- 文件 start gate 保证 4 个 worker 在父进程写入 gate 文件后同时开始，不依赖裸 sleep 或 acquire ordering。
- 所有 worker 使用同一 semantic digest（`sha256_digest_json({"command": "same"})`）、不同 result ref（`result-{worker_index}`）。
- `record_idempotent_result` 内部 read-then-INSERT 模式在 `BEGIN IMMEDIATE` 事务保护下：先到者 INSERT 成功，后来者触发 `IntegrityError` 后 re-read 发现同 digest → 返回既有记录，无冲突。
- 断言：所有 worker 返回 `_STATUS_OK`、digest 唯一、result_ref 唯一、DB 只有一行、digest/result_ref 匹配。✓

### Idempotency same scope/key/different digest multiprocess

- 同一 start gate 机制。
- 每个 worker 使用不同 digest（`sha256_digest_json({"command": "different", "worker": worker_index})`）。
- 先到者 INSERT 成功，后来者触发 `IntegrityError` 后 re-read 发现不同 digest → `HostIdempotencyConflictError`。
- 断言：恰好 1 个 OK + 3 个 CONFLICT、DB 只有一行、digest/result_ref 匹配 winner。✓

### Projection checkpoint lost CAS synthetic test

- 真实推进 checkpoint 到 sequence 1（通过 `_AdvanceCheckpointOperation(first_event)`）。
- monkeypatch `projection_module.ensure_projection_checkpoint` 为 `_stale_projection_checkpoint`，返回 sequence 0。
- `_StaleAdvanceCheckpointOperation(second_event)` 调用 `advance_projection_checkpoint(..., event_sequence=2, ...)`。
- `ensure_projection_checkpoint` 返回 stale row（sequence 0），`event_sequence(2) <= checkpoint_event_sequence(0)` 为 False，进入 UPDATE。
- UPDATE `WHERE checkpoint_event_sequence = 0` 匹配 0 行（真实 checkpoint 是 sequence 1），`rowcount != 1` → `HostDurableError("projection checkpoint advance lost CAS race")`。✓
- 断言：错误消息包含 `"projection checkpoint advance lost CAS race"`、persisted checkpoint 仍为 sequence 1 + first_event.event_id。✓

### Memory snapshot + checkpoint CAS rollback test

- 同样真实推进 checkpoint 到 sequence 1。
- 构造 cursor 为 sequence 2 的 `ConversationMemorySnapshot`。
- 同一 stale checkpoint monkeypatch。
- `write_memory_snapshot_with_checkpoint` 先调用 `write_memory_snapshot`（INSERT），再调用 `advance_projection_checkpoint`（stale → CAS failure → raise）。
- `run_write` 捕获 `HostDurableError`，执行 `_rollback` 回滚整个事务（包括 INSERT）。✓
- 断言：错误消息包含 race 关键词、snapshot 不存在（`read_memory_snapshot` 返回 `None` → `False`）、checkpoint 仍为 sequence 1。✓
- 未发明 snapshot row CAS；rollback 语义由事务保证。

### 不重复 closed-by-evidence 项

- 模块 docstring 明确列出 EventLog append（`test_event_log_multiprocess.py`）、ensure_session（`test_admission_multiprocess.py`）、liveness（`test_host_instance_liveness.py`）closed by evidence。
- 未在本文件重复覆盖这些场景。✓

### 测试 helper 质量

- 所有 helper 均为模块级 top-level 函数/类，满足 multiprocessing fork 要求。
- 类型标注完整：`_IdempotencySummary`（frozen dataclass）、operation classes（`__call__` 返回类型明确）、helper 函数（`HostRow | None`、`tuple[str, ...]`、`str`、`int`、`bool`）。
- 无 `Any`、`object`、无类型参数、无类型返回值。
- 中文 docstring 完整，包含参数、返回值、异常。
- 魔法字符串收拢为模块级常量（`_STATUS_OK`、`_STATUS_CONFLICT`、`_MODE_SAME_DIGEST`、`_RESULT_SEPARATOR` 等），无扩散。✓

### tests/README.md 更新

- 变更 1：缩窄运行命令新增 `test_durable_concurrency_matrix.py`。✓
- 变更 2：新增 durable concurrency matrix 覆盖说明 bullet，明确列出覆盖场景和不重复覆盖理由。✓
- 未超出测试手册职责范围，未添加过程状态、未来计划或时间敏感记录。✓

## Non-blocking Suggestions

无。

## Open Questions / Residual Risk

### Non-blocking

- 多进程 smoke 在极端慢机器上可能受进程启动影响。当前使用文件 start gate、固定 4 worker、bounded timeout 和 result file 模式，与既有 `test_event_log_multiprocess.py` 同类。风险可接受。
- `_RESULT_SEPARATOR = "|"` 作为字段分隔符，当前 digest（hex）和 result_ref（`result-N`）不含 `|`，无碰撞风险。若未来 worker result_ref 格式变化可能含 `|`，需同步更新。当前无需处理。

### Blocking

无。

## Stop Status

review-complete
