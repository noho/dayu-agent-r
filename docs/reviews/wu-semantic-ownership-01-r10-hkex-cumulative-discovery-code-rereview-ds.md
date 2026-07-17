# WU-SEMANTIC-OWNERSHIP-01 / R10 code re-review (AgentDS)

## 1. Review identity、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- review 类型：第二路独立完整 code re-review（AgentDS），按用户指定全流程执行。
- immutable baseline accepted-plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- 初审 MiMo：246 lines / SHA-256 `7e0a1f91d7b69882f079cbca287a33a4e4764e37707a7f62753d839bf1852f5d`，PASS。
- 初审 DS：401 lines / SHA-256 `fc06cfd79f86e7a375fee2ba28f831a59673761c582bbc31072d18e3539db68f`，PASS。
- Controller adjudication：107 lines / SHA-256 `559f582a48a76d6c5e3ed105ffa0b42a226599f64f7e0d5406e44ac3df347db1`。
- review target：exact 13-path immutable implementation（4 production、5 tests、1 fixture、2 README、1 evidence）。
- **verdict：PASS — 0 new material findings、0 blocking questions。**

## 2. Content integrity verification

### 2.1 Individual file hashes — 13/13 全部重算匹配

| Path | Controller SHA-256 | DS Re-review SHA-256 | Match |
|---|---|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | `b3409173...` | `b3409173...` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` | `f1f5bcbc...` | `f1f5bcbc...` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` | `792a70f2...` | `792a70f2...` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` | `235b37ab...` | `235b37ab...` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` | `7d6b3dc0...` | `7d6b3dc0...` | ✓ |
| `tests/fins/test_cninfo_downloader.py` | `86c31dc5...` | `86c31dc5...` | ✓ |
| `tests/fins/test_cn_download_workflow.py` | `da850c08...` | `da850c08...` | ✓ |
| `tests/fins/test_cn_pipeline.py` | `a2ab52c8...` | `a2ab52c8...` | ✓ |
| `tests/fins/test_cn_download_runtime.py` | `c97b7808...` | `c97b7808...` | ✓ |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | `d4bf5965...` | `d4bf5965...` | ✓ |
| `dayu/fins/README.md` | `a4805995...` | `a4805995...` | ✓ |
| `tests/README.md` | `15bb09f8...` | `15bb09f8...` | ✓ |
| AgentCodex evidence | `3074d61c...` | `3074d61c...` | ✓ |

### 2.2 Aggregate manifest hashes — 全部复现

使用 Controller 规范方法（sorted path lines + `shasum -a 256`）：

- **path-manifest SHA-256**：`52a0c5380e3527f260cfb10e3996746967e0173f406187e6f22484fd5004391f` ✓
- **content-lock manifest SHA-256**（`SHA-256  path` 格式，按路径排序）：`91fdf09a26dde192d7973419823330cd702a55686a84941cf9881fe890d41476` ✓
- **Controller validation**：138 lines / SHA-256 `ea244cad3fc4d3b70809bf76562bfaccb050e034f730a4d7530bee2c02719783` ✓

与初审不同，本次 re-review 成功用规范方法复现了两个 aggregate hashes。R10-CR-O04 关闭。

### 2.3 Authority document locks — 全部重读验证

已独立完整读取 AGENTS.md、Controller discussion、docs/fins/design.md、accepted fixed plan、plan re-review Controller adjudication、implementation authorization、AgentCodex evidence、Controller implementation validation、初审 MiMo/DS artifacts。全部与 Codex evidence lock table 一致，无 drift。

## 3. Independent correctness re-review

### 3.1 HKEX strict parser — 独立逐行验证 PASS

`_parse_title_search_snapshot`（`hkexnews_downloader.py` line 697-793）：

