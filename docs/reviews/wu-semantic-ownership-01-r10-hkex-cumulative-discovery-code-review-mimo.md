# WU-SEMANTIC-OWNERSHIP-01 / R10 implementation code deepreview (AgentMiMo)

## 1. Review scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- review 类型：第一路完整 code deepreview。
- immutable baseline HEAD/accepted plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- AgentCodex implementation evidence SHA-256：`3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5`。
- Controller validation SHA-256：`ea244cad3fc4d3b70809bf76562bfaccb050e034f730a4d7530bee2c02719783`。
- **verdict：PASS。**
- **material findings：0。**
- **blocking questions：0。**

## 2. Source locks 与 drift 结论

### 2.1 Controller-owned files（非被审 target，reviewer 只读）

| Source | SHA-256 |
|---|---|
| accepted fixed plan | `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` |
| implementation authorization | `f3ae9f58fce2a7403496ea33dde84aa1b9a0c3bed23f37e0c8dd078aa0bc0d38` |

### 2.2 Implementation target locks（13 paths，全部重算一致）

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1266 | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` |
| `dayu/fins/downloaders/cninfo_downloader.py` | 849 | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` |
| `dayu/fins/pipelines/cn_download_protocols.py` | 231 | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` |
| `dayu/fins/pipelines/cn_download_workflow.py` | 820 | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` |
| `tests/fins/test_hkexnews_downloader.py` | 1706 | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` |
| `tests/fins/test_cninfo_downloader.py` | 1619 | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` |
| `tests/fins/test_cn_download_workflow.py` | 1793 | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` |
| `tests/fins/test_cn_pipeline.py` | 759 | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` |
| `tests/fins/test_cn_download_runtime.py` | 711 | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | 34 | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` |
| `dayu/fins/README.md` | 793 | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| `tests/README.md` | 293 | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |
| AgentCodex evidence | 226 | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` |

**drift 结论：零 drift。** 个别文件 SHA-256 全部与 Controller validation 锁定一致。staged tree empty。Controller-owned dirty files（`docs/host/issues-implementation-control.md`、authorization、Controller validation）未被触碰。

## 3. Correctness 审查

### 3.1 HKEX official cumulative owner — PASS

- `_HkexnewsTitleSearchSnapshot`（L114-122）：private frozen dataclass，6 个 typed 字段。shared protocol/workflow/CNInfo 不读取这些字段。
- strict parser（L697-929）：五个必填字段逐一验证。`hasNextRow` 只接受 exact JSON bool（L816-821）；`rowRange/loadedRecord/recordCnt` 先拒绝 bool 再检查 int 和非负（L844-853）；`result` 必须是非空字符串化 JSON array 且每行是 object（L856-902）。
- 同轮 invariants（L759-793）：response range == request；loaded == len(rows)；loaded <= count；loaded <= range；continuation: loaded < count；terminal: loaded == count == len(rows)。全部正确。
- 累计算法（L472-509）：initial range 100；next range = `max(current_range * 2, snapshot.record_count)`；不冻结首次总数。continuation 间 loaded 必须严格增加（L493-504）。terminal-first 优先返回（L490-491）。
- query invariance（L411-428）：base_params 在 language/category 循环外构造一次 `MappingProxyType`，每轮只派生 `rowRange`。
- snapshot replacement（L489）：`latest_rows = snapshot.rows`；只有 final complete rows 进入后续处理。无 append/dedup。
- 旧语义删除：`_HkexnewsRowsPage.total_count`、`_extract_title_search_total_count`、`_coerce_non_negative_int`、`_raise_if_title_search_truncated`、`HkexnewsDiscoveryTruncatedError`、`_HKEXNEWS_ROW_LIMIT`/`_HKEXNEWS_ROW_RANGE` 全部删除。目标 scan 为 0。

### 3.2 Cancellation seam — PASS

- raw `Callable[[], bool]` 只由 workflow `_is_cancel_requested`（L420-441）和 `_raise_if_cancelled`（L444-473）解释。
- workflow 在 `run_cn_download_stream_impl` L201-209 用 `functools.partial` 构造一次 no-arg checkpoint，raw checker 非空时传同一个对象给 discovery，为空时传 `None`。
- protocol（`cn_download_protocols.py` L88）只声明 `Callable[[], None] | None`，不调用、不解释。
- HKEX 在 `_fetch_complete_title_search_rows` 中，每个 cumulative GET 前（L475-476）和成功响应后 strict parse 前（L480-481）各调用一次同一 checkpoint。
- CNInfo 在 `_query_announcements` 中，每个 pagination POST 前（L471-472）和成功响应后（L484-485）各调用一次同一 checkpoint。
- `if cancellation_checkpoint()` bool 解释 scan：0 matches。
- `Callable[[], bool]` 只出现在 workflow 模块（3 处），protocol/providers 只有 `Callable[[], None] | None`。

