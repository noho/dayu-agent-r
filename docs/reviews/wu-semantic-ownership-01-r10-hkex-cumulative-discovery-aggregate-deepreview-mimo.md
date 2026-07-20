# WU-SEMANTIC-OWNERSHIP-01 / R10 HKEX cumulative discovery — AgentMiMo aggregate deepreview

## 1. Review identity 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- review 类型：第一路完整 aggregate deepreview，覆盖 plan→implementation→validation→initial reviews→Controller adjudication→final re-reviews 组合链。
- immutable baseline accepted-plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- **verdict：PASS。**
- **material findings：0。**
- **blocking questions：0。**

## 2. Aggregate target locks

### 2.1 R10-aggregate-target-paths.txt

- 32 lines；SHA-256 `2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde` ✓

### 2.2 Rereview Controller adjudication

- 85 lines；SHA-256 `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` ✓

Controller-owned 文件 lock 历史：review-time pre-normalization locks 与 final committed blobs 仅差 EOF 空行（Controller staging 时为 `git diff --check` 删除）；语义和所有产品 bytes 不变。本 artifact 使用 final committed blob hashes。受影响的 Controller-owned 文件：

| File | Committed lines | Committed SHA-256 |
|---|---:|---|
| implementation-controller-validation | 137 | `39b01e75f33324941d38dd7d3b10c53c0ff821fd99b2f47aac8ff6f61d5e84ca` |
| code-review-controller-adjudication | 106 | `fde40ca5174782be54c4373d248afdc66b137bd043de3560e840dc9e6061201f` |
| code-rereview-controller-adjudication | 85 | `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` |

### 2.3 Implementation target individual SHA-256（13 paths，全部与 Controller validation 一致）

Implementation target 包含 12 个 product/test/fixture/README 路径与 1 个 AgentCodex implementation evidence：

**Product / test / fixture / README（12 paths）**

| Path | Lines | SHA-256 | Match |
|---|---:|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1266 | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` | 849 | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` | 231 | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` | 820 | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` | 1706 | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` | ✓ |
| `tests/fins/test_cninfo_downloader.py` | 1619 | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` | ✓ |
| `tests/fins/test_cn_download_workflow.py` | 1793 | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` | ✓ |
| `tests/fins/test_cn_pipeline.py` | 759 | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` | ✓ |
| `tests/fins/test_cn_download_runtime.py` | 711 | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` | ✓ |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | 34 | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` | ✓ |
| `dayu/fins/README.md` | 793 | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` | ✓ |
| `tests/README.md` | 293 | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` | ✓ |

**AgentCodex implementation evidence（1 path）**

