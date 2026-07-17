# WU-SEMANTIC-OWNERSHIP-01 / R10 HKEX cumulative discovery completion evidence

## 1. Gate、边界与最终结论

- 本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R10` 的
  completion evidence gate，不是新 WU、issue 或 feature。
- final accepted implementation commit：`140de7144f8bfb79e98cf399abd4712e79a1771b`，commit message
  `fins: accept R10 HKEX cumulative discovery remediation`。
- completion verdict：`COMPLETE / ZERO ACCEPTED OR OPEN FINDING / ZERO R10 ACTUAL ACCEPTED RESIDUAL`。
- R10 accepted plan、implementation、Controller validation、双路 code review、双路完整 re-review、双路 aggregate
  deepreview、Controller adjudication 与 final accepted implementation commit 证据链完整；本 artifact 只固化
  completion evidence，不修改产品、测试、README、design、plan、control 或 prior artifact。
- 本 gate 未 stage、commit、push、创建 PR 或进入 R11/R12。R10 completion 不等于 umbrella closeout；
  `WU-SEMANTIC-OWNERSHIP-01` 仍为 active。下一步只允许 Controller completion validation 与其后另行授权的
  exact-scope completion commit。

第一性原理判断仍成立：HKEX title search 的响应不是 offset page，而是从首条开始的 cumulative snapshot。
只有 downloader 同时拥有官方字段、累计请求状态和最终 rows，才能判定 discovery complete；下游 workflow、selection、
storage、Service 或 CLI 都没有足够事实补判。取消事实则由 workflow 对 raw checker 唯一解释，再以无参 checkpoint
直接传入真实 provider I/O boundary。最终实现把这两个事实分别留在正确 owner，没有建立第二 completeness owner、
generic pagination/cancellation framework 或 speculative hard cap。

## 2. R10 durable evidence universe

本次完整读取并交叉核对 R10 的 23 个 durable artifacts。Controller adjudication 是 finding disposition 真源；
MiMo/DS/Codex artifacts 提供代码、反例、修复与验证直接证据，不能覆盖 Controller 裁决。

Accepted-plan stage 的 11 个 artifacts 为：

1. `docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-entry-controller-validation.md`
3. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-controller-validation.md`
4. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-ds.md`
6. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-rereview-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-rereview-ds.md`
11. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-rereview-controller-adjudication.md`

Accepted fixed plan 为 698 lines / SHA-256
`fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a`；accepted-plan commit
`3dc01b10862a17cb4a4e982a1b684bb4c1680358` 是 final accepted implementation commit 的唯一 parent。
其余 12 个 implementation/review-stage artifacts 全部位于 final accepted implementation commit，见 §3.3。

## 3. Final accepted implementation commit 直接对象审计

### 3.1 Commit identity 与 exact manifest

| 项目 | commit object 直接证据 | 结论 |
|---|---|---|
| commit | `140de7144f8bfb79e98cf399abd4712e79a1771b` | match |
| parent | `3dc01b10862a17cb4a4e982a1b684bb4c1680358` | match；单一 parent |
| tree | `cc20f4d2bd4577a377c26db631bfd04bd549d287` | match |
| message | `fins: accept R10 HKEX cumulative discovery remediation` | match |
| changed path count | 25 | exact |
| status distribution | 13 added / 12 modified | exact |
| sorted 25-path manifest SHA-256 | `4f5bf5175989631a466b2fbb559201d4144b5ad3e8b19919ca40755596e9dd5c` | independently reproduced |
| commit-range whitespace check | `git diff --check` 零输出 | pass |

`git diff-tree -r` 的 25 条记录与授权闭集逐项相等：12 个 product/test/fixture/README、12 个 R10
implementation/review/re-review/aggregate evidence 与 Controller artifacts、1 个同步 control。没有额外路径、缺项、
rename、copy、delete、submodule、mode-only drift 或 workspace smoke artifact。

### 3.2 12 个 product/test/fixture/README paths 与 commit blobs

以下 Git blob OID 均直接来自 final accepted commit tree；对每个 `git show <commit>:<path>` bytes 独立计算
SHA-256，12/12 全部匹配 implementation/Controller immutable content locks。

| 类别 | Status | Path | Git blob OID | SHA-256 |
|---|---|---|---|---|
| README | M | `dayu/fins/README.md` | `6c5875c99297c71b5ccf252166338fc087e17cd7` | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| Product | M | `dayu/fins/downloaders/cninfo_downloader.py` | `b6e6fd743a44ab1b7bf177bdb0cbf224a75021b0` | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` |
| Product | M | `dayu/fins/downloaders/hkexnews_downloader.py` | `f4de3a48fe23b37e971b41f4929db46e52ae5649` | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` |
| Product | M | `dayu/fins/pipelines/cn_download_protocols.py` | `375551ebef7f06d76734b1de4ad23de2fcf5c5de` | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` |
| Product | M | `dayu/fins/pipelines/cn_download_workflow.py` | `d874a1b25c7fd284cbe5eaf7b4735b730897bd3b` | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` |
| README | M | `tests/README.md` | `325176d77f4789dff0b84afd38cbde4961245004` | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |
| Fixture | A | `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | `12b806336e68f4fbb373cebf653add6b64e77b0d` | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` |
| Test | M | `tests/fins/test_cn_download_runtime.py` | `53a8e2e649f4f4b04c1883167bdf3a87b1f59654` | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` |
| Test | M | `tests/fins/test_cn_download_workflow.py` | `8b15402effa0d2cbac6da5f252f04eaeb1ec4414` | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` |
| Test | M | `tests/fins/test_cn_pipeline.py` | `2c21fd66bd9d4a8dcdf363d4c517d76d347b7ce4` | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` |
| Test | M | `tests/fins/test_cninfo_downloader.py` | `cbce6e0b21f69869fcfdd641890745ee3ea241c0` | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` |
| Test | M | `tests/fins/test_hkexnews_downloader.py` | `43d235e04786d0463db1bdb40e0169eb95f89ca9` | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` |