- Top-level object check（line 726-729）：`isinstance(payload, dict)` → typed fail。✓
- `hasNextRow`（line 730-734 → 796-821）：`_require_title_search_bool` 只接受 `isinstance(value, bool)`。**显式拒绝 string `"true"`、int `1`、null。** ✓
- `rowRange/loadedRecord/recordCnt`（line 735-749 → 824-853）：`_require_title_search_non_negative_int` 先 `isinstance(value, bool)` 显式拒绝（Python bool 是 int 子类），再 `isinstance(value, int)` 且 `value >= 0`。**显式拒绝 float `0.0`、string `"100"`、bool `true`。** ✓
- `result`（line 750 → 856-902）：`_require_title_search_rows` 要求非空 string → `json.loads` → list → 每行是 dict。**拒绝 empty string、malformed JSON、non-list、non-object-row。** ✓
- 字段缺失（line 905-929）：`_require_title_search_field` → `field not in payload` → typed fail。✓

Same-round invariants（line 759-793）：

- `response_row_range == requested_row_range`（line 760-764）。✓
- `loaded_record == len(rows)`（line 765-769）。✓
- `loaded_record <= record_count`（line 770-775）。✓
- `loaded_record <= requested_row_range`（line 776-780）。✓
- `has_next_row=true` 时 `loaded_record < record_count`（line 781-786）。✓
- `has_next_row=false` 时 `loaded_record == record_count == len(rows)`（line 787-793）。✓

全部 fail-closed；无 coercion、loose parsing、fallback、default value 或 silent acceptance。初审 MiMo/DS 结论独立复现。

### 3.2 Cumulative state machine — 独立逐行验证 PASS

`_fetch_complete_title_search_rows`（line 445-509）：

- Initial range：`_HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE = 100`（line 472）。✓
- Query invariance：`base_params` 为 `MappingProxyType`（line 411），每轮 `dict(base_params)` 派生（line 477），仅改 `rowRange`（line 478）。✓
- Before-first-GET checkpoint（line 475-476）。✓
- After-response checkpoint（line 480-481），在 strict parse 前。✓
- Terminal-first：`if not snapshot.has_next_row: return latest_rows`（line 490-491）优先于 progress 比较。**自洽 count shrink 被接受。** ✓
- Snapshot replacement：`latest_rows = snapshot.rows`（line 489），无 `extend`/`+=`/dedup。✓
- Continuation progress：`snapshot.loaded_record <= previous_continuation_loaded` 时 typed no-progress fail（line 492-504）。✓
- Next range：`max(current_row_range * 2, snapshot.record_count)`（line 506-509），使用最新 `recordCnt`，不冻结首次总数。✓

### 3.3 Cancellation seam — 独立逐路径验证 PASS

Call path 独立追踪确认：

```
raw Callable[[], bool] | None（workflow 外部传入）
  → workflow._is_cancel_requested（唯一 bool 解释 owner，line 420-441）
  → workflow._raise_if_cancelled（唯一 typed cancel 映射 owner，line 444-473）
  → functools.partial（单次构造 no-arg Callable[[], None]，line 201-209）
  → CnReportDiscoveryClientProtocol（只运输 Callable[[], None] | None，line 88）
  → HKEX: 每个 cumulative GET 前（line 475-476）、成功响应后（line 480-481）
  → CNInfo: 每个 supported-period POST 前（line 471-472）、成功响应后（line 484-485）
```

独立验证扫描：

- `if cancellation_checkpoint()` bool 解释：**0 matches 全仓。** ✓
- `Callable[[], bool]`：只在 workflow 模块（3 处）；protocol/providers 只有 `Callable[[], None] | None`。✓
- 既有 workflow `_raise_if_cancelled` 显式检查（line 215、217、237、248）全部保留。✓
- raw checker 为空时传 `None`（line 201-209）。✓
- 取消后不分发下一 request、不 parse partial rows、不发布 candidates/HEAD。✓

### 3.4 Exception precedence — 独立逐路径验证 PASS

HKEX `list_report_candidates`（line 309-316）：
```python
except CnDownloadCancelledError: raise        # bare re-raise，保持 identity
except HkexnewsProviderProtocolError: raise    # bare re-raise，保持 identity/type/cause
except RuntimeError as exc: raise RuntimeError(...) from exc  # 仅普通失败获得 context wrapper
```

