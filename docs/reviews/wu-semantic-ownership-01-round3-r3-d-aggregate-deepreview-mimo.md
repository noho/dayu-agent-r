# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Aggregate Deepreview — AgentMiMo

## Scope

- Mode: current changes（R3-D accepted plan + S1-S3 accepted implementation commits）
- Branch: `phaseflow/host-issues-control`
- Base: `ecd76426`（R3-D accepted plan commit）
- Head: `0534797c`（R3-D S3 acceptance）
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-aggregate-deepreview-mimo.md`
- Included scope: R3-D plan 与 S1（cae77ab3）、S2（03fe9548）、S3（b9fcd9d9）全部 accepted implementation commits 的聚合 diff，含 36 个 production files、9 个 test files、1 个 README 和 review/control artifacts
- Excluded scope: docs/reviews/ 下的 review/controller/validation artifacts（非生产代码）
- Parallel review coverage: 3 个 subagent 分别覆盖 S1 financial/XBRL contracts、S2 cache/freshness/decode/search、S3 fiscal/normalization/version；主 reviewer 整合、去重并复核所有 findings

## Findings

未发现实质性问题。

以下为 subagent 提出但经主 reviewer 复核后**驳回**的候选 finding，附驳回理由：

### 候选 F1 — validator `complete_quality` 传递逻辑（subagent S1 提出，驳回）

- **入口/函数**: `validate_financial_statement_result_payload()` → `determine_financial_statement_quality()`
- **文件(行号)**: `dayu/fins/domain/financial_result_contract.py:225-232`
- **输入场景**: `data_quality="partial"` 且 rows 非空、scale 和 period 均有直接证据
- **实际分支**: line 229 传递 `complete_quality="xbrl"`；`determine_financial_statement_quality` 内部 `scale_missing=False`、`period_semantics_missing=False`，走到 line 186 返回 `FinancialQualityOutcome("xbrl", None)`
- **预期行为**: validator 应拒绝"有完整证据却声明 partial"的 payload
- **实际行为**: line 231 比较 `data_quality("partial") != expected_quality.data_quality("xbrl")` 为 True → 抛出 `ValueError`。**validator 实际上正确拒绝了该 payload**
- **直接证据**: line 229 `complete_quality="xbrl" if data_quality == "partial" else data_quality`；line 186 `return FinancialQualityOutcome(complete_quality, None)`；line 231 `if data_quality != expected_quality.data_quality`
- **驳回理由**: subagent 误判了控制流。当 `data_quality=="partial"` 时 `complete_quality` 传 `"xbrl"`，若证据完整则 expected 为 `("xbrl", None)`，与 `("partial", ...)` 不一致，validator 拒绝。行为正确。

### 候选 F2 — `Literal["xbrl", "extracted"]` 运行时不强制（subagent S1 提出，驳回）

- **文件(行号)**: `dayu/fins/domain/financial_result_contract.py:157`
- **驳回理由**: Python `Literal` 是 type-checker-only 注解，运行时不强制是语言特性而非 bug。pyright 已通过 0 errors，且实际调用路径传入的 `"xbrl"` 是合法值。无运行时语义漂移。

## Open Questions

无。

## Residual Risk

### 已验证的 propagation scans

| Scan pattern | Scope | Result |
|---|---|---|
| `errors="ignore"` | `dayu/fins` | 仅 `sec_downloader.py`（downloaders，非 S1-S3 scope）3 处；processors/pipelines 零匹配 |
| `except Exception:\n\s+(pass\|continue)` | `read_runtime.py` + `sec_xbrl_query.py` | `read_runtime.py` 零匹配；`sec_xbrl_query.py` 3 处均在辅助 probe 函数（taxonomy/units/fiscal inference），非 `_query_facts_rows`；主查询函数 line 494 正确追踪 `failed_concepts` |
| `_ProcessorFinancialStatementPayload\|data_quality: NotRequired\|reason: NotRequired\|_DECIMALS_SCALE_MAP` | `dayu/fins` | 零匹配。shadow payload、NotRequired quality/reason 和 duplicate scale map 全部消除 |
| `_FISCAL_PERIOD_SORT_ORDER\|def _infer_fiscal_year\|def _infer_fiscal_period\|_resolve_fiscal_.*fallback\|build_document_recency_sort_key\|_build_recommended_documents` | `dayu/fins/tools` | 零匹配。dead fiscal/inference helpers 全部删除 |
| `FinancialStatementResult\|XbrlFactsResult\|SourceDocumentRevision\|ErrorCode\.` | `dayu/fins` + `tests/fins` | 105 处引用，全部 import 自 domain owner |
| `_virtual_section_by_ref\s*=\|_assign_tables_to_virtual_sections\(` | `dayu/fins/processors` | 仅 `sec_form_section_common.py`（mixin owner）内部 4 处；无外部 caller |
| `def _normalize_optional_string` | 3 个 consumer files | 零匹配。旧 wrapper 全部删除，消费者调用 `normalize_optional_dataframe_string` owner |
| `(from\|import) dayu\.(host\|engine)` | `dayu/fins/**/*.py` | 零匹配。无反向依赖 |
| `R3-D\|plan gate\|future\|tool-security\|SSRF\|allowlist` | `dayu/fins/README.md` | 零匹配。README 只描述已落地 current contract |
| `not_modified\|download_version\|try_normalize_ticker\|normalize_optional_dataframe_string` | pipeline/test files | 全部消费 owner helper |

### 已验证的 aggregate validations

| Command | Result |
|---|---|
| `pytest tests/fins -q` | 628 passed, 1 skipped, 3 warnings |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 仅 review artifacts 尾部空行（非生产代码） |
| `git diff --name-only` 范围检查 | 所有文件均在 S1-S3 allowed files、tests、README 和 control doc 范围内 |

### R3-E / tool-security 排除确认

- `git log --oneline ecd76426..HEAD` 无 R3-E 或 tool-security 相关 commit
- `git diff --name-only` 无 security/allowlist/ssrf/egress 相关文件
- `dayu/fins/README.md` 无 tool-security/SSRF/allowlist 术语
- 未修改 upload/download security schema 或 prompt

### 其它 residual

- `sec_downloader.py` 的 3 处 `errors="ignore"` 不在 S1-S3 scope（属于 downloaders，非 processors/pipelines）。若后续需要严格化 downloader charset，应作为独立 WU。
- `DocumentMeta=dict[str, Any]`（`document_models.py:33`）broad durable type 仍存在。plan 已明确 S2 只增加 freshness 所需的 typed revision，不做 broad god-file migration。residual destination 由 umbrella controller 裁决。
- 6-K BS-only routing 保持不变。若需改变 6-K routing，需 controller 创建独立 WU。

## 结论

R3-D S1-S3 聚合实现通过 aggregate deepreview。所有 13 个 accepted findings 的实现均符合 plan 要求：financial/XBRL public contract 字段完整、quality/reason matrix 唯一、scale/period 由 processor owner 产生、read projection 无损传播、source revision cache 正确绑定、decode/search failure 投影为 typed failure、fiscal/normalization/SEC version/ticker alias 各有唯一 owner。propagation scans 和 aggregate validation 全部通过。未发现实质性问题。
