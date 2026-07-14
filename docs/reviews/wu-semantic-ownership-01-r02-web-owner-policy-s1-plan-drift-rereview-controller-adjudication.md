# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 plan drift 双路 re-review Controller 裁决

## 1. Gate 身份与裁决范围

- 本文裁决既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R02` 的 S1 plan-drift 完整双路 re-review；不是新 WU、feature、issue，也不重开历史独立 sub-WU。
- 权威产品裁决仍是 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`。本轮只判断 `R02-S1-DR-01..04` 是否已在最终 946 行 plan 中闭合，以及两路 reviewer 的新增意见是否要求继续修 plan。
- review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-rereview-ds.md`
- 被审 plan：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`。
- 直接代码证据基线：当前 `HEAD 4d2df703`；本 gate 尚无产品、测试或 README 修改。

## 2. 双路结论

- AgentMiMo：`pass-with-risks`。确认 `R02-S1-DR-01..04` 全部 closed-in-plan、九文件直接 consumer 闭集完整、四文件 S1 type-only 边界可执行、owner/payload 唯一、utility `1_024/default=80` 时序自洽、验证矩阵完整，且无 S2/S3、Issue 178、R03 或统一 authorization 偷带；提出两条低风险意见和两个由同一意见派生的 open questions。
- AgentDS：`PASS-WITH-OBSERVATIONS`。独立确认四项 drift finding 全部关闭且无 material blocker；提出一个 kwargs 实施注意和一个非 allowlist 测试 residual note。
- 两路结论在 root cause、owner map、slice 边界、验证闭集和 deferred/no-code 边界上相互印证，没有直接证据冲突。

## 3. `R02-S1-DR-01..04` 最终状态

| Finding | 最终状态 | Controller 证据 |
|---|---|---|
| `R02-S1-DR-01` | `accepted/closed` | 九文件 `WebResourceBudget` 直接引用闭集已由两路独立复扫确认；遗漏的 `web_fetch_orchestrator.py`、`web_playwright_backend.py`、`utils/diagnose_web_access.py`、`test_diagnose_web_access.py` 已精确前移到 S1，且只授权 owner type/signature/forwarding/direct-test 迁移。 |
| `R02-S1-DR-02` | `accepted/closed` | aggregate 只停留在 `WebToolsConfig`；`web_tools.py` 是唯一 child projection point；HTTP、Browser、Diagnostic 参数与 worker/process payload 已在 §4.2、§8.2、§8.3、§15.4 同源冻结；probe 无 budget。 |
| `R02-S1-DR-03` | `narrowed-accepted/closed` | utility HTTP/Browser defaults 在 S1 直接复用 typed owner constants；utility-local `1_024/default=80` 在 S1 保持且不得扩散，S3 删除并同源到 `DiagnosticResourceBudget.error_chars/events`；S1/S3 scans 明确区分预期命中与零残留。 |
| `R02-S1-DR-04` | `accepted/closed` | S1 direct diagnostic budget node、`dayu tests utils` 零残留 scan、两个新增 production coverage candidate、utils direct behavior test 和完整 pyright 已写入 gate/completion；不允许 exclude 或 inherited-failure waiver。 |

## 4. 新增意见逐项裁决

### 4.1 `R02-S1-DRR-MIMO-01` — “type-only”可能被误读为整个 S1

**Disposition：`rejected/no-fix`。**

“type-only”在最终 plan 中始终限定为四个 drift 前移文件的 S1 授权边界；S1 总体名称和 §8.2 items 2-6 明确包含 nested config parser、`WebEgressPolicy.allow_custom_port`、`WebHttpTransportPolicy` 与 aggregate/child projection。不存在把整个 S1 约束成纯 annotation rewrite 的可执行歧义。再增加同义解释会重复边界，不关闭新的语义缺口。

### 4.2 `R02-S1-DRR-MIMO-02` — `web_diagnostics.py` 是否必须接 budget type

**Disposition：`rejected/no-fix`；派生 open question 关闭。**

