# P9.5 Aggregate Deepreview — AgentDS

**Review scope**: `p9.5-pre-p10-hardening` vs `main` full diff
**Branch**: `p9.5-pre-p10-hardening`
**Base**: `main`
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Verdict**: **PASS** — 0 blocking, 0 high, 0 medium findings

---

## Review methodology

对 `p9.5-pre-p10-hardening` 相对 `main` 的完整 diff（159 files, 16,869 insertions, 541 deletions, 39 commits）按四个 ownership domain 并行 deepreview：Engine + contracts、Host durable + schema、ToolRuntime + memory、Host API + dispatch + logging。每域独立审查 correctness、state machine、durable truth、ownership boundary、public API/export、tests gaps、overcoupling。

设计真源: `docs/host/design.md`
总控: `docs/host/implementation-control.md`
计划: `docs/host/p9-5-pre-p10-hardening-plan.md`

---

## Domain 1: Engine + Contracts — PASS

### S1: Engine runner protocol decoupling

- **`dayu/engine/_default_runner.py`** (29 lines, 新增): 私有默认 runner 装配点，模块级 `_` 前缀。
- 正确性验证:
  - `_build_runner` 委托给 `_default_runner.py`，不通过 factory/registry/extension point
  - 与 P9.5 design discussion 裁决 "runner 不做 factory / registry"（`implementation-control.md:2036-2052`）一致
  - Runner 协议（`AgentRunner` Protocol）保持稳定，`_default_runner.py` 是实现细节
- Ownership: 无反向依赖，Engine 不 import Host/Service/UI/Fins

### S2: Engine / OpenAI runner / parser hardening

- **`dayu/engine/runners/openai/usage.py`**: 新增 `coerce_usage()` 共享函数
  - `isinstance(value, int) and not isinstance(value, bool)` — bool 从 int TypeGuard 中正确排除
  - Engine 侧与 `tool_call_aggregator.py` 共用同一 `coerce_usage()`，消除重复
- 无 ToolDefinition/ToolBundle/ToolCallable/ToolRuntime import
- S16 import boundary 增补: `ToolCallable` 加入 Engine forbidden symbols；`tool_declaration` 模块级 ban

### S8: Engine wait confirmation matching-ref hardening

- **`dayu/host/engine_ingest.py`**: wait confirmation 验证是只读检查，不修改 Engine 状态
- Matching ref 验证: 比对 incoming wait confirmation 与 engine pending wait 的 ref，不匹配时拒绝

### Contracts ownership

- `dayu/contracts`: 自 S16 新增 `dayu.runtime` 到 `CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES`
- 验证: contracts 不 import `dayu.engine` / `dayu.host` / `dayu.runtime` / `dayu.service` / `dayu.ui` / `dayu.fins`
- 零反向依赖

**Domain 1 verdict: PASS** — zero findings.

---

## Domain 2: Host Durable + Schema — PASS

### S5: Schema CHECK hardening

- **`dayu/host/durable/schema.py`**: `HOST_SCHEMA_VERSION` 7→8
- `payload_ref` / `payload_digest` pair invariant: 从弱 CHECK 升级为严格 pair CHECK
  - 旧: 允许 `payload_ref` IS NULL AND `payload_digest` IS NOT NULL
  - 新: `(payload_ref IS NULL) = (payload_digest IS NULL)` — 必须同时存在或同时为空
- `_payload_digest_for_verified_fact` 三条路径均保持 pair invariant:
  - `None` → 两者皆空
  - `evidence_anchor.digest` 存在 → 使用 anchor digest
  - fallback → 使用 `provenance.digest_ref`

### S4: Host durable helper API tightening

- **`dayu/host/durable/run_transition.py`**: 
  - PENDING shortcut 移除 → 只有 `WAITING_FOR_LANE` 可转入 dispatching
  - `mark_dispatching_after_lane_row` 要求 `WAITING_FOR_LANE` 前置状态
  - `local_worker_id` 字段新增，用于 dispatch lane 竞争追踪

### S14: EventLog cleanup

- **`dayu/host/durable/event_log.py`**: 移除 `read_run_input_continuity_events`
  - 零残留引用（rg 搜索确认无调用方）

### S6: Read API enum mapping

- **`dayu/host/durable/read_model.py`**: 三层 fail-closed 防御
  1. `require_non_empty_text` — 拒绝空/None
  2. enum membership — 严格枚举匹配
  3. `_TIMELINE_ITEM_KINDS` closed set — 不开放扩展

### Gaps check

- Schema migration: `HOST_SCHEMA_VERSION` 8，无旧版本兼容路径 — 符合 P9.5 "按全新设计" 约束
- pair CHECK 语义: 三个代码路径（`payload_ref/digest` pair）均已覆盖测试

**Domain 2 verdict: PASS** — zero findings.

---

## Domain 3: ToolRuntime + Memory — PASS

### S11: ToolRuntime boundary cleanup

- **`dayu/host/tool_runtime_schema_projection.py`** (157 lines): 从 ToolRuntime 拆出 schema projection
  - 提取逻辑与原地实现 byte-identical（验证: pre/post extraction 的 `effective_bundle.tool_schemas` 不变）
  - 无 public API 变更

