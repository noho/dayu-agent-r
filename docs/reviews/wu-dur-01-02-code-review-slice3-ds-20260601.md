# WU-DUR-01-02 Slice 3 Code Review - DS

## Reviewed Target

- **Diff**: 当前未提交 changes，仅 Slice 3 范围
  - `tests/host/test_durable_concurrency_matrix.py`（新增，untracked）
  - `tests/README.md`（modified，2 insertions / 1 deletion）
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Implementation artifact**: `docs/reviews/wu-dur-01-02-implementation-slice3-codex-20260601.md`
- **Review artifact**: `docs/reviews/wu-dur-01-02-code-review-slice3-ds-20260601.md`

## Conclusion

**pass**

四条测试正确覆盖了 plan 要求的 idempotency 多进程（same digest / different digest）、projection checkpoint lost CAS synthetic、memory snapshot + checkpoint CAS rollback 四个场景。测试 helper 均为 top-level、严格类型、中文 docstring、无 Any/object/untyped。未重复 EventLog append、ensure_session、liveness 已 closed-by-evidence 项。tests/README.md 更新在测试手册职责范围内且不过度。

## Findings

无实质性问题。未发现 correctness、stability 或 maintainability 层面的 defect。

以下逐条对照 review lens 的验证结论：

### Lens 1: idempotency same/different digest 多进程测试

- **真实并发**: 使用 `multiprocessing.Process`，4 个独立 worker 各自通过 `open_host_durable_store` 打开同一 SQLite DB 的独立连接；start gate 文件同步保证所有 worker 在 gate 打开后同时开始竞争，无裸 sleep 依赖。
- **Bounded**: 固定 `_PROCESS_COUNT = 4`，`_START_GATE_TIMEOUT_SECONDS = 5.0`，`_START_GATE_POLL_SECONDS = 0.005`；进程数小且确定性，与现有 `test_event_log_multiprocess.py` 同类。
- **非 timing/order 依赖**: 断言不依赖 acquire ordering。same digest 测试断言所有 worker 返回 OK、result_refs 一致（证明 idempotent replay 返回首次插入的 winning record）；different digest 测试断言恰好 1 个 winner、3 个 conflict、DB 仅 1 行。
- **断言正确性**: `summary.row_count == 1` 直接从 `TABLE_IDEMPOTENCY_RECORDS` COUNT 读取；winner digest/result_ref 与 DB row 交叉验证。
- **CAS 路径验证（生产代码 `dayu/host/durable/projection.py:176-200`）**: `advance_projection_checkpoint` 先调用 `ensure_projection_checkpoint` 获取当前 checkpoint，再通过 `UPDATE ... WHERE checkpoint_event_sequence = ?` 做 CAS 更新，`rowcount != 1` 时抛 `"projection checkpoint advance lost CAS race"`。测试通过 monkeypatch 将 `ensure_projection_checkpoint` 替换为返回 seq 0 的 stale checkpoint，而真实行已是 seq 1，因此 CAS WHERE 条件不匹配 → rowcount=0 → 触发目标错误。

### Lens 2: projection checkpoint lost CAS synthetic test

- **真正触发 CAS race**: monkeypatch `dayu.host.durable.projection.ensure_projection_checkpoint` → 返回 `checkpoint_event_sequence=0`（stale），真实 checkpoint 为 sequence 1。`advance_projection_checkpoint` 内部 CAS `WHERE checkpoint_event_sequence = 0` 不匹配真实行 → rowcount 0 → `HostDurableError("projection checkpoint advance lost CAS race")`。
- **persisted checkpoint unchanged**: 错误后通过 `read_projection_checkpoint` 读取，断言 `checkpoint.checkpoint_event_sequence == first_event.event_sequence`（sequence 1），checkpoint 未受影响。
- **生产代码路径验证**: `dayu/host/durable/projection.py:176` → `ensure_projection_checkpoint`（被 monkeypatch）→ `projection.py:179-198` CAS UPDATE → `projection.py:199-200` rowcount check → error。路径完整且唯一。

### Lens 3: memory snapshot + checkpoint CAS rollback test

- **证明 snapshot 未半提交**: `write_memory_snapshot_with_checkpoint` 生产实现（`dayu/host/durable/memory.py:496-513`）先调用 `write_memory_snapshot` 写入 snapshot（line 496），再调用 `advance_projection_checkpoint` 推进 checkpoint（line 507）。monkeypatch 使后者 CAS 失败 → 整个 transaction rollback → snapshot 写入被回滚。测试通过 `read_memory_snapshot` 断言 `snapshot_exists is False`，并通过 `read_projection_checkpoint` 断言 checkpoint 仍停在 sequence 1。
- **未发明 snapshot row CAS**: 测试仅依赖 projection checkpoint CAS，未对 `write_memory_snapshot` 或 snapshot row 自身引入任何 CAS 语义。符合 plan 的 non-goal："不发明 memory snapshot row 自身 CAS"。

