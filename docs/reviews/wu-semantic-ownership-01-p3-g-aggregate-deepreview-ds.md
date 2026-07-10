# Aggregate Deepreview — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Mode: all slices aggregate (committed)
- Branch: `phaseflow/host-issues-control`
- Accepted commits: plan `e5e4ad97`, S1 `79629dfa`, S2 `92320413`, S3 `c0386fa2`, S4 `cbbad162`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-aggregate-deepreview-ds.md`
- Validation: `pytest` 174 passed, `pyright` 0 errors

## Verdict

**PASS** — P3-G 四个 slice 共同关闭了 controller adjudication 中的全部 5 个 source finding。旧 helper 已删除、download adapter 不再拥有产品级过滤、rejection registry 已 typed、XBRL `total` 已 processor-owned。无 source finding 遗漏、无跨 slice 语义漂移、无下游特例补丁。

---

## Findings

未发现实质性问题。

---

## Source Finding Closure

| Source Finding | Slice | 处置 | 核实 |
| --- | --- | --- | --- |
| AgentCodex 11: XBRL `total` masking | S4 | processor raw contract validator → read runtime 不再覆盖 `total` | ✅ |
| AgentDS 7: SEC form normalization in 3 places | S1 | `form_type_utils.py` 删除；全 11 个消费者改为 domain helper | ✅ |
| AgentDS 8: naked strings for `fiscal_period`, `form_type`, `quality` | S1 | `SecFormType`, `FiscalPeriod`, `DocumentQuality`, `FinancialDataQuality` — 4 种 Literal TypeAlias | ✅ |
| AgentMiMo BI-1: downloader-owned filtering/inference | S2 | CN/HK downloader → raw HTTP parsing only；pipeline helper 持有 business filtering | ✅ |
| AgentMiMo SS-10: rejection registry dict shape | S3 | `DownloadRejectionEntry` / `DownloadRejectionRegistry` typed contract | ✅ |

**5/5 全部关闭，无遗漏。**

---

## Cross-Slice Semantic Ownership Verification

### S1: SEC Form / Fiscal Period / Quality

```
Producer (SEC submissions/user input/source meta)
  → filing_semantics.py (validator)
    ├─ parse_sec_form_filter_value / parse_sec_form_type / normalize_sec_form_type_for_matching
    ├─ normalize_fiscal_period / sanitize_fiscal_period_by_sec_form
    ├─ normalize_document_quality / normalize_financial_data_quality
  → Consumers (11 imports, 0 old normalizer residual)
```

**Source scan**: `form_type_utils` → 零命中。旧 `normalize_form_type` / `_normalize_form_for_fiscal` / `_normalize_report_form_type` 调用 → 零命中。✅

### S2: CN/HK Report Selection

```
Producer (CN/HK HTTP endpoint)
  → Downloader (raw JSON → CninfoRawAnnouncement / HkexnewsRawAnnouncement, HTTP HEAD → ReadHeadMeta)
  → Pipeline helper (cn_report_selection.py)
    ├─ select_cninfo_report_candidates (title blocklist → fiscal inference → amended priority → candidate)
    └─ select_hkexnews_report_candidates (english filter → period/year inference → amended priority → candidate)
  → Workflow (CnReportCandidate → source commit)
```

**Source scan**: `_is_title_blocked` / `_infer_fiscal_year` / `_infer_fiscal_period_from_text` / `_looks_like_english_report_text` → 仅 `cn_report_selection.py` 命中，downloaders 零命中。✅

### S3: SEC Download Rejection Registry

```
Producer (SEC pipeline rejection / ingestion runtime rejected artifact)
  → DownloadRejectionEntry (__post_init__ + from_dict validation)
  → FilingMaintenanceRepositoryProtocol (load/save typed registry)
  → _fs_maintenance_core (load: fail-closed on bad data; save: entry.to_dict())
  → Consumers (SC13 ×7, SEC pipeline ×5, diagnostics, workflow)