### 3.3 12 个 implementation/review evidence paths 与 commit blobs

| Gate | Lines | Path | Git blob OID | SHA-256 |
|---|---:|---|---|---|
| implementation authorization | 120 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-controller-authorization.md` | `5c6fb59b5433768ac64e7dd83adafb68698073b8` | `f3ae9f58fce2a7403496ea33dde84aa1b9a0c3bed23f37e0c8dd078aa0bc0d38` |
| implementation | 226 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md` | `6a70c7703267495951a8fa85dab1eb9c87451499` | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` |
| implementation validation | 137 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-controller-validation.md` | `894ac27026de02b92643e0b256a8b0dc2202dad9` | `39b01e75f33324941d38dd7d3b10c53c0ff821fd99b2f47aac8ff6f61d5e84ca` |
| initial code review | 246 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-review-mimo.md` | `9d9b3a5c198794fcdd9446f37499f54d63f292b4` | `7e0a1f91d7b69882f079cbca287a33a4e4764e37707a7f62753d839bf1852f5d` |
| initial code review | 401 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-review-ds.md` | `ff15f088a254490f5eb51e495cb7564ff22c1af7` | `fc06cfd79f86e7a375fee2ba28f831a59673761c582bbc31072d18e3539db68f` |
| initial adjudication | 106 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-review-controller-adjudication.md` | `0e54734269a369b9c56d7cd0eee02928061b18de` | `fde40ca5174782be54c4373d248afdc66b137bd043de3560e840dc9e6061201f` |
| complete re-review | 262 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-rereview-mimo.md` | `7fc320ee7b44a0ca25fbecec9f73e65dab49ff4d` | `0bc18df2c0c343aeae3b0be04ceaee658ddc6fba89b44452c1f773dc7e045f43` |
| complete re-review | 406 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-rereview-ds.md` | `1733361ea412fe869815f8592004f89836935650` | `60cb426cd5f454d7910faffa8a9a73fb3145c4b982d56a5b40d8f4322fd8f9ae` |
| re-review adjudication | 85 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-code-rereview-controller-adjudication.md` | `3a662b62d96c4ce2eb3584f9a28bc3bdf65e8f46` | `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` |
| aggregate deepreview | 413 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-aggregate-deepreview-mimo.md` | `b2779000d2ae10948d111dd995f89573be5d7d1c` | `584f8a09f49db899c0e3843610b967b4ee35b467edce4bdd96469f57afe85879` |
| aggregate deepreview | 716 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-aggregate-deepreview-ds.md` | `763daf84eae572bdb62fbea98c5dccc8f9abd0c7` | `9bcbb84dfa57a24dff9938657661f2999c361a09f3e24df269bdfd8970c77f9f` |
| aggregate adjudication | 92 | `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-aggregate-deepreview-controller-adjudication.md` | `5b10b5b5e720f22efe33b759297ac4d437c35ca7` | `7d5fd871ac14fdc0780c7a23ab3a60975b7bc340f1a96a591642eed184c0787a` |