### 3.3 Exception precedence — PASS

- HKEX `list_report_candidates`（L309-316）：`except CnDownloadCancelledError: raise` 和 `except HkexnewsProviderProtocolError: raise` 在 generic `except RuntimeError as exc` wrapper 前 bare re-raise，保持 identity/type/cause。
- CNInfo `list_report_candidates`（L295-300）：`except CnDownloadCancelledError: raise` 在 generic `except RuntimeError as exc` wrapper 前 bare re-raise。

### 3.4 Response model 保密性 — PASS

- `_HkexnewsTitleSearchSnapshot` 是 module-private frozen dataclass，不放入 shared models。
- `cn_download_models.py` 未修改。

## 4. Stability 审查

### 4.1 无限循环防护 — PASS

- continuation 间 loaded 必须严格增加（L493-504），否则 typed fail。
- 没有 hard cap、日期递归、sleep-based retry state 或第二 cursor。
- next range 公式 `max(current * 2, recordCnt)` 保证有限增长。

### 4.2 Terminal-first — PASS

- `if not snapshot.has_next_row: return latest_rows`（L490-491）优先于跨轮 progress 比较。
- 自洽 count shrink 被接受（terminal 优先于历史进度）。

### 4.3 HTTP retry — PASS

- `_http_get_json`（L511-543）：最多 `max_retries` 次，指数退避。
- transport 失败（HTTP error、JSON decode error、ValueError）全部捕获并重试。
- retry exhaustion 后抛 `RuntimeError`，不伪造成功响应。

## 5. Maintainability 审查

### 5.1 代码组织 — PASS

- 模块级私有辅助函数（`_parse_title_search_snapshot`、`_require_title_search_bool`、`_require_title_search_non_negative_int`、`_require_title_search_rows`、`_require_title_search_field`）职责单一，无嵌套函数/类。
- 常量使用 `Final` 修饰，有业务可读名称。
- docstring 完整，中文，包含参数/返回值/异常。

### 5.2 类型安全 — PASS

- 所有签名有完整类型标注。
- 无 `object`、`Any`、无类型参数。
- pyright 0 errors（AgentCodex 与 Controller 验证）。

## 6. Adversarial failure 审查

### 6.1 缺失/拼错/矛盾响应 — PASS

- 五个必填字段逐一检查缺失（L726-929）。
- type 严格：bool 不接受 string/int/null；int 不接受 bool/string/float；result 不接受 non-string/malformed/non-list/non-object-row。
- 同轮矛盾检查（L759-793）：response range != request；loaded != len；loaded > count；loaded > range；true 且 loaded == count；false 且三数不等。

### 6.2 No-progress — PASS

- continuation 间 `loaded_record <= previous_continuation_loaded` 时立即 typed fail（L493-504）。
- request count 有上界（progress 要求严格增加，否则有限失败）。

### 6.3 Cancel 时序 — PASS

- before-first-GET、after-response、before-next-round、after-final-round 取消均有测试。
- 任一取消后不发下一 request、不 parse partial rows、不发布 candidates/HEAD。

## 7. Semantic ownership drift 审查

### 7.1 HKEX official fields — PASS

- `hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result` 只在 HKEX owner 和 HKEX owner tests 中读取。
- shared workflow/CNInfo 不读取这些字段。
- `record_count` 仅是 private snapshot 字段和 test fixture helper 参数，不是 generic alias 或第二总数真源。

### 7.2 Cancellation ownership — PASS

- raw `Callable[[], bool]` 只由 workflow 解释。
- `Callable[[], None] | None` 在 protocol/providers 中只运输/调用。
- 无 ambient state、无 ContextVar、无 mutable setter、无反向依赖。

### 7.3 No downstream completeness checker — PASS

- CN/HK workflow 只消费 candidates 或 typed failure，不判断 HKEX completeness。
- selection、storage、Service、CLI 不读取 HKEX completeness fields。

## 8. 过度耦合审查

- workflow 不 import HKEX downloader 具体类，只依赖 `CnReportDiscoveryClientProtocol`。
- protocol 不 import HKEX-specific types。
- checkpoint 只通过显式参数传递，无 ambient context。
- HKEX downloader 不 import workflow 或 protocol 模块。

**结论：无过度耦合。**

## 9. 测试真实性审查

### 9.1 断言 owner contract 而非 mock 固化 — PASS