| Path | Lines | SHA-256 | Match |
|---|---:|---|---|
| `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md` | 226 | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` | ✓ |

### 2.4 Content-lock manifest 重算

使用 Python hashlib 对 32 个 aggregate target paths 按 `SHA-256  path` 格式排序后计算 manifest：

- **path-manifest SHA-256**：`2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde` ✓
- **content-lock manifest SHA-256**（`SHA-256  path` 格式，按路径排序，基于 final committed blobs）：`7b0c8a992870dd1c3b88597f1761dfed9294c6f9f0b1cc2bd2ca359ee76a75db` ✓（已用 Python `hashlib.sha256` 独立复现；旧 review-time lock `187cc123...` 为 pre-normalization 值，差异仅来自 3 个 Controller-owned 文件的 EOF 空行清理）

staged tree：empty。Controller-owned `docs/host/issues-implementation-control.md` 未被触碰。

## 3. Accepted plan 兑现验证

### 3.1 Goal / success signals 逐项核对

| Plan success signal | 实现验证 | 状态 |
|---|---|---|
| 1. 首轮恰好 100 条且 complete 时正常返回 | `hkexnews_downloader.py:490-491` terminal-first 分支；test `test_accepts_exact_100_complete_with_ordered_checkpoint` | ✓ |
| 2. `hasNextRow=true` 时按 `max(current*2, recordCnt)` 扩大 range | `hkexnews_downloader.py:506-509`；test `test_uses_record_count_when_larger_than_doubled_range` | ✓ |
| 3. 每轮替换 snapshot，只有 final complete 进入 parsing | `hkexnews_downloader.py:489` `latest_rows = snapshot.rows`；test `test_replaces_overlapping_snapshot_and_accepts_terminal_shrink` | ✓ |
| 4. 只有 `hasNextRow=false` 且三数相等才 complete | `hkexnews_downloader.py:787-793` same-round invariant | ✓ |
| 5. 字段缺失/类型错误/矛盾时 typed fail | `hkexnews_downloader.py:697-929` strict parser；parametrized tests 覆盖全部向量 | ✓ |
| 6. `recordCnt` 增长时使用最新事实 | `hkexnews_downloader.py:506-509` `snapshot.record_count`；test `test_uses_latest_record_count_for_next_range_and_growth` | ✓ |
| 7. workflow checkpoint → provider I/O boundary | `cn_download_workflow.py:201-209` partial 构造；`hkexnews_downloader.py:475-481` GET 前/后；`cninfo_downloader.py:471-485` POST 前/后 | ✓ |
| 8. focused/full Fins/pyright/Ruff/coverage 全部通过 | implementation evidence §6 + Controller validation §4 | ✓ |

### 3.2 Non-goals / forbidden design 逐项核对

| Forbidden pattern | 实现验证 | 状态 |
|---|---|---|
| hard cap / 固定最大累计条数 | 无 `_HKEXNEWS_ROW_LIMIT`；next range 公式无上限 | ✓ 0 matches |
| 日期窗口递归 | 无 date recursion 逻辑 | ✓ 0 matches |
| page append / dedup | `latest_rows = snapshot.rows` 替换语义；`primary.extend` 仅在 complete 后汇总 | ✓ 0 matches |
| generic pagination/cancellation framework | 只有一个 keyword-only `cancellation_checkpoint` 参数 | ✓ 0 matches |
| 旧 exception compatibility | `HkexnewsDiscoveryTruncatedError` 全仓 scan = 0 | ✓ 0 matches |
| Issue 142/151/175/177/178 | changed hunks 中 0 实现 | ✓ 0 matches |
| R11/R12 | 0 实现 | ✓ 0 matches |
| Web/WeChat/render | 0 实现 | ✓ 0 matches |
| Topic 8/9 | 0 实现 | ✓ 0 matches |
| 统一 authorization | 0 实现 | ✓ 0 matches |

## 4. Official HKEX state machine 与 call path 一致性

### 4.1 跨 workflow/protocol/HKEX 组合 call path

独立追踪完整 call path：

```text
cn_download_workflow.run_cn_download_stream_impl
  → functools.partial(_raise_if_cancelled, ...) → no-arg Callable[[], None]
  → discovery.list_report_candidates(query, profile, cancellation_checkpoint=checkpoint)
  → HkexnewsDiscoveryClient.list_report_candidates (line 256-322)
    → _query_period_announcements (line 382-443)
      → _fetch_complete_title_search_rows (line 445-509)
        → [loop] checkpoint() → GET → checkpoint() → strict parse
        → terminal-first / progress / next range
  → except CnDownloadCancelledError: raise (line 309-310)
  → except HkexnewsProviderProtocolError: raise (line 311-312)
  → except RuntimeError as exc: raise RuntimeError(...) from exc (line 313-316)