### 3.4 Commit 内 control path 与当前 Controller ownership

| 状态 | Path | Git blob OID |
|---|---|---|
| final accepted commit `M` | `docs/host/issues-implementation-control.md` | `7432060350b063dfca8f56f609b6c5831bb58d1e` |
| current working-tree Controller version | 同一路径 | `6a1c3b79da1de97dacbf8b1a815aa7fdc976cf6b` |

当前 working tree 的 control 是 final accepted implementation commit 后由 Controller 有意推进到 completion gate 的版本。
本 gate 只读取并保持它，不修改、不覆盖、不 stage，也不把它吸收到本 completion artifact。

## 4. Aggregate audit-lock refresh 与 product/semantic no-drift

### 4.1 Final 32-path committed-blob lock

`workspace/tmp/r10-aggregate-target-paths.txt` 是 exact 32 lines，path-manifest SHA-256 为
`2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde`。对其中每个路径直接读取
`140de7144f8bfb79e98cf399abd4712e79a1771b:<path>`，按路径顺序生成 `SHA-256  path` lines 后再计算
SHA-256，独立复算得到：

`7b0c8a992870dd1c3b88597f1761dfed9294c6f9f0b1cc2bd2ca359ee76a75db`

结果与 final MiMo、DS、Controller aggregate artifacts 完全一致。旧 `187cc123...bd666` 只是三个 Controller
Markdown 清理 EOF 空行前的 review-time lock，不是 final commit lock。

三条 Controller final committed blob locks 是：

| Artifact | Final lines | Final SHA-256 | Historical pre-normalization lock |
|---|---:|---|---|
| implementation Controller validation | 137 | `39b01e75f33324941d38dd7d3b10c53c0ff821fd99b2f47aac8ff6f61d5e84ca` | 138 lines / `ea244cad...2783` |
| initial code-review Controller adjudication | 106 | `fde40ca5174782be54c4373d248afdc66b137bd043de3560e840dc9e6061201f` | 107 lines / `559f582a...7db1` |
| code-rereview Controller adjudication | 85 | `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` | 86 lines / `5deeb119...f7a5` |

Controller staging 的 `git diff --check` 仅要求删除这三个新建 Markdown 各一个多余 EOF 空行。MiMo 与 DS 在同一
aggregate task 内独立复核正文等价并刷新 final locks；Controller adjudication也明确记录该事实。正文 contract、
finding disposition 和验证结论没有变化。

### 4.2 12-path product binary diff lock

对 parent `3dc01b10862a17cb4a4e982a1b684bb4c1680358` 到 final accepted commit，按 §3.2 的 12 个路径一次
生成 `git diff --binary` 并对原始 bytes 计算 SHA-256，独立复算结果为：

`75799a7e238bc1ed286b8ecdf5dc4122c089d933ca77e242fa2e7f4eaea0b140`

结果与 Controller authority lock 完全一致；`git diff --check` 零输出。与被重写的 pre-refresh tree直接比较，12 个
product/test/fixture/README paths逐字节无差异；树差异只落在 Controller control 与三份 aggregate audit artifacts。
因此 audit refresh 没有产品 byte drift，也没有 owner/state-machine/cancellation/publication/finding 语义 drift。

## 5. 语义 owner、state machine、cancellation 与 publication contract

### 5.1 HKEX official cumulative owner

- `dayu/fins/downloaders/hkexnews_downloader.py` 的 private frozen
  `_HkexnewsTitleSearchSnapshot` 是 `hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt` 与 typed rows 的唯一
  provider contract owner；shared protocol、workflow、CNInfo、selection、storage、Service 与 CLI 均不读取这些字段。
- strict parser 要求 top-level object 与五个官方必填字段：`hasNextRow` 只能是 JSON bool；三个 count/range
  只能是非负 JSON int 且先拒绝 bool-as-int；`result` 只能是非空字符串化 object array。missing、wrong type、negative、
  malformed、non-object row、response/request range 不等、loaded/rows/count/range 矛盾全部抛
  `HkexnewsProviderProtocolError`，无 alias、coercion、default、loose parsing 或 fallback。
