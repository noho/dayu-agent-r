# Phase 15 P15-S6 Code Review — AgentDS

- **Gate**: Phase 15 Slice P15-S6 code review
- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/reviews/phase15-s6-implementation-codex-20260529.md` + workspace diff
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md` Slice P15-S6
- **Date**: 2026-05-29

## Verdict: PASS — No findings

All 5 changed files are within P15-S6 scope (docs + test guard only). No business behavior, public API shape, Engine/Service/UI/Fins/Remote, or `OpenHostOptions` changes. All validation commands pass.

---

## Review Checklist

### 1. Host README (`dayu/host/README.md`) — PASS

**Requirement**: 只写当前已实现事实，准确覆盖 purge preconditions、tombstone、audit JSONL retention、read-after-purge NOT_FOUND、non-goals，且不把 internal durable/audit helpers 提升为 Service-facing contract。

**Evidence**:

- 修正了 command facade 签名为 `purge_session(host, session_id, request)`（原文本遗漏了 `host` 参数，现与 `command.py:769` 一致）。
- 明确 Service-facing 入口为 `Host.purge_session(session_id, request)` 与包根 `purge_session(host, session_id, request)`。
- 前置条件描述准确：`CLOSED`、无 active / queued / waiting / cancelling / recovering Run、全部 Run 终态；不满足返回 `INVALID_STATE`。
- Tombstone 行为描述准确：同事务保留独立 purge tombstone 和幂等记录；tombstone 不位于被 purge 的 Session EventLog 中；不参与 resume / retry / replay / memory / RunInputBuilder / 普通 read truth。
- Audit JSONL retention 描述准确：不删除不重写 append-only audit JSONL；写入 purge tombstone audit record 并将 ref / digest 写入 tombstone；既有 audit 行保留对已删除 EventLog rows 的 refs。
- Read-after-purge 行为准确：`NOT_FOUND` 语义；不从 tombstone、projection、audit、outbox、tool trace 或 memory 重建事实。
- 明确区分 Service-facing 读取路径与 audit/diagnostic 查询路径：`"audit / diagnostic 查询可以用 tombstone 解释源事实已被 purge，但普通 Service-facing 读取路径不能把 audit、projection 或 tombstone 当作 Session snapshot 来源"`。
- Non-goals 完整列出：不做 remote/wire protocol 变更、不新增 public error code、不实现 scheduler/GC/vacuum/rotation/compaction/external audit delivery/cold tool trace retention policy。
- 未暴露 internal helper 名称（如 `PurgeTombstoneRow`、`purge_session_durable` 等）。
- 无"未来设计"或"计划中"表述。

### 2. Tests README (`tests/README.md`) — PASS

**Requirement**: 只同步当前测试事实，不写过程/未来计划。

**Evidence**:

- command handle / public session API 段落从泛化的 `"已关闭 Session 的 tombstone result、幂等重放和 purge 后 read path NOT_FOUND"` 细化为 `"已关闭且全部 Run 终态 Session 的 tombstone result、幂等重放、同 key 不同语义冲突、不同请求访问已 purge Session 冲突、append-only audit JSONL tombstone record 和 purge 后 read path NOT_FOUND"` — 全部为当前已存在测试覆盖的事实。
- import boundary 段落追加 `"显式覆盖 dayu.host.durable.purge 不依赖上层、runtime、public command owner 或 audit / dispatch owner"` — 描述新增测试 `test_purge_durable_module_stays_low_level_host_owner`。
- weak typing guard 段落追加 `"并显式确认 dayu.host.durable.purge 被纳入扫描"` — 描述新增测试 `test_explicit_host_modules_are_covered_by_weak_typing_scan`。
- 无过程历史、无未来计划、无时间敏感信息。

### 3. Import Boundary (`tests/host/test_import_boundary.py`) — PASS

**Requirement**: 正确覆盖 `dayu.host.durable.purge`，没有新增 public export 或反向依赖。

**Evidence**:

- 新增 `PURGE_DURABLE_MODULES = ("durable/purge.py",)` 与 `PURGE_DURABLE_FORBIDDEN_PREFIXES` 精确列出禁止依赖的上层模块：`dayu.config`、`dayu.engine`、`dayu.fins`、`dayu.runtime`、`dayu.service`、`dayu.ui`，以及 Host 内部高层模块 `dayu.host.admission`、`dayu.host.audit`、`dayu.host.command`、`dayu.host.dispatch`、`dayu.host.open_host`、`dayu.host.recovery`。
- 新增 `test_purge_durable_module_stays_low_level_host_owner()` 通过 AST import 扫描验证 `durable/purge.py` 不导入任何禁止前缀。
- 禁止列表合理：purge durable 是低层原语，不应依赖 command / audit / dispatch / opener / recovery 等高层 Host 模块；遵循 Host 内部分层方向。
- 未新增对 `dayu.host.durable` 自身的禁止（purge 是 durable 子模块，依赖同包模块合法）。

