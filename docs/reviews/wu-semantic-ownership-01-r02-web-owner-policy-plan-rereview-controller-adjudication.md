# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy plan re-review — Controller adjudication

## 1. 身份与裁决边界

- 本文裁决既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 R02 remediation plan 的双路完整 re-review；不是新 WU、feature、issue 或 implementation authorization。
- 审查目标是 `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` 的 plan-fix 最终全文。
- 输入是两份完整 re-review：
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-ds.md`
- 上游 disposition 真源仍是：
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`
- Controller 已完整读取最终 plan、AgentCodex fix artifact 与两份 re-review，并把 reviewer 声称重新对照上游裁决、当前代码事实和最终 plan；reviewer verdict 本身不自动授权 acceptance。

## 2. 双路 re-review 完整性

| route | verdict | complete target | controller assessment |
|---|---|---|---|
| AgentMiMo | `pass` | 最终 plan 全文、初始两路 review、两份上游 adjudication、fix artifact、当前 Web code/config/tests | 完整；逐项验证 `R02-PF-01..10`、rejected 项、owner/slice/security/deferred scope；提出一项 LOW finding |
| AgentDS | `pass` | 同一 immutable target 与完整证据链 | 完整；逐项验证 `R02-PF-01..10`、六组 rejected 项、HEAD baseline、owner/slice/security/validation/deferred scope；无新 material finding |

两路均确认当前工作树没有 product/test/README implementation diff，R02 plan 尚未被提前实施。

## 3. `R02-PF-01..10` 最终状态

| finding | final disposition | controller evidence |
|---|---|---|
| `R02-PF-01` | `accepted/closed` | S1 entry 不依赖 S3；S3 使用模块私有版本化 fixture case；无 fixture CLI/path authority |
| `R02-PF-02` | `accepted/closed` | 普通 JSON/JSONL/markdown writer 保持 HEAD 行为；无新增 fsync/replace/rollback/atomic writer contract |
| `R02-PF-03` | `accepted/closed` | 同一次 attempt 的 `merge_environment_settings`、`select_proxy` 与 `Session.send` settings 同源；warning/proof conflict 只消费脱敏的 selected-proxy 存在事实 |
| `R02-PF-04` | `accepted/closed` | S1 只构造并保存 frozen transport policy；S2 原子迁移 sender 与全部 caller，必填 named parameter 无兼容 default |
| `R02-PF-05` | `accepted/closed` | browser/proof config 可共存；只在真实 fallback 启动前以 `browser_peer_proof_unavailable` fail close，进程零启动且 LLM-facing message 不泄漏内部术语 |
| `R02-PF-06` | `accepted/closed` | ConfigLoader record replacement 不变；final record 缺失项由 provider parser 的 typed defaults 拥有，不做 deep merge |
| `R02-PF-07` | `accepted/closed` | search result visibility 与 fetch 同源消费 private/custom-port typed `WebEgressPolicy`，不重读 raw config |
| `R02-PF-08` | `accepted/closed` | S2 有 deterministic DuckDuckGo challenge regression，`web_challenge_detection.py` 保持零 diff |
| `R02-PF-09` | `accepted/closed` | aggregate budget 是无 default、无 validator、无 facade 的 frozen pure composition；child owners 自行校验 |
| `R02-PF-10` | `narrowed-accepted/closed` | controller 冻结值直接进入 S1；无 pre-S1 普遍充分性 gate；S3/aggregate 只记录 metrics，只有直接超限或由 ceiling 导致的失败才 stop |

全部十项上游 accepted/narrowed findings 已关闭；没有 accepted finding 留给后续优化。

## 4. Rejected 项保持未实施

Controller 接受两路共同证据，确认以下上游 rejected 路径没有通过改名、fallback、测试 shim 或兼容分支回流：

- 不在测试章节复制第二份 packaged expected-values 真源；
- 固定 provider endpoint 不绕过初始 DNS/address/custom-port/peer 防御；
- diagnostic `--allow-private-network-url` 继续删除，不建立第二 policy input；
- changed production file coverage 继续逐文件 `>=80%`；
- 不新增 fixture CLI/path authority或 pre-S1 micro-slice；
- ConfigLoader 不改成 deep merge；
- 不恢复 64 KiB warmup；
- 不实施 Issue 178 lifecycle、统一 tool authorization framework、R03 或其它 deferred Issue。

## 5. 新 finding 裁决

### `R02-RR-F01` — MiMo LOW — `rejected/no-fix`

- **Reviewer 观点**：建议在 §11.1 再增加旧 packaged values 到 controller 冻结 values 的逐项映射与 rationale，便于 implementation agent 理解变更幅度。
- **直接证据**：最终 plan §2.3 已记录 HEAD 旧值，§4.1 是冻结后的唯一 packaged/typed 字面值真源，§11.1 记录真实 HTTP/Playwright/filing plan-time metrics，§11.2 定义唯一 stop 规则；`R02-PF-10` controller adjudication 已明确这些值由用户/controller 冻结且不得在 R02 重开普遍充分性裁决。
- **裁决**：拒绝修改。该建议没有发现缺失字段、不同步默认值、错误 owner、不可执行 gate 或未分类风险。再增加一份逐项数值映射会形成第二份易漂移说明真源，并诱使 implementation agent 把已完成的产品裁决重新解释成待证明 rationale。
- **状态**：`rejected/no-fix`。无需 AgentCodex 修改、第三轮 re-review 或新增 residual risk。

AgentDS 没有新 material finding；其三项观察均为 implementation 注意事项，已被 plan 的 fixture fail-fast、transport owner 和 traceability要求覆盖，不产生 fix。

## 6. 安全与 scope 裁决

- 保留 redirect 每跳重检、dangerous/unspecified/multicast deny、mixed-DNS fail close、numeric peer proof、proxy/proof typed incompatibility、resource budgets、challenge detection、diagnostics v2、redaction、explicit storage input、containment 与 symlink 防御。
- 私网、自定义端口、proxy、browser 与 peer-proof 的新默认/开关仍由 typed Web config 与对应执行 owner 拥有；没有创建统一 authorization framework、policy DSL、role/capability 或 sandbox。
- storage-state credential lifecycle 只删除当前提前实现；Issue 178 仍是 future lifecycle owner。`init --reset` 的 Dayu-owned directory 删除边界不在 R02 中被重设计。
- R03 accepted-result/LLM projection、Issue 142/151/175/177/178 的实现均未进入本 plan。

## 7. Final decision

R02 plan re-review gate **通过**：

- `R02-PF-01..10` 全部关闭；
- 所有 rejected 项保持未实施；
- 新增 `R02-RR-F01` 为 `rejected/no-fix`；
- 无 open question、无 accepted finding、无未分配 residual risk；
- 不需要第三轮 plan fix/re-review。

最终 plan 被 Controller 接受为 code-generation-ready，但其授权范围仅是产生 R02 accepted-plan local commit，之后进入 `R02-S1 Config owner 与 typed policy split` implementation gate。它不授权 S2/S3 越序实施、不授权 R03、不授权 Issue 178 lifecycle或统一 tool authorization framework。
