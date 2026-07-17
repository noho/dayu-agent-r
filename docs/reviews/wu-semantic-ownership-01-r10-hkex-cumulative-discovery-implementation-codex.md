# WU-SEMANTIC-OWNERSHIP-01 / R10-S1 implementation evidence (AgentCodex)

## 1. Gate、结论与状态

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- slice：单一 `R10-S1` implementation。
- baseline accepted-plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- branch：`phaseflow/host-issues-control`。
- implementation 结论：PASS。HKEX official cumulative completeness、strict provider protocol、final-only snapshot replacement、显式 cancellation checkpoint seam 与 typed failure precedence 已在唯一 owner 边界实现；local matrix 与 live official `recordCnt>100` smoke 均通过。
- finding：implementation validation 曾发现 workflow branch coverage 精确值为 `79.74%`，已通过真实“discovery 完成后、首 candidate 前取消”owner 行为测试修复；最终为 `81.05%`。未使用 waiver、omit、pragma 或 padding。
- blocking finding：0。
- residual：0 个未分类 residual。官方未来 schema/行为变化由当前 strict typed fail-closed contract 拒绝，不构成本 slice 未实现 fallback。
- stop state：`READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

## 2. Preflight、authority 与 source locks

### 2.1 Git / accepted-plan identity

- preflight HEAD：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- accepted commit parent：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`。
- accepted commit tree：`44a8adf138887581eef4a0ceacc0cc216b7921fa`。
- accepted commit exact 12 paths；sorted path-manifest SHA-256：`4d43456edcca387294145fbc3ef6f84915ec900081237f87323038baeca85b3a`。
- preflight dirty 仅有 Controller-owned `docs/host/issues-implementation-control.md` 与未跟踪 authorization；staged tree 为空。
- `docs/host/issues-implementation-control.md` 未被本 implementation 读写或纳入 allowlist；final observed SHA-256 为 `3bf08ec11942df0af4dfd82f34c3dbe98b64e92e7cecdb507746da640dc5bf9a`。
- authorization 始终保持 120 lines / `f3ae9f58fce2a7403496ea33dde84aa1b9a0c3bed23f37e0c8dd078aa0bc0d38`，未修改。

### 2.2 Authority / historical current-file locks

以下 current-file locks 全部重算并与 accepted plan / authorization 一致：

| Source | Lines | SHA-256 |
|---|---:|---|
| `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| `docs/fins/design.md` | 123 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
| `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-entry-controller-validation.md` | 96 | `885f40461b3b1fd4030437f35ee54eb8ab4227f5e5e1849ce0353d61299136ef` |
| `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-mimo.md` | 166 | `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16` |
| `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-ds.md` | 338 | `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce` |
| `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-review-controller-adjudication.md` | 106 | `3659ef62964b195cda60d4c4d5e961214594076e75fc0a52adcda4f076493f4f` |
| accepted fixed plan | 698 | `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` |
| implementation authorization | 120 | `f3ae9f58fce2a7403496ea33dde84aa1b9a0c3bed23f37e0c8dd078aa0bc0d38` |

fixed plan §2.2 记载的 605-line pre-fix plan 已被 fixed plan 同路径替换，且该节明确不要求伪造旧 SHA；当前 accepted fixed plan 作为 implementation authority 已按上表锁定。

### 2.3 Immutable implementation-input locks

进入修改前全部重算，无 drift：

| Source | Lines | SHA-256 |
|---|---:|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1065 | `8c7c1a3b8e1aebc91ec82756754eb7894d6748471b69ce164a9798b260f5eb31` |
| `tests/fins/test_hkexnews_downloader.py` | 1213 | `d98266b8016e47a5ba4f77d680196b373933f71b184e559b2b483bd76f9de1d9` |
| `tests/fins/test_cn_download_workflow.py` | 1660 | `c2d86d4778002d904df40ab0c5ac67660683e76ea989a692d917650aa09b1e1f` |
| `dayu/fins/pipelines/cn_download_protocols.py` | 227 | `a92f283c0284aa1fce77031d73faf3cf9b37f6438b52b91b1cd317c26a6c003e` |
| `dayu/fins/pipelines/cn_download_workflow.py` | 806 | `3c27e009897c4c6030520f891f38648876cf3dd6a26c14d27f7ae50473f3c24f` |
| `dayu/fins/downloaders/cninfo_downloader.py` | 835 | `baab2ae471fc3f8201fc8bf97447c3fa647abd7dc25788d496d135a82f829d07` |
| `tests/fins/test_cninfo_downloader.py` | 1397 | `92e518f52401b0106c7726a7984b0d90c18cb58aba41aee7470c23864ce15399` |
| `tests/fins/test_cn_pipeline.py` | 718 | `7f00b257ecc7d128218aeca2505ea8cb6e3f89f624d58c3a8c734e8edf5189ee` |
| `tests/fins/test_cn_download_runtime.py` | 704 | `b37a4a86c607f57982536097a16b58a4297b1fcb4d99e406db49e4ec7dc95ba9` |
| `dayu/fins/README.md` | 791 | `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |

