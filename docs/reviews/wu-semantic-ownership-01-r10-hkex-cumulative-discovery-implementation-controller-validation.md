# WU-SEMANTIC-OWNERSHIP-01 / R10 implementation Controller validation

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- accepted-plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- AgentCodex implementation evidence：
  `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md`，226 lines，
  SHA-256 `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。
- implementation validation finding：AgentCodex 曾发现 workflow branch coverage `79.74%`；通过真实 owner 行为测试修复
  到 `81.05%`，未使用 waiver、omit、pragma 或 padding。
- current accepted/open code-review finding：0（尚未进入 code review）。
- blocker：0。
- staged tree：empty。

本验证只授权同一 immutable R10 target 的 AgentMiMo / AgentDS 并发完整 code deepreview；不授权 commit、aggregate、
completion、R11 或 R12。

## 2. Scope 与 immutable locks

### 2.1 Controller-owned inputs

| Source | SHA-256 |
|---|---|
| accepted fixed plan | `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` |
| implementation authorization | `f3ae9f58fce2a7403496ea33dde84aa1b9a0c3bed23f37e0c8dd078aa0bc0d38` |
| pre-review control state | `3bf08ec11942df0af4dfd82f34c3dbe98b64e92e7cecdb507746da640dc5bf9a` |
| AgentCodex evidence | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` |

Controller 重算确认 accepted plan、authorization、AGENTS、controller discussion、umbrella control 与 Fins design locks
无漂移。implementation 未覆盖 Controller-owned control/authorization；当前 control transition 与本 validation 是
Controller 后续有意变更。

### 2.2 Exact implementation target

Implementation exact 13 paths：四个 production owner、五个测试文件、一个 captured fixture、两个 README 和一个
AgentCodex evidence。sorted path-manifest SHA-256 为
`52a0c5380e3527f260cfb10e3996746967e0173f406187e6f22484fd5004391f`；按路径排序的
`SHA-256  path` content-lock manifest SHA-256 为
`91fdf09a26dde192d7973419823330cd702a55686a84941cf9881fe890d41476`。

| Path | Final SHA-256 |
|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` |
| `dayu/fins/downloaders/cninfo_downloader.py` | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` |
| `dayu/fins/pipelines/cn_download_protocols.py` | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` |
| `dayu/fins/pipelines/cn_download_workflow.py` | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` |
| `tests/fins/test_hkexnews_downloader.py` | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` |
| `tests/fins/test_cninfo_downloader.py` | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` |
| `tests/fins/test_cn_download_workflow.py` | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` |
| `tests/fins/test_cn_pipeline.py` | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` |
| `tests/fins/test_cn_download_runtime.py` | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` |
| `dayu/fins/README.md` | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| `tests/README.md` | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |
| AgentCodex evidence | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` |

没有其它 production/test/README/design diff。Controller-owned control、authorization 和本 validation 不属于被审产品
target；reviewer 必须保护它们且不得改写。smoke evidence 位于 gitignored `workspace/tmp`，不得 stage。

## 3. Semantic-owner validation

### 3.1 HKEX official cumulative owner

Controller 逐段复核 production diff：

- `HkexnewsDiscoveryClient` 私有 frozen snapshot 唯一持有 official `hasNextRow`、`rowRange`、`loadedRecord`、
  `recordCnt` 与 typed rows；shared protocol/workflow/CNInfo 不读取这些字段。
- strict parser 要求 top-level object、五个必填字段、exact bool/int/stringified object-list，显式拒绝 bool-as-int、
  negative、missing、coercion、generic aliases 与轮内矛盾。
- state 从 100 开始，continuation 精确使用 `max(current * 2, latest recordCnt)`；每轮只派生 `rowRange`，其余 query
  不变。
- continuation 要求 strict loaded progress；terminal-first 允许自洽 terminal count shrink；没有 hard cap、date
  recursion、append、dedup、prefix guess 或第二套 completeness mechanism。