CNInfo `list_report_candidates`（line 295-300）：
```python
except CnDownloadCancelledError: raise        # bare re-raise
except RuntimeError as exc: raise RuntimeError(...) from exc
```

Typed cancel identity、provider protocol type/cause 在 generic wrapper 前完整保留。初审结论独立复现。

### 3.5 Query invariance — 独立验证 PASS

- `base_params` 在 language/category 循环外构造一次为 `MappingProxyType`（line 411-428）。
- 每轮通过 `dict(base_params)` 派生，仅修改 `rowRange`（line 477-478）。
- `MappingProxyType` 确保只读视图，防止意外修改。
- 测试通过 `without_range` dict exact equality 验证所有非 range 字段完全一致（line 563-567）。✓

## 4. Independent adversarial failure analysis

### 4.1 Field-level attacks — 独立逐一验证

独立重跑了所有初审列出的攻击向量，全部 fail-closed：

| Attack | Defense | 独立验证 |
|---|---|---|
| `hasNextRow` = `"true"` (string) | `isinstance(value, bool)` → False | ✓ `test_requires_exact_has_next_bool` parametrized |
| `hasNextRow` = `1` (int) | same | ✓ |
| `hasNextRow` = `null` | same | ✓ |
| `rowRange` = `true` (JSON bool) | `isinstance(value, bool)` → 显式拒绝在 int check 前 | ✓ `test_requires_exact_count_ints` parametrized |
| `rowRange` = `"100"` (string) | `isinstance(value, int)` → False | ✓ |
| `rowRange` = `0.0` (float) | `isinstance(value, int)` → False（float 不是 int）| ✓ |
| `rowRange` = `-1` (negative) | `value < 0` check | ✓ `test_rejects_negative_count_fields` parametrized |
| `result` = `""` (empty string) | `not value.strip()` | ✓ |
| `result` = `"{"` (malformed JSON) | `json.JSONDecodeError` → typed fail | ✓ `test_requires_stringified_object_list` parametrized |
| `result` = `"{}"` (dict, not list) | `isinstance(decoded, list)` → False | ✓ |
| `result` = `"[1]"` (non-object row) | `isinstance(row, dict)` → False | ✓ |
| Missing any of 5 fields | `_require_title_search_field` | ✓ `test_requires_all_official_fields` parametrized |

All 6 same-round contradiction cases verified via parametrized test（line 795-821）。✓

### 4.2 State machine attacks — 独立验证

| Attack | Defense | 独立验证 |
|---|---|---|
| `hasNextRow=true` + loaded 不增长 | `loaded_record <= previous` → no-progress typed fail | ✓ `test_rejects_continuation_without_loaded_progress` |
| `recordCnt` 从 350 缩小到 200（terminal 自洽） | terminal-first：`not has_next_row` 直接返回 | ✓ `test_replaces_overlapping_snapshot_and_accepts_terminal_shrink` |
| 首轮 100 exact complete | `not has_next_row` → 直接返回 | ✓ `test_accepts_exact_100_complete_with_ordered_checkpoint` |
| HTTP 503 on later round | retry exhaustion → RuntimeError | ✓ `test_discards_partial_rows_when_later_http_fails` |
| Cancel before first GET | CP1 抛出 | ✓ parametrized cancel_call=1 |
| Cancel after response | CP2 抛出 | ✓ parametrized cancel_call=2 |
| Cancel before next round | CP3 抛出 | ✓ parametrized cancel_call=3 |

全部取消/HTTP 失败路径 zero-publication（head_count==0）。✓

### 4.3 Exception chain integrity — 独立验证

| Scenario | 独立验证 |
|---|---|
| Caller cancel identity preserved (`exc_info.value is expected`) | ✓ HKEX test line 869 + CNInfo test line 1252 |
| Non-cancel failure two-layer cause chain across HKEX wrapper | ✓ `test_preserves_non_cancel_failure_full_cause_chain` line 895-897 |
| Non-cancel failure two-layer cause chain across CNInfo wrapper | ✓ `test_preserves_checkpoint_failure_full_cause_chain` line 1292-1293 |
| Provider protocol error with JSONDecodeError cause | ✓ `test_preserves_provider_protocol_error_and_direct_cause` line 913 |
| Provider protocol error object identity (`exc_info.value is expected`) | ✓ `test_preserves_provider_protocol_object_identity` line 948-949 |

