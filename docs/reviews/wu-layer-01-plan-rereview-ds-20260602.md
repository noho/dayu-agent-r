# WU-LAYER-01 Plan Re-Review — AgentDS

**Reviewer**: AgentDS
**Date**: 2026-06-02
**Gate**: plan re-review
**Target**: `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md` (revised)
**Adjudication source**: `docs/reviews/wu-layer-01-plan-review-controller-adjudication-20260602.md`
**Original review**: `docs/reviews/wu-layer-01-plan-review-ds-20260602.md`

## 结论：PASS

全部 ADJ-01 至 ADJ-05 已关闭。修订后的 plan 无 blocking finding，无新增 plan 问题。Plan is code-generation-ready。

---

## ADJ 关闭逐项复核

### ADJ-01 [CLOSED] — schema definition validation 与 DDL CHECK 重组的 slice dependency

**要求**: Slice 2 修改 DDL CHECK 片段后必须重跑 Slice 1 definition validation tests；SQL 文本变化时必须证明同源且 opener 不误报。

**修订证据**:
- Plan:153 新增 Slice dependency 段落，明确 Slice 2 depends on Slice 1，要求 rerun Slice 1 tests，并要求 implementation report 证明 fresh bootstrap + expected SQL 同源
- Plan:261 Slice 2 tests 中明确 "Slice 1 schema definition validation tests are rerun after Slice 2 DDL CHECK helper extraction"
- Plan:267 Slice 2 expected assertions 中明确 "implementation report must show fresh bootstrap and expected SQL remain same-source"
- Plan:330 validation 要求中明确 "Slice 2 reruns Slice 1 schema definition validation tests"
- Plan:343 aggregate review gate 中增加到 "Slice 2 reran Slice 1 definition validation coverage"

**复核**: 5 处修改点覆盖完整——从 plan decision (section 6.2)、slice tests (section 8)、expected assertions (section 8)、validation commands (section 9) 到 aggregate review gate (section 10) 均明确了 slice dependency 和 rerun 要求。已关闭。

---

### ADJ-02 [CLOSED] — WaitRecord corrupted CAS scenario test

**要求**: 显式加入 corrupted wait record scenario，断言 CAS 被拒绝并分类为 CAS_LOST 或 INVALID_STATE；构造方式限定为 test-only。

**修订证据**:
- Plan:258-259 Slice 2 tests 中新增完整 corrupted scenario 描述："construct a test-only row with `status='waiting'` and `terminal_at IS NOT NULL`, then invoke a wait terminal CAS path and assert the CAS is rejected and classified as `CAS_LOST` or `INVALID_STATE`. The corruption setup must be explicitly test-only, for example via direct SQLite mutation under test control or `PRAGMA writable_schema` / constraint bypass if needed; production code must not add repair logic or a special corruption branch."
- Plan:331 validation 要求中明确 "Corrupted wait record with `status=waiting` and non-null `terminal_at` is rejected by terminal CAS and classified as `CAS_LOST` or `INVALID_STATE` through a test-only setup"
- Plan:346 aggregate review gate 中增加 "corrupted wait record CAS scenario exists and is test-only"

**复核**: Scenario 完整定义了输入状态（waiting + non-null terminal_at）、触发路径（wait terminal CAS）、期望结果（CAS_LOST or INVALID_STATE）、构造约束（test-only, PRAGMA writable_schema if needed, no production repair branch）。已关闭。

---

### ADJ-03 [CLOSED] — `_row_rules.py` 与 `_validation.py` 职责边界

**要求**: 明确 `_row_rules.py` 只承载 terminal 规则、`_validation.py` 只承载 scalar validation；`_row_rules.py` 不在 `__init__.py` re-export。

**修订证据**:
- Plan:128-131 `_row_rules.py` responsibility boundary 正面定义："owns only terminal status constants, terminal refs SQL fragments, wait terminal-at SQL fragments, and terminal shape validation helpers; does not own scalar type validation, digest validation, timestamp formatting/parsing, canonical JSON, row decode, transaction behavior, schema bootstrap, or public API validation; is durable-private and must not be re-exported from `dayu/host/durable/__init__.py`"
- Plan:132-134 `_validation.py` responsibility boundary 正面定义："owns only durable-private scalar validation and scalar conversion helpers such as required/optional text, integer and digest validation; must not import `_row_rules.py` and must not learn Run / Attempt / WaitRecord state-machine terminal rules"
- Plan:347 aggregate review gate 中增加 "`_row_rules.py` remains durable-private and is not re-exported"

**复核**: 两个模块的职责边界以正反两面定义，互不交叉；`_validation.py` 不得 import `_row_rules.py`（单向依赖约束）；无 re-export。已关闭。

---

### ADJ-04 [CLOSED] — row decode `KeyError` wrapping

**要求**: 明确 `_decode_*` helper 捕获 `KeyError` 与 scalar helper `HostDurableError`，转换为 `HostRowDecodeError`，保留 `row_name` / `field_name`。

