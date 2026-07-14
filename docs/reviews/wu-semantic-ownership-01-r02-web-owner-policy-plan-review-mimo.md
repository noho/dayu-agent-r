# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy Plan Review — MiMo

## 1. Identity, Scope, and Evidence

- **Reviewed target**: `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（R02 独立 plan gate artifact）
- **Controller adjudication input**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`（`R02-B01/B02=accepted/closed`）
- **Review range**: `b1a0631f^..HEAD`；plan-time HEAD `02fcc5d8`
- **Evidence sources**: AGENTS.md、controller discussion Topic 2/9、五份 design truth、umbrella remediation plan R02 章节、三路原始 designtruth reviews（仅作证据，controller discussion 优先）、当前 HEAD production code/tests/config
- **Temporal baseline**: 2026-07-14，当前分支 `phaseflow/host-issues-control`

### 1.1 Assumptions Tested

1. Motivation/root cause 是否直接同源
2. 五 bool、三 budget groups、HTTP transport/browser/diagnostics owner 是否唯一
3. `web_search_providers.py` 与 `test_config_loader.py` 的精确 allowlist 边界
4. 三 slice sequencing 是否能形成每 slice 完整终态
5. 普通 diagnostic artifact 原子写是否超出 accepted Topic 2 和"已有可保留"的裁决
6. pre-S1 数值裁决是否依赖未来 S3 才新增的参数
7. proxy 实际选择检测、redirect transport、search 固定 endpoint、peer proof/browser fail-close 是否可实现
8. 删除 storage-state lifecycle 是否误删显式 read input 或偷带 Issue 178
9. 删除 `--allow-private-network-url` 是否和唯一 config owner 一致
10. 测试、coverage、pyright、README、source scans、真实 Playwright/SEC fixture smoke 是否充分可复现
11. 是否引入统一 tool authorization framework、其它 deferred Issue 或 R03

---

## 2. Findings

### R02-PR-F01 — 未修复 — 中 — pre-S1 数值裁决 gate 存在不可执行入口（circular dependency）

- **位置**: §11.2 数值裁决 gate 命令
- **问题类型**: 不可直接实施
- **当前写法**: §11.2 给出的 gate 命令包含 `--filing-fixture tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm` 参数传递给 `smoke_web_ci.py`，并称"实现时给 smoke 增加显式 `--filing-fixture` 参数"。§11.2 gate 被定义为在 S1 coding 前必须完成的 mandatory adjudication。
- **反例/失败场景**: 当前 `utils/smoke_web_ci.py` 的 CLI 参数列表（`_parse_args` at line 4606）不含 `--filing-fixture`。该参数在 S3 scope 的 `smoke_web_ci.py` 改动中才会新增。§11.2 gate 命令在当前代码上直接执行会因 `argparse` 未知参数而失败。pre-S1 gate 要求 S3 才产生的功能，形成循环依赖。
- **为什么有问题**: §11.2 声称这是"mandatory pre-S1 adjudication"，但如果 gate 命令不可执行，则 S1 entry criteria 无法满足。plan 要么无法进入 S1，要么需要绕过自己定义的 gate。
- **直接证据**: `utils/smoke_web_ci.py:_parse_args`（line 4606）的参数列表不含 `--filing-fixture`；§11.2 命令包含 `--filing-fixture`；§8.1 声称"S1 entry 仍必须…§11 数值裁决记录完成"。
- **影响**: 实施 Agent 无法执行 pre-S1 gate 命令；要么跳过 gate（违反 plan 不变量），要么在 S1 前偷偷修改 `smoke_web_ci.py`（超出 S1 allowlist）。
- **建议改法和验证点**: 方案 A：将 `--filing-fixture` 参数的实现提取到一个独立的 pre-S1 步骤中（不超出 R02 production allowlist，因为它只修改 `utils/smoke_web_ci.py` 的 CLI 参数解析，属于 R02 已授权文件）。方案 B：pre-S1 gate 改用现有 `_build_local_fixture_cases` 已支持的本地 fixture server 直接提供 SEC fixture，不依赖新 CLI 参数。两种方案都必须使 gate 命令在 S1 coding 前可执行。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

