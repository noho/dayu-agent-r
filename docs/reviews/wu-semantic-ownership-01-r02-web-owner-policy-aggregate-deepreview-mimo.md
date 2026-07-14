# R02 Aggregate Deepreview — AgentMiMo

> Review timestamp: 20260715-044400

## Scope

- Mode: aggregate deepreview (not a new WU; same umbrella `WU-SEMANTIC-OWNERSHIP-01`)
- Branch: `phaseflow/host-issues-control`
- Base: `2d42ceb6` (superseding accepted R02 plan) to `7e679796` (R02-S3 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-mimo.md`
- Included scope: complete `2d42ceb6..7e679796` diff of 11 changed production `.py` files, `dayu/config/tool_discovery.json`, `dayu/config/README.md`, `tests/README.md`, 4 test files, 2 utility scripts; all R02 slice implementation/controller-validation/rereview/controller-adjudication artifacts; aggregate validation and aggregate controller validation artifacts; control document current gate
- Excluded scope: `dayu/render/`, `utils/` non-web scripts, binary/vendor/build artifacts
- Parallel review coverage: 4 parallel agents read AGENTS.md, control doc, plan-entry adjudication, aggregate validation, aggregate controller validation, S1-S3 controller validations, S1-S3 implementation artifacts, S1-S3 rereview artifacts, S1-S3 controller adjudications; main reviewer independently read full diff of `provider.py`, `web_resource_budget.py`, `web_http_session.py`, `web_tools.py`, `web_playwright_backend.py`, `web_fetch_orchestrator.py`, `tool_discovery.json`, README diffs, and performed targeted `rg` adversarial scans

## Adversarial Verification Results

### 1. S1-S3 组合是否真正把 raw parser/default/budget/transport/browser/diagnostic lifecycle 放在唯一 owner

**结论: PASS — 每个语义事实都有唯一 owner，无第二默认、无下游补偿。**

直接证据：

| 语义事实 | Owner | 验证 |
|---|---|---|
| raw `tool_discovery.json` Web provider config parsing/default | `provider._parse_config` | `rg '_parse_config'` 命中 3 处：定义 `provider.py:96`、主入口 `provider.py:85`、诊断工具 `diagnose_web_access.py:2409`。诊断工具只调用一次，不重复解析。 |
| 12-field closed set unknown rejection | `_CONFIG_FIELDS` frozenset in `provider.py` | `provider.py:41-56` 定义精确 12 字段闭集；`provider.py:109-114` 在读取任何字段前计算 `unknown_fields = set(config) - _CONFIG_FIELDS` 并抛出 `ValueError`。 |
| 5 个独立 bool 字段 default | `provider.py` 模块级 `_DEFAULT_*` 常量 | `_DEFAULT_ALLOW_PRIVATE_NETWORK_URL=True`, `_DEFAULT_ALLOW_CUSTOM_PORT_URL=True`, `_DEFAULT_DNS_PEER_PROOF_ENABLED=False`, `_DEFAULT_ALLOW_ENVIRONMENT_PROXY=True`, `_DEFAULT_BROWSER_ENABLED=True`。`_bool_default` 使用 `if field_name not in config` 守卫，JSON `null` 被 `isinstance(value, bool)` 拒绝。 |
| 3 个 child budget type | `web_resource_budget.py` 的 `HttpResourceBudget`/`BrowserResourceBudget`/`DiagnosticResourceBudget` | 旧 `WebResourceBudget` 在 `dayu/tools/web/` 零命中（`rg 'WebResourceBudget\b'` 返回空）。`web_resource_budgets_from_json` 按 group 解析，缺失 group/field 只补对应 child owner 的 typed default。 |
| HTTP transport policy | `WebHttpTransportPolicy` frozen dataclass in `web_http_session.py:97-109` | 由 `provider._parse_config` 从 typed bool 快照构造，下游只消费不重建。 |
| per-HTTP-attempt transport selection | `_send_authorized_request_attempt` in `web_http_session.py:638` | 每 attempt 只 prepare 一次，merged settings 原样进入 proxy selection 与 send；`trust_env` 由 `transport_policy.allow_environment_proxy` 决定；proxy+proof 冲突在发送前抛出 typed 异常。 |
| browser capability / private-network decoupling | `_browser_fallback_available` in `web_tools.py:915-933` | `browser_enabled and not transport_policy.dns_peer_proof_enabled`；双向独立：关闭 browser 不因 private URL 启动，关闭 private URL 不阻止公网 browser。 |
| diagnostic error chars | `DiagnosticResourceBudget.error_chars` | `_raise_fetch_failure` 签名有 mandatory `diagnostic_error_chars: int`（无 default），`rg '_DEFAULT_DIAGNOSTIC_ERROR_CHARS|DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET'` 仅在 `web_resource_budget.py` 的 parser default 中命中（`DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET` 作为缺失字段的 typed default，不是全局 fallback）。 |
| diagnostic lifecycle (storage-state output/TTL/publish/reconcile/cleanup) | 已删除 | `rg 'storage_state_out|output_enabled|output_label|ttl_seconds|published|_StorageStateLifecycle|_PRIVATE_DIRECTORY_MODE|_PRIVATE_FILE_MODE' utils/diagnose_web_access.py` 零命中。测试中的 `output_enabled`/`ttl_seconds`/`published` 命中是**否定断言**（确认不存在），不是生命周期实现。 |
| `--max-network` absent state | `diagnose_web_access.py` | 已删除 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`；`--max-network` absent 时 `None`，消费 typed `DiagnosticResourceBudget.events`。 |
| `--storage-state-in` | `_resolve_explicit_storage_state_input` in `diagnose_web_access.py` | 只做常规文件/UTF-8/JSON object 校验，不做 output/TTL/publish。 |

### 2. private/custom/browser/proxy/peer 按裁决组合且 security fail-close 未被削弱

**结论: PASS — 所有安全 fail-close 行为保留，typed 异常在 I/O 前抛出。**

直接证据：

| 安全行为 | 证据 |
|---|---|
| proxy+proof incompatibility | `web_http_session.py:726-727`: `if selected_proxy is not None and transport_policy.dns_peer_proof_enabled: raise ProxyPeerProofIncompatibleError()` — 在 `call_session.send()` 之前。 |
| browser peer proof unavailable | `web_playwright_backend.py` `_fetch_and_convert_with_playwright`: `if transport_policy.dns_peer_proof_enabled: return {ok: False, reason: "browser_peer_proof_unavailable"}` — 在 import/process start 之前。 |
| proxy denied 时 proxy 映射为空 | `web_http_session.py:685`: `call_session.proxies.clear()`；`web_http_session.py:720-721`: `if not transport_policy.allow_environment_proxy and settings["proxies"]: raise RuntimeError(...)` |
| browser worker proxy 环境清理 | `web_playwright_backend.py` `_playwright_process_entry`: `if not allow_environment_proxy: _clear_proxy_environment()` — 删除 8 个标准 proxy 环境变量。 |
| private/custom-port 独立 deny | S3 controller validation: 两个独立 typed overlay，各自经正式 `ConfigLoader -> assemble_effective_tool_provider_configs -> discover_service_tools -> ToolDefinition.callable` 链，均得到 `permission_denied`。 |
| retained security matrix | 93 passed, 1 skipped, 81 deselected — DNS/redirect recheck/peer proof/proxy conflict/HTTP-browser-diagnostics budgets/browser route/challenge detection/redaction/filesystem containment/symlink 全部保留。 |

### 3. 真实 filing/frozen budgets/diagnostics v2/challenge/storage read input 证据

**结论: PASS — 所有证据直接来自真实执行，未命中 frozen ceiling。**

直接证据：

| 维度 | 观测值 | frozen ceiling | 占比 |
|---|---|---|---|
| HTTP Content-Length | 1,503,780 B | exact fixture bytes | exact |
| HTTP wire bytes | 1,503,780 B | 134,217,728 B | 1.12% |
| HTTP decoded bytes | 1,503,780 B | 268,435,456 B | 0.56% |
| Playwright origin body | 1,503,780 B | HTTP decoded child | below |
| browser DOM | 1,515,212 chars | 16,777,216 | 9.03% |
| browser text | 209,272 chars | 8,388,608 | 2.49% |
| diagnostic events | 6 | 512 | 1.17% |
| diagnostic error chars | 0 | 8,192 | 0% |

- diagnostics v2/revision 2: filing HTTP/Playwright 均 `completed`，`schema_version=web-diagnostics-v2`，`diagnostic_schema_revision=2`
- challenge: filing challenge=`suspected`；独立 challenge control=`confirmed`
- storage read input: Playwright `storage_state.input_used=true`；artifact 零 credential/lifecycle field 命中

### 4. Validation harness 三次错误的归因和 corrected audit 口径

**结论: PASS — 三次均为只读 harness invocation 错误，不是产品 defect；corrected canonical runs 可信。**

三次错误归因：

1. **coverage 辅助循环 zsh `path` 变量冲突**: `path` 是 zsh 特殊变量，覆盖 `PATH` 后在首个 `coverage` 调用前 exit 127。canonical coverage JSON 已先 exit 0 并显示全部 11 文件 `>=80%`；改用 `target_file` 后 exit 0。
2. **docstring audit v1 `ast.dump` TypeError**: 对 AST list 调用 `ast.dump`，在判定前 TypeError，无 source pass/fail 结果。
3. **docstring audit v2 scope 错误**: 把 Sphinx docstring 误限定为 Google sections，把 S1 普通 test fake class 套用 S2 强化 class contract，产生 38 个假阳性；修正为 accepted plan/Controller 口径后 aggregate/S2/S3 issues 均为 0。

Controller 独立重跑验证：310 passed, 1 skipped, pyright 0, 11 local smoke passed, coverage 全部 `>=80%`。Controller 接受 corrected canonical runs。

### 5. 236/99/36 qualified-name completeness

**结论: PASS — 与 Controller validation 独立确认一致。**

- aggregate `2d42ceb6..7e679796`: `added_or_signature_changed=236 issues=0`
- S2 exact range `c7b01d82..d8d6e9d9`: `added_or_signature_changed=99 issues=0`
- S3 exact signature range `08c2380a..7e679796`: `36 issues=0`
- transport signature audit: `2 issues=0`（`_build_requests_profile` 与 `fake_request_with_safe_redirects` 均有 typed `transport_policy: WebHttpTransportPolicy`，无 loose `**kwargs`）

### 6. web_tools.py 和 web_playwright_backend.py 近 80% 覆盖是否隐藏关键缺口

**结论: PASS — 当前精确值通过 `--fail-under=80`，关键 owner/security 路径有直接测试。**

- `web_tools.py`: 712 statements, 570 covered, 142 missing, `80.056%`
- `web_playwright_backend.py`: 533 statements, 429 covered, 104 missing, `80.488%`

关键路径覆盖确认：
- `_raise_fetch_failure` mandatory `diagnostic_error_chars` — 15 个 call site 全部有显式传参
- `_send_authorized_request_attempt` proxy/proof logic — 有 proxy allow/deny、proof match/mismatch、proof+proxy incompatibility 测试
- `_browser_fallback_available` — 有 browser enabled/disabled、proof on/off 测试
- `_try_playwright_fallback` — 有 browser disabled 零启动、proof unavailable fail-closed 测试
- `_fetch_and_convert_with_playwright` proxy environment — 有 inherit/cleanup 测试

未覆盖区域主要是 error branch 的组合和部分 Playwright timeout 路径，不影响 owner 正确性。

### 7. 18-path allowed scope、README、Issue 178/R03/统一 authorization 零偷带

**结论: PASS — 无越权实现。**

- 11 local smoke cases 全部 passed: `local-html-requests`, `local-html-tool`, `local-pdf-requests`, `local-pdf-tool`, `local-browser-playwright`, `local-challenge-control`, `local-filing-http`, `local-filing-playwright`, `local-private-deny`, `local-custom-port-deny`, `local-assembly-config`
- README diff 准确描述五个独立 bool、三组 typed budget、proxy/proof/browser 行为
- `rg 'Issue.*178|R03|unified.*auth|authorization framework|policy DSL|capability token|storage state refresh|storage state retention' dayu utils tests README` 零命中（仅在 plan non-goal 描述中出现）
- Issue 178 replacement lifecycle: 未实现，已删除提前实现
- R03 LLM-facing projection: 未启动
- 统一 authorization: Topic 9 no-code decision

### 8. 所有 residual owner/destination

**结论: PASS — 所有 residual 有明确 destination，无 ownerless 项。**

| residual | owner / destination | non-blocking basis |
|---|---|---|
| credential refresh/retention/concurrent publish/cleanup | GitHub Issue #178 | R02 已删除提前实现，只保留 read input |
| live DOM/event/error 体量变化 | Web config owner | 当前版本化 fixture 未命中 ceiling，runtime 仍 fail bounded |
| proxy 下无法证明 origin peer | Web HTTP transport/config owner | proof+active proxy typed fail closed |
| Playwright 无法提供 numeric peer proof | browser backend owner | proof-on browser 在启动前 typed fail closed |
| external provider DNS/key/site 波动 | Web diagnostics/smoke owner | external-limit=0，local 11/11 |
| `web_tools.py` 80.056% / `web_playwright_backend.py` 80.488% 接近阈值 | R02 aggregate deepreview verification trigger | 当前 JSON 精确值与 `--fail-under=80` 均通过 |
| unified authorization 愿景 | Topic 9 future Controller decision | source/diff 零偷带 |
| accepted-result / LLM projection | umbrella R03 | 必须等待 R02 accepted 后另开 plan gate |

## Findings

未发现实质性问题。

本次 aggregate deepreview 对 S1-S3 组合的完整 diff、所有 review/validation/adjudication artifacts、当前代码状态和验证 harness 进行了对抗验证。每个语义事实都有唯一 typed owner；安全 fail-close 行为全部保留且未被削弱；filing frozen budgets 未触发；harness 三次错误归因可信；qualified-name completeness 与 Controller 独立确认一致；coverage 接近阈值的文件关键路径有直接测试；Issue 178/R03/统一 authorization 零偷带；所有 residual 有明确 destination。

## Open Questions

无。

## Residual Risk

无新增 residual risk。所有既有 residual 的 owner/destination 和 non-blocking basis 见上方 residual 表。