- `_RecordingCheckpoint`（L48-72）：记录精确调用顺序，支持在指定序号抛异常。tests 断言 exact event sequence、checkpoint object identity、exception identity/cause chain。
- `_title_search_payload`（L250-284）：构造官方 exact top-level keys/types，不使用旧 generic fixture。
- tests 断言：exact checkpoint sequence（`CP1, GET(100), CP2` 等）；query invariance（去除 rowRange 后 dict exact equality）；final-only rows（candidates 源头 ID 只来自 final snapshot）；partial zero-publication（head_count == 0）；exception identity（`exc_info.value is expected`）；cause chain（两层 cause 保留）。

### 9.2 四文件 branch coverage — PASS

AgentCodex 与 Controller 独立验证：
- HKEX：80.89%
- CNInfo：89.28%
- protocol：100.00%
- workflow：81.05%

全部 `>=80.00%`，无 waiver/omit/pragma/padding。

### 9.3 Captured fixture — PASS

- `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`：34 lines，SHA-256 `d4bf5965...`。
- 包含 `captured_at_utc`、endpoint、request params、HTTP status、raw response body SHA-256、raw response body、raw JSON response、capture tool。
- 不含 cookie、authorization、proxy credential、headers 或本地 path。
- raw JSON response 的 field types 与 strict parser 一致：`hasNextRow` 是 bool，三个 count/range 字段是 int，`result` 是 string。

### 9.4 Live smoke — PASS

- manifest 107 lines，SHA-256 `db1f67c5...`。
- 首轮 `100/100/1669/true`，第二轮请求 1669 并得到 `1669/1669/false`。
- non-range params 每轮 exact equal。
- formula `max(100*2, 1669) = 1669` 正确。
- 两轮 raw body hashes 与 manifest 一致。

## 10. Security retention 审查

- HTTP timeout（30s）、retry（3 次）、throttle（0.3s 间隔）、指数退避保留。
- HTTPS HKEX endpoint、公开 GET only。
- PDF magic bytes（`%PDF-`）和最小字节数（1024）校验保留。
- stock matching（`_announcement_matches_stock`）保留。
- error messages 只含业务可读 context，不含 raw response/cookie/header/local path/authorization。
- fixture/smoke 只做公开 GET，不保存 cookie/auth/header/proxy credential，不下载 PDF，不写业务 workspace。

**结论：安全边界保留完整。**

## 11. Deferred-scope leakage 审查

- Issue 142/151/175/177/178：0 实现。
- R11/R12：0 实现。
- Web/WeChat/render：0 实现。
- Topic 8/9：0 实现。
- unified tool authorization：0 实现。
- hard cap / date recursion / watchdog / compatibility / generic pagination/cancellation framework：0 实现。
- storage transaction / direct-stream terminal：0 实现。

**结论：零 deferred-scope leakage。**

## 12. README 审查

- `dayu/fins/README.md`：已读取 `Agent更新约束【必须遵守】`。仅补充 HKEX official cumulative、strict completeness、snapshot replacement/final-only owner contract。未写 WU 流水账、未来计划或测试清单。
- `tests/README.md`：删除旧 typed truncated 断言说明，改为 official fields、cumulative、latest count、replacement、contradiction/no-progress 与 checkpoint/zero-publication 当前覆盖。
- 根 README / `dayu/README.md` / design docs：不更新。用户入口、CLI、分层与稳定设计真源未变。

**结论：README 更新符合约束。**

## 13. Git 状态

- staged tree：empty。
- Controller-owned dirty files（`docs/host/issues-implementation-control.md`、authorization、Controller validation）未触碰。
- untracked：AgentCodex evidence、Controller authorization、Controller validation、fixture 目录。
- 无 unexpected production/test/README/design diff。

## 14. Residual / no-action 分类

| Item | Classification |
|---|---|
| 官方未来 schema/行为变化 | residual — 由当前 strict typed fail-closed contract 拒绝，不构成本 slice 未实现 fallback |
| Issue 142/151/175/177/178 | no-touch — 由既有 Issue tracker 持有 |
| R11/R12 | no-touch — 未授权 |
| Web/WeChat/render | no-touch — 由既有 Issue tracker 持有 |
| Topic 8/9 | no-touch — 已由用户裁决 |
| unified tool authorization | no-touch — deferred |

## 15. Review handoff

- material findings：0。
- blocking questions：0。
- artifact：本文件，target 为 `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-review-mimo.md`。
- sorted path-manifest SHA-256（含本 review）：待外部计算。
- content-lock manifest SHA-256（含本 review）：待外部计算。
- Controller validation 138 lines / SHA-256：`ea244cad3fc4d3b70809bf76562bfaccb050e034f730a4d7530bee2c02719783`。
- staged tree：empty。
- next gate：AgentDS 并发完整 code deepreview；两路 PASS 后方可进入 fix/commit。