---

### R02-PR-F02 — 未修复 — 中 — 普通 diagnostic artifact 原子写被误述为"已有可保留"

- **位置**: §2.2 "ordinary diagnostic write" 行、§4.4 "保留" 段、§5.2、§10.3
- **问题类型**: 契约缺失 / 计划描述与代码事实不符
- **当前写法**: §2.2 声称 "umbrella 'ordinary diagnostic artifact 既有原子写' 与 HEAD 不一致，但 owner 和允许 script 未变，可在 S3 直接细化，不构成 allowlist blocker"。§4.4 声称 "ordinary JSON/JSONL/markdown diagnostic/smoke artifact 使用同目录临时文件、flush/fsync、`os.replace` 的原子写"。
- **反例/失败场景**: 直接检查 `utils/diagnose_web_access.py` 和 `utils/smoke_web_ci.py` 的当前 HEAD 代码：
  - `diagnose_web_access.py` 的 `_write_json`（约 line 3028）和 `_write_jsonl`（约 line 3341）使用 `Path.write_text` / `open()` 直接写 final path，无临时文件、无 fsync、无 atomic replace。
  - `smoke_web_ci.py` 的 `_write_json`（约 line 1887）同样使用直接写。
  - Summary markdown 也是直接写。
  - 唯一有原子写的是 `_StorageStateLifecycle.publish`（line 271-318），它使用 `O_EXCL` + fsync + `os.replace` + `chmod 0o600`——但它正是 S3 要删除的 credential lifecycle 的一部分。
- **为什么有问题**: plan 将要删除的 credential lifecycle 的原子写机制描述为"ordinary diagnostic artifact 已有原子写"，然后声称 S3 "保留"它。实际上 ordinary diagnostic artifact 当前没有原子写。plan 说"保留"是不准确的——它是新增。这影响对 scope 的判断：如果它是新增而非保留，它是否仍在 accepted Topic 2 的 "已有可保留" 裁决范围内？
- **直接证据**: `utils/diagnose_web_access.py` 的 `_write_json` / `_write_jsonl` 使用 `Path.write_text`（非原子）；`_StorageStateLifecycle.publish`（line 271-318）是唯一使用 `O_EXCL + fsync + os.replace` 的写入路径，而它属于要删除的 credential lifecycle。
- **影响**: 实施 Agent 可能误解 scope：如果认为"已有原子写只需保留"，就不会意识到需要新写一个 owner-local atomic helper。或者反过来，controller 可能质疑这是否属于超出 "已有可保留" 裁决的新增功能。
- **建议改法和验证点**: 明确 plan 文本：ordinary diagnostic artifact 当前是非原子写；S3 新增 script 内 owner-local atomic text helper 是安全改进而非 credential lifecycle 的保留。在 §4.4 中将 "保留" 改为 "新增 owner-local atomic text helper，不复用 credential lifecycle class"（plan 已在 §10.3 中说"统一调用该 script 的模块级私有 atomic text helper"，但 §2.2 和 §4.4 的 "保留" 措辞仍然不准确）。无需 controller 重新裁决，因为 atomic write for diagnostic artifacts 是安全最佳实践且不涉及 credential lifecycle。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

---

### R02-PR-F03 — 未修复 — 中 — proxy 实际选择检测缺少具体实现方案

- **位置**: §4.3 "allow_environment_proxy=true 且 proof=false" 段、§9.2 "proxy active detection" 段
- **问题类型**: 不可直接实施
- **当前写法**: §9.2 声称 "proxy active detection必须来自 `requests` 对当前 URL/environment的实际 selection，不根据环境变量是否存在就误报。warning只说明'本 attempt 使用环境 proxy，numeric peer proof 未启用'；字段不得包含完整 URL、query、proxy URI/userinfo、headers、cookies、storage path。"
- **反例/失败场景**: `requests` 库没有公开 API 返回 "本次请求实际使用了哪个 proxy" 的信息。`Session.trust_env=True` 时，`requests` 会调用 `get_environ_proxies()` 并在 `urllib3` 层应用 proxy，但这个过程不暴露到 Python 层。实现方案有几种：
  1. 检查 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 环境变量是否存在——但这被 plan 明确禁止（"不根据环境变量是否存在就误报"）。
  2. 检查 `session.proxies` dict——但 `trust_env=True` 时不设置 `session.proxies`，proxy 由 `urllib3` 内部从环境读取。
  3. 在 `_send_authorized_request` 中创建 per-call session 时显式设置 `proxies` dict 从环境读取，然后检查它——但这改变了当前的 proxy 注入路径。
  4. 使用 `urllib3.util.url.parse_url` 和 `proxy_manager_for` 的内部状态——但这是访问私有 API。
  - 如果实现 Agent 无法可靠检测 proxy 是否实际生效，warning 机制可能不准确，或需要依赖环境变量检测（被 plan 禁止）。
