# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy — 第二路独立完整 Adversarial Plan Review

## 0. 审查身份与范围

- **审查类型**：第二路独立完整 adversarial plan review（非复述、非确认）。
- **审查目标**：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（下称 "plan"）。
- **Immutable target**：plan 本身与 controller adjudication `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`；不修改 target、产品、测试、README、control，不 commit。
- **审查姿势**：默认怀疑；寻找会导致 plan 失败、不可实施、违反约束或产生不可恢复行为的基于证据的理由。
- **证据优先级**：AGENTS.md 硬约束 > controller discussion Topic 2/Topic 9 > 五份 design truth > umbrella remediation plan 全局规则/R02 章节 > plan-entry controller adjudication > 三路原始 designtruth review（仅作代码证据；controller discussion 优先）> HEAD production code/tests。
- **审查方法**：对 plan 全文、所有引用的代码文件/符号/行号、design truth、umbrella baseline 与 controller adjudication 做交叉验证；独立挑战每个 claim；每个 finding 绑定直接文件/符号/行证据与 owner-bound fix。
- **输出 artifact**：本文（固定路径 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-ds.md`）。

## 1. 审查覆盖矩阵

| 维度 | 覆盖 |
|---|---|
| owner/source-of-truth 唯一性 | §2.1, §4, §6 全文 |
| 五 bool 与 budget local override parser | §4.1, §8.2 |
| `web_search_providers.py` transport 统一窄授权 | §6.1, §8.2.8, §9.4 |
| S1/S2/S3 依赖/终态 | §8–§10, §15.2 |
| 普通 diagnostic atomic writer 产品裁决 | §2.2, §4.4, §10.3 |
| pre-S1 数值 gate 与 S3 CLI 循环依赖 | §11, §13 |
| proxy selection/warning/proof conflict | §4.3, §9.2 |
| standard transport 与 redirect | §4.3, §9.2 |
| browser/private 解耦 proof fail-close | §4.3, §9.3 |
| storage lifecycle 删除与 explicit read input/Issue 178 边界 | §4.4, §5.1, §10 |
| diagnostic CLI private flag 删除 | §4.4, §10.3 |
| tests/coverage/pyright/README/source scans 可执行性 | §8.4, §9.6, §10.4, §13, §14 |
| retained security、no unified authorization、no deferred Issue/no R03 | §5.2, §5.3, §16 |

## 2. 已测试的 Plan Assumptions

| # | assumption | 验证结果 |
|---|---|---|
| A1 | "ordinary diagnostic artifact 当前非原子写" (§2.2) | **成立**。`utils/diagnose_web_access.py:2765` 直接 `path.write_text(...)`；`smoke_web_ci.py` 同样直接写。 |
| A2 | packaged `allow_private_network_url` 当前为 `false` (§2.3) | **成立**。`dayu/config/tool_discovery.json:78` 确认为 `false`。 |
| A3 | `web_search_providers.py` 直接 import/消费 `WebResourceBudget` (§6.4) | **成立**。`web_search_providers.py:22` 直接 import `WebResourceBudget`；signatures 中 `resource_budget: WebResourceBudget` 贯穿 Tavily/Serper/DuckDuckGo 三条路径。 |
| A4 | browser 被 `allows_private_network` 前置禁用 (§2.2) | **成立**。`web_playwright_backend.py:1387-1392` 检查 `egress_policy.allows_private_network` 并在 false 时返回 `browser_egress_policy_unavailable`。 |
| A5 | `WebResourceBudget` 是七字段 complete-object (§2.2) | **成立**。`web_resource_budget.py:18-44` 定义七字段 frozen dataclass；`web_resource_budget_from_json:88-139` 要求 complete object，缺失/未知字段均 reject。 |
| A6 | test_config_loader 断言 `allow_private_network_url is False` (§6.4) | **成立**。`tests/runtime/test_config_loader.py:471` 在 `test_default_runtime_config_files_load_as_typed_views` 中断言 `is False`。 |
| A7 | S1→S2→S3 严格串行依赖无漂移 (§3.2) | **成立**。config→transport→diagnostics 的 owner 依赖链在 HEAD 与 plan 间一致。 |
| A8 | controller discussion Topic 2/Topic 9 已最终裁决产品方向 (§1.1) | **成立**。controller discussion 记录完整裁决链，无未决产品问题。 |
| A9 | 当前 `_write_json` 与 `_write_jsonl` 使用直接 `Path.write_text` 非原子 | **成立**。`utils/diagnose_web_access.py:2765,2786` 均直接 `path.write_text(...)`。 |
| A10 | plan-time HEAD `02fcc5d8` 在 R02 Web production/test/README 路径上无 diff (§3.1) | **成立**。`git diff --name-only b1a0631f..02fcc5d8` 不触及 dayu/tools/web/ 或 tests/tools/web/。 |

## 3. Findings

### R02-DS-F01 — 严重 — pre-S1 数值裁决 gate 对 S3 smoke 修改形成循环依赖

- **位置**: plan §11.2.1, §13.1
- **问题类型**: 切片过粗 / 不可直接实施 / 状态机漏洞
- **当前写法**: §11.2.1 要求在 "S1 coding 前" 运行版本化矩阵，使用 `smoke_web_ci.py` 的 `--filing-fixture` 参数："实现时给smoke增加显式`--filing-fixture`参数，默认值就是该版本化路径"。§13.1 的 suggested command 同样使用 `--filing-fixture`。
- **反例/失败场景**: `smoke_web_ci.py` 的修改在 S3 (§10.3.2) 才执行。`--filing-fixture` 参数在 HEAD 不存在（`smoke_web_ci.py` 当前无此 CLI 参数）。若 pre-S1 gate 严格需要该参数，则必须等 S3 完成——但 S3 依赖于 S1 和 S2 先完成。形成 `pre-S1 → needs smoke change → S3 → depends on S1 → S1 blocked on pre-S1` 的死锁。
- **为什么有问题**: 违反 plan 自身声明的 "S1 accepted commit前不得进入 S2，S2 accepted commit前不得进入 S3" (§8.1) 不变量。若实施 agent 按字面执行 plan，在 S1 前无法运行完整矩阵；若跳过矩阵进入 S1，则违反 §15.3 stop condition "数值矩阵证明ceiling不足但controller尚未裁决具体config值"。
- **直接证据**:
  - plan §11.2.1: "在 S1 coding 前，以 proposed config的单一 typed snapshot运行版本化/可复现矩阵"
  - plan §11.2.1: "实现时给smoke增加显式`--filing-fixture`参数"
  - plan §10.3.2: smoke_web_ci.py 修改在 S3 slice
  - plan §8.1: "S1 accepted commit前不得进入 S2"
  - HEAD: `utils/smoke_web_ci.py` 不存在 `--filing-fixture` 参数
- **影响**: 实施 Agent 要么绕过数值 gate（弱化预算证据），要么在 S1 前修改 S3 文件（违反 slice 边界），要么无限等待无法执行的 gate。
- **建议改法和验证点**:
  1. 将 pre-S1 数值裁决矩阵拆为两个阶段：(a) pre-S1 阶段只使用当前 smoke 已有能力（`--external-limit 0 --include-playwright`）对已有 fixture 运行，如 plan §11.1 已部分执行的 evidence；(b) `--filing-fixture` 参数和完整矩阵作为 S3 smoke 验证的一部分，不作为 pre-S1 blocker。
  2. 或者将 `--filing-fixture` 参数的添加从 S3 提升为 pre-S1 独立 micro-slice（只加参数和路径 resolve/containment 校验，不加 atomic writer 或 lifecycle 删除），并明确该 micro-slice 不改变 S3 的 allowlist 边界。
  3. 验证点：pre-S1 gate 的命令必须能在当前 HEAD smoke 上直接执行（或只依赖 pre-S1 micro-slice），不得要求 S3 的 atomic writer/lifecycle 删除先完成。
- **修复风险**: 低（只改 plan 的 gate sequencing 文字，不改变 contract）
- **严重程度**: 严重（阻塞 S1 entry）

---

### R02-DS-F02 — 高 — 普通 diagnostic atomic writer 未经产品裁决，scope 边界模糊

- **位置**: plan §2.2 证据表 "ordinary diagnostic write" 行, §4.4 "ordinary JSON/JSONL/markdown diagnostic/smoke artifact" 段, §10.3.1
- **问题类型**: 契约缺失 / 范围漂移
- **当前写法**: plan §2.2 断言 HEAD 当前 diagnostic/smoke 输出使用直接 `Path.write_text`（非原子），并计划在 S3 为每个 script 新增 "owner-local atomic writer"（`临时文件、flush/fsync、os.replace`）。Controller adjudication §4 明确写："本裁决不接受计划中的任何其它范围扩展，也不裁决 ordinary diagnostic artifact 原子写".
- **反例/失败场景**: umbrella remediation plan §9.2（R02 umbrella baseline）写的是 "普通 diagnostic artifact 的既有原子写可保留"——隐含假设 HEAD 已有原子写。但 plan 自己的证据表证明 HEAD 没有。这构成 umbrella baseline 与 HEAD 的事实矛盾。R02 plan 选择"新增原子写"来修正这个矛盾，但 (1) controller 明确未裁决此事，(2) umbrella baseline 的表述可被解读为"如果有就保留，没有就不新增"，(3) 新增原子 writer 是否为"产品行为变更"没有产品裁决。
- **为什么有问题**: 原子写是正确性改进，但它引入了新的文件系统行为语义（临时文件创建、fsync、os.replace 的跨文件系统限制、失败回滚策略）。plan 说 "失败删除临时文件，不删除或回滚既有 final"，但未定义临时文件的命名约定、与 final 的同目录约束、以及 ENOSPC/权限错误的 fail 行为。这些细节如果在 S3 implementation 时由 agent 自行决定，可能引入未预期的行为变更。
- **直接证据**:
  - umbrella plan `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §9.2: "普通 diagnostic artifact 的既有原子写可保留"
  - R02 plan §2.2: "当前 JSON/JSONL/summary 非原子"
  - R02 plan §4.4: "使用同目录临时文件、flush/fsync、`os.replace` 的原子写"
  - controller adjudication §4: "不裁决 ordinary diagnostic artifact 原子写"
  - HEAD: `utils/diagnose_web_access.py:2765` — `path.write_text(...)` 直接写
