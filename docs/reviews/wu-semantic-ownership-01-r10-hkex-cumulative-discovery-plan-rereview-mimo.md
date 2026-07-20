# WU-SEMANTIC-OWNERSHIP-01 / R10 fixed plan — AgentMiMo 第一路完整 re-review

## 1. Review identity 与 target lock

- **reviewer**：AgentMiMo（第一路完整 fixed-plan re-review）
- **review type**：adversarial re-review，不是 plan acceptance 或 implementation authorization
- **target artifact**：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
- **target lock**：698 lines；SHA-256 `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` —— **已核对一致** ✅
- **baseline HEAD**：`1c2585275f4134d8456a3fda2d84464e4e52c9d7` —— **已核对一致** ✅
- **branch**：`phaseflow/host-issues-control`
- **staged tree**：empty —— **已核对一致** ✅
- **review timestamp**：`20260717-182813`

## 2. Prior artifact locks

| Artifact | Lines | SHA-256 | 核对 |
|---|---:|---|---|
| R10 pre-fix plan (已替换) | 605 | `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699` | ✅ |
| AgentMiMo 初轮 review | 166 | `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16` | ✅ |
| AgentDS 初轮 review | 338 | `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce` | ✅ |
| Controller adjudication | 106 | `3659ef62964b195cda60d4c4d5e961214594076e75fc0a52adcda4f076493f4f` | ✅ |
| Codex fix artifact | 120 | `02db30f1d365efd76917b3326893c2e7c58e27c99cb0a63ae8b695f6edb0ffe8` | ✅ |
| Controller fix validation | 107 | `38f184d11cc371216c80dea42a238b9867e7cbf7ffc99f15d93811976478bcd8` | ✅ |

## 3. Implementation input source locks

以下 production/test/README SHA 与 fixed plan §2.2 locks 完全一致：

