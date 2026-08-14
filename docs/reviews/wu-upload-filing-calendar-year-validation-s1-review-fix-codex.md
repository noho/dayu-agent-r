# UF-FIX04 S1 review fix

## Gate record

- Gate: `implementation review fix`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S1-domain-calendar-year-owner`
- Base: `f609a4d8238c6b31456c2e1d548079b22b771a68`
- Branch: `codex/upload-filing-oracle`
- Controller decision: 仅修复 accepted 的 `DS-2`、`DS-3`、`DS-4`；`DS-1` 保持 rejected。
- Completion status: `review fix complete; re-review pending`
- Current gate / next entry point: `dual S1 re-review`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-s1-review-fix-codex.md`

## Scope and reviewed evidence

本轮完整读取并核对：

- `docs/reviews/code-review-20260814-143751.md`
- `docs/reviews/code-review-20260814-144024.md`
- `docs/reviews/wu-upload-filing-calendar-year-validation-s1-review-controller-adjudication.md`
- `docs/reviews/wu-upload-filing-calendar-year-validation-s1-implementation-codex.md`
- 当前三个 tracked 文件的完整工作区 diff，包括只读的
  `tests/fins/test_read_runtime_semantic_ownership_guards.py` diff。

允许的 fix 变更严格限于：

- `dayu/fins/domain/filing_semantics.py`
- `tests/fins/test_fiscal_normalization_contracts.py`
- 本 artifact

未修改 read-runtime 测试或其它文件；未进入 S2/S3，未运行 `UF-PF04`，未 stage/commit。

## First-principles judgment and semantic owner

- `DS-2` 动机成立：年份闭区间是同一业务事实，合法性边界与对外错误文案都应从
  `filing_semantics.py` 内的同一 bounds 真源派生，不能让两个入口各自硬编码。
- `DS-3` 动机成立：`parse_iso_calendar_date` 的 `str` 窄签名是静态 contract，但 owner
  同时明确提供运行时 fail-closed；绕过静态类型的反例必须在 owner-level 测试锁定，不能靠 consumer 测试间接证明。
- `DS-4` 动机成立：模块概览未声明新增 calendar/year 职责，已与实际 owner boundary 不一致。
- 正确 owner 仍是 `dayu.fins.domain.filing_semantics`。本轮没有在 upload/download wrapper、read runtime
  或其它 consumer 增加 fallback、重算、兼容分支或第二真源。
- 修复只增加一个由既有 bounds 派生的私有文本常量和两个直接 owner contract 测试，不引入 helper、wrapper、协议或新层次，
  因而没有过度设计。

## Finding decisions and fix status

### DS-1 — isoformat round-trip 当前不可达

- Controller decision: `rejected-with-reason`
- Fix status: `未修复`（按 controller 裁决无需修复）
- Direct evidence: `dayu/fins/domain/filing_semantics.py:395-396` 的 exact
  `parsed.isoformat() != value` 防御与 raise 均保留；未删除 round-trip，未增加重复其意图的注释。
- Verification: 三文件 coverage 的唯一相关 missing line仍为该防御 raise（当前行 396），证明本轮没有通过测试替身或行为改写掩盖它。

### DS-2 — year 范围 message 与 bounds 不同源

- Controller decision: `accepted`
- Fix status: `已修复`
- Direct evidence:
  - `dayu/fins/domain/filing_semantics.py:46-53` 由 `_MIN_CALENDAR_YEAR` 与
    `_MAX_CALENDAR_YEAR` 派生唯一 `_CALENDAR_YEAR_RANGE_TEXT`。
  - `parse_calendar_year` 与 `normalize_fiscal_year` 的两个错误入口分别在当前行 364、421 共用该文本真源。
  - `tests/fins/test_fiscal_normalization_contracts.py:181-201` 从 required 越界入口和 optional
    非整数入口取实际异常，直接断言二者均精确等于
    `reporting_year 必须是 1000..9999 的整数`。
- External contract: 对外 message 完全不变；范围文本仍为 `1000..9999`，字段名插值行为不变。
- Verification: exact-message owner assertion 与全部既有 message 测试通过。

