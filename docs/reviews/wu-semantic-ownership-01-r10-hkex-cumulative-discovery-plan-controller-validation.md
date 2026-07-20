# WU-SEMANTIC-OWNERSHIP-01 / R10 independent plan Controller validation

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- validated artifact：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`。
- artifact lock：605 lines；SHA-256
  `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699`。
- baseline：branch `phaseflow/host-issues-control`；HEAD
  `1c2585275f4134d8456a3fda2d84464e4e52c9d7`；staged tree empty。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。

本 verdict 只接受该 plan 进入 AgentMiMo / AgentDS 双路完整 plan review；不接受 plan、不授权
implementation、stage/commit、R11 或 R12。

## 2. 第一性原理与 owner 核对

动机成立且风险评级正确。直接代码证据表明当前 `HkexnewsDiscoveryClient` 每个 language/category 只发
一次固定 `rowRange="100"` 请求，随后用八个 generic total aliases 猜完整性，并把满 100 且缺 generic
total 当作 truncated。该实现既不能消费官方累计续取协议，也不能证明超过 100 条时的完整性，与
`docs/fins/design.md` 的 `hasNextRow / loadedRecord / recordCnt` 裁决直接冲突。

Plan 把官方响应解析、累计状态、进展、完整性与 typed provider failure 唯一放在
`dayu/fins/downloaders/hkexnews_downloader.py`，下游 workflow/selection/storage 不重算；owner 正确。
共享 CN/HK protocol/workflow 只显式运输既有 operation cancellation signal，不读取 HKEX 字段或拥有分页
语义。

## 3. Direct cancel seam 裁决

Controller 接受 plan §4.2 的最小显式 `cancel_checker` seam，理由是：

1. 当前 workflow 只在整个 `list_report_candidates(...)` 前后检查取消；进入 downloader 的同步多轮请求后，
   HKEX owner 无法在每轮 I/O 前后观察真实 operation signal。
2. 直接 keyword-only 参数符合项目对朴素接口和显式依赖的要求；不需要 `ContextVar`、mutable setter、factory、
   market branch 或测试私有注入。
3. `cn_download_protocols.py` / `cn_download_workflow.py` 只运输信号；CNInfo 为满足同一 structural contract 在其
   既有单轮 discovery I/O 前后消费信号，不获得 HKEX cumulative 状态。
4. 对 `tests/fins/test_cn_pipeline.py` 与 `tests/fins/test_cn_download_runtime.py` 的授权仅限 test-double 签名迁移
   和 identity/propagation 断言，不能改变 pipeline/runtime 产品行为。

因此 exact allowlist 是同一可验证 cancellation/completeness 闭环，不是通用 pagination framework，也不是对
CNInfo 产品语义的无关扩张。

## 4. State machine 与 protocol 核对

Plan 已给出 code-generation-ready 的单 slice 闭环：

- official top-level 五字段必填；bool/int/stringified-list 使用 exact JSON 类型，显式拒绝 bool-as-int、负数、
  coercion、aliases 与 fallback；
- response `rowRange` 必须等于 requested range，同轮满足 `loadedRecord == len(rows)`、loaded 不超过 count/range；
- `hasNextRow=false` 仅在 `loadedRecord == recordCnt == len(rows)` 时 complete；
- `hasNextRow=true` 使用最新 `recordCnt` 和 `max(current_range * 2, recordCnt)`；除 `rowRange` 外 query 完全不变；
- 每轮替换 cumulative snapshot，只在 final complete 后 parse/selection/HEAD，不 append/dedup；
- continuation response 的 loaded/rows 必须严格增加。客户端主动改变 requested range 本身不算 provider progress，
  因而不会无限 doubling；最新自洽 terminal snapshot 优先，不推测跨轮 prefix identity；
- 每轮 HTTP 前后检查取消；取消、checker failure、HTTP transport failure 与 provider protocol failure 的 precedence
  和 type/cause 保留边界明确；
- 删除 generic total/truncated/cap contract，不保留旧 exception alias 或兼容分支。

该状态机与设计真源一致。特别是 plan 正确区分“最新累计 snapshot 是唯一权威结果”与“跨轮行身份必须保持
prefix”这两个概念，没有用本地 prefix/dedup 规则过度约束 provider 动态数据。

## 5. Scope、测试与验证核对

Plan 的 production allowlist 仅包含 HKEX owner、直接取消运输 seam、共享 structural contract 所需的 CNInfo
实现；test/fixture/README allowlist 与这些路径一一对应。没有 Service/CLI/Host/Engine/storage/R06-R09/R11-R12
或 deferred issue 实现。

Owner test matrix 覆盖：exact 100、两/多轮、next-range 两分支、count growth、snapshot replacement、query
invariance、五字段缺失、严格类型、负值、同轮矛盾、无进展、四个取消时点、checker failure、首轮/后续 HTTP
failure、per-language isolation、CNInfo regression、test-double structural migration 和 workflow propagation。

Validation 同时要求 focused tests、full Fins、四个 modified production file 各自 branch coverage `>=80%`、full
pyright、scoped Ruff、diff/source/owner/deferred scans、captured official response shape 和非破坏性 official
`>100` smoke。外部 endpoint 不可达只能记录环境限制，不能替代 local deterministic protocol gate；若可达并
证明 provider cap/clamp 或 stall，则 stop 并留下 evidence-driven residual，不能自行添加日期递归或第二分页机制。

README 触发、安全保留、fixture secret hygiene、公开 GET 限制和 Issue 142/151/175/177/178、Web/WeChat/render、
Topic 8/9 no-touch 均明确。

## 6. 双路 review 必须重点挑战

双路 review 仍须基于完整 immutable plan 独立挑战以下高风险点；这不是预置 finding：

1. `cancel_checker` 直接 seam 是否是 production-reachable 的最小闭环，是否有任何无意 CNInfo 行为漂移或遗漏
   direct caller/test double；
2. requested range 的增长不能单独算 provider progress，连续 `hasNextRow=true` 时严格 loaded/rows 增长是否足以
   有限失败，同时不会拒绝最新自洽 terminal snapshot；
3. exact bool/int/stringified-list parser 与 response-range equality 是否符合 captured official evidence，是否存在
   loose coercion、raw aliases 或第二 completeness owner；
4. typed provider protocol error 是否在 `list_report_candidates`/workflow 中保留 type/cause，而不是被 generic
   RuntimeError 或 candidate-not-found 语义抹平；
5. final-only parse/HEAD、per-language isolation、query invariance、count growth 与 external smoke stop policy 是否
   能由测试和 evidence manifest 实际证明；
6. exact allowlist、单 slice、coverage 和 README/security/deferred gates 是否完整且不过度设计。

## 7. Gate state

- current accepted/open plan finding：0（review 尚未执行）。
- blocker：0。
- staged tree：empty。
- next gate：AgentMiMo / AgentDS 并发完整 plan review。
- implementation、commit、R11、R12：未授权。