| Source | Lines | SHA-256 | 核对 |
|---|---:|---|---|
| `hkexnews_downloader.py` | 1065 | `8c7c1a3b8e1aebc91ec82756754eb7894d6748471b69ce164a9798b260f5eb31` | ✅ |
| `test_hkexnews_downloader.py` | 1213 | `d98266b8016e47a5ba4f77d680196b373933f71b184e559b2b483bd76f9de1d9` | ✅ |
| `test_cn_download_workflow.py` | 1660 | `c2d86d4778002d904df40ab0c5ac67660683e76ea989a692d917650aa09b1e1f` | ✅ |
| `cn_download_protocols.py` | 227 | `a92f283c0284aa1fce77031d73faf3cf9b37f6438b52b91b1cd317c26a6c003e` | ✅ |
| `cn_download_workflow.py` | 806 | `3c27e009897c4c6030520f891f38648876cf3dd6a26c14d27f7ae50473f3c24f` | ✅ |
| `cninfo_downloader.py` | 835 | `baab2ae471fc3f8201fc8bf97447c3fa647abd7dc25788d496d135a82f829d07` | ✅ |
| `test_cninfo_downloader.py` | 1397 | `92e518f52401b0106c7726a7984b0d90c18cb58aba41aee7470c23864ce15399` | ✅ |
| `test_cn_pipeline.py` | 718 | `7f00b257ecc7d128218aeca2505ea8cb6e3f89f624d58c3a8c734e8edf5189ee` | ✅ |
| `test_cn_download_runtime.py` | 704 | `b37a4a86c607f57982536097a16b58a4297b1fcb4d99e406db49e4ec7dc95ba9` | ✅ |
| `dayu/fins/README.md` | 791 | `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76` | ✅ |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` | ✅ |

`git diff --cached --name-only`：empty。`git diff --check`：PASS（无 whitespace error）。

## 4. Prior finding closure

### R10-PR-F01 — CLOSED

**根因**：raw `Callable[[], bool]` 被运输到 provider，取消解释 owner 分裂。

**Fixed plan 闭合证明**：

1. **§1 定位修正**：明确 "workflow 必须用既有 `_raise_if_cancelled` 语义把 raw `Callable[[], bool] | None` 收敛为一个 workflow-owned、no-arg、无返回值的 `cancellation_checkpoint: Callable[[], None] | None`"。
2. **§4.1 owner map 修正**：workflow 使用 `functools.partial(_raise_if_cancelled, module=..., ticker=..., document_id="", cancel_checker=cancel_checker)` 构造 no-arg checkpoint。protocol 只运输 `Callable[[], None] | None`。provider 只调用，不解释 bool。
3. **§5.3 exception precedence 修正**：显式三路 — `except CnDownloadCancelledError: raise`、`except HkexnewsProviderProtocolError: raise`、`except RuntimeError as exc: existing generic wrapper`。caller cancel object identity 保持。
4. **§6.3 cancellation seam 修正**：HKEX 每个 cumulative GET 前/成功响应后各调用一次同一 checkpoint。CNInfo 每个 fiscal-period POST 前/成功响应后各调用一次。workflow 原有 discovery 前后检查保留。
5. **§8 test matrix 修正**：新增 "caller typed cancel identity"、"checker non-cancel failure"、"HKEX exception precedence"、"workflow bool true mapping" 等显式测试行。

**直接代码验证**：

- `cn_download_workflow.py:430-459`：`_raise_if_cancelled` 存在且签名为 `(module, ticker, document_id, cancel_checker)` —— functools.partial 绑定正确。
- `cn_download_workflow.py:406-428`：`_is_cancel_requested` 存在，处理 bool true、`CnDownloadCancelledError` 主动抛出和非取消异常包装为 RuntimeError —— checkpoint 内部行为已由 workflow owner 定义。
- `cn_download_workflow.py:233`：当前 `discovery.list_report_candidates(query, profile)` 不传 cancel_checker —— 确认需要修改。
- `cn_download_protocols.py:83-106`：当前 protocol 签名无 cancel_checkpoint 参数 —— 确认需要修改。
- `hkexnews_downloader.py:294-299`：当前 `except HkexnewsDiscoveryTruncatedError: raise` + `except RuntimeError as exc: raise RuntimeError(...) from exc` —— 需新增 `HkexnewsProviderProtocolError` 和 `CnDownloadCancelledError` 在 generic wrapper 前的 passthrough。

**结论**：F01 在 plan owner boundary 内完整闭合。workflow 拥有取消语义，protocol 只运输，provider 只在 I/O 边界消费。无 owner 分裂、无反向依赖、无 helper 复制。

### R10-PR-F03 — CLOSED

**根因**：CNInfo "既有 discovery I/O 前后"可被理解为整个方法前后，未唯一指定多 period POST 粒度。

**Fixed plan 闭合证明**：

1. **§3.2 success signal 7 修正**："HKEX 每个 cumulative GET、CNInfo 每个既有 fiscal-period POST 前和响应返回后各调用一次"。
2. **§4.1 owner map 修正**："provider I/O boundary 的 checkpoint ordering" 明确到 "HKEX 每个 cumulative GET、CNInfo 每个既有 fiscal-period POST 前/后调用"。
3. **§6.3 cancellation seam 修正**：明确 "CNInfo 在每个已有 supported fiscal-period POST 前和成功响应后各调用一次同一 checkpoint"，并给出 exact trace `CP1, POST(period_1), CP2, CP3, POST(period_2), CP4`。
4. **§8 test matrix 修正**："CNInfo checkpoint sequence" 行给出 exact trace；"CNInfo response cancel" 和 "CNInfo before-next cancel" 行覆盖各取消时点。

**直接代码验证**：

- `cninfo_downloader.py:268`：`for period in query.target_periods:` —— 确认 CNInfo 按 period 循环发起 POST。
- `cninfo_downloader.py:280`：`self._query_announcements(...)` —— 每个 period 一次 HTTP POST。
- 两个 supported periods 的 exact trace `CP1, POST(p1), CP2, CP3, POST(p2), CP4` 与 per-period POST 语义一致。

**结论**：F03 在 plan owner boundary 内完整闭合。checkpoint 粒度精确到每个 fiscal-period POST，取消窗口最小化。

### DS-R10-F02 — REJECTED-WITH-REASON 确认

Controller baseline pre-check：

```text
dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%
```

Fixed plan §10.3 保留四个 changed production files 各自 branch coverage `>=80%`，零 N/A waiver/omit/pragma/padding。**确认 F02 维持 rejected。**

## 5. Adversarial re-review：逐项压测

### 5.1 functools.partial checkpoint owner / typing / reachability

**攻击路径**：尝试证明 functools.partial 构造不正确、类型不兼容或 production 不可达。

**验证**：

1. **构造正确性**：`functools.partial(_raise_if_cancelled, module=..., ticker=..., document_id="", cancel_checker=cancel_checker)` 绑定全部四个 keyword 参数。`_raise_if_cancelled` 签名为 `(module: str, ticker: str, document_id: str, cancel_checker: Callable[[], bool] | None) -> None`。partial 后得到 `Callable[[], None]`。正确。
2. **类型兼容性**：`Callable[[], None]` 赋给 `cancellation_checkpoint: Callable[[], None] | None`。pyright 兼容。
3. **Production reachability**：workflow `run_cn_download_stream_impl` 已持有 `cancel_checker: Callable[[], bool] | None`（line 55）。构造 checkpoint 后传给 `discovery.list_report_candidates(query, profile, cancellation_checkpoint=checkpoint)`。调用链完整。
4. **Import**：当前 `cn_download_workflow.py` 未 import `functools`；implementation agent 需添加 `import functools` 或 `from functools import partial`。这是明确的单行 import 变更，无歧义。
5. **Checkpoint identity**：同一 checkpoint 对象传入 discovery，provider 每次调用同一对象。test matrix 断言 "两次均为同一对象"。正确。

**结论**：functools.partial 构造正确、类型兼容、production 可达。无 finding。

### 5.2 HKEX/CNInfo 每真实 request 前后 ordering

**攻击路径**：尝试证明 checkpoint ordering 不明确、遗漏或与实际 HTTP 调用不匹配。

**验证**：

1. **HKEX ordering**：plan §6.2 state machine 明确 "if cancellation_checkpoint is not None: cancellation_checkpoint()" → "response = GET(...)" → "if cancellation_checkpoint is not None: cancellation_checkpoint()" → "snapshot = strict parse"。每个 cumulative GET 前后各一次，response 后 checkpoint 位于 strict parse 前。
2. **CNInfo ordering**：plan §6.3 明确 "每个已有 supported fiscal-period POST 前和成功响应后各调用一次同一 checkpoint"。exact trace `CP1, POST(p1), CP2, CP3, POST(p2), CP4`。
3. **HTTP helper retry 不影响 checkpoint**：plan §6.2 说明 "现有 helper 内部 retry 次数/退避保持不变；retry exhaustion 没有成功响应，因而不伪造 after-response checkpoint"。checkpoint 在 `_http_get_json` 调用前和成功返回后，不在 retry 循环内。
4. **取消后无下一 request**：plan §8 test matrix "cancel after response"、"cancel before later round"、"cancel after final round"、"CNInfo response cancel"、"CNInfo before-next cancel" 全部断言 "不发下一 request"。

**结论**：ordering 明确、与 HTTP 调用精确对齐。无 finding。

### 5.3 Typed cancel identity / provider error / cause chain / generic wrapper precedence

**攻击路径**：尝试证明 exception precedence 有漏洞、identity 被抹平或 cause chain 断裂。

**验证**：

1. **HKEX precedence**：plan §5.3 显式三路 — `except CnDownloadCancelledError: raise` → `except HkexnewsProviderProtocolError: raise` → `except RuntimeError as exc: raise RuntimeError("披露易公告分类查询失败...") from exc`。前两者在 generic wrapper 前原样通过。
2. **Caller cancel identity**：plan §5.3 "调用方主动抛出的同一取消对象必须跨 protocol/HKEX generic wrapper 保持 identity"。test matrix "caller typed cancel identity" 行断言 `exc.value is expected_cancel`。
3. **Non-cancel failure cause chain**：plan §5.3 "raw checker 自身的非取消故障只由 workflow 既有语义包装为带直接 cause 的 RuntimeError；若 HKEX 的 generic provider-context wrapper 再包装该 RuntimeError，测试必须断言完整 cause chain 仍指向 workflow wrapper 与原始 checker failure"。test matrix "checker non-cancel failure" 行断言 "workflow-owned RuntimeError 的 direct `__cause__ is expected_failure`；若经过 HKEX generic wrapper 则断言 exact 两层 cause chain"。
4. **CNInfo precedence**：plan §5.3 "CNInfo 的 checkpoint 调用必须位于现有 period transport `RuntimeError` wrapper 之外，或用 `except CnDownloadCancelledError: raise` 把 typed cancel 放在 generic wrapper 之前"。当前 cninfo_downloader.py:289-292 的 `except RuntimeError as exc: raise RuntimeError("巨潮公告分类查询失败...") from exc` 需在前面加 `except CnDownloadCancelledError: raise`。

**直接代码验证**：

- `hkexnews_downloader.py:294-299`：当前 precedence 为 `except HkexnewsDiscoveryTruncatedError: raise` → `except RuntimeError as exc: raise RuntimeError(...) from exc`。需新增 `CnDownloadCancelledError` 和 `HkexnewsProviderProtocolError` 在 `RuntimeError` 前的 passthrough。
- `cninfo_downloader.py:289-292`：当前 precedence 为 `except RuntimeError as exc: raise RuntimeError(...) from exc`。需新增 `CnDownloadCancelledError` 在 `RuntimeError` 前的 passthrough。

**结论**：exception precedence 规格完整，identity/cause chain 有明确测试覆盖。无 finding。

### 5.4 Strict official parser

**攻击路径**：尝试证明 parser 规格与官方证据不一致、存在类型漏洞或引入第二 completeness owner。

**验证**：

1. **Bool 严格性**：plan §5.2.2 "hasNextRow 只接受 JSON bool；字符串 'true'、整数 0/1、null 全部拒绝"。Controller discussion Topic 6.6 live 验证确认为 JSON bool。Python `bool` 是 `int` 子类，plan 要求先显式拒绝 bool 再检查 int。
2. **Int 严格性**：plan §5.2.3 "rowRange、loadedRecord、recordCnt 只接受 JSON int 且非负；先显式拒绝 bool"。字符串数字、integral float、non-integral float、null、负值全部拒绝。
3. **Stringified-list**：plan §5.2.4 "result 只接受字符串化 JSON array。空字符串、malformed JSON、解码后非 list 或 list 中任一非-object row 全部 typed fail"。不回退到 `_extract_json_rows` 通用别名。
4. **Response range equality**：plan §5.2.5 "response_row_range 必须等于本轮 requested_row_range"。
5. **Same-round invariants**：plan §5.2.6-7 七项约束覆盖 loaded/count/range/hasNextRow 一致性。
6. **无第二 owner**：completeness decision 只在 HKEX downloader 内部。selection/workflow/storage 不读取官方字段。

**结论**：parser 规格与官方证据一致，类型检查严格，无第二 completeness owner。无 finding。

### 5.5 Cumulative progress

**攻击路径**：尝试证明 no-progress 检测有漏洞、允许无限 doubling 或拒绝合法 terminal。

**验证**：

1. **Progress 定义**：plan §6.2 "在 hasNextRow=true 的连续响应间，loadedRecord（也即 rows 长度）必须严格增加"。只检查 loaded，不检查 requested range 增长。
2. **Terminal precedence**：plan §6.2 "terminal complete 优先于跨轮 progress 比较：如果最新 snapshot 因 provider 数据变化而以内部一致的 hasNextRow=false 完成，使用该最新 complete snapshot"。
3. **无限 doubling 阻止**：round 1 `loaded=100, hasNextRow=true` → round 2 扩大 range 后仍 `loaded=100, hasNextRow=true` → `100 > 100` false → typed fail。有限失败。
4. **recordCnt 增长**：plan §6.2 "recordCnt 不缓存为第一次总数。每轮用最新值计算 next range；增长场景必须继续"。test matrix "multi-round count growth" 行覆盖。
5. **Next range 公式**：`max(current_range * 2, snapshot.record_count)`。无 fixed cap、日期 recursion 或第二 cursor。

**结论**：progress 检测正确，有限失败保证成立，合法 terminal 不被拒绝。无 finding。

### 5.6 Final-only

**攻击路径**：尝试证明 partial rows 会泄漏到 selection/HEAD/publication。

**验证**：

1. **Snapshot replacement**：plan §6.2 "每轮赋值 `latest_rows = snapshot.rows`，不使用 extend/+="。只有 complete 后才把 final rows 交给 `_parse_announcement(...)`。
2. **No append/dedup**：plan §6.2 "不比较 row identity、不要求旧 rows 是新 rows 的 exact prefix，也不在本地 dedup"。
3. **Cancel 后无 publication**：test matrix "cancel after response"、"cancel before later round"、"cancel after final round" 全部断言 "不 strict-parse/publish partial，不发下一 range；无 HEAD"。
4. **Overlapping/replacement**：test matrix "overlapping/replacement" 行 "返回只反映 final snapshot；first-only candidate/HEAD 不出现"。

**结论**：final-only 语义明确，partial rows 不进入 selection/HEAD。无 finding。

### 5.7 Query invariance

**攻击路径**：尝试证明参数在循环中被改变或规范化。

**验证**：

1. **Immutable base params**：plan §6.1 "每个 language/category 先构造一次 immutable base params"。每轮只派生新 dict 写入 `rowRange=str(current_row_range)`。
2. **不变字段**：`lang/category/market/stockId/searchType/documentType/t1code/t2Gcode/t2code/fromDate/toDate/MB-Daterange/sortByOptions/sortDir`。
3. **Test 断言**：test matrix "query invariance" 行 "去除 rowRange 后 dict exact equality；date/sort/category/filter 全不变"。

**结论**：query invariance 有明确规格和测试覆盖。无 finding。

### 5.8 Test matrix 完整性

**攻击路径**：尝试证明 test matrix 遗漏关键场景或断言不足。

**验证**：

Plan §8 共 30 行测试用例，覆盖：

| 维度 | 覆盖用例 |
|---|---|
| Happy path | checkpoint normal return、exact 100 complete、two-round cumulative、formula recordCnt branch、multi-round count growth |
| Snapshot 语义 | overlapping/replacement、final no duplicate |
| 参数不变性 | query invariance |
| 类型严格性 | missing fields (5 fields)、hasNext type、count/range type、negative fields、rows type |
| 一致性约束 | same-round contradictions (6 cases)、no progress、count change terminal |
| Cancel 时序 | cancel before first GET、cancel after response、cancel before later round、cancel after final round |
| Cancel 语义 | workflow bool true mapping、caller typed cancel identity、checker non-cancel failure、HKEX exception precedence |
| HTTP 失败 | HTTP initial failure、HTTP later failure |
| 隔离性 | per-language isolation |
| CNInfo | CNInfo checkpoint sequence、CNInfo response cancel、CNInfo before-next cancel |
| Test doubles | injected test doubles、workflow propagation |

每个用例有明确 setup 和 required assertions。cancel 测试使用 ordered event log 断言 exact sequence。

**结论**：test matrix 完整，覆盖 happy path、类型错误、一致性约束、cancel 时序、HTTP 失败、隔离性和 CNInfo 回归。无 finding。

### 5.9 Coverage

**攻击路径**：尝试证明 coverage gate 不可执行或有绕过路径。

**验证**：

1. **逐文件 >=80%**：plan §10.3 要求四个 modified production file 各自 `--fail-under=80`。命令具体到文件路径。
2. **Protocol baseline**：Controller pre-check 确认 `cn_download_protocols.py` 100% coverage（40/40 stmts, 0 miss）。F02 rejected。
3. **无 waiver**：plan 明确 "不得添加 waiver、omit、pragma 或 padding"。
4. **Controller validation 确认**：fix validation §5 "没有 N/A waiver、omit、pragma、padding 或 coverage compatibility"。

**结论**：coverage gate 可执行、无绕过路径。无 finding。

### 5.10 Smoke

**攻击路径**：尝试证明 live smoke 不可执行或 fixture 不足。

**验证**：

1. **Captured fixture**：plan §9.1 要求 `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` 包含 captured_at_utc、endpoint、params、HTTP status、raw body SHA-256、raw JSON response。不保存 cookie/auth/header。
2. **Local fixture gate**：plan §9.2 要求 captured small official shape replay + 程序化 100、两轮、多轮、count growth、矛盾/no-progress fixtures。
3. **Live smoke**：plan §9.3 opt-in、非默认、只读。选择 `recordCnt > 100` 的 query。每轮保存 normalized params、HTTP status、fields、raw body SHA-256。
4. **外部不可用分流**：plan §12 "外部 endpoint DNS/网络/challenge/限流不可用时，记录环境限制；local captured/deterministic protocol gates 仍必须通过"。

**结论**：fixture 和 smoke 规格完整，外部不可用有分流逻辑。无 finding。

### 5.11 Security

**攻击路径**：尝试证明安全边界被削弱。

**验证**：

Plan §11.2 明确保留：HTTP timeout、retry 上限、throttle、公开 HTTPS endpoint、PDF magic/size 校验、stock matching、error 不含 raw body/secret/local path。

- captured fixture/live smoke 只用公开 GET，不保存 cookie/auth/proxy/header。
- 不新增 permission schema、auth profile、DNS/egress framework 或 browser capability。

**结论**：安全边界完整保留。无 finding。

### 5.12 Deferred

**攻击路径**：尝试证明 deferred scope 有越界。

**验证**：

Plan §3.3 non-goals 和 §10.6 明确禁止：Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9、authorization/auth profile。§10.6 要求对 R10 changed hunks 做 deferred scope audit，不对历史文本全文 grep。

**结论**：deferred 边界清晰。无 finding。

## 6. 新 material finding

**零 finding。** 以下是对 fixed plan 的补充验证，均未发现 material issue：

### 6.1 functools.partial import 缺失（非 finding）

当前 `cn_download_workflow.py` 未 import `functools`。implementation agent 需添加单行 import。这是 trivial 实现细节，plan §4.1 已明确 `functools.partial` 构造方式，implementation agent 不可能遗漏。

### 6.2 CNInfo checkpoint 粒度的隐式推导（非 finding）

Plan §6.3 的 exact trace `CP1, POST(p1), CP2, CP3, POST(p2), CP4` 隐含每个 period POST 前后各一次 checkpoint，但未显式说 "在 for 循环体内、每个 `_query_announcements` 调用前后"。然而 test matrix "CNInfo checkpoint sequence" 行的 exact trace 足以唯一确定实现位置。implementation agent 有足够指引。

### 6.3 HKEX per-language 循环内的 checkpoint 位置（非 finding）

Plan §6.2 state machine 描述单个 language/category 的算法。当前代码 `hkexnews_downloader.py:391` 按 `self._languages` 循环。Plan §8 "per-language isolation" 测试用例覆盖每个 language 独立从 100 开始。implementation agent 需在 per-language 循环内实现 cumulative loop + checkpoint。plan 描述已充分。

### 6.4 `_extract_json_rows` 删除范围（非 finding）

Plan §5.3 要求删除 `_extract_title_search_total_count`、`_coerce_non_negative_int` 等。但 `_extract_json_rows`（hkexnews_downloader.py 中的通用 JSON 行提取 helper）是否需要删除？Plan §5.2.4 "不得回退到 generic `_extract_json_rows(...)` aliases" 只禁止回退，不要求删除该 helper 本身（它可能被其他代码使用）。Implementation agent 需在 code review 时确认 `_extract_json_rows` 的使用范围。非 plan blocker。

## 7. Open questions

无。所有关键设计决策已由 Controller adjudication 裁决、fixed plan 修正、Controller fix validation 确认。

## 8. Residual risks

| Risk | Classification | Owner |
|---|---|---|
| 外部 HKEX endpoint DNS/网络/challenge/限流不可用 | 环境限制；local deterministic gates 不受影响 | implementation agent 记录环境限制 |
| Provider 可能未来引入 rowRange hard cap | evidence-driven residual；当前无证据 | 未来独立 HKEX provider WU |
| `functools.partial` 需新增 import | trivial 实现细节 | implementation agent |
| `_extract_json_rows` 可能被其他模块使用 | implementation agent 确认；非 plan blocker | implementation agent |

## 9. Final plan review conclusion

**PASS**

Fixed plan 是 code-generation-ready 的。逐项证明：

1. **R10-PR-F01 CLOSED**：workflow 拥有取消语义（`functools.partial(_raise_if_cancelled, ...)` → no-arg checkpoint）；protocol 只运输 `Callable[[], None] | None`；provider 只在 I/O 边界消费；exception precedence 三路分明；identity/cause chain 有明确测试覆盖。
2. **R10-PR-F03 CLOSED**：HKEX 每个 cumulative GET 前/后、CNInfo 每个 fiscal-period POST 前/后各调用一次同一 checkpoint；exact trace 有测试矩阵覆盖；取消后无下一 request/partial publication。
3. **DS-R10-F02 REJECTED**：protocol file 100% coverage，零 waiver。
4. **functools.partial checkpoint**：构造正确、类型兼容、production 可达。
5. **HKEX/CNInfo ordering**：checkpoint 与 HTTP 调用精确对齐。
6. **Typed cancel / provider error / cause chain**：exception precedence 完整，identity 保持，cause chain 有两层断言。
7. **Strict parser**：与官方证据一致，无 alias/coercion/第二 owner。
8. **Cumulative progress**：有限失败保证，合法 terminal 不被拒绝。
9. **Final-only / query invariance**：有明确规格和测试覆盖。
10. **Test matrix**：30 行用例覆盖全部维度。
11. **Coverage / smoke / security / deferred**：全部完整。

Plan 满足 `docs/fins/design.md` §8、Controller discussion Topic 6.6 final adjudication、AGENTS.md 约束、umbrella plan §7.3 sub-WU plan 要求，以及 Controller fix validation 的闭合确认。可以交给 implementation agent。