- **影响**: 实施 Agent 可能自行设计原子 writer 的细节（临时文件命名、错误语义），而这些细节应是 product owner 的决策。若未来 Issue #178 引入正式的 credential atomic publish，可能与 R02 的普通 artifact 原子 writer 产生两份不一致的原子写实现。
- **建议改法和验证点**:
  1. 在 plan §4.4 中明确原子 writer 的最小 contract：临时文件命名规则（如 `<final>.tmp.<uuid>`）、与 final 同目录约束、fsync 策略（data only 还是 data+metadata）、replace 失败后的恢复策略（保留临时文件供 manual recovery 还是删除）。
  2. 显式声明该原子 writer 不是 credential lifecycle，不与 Issue #178 的 future storage-state atomic publish 共享实现或 contract。
  3. 在 plan §10.3.1 中增加约束：原子 writer 只用于普通 JSON/JSONL/markdown artifact；不得被 `_StorageStateLifecycle` 的删除残留或未来 Issue #178 实现复用。
- **修复风险**: 低（plan 文字细化，不改变 implementation 的 allowlist 边界）
- **严重程度**: 高（scope 边界不清，可能导致 implementation agent 自行设计产品行为）

---

### R02-DS-F03 — 高 — `web_search_providers.py` transport 统一对固定 API endpoint 过度应用 egress policy