### 4.4 Infinite/no-progress scenarios — 独立验证

- `hasNextRow=true` + loaded 不增长 → no-progress typed fail（line 492-504），不继续 doubling。已测试：exactly 2 requests，no HEAD（line 713）。✓
- `recordCnt=0` + `hasNextRow=false` → terminal check `loadedRecord == recordCnt == len(rows) = (0,0,0)`，通过。✓
- 超大 `recordCnt`（如 100000）→ `max(current*2, recordCnt)` 直接请求 100000。无 hard cap。按 plan 设计。✓

## 5. Independent test authenticity audit

### 5.1 Test fixture vs real network — 独立验证

全部 77 个 HKEX 测试和 45 个 CNInfo 测试使用 `httpx.MockTransport`。独立运行确认：
- `tests/fins/test_hkexnews_downloader.py`: **77 passed** in 0.13s ✓
- `tests/fins/test_cninfo_downloader.py`: **45 passed** in 0.11s ✓

### 5.2 Owner-level contract assertions — 独立验证

HKEX 新测试独立逐项核对：

- `test_accepts_exact_100_complete_with_ordered_checkpoint`：断言 `events[:3] == ["CP1", "GET(100)", "CP2"]` + `checkpoint.call_count == 2` + 只返回 final rows。✓
- `test_fetches_two_round_cumulative_snapshot_with_invariant_query`：断言 exact 6 events（CP1→GET(100)→CP2→CP3→GET(200)→CP4）+ ranges `["100","200"]` + non-range params exact equal + final-only candidate。✓
- `test_uses_latest_record_count_for_next_range_and_growth`：断言 ranges `[100, 200, 400]` + final-only 使用 GROW3 prefix。✓
- `test_uses_record_count_when_larger_than_doubled_range`：断言 ranges `[100, 350]`（公式 `max(100*2, 350)`）。✓
- `test_replaces_overlapping_snapshot_and_accepts_terminal_shrink`：断言 candidates 只有 FINAL_ONLY_0 + HEAD 只发生在 final rows。✓
- `test_rejects_continuation_without_loaded_progress`：断言 exactly 2 requests + no HEAD。✓
- `test_requires_all_official_fields`：parametrized 5 字段逐缺 → typed fail。✓
- `test_requires_exact_has_next_bool`：parametrized `["true", 1, None, [], {}]` → all fail。✓
- `test_requires_exact_count_ints`：parametrized field × value (3×6) → all fail。✓
- `test_rejects_negative_count_fields`：parametrized 3 fields → all fail。✓
- `test_requires_stringified_object_list`：parametrized `[[], "", "{", "{}", "[1]"]` → all fail。✓
- `test_rejects_same_round_contradictions`：parametrized 6 cases → all typed fail。✓
- `test_preserves_cancel_identity_and_suppresses_publication`：parametrized 3 cancel timing + assert `exc_info.value is expected` + `head_count == 0`。✓
- `test_preserves_non_cancel_failure_full_cause_chain`：assert two-layer cause chain + zero HTTP。✓
- `test_preserves_provider_protocol_error_and_direct_cause`：assert `JSONDecodeError` cause。✓
- `test_preserves_provider_protocol_object_identity`：monkeypatch → assert identity/cause。✓
- `test_discards_partial_rows_when_later_http_fails`：assert 3 GET attempts + no HEAD。✓
- `test_keeps_cumulative_state_isolated_per_language`：断言 zh/en 各 `[100, 200]`。✓
- `test_captured_official_title_search_shape_replays_through_strict_owner`：验证 body hash、field types、request params。✓

CNInfo 新测试独立核对：

- `test_calls_same_checkpoint_around_each_period_post`：断言 `CP1→POST(FY)→CP2→CP3→POST(H1)→CP4`。✓
- `test_calls_checkpoint_around_every_paginated_post`：断言 `CP1→POST(1)→CP2→CP3→POST(2)→CP4`。✓
- `test_preserves_cancel_identity_and_stops_next_period`：parametrized CP2/CP3 → assert `exc_info.value is expected` + `head_count == 0`。✓
- `test_preserves_checkpoint_failure_full_cause_chain`：assert two-layer cause chain across CNInfo wrapper。✓