```

**结论：call path 与 plan §4-§6 完全一致。**

### 4.2 State machine 关键不变量

| Invariant | 代码位置 | 验证 |
|---|---|---|
| initial range = 100 | `hkexnews_downloader.py:472` | ✓ |
| next range = `max(current*2, recordCnt)` | `hkexnews_downloader.py:506-509` | ✓ |
| terminal-first 优先于 progress 比较 | `hkexnews_downloader.py:490-491` | ✓ |
| continuation loaded 必须严格增加 | `hkexnews_downloader.py:492-504` | ✓ |
| 每轮 snapshot replacement | `hkexnews_downloader.py:489` | ✓ |
| query invariance（base_params + 只改 rowRange） | `hkexnews_downloader.py:411-428, 477-478` | ✓ |
| response range == request range | `hkexnews_downloader.py:760-764` | ✓ |
| terminal: loaded == count == len(rows) | `hkexnews_downloader.py:787-793` | ✓ |

### 4.3 Cancellation ordering

| Provider | Before | After | 验证 |
|---|---|---|---|
| HKEX | 每个 cumulative GET 前（L475-476） | 成功响应后 strict parse 前（L480-481） | ✓ |
| CNInfo | 每个 pagination POST 前（L471-472） | 成功响应后（L484-485） | ✓ |

- HKEX exact trace（一轮）：`CP1, GET(100), CP2` ✓
- HKEX exact trace（两轮）：`CP1, GET(100), CP2, CP3, GET(200), CP4` ✓
- CNInfo exact trace（两 period）：`CP1, POST(FY), CP2, CP3, POST(H1), CP4` ✓

### 4.4 Exception precedence

HKEX `list_report_candidates`（L309-316）：
```python
except CnDownloadCancelledError: raise        # bare re-raise，保持 identity
except HkexnewsProviderProtocolError: raise    # bare re-raise，保持 type/cause
except RuntimeError as exc: raise RuntimeError(...) from exc  # 仅普通失败
```

CNInfo `list_report_candidates`（L295-300）：
```python
except CnDownloadCancelledError: raise        # bare re-raise
except RuntimeError as exc: raise RuntimeError(...) from exc
```

**typed cancel identity / provider protocol type/cause 在 generic wrapper 前完整保留。** ✓

## 5. Tests / fixtures / live smoke 证据一致性

### 5.1 测试覆盖矩阵

plan §8 的 30 行测试用例全部有对应实现：

| 测试维度 | 实现测试 | 验证 |
|---|---|---|
| exact 100 complete | `test_accepts_exact_100_complete_with_ordered_checkpoint` | ✓ |
| two-round cumulative | `test_fetches_two_round_cumulative_snapshot_with_invariant_query` | ✓ |
| formula recordCnt branch | `test_uses_record_count_when_larger_than_doubled_range` | ✓ |
| multi-round count growth | `test_uses_latest_record_count_for_next_range_and_growth` | ✓ |
| overlapping/replacement | `test_replaces_overlapping_snapshot_and_accepts_terminal_shrink` | ✓ |
| query invariance | 同 two-round test 中 dict equality | ✓ |
| missing fields (5) | `test_requires_all_official_fields` parametrized | ✓ |
| hasNext type | `test_requires_exact_has_next_bool` parametrized | ✓ |
| count/range type | `test_requires_exact_count_ints` parametrized | ✓ |
| negative fields | `test_rejects_negative_count_fields` parametrized | ✓ |
| rows type | `test_requires_stringified_object_list` parametrized | ✓ |
| same-round contradictions (6) | `test_rejects_same_round_contradictions` parametrized | ✓ |
| no progress | `test_rejects_continuation_without_loaded_progress` | ✓ |
| cancel before first GET | parametrized cancel_call=1 | ✓ |
| cancel after response | parametrized cancel_call=2 | ✓ |
| cancel before later round | parametrized cancel_call=3 | ✓ |
| workflow bool true mapping | `test_maps_bool_true_inside_single_owned_checkpoint` | ✓ |
| caller cancel identity | `test_preserves_caller_cancel_object_through_checkpoint` | ✓ |
| checker non-cancel failure | `test_preserves_non_cancel_failure_full_cause_chain` | ✓ |
| HKEX exception precedence | `test_preserves_provider_protocol_error_and_direct_cause` + identity test | ✓ |
| HTTP initial/later failure | `test_discards_partial_rows_when_later_http_fails` | ✓ |
| per-language isolation | `test_keeps_cumulative_state_isolated_per_language` | ✓ |
| CNInfo checkpoint sequence | `test_calls_same_checkpoint_around_each_period_post` | ✓ |
| CNInfo response cancel | `test_preserves_cancel_identity_and_stops_next_period` | ✓ |
| CNInfo before-next cancel | 同上 parametrized | ✓ |
| pipeline/runtime test doubles | pipeline 2 fakes + runtime 1 fake 显式 checkpoint transport | ✓ |
| workflow propagation | 4 个 workflow owner tests | ✓ |
| captured fixture replay | `test_captured_official_title_search_shape_replays_through_strict_owner` | ✓ |

### 5.2 Zero-publication 证据

每个 cancel/failure 测试均断言：
- `head_count == 0`（无 HEAD 请求）
- `discovery.download_calls == 0`（无 PDF 下载）
- `converter.calls == 0`（无 Docling 转换）
- 无 `FILING_STARTED` / `FILE_DOWNLOAD_STARTED` event

**Partial rows/candidates/HEAD/PDF/Docling 在任何 cancel/failure 路径下 zero-publication。** ✓

### 5.3 Captured fixture

`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（34 lines）：
- `captured_at_utc`: `2026-07-17T10:54:36Z` ✓
- `endpoint`: public HTTPS `titleSearchServlet.do` ✓
- `request_params`: 完整 non-sensitive params ✓
- `raw_json_response.hasNextRow`: `false`（JSON bool）✓
- `raw_json_response.rowRange`: `100`（int, not bool）✓
- `raw_json_response.loadedRecord`: `0`（int）✓
- `raw_json_response.recordCnt`: `0`（int）✓
- `raw_json_response.result`: `"[]"`（string）✓
- 不含 cookie、authorization、proxy credential、headers 或本地 path ✓