- **为什么有问题**: plan 对 proxy detection 提出了精确的语义要求（"实际 selection"而非"环境变量存在"），但没有给出可实现的检测方法。这迫使实施 Agent 自行设计检测策略，可能违反 plan 的禁止条款。
- **直接证据**: `web_http_session.py:_send_authorized_request`（当前使用 `proxies={}` 强制禁 proxy）；plan §9.2 要求 "detection必须来自 requests 对当前 URL/environment 的实际 selection"；`requests` 库没有 `session.proxy_was_used_for(url)` API。
- **影响**: 实施 Agent 可能 (a) 使用环境变量检测（违反 plan），(b) 使用 `urllib3` 私有 API（脆弱），或 (c) 无法实现准确的 proxy detection（warning 不可靠）。
- **建议改法和验证点**: 明确 implementation 时的具体检测策略。建议：当 `trust_env=True` 时，通过 `urllib3.util.request.proxy_from_environment()` 或 `urllib3.get_environ_proxies(url)` 获取当前 URL 的 proxy 列表（这些是 urllib3 公开 API），检查是否有非空 proxy result。这比检查环境变量更精确，因为 `NO_PROXY` 排除规则会被应用。如果这些 API 也不可用，plan 应接受环境变量检测加 `NO_PROXY` 排除作为可行近似，或明确 proxy warning 是 best-effort 而非 deterministically 证明。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

---

### R02-PR-F04 — 未修复 — 低 — default warmup_body_bytes 值变更缺少直接证据

- **位置**: §4.1 packaged config、§4.2 `BrowserResourceBudget` 默认
- **问题类型**: 动机不完全成立
- **当前写法**: §4.1 packaged config 指定 `warmup_body_bytes: 1048576`（1 MiB）。当前代码 `WebResourceBudget` 默认 `warmup_body_bytes = 64 * 1024`（64 KiB）。这是一个 16 倍的放大。
- **反例/失败场景**: §11.1 的 evidence table 列举了三条直接证据，但没有一条明确证明 64 KiB warmup 不足。SEC AAPL HTML fixture 的 evidence 证明了 DOM/text 预算不足（旧 5M DOM default 触发 `browser_dom_too_large`），但这与 warmup 是不同字段。warmup 是 HTTP fetch 的第一个小 body 探测（content-type probe），不需要下载整个页面。1 MiB warmup 对于 content-type 探测是否必要？当前 64 KiB 限制没有已知的失败案例。
- **为什么有问题**: plan 声称"若没有直接证据证明某值不足，保留 umbrella initial value"（§11.2 裁决规则）。但 warmup 从 64 KiB 放大到 1 MiB 没有直接不足证据。这违反了 plan 自己的裁决规则。
- **直接证据**: `web_resource_budget.py` line 24: `warmup_body_bytes: int = 64 * 1024`；§4.1 packaged config: `warmup_body_bytes: 1048576`；§11.1 evidence table 无 warmup 不足证据。
- **影响**: 如果 64 KiB warmup 在真实场景中确实不足，pre-S1 数值裁决 gate 会发现并修正。但如果 gate 被跳过或不完整（见 F01），这个无证据的放大会进入生产代码。
- **建议改法和验证点**: 在 §11.2 pre-S1 matrix 中明确包含 warmup body bytes 的 observed maximum 记录。如果证据支持 1 MiB，保留之；如果没有直接证据，按 plan 自己的裁决规则恢复为 64 KiB（或 umbrella 初值）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

