# R3-D Aggregate Deepreview (AgentDS)

## Scope

- **Mode**: current changes (aggregate review of S1+S2+S3 committed changes)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: baseline before accepted plan (S1 parent: cae77ab3^)
- **Accepted commits**: S1 cae77ab3, S2 03fe9548, S3 b9fcd9d9
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-aggregate-deepreview-ds.md`
- **Included scope**: All files changed across all three slices (83 files: 34 production, 8 test, 27 docs, 1 README, plus plan and control docs)
- **Excluded scope**: R3-E files (not created), tool-security files (not created), Host/Engine internals (no changes in scope)
- **Parallel review coverage**: 5 focus-area agents covering:
  1. Financial/XBRL aggregate projection chain (processor → domain → read → tool → LLM)
  2. Source revision cache/ABA/build race/concurrent rebuild
  3. Strict decode/search failure/cancellation priority
  4. Virtual section mapping/fiscal normalization/SEC version/upload alias
  5. Fins README current contract and propagation/residual scans

## Design Truth

- `docs/host/design.md` (relevant sections: 3141-3145, 3481-3488, 3642-3652) — Host demands LLM-facing evidence self-explaining, retrieval/degradation explainable; financial semantics are Fins tool boundary concern
- `docs/engine/design.md:3-26, 340-356` — Engine does not understand financials, ticker, XBRL, or storage; tool outcomes are `ToolResultSuccess`/`ToolResultFailure` only

## Control Truth

- `docs/host/issues-implementation-control.md` — R3-D section confirms 13 accepted findings, 3-slice plan, per-slice review gate
- `docs/phaseflow-umbrella-optimization-control.md:42-60, 95-120` — production-high changes require full gate, per-slice review

## Plan

- `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`

## Key Artifacts Reviewed

S1-S3 implementation, review (DS/MiMo), fix (Codex), rereview (DS/MiMo), and controller validation artifacts under `docs/reviews/`. All prior per-slice findings (DS: 5 findings, MiMo: 2 findings) were fixed and accepted. Residual risks from per-slice reviews classified and tracked to later work units or umbrella controller.

## Findings

未发现实质性问题。

### 验证摘要

全部五个关注面的 adversarial aggregate paths 均通过验证。以下是逐面详细结果：

---

#### 1. Financial/XBRL 全矩阵 (all-fail/partial/empty)

**财务报表面投影链 (processor → domain validator → read runtime → result type → LLM description)：**
- 全部 13 个字段 (`ticker`, `document_id`, `citation`, `statement_type`, `periods`, `rows`, `currency`, `units`, `scale`, `data_quality`, `reason`, `statement_locator`) 从 processor 产出到 LLM-facing 结果逐字段同源，无重算、无 fallback、无字段丢失。
- `units` 与 `scale` 分离：所有 producer（`sec_processor.py:653-656`、`bs_report_form_common.py:401-404`、`bs_six_k_processor.py:948-951`、`html_financial_statement_common.py:219-227`、`six_k_form_common.py` OCR 路径）分别赋值，domain validator `financial_result_contract.py:219-223` 硬拒绝 units 承载 scale 值。
- `deduped_fact_count` ownership：domain validator `xbrl_result_contract.py:98-99` 拒绝 producer payload 夹带该字段；只在 `read_runtime_helpers.py:1220` 计算、`result_types.py:294` 声明。producer `total` 原样保留。

**XBRL 查询状态矩阵 (all 6 states unique and non-overlapping)：**

| 状态 | data_quality | reason | facts/total | 最终 outcome |
|---|---|---|---|---|
| XBRL 不可用 | partial | xbrl_not_available | []/0 | 成功 degraded |
| 正常零命中 | xbrl | None | []/0 | 成功 empty |
| 部分成功 | partial | query_partially_failed | 有数据 | 成功 degraded |
| 全部失败 | N/A | N/A | N/A | XbrlQueryExecutionError → tool failure |
| 空 concepts | N/A | N/A | N/A | ValueError / 默认 concepts |
| 本地过滤空集 | xbrl (不变) | None (不变) | total>0, deduped=0 | 成功 empty |

全部 6 个状态有唯一、无重叠的 (data_quality, reason, outcome) 信号。edgartools `execute()` 表征化测试覆盖了 8 个 scenario：成功空列表、sentinel 异常、非 list 返回、非 mapping row、本地过滤空集、部分失败、全部失败、空 concepts。

---

#### 2. Source Revision Cache / ABA / Build Race

**Revision 计算 (`_fs_source_document_core.py:169-224`)：**
- 从 canonical source meta 字段 (`document_version`、`source_fingerprint`、`form_type`、`primary_document`、`ingest_complete`、`is_deleted`、`files` identity/content) 计算，使用 `sort_keys=True` JSON + SHA-256。
- 不依赖 mtime、log、processed state、timestamp。
- 字段缺失/类型非法 fail closed (KeyError/ValueError)。

**Processor 缓存 (`_get_or_create_processor`, read_runtime.py:2524-2621)：**
- R1 → build → R2 模式：build 前读 revision，build 后重读。R1 != R2 时 evict 全部相关缓存并立即抛 `SOURCE_CHANGED_DURING_READ`，零次自动 retry。
- Revision 读取异常（source 删除等）时 evict 缓存并 propagate 异常。
- 缓存命中条件：`cached.source_kind is source_kind and cached.revision == revision_before`（行 2570-2574）。
- 文档级 `Lock`（`_get_creation_lock`）保证并发构建安全。

**独立 Meta 缓存 (`_get_source_meta_cached_by_kind`, read_runtime.py:2172-2253)：**
- 独立完成 revision 比较：M1 → rebuild → M2。不依赖 processor build 先运行。
- 同时检查 processor staleness（行 2209-2213）：若 processor 缓存中有同 source_kind 但 revision 已不匹配的条目，一并 evict。
- `_get_document_meta_cached`（行 2255-2272）先 resolve source_kind 再委托给 revision-aware owner，无独立 no-revision 快路。

**ABA 场景：**
- Revision 比较是基于 digest 值的字符串比较，A → B → A 正确命中缓存（digest A == digest A）。

**并发双线程构建：**
- 文档级 Lock 确保只有一次 build；第二个线程在 lock 内部检查到缓存命中后直接返回。

---

#### 3. Strict Decode / Search Failure / Cancellation Priority

**Strict UTF-8 decode (`source_text.py`)：**
- `decode_source_bytes` 使用 `"utf-8-sig"` 且无 `errors=` 参数（默认 strict）。非法 bytes → `UnicodeDecodeError` → `FinsSourceDecodeError`。
- Materialize 失败 (`source_text.py:90`) 和读取失败 (`source_text.py:69`) 均抛 `FinsSourceDecodeError`，不返回空文本。
- `_create_processor` (`read_runtime.py:2675-2680`) 映射为 `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)`。
- 全部错误消息不含绝对路径或 raw bytes。

**Search failure (`search_document`, read_runtime.py:997-1026)：**
- Section enumeration、semantic enrichment、BM25F build、profile build 任一异常统一转为 `SEARCH_INDEX_FAILED` 并保留 cause。
- Cancellation 优先：`except FinsReadCancelledError: raise`（行 1016）在 `except Exception:`（行 1018）之前，cancellation 不被 search error mapping 改写。
- 空 BM25F index 不会崩溃（`bm25f_scorer.py:164` 返回 0.0），search 仍通过其他策略完成。这是设计决策，非 bug。

**ErrorCode 枚举 (`error_contract.py:12-38`)：**
- 全部 7 个成员为 typed enum：`NOT_FOUND`、`INVALID_ARGUMENT`、`NOT_SUPPORTED`、`XBRL_QUERY_FAILED`、`SOURCE_DECODE_FAILED`、`SEARCH_INDEX_FAILED`、`SOURCE_CHANGED_DURING_READ`。
- `fins_tools.py:1048` 使用 `exc.code.value` 投影为 tool outcome error 字符串。

---

#### 4. Virtual Section / Fiscal / Normalization / SEC Version / Ticker

**Virtual section refresh (`_refresh_virtual_section_state`, sec_form_section_common.py:426-497)：**
- 是 section index 和 table 双向映射的**唯一**重建点。全部 4 个 form processor（10-K/10-Q × edgartools/BS）在 postprocess 中调用。
- 10-Q expansion 只修改已有 section 的 start/end/content/preview，不创建新 section/ref。identity multiset 在 refresh 前捕获并由 refresh 内部验证（行 447-448）。
- 10 种违规全部 fail closed（raise ValueError），无 last-write-wins 或静默 skip。

**Fiscal ownership (`filing_semantics.py`)：**
- `normalize_fiscal_year`：bool 检查在 int 检查之前（正确 reject `True`/`False`），只接受正整数，None 返回 None。
- `fiscal_period_recency_rank` 使用 `Final[tuple[str, ...]]` 不可变元组，不暴露 mutable dict。
- Read runtime 只消费 domain helper，旧 inference/fallback/sort-order/recommendation 全部删除（~170+ 行）。

**Dataframe optional string (`value_normalization.py`)：**
- `normalize_optional_dataframe_string` 正确处理 None/pd.NA/pd.NaT/NaN → None，0 → "0"，False → "False"。
- 三份 processor 私有 wrapper 已删除，所有 consumer 直接 import owner。

**SEC version (`sec_download_state.py`)：**
- `has_current_download_version` 被三条 skip 路径消费：fast skip (`sec_pipeline.py:1388`)、remote fingerprint/files skip (`:1419`)、not-modified terminal (`sec_download_filing_workflow.py:533`)。
- Legacy/missing version + all-files-not-modified：不 skip，走 commit current version 路径。

**Upload ticker alias (`upload_company_meta.py:148-182`)：**
- Canonical ticker 始终首项。每个非空 alias 调用 `try_normalize_ticker`。
- Unrecognized alias 抛 `ValueError`，repository 零写入。
- 无 `strip().upper()` 持久化。

---

#### 5. README 当前契约与 Propagation Scans

**`dayu/fins/README.md`：**
- 描述全部当前落地契约：financial statement invariants、XBRL quality/reason matrix、source revision cache、typed read degradation、fiscal/normalization owners、upload ticker canonicalization。
- 零个禁止术语：R3-D、plan gate、future、tool-security、SSRF、allowlist。
- 描述的不变量与 code 一致。

**Propagation scans（全部 clean）：**

| Scan | 预期 | 实际 | 判定 |
|---|---|---|---|
| `errors="ignore"` in fins | 读路径 0 命中 | 3 命中均在 `sec_downloader.py`，非读路径 | Clean |
| `except Exception: pass/continue` in read_runtime | 0 命中 | 0 命中 | Clean |
| Shadow payload/NotRequired scale map | 0 命中 | 0 命中 | Clean |
| Old fiscal helpers in tools | 0 命中 | 0 命中 | Clean |
| Cross-layer imports (dayu.host/engine) | 0 命中 | 0 命中 | Clean |
| `strip().upper()` in upload_company_meta | 0 命中 | 0 命中 | Clean |
| Scale in units (processors + tools) | 只在 LLM description | 3 命中：LLM description + 2 validation guards | Clean |
| `deduped_fact_count` in domain/processors | 只在 validator reject | 只在 validator reject + read projection | Clean |
| R3-E/tool-security leakage | 0 命中 | 0 命中 | Clean |

**Changed files verification：**
- `git diff cae77ab3^..b9fcd9d9 --name-only` 共 83 个文件。全部生产文件在 `dayu/fins/` 下，全部测试文件在 `tests/fins/` 下，全部文档在 `docs/` 下。无文件超出 plan allowed files 边界。

---

### 非 Finding 观察（不构成实质性缺陷）

1. **`_assign_tables_to_virtual_sections` 重复清空状态**（`sec_form_section_common.py:884`）：`_refresh_virtual_section_state` 已在调用前清空 `_table_ref_to_virtual_ref` 和 section `table_refs`（行 464-467），`_assign_tables_to_virtual_sections` 内部又清空一次。无害但增加维护风险：若未来有独立 caller 绕过 `_refresh_virtual_section_state` 直接调用 `_assign_tables_to_virtual_sections`，状态语义可能不一致。

2. **Plan 中引用的 `_preview_payload` 函数不存在于 `sec_6k_rules.py`**：Plan 文档将 `sec_6k_rules.py:_preview_payload` 列为 strict decode consumer，但实际代码中该名称的函数不存在。最近似的是 `_extract_head_text`（行 154），它已正确使用 `decode_source_bytes`。不影响功能，属于 plan 与 implementation 的命名偏差。

3. **`read_runtime.py:873` 中 `except Exception` 过宽**（在 `read_section` 中，非 search_document）：`processor.get_section_title()` 失败时 `except Exception: parent_title = None`。意图合理（title 查找失败降级为 None），但 silently 吞掉所有异常包括 `KeyboardInterrupt`。属于 S2 之前既存代码，未在本次改动范围内。

4. **`sec_xbrl_query.py` 中 3 处 `except Exception: continue`**（行 101, 736, 834）：全部在 XBRL concept probe 方法中，不是主 concept 执行路径。probe 失败由 caller 的 aggregate 结果处理（返回 None 表示 probe 未命中）。这是已知的 edgartools 宽异常面耐受策略，已在 plan 中记录。

## Open Questions

无。

## Residual Risk

以下 residual risk 已在 per-slice review 中分类并分配 owner/destination，不在本 aggregate review 中重新打开：

| Residual | Owner/Destination | Slice |
|---|---|---|
| SEC downloader `errors="ignore"` (3 sites) | 后续 Fins downloader decode-policy WU | S2/S3 |
| Historical non-UTF-8 source 的 charset support | 独立 Fins encoding-policy decision | S2 |
| Full `DocumentMeta` broad type migration | Umbrella controller 后续裁决 | S1-S3 |
| 6-K BS-only routing | Controller 独立 6-K routing WU | S1-S3 |
| Cache revision read 性能开销 | 后续 profiling/optimization | S2 |
| `_to_optional_float` docstring 不准确 | 后续 docstring cleanup | S3 |
| edgartools deprecated import warnings | 依赖升级 tracking | S3 |
| `_creation_locks` 单调增长 | 不在 R3-D scope，umbrella controller 后续裁决 | 全 S |

## Completion Report

- **结论**: 未发现实质性问题。全部 5 个关注面的 adversarial aggregate paths 通过验证。S1-S3 合在一起无跨 slice 语义所有权漂移、contract 不一致、遗漏测试或 README/propagation 问题。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-aggregate-deepreview-ds.md`
- **Findings count**: 0
- **Blocking questions**: 0
- **Non-finding observations**: 4（均不构成实质性缺陷）
- **R3-E/tool-security code confirmed absent**: 是
- **Next allowed action**: Controller 进入 R3-D final closeout，不进入 R3-E。