- 每轮替换 snapshot，只有 final complete rows 才进入 announcement parsing、selection 与 HEAD。
- typed cancel/provider protocol error 在 generic RuntimeError wrapper 前 bare re-raise，保持 identity/type/cause。

旧 `_HkexnewsRowsPage`、generic totals/coercion、100 即 truncated failure、旧 exception 与 cap 命名均已删除；目标 source
scan 为 0。

### 3.2 Cancellation ownership

- raw `Callable[[], bool]` 仍只由 workflow 既有 `_raise_if_cancelled` 解释。
- workflow 只构造一次 `functools.partial` no-arg checkpoint；protocol 仅运输
  `Callable[[], None] | None`；provider 只调用，不读取返回值、不解释 bool、不复制 helper。
- HKEX 每个 cumulative GET 前、成功响应后 strict parse 前调用同一 checkpoint。
- CNInfo 在现有 `_query_announcements` transport 内对每个实际 supported-period POST 前/成功响应后调用；若既有
  pagination 产生多个 POST，则每个真实 I/O 都有相同边界检查。这没有改变 query、period iteration、pagination、
  retry、selection 或错误语义，也没有引入第二 pagination design。
- typed cancel、caller cancel identity、non-cancel direct/full cause chain、next-request suppression 与 partial
  rows/candidates/HEAD/PDF zero-publication 均有 owner tests。

## 4. Controller independent validation

所有 Python 命令均先 `source .venv/bin/activate`。

| Gate | Controller result |
|---|---|
| focused five-file suite | `172 passed`, 3 external deprecation warnings |
| full `tests/fins` | `933 passed, 1 skipped`, 3 external warnings；skip 是既有 opt-in Docling integration |
| HKEX branch coverage | `80.89%` |
| CNInfo branch coverage | `89.28%` |
| protocol branch coverage | `100.00%` |
| workflow branch coverage | `81.05%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff | `All checks passed!` |
| `git diff --check` | PASS |
| staged tree | empty |

四个 production owner 均逐文件 `>=80.00%`，没有 aggregate 替代或 waiver。Controller 同时确认：

- official fixture 34 lines，file SHA 与 raw body SHA/provenance 一致，不含 cookie、authorization、proxy credential、
  headers 或本地 path；
- live smoke manifest 107 lines，SHA-256
  `db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe`；`jq -e` verifier 返回 true；
- public GET 首轮 `100/100/1669/true`，第二轮请求 1669 并得到 `1669/1669/false`；non-range params exact equal；
- 两轮 raw body hashes 分别为 `cfec10de...d1ed18` 与 `548254d4...e8fdd`，evidence root 被 `.gitignore` 覆盖；
- README 更新只说明当前 Fins owner contract 与测试覆盖；未修改根 README、分层 README 或 design truth；
- 保留 HTTP timeout/retry/throttle、HTTPS、PDF magic/size、stock match、HEAD/PDF policy 与 error/secret hygiene。

## 5. Scope / deferred / security verdict

- 没有实现 Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9 或统一 tool authorization。
- 没有 compatibility、generic pagination/cancellation framework、speculative watchdog、hard cap 或 date recursion。
- 原有网络与 PDF 防御机制保留；fixture/smoke 只执行公开只读 GET，不下载 PDF、不调用 mutation endpoint、不写业务
  workspace。
- current implementation validation residual：0；未来 provider 官方协议变化由当前 strict typed fail-closed owner 拒绝，
  不是当前未分类 finding。

## 6. Next gate

AgentMiMo 与 AgentDS 必须并发对本 artifact 锁定的完整 13-path implementation target 执行 `/deepreview`。两路都必须
覆盖 correctness、stability、maintainability、adversarial failure、semantic ownership drift、过度耦合、测试真实性、
security retention 与 deferred-scope leakage。任何 accepted finding 必须交 AgentCodex 全部修复并完成双路完整
re-review；一次 review PASS 不授权 commit 或 R10 completion。
