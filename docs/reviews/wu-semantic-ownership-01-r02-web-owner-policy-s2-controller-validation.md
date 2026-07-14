# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 Controller Validation

## 1. Gate identity and verdict

- Umbrella：现有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- Internal remediation slice：`R02-S2` HTTP / proxy / peer proof / browser owner execution。
- Validation base：accepted R02-S1 commit `c7b01d82` 加当前未提交 R02-S2 implementation diff。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`。
- Verdict：**PASS — ENTER DUAL COMPLETE CODE REVIEW**。

Controller 已独立读取 final plan、plan-drift 裁决链、实现 artifact、全部 production diff、diagnostic direct-consumer diff及关键 owner tests。当前没有 Controller implementation finding、blocking question 或未分类风险。该结论只允许 AgentMiMo / AgentDS 对同一 immutable target 并发执行完整 code review；R02-S2 尚未 accepted、未 commit，也不授权 R02-S3、Issue 178、R03、proxy credential schema或统一 tool authorization framework。

## 2. Motivation and semantic owners

本 slice 的动机成立且严重度为 production-high：旧实现把环境 proxy、numeric peer proof与 pinned transport绑定为单一路径，并把 private-network permission错误当作 browser capability，导致合法默认 proxy、公网 browser与独立 proof配置组合无法按产品裁决执行。

当前 owner 划分与裁决一致：

- `provider._parse_config` 是 raw `tool_discovery.json` Web provider config 的唯一 parser/default owner。
- `web_http_session.py` 是 `WebHttpTransportPolicy` 与每次 HTTP attempt transport选择的 owner。
- `WebEgressPolicy` 继续唯一拥有 URL、scheme、host、port与 resolved-address authorization。
- `web_fetch_orchestrator.py`、`web_search_providers.py`、`web_playwright_backend.py`、`web_tools.py` 与 diagnostic utility只消费同一次 typed snapshot，不重建 transport default或从环境反推业务配置。
- challenge detector、HTTP/browser/diagnostic child budget与 diagnostics v2 projection owner均保持不变。

## 3. Independently confirmed implementation behavior

### 3.1 HTTP and search transport

- proof关闭时使用标准 `requests` adapter；proxy允许时以一次 prepared request、一次 `merge_environment_settings`、一次 `select_proxy` 和同一 settings 的 `Session.send`消费当前 URL实际选择的环境 proxy。
- proxy禁止时 `trust_env=false`，session/per-call proxy输入为空，send settings保持 `proxies={}`。
- proof开启且当前 URL没有active proxy时继续使用既有 numeric target / peer comparison owner；active proxy存在时在发送前抛出 typed `proxy_peer_proof_incompatible`，没有静默降级。
- proxy warning只包含稳定 reason与存在性，不包含 URL、proxy URI、credential、headers或cookies。
- redirect每跳继续先执行 egress authorization，再执行 attempt-local transport选择。
- Tavily、Serper、DuckDuckGo固定endpoint已迁入同一 plain sender；首次发送仍执行DNS/address/custom-port authorization，redirect仍禁止，API key与query/result业务语义没有迁入transport owner。

### 3.2 Browser and challenge

- `browser_enabled` 与 private-network permission双向解耦：公网 browser不再因private=false被拒绝，private=true也不反向启用browser。
- browser route/navigation仍逐目标消费同一 `WebEgressPolicy`；private/custom-port/dangerous/mixed-DNS防御没有删除。
- proof开启的browser fallback在import/process start前以 `browser_peer_proof_unavailable` fail closed；LLM-facing message只表达无法验证目标连接，不泄漏Playwright、socket、peer/proof或Host/runtime术语。
- environment proxy禁止时只在spawn出的browser worker清理标准proxy变量；允许时继承运行环境。
- challenge detector文件零diff；所有challenge availability不再硬编码true，而是消费当前browser capability与proof compatibility。

### 3.3 Diagnostic direct consumer

- single diagnostic orchestration只调用一次 `_provider_config(options)` 得到raw mapping。
- 同一mapping同时进入 `provider._parse_config(...).transport_policy` 与 provider discovery；raw requests profile只接收并转发该typed snapshot。
- `_build_requests_profile` 与 exact fake都使用无default、typed、keyword-only `transport_policy`，没有 `**kwargs`、compatibility default、wrapper、`getattr`、第二parser、policy constructor或环境推断。
- 原三个 `artifact_missing` case已恢复为真实 v2/revision2 evidence；没有修改 `utils/smoke_web_ci.py` 来迁就失败。

## 4. Controller independent validation evidence

所有命令均在 `source .venv/bin/activate` 后执行。

### 4.1 Tests

| gate | result |
|---|---:|
| provider focused：`private or custom_port or proxy or peer or redirect or browser or challenge` | `69 passed, 1 skipped, 105 deselected` |
| provider full | `174 passed, 1 skipped` |
| diagnostic full | `37 passed` |
| ConfigLoader regression | `52 passed` |
| fresh joint coverage run | `211 passed, 1 skipped` |

唯一skip是既有opt-in/manual live browser cleanup test；不是 deterministic local hard gate。

### 4.2 Exact changed-production coverage

Controller使用独立data file `workspace/tmp/.coverage-r02-s2-controller` 与JSON `workspace/tmp/coverage-r02-s2-controller.json` 重跑：

| production file | exact percent | covered / statements / missing |
|---|---:|---:|
| `web_http_session.py` | `89.12280701754386%` | `254 / 285 / 31` |
| `web_fetch_orchestrator.py` | `81.6247582205029%` | `422 / 517 / 95` |
| `web_search_providers.py` | `87.45762711864407%` | `258 / 295 / 37` |
| `web_playwright_backend.py` | `80.48780487804878%` | `429 / 533 / 104` |
| `web_tools.py` | `80.0561797752809%` | `570 / 712 / 142` |

五个changed production files均按JSON精确值达到 `>=80%`；`web_tools.py`没有依赖整数显示或四舍五入通过。

### 4.3 Type, signature, docs and source gates

- 完整 `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check c7b01d82 --`：通过。
- target-specific AST：`transport_signature_audit=2 / issues=0`。
- Controller semantic AST exact set：`added-or-signature-touched=99 / issues=0`，新增class/TypedDict为2个；implementation artifact的保守100项闭集额外包含外层 `test_playwright_budget_failure_projects_stable_tool_error`，因为其nested fake签名及外层docstring/body同时改变。两种闭集的全部function/method/nested helper均有中文 `Args/Returns/Raises`，两个新增class/TypedDict均有fields/attributes、call contract、returns与raises说明。
- 相对 `c7b01d82` 的changed paths只落在final plan允许的五个Web production files、diagnostic utility、两个Web tests、两份README、plan/control和固定artifact链。
- `dayu/tools/web/web_challenge_detection.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh` 与根 `README.md` 均零diff。
- utility中没有 `WebHttpTransportPolicy(...)` constructor、transport bool raw parsing、environment读取或 `getattr`；仅保留两个既有browser Protocol `**kwargs`，不属于transport seam。

### 4.4 Deterministic real smoke

Controller以独立输出目录执行final plan命令：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-controller \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-controller
```