- **位置**: plan §6.1, §8.2.8, §9.4
- **问题类型**: 过度耦合 / 架构边界
- **当前写法**: plan §8.2.8: "S2再把三个模块级`requests.get/post`调用迁到`web_http_session.py`的同一typed attempt sender，使proxy-disable/proof/sanitized-warning对search与fetch同源"。plan-entry adjudication 授权 S2 "只复用同一Web HTTP transport policy。不得改变provider选择、业务结果、credential读取、query/domain语义".
- **反例/失败场景**: 当前 search providers 连接固定 public API endpoints（`api.tavily.com`、`google.serper.dev`、`duckduckgo.com`），使用 `allow_redirects=False`，不跟随 redirect。若 S2 transport 统一意味着对 search provider 的每个请求也调用 `WebEgressPolicy.authorize_http_target()` 做 DNS resolution + address classification，则：
  1. Tavily/Serper API endpoint 的 DNS 可能返回与用户 fetch 目标完全无关的地址集合；
  2. 若 Tavily/Serper 的 DNS 恰包含一个被 egress policy 拒绝的地址（如 mixed DNS 中含 private address 且 `allow_private_network_url=false`），search 将因与 search 业务无关的 DNS 事实而整体失败；
  3. search provider 固定 endpoint 不需要 per-hop redirect recheck（`allow_redirects=False`），强制对其做 egress authorization 增加了无业务价值的失败面。
- **为什么有问题**: controller adjudication 授权的是 "复用同一Web HTTP transport policy"，不是 "复用同一 Web egress policy"。Transport policy（proxy、peer-proof、trust_env）与 egress policy（address classification、custom port、redirect recheck）是不同的 owner。plan 当前文字将两者混称为 "transport"，可能导致 implementation agent 对 search provider 的固定 API endpoint 也执行不必要的 DNS/address/redirect 检查，超出 adjudication 授权的 "不得改变 provider 选择、业务结果" 边界。
- **直接证据**:
  - `web_search_providers.py:654-665` (Tavily): `requests.post("https://api.tavily.com/search", ..., allow_redirects=False)`
  - `web_search_providers.py:739-754` (Serper): `requests.post("https://google.serper.dev/search", ..., allow_redirects=False)`
  - `web_search_providers.py:816-830` (DuckDuckGo): `requests.get("https://duckduckgo.com/html/", ..., allow_redirects=False)`
  - plan §8.2.8: "使proxy-disable/proof/sanitized-warning对search与fetch同源"
  - plan-entry adjudication §2: "S2 只让实际请求复用 Web HTTP transport owner 的 proxy/peer-proof/egress 决定与脱敏 warning"
- **影响**: search provider 因与 search 业务无关的 DNS egress 事实而误失败；违反 adjudication "不得改变 provider 选择、业务结果" 约束。
- **建议改法和验证点**:
  1. 在 plan §9.4 中明确区分：search provider 的 S2 transport 统一只复用 (a) `HttpResourceBudget`（已在 S1 完成），(b) proxy 选择与脱敏 warning，(c) peer-proof 约束。不强制对固定 API endpoint 做 DNS resolution 或 address classification。
  2. 或者明确：search provider 也走完整的 `authorize_http_target`，但如果 endpoint hostname 在 packaged config 或 typed constant 中注册为 known-safe（如 `api.tavily.com`），则跳过 address-level check。
  3. 验证点：S2 后 Tavily/Serper API endpoint 请求不使用 `_PinnedHTTPConnection`（除非 peer-proof 显式开启），不受 `allow_private_network_url=false` 影响，且 search 业务结果与 S2 前一致。
- **修复风险**: 中（需要精确区分 transport policy 和 egress policy 在 search path 上的应用边界）
- **严重程度**: 高（可能违反 controller adjudication 授权边界）

---

### R02-DS-F04 — 高 — Browser proof fail-close contract 未指定错误类型与 pre-flight 可检测性

- **位置**: plan §4.3, §9.3
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: plan §4.3: "proof=true 时，若 browser backend 无法提供等价 numeric peer proof，browser path typed fail closed；不得把 browser 当 proof bypass"。§9.3: "proof-on unsupported => typed fail closed"。
- **反例/失败场景**: Browser 使用 Playwright/Chromium 的网络栈，不经过 Python `requests`/`urllib3`，因此从根本上无法复用 `_PinnedHTTPConnection` 的 peer verification。Plan 承认这一点并以 "typed fail closed" 处理。但 plan 未指定：
  1. fail closed 发生在哪个阶段——是 `WebToolsConfig` 构造时（pre-flight detection）、browser 尝试前（early gate）、还是 browser 已启动后（late detection）？
  2. typed fail 使用什么错误类型——现有 `WebEgressPolicyError` 的子类？新的 browser-specific error？还是现有的 `browser_egress_policy_unavailable`（该字符串当前表示 private-network 拒绝，语义不同）？
  3. 若 proof-on 且 browser 被 typed fail closed，HTTP fallback 仍可用吗？（plan §9.3 的流程图显示 browser 在 "HTTP terminal/challenge" 之后，所以 HTTP 已尝试过——此时 browser typed fail 意味着整体请求失败，没有 fallback。）
- **为什么有问题**: 错误类型和检测时机的缺失意味着 implementation agent 必须自行设计这些细节，可能产生与其他 plan contract 不一致的错误语义。特别是 "typed fail closed" 的错误消息若进入 LLM-facing 文本（作为 `web_fetch` tool 的 error outcome），需要满足 AGENTS.md LLM-facing 约束。
- **直接证据**:
  - plan §4.3: "proof=true 时，若 browser backend 无法提供等价 numeric peer proof，browser path typed fail closed"
  - plan §9.3 flowchart: "proof-on unsupported => typed fail closed"
  - `web_playwright_backend.py:1387-1392`: 当前 "browser_egress_policy_unavailable" 语义是 private-network denial，不是 proof incompatibility
  - AGENTS.md §LLM-facing 文本约束: "只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"
- **影响**: Implementation agent 自行发明错误类型和检测时机，可能与其他 error contract 不一致或违反 LLM-facing 约束。
- **建议改法和验证点**:
  1. 在 plan §9.3 中明确 browser proof fail-closed 的错误类型（建议新增独立 typed reason，如 `browser_peer_proof_incompatible`，与现有 `browser_egress_policy_unavailable` 区分）。
  2. 明确检测时机：建议在 `browser_enabled=true` 且 `dns_peer_proof_enabled=true` 时，于 browser 尝试前 early fail（不启动 Playwright 进程），因为 browser 无法提供 peer proof 是结构性事实而非运行时条件。
  3. 验证点：proof-on + browser enabled 的组合在 config validation 或 tool call 早期即 typed fail，不启动 Playwright process；错误文本不暴露内部模块名/实现术语给 LLM。
