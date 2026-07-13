# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review Re-Review — AgentDS

## Re-Review Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review re-review (AgentDS)`
- Reviewer: `AgentDS`
- Timestamp: 2026-07-13
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-ds.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-mimo.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-fix-codex.md`

## Scope

本 re-review 仅验证 controller accepted 的四个 fix (CR-S1-01 至 CR-S1-04) 是否已关闭，并确认无新 scope creep。不做全量 review。

## Closure Table

| Finding | Source | Verdict | Direct Evidence |
|---------|--------|---------|-----------------|
| CR-S1-01 — fiscal_year/fiscal_period invariant | AgentDS DS-01 | **已关闭** | `_build_period_for_column:735-741` 和 `_build_single_scope_period:784-790` 均以 `fiscal_period is not None` 为条件产生 `fiscal_year`。新测试 `test_html_year_token_without_accepted_fiscal_period_clears_fiscal_year` 验证普通 `2025` token 无 fiscal-period evidence 时 `fiscal_year`/`fiscal_period` 均为 `None`，`data_quality=partial`，`reason=period_semantics_unavailable`。 |
| CR-S1-02 — unused `period_end` param removed | AgentDS DS-02 | **已关闭** | `_extract_fiscal_period_from_direct_text:1579-1601` 签名仅含 `scope_text`；`del period_end` 已删除。两个 call site (`:730-732`, `:779-781`) 仅传入 `scope_text=...`。`grep period_end` 在 direct_text helper 与 call site 上下文中零命中。 |
| CR-S1-03 — OCR income-summary units/currency docstring | AgentDS DS-03 | **已关闭** | `_build_income_summary_result_from_title_match:1106-1107` docstring 新增："income summary 的 `units` 与 `currency` 有意同源，均表示该货币报表的报告货币；该假设不适用于非货币计量的 statement type，后者不得复用。" |
| CR-S1-04 — owner-level rows rejection test | AgentMiMo F1 | **已关闭** | 测试重命名为 `test_financial_statement_owner_rejects_missing_or_non_list_rows`，直接调用 `validate_financial_statement_result_payload(payload)`。两个 fixture：缺失 `rows` → `"缺少必填字段: rows"`；`rows` 为 dict → `"rows 必须为数组"`。不再依赖 runtime citation 构造或下游 row iteration 的偶然失败。 |

## Scope Creep Check

- 变更文件 17 个（14 production + 3 test），全部在 S1 allowlist 内。
- 生产 diff 中 scope creep 关键词（S2/S3/R3-E/tool-security/upload/download security/6-K routing/DocumentMeta migration/compat）零命中。
- 无新增 Host/Engine 变更。
- 无新增 `filing_semantics.py` 变更（S1 复用既有 domain owner）。
- 无新增兼容 re-export/wrapper/facade。
- 无新增 `_is_json_value` duplication 或 import consolidation 变更（controller 明确排除）。

## Validation Commands (Independently Verified)

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
→ 73 passed, 3 edgartools deprecation warnings

pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
→ 4 passed, 45 deselected, 3 edgartools deprecation warnings

python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ pass
```

## New Findings

无。

## Decision

**PASS**

全部 4 个 controller-accepted fix 已独立验证关闭。73 个 S1 focused 测试通过（含 1 个 CR-S1-01 新增测试）。pyright 零错误。无 scope creep。无新增 finding。
