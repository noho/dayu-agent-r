# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 Code Review Controller Adjudication

## 1. 身份与边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- internal remediation sub-WU / slice：`R02 / S2`。
- review base：accepted S1 commit `c7b01d82`。
- target：当前完整 R02-S2 worktree。
- review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-ds.md`
- authority：产品裁决以 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 为准；R02 执行边界以 accepted R02 plan 及已闭合的 S2 plan-drift 裁决链为准。

本裁决只判断 reviewer 提出的 finding 是否代表当前 S2 owner contract 缺陷。它不授权 R02-S3、Issue 178、R03、proxy credential schema、统一 tool authorization framework 或其它 deferred scope。

## 2. 第一性原理判断

R02-S2 的真实问题是：Web HTTP、search provider、browser 与 diagnostic raw requests 必须消费同一份 provider-owned transport policy，并在每次出站 attempt 上正确执行 proxy、DNS peer proof、egress、browser capability 与安全投影。Controller implementation validation 和两路完整 review 都确认这些行为已经成立。

三项 reviewer 意见中，没有一项给出错误结果、错误状态、越权出站、安全降级、资源泄漏、LLM-facing 语义错误或 owner divergence 的直接反例。两项 DS 意见明确承认当前行为正确，提出的只是结构重排或 helper 抽取；MiMo 意见则精确命中 accepted plan 已冻结给 S3 的 pre-existing diagnostic CLI 状态。因此，本轮不存在需要修改 S2 产品代码的 accepted finding。

## 3. Finding 唯一 disposition

### R02-S2-MIMO-F01 — reclassified / no S2 fix

- reviewer 主张：`utils/diagnose_web_access.py` 当前把 diagnostic `allow_custom_port` 与 `allow_private_network_url` 绑定。
- 直接证据：该代码事实存在；MiMo 与 DS 都定位到同一路径。
- Controller disposition：**reclassified as an already-planned S3 observation；不是 S2 accepted finding**。
- 理由：accepted R02 plan §9.4、§9.6 与 S2 plan-drift `R02-S2-DR-01` 明确要求 S2 只前移 mandatory typed transport snapshot 的 direct-caller/fake 传播，并保持 utility CLI / egress-policy transitional behavior；plan §10.3 已把 diagnostic utility 消费完整 typed Web config、删除旧 CLI coupling 分配给 S3。现在于 S2 修改该行为会违反 slice temporal boundary，而不是修复 S2 缺陷。
- owner / destination：`R02-S3`，由 diagnostic typed-config integration 闭合；不是 future optimization，也不需要新 Issue。
- tests：S3 必须覆盖 private-network 与 custom-port 独立组合；S2 不增加提前固化 S3 结果的测试。

### R02-S2-DS-F01 — rejected / no fix

- reviewer 主张：`ProxyPeerProofIncompatibleError` 分支调用 `_raise_fetch_failure(...)` 后缺少显式 `return`、独立 `except` 或说明注释。
- 直接证据：`_raise_fetch_failure` 的唯一 contract 是记录诊断后始终 `raise ToolBusinessError`；其实现、docstring 与现有调用路径一致。reviewer 也明确确认该分支当前不会 fall through，产品行为正确。
- Controller disposition：**rejected as a defect；不修改**。
- 理由：以“未来可能把 owner helper 改成不抛异常”为前提增加局部注释、无效 `return` 或重排 exception hierarchy，不修复任何当前业务事实或安全事实，还会为不成立的未来兼容假设增加 seam。若要让静态类型直接表达 never-return，应由该共享 owner contract 的独立任务整体评估，而不能只在一个消费者处局部补偿；本 WU 没有该需求或证据。
- tests：现有 proxy+proof typed fail-close 测试已覆盖真实 contract；无新增测试缺口。

### R02-S2-DS-F02 — rejected / no fix

- reviewer 主张：RequestException challenge 路径与 successful fetch post-hoc challenge 路径的 `FAIL_BLOCKED` projection 可抽成 helper，并统一微有差异的 message。
- 直接证据：两处分别拥有不同输入事实：前者消费 HTTP exception/response 上下文并说明“bot challenge page or access gate”，后者消费成功 materialization 后的内容判定并说明“bot challenge page”。reviewer 明确确认两处有不同到达条件且功能正确。
- Controller disposition：**rejected as a defect；不修改**。
- 理由：这是两个独立 stage 的 terminal projection，不是同一业务事实被不同 owner 重算。为两处调用抽取单一 helper 会增加参数化 glue，并可能抹平 stage-specific LLM-facing 语义；没有错误输出或重复真源证据支持该重构。当前 overdesign remediation 更不应实施无行为收益的抽取。
- tests：两类 challenge path 已有 owner-level tests；无新增测试缺口。

## 4. Observations 与 residual owners

- DS-O01 与 MiMo-F01 是同一 S3-owned transitional diagnostic 状态，只保留一个 owner/destination：`R02-S3`。
- DS-O02、O04、O05 是正向验证事实，不生成修复项。
- DS-O03 的 near-threshold coverage 不是产品缺陷；S3 和 aggregate gate 仍必须重跑 changed-production per-file coverage，不得把当前精确通过值当作豁免。
- storage lifecycle、TTL、owner filename、publish/reconcile 仍由 R02-S3 删除当前实现；未来 lifecycle 仍由 Issue 178 承接。
- retained DNS/redirect/peer proof/proxy deny/resource budget/browser route/challenge/diagnostic v2/redaction/containment/symlink 安全机制保持；未设计或预埋统一 tool authorization framework。

## 5. Gate 裁决

- accepted S2 code findings：**0**。
- rejected as current defects：`R02-S2-DS-F01`、`R02-S2-DS-F02`。
- reclassified to already-planned S3 owner：`R02-S2-MIMO-F01`（与 `R02-S2-DS-O01` 同一事实）。
- blocking question：0。
- verdict：**PASS into the mandatory zero-change fix/adjudication record gate**。

按 accepted plan §15.1，即使零 accepted finding 也必须形成 zero-change fix/adjudication 记录，不能 conversation-only pass。因此下一步由 AgentCodex 生成固定 artifact `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-fix-codex.md`，只证明当前 immutable target、三项 disposition、零代码/测试/README/plan 变更及 gate checks；不得借此修改 reviewer 建议、S3-owned behavior 或 deferred scope。随后仍需 MiMo/DS 对完整最终 slice 做双路 re-review，Controller 最终裁决后才允许 accepted local commit。

## 6. Handoff

等待 Controller 路由 AgentCodex 执行 zero-change fix record。当前不得 commit、不得进入 R02-S3、不得实施 Issue 178 / R03 / proxy credential schema / unified authorization。