### 4. Package Exports (`tests/host/test_package_exports.py`) — PASS

**Requirement**: 正确覆盖 purge 相关符号不进入 public namespace。

**Evidence**:

- 新增 `INTERNAL_PURGE_DURABLE_EXPORTS` frozenset 包含 25 个 purge durable 内部符号（dataclass、helper 函数、常量、错误类型）。
- 新增 `test_purge_durable_symbols_are_not_package_root_exports()` 双重断言：既不出现于 `host.__all__`，也不出现于 `vars(host)` 模块属性。
- 白名单覆盖了 plan 中列出的所有 purge durable primitives：`PurgeTombstoneRow`、`PurgeDeleteCounts`、`PurgePreconditionSnapshot`、`PurgeReplayDecision`、`PurgeReplayDecisionKind`、`build_purge_semantic_digest`、`build_deleted_counts_digest`、`insert_purge_tombstone`、`read_purge_tombstone_by_id`、`read_purge_tombstone_by_session_id`、`record_or_read_purge_idempotency`、`purge_session_durable` 及审计相关类型。
- 未新增 public export。

### 5. Weak Typing Guard (`tests/host/test_weak_typing_guard.py`) — PASS

**Requirement**: 正确覆盖 `dayu.host.durable.purge` 的弱类型扫描。

**Evidence**:

- 新增 `EXPLICIT_WEAK_TYPING_SCAN_FILES = frozenset({"durable/purge.py"})`。
- 新增 `test_explicit_host_modules_are_covered_by_weak_typing_scan()` 断言 `durable/purge.py` 在 `_iter_files()` 扫描范围内，从而被 `test_host_disallows_weak_typing()` 覆盖。
- 不重复实现弱类型检查逻辑，正确复用已有 AST 扫描基础设施。

### 6. 禁止修改范围检查 — PASS

**Requirement**: 没有业务行为改动、没有 Engine/Service/UI/Fins/Remote/OpenHostOptions/public API shape 变化。

**Evidence**:

- Diff 仅涉及 5 个文件：`dayu/host/README.md`、`tests/README.md`、`tests/host/test_import_boundary.py`、`tests/host/test_package_exports.py`、`tests/host/test_weak_typing_guard.py`。
- 零 `dayu/engine/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/runtime/**` 变更。
- 零 RemoteProxy / RemoteStub / wire protocol 变更。
- 零 `OpenHostOptions` 字段变更。
- 零 `Host` public method shape 变更。
- 零 `PurgeSessionRequest` / `PurgeSessionResult` / public error code 变更。

### 7. 验证命令覆盖率 — PASS

**Requirement**: 验证命令覆盖 plan 定义的 S6 验证范围。

**Evidence** (来自 implementation artifact):

| 验证命令 | 结果 |
| --- | --- |
| `pytest tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q` | 25 passed |
| `pytest tests/host/test_purge_session.py ... (完整 P15 16 文件) -q` | 227 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

验证命令与 plan Slice P15-S6 中规定的命令一致，覆盖率完整。

---

## Adversarial Failure Pass

以下 adversarial 场景均已检查并通过：

| 场景 | 结论 |
| --- | --- |
| README 描述了未实现的功能 | 否 — 所有描述对应 S1-S5 已实现行为 |
| README 将 internal helper 暴露为 Service-facing contract | 否 — 未出现 `PurgeTombstoneRow`、`purge_session_durable` 等内部符号名 |
| tests README 写了过程/未来计划 | 否 — 仅描述当前测试事实 |
| import boundary 测试遗漏反向依赖方向 | 否 — forbidden 列表覆盖 config/engine/fins/runtime/service/ui + 6 个 Host 高层模块 |
| package exports 测试仅检查 `__all__` 遗漏 `vars()` | 否 — 双重断言 |
| weak typing guard 仅声明文件应被扫描但未验证 | 否 — 使用 `<=` 子集断言确认文件在扫描范围内 |
| 业务行为被意外修改 | 否 — 零生产代码变更 |
| pyright 报错被掩盖或扩散 | 否 — 0 errors |

---

## 项目指令检查

| 指令 | 状态 |
| --- | --- |
| 中文 docstring | 新增测试函数均有中文 docstring（参数、返回值、异常） |
| 禁止 `object`/`Any`/无类型签名 | 新增代码无此类违规（测试文件在弱类型扫描覆盖范围内） |
| 禁止魔法数字/字符串 | 新增常量均使用模块级 `frozenset` / `tuple` |
| 禁止兼容性代码 | 无 compat re-export / wrapper / facade |
| 架构分层 | purge durable 禁止依赖上层，与分层方向一致 |
| README 触发规则 | Host README 与 tests README 均命中触发条件且更新内容在职责范围内 |

---

## 总结

- **Blocker**: 0
- **Warning**: 0
- **Info**: 0
- **Verdict**: **PASS** — Slice P15-S6 实现完全符合 plan 要求。所有变更为 docs 与 test guard 同步，无业务行为改动，无架构边界违反，验证全部通过。