Plan §8.2 item 7 明确允许 diagnostics projection signature 接 `DiagnosticResourceBudget` **或两个显式 owner fields**；当前代码已采用显式 owner fields，因此 S1 可以 inspect 后保持零 diff。§6.1 把该文件纳入总闭集并不要求制造无语义改动；§10.3 同样只要求确认 typed diagnostic config 的同源消费而不改变 v2/revision/redaction。给现有精确字段强行包一层 dataclass 反而会扩大 diff，并使同一事实出现不必要的第二种投影形式。

### 4.3 `R02-S1-DRR-MIMO-Q02` — Playwright 两个 child budget 的 runtime 传播

**Disposition：`rejected/no-fix`；open question 关闭。**

Plan §8.2 item 6 已要求 `_PlaywrightFallbackKwargs` 拆成 browser/diagnostic 两个显式 typed fields，并由 `web_tools.py` 从 `WebToolsConfig.resource_budgets` 唯一投影；item 10 要求 `_fetch_and_convert_with_playwright` 显式接两个 child values，worker kwargs 只含 Browser、process wrapper 单独接 Diagnostic。§4.2 还禁止下游接 aggregate 或从 raw config 重建。传播链已经 code-generation-ready。

### 4.4 `R02-S1-DRR-DS-01` — `_StageFetchKwargs` 与 probe 的 `**kwargs` 冲突风险

**Disposition：`rejected/no-plan-fix`，保留为 S1 实施验证点。**

该反例在机械替换旧字段时成立，但最终 plan §8.2 item 6 已明确：“`_StageFetchKwargs` 不再让 warmup/probe 共用 budget”，“所有 wrapper/fake/callable 使用精确参数”，“不用 `**kwargs`”；item 9 又要求 `_probe_content_type` 删除 budget 参数与 forwarding。正确实现只能拆分 payload 或显式传 probe 参数，不允许继续把含 budget 的共享 TypedDict 解包给 probe。S1 focused tests、full provider test 和 pyright 会验证这一点；不需要再次修 plan。

### 4.5 `R02-S1-DRR-DS-02` — 非 allowlist 测试含 Web config 字面量

**Disposition：`accepted residual verification note`，不是 plan defect，不扩 allowlist。**

`tests/service/test_host_assembly.py` 与 `tests/tools/test_combined_tools_acceptance.py` 的三处命中均显式提供现存 `allow_private_network_url`，不 import 旧 budget type，不消费 flattened budget schema，也不依赖 packaged private default。S1 保留该字段并只为缺失 sibling/group 应用 typed defaults，当前没有直接断裂证据。若实施后任何非 allowlist 测试真实失败，§15.3 要求停止并由 Controller 裁决，不得自行扩 scope；在此之前机械把整份 `tests/` 加入 gate 会扩大验证成本且不修 owner contract。

## 5. 安全与 scope 复核

- S1 仍保留 sender 的 pinned/no-proxy、每 hop authorization、mixed-DNS fail-close、response lease、timeout/cancellation；本 gate 不删除 DNS/peer、proxy、resource budget、containment、symlink 或其它防御机制。
- 私网/custom-port、peer proof、proxy 与 browser/private 解耦的产品行为只在 S2 实施；S1 不提前改变 transport/browser 行为。
- storage-state lifecycle 删除只在 S3；Issue 178 的未来 lifecycle 不进入 R02。
- 未设计或实现统一 tool authorization framework、permission schema、policy DSL、role/capability 或 sandbox。
- R03、Issue 142、151、175、177、178 及 Web/WeChat/render tracker 能力均未偷带。

## 6. Gate 结论

**Controller verdict：PASS。**

- `R02-S1-DR-01..04` 全部闭合。
- 两路 re-review 没有 accepted plan fix、material blocker 或未关闭 open question。
- 所有新增低风险意见已有最终 disposition；唯一 accepted residual note 只要求在真实失败时按既有 stop condition 裁决，不授权现在扩大 allowlist。
- 最终 plan 可进入 superseding accepted-plan local commit。历史 commit `6e2a76b3` 只保留历史证据，不再是 execution truth。
- 在 superseding accepted-plan commit 产生并由 control 记录前仍不得进入 S1 implementation；之后只授权 R02-S1，不授权 S2/S3、R03、Issue 178 或统一 authorization。
