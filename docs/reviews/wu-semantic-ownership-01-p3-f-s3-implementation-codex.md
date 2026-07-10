# WU-SEMANTIC-OWNERSHIP-01 P3-F S3 Implementation Report

## 动机检查

S3 动机成立。Fins wait adapter 原先用 `_TRANSIENT_PENDING_MAX_SECONDS = 300.0` 和 `WaitRecordRow.created_at` 推断 `TRANSIENT_UNAVAILABLE` 是否应转为 lost。这把 terminal wait timeout 的事实放到了 Fins adapter 内部，和 Host wait record 的 deadline / expiry truth 不同源。

正确 owner boundary 是：

- Host wait record 拥有 deadline / expiry truth。
- Fins adapter 只消费 `WaitRecordRow.deadline_at`，没有 deadline 时再消费 `expires_at`。
- Fins adapter 不应从 `created_at` 年龄自行创造 terminal lost 边界。

## Host wait creation evidence

已检查 `dayu/host/waiting.py:_wait_record_row`：

- `deadline_at` 来自 `candidate.await_spec.deadline`，通过 `format_utc_timestamp(...)` 写入。
- 当 await spec 没有 deadline 时，`deadline_at=None`。
- `expires_at` 当前写入为 `None`。

这说明 Fins awaiting wait record 可能没有 deadline / expires 边界；这种场景下 Fins adapter 应返回 `WaitPollNotReady`，由 Host poller cadence、cancel / close lifecycle 和后续 Host-owned boundary 负责治理。

已对齐 `dayu/host/wait_callback.py:_stale_status_or_none` 的 precedence：先读 `deadline_at`，只有 deadline 缺失时才读 `expires_at`；边界存在但非法时 fail closed。

## 修改文件与行为

- `dayu/fins/ingestion/wait_adapter.py`
  - 删除 `_TRANSIENT_PENDING_MAX_SECONDS`。
  - 删除 `_transient_pending_expired(...)`。
  - 新增 `_wait_boundary_lost(...)`，按 Host boundary 判断 transient unavailable 是否 lost：
    - future `deadline_at` -> not ready。
    - past `deadline_at` -> lost。
    - no deadline + past `expires_at` -> lost。
    - present invalid `deadline_at` / `expires_at` -> lost。
    - no boundary -> not ready。
    - 不再读取 `created_at` 年龄。
- `tests/fins/test_fins_ingestion_tools.py`
  - 更新 transient unavailable 测试矩阵。
  - `_wait_record(...)` builder 支持显式 `deadline_at` / `expires_at`。
- `dayu/fins/README.md`
  - 更新 wait adapter contract，去掉“有界窗口”描述，记录 Host wait boundary ownership。

未修改 `tests/fins/test_fins_ingestion_runtime.py`；现有 builder 不需要额外 deadline / expires 覆盖。

## Owner boundary 与传播审计

1. Producer: Host awaiting accept 通过 `_wait_record_row(...)` 从 await spec 写入 `deadline_at`，并写 `expires_at=None`。
2. Durable truth: `WaitRecordRow.deadline_at` / `expires_at` 是 wait boundary 真源。
3. Adapter consumption: Fins `FinsIngestionWaitPollAdapter` 在 observation transient unavailable 时只消费 Host boundary，按 deadline-first / expires-second precedence 判断 lost。
4. Projection: adapter 返回 `WaitPollNotReady` 或 `WaitPollLost(_lost_outcome())`；不把 wait id、deadline、expiry timestamp 或 Host governance wording 暴露给 LLM-facing tool result。
5. Host resolution: Host poll / resolve 继续拥有 wait terminal governance；Fins adapter 不写 Host wait record、不写 EventLog、不恢复 Engine generator。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：`132 passed, 3 warnings`
- `source .venv/bin/activate && rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests`
  - 结果：无匹配；`rg` exit code 为 `1`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

README 决策：

- `dayu/fins/README.md` 更新，因为 S3 改变了已记录的 wait adapter 稳定 contract。
- `tests/README.md` 未更新，因为没有新增测试层级、测试运行方式或维护规则。

## 残余风险

- 无 deadline / expires 的 transient unavailable 可能长期 not ready；这是有意边界选择，因为 Fins adapter 不拥有 terminal timeout。实际轮询节奏、claim TTL、cancel / close lifecycle 仍由 Host 治理。
- `expires_at` 当前 Host creation path 写 `None`；本次实现按 contract 支持该字段，供未来 Host-owned expiry truth 消费。

## 完成状态

ready-for-code-review
