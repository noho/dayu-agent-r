# WU-SEMANTIC-OWNERSHIP-01 / R10 implementation Controller authorization

## 1. Authorization

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- accepted plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`
  (`docs: accept R10 HKEX cumulative discovery plan`)。
- parent：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`。
- tree：`44a8adf138887581eef4a0ceacc0cc216b7921fa`。
- accepted plan：698 lines；SHA-256
  `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a`。
- accepted-plan commit scope：exact 12 paths；sorted path-manifest SHA-256
  `4d43456edcca387294145fbc3ef6f84915ec900081237f87323038baeca85b3a`。
- branch：`phaseflow/host-issues-control`；authorization 前 working/staged tree clean。
- verdict：`AUTHORIZED_FOR_AGENTCODEX_SINGLE_SLICE_IMPLEMENTATION`。

本 authorization 只允许 R10-S1 implementation、测试/README/fixture 与 implementation evidence；不授权 code
review、commit、aggregate、completion、R11 或 R12。

## 2. Immutable implementation input locks

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

Agent 开始前必须重算。任一 lock drift 或未知工作树变更立即 stop；不得覆盖 Controller-owned control/authorization。

## 3. Exact implementation allowlist

**Production**

- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/downloaders/cninfo_downloader.py`

**Tests / fixture**

- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（new）

**README**

- `dayu/fins/README.md`
- `tests/README.md`

**Evidence**

- new `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md`

任何其它 production/test/README/design/control/review path 出现 diff 立即 stop。Smoke evidence 只可落在 gitignored
`workspace/tmp/wu-semantic-ownership-01-r10-hkex-smoke/`，不得 stage。

## 4. Required implementation semantics

### HKEX owner

- private frozen typed snapshot + strict exact official parser；五字段必填，exact bool/int/stringified-list，显式拒绝
  bool-as-int、coercion、negative、aliases、fallback 和矛盾；
- initial range 100；continuation `max(current_range * 2, latest recordCnt)`；除 rowRange 外 query byte-for-byte 等价；
- response range equality、loaded/count/range invariants、strict continuation loaded/rows progress、terminal-first；
- per-round cumulative snapshot replacement，final complete 后才 parse/filter/selection/HEAD；不 append/dedup/prefix guess；
- 删除 generic total/truncated/cap semantics 与旧 exception；不留兼容 alias/wrapper；
- typed `HkexnewsProviderProtocolError` 与 `CnDownloadCancelledError` 必须在 generic RuntimeError wrapper 前原样通过。

### Cancellation seam

- workflow 用 `functools.partial` over existing `_raise_if_cancelled` 构造一次 workflow-owned no-arg checkpoint；raw bool
  checker 不跨 protocol；
- protocol 只运输 `Callable[[], None] | None`；provider只调用、不能读返回值/解释 bool/复制 helper/字符串判错；
- HKEX 每个 cumulative GET 前、成功响应后 strict-parse 前调用；CNInfo 每个 supported fiscal-period POST 前、成功响应
  后调用；workflow 原有方法前后检查保留；
- exact ordered tests证明 bool mapping、caller cancel object identity、non-cancel direct/full cause chain、normal return、
  wrappers、每个取消时点、下一 request suppression 与 partial rows/candidates/HEAD zero-publication。

### No-touch

不实现 hard cap、date recursion、page append/dedup、generic pagination/cancellation framework、speculative watchdog、
compatibility、Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9 或 authorization。保留现有 HTTP
timeout/retry/throttle、HTTPS、PDF magic/size、stock match、error/fixture secret hygiene。

## 5. Validation requirements

严格执行 accepted plan §8-§11：

1. focused five-file test suite + checkpoint/HKEX/CNInfo selected suite；
2. full `tests/fins`；
3. four changed production files each branch coverage `>=80.00%`，zero waiver/omit/pragma/padding；
4. full `python -m pyright dayu/ tests/ utils/` zero errors；
5. scoped Ruff、`git diff --check`、obsolete/generic/official field/cancellation/owner/deferred scans；
6. README update constraints first read，再更新 Fins/tests README only；
7. captured official small-shape fixture with provenance/hash/no secrets；
8. non-destructive live official `recordCnt>100` smoke and evidence manifest；external DNS/challenge/limit unavailable may be
   accurately recorded but does not waive local protocol gates。If endpoint is reachable but proves cap/clamp/stall or official types contradict
   plan，stop with evidence，do not add fallback/date recursion/second mechanism。

Implementation artifact must report exact changed-path manifest/content locks、test/coverage/type/lint/scans、fixture/live smoke、
README/security/deferred decisions、finding/residual status、staged empty and stop state `READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

## 6. Gate state

- current gate：AgentCodex R10-S1 implementation。
- plan findings：accepted/open 0。
- implementation / review findings：none yet。
- commit / aggregate / completion / R11 / R12：未授权。