## 3. Exact changed paths 与 final content locks

除本 evidence 自身外，implementation exact 12 paths 如下；没有其它 production/test/README/design/control/review diff：

| Kind | Path | Lines | Final SHA-256 |
|---|---|---:|---|
| production | `dayu/fins/downloaders/hkexnews_downloader.py` | 1266 | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` |
| production | `dayu/fins/pipelines/cn_download_protocols.py` | 231 | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` |
| production | `dayu/fins/pipelines/cn_download_workflow.py` | 820 | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` |
| production | `dayu/fins/downloaders/cninfo_downloader.py` | 849 | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` |
| test | `tests/fins/test_hkexnews_downloader.py` | 1706 | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` |
| test | `tests/fins/test_cn_download_workflow.py` | 1793 | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` |
| test | `tests/fins/test_cninfo_downloader.py` | 1619 | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` |
| test | `tests/fins/test_cn_pipeline.py` | 759 | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` |
| test | `tests/fins/test_cn_download_runtime.py` | 711 | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` |
| fixture | `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | 34 | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` |
| README | `dayu/fins/README.md` | 793 | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| README | `tests/README.md` | 293 | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |

本 evidence 是授权的唯一 implementation artifact；其自锁必须在文件写完后外部计算，避免自引用 hash。final handoff 报告其 lines/SHA。

## 4. Semantic owner、call path 与 implementation facts

### 4.1 Cancellation seam

实际 call path：

```text
raw Callable[[], bool] | None
  -> cn_download_workflow._raise_if_cancelled（唯一 bool/typed cancel/non-cancel failure 解释 owner）
  -> functools.partial（单次构造同一 no-arg Callable[[], None]）
  -> CnReportDiscoveryClientProtocol（只运输）
  -> HKEX 每个 cumulative GET 前 / 成功响应后调用
  -> CNInfo 每个 supported fiscal-period 的每个 POST 前 / 成功响应后调用