- state machine 从 100 开始；continuation 使用最新 `recordCnt` 计算
  `max(current_row_range * 2, snapshot.record_count)`；非 `rowRange` 查询参数保持不变。
- 每轮以 `latest_rows = snapshot.rows` 替换前一 snapshot；不 append overlapping prefix、不 dedup 掩盖 append。
  continuation 的 loaded 必须严格增长，否则有限 typed fail；最新自洽 terminal snapshot 先于历史 progress 比较。
- 只有 `hasNextRow=false` 且 `loadedRecord == recordCnt == len(rows)` 的最终 rows 才进入 announcement parsing、
  stock matching、selection 与 HEAD；首轮 exactly 100 且官方证明 complete 时正常返回。

### 5.2 Cancellation owner 与 direct transport seam

实际 call path 为：

```text
raw Callable[[], bool] | None
  -> cn_download_workflow._is_cancel_requested / _raise_if_cancelled
     （唯一 bool、typed cancel、non-cancel failure 解释 owner）
  -> functools.partial（单次构造同一 no-arg Callable[[], None]）
  -> CnReportDiscoveryClientProtocol（只运输）
  -> HKEX 每个 cumulative GET 前 / 成功响应后 strict parse 前调用
  -> CNInfo 每个现有 pagination POST 前 / 成功响应后调用
```

- raw checker 不跨 protocol；provider 不读取 checkpoint 返回值、不解释 bool、不复制 workflow helper、不按消息字符串判错。
- workflow 原有 resolve/discovery 阶段检查保留；同一 checkpoint identity 贯穿一次 discovery。
- caller 主动抛出的同一 `CnDownloadCancelledError` 保持 object identity；raw checker 的非取消 failure 由 workflow
  包装并保留 direct/full cause chain。
- HKEX 的 `CnDownloadCancelledError` / `HkexnewsProviderProtocolError`、CNInfo 的 typed cancel 均在 generic
  `RuntimeError` context wrapper 前 bare re-raise，typed identity/type/cause 不被改写。

### 5.3 Publication、failure 与 obsolete contract

- before-first、after-response、before-next 与 final-response 后取消，以及 later-round HTTP/protocol failure，均不发送下一
  request，不把 partial rows 当 complete，不进入 candidate/HEAD/PDF/Docling publication。
- tests 直接断言 exact checkpoint/request sequence、query invariance、cancel identity、cause chain、zero HEAD、zero
  download/convert 与无 filing-start event；不是由 fake/fixture 下游重算 completeness。
- 旧 `_HkexnewsRowsPage.total_count`、generic total aliases/coercion、`_raise_if_title_search_truncated`、
  `HkexnewsDiscoveryTruncatedError`、固定上限命名和“100 即失败” contract 已删除且目标 scan 为零；没有 compatibility
  alias、wrapper 或 re-export。
- `R10-CR-O02/O03` 涉及的 stock-list helper 与 announcement raw aliases 有现存非-completeness consumer，按其原 owner
  保留，不成为第二 HKEX completeness parser。

## 6. 全部 7 个历史 candidates 的最终 disposition

| Candidate | 来源 | Controller final disposition | Completion evidence |
|---|---|---|---|
| `R10-PR-F01` | AgentDS plan review | accepted -> fixed -> closed | workflow 唯一解释 raw checker；no-arg checkpoint 只运输并在 I/O boundary 调用；typed identity/cause 与 zero-publication tests 闭合 |
| `R10-PR-F03` | AgentDS plan review | accepted -> fixed -> closed | HKEX 每个 cumulative GET、CNInfo 每个真实 POST 前后 exact ordering 已实现并经双路 plan/code re-review 确认 |
| `DS-R10-F02` | AgentDS plan review | rejected-with-reason / final | protocol 实际 branch coverage 100%；四个 changed production owners 均 `>=80%`，无 waiver |
| `R10-CR-O01` | AgentDS code review | rejected / no action | CNInfo 既有 50-page protection 不在 R10 root cause/diff；不建新 WU/issue、不纳入 R11、不改代码 |
| `R10-CR-O02` | AgentDS code review | rejected / intentional retention | stock-list JSON helpers仍有真实 stock mapping consumer |
| `R10-CR-O03` | AgentDS code review | rejected / pre-existing | announcement raw aliases不承担 title-search completeness，本轮未改义 |
| `R10-CR-O04` | AgentDS code review | rejected evidence-format observation / closed | 13/13 individual locks 与规范 aggregate manifests 已复现；没有 content drift |