结果：exit `0`，`status=passed`，7个local cases全部通过，`failures=0`、`skips=0`；4个external search cases保持diagnostic-only。

- `local-html-requests`：requests completed，HTTP 200，challenge=`none`，v2/revision2。
- `local-pdf-requests`：requests completed，HTTP 200，challenge=`none`，v2/revision2。
- `local-challenge-control`：requests completed，HTTP 200，challenge=`confirmed`，v2/revision2。
- `local-browser-playwright`：真实browser completed，HTTP 200，challenge=`none`，v2/revision2。
- `local-html-tool`、`local-pdf-tool` 与 `local-assembly-config` 同时通过。

## 5. Retained security, deferred scope and residuals

保留的安全行为：initial URL与redirect逐跳authorization、dangerous/unspecified/multicast/mixed-DNS拒绝、private/custom-port配置边界、numeric peer match/mismatch、proxy+proof fail closed、browser route/navigation egress、HTTP/browser/diagnostic resource budgets、challenge evidence、redaction、filesystem containment与symlink防护。当前实现没有统一 tool authorization framework，也没有删除既有局部权限配置或防御性安全机制。

明确未实施：

- R02-S3拥有的credential storage-state lifecycle删除、diagnostic utility本地 `1_024` / `--max-network default=80`迁移与后续filing fixture smoke。
- Issue 178未来credential lifecycle。
- R03及其它remediation sub-WU。
- proxy credential schema、PAC、permission DSL、role/capability、sandbox或统一authorization。

Residual risks均有owner：external provider DNS/key/站点波动归external diagnostics且不阻塞local hard gate；proxy无法同时证明origin peer与browser无法提供numeric peer proof均由当前typed fail-closed语义承担；storage lifecycle与utility-local diagnostic defaults归R02-S3。`web_tools.py`覆盖率接近门槛，进入双路review时继续作为验证触发项，但当前精确gate已通过，不是accepted residual defect。

## 6. Handoff

当前没有Controller accepted finding。下一gate是AgentMiMo与AgentDS对同一未提交target执行双路完整code review。Reviewer必须重点挑战：

1. 同一次prepared/merged settings是否真实贯穿proxy selection与send；
2. search provider是否保留初始egress/proof、credential与challenge语义；
3. browser capability/proof/proxy与challenge facts是否发生隐式重写；
4. 大幅test/docstring diff是否只锁定owner contract而未冻结无关偶然行为；
5. R02-S3、Issue 178、R03与统一authorization是否保持零泄漏。

R02-S2只有在双路review、Controller逐finding裁决、所有accepted findings修复和双路完整re-review闭合后才能产生accepted local commit。
