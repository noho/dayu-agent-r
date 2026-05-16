# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: P8-S1 accepted commit `80c12a2`
- Output file: `docs/reviews/host-phase8-code-review-s2-mimo-20260516.md`
- Included scope: `tests/host/test_public_event_stream.py` (workspace diff), `tests/host/test_import_boundary.py` (workspace diff), `dayu/host/read_api.py` (production code review), `tests/host/test_weak_typing_guard.py` (guard check), implementation artifact `docs/reviews/host-phase8-implementation-s2-event-stream-cursor-20260516.md`
- Excluded scope: `dayu/host/README.md` (unchanged, decision documented in implementation artifact), `docs/host/implementation-control.md` (staged change outside S2 scope)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Details

### 1. Plan Compliance

P8-S2 scope 限定为 `dayu/host/read_api.py`、`tests/host/test_public_event_stream.py`、`tests/host/test_import_boundary.py`、`tests/host/test_weak_typing_guard.py`、optional `dayu/host/README.md`。实际变更仅涉及两个测试文件的 workspace diff；`read_api.py` 未修改；未修改任何 plan 禁止文件（engine、runtime、service、ui、fins、command、dispatch、admission、waiting）。scope creep: 无。

### 2. Production Code Review — `dayu/host/read_api.py`

- `stream_run_events` 保持 EventLog-backed read path，使用 `read_events_after(transaction, cursor.event_sequence, limit=...)` 从 EventLog 补读。
- `next_cursor` 从 `scanned[-1].event_sequence` 构造，符合 scan-window contract。
- 无 projection checkpoint / failure / fanout / notification / read_model / repair import 或 token。
- `HostEventStream` public shape 未变更。
- 无新增 `__all__` 符号。

### 3. Test Adequacy

新增三个测试覆盖 P8-S2 计划要求：

| 计划要求 | 测试覆盖 |
|---|---|
| projection checkpoint lag 不影响 stream | `test_stream_run_events_ignores_projection_checkpoint_lag` |
| projection failure row 不影响 stream | `test_stream_run_events_ignores_projection_failure_row` |
| stream 不写 projection 表 | `test_stream_run_events_does_not_write_projection_tables` |

辅助函数设计：

- `_write_projection_checkpoint` / `_write_projection_failure` 直接通过 SQLite 写入干扰 row，绕过 projection runner，确保测试隔离。
- `_projection_checkpoint_rows` / `_projection_failure_rows` 在 stream 调用前后取快照，断言无副作用。
- `_event_views_for_run_after` 按 scan-window contract 从 EventLog 读取期望值，断言与 public API 一致。

### 4. Import / Token Guard Quality

`test_read_api_stream_does_not_reference_projection_or_fanout_truth` 同时检查：

- AST 级 import 禁止：`dayu.host.projection`、`dayu.host.durable.projection`、`dayu.host.read_model`、`dayu.host.fanout`、`dayu.host.notification`。
- 源码 token 禁止：`host_projection_checkpoints`、`host_projection_failures`、`host_session_timeline_items`、`repair_minimal_read_models`、`fanout`、`wakeup`。

两个 guard 均为纯 AST/文本扫描，不依赖模块可导入性，可在 P8-S1 schema 表 DDL 存在但 projection/fanout 模块尚未创建时正常运行。

### 5. Validation Results

```text
pytest tests/host/test_public_event_stream.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
→ 18 passed in 0.62s

python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ clean
```

### 6. No Fanout / Wakeup Implementation

S2 未创建 fanout 模块、wakeup port、notification shell 或 disabled listener。测试仅证明 stream 正确性独立于这些概念。

### 7. stream_run_events Remains EventLog Cursor Truth

`read_api.py` 中 `stream_run_events` 的 cursor truth 是 `HostStreamCursor.event_sequence`，来源是 EventLog `read_events_after` 返回的最后一行。未引用 `host_projection_checkpoints`、session-local cursor、client sequence、fanout offset 或内存订阅位置。

### 8. No Public Shape Change

`HostEventStream`、`HostEventView`、`HostStreamCursor` 均未变更。`__all__` 未新增。

## Open Questions

无。

## Residual Risk

- 未来 approved fanout/wakeup 实现可能意外耦合 stream 正确性与 notification state。S2 新增的 import/token guard 可在 read_api 层级捕获此类回归。
- P8-S3 repair 实现按设计不在本 slice。Owner: P8-S3。

## Conclusion

**PASS**。P8-S2 实现正确，测试充分覆盖计划要求，无 scope creep，无 blocking finding。workspace diff 可进入 accept 流程。