```

- workflow 原有 resolve/discovery 方法前后 `_raise_if_cancelled` 检查全部保留。
- raw checker 为空时传 `None`；非空时每次 discovery 只构造并传一个 partial 对象。
- provider 不读 checkpoint 返回值、不解释 bool、不复制 helper、不做异常字符串判断。
- exact normal traces：HKEX `CP1, GET(100), CP2`；两轮 `CP1, GET(100), CP2, CP3, GET(200), CP4`；CNInfo 两财期 `CP1, POST(FY), CP2, CP3, POST(H1), CP4`。
- bool true 在 workflow-owned checkpoint 内映射为 `CnDownloadCancelledError`；caller 主动抛出的同一 cancel object 跨 workflow/protocol/provider 保持 identity。
- raw checker 非取消 failure 由 workflow RuntimeError 以 direct cause 持有；通过 HKEX/CNInfo provider context wrapper 时保留完整两层 cause chain。
- before-first、after-response、before-next、after-final / before-first-candidate 取消均抑制下一 request、partial candidate、HEAD、PDF/Docling publication。

### 4.2 HKEX provider owner

- 新增 provider-private frozen `_HkexnewsTitleSearchSnapshot`：requested/response range、`has_next_row`、`loaded_record`、`record_count`、typed row tuple。
- strict parser 要求 top-level object 与五个必填官方字段：`hasNextRow` exact bool；`rowRange/loadedRecord/recordCnt` exact non-negative int 且拒绝 bool-as-int；`result` 必须是非空字符串化 JSON array 且每行是 object。
- 同轮 invariants：response range 等于 request；`loadedRecord == len(rows)`；loaded 不超过 count/range；continuation 必须 loaded < count；terminal 必须 `loadedRecord == recordCnt == len(rows)`。
- state 从 100 开始；next range 精确为 `max(current_range * 2, latest recordCnt)`；不冻结首次总数。
- continuation 间 loaded rows 必须严格增加；latest terminal complete 在 progress 比较前返回，因此自洽 count shrink 被接受。
- 每个 language/category 构造一次只读 base params，每轮仅派生 `rowRange`；测试删除 range 后 exact dict equality。
- 每轮 snapshot replacement；只有 final complete rows 进入 announcement parsing / stock matching / selection / HEAD。没有 append、prefix guess 或 dedup 补偿。
- exception order：`CnDownloadCancelledError`、`HkexnewsProviderProtocolError` 在 generic RuntimeError context wrapper 前 bare re-raise；identity/type/direct cause 均有测试。

### 4.3 Deleted obsolete semantics

已删除且全仓目标 scan 为零：

- `_HkexnewsRowsPage.total_count`
- `_extract_title_search_total_count`
- `_coerce_non_negative_int`
- `_raise_if_title_search_truncated`
- `HkexnewsDiscoveryTruncatedError`
- `_HKEXNEWS_ROW_LIMIT` / `_HKEXNEWS_ROW_RANGE`
- generic `total/totalCount/total_count/recordCount/recordsTotal/count` completeness aliases、float/string coercion 与“100 即失败”测试

当前 private `record_count` 仅是官方 `recordCnt` 的 typed snapshot 字段，是 accepted plan 明定的 owner projection，不是 generic alias 或第二总数真源。

## 5. Owner-level tests 与 zero-publication evidence

新增/迁移测试覆盖：

- exact 100 complete；two-round cumulative；`recordCnt > doubled range`；multi-round count growth；latest terminal shrink；per-language isolation。
- query invariance；overlap replacement；final-only candidate/HEAD；no-progress finite typed failure。
- 五字段逐一缺失；bool/int/negative/result exact type；response range、loaded/rows/count/range、terminal/continuation contradictions。
- official captured fixture replay与 raw body hash。
- checkpoint normal return、bool true mapping、caller cancel identity、provider error identity/cause、non-cancel direct/full cause chain。
- HKEX before-first/after-response/before-next 取消、later HTTP failure；CNInfo 每页 POST exact trace、response cancel、before-next cancel。
- pipeline 两个 discovery fakes 与 runtime injected fake 的显式 keyword-only checkpoint transport；raw checker 未跨 protocol。
- 任一取消/失败路径均断言下一 request suppression，并通过 zero HEAD / zero download / zero conversion / no filing event 证明 partial rows/candidates 不发布。

## 6. Validation evidence

所有命令均先 `source .venv/bin/activate`。

| Gate | Command / scope | Result |
|---|---|---|
| focused five files | plan §10.1 第一个 pytest 命令 | `172 passed`, 3 external deprecation warnings |
| selected checkpoint/HKEX/CNInfo | plan §10.1 第二个 pytest 命令 | `135 passed, 21 deselected` |
| full Fins | `pytest -q tests/fins` | `933 passed, 1 skipped`, 3 warnings, `38.72s` |
| coverage run | exact five focused files, `coverage run --branch` | `172 passed` |
| HKEX coverage | exact production file | `80.89%` branch coverage |
| CNInfo coverage | exact production file | `89.28%` branch coverage |
| protocol coverage | exact production file | `100.00%` branch coverage |
| workflow coverage | exact production file | `81.05%` branch coverage |
| full pyright | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff | exact 4 production + 5 test files | `All checks passed!` |
| diff whitespace | `git diff --check` | PASS |

Coverage 全部逐文件 `>=80.00%`，没有 aggregate 替代、waiver、omit、pragma 或 test-only dead-code padding。

full Fins 唯一 skip 是既有 opt-in `tests/fins/test_docling_upload_service_integration.py`：未设置 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 时按测试 contract 跳过真实 Docling upload；与 R10 无关。3 个 warnings 均来自 edgartools 依赖的 deprecated import。

## 7. Diff / source / owner / deferred scans

- obsolete symbol scan：0 matches。
- disallowed generic raw aliases：0；命中的 `record_count` 仅为 official `recordCnt` 的 accepted private typed field/test input。
- official field scan：只落在 HKEX owner、HKEX owner tests 与 captured fixture；shared protocol/workflow/CNInfo 不读取 HKEX completeness fields。
- cancellation scan：raw `Callable[[], bool]` 只在 workflow；protocol/HKEX/CNInfo 只接收 `Callable[[], None] | None`。
- `if cancellation_checkpoint()` / bool interpretation：0 matches。
- cancellation helper scan：只有 workflow 既有 `_is_cancel_requested` / `_raise_if_cancelled`。
- cumulative method scoped scan：无 rows `extend` / `+=` / dedup；`primary.extend` 只在各 language/category 已 complete 后汇总已验证公告，不参与 cumulative snapshot。
- word-level added-hunk forbidden scan：Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9、authorization/auth profile、hard cap、date recursion、watchdog、compatibility 均为 0 added matches。
- diff path scan：implementation 仅为 §3 的 12 paths + 本 evidence；Controller dirty files保持其原所有权。
- staged scan：empty。

## 8. Official fixture 与 live smoke

### 8.1 Captured official small-shape fixture

- fixture：`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`。
- captured at：`2026-07-17T10:54:36Z`。
- endpoint：public HTTPS `titleSearchServlet.do` GET。
- query：Tencent `stockId=7609`，annual-report category，`20260715..20260715`，`rowRange=100`。
- HTTP：200。
- official raw facts：`result="[]"`, `hasNextRow=false`, `rowRange=100`, `loadedRecord=0`, `recordCnt=0`。
- raw body SHA-256：`5745632a449bf3075e6ba27892b7cbe1eed98fd885c487fe3c98e1d5328a51f5`。
- fixture file SHA-256：`d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3`。
- capture tool：curl 8.7.1；未保存 cookie、authorization、proxy credential、request/response header 或本地路径。

### 8.2 Non-destructive official `recordCnt>100` smoke

- evidence root（gitignored）：`workspace/tmp/wu-semantic-ownership-01-r10-hkex-smoke/`。
- manifest：107 lines，SHA-256 `db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe`。
- query：public GET，`stockId=7609`，all title categories (`t1code/t2Gcode/t2code=-2`)，`20000101..20260717`；无 PDF 或 mutation 请求。
- round 1：request 100；HTTP 200；`rowRange=100`, `loadedRecord=100`, `recordCnt=1669`, `hasNextRow=true`, `len(rows)=100`；raw SHA `cfec10de8f3d20d8a6b7eefc73937cf00a71c61124061f49ec16704222d1ed18`。
- formula：`max(100 * 2, 1669) = 1669`。
- round 2：request 1669；HTTP 200；`rowRange=1669`, `loadedRecord=1669`, `recordCnt=1669`, `hasNextRow=false`, `len(rows)=1669`；raw SHA `548254d47e805d841a39b60fb51af879d453b36c9bb5c9987156f251969e8fdd`。
- `jq -e` manifest verifier：true；证明两轮非-range params exact equal、range 公式、response/request equality、每轮 loaded/rows equality 与 final completeness。
- endpoint 可达且未观察到 cap、clamp、stall 或 official type contradiction；无需触发 stop condition，也未加入 fallback/date recursion/second mechanism。

## 9. README 与 security retention

- 已先读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】` 与 `tests/README.md` 当前维护边界。
- `dayu/fins/README.md`：仅补充当前已实现的 HKEX official cumulative、strict completeness、snapshot replacement/final-only owner contract；未写 WU 流水账或未来计划。
- `tests/README.md`：删除旧 typed truncated 断言说明，改为 official fields、cumulative、latest count、replacement、contradiction/no-progress 与 checkpoint/zero-publication 当前覆盖。
- 根 README / `dayu/README.md` / design docs：不更新；用户入口、CLI、分层与稳定设计真源未变。
- 保留原 HTTP timeout/retry/throttle、HTTPS HKEX endpoint、PDF magic/size、stock match、HEAD/PDF policy与 error secret hygiene。
- fixture/smoke 只做公开 GET；不保存 cookie/auth/header/proxy credential，不下载 PDF、不写业务 workspace、不调用 mutation endpoint。

## 10. Deferred / no-touch / handoff

- 未实现 hard cap、date recursion、page append/dedup、generic pagination/cancellation framework、speculative watchdog 或 compatibility。
- 未触碰 Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9、authorization、storage transaction 或 direct-stream terminal。
- 未修改 design、control、authorization 或 prior artifacts。
- 未 stage、commit、push、创建 PR、执行 code review、aggregate 或 completion。
- Controller-owned dirty control/auth 保留；smoke evidence 仅在 gitignored `workspace/tmp`。
- staged tree：empty。
- next authorized gate：双路完整 code review。
- final state：`READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。