- **修复风险**: 低（plan 文字补充，implementation 按补充后的 contract 执行）
- **严重程度**: 高（缺失的关键设计决策，implementation agent 无法从 plan 直接推导）

---

### R02-DS-F05 — 中 — 五 bool 与 budget group 的 "local override" 语义与 ConfigLoader 的 record-replace 语义存在张力

- **位置**: plan §4.1, §8.2.3
- **问题类型**: 架构边界 / 不可直接实施
- **当前写法**: plan §4.1: "`resource_budget` 整体缺失、任一 owner group 缺失或任一 group field 缺失时，只对缺失部分使用对应 typed default；已有 sibling 值不得被重置"。§4.1: "一次 discovery 产生 immutable `WebToolsConfig` snapshot；同一 tool attempt 不重新读取 JSON/environment 配置"。
- **反例/失败场景**: ConfigLoader 的当前语义是整条 provider record 替换（`test_config_loader.py:608` 的 `test_workspace_record_replaces_package_record_without_deep_merge` 证明这是既有行为）。若 plan 的 "local override" 语义要求 ConfigLoader 对 `resource_budget` 内部做 deep merge（group-level 和 field-level），则这与 ConfigLoader 的 record-level replace 语义矛盾。Plan 将此职责分配给 `provider._parse_config`（"是唯一 raw JSON parser owner"），但 `_parse_config` 只看到 ConfigLoader 已经完成 merge 的最终 record——它无法区分 "用户显式覆盖了 http.wire_body_bytes" 和 "用户未提供 resource_budget 整体"。
- **为什么有问题**: "local override" 需要一个明确的 merge 语义 owner。如果 ConfigLoader 做整 record replace，则 `_parse_config` 收到的是已替换后的完整对象（或缺失对象）。如果 workspace config 只写了 `{"resource_budget": {"http": {"wire_body_bytes": 999}}}` 而没有写 browser/diagnostics group，ConfigLoader 的 replace 语义可能导致 browser/diagnostics group 被整体删除——此时 `_parse_config` 只能看到缺失，无法区分是 "用户想保留默认" 还是 "用户想删除 browser budget"。
- **直接证据**:
  - plan §4.1: "只对缺失部分使用对应 typed default；已有 sibling 值不得被重置"
  - `tests/runtime/test_config_loader.py:608`: `test_workspace_record_replaces_package_record_without_deep_merge` — 证明 ConfigLoader 语义是整 record replace
  - `dayu/tools/web/provider.py`: `_parse_config` 接收 provider config dict
- **影响**: 若 ConfigLoader 语义不做相应修改，用户部分覆盖 budget group 时可能意外丢失其他 group 的配置——与 plan 的 "已有 sibling 值不得被重置" 矛盾。
- **建议改法和验证点**:
  1. 在 plan §4.1 中明确：五个 bool 的覆盖使用 ConfigLoader 现有 record-replace 语义（字段缺则用 typed default）；`resource_budget` 内部的 group/field local override 由 `provider._parse_config` 在收到完整或部分 config dict 后执行 deep merge——具体策略在 plan 中写明（如：以 packaged default 为 base，用 config 提供的值 shallow-merge 到 group level，field level 也是 shallow-merge）。
  2. 在 test contract 中增加：workspace config 只覆盖 `resource_budget.http.wire_body_bytes` 时，browser/diagnostics group 仍保持 packaged defaults。
  3. 验证点：五个 bool 的覆盖与现有 ConfigLoader 行为一致；budget group/field 的 partial override 不改变其他 group/field 的值。
- **修复风险**: 低（plan 文字澄清，implementation 按澄清后的 contract 实现 `_parse_config` 的 merge 逻辑——该 merge 逻辑是 `_parse_config` 内部的实现细节，不影响 ConfigLoader）
- **严重程度**: 中（可能导致 implementation agent 做出与 plan 意图不一致的 merge 策略）

---

### R02-DS-F06 — 中 — diagnostic CLI `--allow-private-network-url` 删除可能使现有 smoke/diagnostic 工作流静默改变行为

- **位置**: plan §4.4, §10.3.1
- **问题类型**: 契约缺失 / open question 未收敛
- **当前写法**: plan §4.4: "删除 CLI `--allow-private-network-url` 及 `CliOptions.allow_private_network_url`：accepted packaged default已经allow，保留它会成为无效兼容开关"。§10.3.1: "诊断默认直接消费packaged private=true，显式deny测试通过smoke的typed provider overlay进入唯一parser"。
- **反例/失败场景**: 当前 `--allow-private-network-url` 的行为是将 CLI flag 值覆盖到 Web provider config（作为 overlay），使单次 diagnostic run 可以使用与 packaged default 不同的 private network policy。删除该 flag 后：
  1. 现有使用 `--allow-private-network-url=false` 的 diagnostic 脚本（如果有）将静默改变行为——从显式 deny private 变为使用 packaged default（plan 改后为 `true`）；
  2. §13.1 的 deterministic local hard gate 需要验证 "显式 private deny"——但删除 CLI flag 后，diagnostic 脚本无法从 CLI 表达 "private deny"。Plan 说 "显式deny测试通过smoke的typed provider overlay进入唯一parser"，但 smoke overlay 是 `smoke_web_ci.py` 内部的测试机制，不是 `diagnose_web_access.py` 的 CLI。
  3. 这造成 diagnostic CLI 和 smoke 之间的非对称：smoke 可以通过 overlay 测试 private deny，但 diagnostic CLI 用户无法再从命令行选择 private deny。