### 5.4 Live smoke

manifest 107 lines，SHA-256 `db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe`：
- Public GET，`stockId=7609`，all categories，`20000101..20260717` ✓
- Round 1：`rowRange=100` → `loadedRecord=100, recordCnt=1669, hasNextRow=true` ✓
- Formula：`max(100*2, 1669) = 1669` ✓
- Round 2：`rowRange=1669` → `loadedRecord=1669, recordCnt=1669, hasNextRow=false` ✓
- `jq -e` verifier：true ✓
- non-range params 每轮 exact equal ✓
- endpoint 可达，未观察到 cap/clamp/stall ✓

### 5.5 Coverage

四文件逐文件 branch coverage：
- HKEX：**80.89%** ✓
- CNInfo：**89.28%** ✓
- protocol：**100.00%** ✓
- workflow：**81.05%** ✓

全部 `>=80.00%`，无 waiver/omit/pragma/padding。workflow `79.74%→81.05%` 通过真实 owner 行为测试修复。✓

### 5.6 Validation matrix

| Gate | Result |
|---|---|
| focused five-file suite | 172 passed |
| selected checkpoint/HKEX/CNInfo | 135 passed, 21 deselected |
| full Fins | 933 passed, 1 skipped, 38.72s |
| full pyright | 0 errors, 0 warnings, 0 informations |
| scoped Ruff | All checks passed |
| `git diff --check` | PASS |
| obsolete symbol scan | 0 matches |
| `if cancellation_checkpoint()` bool scan | 0 matches |
| `hasattr`/`getattr` scan | 0 matches |
| deferred scope scan | 0 added matches |

## 6. 历史 findings 最终状态

### 6.1 Plan findings

| Finding | Final status | Controller basis |
|---|---|---|
| `R10-PR-F01` | fixed / dual-rereview-closed | workflow-owned no-arg checkpoint；protocol transport；provider I/O boundary；typed cancel/provider error precedence/identity/cause；zero-publication tests |
| `R10-PR-F03` | fixed / dual-rereview-closed | HKEX 每个 cumulative GET、CNInfo 每个 supported period POST 前/后 exact ordering |
| `DS-R10-F02` | rejected-with-reason / final | baseline protocol coverage 40/40 100%；四文件各 >=80%，zero waiver |

### 6.2 Code review observations

| ID | Final disposition | 独立验证 |
|---|---|---|
| `R10-CR-O01` | rejected / no action | CNInfo `page_num > 50` 不在 R10 diff；accepted plan 禁止 CNInfo pagination redesign；不创建新 WU/issue ✓ |
| `R10-CR-O02` | intentional retention | `_extract_json_rows` 被 stock mapping 真实消费（`hkexnews_downloader.py:375`）✓ |
| `R10-CR-O03` | pre-existing non-completeness parsing | announcement `_first_text` 不承担 title-search completeness ✓ |
| `R10-CR-O04` | closed | 13/13 individual hashes + 两个 aggregate manifests 均已复现 ✓ |

### 6.3 Aggregate finding ledger

7 个历史 candidates 的终态：