Final ledger：accepted -> fixed -> closed `2`；rejected/no-action `5`；accepted/open `0`；deferred accepted finding `0`；
blocker `0`。两路 aggregate deepreview 均为 `PASS / 0 material finding / 0 blocker`，final artifacts 是：

- AgentMiMo：413 lines / SHA-256
  `584f8a09f49db899c0e3843610b967b4ee35b467edce4bdd96469f57afe85879`；
- AgentDS：716 lines / SHA-256
  `9bcbb84dfa57a24dff9938657661f2999c361a09f3e24df269bdfd8970c77f9f`；
- Controller adjudication：92 lines / SHA-256
  `7d5fd871ac14fdc0780c7a23ab3a60975b7bc340f1a96a591642eed184c0787a`。

Controller final verdict 为 `PASS / ZERO ACCEPTED OR OPEN FINDING`。不存在产品 fix，也不需要对不存在的 aggregate fix
伪造 re-review。

## 7. 最终实际验证证据

completion 采用 implementation 后由 AgentCodex 运行、Controller 独立复跑并被双路 code review/re-review/aggregate
确认 target 无 drift 的最终真值；final accepted commit 的 12 个 product blobs 与该 immutable target 逐一同 SHA，
因此验证没有被 audit refresh 或 post-review 产品改动失效。

| Validation | Final truth |
|---|---|
| focused five-file owner/seam/workflow suite | `172 passed`；3 个既有 external deprecation warnings |
| selected checkpoint/HKEX/CNInfo suite | `135 passed, 21 deselected` |
| full Fins | `933 passed, 1 existing opt-in skip`；3 个既有 warnings |
| HKEX downloader branch coverage | `80.89%` |
| CNInfo downloader branch coverage | `89.28%` |
| discovery protocol branch coverage | `100.00%` |
| CN/HK workflow branch coverage | `81.05%` |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（4 production + 5 test files） | `All checks passed!` |
| diff/source/owner/deferred scans | pass；obsolete/generic/bool-interpretation/deferred added-hunk 命中均为零或已按 owner 分类 |
| staged tree at implementation/review gates | empty |

唯一 skip 是未设置 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 时按既有 contract 跳过真实 Docling upload integration；
与 R10 无关，不是 waiver。workflow coverage 曾为 `79.74%`，已通过真实“discovery 完成后、首 candidate 前取消”owner
测试提高到 `81.05%`；没有 omit、pragma、padding、aggregate threshold 或 N/A waiver。

外部协议证据同样闭合：

- captured fixture 为 34 lines / SHA-256
  `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3`，raw body SHA-256
  `5745632a449bf3075e6ba27892b7cbe1eed98fd885c487fe3c98e1d5328a51f5`；字段实际类型与 strict parser 一致。
- 只读 official smoke 的 gitignored manifest 为 107 lines / SHA-256
  `db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe`：首轮请求 100 得到
  `loadedRecord=100 / recordCnt=1669 / hasNextRow=true`；第二轮按公式请求 1669，得到
  `loadedRecord=recordCnt=len(rows)=1669 / hasNextRow=false`；两轮 non-range params exact equal。
- fixture/smoke 只访问公开 HTTPS GET，不下载 PDF、不调用 mutation endpoint、不写业务 workspace；smoke 未进入 commit。

## 8. README、security retention 与 no-sneak scope audit

### 8.1 README decision

- `dayu/fins/README.md` 的开发者职责覆盖 downloader 当前稳定 owner contract；commit 只新增已实现的 official
  cumulative、exact fields、final snapshot replacement 与 typed fail-closed 说明，没有测试清单、WU 流水账或未来能力。
- `tests/README.md` 按当前测试事实把旧“满 100 即 truncated”说明替换为 official fields、cumulative、latest-count、
  contradiction/no-progress、checkpoint 与 partial zero-publication 覆盖。
- 根 `README.md`、`dayu/README.md`、config/host/engine/tool/UI/Fins design truth均无需且没有修改；用户 CLI、安装、
  工作区位置、分层装配和稳定设计 contract 未变化。

### 8.2 Security retention 与统一 authorization 边界

