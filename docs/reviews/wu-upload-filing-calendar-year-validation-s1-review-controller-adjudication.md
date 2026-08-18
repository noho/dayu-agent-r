# UF-FIX04 S1 dual deepreview controller adjudication

## Gate record

- Gate: `implementation review`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S1-domain-calendar-year-owner`
- Base: `f609a4d8238c6b31456c2e1d548079b22b771a68`
- Review inputs:
  - `docs/reviews/code-review-20260814-143751.md`（AgentMiMo，`pass`，无 finding）
  - `docs/reviews/code-review-20260814-144024.md`（AgentDS，`pass`，4 个低严重度 finding）
- Controller conclusion: `fix accepted findings`
- Next entry point: AgentCodex S1 review fix，之后 dual S1 re-review。

## Shared review conclusion

两路 reviewer 均确认 S1 没有 correctness、分层、owner 漂移、类型、compatibility 或 coverage blocker：

- strict ASCII `YYYY-MM-DD`、实际 Gregorian `0001..9999` 与 fiscal/partial year `1000..9999` 正确解耦；
- bool/non-int fail closed，`normalize_fiscal_year` 先 narrow raw JSON 再委托 required owner；
- read-runtime 唯一生产 direct consumer 没有吞掉 `ValueError`；
- focused tests `95 passed`、coverage 集合 `208 passed`、owner coverage `86%`、pyright `0 errors`、diff check clean 均被 reviewer 复现；
- S2/S3 尚未接线是 planned later slice，不构成 S1 finding。

## Finding adjudication

### DS-1 — isoformat round-trip 当前不可达

- Decision: `rejected-with-reason`
- Reason: accepted plan 明确要求 `datetime.date` 构造后执行 exact `isoformat()` round-trip；该检查是 canonical output contract 的直接防御，即使在当前 regex 与 Python 3.11 组合下恒真，也不应删除。实现足够直接，额外注释只会重复代码，没有证据表明维护者会误读。

### DS-2 — year 范围 message 与 bounds 不同源

- Decision: `accepted`
- Required fix: 在同一 owner 模块内由 `_MIN_CALENDAR_YEAR` / `_MAX_CALENDAR_YEAR` 派生唯一范围文本或等价私有真源，让 `parse_calendar_year` 与 `normalize_fiscal_year` 的错误文案共同消费；最终对外文本必须保持完全不变。
- Verification: 现有 exact message tests 保持通过，并增加/保留能证明两条入口 message 一致的 owner-level assertion；不得把 message 重建放到 consumer。

### DS-3 — full-date 非 str 防御无测试

- Decision: `accepted`
- Required fix: 为 `parse_iso_calendar_date` 增加绕过静态类型的 `None`、整数等 runtime 反例，断言统一 `ValueError` message；只改 owner test，不扩宽生产签名。
- Verification: coverage missing 不再包含非 str raise 分支；focused/coverage/pyright 全部重跑。

### DS-4 — 模块 docstring 未涵盖 calendar/year owner

- Decision: `accepted`
- Required fix: 更新 `filing_semantics.py` 中文模块概览，明确它同时拥有四位 fiscal/partial year 与 canonical Gregorian full-date 合法性；不要把 upload/download wrapper-owned shape、partial expansion 或错误投影写入 domain 概览。
- Verification: review 确认职责描述准确且未泄漏上层语义。

## Scope and docs decision

- Fix 只允许修改 `dayu/fins/domain/filing_semantics.py`、`tests/fins/test_fiscal_normalization_contracts.py` 和新增 S1 fix artifact；read-runtime 回归文件无需机械改动。
- README decision 不变：S1 不修改 README，最终稳定 contract 由 S3 更新。
- 不进入 S2/S3，不执行 `UF-PF04`，不修改冻结文件，不 stage/commit。

## Residual risks

- S2/S3 consumer 接线：`covered by later approved slice`。
- `UF-PF04`：`assigned to later work unit`，owner=`UF-PF04`。
- 其它 upload findings：`assigned to later work unit`，owner=各自 work unit。
- `upload_filings_from` strict metadata parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。

没有 `unclassified residual risk`，没有需要用户裁决的事项。
