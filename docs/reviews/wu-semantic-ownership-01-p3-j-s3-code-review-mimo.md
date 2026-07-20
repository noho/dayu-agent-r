# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `6a208bec`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-mimo.md`
- Included scope: P3-J S3 diff for idempotency and descriptor kind weak-contract closure
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-controller-validation.md`

## Findings

### S3-01-未修复-中-IdempotencyScope/IdempotencyResultRef 数据类字段仍为裸 str，缺失构造时校验

- **入口/函数**: `IdempotencyScope.__init__`, `IdempotencyResultRef.__init__`
- **文件(行号)**: `dayu/host/durable/idempotency.py:109-136`
- **输入场景**: 调用方构造 `IdempotencyScope(scope_kind="external_plugin_scope", ...)` 或 `IdempotencyResultRef(result_kind="external_ack", ...)`
- **实际分支**: 数据类构造器直接接受任意 `str`，不校验值是否在 `IdempotencyScopeKind` / `IdempotencyResultKind` 闭集内。校验仅发生在 store insert (`_validate_scope` / `_validate_result_ref`，行 315-351) 和 row decode (`_idempotency_record_from_host_row`，行 354-384)。
- **预期行为**: Plan §3.4 要求 "Validation: `IdempotencyScope` and `IdempotencyResultRef`"。Controller validation 明确标注 "Construction-time validation of `IdempotencyScope` / `IdempotencyResultRef` remains a review focus before S3 acceptance"。数据类作为幂等 owner 语义的载体，应在其构造边界拒绝非法值，使类型字段从 `str` 提升为 `IdempotencyScopeKind` / `IdempotencyResultKind`。
- **实际行为**: 数据类字段为 `str`，非法实例可被构造并在 store 边界前传递。虽然后续 store insert/read 会拒绝，但在构造与 store 之间存在非法值可存活的窗口，且数据类本身的类型签名未承诺合法值域。
- **直接证据**:
  - `dayu/host/durable/idempotency.py:118` — `scope_kind: str`
  - `dayu/host/durable/idempotency.py:133` — `result_kind: str`
  - `dayu/host/durable/idempotency.py:154` — `IdempotencyRecord.scope_kind: str`
  - `dayu/host/durable/idempotency.py:159` — `IdempotencyRecord.result_kind: str`
  - `dayu/host/durable/idempotency.py:323` — `_validate_scope` 调用 `parse_idempotency_scope_kind(scope.scope_kind)` 但不在构造器中
  - `dayu/host/durable/idempotency.py:336` — `_validate_result_ref` 调用 `parse_idempotency_result_kind(result.result_kind)` 但不在构造器中
- **影响**: 语义所有权边界不完整。数据类作为幂等 owner 的公开 contract，未在其构造边界承诺合法值域，将校验推迟到 store 边界。构造非法实例不会立即失败，可能在 error logging、debug 输出或中间传递中暴露非法值。当前实际风险较低，因为 `IdempotencyScope` / `IdempotencyResultRef` 的消费者只有 `record_idempotent_result()` 和 `read_idempotency_record()`，两者均在 store 边界校验。
- **建议改法和验证点**:
  1. 将 `IdempotencyScope.scope_kind` 类型从 `str` 改为 `IdempotencyScopeKind`
  2. 将 `IdempotencyResultRef.result_kind` 类型从 `str` 改为 `IdempotencyResultKind`
  3. 将 `IdempotencyRecord.scope_kind` / `result_kind` 类型从 `str` 改为对应 enum
  4. 更新 `_validate_scope` / `_validate_result_ref` 中的 `parse_*` 调用，因为构造器已保证类型正确
  5. 更新 row decode 中的 `parse_*` 调用，使用 typed 返回值直接赋值
  6. 更新生产调用方传入 enum 值而非裸字符串
  7. 验证：`pytest tests/host/test_idempotency_store.py tests/host/test_durable_concurrency_matrix.py tests/host/test_purge_session.py -q`
- **修复风险（低/中/高）**: 低。类型收紧是纯类型变更，不改变运行时行为，因为 store 边界已做同样校验。
- **严重程度（低/中/高/严重）**: 中。违反 plan 明确要求的 owner 边界语义，但当前 store 边界已兜底，实际运行时风险低。

## Open Questions

- **旧 descriptor kind 字符串常量是否应从 `payload_resolution.py` 消费端迁移为 typed enum?** `payload_resolution.py:247,298` 仍导入 `TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND` / `TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`（现为 `PayloadDescriptorKind` enum `.value` 的派生值）作为 `_validate_descriptor_kind` 的 `expected_kind` 参数。虽然该函数内部通过 `parse_payload_descriptor_kind(expected_kind)` 校验，但 plan §3.5 要求 "replay / conflict helpers compare enum values or owner helper outputs, not naked strings"。当前这些常量已是 enum 派生值（非独立裸字符串），且 `_validate_descriptor_kind` 接受 `str | PayloadDescriptorKind`。此为 maintainability 观察，非 correctness 缺陷。

## Residual Risk

- `tests/host/test_purge_session.py:2556-2575` 使用 direct SQL INSERT 绕过 `IdempotencyStore` 写入 `_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND`（值为 `"external_projection_ack"`，不在 `IdempotencyScopeKind` 闭集内）和 `result_kind="external_ack"`（不在 `IdempotencyResultKind` 闭集内）。这是可接受的，因为该测试模拟的是 purge 矩阵中超出当前 idempotency owner 路径的历史/外部 row；生产路径通过 `IdempotencyStore` 写入时会拒绝这些值。但此设计意味着 purge 测试不验证 store 对 out-of-scope row 的拒绝行为。
- `IdempotencyRecord` 数据类同样暴露 `str` 字段，虽然 row decode 路径已通过 `parse_*` 校验，但如果未来有代码直接构造 `IdempotencyRecord`（而非从 row decode），将绕过校验。当前无此路径。
- `payload_descriptor_metadata()` helper 正确拒绝 `fields` 中包含 `descriptor_kind` 的覆盖尝试，但生产调用方传入的 `fields` 中是否可能通过嵌套结构间接包含 `descriptor_kind` 值未被覆盖。当前所有生产调用方均为显式字面量字典，风险低。
