# Phase 15 P15-S6 Code Review

- Gate: Phase 15 Slice P15-S6 Docs, Import Boundaries, Full Validation
- Role: AgentMiMo code review specialist
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md` Slice P15-S6
- Implementation artifact: `docs/reviews/phase15-s6-implementation-codex-20260529.md`
- Review scope: workspace diff only (5 files, +94 / -4 lines)

## Verdict

**PASS** — 无 blocker，无 major findings。

## Changed Files

| File | Lines | Nature |
|------|-------|--------|
| `dayu/host/README.md` | +10 / -1 | Docs: purge current-fact sync |
| `tests/README.md` | +4 / -3 | Docs: test fact sync |
| `tests/host/test_import_boundary.py` | +35 | Test guard: purge durable import boundary |
| `tests/host/test_package_exports.py` | +35 | Test guard: purge durable symbol leakage |
| `tests/host/test_weak_typing_guard.py` | +11 | Test guard: purge durable weak typing scan |

## Findings

### INFO-01: Host README purge 段落准确覆盖已实现事实

**Severity**: INFO

**Verified points**:

- Service-facing 入口描述了 `Host.purge_session(session_id, request)` 与包根 command facade `purge_session(host, session_id, request)` — 对应 P15-S3 已实现的两条调用路径。
- 前置条件准确列出 `CLOSED`、无 active / queued / waiting / cancelling / recovering Run、所有 Run 终态 — 与 `PURGE_DURABLE_FORBIDDEN_PREFIXES` 和实际 `purge_session_durable` 一致。
- 删除范围覆盖 Session / slot binding、Run、Attempt、EventLog rows、payload descriptor / 本地 SQLite payload、memory snapshot、minimal read model、projection checkpoint / failure、outbox terminal projection、tool trace hot rows、旧 command idempotency rows — 与 S2 delete matrix 完全对应。
- 共享 artifact 的 "只在没有其它 durable ref 引用时清理" 限制条件 — 与 payload cleanup ref-count 设计一致。
- Tombstone 不参与 resume / retry / replay / memory / RunInputBuilder / 普通 read truth — 与 plan 的 governance truth 约束一致。
- 幂等重放语义（同请求 replay、同 key 不同语义 `IDEMPOTENCY_CONFLICT`、不同请求 `CONFLICT`）— 与 S1 idempotency design 一致。
- Read-after-purge 不从 tombstone / projection / audit / outbox / tool trace / memory 重建，返回 `NOT_FOUND` — 与 S3 read-after-purge 语义一致。
- Audit JSONL append-only 保留 + purge tombstone audit record — 与 S4 audit retention 一致。
- Non-goals 列表完整（remote / wire、public error code、close / cancel / archive / memory forget / UI hide、retention scheduler、周期 GC、DB vacuum、audit JSONL rotation / compaction、外部 audit 投递、tool trace cold JSONL retention policy）— 与 plan non-goals 完全对应。

**未提升为 Service-facing contract 的 internal helpers**：README 中未出现 `purge_session_durable`、`PurgeTombstoneRow`、`record_or_read_purge_idempotency` 等 durable 内部符号作为 public contract 描述，只以自然语言描述行为语义。正确。

**结论**：Host README 准确、完整、无越界。

### INFO-02: tests README 同步当前事实

**Severity**: INFO

**Verified points**:

- `purge_session` 覆盖描述已更新为 "已关闭且全部 Run 终态 Session 的 tombstone result、幂等重放、同 key 不同语义冲突、不同请求访问已 purge Session 冲突、append-only audit JSONL tombstone record 和 purge 后 read path `NOT_FOUND`" — 与实际测试 `test_purge_session.py` 对应。
- import boundary 描述新增 "显式覆盖 `dayu.host.durable.purge` 不依赖上层、runtime、public command owner 或 audit / dispatch owner" — 与新增 `test_purge_durable_module_stays_low_level_host_owner` 对应。
- weak typing guard 描述新增 "显式确认 `dayu.host.durable.purge` 被纳入扫描" — 与新增 `test_explicit_host_modules_are_covered_by_weak_typing_scan` 对应。

**无过程/未来计划写入**。正确。

### INFO-03: import boundary guard 正确覆盖 `dayu.host.durable.purge`

**Severity**: INFO

**验证**：

- `PURGE_DURABLE_MODULES = ("durable/purge.py",)` 精确限定扫描目标。
- `PURGE_DURABLE_FORBIDDEN_PREFIXES` 包含 12 个 forbidden 前缀：`dayu.config`、`dayu.engine`、`dayu.fins`、`dayu.runtime`、`dayu.service`、`dayu.ui`、`dayu.host.admission`、`dayu.host.audit`、`dayu.host.command`、`dayu.host.dispatch`、`dayu.host.open_host`、`dayu.host.recovery`。
- 实际 `purge.py` 的 imports：`dayu.contracts.json_value`、`dayu.host.durable._validation`、`dayu.host.durable.codec`、`dayu.host.durable.errors`、`dayu.host.durable.idempotency`、`dayu.host.durable.schema` — 全部为 `dayu.host.durable.*` 或 `dayu.contracts.*`，不命中任何 forbidden prefix。
- 测试结构复用了既有 `_imported_module_names` / `_matches_prefix` helper，与 memory modules 测试模式一致。

**结论**：import boundary 覆盖正确，无遗漏。

### INFO-04: package exports guard 正确防止 purge durable 符号泄漏

**Severity**: INFO

**验证**：

- `INTERNAL_PURGE_DURABLE_EXPORTS` 包含 23 个符号，与 `purge.py` 的 `__all__`（23 项）完全一致 — 逐项比对无遗漏、无多余。
- 新增 `test_purge_durable_symbols_are_not_package_root_exports` 同时断言 `host.__all__` 和 `vars(host)` 均不包含这些符号 — 防止 `__all__` 泄漏和模块属性泄漏两条路径。
- 测试模式与既有 `REMOVED_SERVICE_FACING_ALL_EXPORTS` guard 一致。

**结论**：package exports guard 完整正确。

### INFO-05: weak typing guard 显式确认 purge 模块被扫描

**Severity**: INFO

**验证**：

- `EXPLICIT_WEAK_TYPING_SCAN_FILES = frozenset({"durable/purge.py"})` 精确指定。
- `test_explicit_host_modules_are_covered_by_weak_typing_scan` 断言 `EXPLICIT_WEAK_TYPING_SCAN_FILES <= scanned_files` — 确保 `_iter_files()` 收集的扫描范围包含 purge.py。
- 测试语义为正向断言（"必须在扫描范围内"），不依赖特定违规内容，适合 regression guard。

**结论**：weak typing guard 覆盖正确。

### INFO-06: 无业务行为变更

**Severity**: INFO

**验证**：

- `dayu/host/README.md`：纯文档更新，不改代码。
- `tests/README.md`：纯文档更新，不改代码。
- `tests/host/test_import_boundary.py`：新增测试函数 + 常量，不改现有测试逻辑。
- `tests/host/test_package_exports.py`：新增测试函数 + 常量，不改现有测试逻辑。
- `tests/host/test_weak_typing_guard.py`：新增测试函数 + 常量，不改现有测试逻辑。
- 无 Engine / Service / UI / Fins / Remote / `OpenHostOptions` / public API shape 变更。
- 无 `dayu/host/durable/purge.py` 或任何 `dayu/` 源码变更 — 仅 test guard 和 docs。

**结论**：符合 S6 scope（docs, import boundaries, full validation only）。

### INFO-07: 验证命令覆盖 plan

**Severity**: INFO

**Plan S6 要求**：

```
pytest tests/host/test_purge_session.py tests/host/test_durable_schema.py tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_audit_sink.py tests/host/test_projection_read_model.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py tests/host/test_open_host_runtime.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
```

**Implementation artifact 记录**：

- Focused guard sanity：25 passed (3 guard files)。
- Required focused P15 suite：227 passed (16 test files，与 plan 一致)。
- Required pyright：0 errors, 0 warnings, 0 informations。

**结论**：验证命令与 plan 完全匹配，结果均通过。

## Adversarial Failure Pass

| Attack vector | Result |
|---------------|--------|
| purge.py `__all__` 与 test `INTERNAL_PURGE_DURABLE_EXPORTS` 不一致 | 已验证 23 对 23，完全一致 |
| purge.py 实际 import 了 forbidden prefix 模块 | 已验证实际 imports 全部为 `dayu.host.durable.*` / `dayu.contracts.*`，无 forbidden |
| Host README 提升了 internal helpers 为 public contract | 已验证 README 仅描述行为语义，不暴露 internal 符号名 |
| tests README 写入了过程/未来计划 | 已验证仅同步当前测试事实 |
| S6 scope 越界改了 production code | 已验证仅 docs + test guards |
| validation commands 不完整 | 已验证 16 test files + pyright 与 plan 一致 |
| weak typing scan 未覆盖 purge.py | 已验证显式正向断言 `EXPLICIT_WEAK_TYPING_SCAN_FILES <= scanned_files` |
| purge durable 符号泄漏到 `host.__all__` 或 `vars(host)` | 已验证双路径断言均 PASS |

## Project Constraint Compliance

| Constraint | Status |
|------------|--------|
| 中文 docstring（函数至少含参数/返回值/异常） | N/A — 无新增函数 |
| 禁止 `object` / `Any` / 无类型签名 | N/A — 无新增代码 |
| README 只写已实现事实 | PASS |
| README 不写过程/未来计划 | PASS |
| test guard 跟随实现边界迁移 | PASS |
| 无反向依赖 | PASS |
| 无 Engine 变更 | PASS |

## Residual Risks

- 无当前 slice 残留风险。
- P15 整体 follow-up（retention scheduler / cold JSONL / external audit / remote wire protocol）由 plan non-goals 明确排除，归后续 owner。
