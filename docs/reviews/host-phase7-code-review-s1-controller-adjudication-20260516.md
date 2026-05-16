# Host Phase 7 P7-S1 Code Review Controller Adjudication - 2026-05-16

## 结论

Controller 裁决：P7-S1 code review 需要一个小范围 fix pass。

两路 review：

- `docs/reviews/host-phase7-code-review-s1-mimo-20260516.md`：无阻塞，2 个低严重度 finding。
- `docs/reviews/host-phase7-code-review-s1-ds-20260516.md`：无阻塞，1 个中严重度 finding、2 个低严重度 finding。

## 裁决记录

### S1-F1 accepted - 长度常量重复定义存在漂移风险

来源：MiMo-1、DS-001。

裁决：接受，当前 slice 修复。

理由：P7 plan 明确 dataclass validation 与 DDL CHECK 必须保持一致。`dayu/host/api.py` 与
`dayu/host/durable/schema.py` 当前重复定义 wait length constants，未来漂移会让 Python 校验与 SQLite CHECK 不一致。
`dayu.host.api` 不依赖 durable schema，schema 从 api 导入这些公共契约常量不会引入反向依赖。

要求：`dayu/host/durable/schema.py` 从 `dayu.host.api` 导入 wait length constants，删除本地重复定义，保持 schema tests 通过。

### S1-F2 accepted - snapshot_digest DDL 配对约束不完整

来源：MiMo-2。

裁决：接受，当前 slice 修复。

理由：`snapshot_ref`、`snapshot_captured_at`、`snapshot_digest` 是同一 optional snapshot ref 组。Python deserialize 已拒绝
不完整组合，DDL 也应拒绝直接 SQL 写入 `snapshot_digest` orphan 值，避免 durable row 脏数据。

要求：`host_wait_records` DDL CHECK 改为：无 snapshot 时三列均为 NULL；有 snapshot 时 `snapshot_ref` 与
`snapshot_captured_at` 必须非 NULL，`snapshot_digest` 可为 NULL。补充 DDL 测试覆盖 orphan `snapshot_digest` 被拒绝。

### S1-F3 rejected - DDL 强制 adapter_key 字符模式

来源：DS-002。

裁决：拒绝当前修复。

理由：SQLite CHECK 不适合表达与 Python regex 完全一致的字符集规则；当前正常写入路径全部经 `WaitAdapterKey`
dataclass validation。DDL 已覆盖非空与长度边界，字符集规则保留在 typed constructor 层，符合当前 slice 的防御层级。

追踪：若后续 durable hardening 统一引入 SQLite string-pattern CHECK helper，可作为独立 hardening 处理。

### S1-F4 deferred - 单条 CAS_LOST deterministic coverage

来源：DS-003 与 MiMo residual risk。

裁决：deferred to P7-S4。

理由：单条 wait record CAS_LOST 是并发事务竞态分支，P7-S4 的 cancel-vs-resolve first-committer-wins 测试天然拥有并发顺序建模场景。
当前 P7-S1 已覆盖 UPDATED / NOT_FOUND / INVALID_STATE；不应通过 sleep 型脆弱测试强造 CAS_LOST。

## Fix Scope

Fix agent 只能修改：

- `dayu/host/durable/schema.py`
- `tests/host/test_durable_schema.py` 或 `tests/host/test_wait_record_state.py`
- `docs/reviews/host-phase7-fix-s1-public-contracts-wait-record-20260516.md`

不得修改 public API、state helpers、ToolRuntime、plan 或其它 docs。

## Re-review Gate

Fix 完成后，必须至少由原 reviewers 复核 accepted findings S1-F1 / S1-F2 是否关闭，且确认 rejected / deferred findings 未被误修。