### R02-PR-F05 — 未修复 — 低 — `test_config_loader.py` allowlist 边界精确但测试改写范围未展开

- **位置**: §6.2 tests/docs 闭集、§8.3 S1 owner tests
- **问题类型**: 测试缺口
- **当前写法**: plan-entry adjudication 精确授权 `tests/runtime/test_config_loader.py`，边界为"只更新 packaged Web 五个独立 bool 与三组 resource budget projection 的精确断言；不得改其它 ConfigLoader 行为"。§8.3 列出"S1 owner tests"包括 "config-loader packaged snapshot 更新为 accepted default，而不是跳过旧断言"。
- **反例/失败场景**: 当前 `test_config_loader.py:test_default_runtime_config_files_load_as_typed_views`（line 460-476）断言 `allow_private_network_url is False`。R02 改为默认 `true` 后，这个断言必须更新。但当前测试没有断言 `allow_custom_port_url`、`dns_peer_proof_enabled`、`allow_environment_proxy`、`browser_enabled` 中的任何一个（因为它们当前不存在于 config 中）。plan 要求新增这些断言，但没有给出它们的精确 expected values。§4.1 的 packaged config 指定了默认值，但 §8.3 的 test 描述只说 "packaged Web 五个独立 bool 与三组 resource budget projection 精确断言"，没有列出具体的 expected values。
- **为什么有问题**: 实施 Agent 需要知道精确的 expected values 来写断言。虽然 §4.1 给出了 packaged config，但 test_config_loader 的断言方式是 `web_provider.config["key"] == value`，需要逐字段写出。这不是 blocker，但增加实施 Agent 的推导负担。
- **直接证据**: `tests/runtime/test_config_loader.py` line 471: `assert web_provider.config["allow_private_network_url"] is False`；§4.1 packaged config 列出五个 bool 的默认值。
- **影响**: 低。实施 Agent 可以从 §4.1 packaged config 推导 expected values，但最好在 §8.3 中显式列出。
- **建议改法和验证点**: 在 §8.3 中列出 `test_config_loader.py` 的精确 expected 断言值（如 `allow_private_network_url is True`、`allow_custom_port_url is True` 等），减少实施推导空间。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

### R02-PR-F06 — 未修复 — 低 — S2 HTTP transport policy 设计缺少 `WebHttpTransportPolicy` 数据流细节

- **位置**: §8.2 item 5、§9.2
- **问题类型**: 切片过粗
- **当前写法**: §8.2 item 5 声称 "新增最小 frozen `WebHttpTransportPolicy(dns_peer_proof_enabled, allow_environment_proxy)`；不在此定义部署默认数值"。§9.2 描述了四种 transport 组合的 flow。但没有说明 `WebHttpTransportPolicy` 如何从 `WebToolsConfig` 传递到 `_send_authorized_request`。
- **反例/失败场景**: 当前 `_send_authorized_request` 不接收 transport policy 参数。`_TargetBoundHTTPAdapter` 无条件使用 pinned connection pool 并拒绝 proxy。要实现 §9.2 的四种组合，需要修改 `_send_authorized_request` 的签名和 `_TargetBoundHTTPAdapter` 的行为。但 plan 没有说明这个修改在哪个 slice 发生（S1 定义 policy 类型，S2 实施分支行为），也没有说明 `_send_authorized_request` 签名变化如何影响所有调用点。
- **为什么有问题**: 实施 Agent 需要自行决定 transport policy 的传递路径。如果在 S1 定义类型但不在 S1 传递它，S1 的 typed snapshot 不完整；如果在 S1 就传递，S1 会涉及 S2 的 transport 行为变更。
- **直接证据**: `web_http_session.py:_send_authorized_request` 签名只有 `source_session, target, method, timeout, headers, stream`；§8.2 item 5 定义 `WebHttpTransportPolicy` 但没有说明它如何注入到 HTTP 发送路径。
- **影响**: 低。实施 Agent 可以自行设计传递路径（最自然的方式是给 `_send_authorized_request` 增加 `transport_policy` 参数），但 plan 的 slice 边界可能导致 S1 和 S2 之间的接口不清晰。
- **建议改法和验证点**: 在 §9.2 或 §8.2 中明确 `_send_authorized_request` 的签名变化和调用点迁移策略，以及 S1 和 S2 之间的接口契约。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## 3. Open Questions