Workflow 新测试独立核对：

- `test_maps_bool_true_inside_single_owned_checkpoint`：raw_calls==4、checkpoint is not cancel_checker、checkpoint_errors[0] is CnDownloadCancelledError、zero download/convert、no FILING_STARTED。✓
- `test_preserves_caller_cancel_object_through_checkpoint`：checkpoint_errors[0] is expected cancel object、zero download/convert。✓
- `test_cancel_before_first_candidate_suppresses_download`：raw_calls==6、zero download/convert、no FILING_STARTED。✓
- `test_wraps_checkpoint_non_cancel_failure_with_direct_cause`：workflow_error is RuntimeError、`__cause__ is expected`。✓

### 5.3 Captured fixture — 独立验证

`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（34 lines）：

- `raw_response_body_sha256`：`5745632a449bf3075e6ba27892b7cbe1eed98fd885c487fe3c98e1d5328a51f5`。测试 line 1045 独立验证 body hash 匹配。✓
- `raw_json_response.hasNextRow`：`false`（JSON bool）。测试 line 1048 断言 `isinstance(..., bool)`。✓
- `raw_json_response.rowRange`：`100` (int, not bool)。测试 line 1049 断言 `isinstance(..., int) and not isinstance(..., bool)`。✓
- 不含 cookie、authorization、proxy credential、headers 或本地 path。✓

### 5.4 Branch coverage — 独立承认

本 re-review 未独立运行 coverage（已在初审和 Controller 中独立验证）。controller-reported 数值：
- HKEX：**80.89%** ✓
- CNInfo：**89.28%** ✓
- protocol：**100.00%** ✓
- workflow：**81.05%** ✓

全部逐文件 `>=80.00%`，无 waiver/omit/pragma/padding。workflow `79.74%→81.05%` 修复通过真实 owner 行为测试完成。✓

### 5.5 Obsolete symbol scan — 独立验证

独立全仓 scan 确认以下符号 zero match：
- `_HkexnewsRowsPage` ✓
- `_extract_title_search_total_count` ✓
- `_coerce_non_negative_int` ✓
- `_raise_if_title_search_truncated` ✓
- `HkexnewsDiscoveryTruncatedError` ✓
- `_HKEXNEWS_ROW_LIMIT` ✓
- `_HKEXNEWS_ROW_RANGE` ✓

### 5.6 Deferred-scope leakage scan — 独立验证

独立 diff scan 确认：
- Issue 142/151/175/177/178：**0 matches** ✓
- R11/R12 mention：**0 matches** ✓
- hard cap / date recursion / compatibility：**0 matches** ✓
- `hasattr` / `getattr` in changed files：**0 matches** ✓
- `if cancellation_checkpoint()` bool interpretation：**0 matches** ✓

## 6. Independent Controller disposition verification

逐项独立核对 Controller 对 R10-CR-O01..O04 的 disposition：

### R10-CR-O01：CNInfo `page_num > 50` 保护

- **独立验证**：`cninfo_downloader.py` line 497 确认 `if page_num > 50:` 仍存在，为 CNInfo pagination 的 silent cap。
- **disposition 验证**：此行为**不在 R10 diff 中**，R10 修改的是 CNInfo 的 cancellation checkpoint 注入（line 471-485），未触及 pagination 逻辑。accepted plan §3.3 明确禁止 CNInfo pagination redesign。
- **结论**：Controller rejection 成立。不应转化为 current finding、new issue/WU 或代码修改。

### R10-CR-O02：`_extract_json_rows` / `_parse_embedded_json_list` 仍存在

- **独立验证**：`hkexnews_downloader.py` line 375 确认 `_fetch_stock_mapping` 调用 `_extract_json_rows(payload)` 解析 stock list JSON。`_parse_embedded_json_list`（line 932-954）被 `_extract_json_rows`（line 691）调用。
- **disposition 验证**：这两个函数服务于 stock mapping（`resolve_company`），不参与 title search completeness。删除它们会破坏 `_fetch_stock_mapping`。
- **结论**：Controller 保留成立。不得误删。

### R10-CR-O03：announcement `_first_text` raw field aliases

- **独立验证**：`_parse_announcement`（line 985-1036）使用 `_first_text`（line 1039-1059）以 permissive alias 方式解析 announcement 字段（`FILE_TYPE`、`NEWS_ID`、`TITLE`、`FILE_LINK`、`STOCK_CODE`、`LONG_TEXT`、`DATE_TIME`）。这些字段**不是** title search 官方 completeness 字段（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result`）。
- **disposition 验证**：announcement 解析是既有的非 completeness 路径；title search completeness 由新增 strict parser 独立拥有。两者无交集。
- **结论**：Controller pre-existing / no action 成立。不应误升级为 generic total alias finding。