```

**Source scan**: `dict[str, dict[str, str]]` → 仅 `_fs_maintenance_core.py:111` (局部序列化变量), `sec_downloader.py` (文件元数据, 无关), `section_semantic.py` (SEC section map, 无关)。无 public contract 残留。✅

### S4: XBRL Processor Result Contract

```
Producer (sec_processor / bs_report_form_common)
  → validate_xbrl_facts_result_payload(payload)
  → ValidatedXbrlFactsResult (total, facts, query_params, data_quality, reason)
  ├─ Read runtime: validate → normalize → dedupe → preserve validated.total, add deduped_fact_count if needed
  └─ Fiscal inference: validate → extract fiscal fields from validated.facts
```

**Source scan**: `"total": len(deduped_facts)` → 零命中。`normalized_payload["total"] = validated.total` → 保留 processor truth。✅

---

## Cross-Slice Dependency Check

| 依赖 | Direction | 核实 |
| --- | --- | --- |
| S2 `CnFiscalPeriod` → S1 `FiscalPeriod` | `TypeAlias = FiscalPeriod` | ✅ `cn_download_models.py:30` — 消费 shared domain type |
| S3 `DownloadRejectionEntry.from_dict` → S1 `parse_sec_form_type` | domain → domain | ✅ 复用 domain SEC form parser |
| S4 `validate_xbrl_facts_result_payload` → S1 `normalize_financial_data_quality` | domain → domain | ✅ 复用 domain financial data quality parser |
| S4 `read_runtime_helpers` → S4 `xbrl_result_contract` | tools → domain | ✅ 方向正确 |
| S4 `sec_fiscal_fields` → S4 `xbrl_result_contract` | pipeline → domain | ✅ 方向正确 |

无反向依赖。无跨层穿透。

---

## Source Scan Summary (Aggregate)

| Scan | S1 | S2 | S3 | S4 | Status |
| --- | --- | --- | --- | --- | --- |
| Old form normalizer | 零命中 | — | — | — | ✅ |
| Downloader business functions | — | 仅 pipeline helper | — | — | ✅ |
| `dict[str, dict[str, str]]` public | — | — | 仅序列化边界 | — | ✅ |
| `total = len(deduped_facts)` | — | — | — | 零命中 | ✅ |
| `CnFiscalPeriod = Literal["FY"...` | — | 零命中 | — | — | ✅ |

---

## Owner Boundary Map (P3-G Complete)

```
dayu/fins/domain/
├── filing_semantics.py          ← SEC form, fiscal period, doc quality, financial data quality
├── xbrl_result_contract.py       ← XBRL processor result contract validator
└── document_models.py
    ├── DownloadRejectionEntry    ← SEC download rejection typed entry
    ├── DownloadRejectionRegistry ← typed map
    └── (existing models)

dayu/fins/pipelines/
├── cn_report_selection.py        ← CN/HK report candidate selection & fiscal inference
├── (sec_form_utils, sec_fiscal_fields, sec_download_state, ...) ← consumers

dayu/fins/downloaders/
├── cninfo_downloader.py          ← raw HTTP/JSON parsing + delegation to cn_report_selection
└── hkexnews_downloader.py        ← raw HTTP/JSON parsing + delegation to cn_report_selection

dayu/fins/tools/
└── read_runtime_helpers.py        ← XBRL post-validation normalization & dedup
```

---

## Residual Risk

| Risk | Severity | Owner |
| --- | --- | --- |
| S4 `xbrl_result_contract.py` coverage = 80% (exactly at gate) | Low | S4 |
| Old workspace `_download_rejections.json` with missing fields will fail closed | Low | S3 — by design, no migration |
| `CnFiscalPeriod` = `FiscalPeriod` TypeAlias (not a re-export from domain) | Observation | S2 — current approach is acceptable; if CN/HK semantic docstring diverges from domain truth, re-evaluate |
| `DocumentSummary.form_type` remains `Optional[str]` for mixed SEC/CN/material | Observation | S1 — plan-accepted, SEC-only form validation applied at narrower boundaries |

## Open Questions

无。