- **为什么有问题**: plan 说 flag 是 "无效兼容开关"，但它当前提供了 diagnostic 用户独立于 packaged default 选择 private policy 的能力。删除它以 "packaged default 已经 allow" 为由，混淆了 "部署默认" 和 "单次 diagnostic run 的策略选择" 两个不同概念。虽然 plan 的设计意图是 "配置只有一个 parser owner"，但 diagnostic CLI 的 overlay 本就是对 parser 的正常输入——删除 overlay 不等于修复了 "第二 parser"，而是删除了一个合法的单次覆盖入口。
- **直接证据**:
  - plan §4.4: "删除 CLI `--allow-private-network-url`"
  - plan §10.3.1: "诊断默认直接消费packaged private=true，显式deny测试通过smoke的typed provider overlay进入唯一parser"
  - HEAD `utils/diagnose_web_access.py`: 当前存在 `--allow-private-network-url` CLI flag
- **影响**: diagnostic CLI 用户失去单次 private policy 覆盖能力；smoke 和 diagnostic 对 "private deny" 的测试路径不对称；若有人依赖 `--allow-private-network-url=false` 做安全敏感的诊断，行为将静默改变。
- **建议改法和验证点**:
  1. 明确 diagnostic CLI 的 `--allow-private-network-url` flag 的删除是否属于 plan §5.1 "必须删除" 列表中的 "compatibility code"。如果不是（即该 flag 有独立产品语义），应保留但改为透传到 `WebEgressPolicy` 的 `allow_private_network` 字段，不加第二套 parser。
  2. 若确实删除，在 plan §10.3.1 中增加说明：删除后用户如何用单次 diagnostic run 验证 private deny（例如通过 workspace config overlay 文件或 smoke 替代）。
- **修复风险**: 低（只影响 diagnostic CLI 的用户界面，不影响 production Web tool path）
- **严重程度**: 中

---

### R02-DS-F07 — 中 — S1 coverage 包含 `web_search_providers.py` 但 search provider 测试依赖外部 API key，覆盖率可能无法达到 80%

- **位置**: plan §8.4, §14.1
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: plan §14.1 S1 候选 coverage 文件列表包含 `web_search_providers.py`（plan-entry adjudication 精确授权），要求 "逐文件 `>=80%`"。
- **反例/失败场景**: `web_search_providers.py` 的 Tavily 和 Serper 路径依赖环境变量 `TAVILY_API_KEY` / `SERPER_API_KEY`。在 CI 或无 API key 的环境中，这些路径只能通过 monkeypatch/mock 覆盖——但 mock 覆盖的代码行可能不足以达到 80%。DuckDuckGo 路径不依赖 API key，但其 HTML 解析（`_parse_duckduckgo_html`）需要真实 HTML 响应或精心构造的 fixture。当前 `tests/tools/web/test_web_tools_provider.py` 中 search 相关测试可能依赖 external fixture 或 skip。
- **为什么有问题**: plan 要求 coverage 逐文件 `>=80%`，但 `web_search_providers.py` 的 Tavily/Serper 路径（`_search_with_tavily`、`_search_with_serper`）各约 40-50 行核心逻辑，若因缺少 API key 而无法通过真实调用覆盖，mock-based 测试可能不够充分。这可能导致 S1 无法通过 coverage gate，或因 coverage 不足而被迫在 S1 中追加测试——而 S1 的 scope 只授权 "把 budget 依赖收窄到 `HttpResourceBudget`"，不授权大量新增 search-specific 测试。
- **直接证据**:
  - plan §14.1: "S1候选：...plan-entry adjudication精确授权的`web_search_providers.py`"
  - `web_search_providers.py:639-641` (Tavily): `api_key = os.environ.get(TAVILY_API_KEY_ENV, "").strip()` — 需要真实 key
  - `web_search_providers.py:723-725` (Serper): 同上
  - plan-entry adjudication §2: "S1 只把 budget 依赖收窄到 `HttpResourceBudget`"
- **影响**: S1 coverage gate 可能因 search provider API key 依赖而无法通过；为通过 gate，implementation agent 可能新增超出 S1 授权的 search mock 测试。
- **建议改法和验证点**:
  1. 在 plan §14.1 中为 `web_search_providers.py` 增加 coverage 例外说明：S1 只要求该文件中被实际修改的行（budget 类型引用替换）有测试覆盖；未修改的 Tavily/Serper/DuckDuckGo 请求逻辑不要求新增测试。
  2. 或明确 S1 中 `web_search_providers.py` 的 coverage 通过 import-boundary 和 type-change regression tests 即可满足，不要求 80% 行覆盖。
- **修复风险**: 低
- **严重程度**: 中（可能阻塞 S1 coverage gate）

---

### R02-DS-F08 — 中 — packaged budget initial values 的证据基础不足以证明对代表性财报站点普遍充分

- **位置**: plan §11.1, §11.2
- **问题类型**: 契约缺失 / open question 未收敛
- **当前写法**: plan §11.1 自身承认 "上述证据不足以证明 128/256 MiB、1 MiB warmup、8 Ki chars error、512 events 对代表性真实站点普遍足够"。§11.2 设置了 pre-S1 数值裁决 gate 来弥补这一不足。
- **反例/失败场景**: 若 pre-S1 gate 因 R02-DS-F01（循环依赖）无法按计划执行，则 S1 将以 "证据不足以证明充分" 的 initial values 进入 implementation。这意味着 128/256 MiB 可能对某些真实财报站点不足——特别是包含大量嵌入图片的 HTML 或大型 PDF（如某些港股 filing 可达数百 MB）。若 production 中触发 budget exceeded，LLM 将收到 `response_body_too_large` 错误而非财报内容，影响分析能力。
- **为什么有问题**: plan §11.2 的裁决规则说 "若没有直接证据证明某值不足，保留 umbrella initial value"。但 umbrella initial values 本身也是从旧值（25/50 MiB 等）外推而来，没有比 R02 plan 更强的证据基础。"证据不足时保留旧值" 的策略在这里等价于 "保留一个可能也不足的值"。plan 对 warmup_body_bytes (1 MiB)、diagnostic_error_chars (8 Ki)、diagnostic_events (512) 的初始值尤其缺乏证据——§11.1 的 smoke 数据太小（HTML 238B, PDF 652B），完全不能证明这些值在真实场景中充分。
- **直接证据**:
  - plan §11.1: "上述证据不足以证明 128/256 MiB、1 MiB warmup、8 Ki chars error、512 events 对代表性真实站点普遍足够"
  - plan §11.2 裁决规则: "若没有直接证据证明某值不足，保留 umbrella initial value；禁止凭偏好增大或缩小"
  - plan §4.1: packaged defaults 为 `warmup_body_bytes: 1048576` (1 MiB), `error_chars: 8192`, `events: 512`
