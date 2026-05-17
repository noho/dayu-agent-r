# P9.5 S5 Schema CHECK Hardening Implementation

## 范围

- Gate：P9.5 S5 Schema CHECK Hardening implementation。
- 分支：`p9.5-pre-p10-hardening`。
- 计划来源：`docs/host/p9-5-pre-p10-hardening-plan.md` 的 S5。

## 动机判断

S5 动机成立。当前 durable DDL 已覆盖多数状态枚举、projection、memory、wait record 与 dispatch record 约束，但 foundation 层仍存在 direct SQLite insertion 可绕过 Python validation 的事实缺口：`event_log` 允许只有 `payload_digest` 没有 `payload_ref`，`idempotency_records` 允许结果事件 id / sequence 单边出现或非正 sequence。这些不是未来语义，而是当前 Python primitive 已经强制的持久化事实。

## 变更文件

- `dayu/host/durable/schema.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/p9-5-s5-schema-check-hardening-implementation-20260517.md`

## 实现内容

- 将 `HOST_SCHEMA_VERSION` 从 `7` bump 到 `8`，保持 fresh schema 版本与 DDL 变化一致。
- 收紧 `event_log` 的 payload reference CHECK：`payload_ref` 与 `payload_digest` 必须同时为空或同时非空。
- 收紧 `idempotency_records` 的 result event reference CHECK：`created_event_id` 与 `created_event_sequence` 必须同时为空或同时非空，且 sequence 非空时必须大于零。
- 新增 direct SQLite insertion 测试，证明绕过 Python API 时单边 payload reference、单边 idempotency event reference 与非正 event sequence 都会被 SQLite 拒绝。
- Python validation parity 已存在于 `event_log.py` 与 `idempotency.py`，本次未改 `_validation.py` 或其它 durable helper。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py`
  - 结果：71 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无输出。

## 文档决策

已检查 `dayu/host/README.md` 与 `tests/README.md`。现有文档只描述 Host durable fresh bootstrap、schema version 校验、table constraints、CHECK / FK / index 覆盖类别，没有固定 schema version 或与本次成对引用约束冲突的接口示例；本次不需要修改 README。

## 残余风险

- 本次只收紧当前 Python validation 已有事实，没有添加 digest 格式 CHECK、future state、future table、migration 或兼容读取。
- 未为 `wait_records.await_kind`、memory diagnostic event reference 等可能随后续阶段扩展的字段新增额外 DDL 约束，避免把未稳定语义写死到 S5。
- 未新增 public facade、public error code、状态机语义、compat wrapper、export 或 P10/P11/P13/P15 行为。

## 停止状态

S5 implementation 完成。未 commit、未 push、未创建 PR，未进入 review gate。