### DS-3 — full-date 非 str 防御无测试

- Controller decision: `accepted`
- Fix status: `已修复`
- Direct evidence:
  - 生产 API 仍为 `parse_iso_calendar_date(value: str, *, field_name: str = "date") -> datetime.date`；签名未扩宽。
  - `tests/fins/test_fiscal_normalization_contracts.py:273-288` 使用 `JsonValue` 参数和 `cast(str, value)`
    模拟绕过静态类型，覆盖 `None` 与整数 `2024`，并断言统一 `ValueError` message。
- Verification: 三文件 coverage missing 列表不再包含非字符串 raise 的当前行 383；focused tests 与定向 pyright 均通过。

### DS-4 — 模块 docstring 未涵盖 calendar/year owner

- Controller decision: `accepted`
- Fix status: `已修复`
- Direct evidence: `dayu/fins/domain/filing_semantics.py:1-6` 现准确声明四位 fiscal/partial year 与
  canonical Gregorian full-date 合法性由该 domain 模块统一拥有。
- Boundary check: 概览没有写入 upload/download wrapper-owned shape、partial expansion、错误投影或上层调度语义。
- Verification: docstring 与当前 owner API/边界一致，且没有改变运行时行为。

## Validation

所有 Python 命令均在仓库根目录先执行 `source .venv/bin/activate`；未运行 `UF-PF04`。

1. S1 focused tests
   - Command: `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`
   - Result: exit `0`; `98 passed`, `3 warnings`。
2. Three-file reachable coverage set
   - Command: `coverage erase && coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_sec_pipeline_download.py -q`
   - Result: exit `0`; `211 passed`, `3 warnings`。
   - Command: `coverage report --include='dayu/fins/domain/filing_semantics.py' --show-missing --fail-under=80`
   - Result: exit `0`; `141` statements, `18` missed, **`87%` coverage**。
   - Missing lines: `212, 238, 262, 266, 289, 311, 335-341, 396, 462, 468, 492, 515`；
     非 str 防御行 383 已覆盖，round-trip raise 行 396 保持未伪造覆盖。
3. Targeted pyright
   - Command: `python -m pyright dayu/fins/domain/filing_semantics.py tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py`
   - Result: exit `0`; `0 errors, 0 warnings, 0 informations`。
4. Diff integrity
   - Command: `git diff --check`
   - Result: exit `0`; 无输出。

三条 warning 均来自 `.venv` 中 `edgar` deprecated imports，与本轮改动无关。

## Docs decision

- 本轮只更新 `filing_semantics.py` 模块中文概览和本 fix artifact。
- `dayu/fins/README.md` 与根 `README.md` 仍由 approved S3 在最终 consumer contract 稳定后更新；S1 不提前宣称尚未接线的用户行为。
- `tests/README.md` 不更新：没有新增测试层级、运行方式或维护规则。
- `dayu/README.md`、Host/Engine README 不更新：分层、装配及对应生产目录未变化。

## Residual risks and uncovered areas

- S2 upload consumer 接线：`covered by later approved slice`，owner=`S2-upload-strict-static-admission`。
- S3 download shared-owner 接线与最终 README：`covered by later approved slice`，owner=`S3-download-shared-owner-and-docs`。
- `UF-PF04` 真实 CLI evidence：`assigned to later work unit`，owner=`UF-PF04`。
- 其它 upload findings：`assigned to later work unit`，owner=各自既定 work unit。
- `upload_filings_from` strict metadata parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
- DS-1 round-trip 防御当前不可达：controller 已 `rejected-with-reason`，不是未分类风险；实现按 accepted plan 原样保留。

没有 `unclassified residual risk`，没有 blocking open question。

## Completion and handoff

Controller accepted 的 `DS-2`、`DS-3`、`DS-4` 均已在 owner boundary 修复并通过 focused tests、三文件 coverage、
定向 pyright 与 diff integrity 验证；`DS-1` 严格保持 rejected 状态。本 artifact 只声明 review fix complete，
不声明 S1 accepted，不创建 checkpoint commit，也不进入后续 slice。

Next entry point: `dual S1 re-review`。