- **影响**: Production 中 budget exceeded 可能导致 LLM 无法获取完整财报内容；runtime failure 虽 bounded（fail closed 而非 silent truncation），但对买方财报分析场景影响严重。
- **建议改法和验证点**:
  1. 在 §16 residual risks 中显式列出每个 initial value 的证据状态（充分/不充分/未知），并对证据不充分的值标注 "可能需要基于 production 观察调整"。
  2. 对 warmup/error/events 这三个最小且证据最弱的值，建议在 pre-S1 矩阵中至少用一个真实大财报 fixture（如大型港股 PDF filing）验证。
  3. 若 pre-S1 矩阵无法完整执行，明确将这些值的裁决推迟到 S3 的 real Playwright/diagnostic smoke 之后，并在 completion report 中记录最终 observed metrics 与 headroom。
- **修复风险**: 低（不影响 implementation 边界，只影响数值和 residual risk 记录）
- **严重程度**: 中

---

### R02-DS-F09 — 低 — `web_egress_policy.py` 的 `allow_custom_port` 拆分可能触及 `is_url_allowed` 的隐式 consumer

- **位置**: plan §4.3, §8.2.4
- **问题类型**: 架构边界
- **当前写法**: plan §4.3 将 `WebEgressPolicy` 的 private/custom-port 拆为独立字段。当前 `authorize_http_target:312-313` 中 custom port 拒绝与 `allow_private_network` 耦合。
- **反例/失败场景**: `WebEgressPolicy.is_url_allowed` (line 401-418) 是对外暴露的布尔投影，当前在 `web_search_providers.py:446-450` 的 `_filter_visible_results` 中作为 `is_safe_public_url` 回调使用。该回调的签名是 `(url: str, *, allow_private_network_url: bool = False) -> bool`。若 `WebEgressPolicy` 新增 `allow_custom_port` 独立字段，`is_url_allowed` 的内部逻辑会相应改变（不再因 `allow_private_network=false` 而拒绝 custom port）。但 `_filter_visible_results` 的调用方 `search_public_web` 接收的仍是 `allow_private_network_url: bool` 参数（line 267）——它不知道 `allow_custom_port_url` 的存在。这可能导致 search result URL filtering 对 custom port URL 的行为与 fetch 不一致。
- **为什么有问题**: `_filter_visible_results` 是 `WebEgressPolicy.is_url_allowed` 的消费者，它通过 `allow_private_network_url` 参数间接影响 policy 行为。但 plan 拆分了 private 和 custom-port 后，`is_url_allowed` 的行为取决于 `WebEgressPolicy` 实例的两个独立字段——而 `_filter_visible_results` 的调用方只传递了 `allow_private_network_url`，没有传递 `allow_custom_port_url`。如果 search provider 返回一个 `https://example.com:8443/something` 的结果 URL，其可见性将取决于 policy 实例的 `allow_custom_port` 字段——这个字段是 search 调用方从未显式控制的。
- **直接证据**:
  - `web_egress_policy.py:312-313`: 当前 custom port 拒绝与 `_allow_private_network` 耦合
  - `web_egress_policy.py:401-418`: `is_url_allowed` 使用相同的 policy 实例判断
  - `web_search_providers.py:267,446-450`: `allow_private_network_url` 参数传给 `_filter_visible_results` -> `is_safe_public_url`
  - plan §8.2.4: `WebEgressPolicy` 增加独立 `allow_custom_port`
- **影响**: S1 后 search result URL filtering 对 custom port URL 的行为可能改变且不被 search 调用方显式控制；行为漂移可能被 S2 transport 统一时发现，导致 S2 返工。
- **建议改法和验证点**:
  1. 在 plan §8.2.8 中明确：`search_public_web` 的 `allow_private_network_url` 参数在 S1 后如何映射到新的独立 policy 字段（search 调用方是否也需要 `allow_custom_port_url` 参数？还是 search 始终使用 packaged default 的 custom port policy？）。
  2. 在 S1 test contract 中增加：search result URL filtering 在 custom port URL 上的行为与 fetch 的 egress decision 一致（或明确声明 search 不受 custom port policy 影响）。
- **修复风险**: 低
- **严重程度**: 低（search result URL 中出现 custom port 的概率低；S2 transport 统一时会自然暴露不一致）

---

### R02-DS-F10 — 低 — `web_search_providers.py` 的 DuckDuckGo HTML 端点也可能触发 challenge redirect，但 S2 不改变 challenge detection owner

- **位置**: plan §6.1, §9.4
- **问题类型**: 契约缺失
- **当前写法**: plan §9.4: "`web_search_providers.py`...Tavily/Serper/DuckDuckGo固定endpoint不跟随redirect，仍由现有provider parser/result owner处理". §6.1: "`web_recovery.py`...预期无 diff；只有真实 challenge/capability reason 传播缺口才允许 S2 修改". `web_challenge_detection.py` 不在 R02 allowlist。
- **反例/失败场景**: DuckDuckGo 的 HTML 端点 (`https://duckduckgo.com/html/`) 与 DuckDuckGo 的常规搜索页面共享同一 challenge 防御体系。当前 `_search_with_duckduckgo` 已通过 `detect_bot_challenge` (line 923) 做 challenge detection——但这是 search module 内联调用，不经过 `web_fetch_orchestrator` 的 challenge→browser fallback 路径。若 S2 将 DuckDuckGo 请求迁到统一 transport sender，challenge detection 的调用路径可能改变——但 `web_challenge_detection.py` 不在 R02 allowlist，plan 不授权修改它。如果 transport 统一后 DuckDuckGo 的 challenge 行为回归（如 challenge detection 不再被调用或返回不同结果），S2 将面临 "需要修改 challenge detector 但不在 allowlist" 的 blocker。
- **为什么有问题**: plan 正确识别了 `web_challenge_detection.py` 不在 allowlist，但未分析 search provider 中内联使用的 challenge detection 在 transport 统一后如何保持行为不变。这是一个可验证的 risk（可以通过 DuckDuckGo HTML smoke 验证），但 plan 未将其列为显式的 S2 verification point。
- **直接证据**:
  - `web_search_providers.py:923-931`: DuckDuckGo search 内联调用 `detect_bot_challenge`
  - plan §6.1: "`web_challenge_detection.py` 独立 producer；fetch/search fallback 消费 typed decision；保留；该文件不在 R02 allowlist且预期无 diff"
  - plan §9.4: search provider 在 S2 的改动