### R10-CR-O04：manifest-level hash 复现差异

- **独立验证**：本次 re-review 成功用 Controller 规范方法（sorted path lines + `shasum -a 256`）复现两个 aggregate hashes：
  - path-manifest: `52a0c5380e3527f260cfb10e3996746967e0173f406187e6f22484fd5004391f`
  - content-lock manifest: `91fdf09a26dde192d7973419823330cd702a55686a84941cf9881fe890d41476`
- **结论**：R10-CR-O04 **正式关闭**。13/13 individual hashes 全部匹配，两个 aggregate hashes 现已复现。不存在 content drift。

### Disposition summary

| ID | 初审状态 | Re-review 状态 | 独立验证依据 |
|---|---|---|---|
| R10-CR-O01 | rejected / no action | **confirmed** | `cninfo_downloader.py:497` 确认为 pre-existing，不在 R10 diff |
| R10-CR-O02 | intentional retention | **confirmed** | `hkexnews_downloader.py:375` 确认 stock mapping 仍消费 |
| R10-CR-O03 | pre-existing | **confirmed** | `_parse_announcement` 的非 completeness alias 未改 |
| R10-CR-O04 | tooling / closed | **closed** | 两个 aggregate hashes 本次成功复现 |

## 7. Independent code quality re-audit

### 7.1 AGENTS.md compliance

- 函数 docstring：全部新增/修改函数有完整中文 docstring（参数、返回值、异常）。✓
- 类型注解：无 `object`、`Any`、无类型参数、无类型返回值。✓
- `hasattr`/`getattr`：0 matches in changed production files。✓
- 无 magic number：`_HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE = 100` 和 doubling factor `2` 为显式算法语义。✓
- 无兼容性代码：deleted symbols zero match，无 alias/wrapper/re-export。✓
- 模块间依赖：workflow → protocol（运输）→ provider（I/O），无反向依赖。✓

### 7.2 LLM-facing 文本约束

- R10 实现不产生 LLM-facing 文本（不修改 tool schema、prompt 或 LLM message）。✓
- Protocol docstring 描述 provider 语义，不暴露内部类型名或 Host 治理字段。✓
- 错误消息只含业务可读 context（stock_code、lang、t1code、t2code、row_range、count），不含 raw response、cookie/header、local path。✓

### 7.3 分层架构

- `dayu.fins.downloaders` → provider I/O owner。✓
- `dayu.fins.pipelines.cn_download_protocols` → 运输层。✓
- `dayu.fins.pipelines.cn_download_workflow` → workflow orchestration owner。✓
- 无 `dayu.runtime` 违规 import。无 Engine/Host 反向依赖。✓

### 7.4 Security retention

- HTTP timeout (30s)、max_retries (3)、exponential backoff、throttle (0.3s) 保留。✓
- HTTPS HKEX endpoint 不变。✓
- PDF magic bytes (`%PDF-`) + min size (1024 bytes) 校验保留。✓
- Stock code matching 保留。✓
- Error messages 不含 raw response/cookie/auth/local path。✓
- Captured fixture 只用 public GET，不含 secrets。✓

## 8. Finding ledger