### Lens 4: 未重复 closed-by-evidence 项

- 模块 docstring（`test_durable_concurrency_matrix.py:1-9`）明确列出 EventLog append、ensure_session、liveness 的 closed-by-evidence 来源文件。
- 测试体未调用任何 EventLog append（除辅助构造测试数据用的 `_AppendEventOperation`，用于创建 EventLog row 作为 projection/memory 测试的前置条件，这是正常的测试 setup）、`ensure_session` 或 liveness 相关函数。
- 未修改 `dayu/host/durable/event_log.py`、`dayu/host/durable/session_lifecycle.py`、`dayu/host/durable/liveness.py`，符合 plan Slice 3 的禁止修改文件列表。

### Lens 5: 测试 helper 类型与文档

- **Top-level**: 所有 helper 均为模块级函数或类，无嵌套函数/类。
- **严格类型**: 所有函数参数与返回值均有类型标注。`_IdempotencySummary` 为 `frozen=True, slots=True` dataclass。`_RecordIdempotencyOperation` 等 operation class 实现 `__call__(self, transaction: HostTransaction) -> T` 协议。pyright 结果 0 errors, 0 warnings。
- **中文 docstring**: 所有 helper 均包含中文 docstring，覆盖参数、返回值、异常。模块 docstring 说明覆盖范围与 closed-by-evidence 理由。
- **无 Any/object/untyped**: pyright 已验证。
- **无魔法字符串扩散**: 跨 worker/test 共享的字符串（`_SCOPE_KIND`、`_STATUS_OK`、`_STATUS_CONFLICT`、`_MODE_SAME_DIGEST`、`_MODE_DIFFERENT_DIGEST`、`_CONSUMER_ID` 等）均为模块级常量。测试内临时 event_id、snapshot_id 等为各测试局部字面量，不跨测试共享。

### Lens 6: tests/README.md 更新

- 变更范围：新增一行 `pytest` 命令（line 41，在 durable foundation 命令组中加入 `test_durable_concurrency_matrix.py`），新增一行 coverage bullet（line 128，描述 durable concurrency matrix 覆盖项）。
- 职责范围内：属"测试分层"与"运行方式"事实同步，未越界写用户手册、Engine 设计、未来计划或时间敏感记录。
- 不过度：更新仅描述当前测试覆盖事实，不展开实现细节或 process status。

## Non-blocking Suggestions

1. **`mode: str` 可用 `Literal` 收紧**: `_idempotency_worker` 与 `_worker_digest` 的 `mode` 参数当前标注为 `str`，实际仅接受 `_MODE_SAME_DIGEST` / `_MODE_DIFFERENT_DIGEST` 两个值。可改为 `Literal["same_digest", "different_digest"]` 提升类型精度。当前 `str` 不影响正确性，且 multiprocessing worker 的 args 必须是可 pickle 类型（`str` 和 `Literal` 均可），故仅为 non-blocking 建议。

2. **same-digest 测试可加显式验证"非首次 worker 返回的是已存在记录"**: 当前通过 `frozenset(result_refs)` 大小间接验证所有 worker 拿到同一 winning result_ref，已经充分。若想更直接，可加一条注释说明"result_refs 一致证明 idempotent replay 返回首次插入的 record，而非各 worker 自身候选值"。当前断言链已隐含此语义，仅作可读性建议。

## Open Questions / Residual Risk

### Blocking

无。

### Non-blocking

- **多进程 smoke 极端慢机器风险**: Implementation artifact 已记录。当前使用 start gate、4 固定 worker、bounded timeout，断言不依赖 acquire ordering。风险低，无需新增 issue。
- **`write_memory_snapshot_with_checkpoint` 的 write-then-checkpoint 内部顺序**: 测试只能验证"snapshot 最终未持久化"，无法区分"snapshot 从未写入"与"snapshot 写入后被 rollback"。当前测试依赖生产代码的 write-before-checkpoint 实现顺序（`memory.py:496` 写 snapshot → `memory.py:507` 推进 checkpoint），且生产代码已通过代码走读确认该顺序。若未来重构改变此顺序，本测试不会失败但语义覆盖减弱。当前 risk 低，因为该顺序也是 plan 的明确要求。

## Stop Status

review-complete
