# WU-LAYER-01 Slice 1 Schema Definition Validation Implementation Artifact

## Changed Files

- `dayu/host/durable/schema.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/wu-layer-01-slice1-schema-definition-validation-codex-20260602.md`

## Implemented Plan Items

- 保持 `HOST_DURABLE_DDL` 为唯一 DDL 真源。
- 在 `schema.py` 增加 private schema helpers：
  - 从当前 `HOST_DURABLE_DDL` 创建 in-memory SQLite fresh DB 并生成 expected `sqlite_master.sql`。
  - 读取目标 DB 中 required table / index 的 `sqlite_master.sql`。
  - 用最小 `_normalize_schema_sql` 规则比较定义：只 strip 首尾空白并折叠连续空白为单个 ASCII space，不解析 SQL、不改大小写、不移除 quotes、不归一化标点或 clause。
  - 只比较 `HOST_DURABLE_TABLES` 与 `HOST_DURABLE_INDEXES`，不读取或比较 `sqlite_sequence` / SQLite autoindexes。
- `validate_host_durable_schema` 在 user_version、required table existence、required index existence 校验后，新增 required object definition 校验。
- definition mismatch 使用 `HostSchemaMismatchError`，message 命名 object type 与 object name，例如 `Host durable schema definition mismatch: index host_runs_one_active_per_session`。
- 新增测试覆盖：
  - current-version DB 中同名 required index 定义错误时 opener fail closed 且不 repair。
  - current-version DB 中同名 table 的 `sqlite_master.sql` 定义变异时 opener fail closed 且不 repair。
  - secondary connection 遇到 definition mismatch 时 fail closed 且不 repair。
  - fresh bootstrap 成功，fresh DB 可通过 generated expected SQL 校验。
  - `_normalize_schema_sql` 只归一化首尾空白与连续空白；大小写、identifier quote、clause 和标点变化不会被吞掉。

## Validation Output Summary

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py`
  - `33 passed in 0.50s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`

## README Decision

- `dayu/host/README.md`: checked-no-change。
- 理由：本 Slice 只增强 Host durable 内部 schema validation fail-closed 行为；未改变 public contract、状态机语义、开发者稳定扩展入口或 README 当前职责范围内的 durable foundation 描述。

## Residual Risks / Uncovered Areas

- 未实现 Slice 2 terminal shape rules owner。
- 未实现 Slice 3 `HostRowDecodeError`。
- 未处理 WU-LAYER-02 shared helper consolidation。
- 本 Slice 不做旧库兼容迁移或 repair；definition mismatch 仍按当前计划 fail closed。

## Completion Status

- Slice 1 implementation complete。
- 未 commit、未 push、未 open PR，未进入 review gate。