### 8.1 New material findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| — | — | — | **0 new material findings** |

本 re-review 未发现初审 MiMo/DS 或 Controller adjudication 未覆盖的新 correctness、stability、maintainability、semantic ownership、security 或 deferred leakage 问题。

### 8.2 Prior finding ledger confirmation

| Group | Accepted | Open | Rejected/no-action | Deferred | Blocker |
|---|---|---|---:|---:|---:|
| R10 initial code review | **0** | **0** | **4** | **0** | **0** |

全部四项 Controller disposition 经独立验证成立。无新增 finding 需加入 ledger。

### 8.3 Residual / no-action items — 独立确认

| Item | Re-review 确认 |
|---|---|
| CNInfo `page_num > 50` 保护 | 确认为 pre-existing（`cninfo_downloader.py:497`），不在 R10 scope。独立的 CNInfo completeness concern |
| `_extract_json_rows` / `_parse_embedded_json_list` | 确认为 stock mapping 消费（`hkexnews_downloader.py:375`），不应删除 |
| `_first_text` raw field aliases | 确认为 announcement 解析（非 completeness），与 R10 strict parser 无交集 |
| manifest hash 格式差异 | **本次已复现两个 aggregate hashes，正式关闭** |

## 9. Review completeness checklist

- [x] 完整独立读取 AGENTS.md、Controller discussion、docs/fins/design.md
- [x] 完整独立读取 accepted fixed plan、plan re-review Controller adjudication
- [x] 完整独立读取 implementation authorization、AgentCodex evidence、Controller validation
- [x] 完整独立读取初审 MiMo (246L) 和 DS (401L) artifacts
- [x] 完整独立读取 Controller adjudication (107L / SHA-256 `559f582a...47db1`)
- [x] 完整独立重算全部 13 个 target file SHA-256 → 全部匹配
- [x] 独立重算 path-manifest `52a0c538...4391f` → 匹配
- [x] 独立重算 content-lock manifest `91fdf09a...41476` → 匹配
- [x] 独立验证 Controller validation hash `ea244cad...2783` → 匹配
- [x] 独立逐行验证 HKEX strict parser（5 field types + 6 same-round invariants）
- [x] 独立逐路径验证 cumulative state machine（initial→doubling→recordCnt→terminal-first→progress→snapshot replacement）
- [x] 独立逐路径验证 cancellation seam（workflow→partial→protocol→provider I/O boundary）
- [x] 独立逐路径验证 exception precedence（cancel/provider bare re-raise before generic wrapper）
- [x] 独立逐路径验证 exception chain integrity（identity/cause/two-layer）
- [x] 独立全仓 scan：deleted symbols = 0
- [x] 独立全仓 scan：deferred topics = 0
- [x] 独立全仓 scan：`hasattr`/`getattr` = 0
- [x] 独立全仓 scan：`if cancellation_checkpoint()` = 0
- [x] 独立运行 HKEX tests：77 passed
- [x] 独立运行 CNInfo tests：45 passed
- [x] 独立验证 Controller 四项 disposition（O01–O04）：全部成立，O04 正式关闭
- [x] 独立验证 captured fixture body hash + field types
- [x] 独立验证 security retention：HTTP/HTTPS/PDF/throttle/error hygiene
- [x] 独立验证 staged tree empty（无 stage/commit/push/PR）
- [x] 独立验证 Controller-owned files untouched
- [x] 独立验证 implementation evidence 未覆盖 Controller control/auth/validation

## 10. Review handoff

- **verdict: PASS**
- **new material findings: 0**
- **blocking questions: 0**
- **all prior Controller dispositions: confirmed; R10-CR-O04 formally closed**
- **prior finding ledger: 0 accepted / 0 open / 4 rejected / 0 deferred / 0 blocker**（不变）
- **artifact: 本文件**；target path: `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-rereview-ds.md`
- **artifact SHA-256**: 外部计算（文件写入完成后）
- **next gate**: AgentMiMo 并发 re-review 完成后 Controller aggregate 裁决
- **明确声明**: 未开始 fix、aggregate、commit、R11/R12
