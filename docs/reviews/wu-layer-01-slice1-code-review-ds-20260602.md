# WU-LAYER-01 Slice 1 Code Review — AgentDS

## Conclusion: PASS

No blocking findings. Slice 1 implementation correctly delivers schema definition validation with:
- single-source DDL truth (no second hand-written DDL),
- fail-closed only (no repair/migrate),
- minimum whitespace-only normalization,
- type-safe parameterized queries,
- focused tests covering all required scenarios,
- no scope creep into Slice 2/3 or WU-LAYER-02.

## Review Scope

- **Plan**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`
- **Implementation artifact**: `docs/reviews/wu-layer-01-slice1-schema-definition-validation-codex-20260602.md`
- **Changed files reviewed**:
  - `dayu/host/durable/schema.py` (diff)
  - `tests/host/test_durable_schema.py` (diff)
  - `docs/host/host-core-followup-implementation-control.md` (controller bookkeeping only)
- **Review criteria**: correctness, stability, maintainability, adversarial failure pass, AGENTS.md compliance.

---

## Findings

### Finding 1 — Informational: `_sqlite_placeholders` guard clause is unreachable in practice

- **Severity**: Informational
- **Evidence**: `dayu/host/durable/schema.py:1519-1522`
- **Issue**: `_sqlite_placeholders` raises `HostSchemaMismatchError("required object set is empty")` when `value_count <= 0`. The callers (`_read_schema_sql_by_name:1459-1460`) pass `len(HOST_DURABLE_TABLES)` and `len(HOST_DURABLE_INDEXES)`, which are module-level non-empty tuple constants. The guard is unreachable in practice.
- **Impact**: None at runtime. The error type (`HostSchemaMismatchError`) slightly mischaracterizes what would be a programming error (empty constant) as a schema mismatch. But consistent with the module's convention of using `HostSchemaMismatchError` for all validation failures.
- **Recommendation**: Accept as-is. The guard is defensive and fails fast with a clear message. Not worth changing error type for an unreachable path.

### Finding 2 — Informational: `_expected_schema_sql_by_name()` recomputes on every validation call

- **Severity**: Informational
- **Evidence**: `dayu/host/durable/schema.py:1422-1448` called from `_validate_required_object_definitions:1410`, which is called from `validate_host_durable_schema:1327`.
- **Issue**: Every call to `validate_host_durable_schema` (including secondary `store.connect()`) creates a new `:memory:` SQLite DB and executes full `HOST_DURABLE_DDL`. No caching.
- **Impact**: Negligible — `HOST_DURABLE_DDL` is ~30 statements, in-memory SQLite execution is sub-millisecond. The design is intentional: every call verifies against the current in-process DDL truth, avoiding staleness if `HOST_DURABLE_DDL` were hypothetically mutated at runtime (e.g., by tests via `monkeypatch`).
- **Recommendation**: Accept as-is. The correctness guarantee (always current DDL truth) outweighs any performance concern.

### Finding 3 — Informational: Test-private constants duplicate production values

- **Severity**: Informational
- **Evidence**: `tests/host/test_durable_schema.py:86-90` defines `_SQLITE_OBJECT_TYPE_TABLE = "table"` and `_SQLITE_OBJECT_TYPE_INDEX = "index"`, duplicating `schema.py:1253-1257` (`_SCHEMA_OBJECT_TYPE_TABLE`, `_SCHEMA_OBJECT_TYPE_INDEX`).
- **Issue**: Same values defined in test and production code. If SQLite ever changed these catalog type names (will not happen), the constants would diverge silently.
- **Impact**: None. SQLite `sqlite_master.type` values are stable and will never change. Tests correctly avoid importing private `_SCHEMA_*` constants.
- **Recommendation**: Accept as-is. Test isolation from private implementation constants is the right pattern.

---

## Review Criteria Walkthrough

### 1. Schema expected SQL generation 是否同源于 HOST_DURABLE_DDL

**PASS.** `_expected_schema_sql_by_name()` (`schema.py:1422`) creates an in-memory SQLite DB, executes `HOST_DURABLE_DDL`, and reads `sqlite_master.sql` from that DB. No second hand-written DDL string set exists anywhere. The function also self-verifies that all required objects appear in the generated catalog (`schema.py:1442-1447`).

### 2. validate_host_durable_schema 是否仍 fail closed 且不 repair/migrate

**PASS.** `_validate_required_object_definitions` (`schema.py:1397`) only reads and compares — it executes no `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, or `DELETE`. On mismatch it raises `HostSchemaMismatchError`. Tests confirm:

- `test_current_schema_wrong_index_definition_opener_raises_without_repair` (`test:531`): wrong index persists after error.
- `test_current_schema_mutated_table_definition_opener_raises_without_repair` (`test:571`): mutated `sqlite_master.sql` persists after error.
- `test_secondary_connection_definition_mismatch_raises_without_repair` (`test:666`): secondary connection also fail-closed only.

### 3. _normalize_schema_sql 是否只做最小 whitespace normalization

**PASS.** `_normalize_schema_sql` (`schema.py:1497`) applies `_WHITESPACE_RUN_PATTERN.sub(" ", sql.strip())` — only strip + collapse consecutive whitespace. No SQL parsing, no case folding, no quote stripping, no clause reordering. `test_normalize_schema_sql_only_strips_and_collapses_whitespace` (`test:752`) proves all five negative cases:

