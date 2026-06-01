# WU-DUR-01-02 Slice 2 Code Review - DS

## Reviewed Target

- **Mode**: current uncommitted changes, Slice 2 only
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice2-codex-20260601.md`
- **Changed files**:
  - `dayu/host/durable/maintenance.py` — 新增 internal WAL checkpoint primitive
  - `tests/host/test_durable_connection.py` — 新增 PASSIVE checkpoint 结果可观测、closed connection 失败结构化、checkpoint 不改变 EventLog truth 三个测试
  - `tests/host/test_durable_transaction.py` — 新增两个独立 connection 的 read-stale snapshot 测试
  - `dayu/host/README.md` — 低层与 Diagnostic 路径条目同步当前 durable 能力
- **Review lens**: 按 handoff 指定的六个 review lens 逐项审查

## Conclusion

**pass**

实现质量高：WAL checkpoint primitive 严格内部-only、类型完整、无 public API leak、error handling 正确覆盖 no-row / sqlite error / busy_pages diagnostic / WAL size；read-stale 测试使用真正的同一 DB 两个独立 connection 证明 snapshot 语义；checkpoint diagnostic 测试正确证明不改变 EventLog truth；README 只在内部 diagnostic 路径同步事实。发现两个低严重度 finding，无 blocking open question。

## Findings

### DS-C2-未修复-低: `_read_wal_size_bytes` OSError 与 checkpoint PRAGMA 错误共用相同消息

- **入口/函数**: `_read_wal_size_bytes` 与 `run_host_wal_checkpoint` 的 `sqlite3.Error` except 分支
- **文件(行号)**: `dayu/host/durable/maintenance.py:69` 与 `dayu/host/durable/maintenance.py:122`
- **输入场景**: checkpoint PRAGMA 执行成功，但随后的 WAL 文件 stat 因为权限变化等非 FileNotFound 的 OSError 失败
- **实际分支**: 代码沿线 67（checkpoint PRAGMA success）→ 90（进入 `_read_wal_size_bytes`）→ 121（非 FileNotFound OSError）→ 122 raise
- **预期行为**: 报告 WAL 文件 stat 失败，区分于 checkpoint PRAGMA 执行失败
- **实际行为**: 抛出 `HostDurableError("Host durable WAL checkpoint failed")`，与 checkpoint PRAGMA 真正失败（行 69）完全相同的错误消息
- **直接证据**:
  - 行 69: `raise HostDurableError("Host durable WAL checkpoint failed") from exc` — sqlite3.Error 路径
  - 行 122: `raise HostDurableError("Host durable WAL checkpoint failed") from exc` — OSError 路径
  - 两条路径共用相同错误消息字符串，调用方无法区分
- **影响**: 运维层面可能导致误判——checkpoint 实际成功但因 WAL 文件 stat 权限问题抛错时，错误消息暗示 "checkpoint failed"，可能触发不必要的重试或告警。该路径是 diagnostic 而非 correctness-critical，实际触发概率极低（需 checkpoint 执行期间 WAL 文件权限突变）。
- **建议改法和验证点**: `_read_wal_size_bytes` 的 OSError 分支使用独立错误消息，例如 `"Host durable WAL checkpoint failed to read wal file size"`。验证: 确保 `sqlite3.Error` 路径与 `OSError` 路径可被错误消息区分。
- **修复风险（低）**: 只改字符串，不改变控制流、状态或异常类型。
- **严重程度（低）**:
- **Controller decision status**: pending

### DS-C2-未修复-低: `row_values` 长度校验分支错误消息不精确

- **入口/函数**: `run_host_wal_checkpoint` 的 row length check 分支
- **文件(行号)**: `dayu/host/durable/maintenance.py:74-75`
- **输入场景**: SQLite `PRAGMA wal_checkpoint` 返回非 3 列的 row（实际上不可能，但防御代码存在此分支）
- **实际分支**: 行 74: `len(row_values) != _SQLITE_CHECKPOINT_ROW_LENGTH` → 行 75: raise
- **预期行为**: 报告 "unexpected result shape" 或类似，因为 SQLite 实际返回了 row 只是列数不符合预期
- **实际行为**: 错误消息为 `"Host durable WAL checkpoint returned no result"`，与行 71 的 `row is None` 分支完全相同的消息
- **直接证据**: 行 71: `raise HostDurableError("Host durable WAL checkpoint returned no result")` ；行 75: `raise HostDurableError("Host durable WAL checkpoint returned no result")`
- **影响**: SQLite 实际返回了结果但错误消息声称 "no result"，增加调试困惑。该分支在 SQLite 正确实现下不可达，实际影响几乎为零。
- **建议改法和验证点**: 使用独立消息如 `"Host durable WAL checkpoint returned unexpected result shape"`。验证: 可控注入使触发消息区分。
- **修复风险（低）**: 只改字符串。
- **严重程度（低）**:
- **Controller decision status**: pending

## Non-blocking Suggestions

1. **TRUNCATE 模式缺乏直接测试**: `HostWalCheckpointMode.TRUNCATE` 在 plan 中被明确支持，当前三个 checkpoint 测试只用 `PASSIVE` 模式。建议至少增加一个 TRUNCATE 基本可调用 + 返回字段合法的测试，但 plan 未要求此覆盖，不作为 finding。

2. **test_durable_connection.py 与 test_durable_transaction.py 的 `_event_request` / `_append_event` / `_count_event_log_rows` 存在结构性重复**: 两个测试文件各自定义了功能相似的 helper，仅在 `session_id` / `run_id` 等 fixture 参数上有差异。这是两个独立测试模块的合理自包含，但长期可考虑将通用 EventLog fixture 抽取到 `tests/host/conftest.py`。当前重复不影响测试正确性。

3. **`_checkpoint_int` 错误消息可增加实际类型信息**: 行 105 的 `"Host durable WAL checkpoint invalid {field_name}"` 如需提升诊断精度，可追加 `f"expected int, got {type(value).__name__}"`。该路径在正常 SQLite 行为下不可达。

## Open Questions / Residual Risk

### Blocking

无。

### Non-blocking

- **WAL size 读后一致性**: `_read_wal_size_bytes` 在 checkpoint PRAGMA 之后读取 WAL 文件大小，存在 TOCTOU 窗口——并发写入者可能在两个操作之间 append WAL frame。这不会造成数据损坏或其他 correctness 问题，因为该 primitive 明确设计为 diagnostic-only，不消费 WAL size 做 correctness decision。Plan 与 design doc 均未要求该值满足任何一致性保证。
- **test_durable_connection.py 中被标记为 modified 的既有测试** (`test_close_connection_best_effort_suppresses_close_failure`、`test_configure_connection_pragmas_sets_wal_autocheckpoint`) 未做语义变更，仅因 import block 新增而出现在 diff 中。已逐行确认不影响既有行为。

## Residual Risk

- Slice 2 范围内未覆盖的 TRUNCATE checkpoint path、`busy_pages > 0` 生产场景稳定性证明属于 plan 预留的"不在本 slice"范围，不影响当前 pass 结论。
- WU-DUR-02 idempotency 多进程、projection checkpoint CAS、memory snapshot + checkpoint CAS 并发矩阵缺口属于 Slice 3，不在本 review scope。

## Stop Status

review-complete