- **影响**: 若 transport 统一改变 DuckDuckGo challenge detection 的调用路径，S2 可能引入 challenge 行为回归且无法在 allowlist 内修复。
- **建议改法和验证点**:
  1. 在 plan §9.5 的 S2 owner/security tests 中增加 DuckDuckGo challenge response 的回归用例。
  2. 在 plan §15.3 stop conditions 中增加：若 S2 后 DuckDuckGo challenge detection 行为改变（与 S1 baseline 比较），立即 stop 回 controller。
- **修复风险**: 低
- **严重程度**: 低

---

### R02-DS-F11 — 低 — S3 smoke 的 `--filing-fixture` 路径 resolve/containment 失败语义未定义

- **位置**: plan §11.2.1, §13.1
- **问题类型**: 契约缺失
- **当前写法**: plan §11.2.1: "路径resolve/regular-file/仓库containment失败则hard fail"。
- **反例/失败场景**: "hard fail" 的具体语义（退出码、错误消息、是否产生 partial artifact）未定义。若 fixture 路径是一个 symlink（在 macOS 上，`/tmp` 有时是 symlink 到 `/private/tmp`），resolve 后的路径可能触发 containment 检查失败。plan 的 "仓库containment" 检查的精确边界（是否允许 resolved path 在仓库外但经由 symlink 在仓库内？）未说明。
- **为什么有问题**: `--filing-fixture` 的 resolve/containment 语义应与 `dayu-cli init` 的 containment 策略（`docs/ui/design.md §3`）保持一致——但 plan 未引用该策略。Implementation agent 可能自行定义 containment 语义，导致与项目其他地方不一致。
- **直接证据**:
  - plan §11.2.1: "路径resolve/regular-file/仓库containment失败则hard fail"
  - `docs/ui/design.md §3`: init containment/symlink 策略——"目标路径或其已有祖先/子树包含 symlink 时 fail closed"
- **影响**: smoke fixture 路径在某些 macOS 配置下可能误 fail；containment 语义不一致增加维护负担。
- **建议改法和验证点**:
  1. 在 plan §11.2.1 中引用 `docs/ui/design.md §3` 的 containment/symlink 规则作为 `--filing-fixture` 路径校验的 baseline。
  2. 明确 "hard fail" 为：非零退出码、明确错误消息（含 resolved path 和拒绝原因）、不产生 partial artifact。
- **修复风险**: 低
- **严重程度**: 低

---

## 4. 非 Finding 裁决

以下候选经独立核实后判定为不构成 material finding：

| 候选 | 审查结论 | 裁决依据 |
|---|---|---|
| "proxy warning 包含 URL query" 风险 | **不成立** | plan §9.2 已明确 "warning只说明...字段不得包含完整 URL、query、proxy URI/userinfo、headers、cookies、storage path"。S2 test matrix §9.5 有 "只出现sanitized warning" case。 |
| "standard transport 不检查 peer" 安全性 | **不成立** | plan §4.3 明确 peer proof 默认 off 时走标准 `requests.Session` transport，但仍做 DNS/address/custom-port policy。这是在 controller discussion Topic 2.3 中裁决的 "default off, matching private-network and custom-port policies defaulting to allow"。 |
| "web_search_providers.py S1 改 import 会破坏 Tavily/Serper 类型" | **不成立** | S1 只把 `WebResourceBudget` import 替换为 `HttpResourceBudget`；`_materialize_bounded_search_response` 当前通过 `_web_fetch_orchestrator._materialize_response_body` 间接使用 budget 字段——该函数当前接收 `WebResourceBudget` 但只用 `wire_body_bytes` 和 `decoded_body_bytes`（HTTP 字段）。改为 `HttpResourceBudget` 后只需更新该函数签名，不改变 behavior。 |
| "S1 新增五个 bool 解析器可能遗漏 `playwright_channel` 和 `playwright_storage_state_dir`" | **不成立** | plan §4.1 packaged config 保留了 `playwright_channel` 和 `playwright_storage_state_dir`；§8.2.3 的 parser 设计包含 "channel/storage dir"。 |
| "删除 lifecycle 后 storage-state path 输入仍可读" 可行性 | **不成立** | plan §4.4 保留了 "显式 `--storage-state-in <file>` 和 `--storage-state-dir <dir>` 作为只读输入"，并明确定义了缺失/不可读/JSON-shape 错误处理。`playwright_storage_state_dir` 的 production resolver（`_resolve_playwright_storage_state_path`）保留并继续做 pre-range host candidate lookup。 |

## 5. Plan 的已知未解决问题（来自 plan 自身的 §16 residual risks）

以下风险 plan 已识别并分配 owner/destination，本 review 确认其处置合理，不另立 finding：

| residual | plan 处置 | 本 review 评估 |
|---|---|---|
| credential lifecycle → Issue #178 | 删除提前实现，保留 read input | 处置正确；R02-DS-F02 关注的原子 writer 不与此冲突 |
| live 网站 DOM/event/error 规模变化 | pre-S1 矩阵裁决 + runtime fail bounded | R02-DS-F01 和 R02-DS-F08 已指出执行和证据风险 |
| proxy 下无法证明 origin peer | proof+proxy typed fail closed | 处置正确 |
| Playwright 无法提供 numeric peer proof | browser typed unavailable/fail closed | R02-DS-F04 已指出 contract 缺失 |
| external provider/challenge 波动 | local hard gate + external 补充 | 处置正确 |
| unified authorization → Topic 9 | 不设计/不预埋 | 与 controller discussion Topic 9 一致 |
| R03 accepted-result/LLM projection | 本 plan 无 diff/无依赖 | 处置正确 |