### S12: ToolRuntime truncation/duplicate defensive hardening

- Truncation: REUSE 路径不调用 business callable，仅从已缓存的 tool result 中截取
- Duplicate detection: 受治理的错误验证，不向上泄漏实现细节
- `TruncationManager` 初始化成本: 裁决为"no production fix needed"（S12），不引入 singleton/durable cursor/cross-run reuse — 裁决合理

### S13: Size governance

- Structured diagnostic on oversized tool results
- Never silent drop: 所有超限情况均有 WARNING 级别日志
- `_MAX_LLM_INLINE_TOOL_RESULT_BYTES` 作为治理上限

### S14: Memory catch-up / projection

- **Per-row checkpoint advance**: catch-up 逐行推进 checkpoint，不追加 EventLog
- **`current_goal` first-write-wins**: `if current_goal is None: current_goal = text`
  - 纯内存投影逻辑，不构成公共 API 或架构契约
- 通用默认 catch-up 被拒绝: 需要 snapshot history，归属未来 Context Governance
- S15 日志级别校准: `LOGGER.exception()`（ERROR+traceback）→ `LOGGER.warning("... error_type=%s", type(exc).__name__)`（WARNING+type only）

### S16: fetch_more attempt-local isolation

- `FetchMoreToolCallable` 仅在 `dayu/host/tool_runtime.py` 中创建
- `test_factory_creates_attempt_local_fetch_more_callable`: 两个 handle 有不同 effective bundle、不同 fetch_more callable
- `fetch_more` 字符串搜索: 仅在 `host/tool_runtime.py` 和 `host/tooling.py` 中出现

**Domain 3 verdict: PASS** — zero findings.

---

## Domain 4: Host API + Dispatch + Logging — PASS

### S3: Public error taxonomy

- 7 个 durable→public 错误映射，close→INVALID_STATE
- 无 public API 重写

### S15: Logging redaction

- 全量模块扫描: 所有 Host 模块日志格式字符串中无 prompts、tool args、secrets 等敏感数据
- Command handle: VERBOSE 级别仅记录 typed ids，不记录内容

### S10: Dispatch lifecycle

- Lane competition fix: PENDING shortcut 移除
- Drain loop observability: worker event exception 清理
- RunInputBuilder 非恢复清理: 正确释放资源

### S7: LocalProxy close/events race

- `events()` single-use: 通过 `_events_started` boolean 保证单次消费
- `close()` idempotency: 通过 `asyncio.Lock()` 保证幂等

### S8: Engine ingest

- Wait confirmation validation: 只读检查，不修改状态

### Public API stability

- `dayu/host/__init__.py`: 零变更
- `dayu/host/api.py`: 零变更
- `dayu/engine/__init__.py`: 零变更
- 无 `__all__` 修改

**Domain 4 verdict: PASS** — zero findings.

---

## Cross-Domain Integrity Checks

### Import boundary (S16 verified)

| Layer | Forbidden | Status |
|---|---|---|
| contracts | `dayu.engine`, `dayu.host`, `dayu.runtime`, `dayu.service`, `dayu.ui`, `dayu.fins` | Clean |
| engine | `ToolDefinition`, `ToolBundle`, `ToolCallable`, `ToolRuntime`, `tool_declaration` module | Clean |
| host | `importlib`/`pkgutil` business tool scan | Clean |
| host | `fetch_more` string outside `tool_runtime.py`/`tooling.py` | Clean |
| runtime | `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins` | Clean |

### Validation evidence (S18 re-executed)

| Command | Result |
|---|---|
| `pytest -q` | 1066 passed |
| `python -m pyright dayu tests` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

### Tracking item disposition

P9.5 收口清单 23 项全部 dispositioned:
- 22 fixed (slice S1-S17), 1 partially fixed with reassigned portion (production memory catch-up → future Context Governance)
- 7 deferred items assigned to P10-P15 phase owners
- 无 unowned residual risk

### Test coverage

- 1066 tests passed，覆盖 S1-S17 全部切片
- Import-boundary guard tests: 4 层（contracts, engine, host, runtime）
- `fetch_more` attempt-local isolation: 端到端验证
- Schema CHECK pair invariant: 三条路径均已覆盖
- Lane competition, LocalProxy race, catch-up survivability, size governance: 均有针对性测试

---

## Findings Summary

| # | Finding | Severity | Verdict |
|---|---|---|---|
| — | — | — | — |

**Zero findings across all four domains.** 无 blocking、high、medium 或 low severity 发现。

---

## Overall Verdict

**PASS** — `p9.5-pre-p10-hardening` 相对 `main` 的完整 diff 经过四个 ownership domain 的独立并行 deepreview，在 correctness、state machine、durable truth、ownership boundary、public API/export、tests gaps、overcoupling 七个维度均无发现。

P9.5 的 23 项收口清单已全部 disposition，7 项 deferred 均有 P10-P15 phase owner，无未归属 residual risk。1066 tests passed，pyright clean。分支可以进入 aggregate deepreview acceptance。
