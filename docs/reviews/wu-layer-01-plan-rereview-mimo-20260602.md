# WU-LAYER-01 Plan Re-Review — AgentMiMo

- Reviewer: AgentMiMo
- Date: 2026-06-02
- Gate: plan re-review
- Controller adjudication: `docs/reviews/wu-layer-01-plan-review-controller-adjudication-20260602.md`
- Original review: `docs/reviews/wu-layer-01-plan-review-mimo-20260602.md`
- Revised plan: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md`

## 结论：PASS

ADJ-01 至 ADJ-05 全部关闭，修订未引入新 blocking plan 问题。Plan code-generation-ready。

---

## ADJ 关闭状态

### ADJ-01 CLOSED — schema definition validation 与 DDL CHECK slice dependency

修订内容：
- section 6.2 新增 "Slice dependency" 段落（line 153）：明确 Slice 2 修改 DDL CHECK 后必须重跑 Slice 1 schema definition validation tests。
- Slice 2 tests 新增条目（line 260）："Slice 1 schema definition validation tests are rerun after Slice 2 DDL CHECK helper extraction."
- Slice 2 expected assertions 新增（line 267）：要求证明 fresh bootstrap 与 expected SQL 仍同源，opener 不 false-positive。
- section 9 minimum assertions 新增（lines 330-331）：corrupted wait record 和 Slice 1 rerun 均列入最终验证。

判定：修订精确对齐 ADJ-01 要求，dependency 和验证策略均明确。

### ADJ-02 CLOSED — WaitRecord corrupted CAS scenario test

修订内容：
- Slice 2 tests 新增条目（line 258）：构造 `status='waiting'` 且 `terminal_at IS NOT NULL` 的 test-only row，断言 CAS 被拒绝并分类为 `CAS_LOST` 或 `INVALID_STATE`。
- 明确 corruption setup 为 test-only（direct SQLite mutation 或 `PRAGMA writable_schema`），生产代码不加 repair 逻辑。
- section 9 minimum assertions（line 331）将此场景列入最终验证。

判定：修订精确对齐 ADJ-02 要求，test-only 限定清晰。

### ADJ-03 CLOSED — `_row_rules.py` 与 `_validation.py` 职责边界

修订内容：
- section 6.2 新增 responsibility boundary 定义（lines 128-134）：
  - `_row_rules.py`：只承载 terminal status constants、terminal refs SQL fragments、wait terminal-at SQL fragments、terminal shape validation helpers；不承载 scalar validation、digest、timestamp、row decode、transaction、schema bootstrap、public API validation。
  - `_validation.py`：只承载 durable-private scalar validation 和 scalar conversion helpers；不得 import `_row_rules.py`。
  - `_row_rules.py` 不在 `dayu/host/durable/__init__.py` re-export。
- section 7（line 201-203）保持 one-way dependency 约束。

判定：修订精确对齐 ADJ-03 要求，职责边界和 no-re-export 均明确。

### ADJ-04 CLOSED — row decode `KeyError` wrapping

修订内容：
- section 6.3 新增 `_decode_*` helper error wrapping requirements（lines 174-179）：
  - catch `HostRow.get(...)` 的 `KeyError` → `HostRowDecodeError`。
  - catch scalar helpers 的 `HostDurableError` → `HostRowDecodeError`。
  - catch enum deserializers / terminal shape validators 的 `HostDurableError` → `HostRowDecodeError`。
  - 保留 `row_name` 和 `field_name`；row-level shape failures 设 `field_name=None`。
  - 保留原始异常为 `__cause__`（`raise ... from exc`）。

判定：修订精确对齐 ADJ-04 要求，error wrapping 路径完整且 `from exc` 链保留。

### ADJ-05 CLOSED — schema SQL normalization minimal spec

修订内容：
- section 6.1 新增 `_normalize_schema_sql` minimal spec（lines 107-113）：
  - strip leading/trailing whitespace。
  - collapse consecutive whitespace to single ASCII space。
  - preserve case exactly。
  - preserve identifier quoting exactly。
  - 不 reorder clauses、parse SQL、lower/upper-case keywords、remove quotes、normalize punctuation。
- 明确 stop condition（line 113）：若 SQLite 输出需要更宽规则，停止并回报 controller。
- Slice 1 expected assertions（line 233）新增 normalization 行为断言。

判定：修订精确对齐 ADJ-05 要求，minimal spec 边界清晰且有 stop condition。

---

## 新引入问题检查

修订内容均为对 ADJ findings 的精确补充，未改变 plan 整体架构、slice 划分、non-goals 或 stop conditions。未引入新 blocking plan 问题。

唯一新增的隐含约束是 Slice 2 的 implementation report 必须包含 Slice 1 rerun 结果和 fresh bootstrap 同源证明。这增加了 Slice 2 的报告工作量，但不改变 slice 范围或 allowed files，属于合理验证要求。