### OQ-1: browser proof-on fail-close 的具体实现边界

plan §4.3 声称 "proof=true 时，若 browser backend 无法提供等价 numeric peer proof，browser path typed fail closed；不得把 browser 当 proof bypass。" 但当前 Playwright 浏览器没有内置 API 来验证 socket 级别的 peer address。`_connect_to_approved_addresses` 在 `web_http_session.py` 中通过 `socket.getpeername` 实现——但 Playwright 不暴露底层 socket。实施 Agent 需要决定：(a) 当 proof=true 时完全禁止 browser path（最安全但功能退化），(b) 在 route handler 中用 egress policy 检查替代 numeric peer proof（已有），或 (c) 某种 Playwright CDP 级别的 network interception。plan 没有明确哪个方案是可接受的。

### OQ-2: `WebResourceBudgets` aggregate 类型的行为

§4.2 定义 `WebResourceBudgets(http, browser, diagnostics)` 作为 "config snapshot 组合，不添加跨 owner rule、flattened property、validator facade 或第二组 defaults"。但 plan 没有说明这个 aggregate 类型是否需要 `__post_init__` 验证（如验证每个子 budget 的字段范围），或者它是否只是一个纯 tuple-like 容器。如果它不验证，某个子 budget 的构造错误会延迟到消费时才暴露。

---

## 4. Residual Risks

| residual | 当前处理 | owner / destination |
|---|---|---|
| credential storage-state refresh/retention/concurrent publish/cleanup | R02 删除提前实现，只保留 read input | Issue #178 |
| live 网站 DOM/event/error 规模变化 | initial values 由 pre-S1 真实矩阵裁决 | Web config owner |
| proxy 下无法证明 origin peer | proof+active proxy typed fail closed | Web HTTP transport/config owner |
| Playwright 无法提供 numeric peer proof | proof-on browser typed fail closed | browser backend owner |
| external provider/challenge 波动 | local deterministic hard gate + external 补充 | Web diagnostics/smoke owner |
| unified authorization 愿景 | R02 明确不设计、不预埋 | Topic 9 future controller decision |

---

## 5. Summary of Accepted-Scope Blockers vs Suggestions vs Open Questions

| Category | Count | IDs |
|---|---|---|
| Accepted-scope blocker | 0 | — |
| Suggestion (中 severity) | 3 | F01, F02, F03 |
| Suggestion (低 severity) | 3 | F04, F05, F06 |
| Open Question | 2 | OQ-1, OQ-2 |

**No accepted-scope blocker found.** All findings are implementation-level clarifications or accuracy improvements that can be addressed during plan fix without controller re-adjudication of accepted design decisions.

---

## 6. Final Verdict

**`pass-with-risks`**

The plan is structurally sound: motivation is direct and controller-adjudicated, root cause is evidence-based and same-source, owner assignments are unique, slice sequencing forms complete terminal states per slice, allowlist boundaries are precise, and the non-goals (unified framework, Issue 178, R03) are clearly excluded. The six findings are implementation-level issues that an AgentCodex plan fix can address without reopening accepted design decisions:

1. **F01** (中): pre-S1 gate 命令依赖未实现的 CLI 参数——需要将参数实现提前到 pre-S1 步骤，或改用现有 fixture server。
2. **F02** (中): 普通 diagnostic artifact 原子写被误述为"已有可保留"——需要修正 plan 文本措辞。
3. **F03** (中): proxy 实际选择检测缺少具体实现方案——需要明确检测策略或接受近似。
4. **F04** (低): warmup_body_bytes 放大缺少直接证据——需要在 pre-S1 matrix 中记录。
5. **F05** (低): test_config_loader 断言值未展开——建议在 §8.3 列出精确 expected values。
6. **F06** (低): transport policy 数据流路径未明确——建议补充签名变化说明。

**Finding count**: 6 findings (0 blocker, 3 medium, 3 low) + 2 open questions.