| ID | 来源 | 最终状态 | 说明 |
|---|---|---|---|
| `R10-PR-F01` | AgentDS plan review | accepted → fixed → closed | 取消 owner 分裂；Controller 修正后 workflow-owned no-arg checkpoint |
| `R10-PR-F03` | AgentDS plan review | accepted → fixed → closed | CNInfo POST 粒度；Controller 修正后 per-period POST 前/后 |
| `DS-R10-F02` | AgentDS plan review | rejected-with-reason / final | protocol coverage 40/40 100%；zero waiver |
| `R10-CR-O01` | AgentDS code review | rejected / no action | CNInfo `page_num > 50` 不在 R10 diff；pre-existing/non-R10 |
| `R10-CR-O02` | AgentDS code review | rejected / no action | `_extract_json_rows` 被 stock mapping 真实消费；intentional retention |
| `R10-CR-O03` | AgentDS code review | rejected / no action | announcement `_first_text` 不承担 completeness；pre-existing |
| `R10-CR-O04` | AgentDS code review | closed | 13/13 individual hashes + 两个 aggregate manifests 均已复现 |

终态计数：

| 状态 | 数量 |
|---|---:|
| accepted / open | **0** |
| accepted → fixed → closed | **2**（F01、F03） |
| rejected / no-action | **5**（F02、O01-O03、O04） |
| deferred | **0** |
| blocker | **0** |

**无 accepted finding 被误拒绝/漏记/伪关闭。** 全部 7 个历史 candidates 均有直接代码证据和 Controller 裁决依据。

## 7. Semantic ownership drift 审查

### 7.1 HKEX official fields ownership

- `hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result` 只在 `hkexnews_downloader.py` 和 HKEX owner tests 中读取。
- shared protocol/workflow/CNInfo 不读取这些字段。
- `record_count` 仅是 private snapshot 字段和 test fixture helper 参数，不是 generic alias 或第二总数真源。
- selection、财期推断、amended 优先、去重仍由 `cn_report_selection.py` 持有。

**无 semantic ownership drift。** ✓

### 7.2 Cancellation ownership

- raw `Callable[[], bool]` 只由 workflow `_is_cancel_requested`（L420-441）和 `_raise_if_cancelled`（L444-473）解释。
- `Callable[[], None] | None` 在 protocol/providers 中只运输/调用。
- 无 ambient state、无 ContextVar、无 mutable setter、无反向依赖。

**无 cancellation ownership drift。** ✓

### 7.3 No downstream completeness checker

- CN/HK workflow 只消费 candidates 或 typed failure，不判断 HKEX completeness。
- selection、storage、Service、CLI 不读取 HKEX completeness fields。

**无 downstream completeness checker。** ✓

## 8. 过度耦合审查

- workflow 不 import HKEX downloader 具体类，只依赖 `CnReportDiscoveryClientProtocol`。
- protocol 不 import HKEX-specific types。
- checkpoint 只通过显式参数传递，无 ambient context。
- HKEX downloader 不 import workflow 或 protocol 模块。
- CNInfo 接受同一 checkpoint 签名但不获得 HKEX state machine。

**无过度耦合。** ✓

## 9. LLM-facing / README 影响

- R10 实现不产生 LLM-facing 文本（不修改 tool schema、prompt 或 LLM message）。
- Protocol docstring 描述 provider 语义，不暴露内部类型名或 Host 治理字段。
- 错误消息只含业务可读 context（stock_code、lang、t1code、t2code、row_range、count），不含 raw response、cookie/header、local path。
- `dayu/fins/README.md`：仅补充 HKEX official cumulative、strict completeness、snapshot replacement/final-only owner contract。未写 WU 流水账、未来计划或测试清单。
- `tests/README.md`：删除旧 typed truncated 断言说明，改为 official fields、cumulative、latest count、replacement、contradiction/no-progress 与 checkpoint/zero-publication 当前覆盖。
- 根 README / `dayu/README.md` / design docs：不更新。

**README 更新符合约束。** ✓

## 10. Security retention