**修订证据**:
- Plan:174-179 新增 `_decode_*` helper error wrapping requirements 完整段落：
  - "catch `KeyError` raised by `HostRow.get(...)` for missing columns and convert it to `HostRowDecodeError`"
  - "catch `HostDurableError` raised by scalar helpers such as `_require_text`, `_optional_text`, `_require_int`, `_optional_int` and convert it to `HostRowDecodeError`"
  - "catch `HostDurableError` raised by enum deserializers or terminal shape validators and convert it to `HostRowDecodeError`"
  - "preserve `row_name` and `field_name` on the raised `HostRowDecodeError`; for row-level shape failures without one column owner, set `field_name=None` and include the affected row name in the message"
  - "keep the original exception as `__cause__` with `raise ... from exc`"
- Plan:349 aggregate review gate 中增加 "row decode helpers wrap both `KeyError` and scalar-helper `HostDurableError` into `HostRowDecodeError`"

**复核**: 三个 catch 路径（KeyError、scalar helper error、enum/terminal shape error）全部显式列出；`row_name`/`field_name` 保留规则明确；`__cause__` chain 保留 root cause 可追溯性。已关闭。

---

### ADJ-05 [CLOSED] — schema SQL normalization minimal spec

**要求**: 明确 normalization 只做首尾空白去除、连续空白归一、保持大小写与标识符引用不变；更宽规则需停止回报。

**修订证据**:
- Plan:107-113 `_normalize_schema_sql` minimal spec 给出 5 条精确规则：
  1. "strip leading and trailing whitespace"
  2. "collapse every consecutive whitespace run to a single ASCII space"
  3. "preserve letter case exactly as SQLite returned it"
  4. "preserve identifier quoting exactly as SQLite returned it"
  5. "do not reorder clauses, parse SQL, lower/upper-case keywords, remove quotes, or normalize punctuation"
  - + stop condition: "If implementation evidence shows current SQLite output needs a broader normalization rule, stop and report back to controller"
- Plan:233 Slice 1 expected assertions 中增加 normalization 负向测试要求："`_normalize_schema_sql` tests prove only leading/trailing whitespace and consecutive whitespace are normalized; case changes, identifier quote changes, clause changes, and punctuation changes are not silently normalized away"

**复核**: Normalization spec 精确到逐条规则，同时给出了 5 条不允许做的事情（不 reorder、不 parse、不 lower/upper-case、不 remove quotes、不 normalize punctuation）。Stop condition 兜底。已关闭。

---

## 新增内容完整性检查

修订后的 plan 在以下位置新增了内容，逐条审查未发现引入新问题：

| 位置 | 新增内容 | 评估 |
|------|---------|------|
| 6.1:107-113 | Normalization minimal spec | OK — 精确、有 stop condition |
| 6.1:103 | `_normalize_schema_sql` docstring 引用 "minimal normalization spec below" | OK — 自引用正确 |
| 6.2:128-134 | `_row_rules.py` / `_validation.py` responsibility boundary | OK — 正反两面定义清晰 |
| 6.2:153 | Slice dependency paragraph | OK — 与 8/9/10 节一致 |
| 6.3:174-179 | `_decode_*` error wrapping requirements | OK — 三个 catch 路径完整 |
| 8, Slice 1:224 | "freshly bootstrapped DB validates cleanly" test | OK — 防止 normalization 产生 false-positive |
| 8, Slice 1:233 | `_normalize_schema_sql` negative tests | OK — 防止 normalization 过度宽松 |
| 8, Slice 2:258-259 | Corrupted wait record scenario test | OK — test-only 约束明确 |
| 8, Slice 2:261 | Rerun Slice 1 tests | OK — 依赖方向正确 |
| 8, Slice 2:267 | SQL text change report requirement | OK — 可验证 |
| 9:330-331 | Validation 要求同步新增 | OK — 与 slice tests 一致 |
| 10:343-350 | Aggregate review gate 扩展 | OK — 覆盖所有 ADJ |

---

## ADJ-06 / ADJ-07 状态确认

- **ADJ-06** (rejected as non-blocking): `_decode_enum` generic helper — plan 未添加，符合预期
- **ADJ-07** (deferred-within-implementation): baseline transition tests before Slice 2 — plan 未强制修改，符合 "不阻塞 plan fix" 裁决；implementation report 阶段再验证

---

## Residual Risk

无新 residual risk。Plan 中原有的 4 项 risk 均保留且 mitigation 未变。

---

## Verification Checklist

- [x] ADJ-01: slice dependency 5 处明确（6.2/8/8/9/10）
- [x] ADJ-02: corrupted wait record CAS scenario 完整定义（8/9/10）
- [x] ADJ-03: `_row_rules.py` / `_validation.py` 职责边界 + 无 re-export（6.2/10）
- [x] ADJ-04: `_decode_*` helper 3 个 catch 路径 + row_name/field_name/__cause__（6.3/10）
- [x] ADJ-05: normalization 5 条规则 + stop condition + 负向测试（6.1/8）
- [x] 无新增 blocking finding
- [x] 无新增 scope creep / layer violation / WU-LAYER-02 越界
- [x] ADJ-06 正确未修入计划
- [x] ADJ-07 正确 deferred-within-implementation

---

## Review Metadata

- Review 仅基于 revised plan text、controller adjudication、原 review artifact
- 未修改 plan/source/test/README
- 未 commit / push
