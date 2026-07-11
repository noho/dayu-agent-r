# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Code Review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `6a208bec`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-ds.md`
- Included scope: only current uncommitted diff in P3-J S3 files (see below)
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-*.md` (unrelated dirty/untracked)
- Parallel review coverage: 无（单 reviewer 完整走读所有 S3 changed files）

### Included Changed Files

- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`
- `tests/host/test_idempotency_store.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_durable_concurrency_matrix.py`

### Design / Control Sources Reviewed

- `docs/host/design.md` (referenced, not re-read in full — S3 scope is bounded by plan)
- `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- `docs/reviews/wu-semantic-ownership-01-p3-j-s3-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-p3-j-s3-controller-validation.md`
- `AGENTS.md` (semantic ownership, LLM-facing, 分层, 类型, docstring 约束)

## Findings

### 1-未修复-中-IdempotencyScope/IdempotencyResultRef 保持 str 字段，构造期不校验 owner 闭集

- **入口/函数**: `IdempotencyScope.__init__` / `IdempotencyResultRef.__init__`
- **文件(行号)**: `dayu/host/durable/idempotency.py:118` (`scope_kind: str`), `dayu/host/durable/idempotency.py:133` (`result_kind: str`)
- **输入场景**: 调用方构造 `IdempotencyScope(scope_kind="bogus_value", ...)` 或 `IdempotencyResultRef(result_kind="bogus_value", ...)`，不经过 store insert/read 路径。
- **实际分支**: dataclass 是 `frozen=True, slots=True`，无 `__post_init__`；构造时不做任何 owner 闭集校验。`"bogus_value"` 可以成功构造并被传递、存储到局部变量、序列化到 log 等。
- **预期行为**: Plan 3.4 写 "Validation: `IdempotencyScope` and `IdempotencyResultRef`." controller validation 明确将此列为 review focus："IdempotencyScope and IdempotencyResultRef still expose str fields. Current fail-closed behavior is at store insert/read boundaries, not dataclass construction. Reviewers should verify whether this satisfies the accepted S3 owner-boundary requirement or whether construction-time validation is required."
- **实际行为**: 校验仅在 `_validate_scope()`（`idempotency.py:323`）和 `_validate_result_ref()`（`idempotency.py:336`）中执行，这两个函数被 `record_idempotent_result()`（store insert 路径）和 `read_idempotency_record()`（store read 路径）调用。dataclass 自身不强制 invariant。
- **直接证据**:
  - `IdempotencyScope` 定义于 `idempotency.py:109-120`，字段 `scope_kind: str`，无 `__post_init__`
  - `IdempotencyResultRef` 定义于 `idempotency.py:123-136`，字段 `result_kind: str`，无 `__post_init__`
  - `_validate_scope()` (`idempotency.py:315-325`) 调用 `parse_idempotency_scope_kind(scope.scope_kind)`——store 边界校验
  - `_validate_result_ref()` (`idempotency.py:328-351`) 调用 `parse_idempotency_result_kind(result.result_kind)`——store 边界校验
  - 但 `tests/host/test_idempotency_store.py:67-70` 中 `_scope()` helper 使用 `scope_kind="close_session"`（合法值），非法值构造从未被单独测试——所有非法值测试都经过 store 路径
- **影响**: 一个携带非法 `scope_kind` / `result_kind` 的 `IdempotencyScope` / `IdempotencyResultRef` 可以在 store 边界之外被构造、传递、比较、序列化。当前所有生产路径都经过 store，因此不会产生 durable 脏数据；但在未来新增非 store 消费者（如 log、audit、diagnostic projection、test helper 复用）时，非法值可能被当作合法值使用。构造期不校验也意味着类型系统不帮助调用方在早期发现错误——错误推迟到 store insert 才暴露。
- **建议改法和验证点**:
  1. 为 `IdempotencyScope` 添加 `__post_init__`，在其中调用 `parse_idempotency_scope_kind(self.scope_kind)`
  2. 为 `IdempotencyResultRef` 添加 `__post_init__`，在其中调用 `parse_idempotency_result_kind(self.result_kind)`
  3. `_validate_scope()` / `_validate_result_ref()` 中的重复校验可保留作为 defense-in-depth，或精简为仅校验非 kind 字段
  4. 新增测试：直接构造非法 `IdempotencyScope(scope_kind="bogus", ...)` 断言抛出 `HostDurableError`
  5. 如果 `IdempotencyRecord` 也应携带 typed kind，同理添加 `__post_init__`
- **修复风险（低）**: `__post_init__` 抛出 `HostDurableError` 而非 `ValueError` 符合现有错误惯例；当前所有生产路径传入的值都在闭集内，不会引入新失败。唯一风险是测试中如有直接构造非法 scope/result 但不经过 store 的代码——当前扫描未发现此类用例。
- **严重程度（中）**: 不阻塞 merge；当前 durable state 安全；但不满足 plan 3.4 "Validation: `IdempotencyScope` and `IdempotencyResultRef`" 的最强解读（构造期即 enforce）。Controller 已将此标记为 review focus。

### 2-未修复-低-payload_resolution 仍导入旧字符串常量而非 PayloadDescriptorKind 枚举成员

- **入口/函数**: `payload_resolution._validate_descriptor_kind` 的调用方
- **文件(行号)**: `dayu/host/payload_resolution.py:17`（导入 `TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND`），`dayu/host/payload_resolution.py:20`（导入 `TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`），`dayu/host/payload_resolution.py:247`（传入 `expected_kind=TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND`），`dayu/host/payload_resolution.py:298`（传入 `expected_kind=TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`）
- **输入场景**: 正常的 tool call arguments / semantic query payload 解析路径。
- **实际分支**: `_validate_descriptor_kind()` 在 `payload_resolution.py:335` 调用 `parse_payload_descriptor_kind(expected_kind)` 解析传入的字符串，该字符串是 `PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON.value` 的模块级常量别名。
- **预期行为**: Plan 3.5 写 "payload_resolution parses the caller-provided expected descriptor kind and fails closed only when descriptor metadata is missing or mismatched for that expected kind." 当前行为符合此要求。但 `payload_resolution` 作为 descriptor kind 的 consumer，同时导入 owner 模块的两个枚举别名（`TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND`、`TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`）而非直接使用 `PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON`，增加了间接层。
- **实际行为**: 功能正确——`_validate_descriptor_kind` 对 expected_kind 做 owner 解析，actual kind 也从 metadata JSON 解析后做 identity 比较。两个字符串常量均从 `PayloadDescriptorKind` 枚举值派生，语义上等价。
- **直接证据**:
  - `payload_resolution.py:17,20` 的 import 语句（见 `rg` 扫描输出）
  - `payload_resolution.py:247` 的 `expected_kind=TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND`
  - `payload_resolution.py:298` 的 `expected_kind=TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND`
  - `schema.py:300-302` 的 `TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND = PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON.value`
- **影响**: 不影响正确性——两个常量都是从同一 enum owner 派生的。但 `payload_resolution` 是 descriptor kind consumer，直接使用 `PayloadDescriptorKind` 枚举成员会比通过字符串常量别名更直接、更可搜索。当前间接层为未来新增 descriptor kind consumer 制造了不一致的 precedent：有的 consumer 使用 `PayloadDescriptorKind` 枚举（如 tool_runtime、run_input），有的使用字符串常量（如 payload_resolution）。
- **建议改法和验证点**:
  1. `payload_resolution.py` 改为导入 `PayloadDescriptorKind` 并使用 `PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON.value` 或直接传枚举成员（`parse_payload_descriptor_kind` 已接受 `str | PayloadDescriptorKind`）
  2. 或保留现状并在 plan/review 中明确记录"字符串常量与枚举成员等价使用是 colocation 策略的一部分"
- **修复风险（低）**: 纯 import 替换，`parse_payload_descriptor_kind()` 接受两种类型。
- **严重程度（低）**: 不阻塞 merge；不影响正确性；仅影响 consumer 端代码一致性。

### 3-未修复-低-IdempotencyRecord 三个 dataclass 的 kind 字段仍为 str，row decoder 已校验但 record 自身不携带类型信息

- **入口/函数**: `IdempotencyRecord.__init__`
- **文件(行号)**: `dayu/host/durable/idempotency.py:154` (`scope_kind: str`), `dayu/host/durable/idempotency.py:158` (`result_kind: str`)
- **输入场景**: `_idempotency_record_from_host_row()` 返回 `IdempotencyRecord` 后，consumer 读取 `record.result_kind` 做字符串比较。
- **实际分支**: `_idempotency_record_from_host_row()` 在 `idempotency.py:362-365` 先用 `_require_text` 提取字符串，再调用 `parse_idempotency_scope_kind(scope_kind)` 和 `parse_idempotency_result_kind(result_kind)` 做校验——但返回值被丢弃，record 的字段仍是原始字符串。`IdempotencyRecord` 本身的 `scope_kind: str` 和 `result_kind: str` 字段未改为 typed。
- **预期行为**: Plan 3.4 写 "replay / conflict helpers compare enum values or owner helper outputs, not naked strings." 当前 `record_idempotent_result()` 中 conflict 检测在 `idempotency.py:232` 比较 `semantic_input_digest`（digest 而非 kind），kind 比较不发生在 store 内部。但 consumer（如 admission replay helper）可能直接读取 `record.result_kind` 做字符串比较。
- **实际行为**: row decoder 已做 owner 校验（防止非法值从 durable store 进入 Python 内存），但 `IdempotencyRecord` 的字段类型仍为 `str`，consumer 拿到的是已校验但未 typed 的字符串。
- **直接证据**:
  - `idempotency.py:362-365`：`parse_idempotency_scope_kind(scope_kind)` 和 `parse_idempotency_result_kind(result_kind)` 的返回值未被赋值给 record 构造参数
  - `idempotency.py:366-384`：`IdempotencyRecord(...)` 构造时 `scope_kind=scope_kind`（原始字符串）和 `result_kind=result_kind`（原始字符串）
- **影响**: 低。row decoder 已保证只有合法值能通过 decode 进入 Python 内存，consumer 拿到的字符串一定是合法值。但不 typed 意味着 consumer 仍可能做裸字符串比较（如 `record.result_kind == "session"`），而非 `record.result_kind is IdempotencyResultKind.SESSION`。这在当前代码中不构成已知 bug。
- **建议改法和验证点**: 若后续 slice 要求 consumer 使用 typed kind，可将 `IdempotencyRecord.scope_kind` 和 `result_kind` 改为 `IdempotencyScopeKind` / `IdempotencyResultKind` 类型，row decoder 中直接将 parse 返回值赋给构造参数。
- **修复风险（低）**: 需检查所有 `IdempotencyRecord` consumer 是否做字符串比较并迁移。
- **严重程度（低）**: 防御性 finding；row decoder 已 fail closed；不阻塞 merge。

## Open Questions

- 无。所有 review 项均有直接证据支撑结论。

## Residual Risk

- **构造期校验缺失的 blast radius**: 若未来新增非 store 路径的 `IdempotencyScope` / `IdempotencyResultRef` consumer（如 audit log 序列化、diagnostic projection、跨进程 wire format），当前不校验构造期的设计可能导致非法值传播到非 store 上下文。建议在下一个接触 idempotency 数据结构的 slice 中补齐 `__post_init__` 校验（见 finding 1）。
- **`payload_resolution` 不校验无 `descriptor_kind` 的 metadata**: 当 producer 使用原始 `metadata={...}` 而不含 `descriptor_kind` 时，`_validate_payload_descriptor_metadata()` 静默放行。consumer 侧 `_validate_descriptor_kind()` 会 fail closed（"descriptor kind is missing"）。此设计是 plan 3.5 明确要求的行为（"PayloadStore validates explicit descriptor_kind metadata before write"），但失败推迟到 consumer 读取时才暴露。当前所有生产 producer 已迁移到 `payload_descriptor_metadata()`，此风险仅存在于直接调用 `write_sqlite_payload` / `write_payload_descriptor` 的测试或未来新增 producer。分类：accepted design tradeoff。
- **Idempotency scope_kind mutated-row 测试只覆盖 result_kind 篡改**: `test_idempotency_read_rejects_mutated_unknown_result_kind` 只测试了 result_kind 被篡改的场景。scope_kind 是主键的一部分，篡改 scope_kind 会导致 row 查找不到（而非读到非法值后被 decode 拒绝），因此 scope_kind 篡改的防护由主键唯一性和 WHERE 子句匹配提供。分类：accepted（主键提供等效防护）。
- **测试覆盖的整体评价**: 新增 8 个测试覆盖了 producer-side 非法值拒绝、consumer-side missing/mismatched rejection、row decoder 篡改拒绝、DDL 省略断言、owner value 稳定性、helper override 拒绝、以及 payload 写入的事务原子性（非法写入不残留行）。测试覆盖了真实 failure path（直接 SQL 篡改、构造非法 dataclass 经 store 写入），而非仅 happy path。剩余未覆盖的 failure path 已在上述 residual risk 中记录。