- HTTP timeout（30s）、max_retries（3）、exponential backoff、throttle（0.3s）保留。
- HTTPS HKEX endpoint 不变。
- PDF magic bytes（`%PDF-`）+ min size（1024 bytes）校验保留。
- Stock code matching 保留。
- Error messages 不含 raw response/cookie/auth/local path。
- Captured fixture 只用 public GET，不含 secrets。
- Live smoke 只用 public GET，不下载 PDF、不调用 mutation endpoint、不写 business workspace。
- 未新增 permission schema、auth profile、DNS/egress framework、browser capability。

**安全边界保留完整。** ✓

## 11. Deferred Issue / R11/R12 / Topic 8/9 结论

| Item | 状态 |
|---|---|
| Issue 142/151/175/177/178 | no-touch — 由既有 Issue tracker 持有 |
| R11/R12 | no-touch — 未授权 |
| Web/WeChat/render | no-touch — 由既有 Issue tracker 持有 |
| Topic 8/9 | no-touch — 已由用户裁决 |
| unified tool authorization | no-touch — deferred |

**全部 deferred items 正确保留，未实现也未误删。** ✓

## 12. Commit scope 与 staged-empty

- implementation target 包含 13 paths：12 个 product/test/fixture/README + 1 个 AgentCodex implementation evidence。
- 最终 accepted implementation commit 的 exact scope 由 Controller 在 aggregate adjudication 后确定，可能包含本 aggregate review artifact 与第二路 aggregate review artifact；本 review 不预判 Controller 的 commit scope 裁决。
- staged tree：empty。
- Controller-owned dirty files（`docs/host/issues-implementation-control.md`、authorization、validation、adjudication）未触碰。
- smoke evidence 位于 gitignored `workspace/tmp/`。
- 无 unexpected production/test/README/design diff。

**implementation target 完整且不夹带无关改动。** ✓

## 13. Residual risk 分类

| Risk | Classification | Owner / Destination |
|---|---|---|
| 官方未来 schema/行为变化 | residual — 由当前 strict typed fail-closed contract 拒绝 | 未来 provider evidence-driven WU（非当前 slice fallback） |
| 外部 HKEX endpoint DNS/网络/challenge/限流不可用 | 环境限制；local deterministic gates 不受影响 | R10 completion report 环境限制记录 |
| Provider 可能未来引入 rowRange hard cap | evidence-driven residual；当前无证据 | 未来独立 HKEX provider WU |
| CNInfo `page_num > 50` 保护 | pre-existing / non-R10；R10-CR-O01 rejected / no action | 不在 R10 diff；accepted plan 禁止 CNInfo pagination redesign；不创建新 WU/issue |
| `_extract_json_rows` / `_parse_embedded_json_list` | intentional retention | stock mapping 真实消费者 |
| announcement `_first_text` raw field aliases | pre-existing non-completeness parsing | 不承担 title-search completeness |

**所有 residual 均有准确 owner/destination，无未分类项。** ✓

## 14. 最终结论

**PASS — 0 material findings / 0 blocking questions / 0 residual without owner。**

### 组合证据总结

1. **Plan 兑现**：accepted plan 的全部 goal/success signals/non-goals 已在 implementation 中完整实现。
2. **State machine 一致性**：official HKEX cumulative protocol 与 call path 跨 workflow/protocol/HKEX 组合完全一致；terminal-first/progress/latest count/query invariance/final-only/cancel/error precedence 全部正确。
3. **测试证据一致性**：30 行 test matrix 全部有对应实现；captured fixture 与 live smoke 证据一致；mock 不固化偶然行为。
4. **历史 findings 状态**：7 个历史 candidates 中 2 个 accepted→fixed→closed（F01、F03）、5 个 rejected/no-action（F02、O01-O04）；accepted/open=0，blocker=0。
5. **Semantic ownership drift**：零 drift。HKEX completeness fields 只在 HKEX owner 内；cancellation 只由 workflow 解释。
6. **Security / deferred**：安全边界保留完整；Issue 142/151/175/177/178、R11/R12、Topic 8/9、Web/WeChat/render、统一 authorization 全部正确 no-touch。
7. **Commit scope**：implementation target 13 paths 完整且不夹带无关改动；最终 accepted commit scope 由 Controller 在 aggregate adjudication 后确定；staged tree empty。

### 下一 gate

R10 aggregate deepreview 完成。两路 aggregate PASS 后方可考虑 accepted implementation commit。R10 completion、R11/R12 均未授权。