## 6. Open Questions

| # | 问题 | 相关 finding | 建议裁决方 |
|---|---|---|---|
| Q1 | pre-S1 数值 gate 是否可以在不修改 `smoke_web_ci.py`（即不提前做 S3 改动）的前提下完整执行？若不能，gate 应推迟到哪个阶段？ | R02-DS-F01 | controller |
| Q2 | 普通 diagnostic atomic writer 的临时文件命名、fsync 策略（data vs data+metadata）、replace 失败恢复策略是否需要产品裁决？还是可作为 implementation detail 由 S3 agent 决定？ | R02-DS-F02 | controller |
| Q3 | search provider transport 统一是否应区分 "transport policy"（proxy/peer-proof）和 "egress policy"（address classification/redirect check）？search provider 的固定 API endpoint 是否应绕过 DNS/address egress check？ | R02-DS-F03 | controller |
| Q4 | diagnostic CLI `--allow-private-network-url` 的删除是一个产品决策（"用户不需要从 CLI 覆盖 private policy"）还是 cleanup（"兼容开关"）？若是产品决策，是否有足够的理由？ | R02-DS-F06 | controller |
| Q5 | `web_search_providers.py` 的 S1 coverage 是否需要 80% 行覆盖？若是，Tavily/Serper 路径在无 API key 的 CI 环境中如何达到？ | R02-DS-F07 | controller |
| Q6 | 五 bool 和 budget group/field 的 "local override" 是否需要在 ConfigLoader 层支持 deep merge？还是全部在 `provider._parse_config` 内实现？ | R02-DS-F05 | controller |

## 7. Final Plan Review Conclusion

**Verdict: `fail`**

**Blocker findings: 1**（R02-DS-F01 — pre-S1 数值 gate 循环依赖）
**High findings: 3**（R02-DS-F02, R02-DS-F03, R02-DS-F04）
**Medium findings: 4**（R02-DS-F05, R02-DS-F06, R02-DS-F07, R02-DS-F08）
**Low findings: 3**（R02-DS-F09, R02-DS-F10, R02-DS-F11）
**Open questions: 6**

### 不通过理由

plan 在以下关键维度上尚未 code-generation-ready：

1. **Sequencing（严重）**: pre-S1 数值裁决 gate 要求的 `--filing-fixture` 参数在 S3 才添加到 smoke，而 S3 依赖 S1 和 S2 先完成——形成不可执行的循环依赖。这是结构性 sequencing 缺陷，不是文字细化可修复。**不修复则 S1 implementation 无法按 plan 进入。**

2. **Contract completeness（高）**: browser proof fail-close 的错误类型和检测时机未指定（R02-DS-F04）；search provider transport 统一的 egress policy 应用边界未与 transport policy 区分（R02-DS-F03）。这两项是 implementation agent 必须知道但 plan 未提供的关键设计细节。

3. **Scope clarity（高）**: 普通 diagnostic atomic writer 的引入未经 controller 产品裁决（R02-DS-F02），且 plan 的 contract 未指定临时文件命名、fsync 策略和错误恢复语义。虽然在 S3 的总体范围内，但具体行为缺乏产品级授权。

4. **Evidence sufficiency（中）**: budget initial values 的证据基础 plan 自身承认不足（R02-DS-F08），且 pre-S1 数值裁决 gate 的可执行性存疑（R02-DS-F01）。若两者叠加——gate 无法执行且 initial values 缺乏证据——R02 将以未经验证的预算值进入 production。

### 积极发现

plan 在以下方面表现良好，本 review 独立确认：

- **Root cause 分析**（§2.2）：六项语义错误的 owner-side 直接证据精确、可追溯。
- **Owner 判定**（§3.2）：config owner、HTTP transport owner、browser capability owner、diagnostics v2 owner 与 Issue #178 destination 均清晰无歧义。
- **Controller adjudication 消费**（§1.3, §6.4）：R02-B01/B02 的精确 allowlist 扩展已正确写回，边界明确。
- **删除 contract**（§5.1）：七项必须删除的语义与对应代码位置/symbol 精确映射。
- **保留 contract**（§5.2）：retained security 机制的 owner-level 回归要求可验证。
- **测试矩阵**（§8.3, §9.5, §10.4）：S1/S2/S3 的 owner tests 覆盖了 happy path 和主要 failure path。
- **Stop conditions**（§15.3）：覆盖 owner drift、security regression、数值不足、pyright/coverage 失败与 allowlist 越界。
- **三 slice 终态**（§8.5, §9.7, §10.5）：S1/S2/S3 的 accepted gate 状态和 commit 授权边界清晰。

### 建议的修复优先级

1. **先修 R02-DS-F01**（blocker）：重新设计 pre-S1 数值裁决 gate 的 sequencing——要么 gate 只使用当前 smoke 能力而不依赖 `--filing-fixture`，要么将 `--filing-fixture` 参数添加提升为 pre-S1 micro-slice。
2. **再修 R02-DS-F03 和 R02-DS-F04**（high）：补充 search transport 统一的 egress 边界和 browser proof fail-close 的 error contract。
3. **再修 R02-DS-F02**（high）：补充 atomic writer 的最小 contract 或等待 controller 产品裁决。
4. **最后修 medium/low findings**：这些不阻塞 plan 的可实施性，但应在 implementation 前收敛。

### Handoff

本 review 到此停止。不修改 plan、产品代码、测试、README 或 control。下一动作只能由 umbrella controller 在消费本 review 与第一路 MiMo review 后执行 finding adjudication，随后 AgentCodex 修复全部 accepted findings，再经双路完整 re-review 后产生 accepted-plan commit。

---

**审查完成时间**: 2026-07-14 21:20 UTC+8
**审查分支**: `phaseflow/host-issues-control`
**审查基线**: `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb`