| Input variation | Expected behavior | Verified |
|---|---|---|
| Extra whitespace (`\n\t`, multiple spaces) | Normalized to match base | Yes |
| Case change (`create` vs `CREATE`) | NOT normalized away | Yes |
| Quote change (`host_runs` vs `"host_runs"`) | NOT normalized away | Yes |
| Clause addition (`WITHOUT ROWID`) | NOT normalized away | Yes |
| Punctuation change (space before `(`) | NOT normalized away | Yes |

### 4. sqlite_master query/placeholders 类型安全、无 SQL 注入、无空集合隐患

**PASS.** All user values go through `?` placeholders. The `.format()` call (`schema.py:1462-1464`) only inserts `{table_placeholders}` and `{index_placeholders}`, both generated by `_sqlite_placeholders` which produces only comma-separated `?` characters — no string concatenation of user input. `_sqlite_placeholders` (`schema.py:1511`) guards against `value_count <= 0` with an explicit raise.

### 5. Tests coverage

**PASS.** All five required test scenarios are covered:

| Required scenario | Test | Evidence |
|---|---|---|
| Wrong index definition, opener fail-closed | `test_current_schema_wrong_index_definition_opener_raises_without_repair` | `test:531` |
| Mutated table definition, opener fail-closed | `test_current_schema_mutated_table_definition_opener_raises_without_repair` | `test:571` |
| Secondary connection mismatch, fail-closed | `test_secondary_connection_definition_mismatch_raises_without_repair` | `test:666` |
| Fresh bootstrap false-positive check | `test_fresh_bootstrapped_schema_matches_generated_expected_sql` | `test:729` |
| Normalization negative cases (5 assertions) | `test_normalize_schema_sql_only_strips_and_collapses_whitespace` | `test:752` |

Existing tests (`test_current_schema_missing_table_opener_raises_without_repair`, `test_current_schema_missing_index_opener_raises_without_repair`, `test_host_durable_tables_match_create_table_ddl`, `test_host_durable_indexes_match_create_index_ddl`) continue to pass, confirming no regression.

### 6. Scope boundary — 是否越界实现 Slice 2/3 或 WU-LAYER-02

**PASS.** Diff touches only `schema.py` and `test_durable_schema.py` (Slice 1 allowed files). No changes to:
- `dayu/host/durable/state.py` (Slice 2/3)
- `dayu/host/durable/errors.py` (Slice 3)
- Any `_row_rules.py` (Slice 2)
- Any WU-LAYER-02 modules

### 7. AGENTS.md compliance — docstring/type/signature

**PASS.** All six new functions have complete Chinese docstrings with `:param`, `:returns`, `:raises`. All parameters and returns are fully typed. No `Any`, `object`, untyped params, `hasattr`/`getattr`, lazy imports, or extra payload. Module-level constants (`_SCHEMA_OBJECT_TYPE_TABLE`, `_SCHEMA_OBJECT_TYPE_INDEX`, `_SQLITE_MASTER_SQL_QUERY_TEMPLATE`, `_WHITESPACE_RUN_PATTERN`, `_SchemaObjectKey`) all have Chinese docstrings.

### 8. Controller bookkeeping

**PASS.** `docs/host/host-core-followup-implementation-control.md` updates are accurate:
- `gate: implementation` — correct for code review phase
- `implementation status` — accurately reflects Slice 1 complete, review pending
- `current slice: WU-LAYER-01 Slice 1 code review` — correct
- `implementation artifact` — correctly points to Codex implementation report
- `validation` — matches reported 33 passed, pyright 0 errors
- `next entry point: WU-LAYER-01 Slice 1 code review` — accurate

---

## Adversarial Failure Pass

| Scenario | Outcome |
|---|---|
| SQLite produces different whitespace on different platforms | Handled by normalization; same-process guarantee validated by `test_fresh_bootstrapped_schema_matches_generated_expected_sql` |
| New table added to DDL but not to `HOST_DURABLE_TABLES` | Caught by existing `test_host_durable_tables_match_create_table_ddl` |
| `sqlite_master.sql` is NULL for a required object | Treated as missing definition → `HostSchemaMismatchError` raised correctly |
| Required object missing from `sqlite_master` entirely | Caught first by existence checks (`_validate_required_tables` / `_validate_required_indexes`) |
| `HOST_DURABLE_TABLES` or `HOST_DURABLE_INDEXES` empty | `_sqlite_placeholders` raises (defensive, unreachable in practice) |
| `_normalize_schema_sql` false-positive match | Cannot happen — only whitespace is normalized; case, quotes, clauses, punctuation are preserved |
| Unicode whitespace in catalog SQL | `\s` matches Unicode whitespace (no `re.ASCII` flag), but SQLite catalog SQL is ASCII-only |

---

## Open Questions

None.

## Residual Risks

1. **Cross-platform SQLite catalog SQL stability**: `_normalize_schema_sql` only handles whitespace. If a future SQLite version changes identifier quoting or keyword casing in `sqlite_master.sql`, the comparison would false-positive. Per plan stop condition: "If implementation evidence shows current SQLite output needs a broader normalization rule, stop and report back to controller." The current test `test_fresh_bootstrapped_schema_matches_generated_expected_sql` validates this on Python 3.11 sqlite3.

2. **Slice 2/3 dependency**: Slice 2 will modify DDL CHECK fragments. Per plan, Slice 2 must rerun Slice 1 schema definition validation tests after DDL CHECK helper extraction. This dependency is documented in the plan but not yet exercised.

3. **No cache for `_expected_schema_sql_by_name()`**: As noted in Finding 2, every `store.connect()` creates a new in-memory DB. Currently negligible; worth monitoring if secondary connection frequency increases significantly.