以下局部安全/稳态机制在 commit blob 中仍存在并由原 owner 执行：HTTP timeout、有限 retry、throttle、HTTPS endpoint、
PDF magic/size 校验、stock matching、error 不包含 raw response/cookie/header/authorization/local path、fixture/smoke secret
hygiene。R10 没有删除、放宽或替换这些机制。

Topic 9 的统一 tool authorization framework 仍未设计、未实现；future semantic owner 仍是 Host ToolRuntime 或等价
Host-owned governance boundary，实际 filesystem/network/process/storage boundary 继续执行 defense-in-depth。本 R10 没有
新增 permission schema、auth profile、policy DSL、capability token、DNS/egress 或 browser framework。

### 8.3 Deferred/no-touch destination

| Item | R10 状态 | Owner / destination |
|---|---|---|
| Issue 142 | no-touch | 既有 workspace migration issue owner |
| Issue 151 | no-touch | 既有 future write/product assets issue owner |
| Issue 175 | no-touch | 既有 Fins Docling process-isolation issue owner |
| Issue 177 | no-touch | 既有 Doc `TruncationManager` output-continuation issue owner |
| Issue 178 | no-touch | 既有 Web credential/storage-state lifecycle issue owner |
| Web/WeChat/render | no-touch | 既有各自 trackers；R10 不发布、删除或重写 placeholder surface |
| R11 | unauthorized/no leakage | umbrella 后续独立 upload-script + placeholder-surface-removal plan gate；不是 CNInfo O01 destination |
| R12 | unauthorized/no leakage | umbrella 后续独立 CLI init plan gate |
| Topic 8 | accepted-as-is/no code | Engine 240-character redacted/truncated exception projection未修改 |
| Topic 9 | design clarification/no code | unified Host authorization仍 deferred；现有局部防御保留 |

12-path product diff 的 added-hunk 审计对 Issue 142/151/175/177/178、R11/R12、Topic 8/9、Web/WeChat/render、
storage transaction、direct-stream terminal、hard cap、date recursion、watchdog、compatibility 与统一 authorization 均无
实现命中。Fixture 中 `no ... authorization ... retained` 只是 secret-retention 元数据，不是 authorization framework。

## 9. Residual reconciliation

| Item | Final classification | Owner / destination |
|---|---|---|
| 官方未来 HKEX schema/行为变化 | 当前 strict typed fail-closed contract 正确拒绝；不是 R10 open finding | HKEX provider owner；只有未来直接 provider evidence 才交明确 owner/user decision，当前不建 fallback/WU |
| 外部 endpoint DNS/网络/challenge/限流 | environment/operations risk；不改变 deterministic local contract | 外部运行环境；准确记录，不放宽 owner contract |
| CNInfo `page_num > 50` protection | `R10-CR-O01` rejected/no-action；pre-existing/non-R10 | 既有 CNInfo owner仅作事实定位；不建新 WU/issue、不纳入 R11 |
| stock-list JSON helpers | intentional retention | 既有 stock mapping consumer |
| announcement raw aliases | pre-existing non-completeness parsing | 既有 announcement parsing/selection owner |

R10 actual accepted residual finding = `0`。没有 residual 缺 owner/destination；也没有把 rejected CNInfo O01、未来
provider 猜测或 deferred issue 伪装成 R10 follow-up。

## 10. Completion state、workspace ownership 与 handoff

- R10 completion evidence verdict：`COMPLETE / ZERO ACCEPTED OR OPEN FINDING / ZERO R10 ACTUAL ACCEPTED RESIDUAL`。
- umbrella status：`WU-SEMANTIC-OWNERSHIP-01 ACTIVE`。
- R11/R12 status：`NOT AUTHORIZED`。
- 本 gate 唯一 authored path：
  `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-completion-codex.md`。
- Controller-owned `docs/host/issues-implementation-control.md` 的 current working-tree 修改保持原样；本 gate没有修改、
  stage、覆盖或吸收它。
- staged tree 必须并保持 empty；本 gate 不执行 stage、commit、push、PR 或任何 R11/R12 动作。
- stop state：`READY_FOR_CONTROLLER_COMPLETION_VALIDATION`。任何 completion commit 必须由 Controller 独立验证后另行
  exact-scope 授权，不能由本 artifact 自动产生。

为避免递归自引用，本 artifact 不在正文嵌入自身最终行数或 SHA-256。写入完成后由外部只读命令计算，并在 handoff
中报告 path、lines、SHA-256、verdict 与 staged/working status。
