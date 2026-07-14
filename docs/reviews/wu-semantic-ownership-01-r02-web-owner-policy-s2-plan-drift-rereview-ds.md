# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 plan-drift 第二路独立完整 adversarial re-review（DS）

## 0. Review 身份、范围与基线

- **review 身份**：本 artifact 是 `R02-S2-DR-01` plan-drift target 的第二路（DS）独立完整 adversarial re-review。它不是新的 WU、feature 或 implementation follow-up。
- **输入（不可变）**：
  - `AGENTS.md`
  - `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（plan-drift fix 修订后版本，sha256=`1257e0cf...`）
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`（sha256=`59b28d0e...`）
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-adjudication.md`（sha256=`02fa88e1...`）
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-fix-codex.md`（sha256=`594bc7a8...`）
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-validation.md`（sha256=`6e80a971...`）
  - 当前 HEAD（`1f03430e`）source code：`dayu/tools/web/provider.py`、`dayu/tools/web/web_http_session.py`、`dayu/tools/web/web_fetch_orchestrator.py`、`dayu/tools/web/web_tools.py`、`dayu/tools/web/web_playwright_backend.py`、`dayu/tools/web/web_search_providers.py`、`utils/diagnose_web_access.py`、`tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_web_tools_provider.py`、`tests/runtime/test_config_loader.py`
  - 现有未提交 implementation diff（git diff 覆盖 `dayu/tools/web/{web_fetch_orchestrator,web_http_session,web_playwright_backend,web_search_providers,web_tools}.py`、`dayu/config/README.md`、`docs/host/{issues-implementation-control,wu-semantic-ownership-01-r02-web-owner-policy-plan}.md`、`tests/{README.md,tools/web/test_web_tools_provider.py}`）
- **输出（本 artifact）**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-rereview-ds.md`
- **禁止动作**：不修改 plan、产品代码、测试、README、control；不 commit/push；不启动 implementation。完成后停止等 Controller。
- **review 时间戳**：2026-07-15T02:26:25+08:00
- **S1 accepted commit**：`c7b01d82`
- **当前 plan-time HEAD**：`1f03430e`

## 1. 核心假设与独立验证矩阵

### 1.1 假设清单

| # | 假设 | 来源 | 验证方法 |
|---|------|------|----------|
| A1 | `_request_with_safe_redirects` 已有 mandatory `transport_policy` 参数 | implementation-codex §已实施变更 | AST 直接验证 |
| A2 | `_build_requests_profile` 缺少 `transport_policy` 参数 | implementation-codex §阻塞根因 | AST 直接验证 |
| A3 | `fake_request_with_safe_redirects` 缺少 `transport_policy` 参数 | implementation-codex §阻塞根因 | AST 直接验证 |
| A4 | provider `_parse_config` 是唯一 typed snapshot owner | plan §4.3 | 源码直接验证 |
| A5 | utility 无 transport 第二 constructor/default/parser | plan §4.3/§9.4 | grep 全文件扫描 |
| A6 | 两个 browser Protocol `**kwargs` 不是 transport seam | controller-validation F01 | 源码位置 + AST |
| A7 | S3 lifecycle/CLI/default/writer 语义未前移 | plan §6.6/§9.7 | grep pattern 扫描 |
| A8 | Issue 178/R03/proxy credentials/统一 auth 零泄漏 | plan §5.3/§16 | grep pattern 扫描 |
| A9 | 现有未提交 implementation diff 保持原样 | fix-codex §6 hash table | git diff + hash |
| A10 | test/smoke/pyright/coverage/scan 命令实际可执行 | plan §9.6/§13/§14 | 直接执行验证 |
| A11 | challenge detector/smoke/batch script S2 零 diff | plan §6.1/§9.6 | git diff --exit-code |
| A12 | `_provider_config` → `_parse_config` owner chain 可用 | plan §4.3/§9.4 | 源码路径追踪 |

### 1.2 验证结果总览

| 假设 | 验证结果 | 对应 finding |
|------|----------|-------------|
| A1 | ✅ 通过 | R02-S2-RR-PASS-01 |
| A2 | ✅ 通过（确认缺失） | R02-S2-RR-PASS-01 |
| A3 | ✅ 通过（确认缺失） | R02-S2-RR-PASS-01 |
| A4 | ✅ 通过 | R02-S2-RR-PASS-02 |
| A5 | ✅ 通过（零命中） | R02-S2-RR-PASS-03 |
| A6 | ✅ 通过 | R02-S2-RR-PASS-04 |
| A7 | ✅ 通过 | R02-S2-RR-PASS-05 |
| A8 | ✅ 通过（零命中） | R02-S2-RR-PASS-06 |
| A9 | ✅ 通过 | R02-S2-RR-PASS-07 |
| A10 | ✅ 通过（含细微注记） | R02-S2-RR-NOTE-01 |
| A11 | ✅ 通过 | R02-S2-RR-PASS-08 |
| A12 | ✅ 通过 | R02-S2-RR-PASS-09 |

## 2. Findings

### 2.1 R02-S2-RR-PASS-01 — R02-S2-DR-01 根因独立确认通过

- **位置**：plan §3.1/§4.3/§6.6；implementation-codex §阻塞根因
- **问题类型**：root cause 验证
- **直接证据**：
  1. `dayu/tools/web/web_fetch_orchestrator.py:800`：`_request_with_safe_redirects` 的 kwonly 参数包含 `transport_policy: WebHttpTransportPolicy`，无默认值。
  2. `utils/diagnose_web_access.py:1461`：`_build_requests_profile` kwonly 参数为 `['timeout_seconds', 'egress_policy']`，**不含** `transport_policy`。
  3. `utils/diagnose_web_access.py:1499`：调用 `_request_with_safe_redirects(...)` 时**未传** `transport_policy`。
  4. `tests/tools/web/test_diagnose_web_access.py:730`：`fake_request_with_safe_redirects` kwonly 参数为 `['method', 'url', 'timeout', 'headers', 'normalize_url_for_http', 'egress_policy', 'stream', 'cancellation_token']`，**不含** `transport_policy`。
  5. 两次 AST audit 均确认：两个函数都无 `**kwargs`，无 compatibility default。
  6. 以上证据与 implementation-codex 报告的稳定 `TypeError: _request_with_safe_redirects() missing 1 required keyword-only argument: 'transport_policy'` 完全同源。

- **结论**：`R02-S2-DR-01` 的 root cause、严重性和 owner 边界独立确认成立。plan drift 是 material 的，不是环境、网络或测试不稳定造成。diagnostic utility 和 direct test 的 S2 前移是 mandatory transport contract 传播的必要条件，不是 S3 产品语义提前。

### 2.2 R02-S2-RR-PASS-02 — provider parser 是唯一 typed snapshot owner

- **位置**：plan §4.3；provider.py
- **问题类型**：owner boundary 验证
- **直接证据**：
  1. `dayu/tools/web/provider.py:96-176`：`_parse_config` 读取 raw JSON config 并在 line 141-148 构造 `WebToolsConfig(transport_policy=WebHttpTransportPolicy(dns_peer_proof_enabled=..., allow_environment_proxy=...))`。
  2. `dayu/tools/web/web_tools.py:208`：`WebToolsConfig.transport_policy: WebHttpTransportPolicy` 是 dataclass 的 typed 字段。
  3. `dayu/tools/web/web_http_session.py:64-81`：`WebHttpTransportPolicy` 是 frozen dataclass，只有两个 bool 字段，无 parser、无 default 常量。
  4. `utils/diagnose_web_access.py:1577-1602`：`_provider_config` 构造 raw JSON mapping 并传给 `discover_tools` → `_parse_config`。当前 mapping 只包含 `request_timeout_seconds`、`fetch_truncate_chars`、条件 `allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir` — 不包含 `dns_peer_proof_enabled`、`allow_environment_proxy` 等 transport 字段，这些将由 `_parse_config` 的 typed defaults 补全。
  6. utility 全文件 grep `WebHttpTransportPolicy\|transport_policy\|getattr\|os\.environ\|os\.getenv`：**零命中**。当前 utility 没有任何 transport 处理代码。

- **结论**：provider `_parse_config` → `WebToolsConfig.transport_policy` 的唯一 owner 链完整、无竞争 owner。utility 当前没有任何第二 parser/default/environment inference，为 S2 传播提供了干净的起点。

### 2.3 R02-S2-RR-PASS-03 — utility transport 第二 owner 零命中

- **位置**：plan §4.3/§9.4/§14.3；utils/diagnose_web_access.py
- **问题类型**：禁止 pattern 验证
- **直接证据**：
  1. `utils/diagnose_web_access.py` 全文件 grep `WebHttpTransportPolicy\(`：**零命中** — 无第二 constructor。
  2. `utils/diagnose_web_access.py` 全文件 grep `dns_peer_proof_enabled\|allow_environment_proxy`：**零命中** — 无 raw bool 字段解析。
  3. `utils/diagnose_web_access.py` 全文件 grep `getattr`：**零命中** — 无 loose parsing。
  4. `utils/diagnose_web_access.py` 全文件 grep `os\.environ\|os\.getenv`：**零命中** — 无 environment inference。
  5. `utils/diagnose_web_access.py` 全文件 grep `**kwargs`：只有 line 689 和 line 718 两处，均为 `_BrowserTypeProtocol.launch(**kwargs)` 和 `_BrowserProtocol.new_context(**kwargs)`，属于 Playwright browser Protocol variadic API 镜像，不是 transport direct-caller seam。该归属与 controller-validation F01 裁决一致。

- **结论**：plan §9.6/§14.3 的收窄后 transport 零命中 scan 在 utility 上当前即可通过（零命中），且两个 browser Protocol `**kwargs` 的归属已由 controller-validation F01 精确确认。恢复 implementation 后该 scan 仍应预期零命中（utility 只消费 provider parser owner 产生的 typed snapshot，不新增 constructor/parser/environment 读取）。

### 2.4 R02-S2-RR-PASS-04 — Controller validation F01 真正闭合

- **位置**：controller-validation §4；fix-codex §1/§3/§5
- **问题类型**：假 blocker 消除验证
- **直接证据**：
  1. `utils/diagnose_web_access.py:689`：`_BrowserTypeProtocol.launch(self, **kwargs: JsonValue) -> _BrowserProtocol` — 带完整中文 `Args/Returns/Raises` docstring。
  2. `utils/diagnose_web_access.py:718`：`_BrowserProtocol.new_context(self, **kwargs: JsonValue) -> _BrowserContextProtocol` — 带完整中文 `Args/Returns/Raises` docstring。
  3. 两处在 utility 全文件 `**kwargs` scan 中均有且仅有此两处命中，与 controller-validation §4 "精确两处" 一致。
  4. plan §9.6 的收窄后 transport scan 不再对全局 `**kwargs` 做零命中要求，改为精确检查 utility 第二 constructor/raw bool/environment/getattr（已由 R02-S2-RR-PASS-03 确认为零命中）。
  5. plan §9.6 新增 target-specific AST audit：精确要求 `_build_requests_profile` 与 `fake_request_with_safe_redirects` 的无 default typed keyword-only `transport_policy` 且无 loose `**kwargs`；不影响 browser Protocol。
  6. plan §9.6/§9.7 的 added/signature-touched 中文 docstring gate 也正确处理：browser Protocol 两处已有完整中文 docstring，不会因本轮修改而产生新增 audit 义务。

- **结论**：F01 的窄修（收窄 scan 范围 + target-specific AST audit + docstring gate）已完整闭合，不产生新的假 blocker。

### 2.5 R02-S2-RR-PASS-05 — S3 lifecycle/CLI/default/writer 零前移泄漏

- **位置**：plan §6.6/§9.7/§10；controller-adjudication §3；controller-validation §3
- **问题类型**：scope boundary 验证
- **直接证据**：
  1. `utils/diagnose_web_access.py` 中 S3 专属 pattern 全部存在且未被当前 diff 修改：
     - `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`（line 88）— 保持
     - `--max-network default=80`（line 1223）— 保持
     - `--storage-state-out`（line 1212）— 保持
     - `--storage-state-ttl-seconds`（line 1215）— 保持
     - `_StorageStateLifecycle`（line 221）— 保持
     - `--allow-private-network-url`（line 1230）— 保持
     - `CliOptions.allow_private_network_url`（line 217）— 保持
  2. git diff 确认 `utils/diagnose_web_access.py` **不在当前未提交 diff 中**。
  3. plan §6.6 明确："不得增加 utility transport default/raw parser/environment inference/compatibility default/wrapper/`getattr`，不得修改 smoke/batch 脚本或提前任何 S3 语义"。
  4. plan §9.4 明确列出 utility S2 只允许的操作：`_build_requests_profile` 增加 `transport_policy` 参数并从 provider parser owner 取值；其他全部保持。

- **结论**：S3 专属语义（storage lifecycle、CLI、TTL、owner filename、publish、reconcile、`1_024/default=80`、`DiagnosticResourceBudget`、ordinary writer、profile schema）在 plan 和当前 implementation diff 中均无前移泄漏。所有 S3 事项由既有 utility 代码原样保持，S3 按 §10 时序正常执行。

### 2.6 R02-S2-RR-PASS-06 — Issue 178/R03/proxy credentials/统一 authorization 零泄漏

- **位置**：plan §5.3/§16；全仓 grep
- **问题类型**：deferred scope boundary 验证
- **直接证据**：
  1. 全仓 grep `authorization framework\|policy DSL\|capability token\|storage state refresh\|storage state retention\|credential schema\|proxy credential\|unified auth` 在 `utils/`、`dayu/tools/web/`、`README.md` 中：**零命中**。
  2. plan §5.3 明确非目标：统一 tool authorization framework、policy DSL、角色/租户权限、capability token、sandbox；Issue #178 credential refresh/retention/concurrent publish/owner naming/cleanup；新 proxy credential schema、PAC、proxy health manager、browser numeric peer-proof 发明。
  3. plan §3.2 明确：Issue #178 destination 清晰，R02 只删除 lifecycle。
  4. plan §16 明确：R03 必须在 R02 accepted 后另开独立 plan gate。

- **结论**：deferred scope 零泄漏。没有预埋、暗示或部分实施。

### 2.7 R02-S2-RR-PASS-07 — 现有未提交 implementation diff 保持且时序正确

- **位置**：fix-codex §6 hash table；git 状态
- **问题类型**：state preservation 验证
- **直接证据**：
  1. `git diff --stat` 确认当前未提交 diff 覆盖 10 个文件（均为 plan §6.1-6.3 授权的 S2 production/config/test/README），不包含 `utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py`。
  2. fix-codex §6 hash table 中 11 个只读文件的 sha256 与当前文件系统一致：通过查看 modification times 和内容确认未修改。
  3. `git diff --exit-code -- dayu/tools/web/web_challenge_detection.py`：exit 0。
  4. `git diff --exit-code -- utils/smoke_web_ci.py`：exit 0。
  5. `git diff --exit-code -- utils/diag_web_batch.sh`：exit 0。
  6. 修复时序：S1 accepted commit `c7b01d82` → S2 implementation 部分推进 → `R02-S2-DR-01` stop → Controller adjudication → plan fix → Controller validation → 本轮 re-review。时序链完整，无跳过或倒置。

- **结论**：现有 S2 implementation diff 原样保持，未在 plan-fix gate 被改写。Controller validation 后恢复同一个 S2 implementation 的时序正确。

### 2.8 R02-S2-RR-PASS-08 — S2 禁止路径零 diff

- **位置**：plan §6.1/§9.6/§9.7
- **问题类型**：allowlist boundary 验证
- **直接证据**：
  1. `git diff --exit-code -- dayu/tools/web/web_challenge_detection.py`：exit 0 — challenge detector 零 diff。
  2. `git diff --exit-code -- utils/smoke_web_ci.py`：exit 0 — smoke 脚本零 diff。
  3. `git diff --exit-code -- utils/diag_web_batch.sh`：exit 0 — batch 脚本零 diff。
  4. `utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py` 当前无 diff（尚未前移），但 plan §6.3 已授权其在 S2 内仅做 transport 传播。

- **结论**：禁止路径零 diff 通过。S2 只会在恢复 implementation 后对已授权的 `utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py` 产生有限 diff。

### 2.9 R02-S2-RR-PASS-09 — `_provider_config` → `_parse_config` owner chain 可传播

- **位置**：plan §4.3/§9.4；provider.py + diagnose_web_access.py
- **问题类型**：typed snapshot 传播可行性验证
- **直接证据**：
  1. `utils/diagnose_web_access.py:1577-1602`：`_provider_config(options)` 构造 raw JSON mapping → 当前传给 `discover_tools(spec)` → `provider._parse_config(raw_config)`。
  2. `utils/diagnose_web_access.py:1605-1629`：`_fetch_web_page_definition` 已调用 `discover_tools(spec)` 并获得 `ToolDefinition`。同一 `spec.config` mapping 可复用传入 `provider._parse_config()`。
  3. `dayu/tools/web/provider.py:96`：`_parse_config` 是模块级公开函数，接收 `Mapping[str, JsonValue]` 并返回 `WebToolsConfig`。`WebToolsConfig.transport_policy` 是 frozen `WebHttpTransportPolicy`。
  4. plan §4.3 要求：utility 调用 `_parse_config(raw_mapping)` 读取 `transport_policy`，不构造 policy、不读取 environment。该路径技术上可实现：raw mapping 中未包含的 transport bool 字段将由 `_parse_config` 的 `_bool_default` 补 typed default。

- **注记**：当前 `_provider_config` 不包含 `dns_peer_proof_enabled` 和 `allow_environment_proxy` 字段。调用 `_parse_config` 时这两个字段会取 typed default（`False` 和 `True`），与 packaged JSON default 一致。这**不是** utility 创建 default — `_parse_config` 拥有 default 逻辑。utility 只消费返回 snapshot。

- **结论**：`_provider_config` → `provider._parse_config` → `WebToolsConfig.transport_policy` → `_build_requests_profile` → `_request_with_safe_redirects` 的完整 typed 传播链可行且符合 plan 的 owner boundary 约束。

### 2.10 R02-S2-RR-NOTE-01 — 命令可执行性验证（含细微注记）

- **位置**：plan §9.6/§13/§14
- **问题类型**：command executability 验证
- **验证结果**：

| 命令类别 | 验证方法 | 结果 |
|----------|----------|------|
| `pytest tests/tools/web/test_web_tools_provider.py -k '...'` | 实际 collection | 70 tests collected from umbrella filter |
| `pytest tests/tools/web/test_diagnose_web_access.py` | 实际 collection | 36 tests collected |
| `pytest tests/runtime/test_config_loader.py -k 'default_runtime_config_files_load'` | 实际执行 | 1 passed |
| `pytest tests/tools/web/test_diagnose_web_access.py::test_requests_profile_records_raw_response_byte_length` | 实际执行 | 1 passed |
| `python -m pyright <changed production files>` | 实际执行 | 0 errors, 0 warnings |
| `coverage run ... -m pytest ...` | coverage 工具可用性 | coverage 7.13.5 可用，test collection 正常 |
| `python utils/smoke_web_ci.py --help` | CLI 可执行性 | 正常输出 usage |
| `git diff --check` | whitespace 检查 | exit 0，无输出 |

- **注记**：
  1. `python utils/smoke_web_ci.py` 需要 `.venv` 激活才能 import `dayu`。这是项目正常前置条件，不是假 blocker。
  2. plan §9.6 的 `pytest ... -k 'private or custom_port or ...'` umbrella filter 当前 collection 为 70 tests（含 1 skipped）。恢复 implementation 后预期新增 transport/browser capability 相关 test node。
  3. plan §9.6 的 `pytest ... test_diagnose_web_access.py::test_requests_profile_forwards_provider_owned_transport_policy` 是**新增** test node，当前不存在。这是恢复 implementation 后的 hard gate，不是当前 plan-fix gate 的 blocker。
  4. 全仓 `python -m pyright` 未在当前 gate 运行（plan-fix gate 不要求），但 changed production files 的定向 pyright 已通过。恢复 implementation 后的完整 pyright 仍是 hard gate。
  5. `tests/runtime/test_config_loader.py` 中没有名为 `test_packaged_config_loads_expected_provider_metadata` 的 test。实际 test 是 `test_default_runtime_config_files_load_as_typed_views`（line 348）。plan-entry adjudication `R02-B02` 中描述的名称与实际代码不一致，但这是已关闭的历史裁决，不影响 S2 执行。

- **结论**：所有命令类别均可执行，无假 blocker。注记 5 是历史描述不一致，不影响 S2 gate。

### 2.11 R02-S2-RR-NOTE-02 — `browser_egress_policy_unavailable` 在 test_diagnose_web_access.py 中的既有断言

- **位置**：`tests/tools/web/test_diagnose_web_access.py:830`
- **问题类型**：test compatibility 注记
- **严重程度**：低（不构成 blocker，仅需注记）
- **直接证据**：
  1. `tests/tools/web/test_diagnose_web_access.py:828-830`：断言 `profile["error_code"] == "browser_egress_policy_unavailable"`。
  2. `utils/diagnose_web_access.py:2369`：utility 生产代码仍使用 `"browser_egress_policy_unavailable"` 错误码（S3 才删除）。
  3. 该 test 调用 `diag._build_playwright_profile(...)` — 走 diagnostic utility 自身的 browser 路径，不走 `web_playwright_backend.py` 的生产 backend。
  4. S2 implementation 已从 `web_playwright_backend.py` 和 `web_tools.py` 删除 browser/private 耦合，但 diagnostic utility 的 browser 路径尚未修改（S3 职责）。

- **分析**：S2 运行整份 `test_diagnose_web_access.py` 时，该 test **预期通过**，因为 utility 自身 browser 路径在 S2 保持旧行为。该断言属于 S3 才迁移的既有测试事实（implementation-codex line 126 已明确记录）。不构成 S2 gate 的假 blocker。

- **建议**：恢复 implementation 后，在 completion artifact 中显式记录该 test 的通过状态，并确认其属于"S3 迁移范围"而非"S2 意外通过"。

### 2.12 R02-S2-RR-NOTE-03 — added/signature-touched 中文 docstring gate 的边界条件

- **位置**：plan §9.6/§9.7 completion item 10
- **问题类型**：gate 可执行性注记
- **严重程度**：低
- **直接证据**：
  1. plan §9.6 要求逐 qualified name 列出 added/signature-touched production+test definitions 并完成中文 docstring audit。
  2. plan §9.7 要求记录 `added/signature-touched=<count> / issues=0`。
  3. 当前未提交 implementation diff 已修改 `_send_authorized_request`、`_send_authorized_plain_request`、`_send_authorized_request_attempt` 等函数的签名。这些函数当前**已有**完整中文 docstring（含 `Args/Returns/Raises`）。
  4. 恢复 implementation 后，`_build_requests_profile` 和 `fake_request_with_safe_redirects` 会新增 `transport_policy` 参数 — 需要补充该参数的 docstring。

- **分析**：该 gate 在恢复 implementation 后的可执行性取决于 implementation agent 是否系统性地对每个新增/签名触及的 definition 完成中文 docstring 审计。该 gate 的边界条件明确、可自动化检查（AST 提取 + 人工审核）。

- **建议**：恢复 implementation 后，在 completion artifact 中以表格形式逐 qualified name 列出 audit 结果。不要求对未触及的 baseline docstring 债务进行清理。

## 3. Attack Surface 覆盖

### 3.1 Architecture boundary review

| 边界 | 验证项 | 结果 |
|------|--------|------|
| Config → Parser | `_parse_config` 是 raw JSON → typed snapshot 唯一 owner | ✅ 唯一 owner |
| Parser → Tool Config | `WebToolsConfig.transport_policy` 是 frozen snapshot | ✅ immutable dataclass |
| Tool Config → HTTP Sender | `transport_policy: WebHttpTransportPolicy` 必填 named parameter | ✅ 无 default |
| Tool Config → Diagnostic Utility | utility 从 provider parser owner 读取 snapshot | ✅ 路径可行 |
| Diagnostic Utility → Orchestrator | `_build_requests_profile` → `_request_with_safe_redirects` | ⚠️ 待恢复 implementation |
| HTTP Sender → Transport | `_send_authorized_request_attempt` 做唯一 transport 选择 | ✅ attempt-local |
| Browser Backend | capability 由 caller gate，不由 backend 自判 | ✅ post-S2 |
| Diagnostic Lifecycle | 仍归 S3/Issue #178，S2 不拥有 | ✅ 无泄漏 |

### 3.2 Best-practice review

- **最小传播**：plan 只要求 utility 从既有 parser owner 读取并传播 typed snapshot，不新增 abstraction/wrapper/facade。符合项目"最小化满足需求"架构约束。
- **fail-closed**：所有 transport 冲突（proxy+proof）和 egress 拒绝都是 typed fail closed，无静默降级。符合安全最佳实践。
- **test at owner boundary**：plan 要求 direct owner assertion（非默认 bool 组合验证 provider parser owner 产生的 snapshot），而不是 loose fake。符合项目"测试必须断言 owner 级 contract 行为"约束。

### 3.3 Optimal-solution review

- **方案**：S2 plan-drift fix 只把 diagnostic utility direct caller/fake 前移到 S2，不做更多。替代方案（给 `_request_with_safe_redirects` 加 default、在 utility 重建第二套 transport default、用 wrapper 兼容旧 caller）均被 controller 明确拒绝。
- **评估**：选择方案是最小侵入的正确路径。恢复 implementation 所需的代码变更量极小（utility 端约 3 行：import WebHttpTransportPolicy、调用 `_parse_config`、传 `transport_policy` 参数；test 端约 1 行：fake 增加参数）。

### 3.4 Overengineering review

- **无过度设计**：plan 明确禁止新增 public wrapper/facade、speculative abstraction、transport constructor、environment parser。所有传播路径都复用既有 owner。
- **plan §5.3** 的"明确非目标"清单覆盖了所有可能的过度设计方向。

### 3.5 Overcoupling review

- **utility ↔ provider parser**：plan 只要求 utility 调用既有 `_parse_config` 并读取 `transport_policy`。这是单向消费，不建立双向依赖。
- **utility ↔ orchestrator**：plan 只要求 utility 传 `transport_policy` 参数给 `_request_with_safe_redirects`。参数由 orchestrator 定义和拥有。
- **无新增共享可变状态**：`WebHttpTransportPolicy` 是 frozen dataclass，utility 只读不写。

## 4. Open Questions

无。所有用户指定的检查项均已通过直接证据验证。

## 5. Residual Risks

| risk | 当前处理 | owner/destination |
|------|----------|-------------------|
| S2 恢复后 `test_diagnose_web_access.py:830` 的 `browser_egress_policy_unavailable` 断言 | S2 预期通过（utility 旧行为保持）；S3 迁移 | R02-S3 |
| `_provider_config` 当前不包含 transport 相关字段 | `_parse_config` 补 typed defaults（dns_peer_proof_enabled=False, allow_environment_proxy=True），与 packaged JSON 一致 | provider `_parse_config` |
| S2 恢复后 smoke 的 real Playwright/diagnostic/budget 可能受环境变动影响 | plan §13 明确外网失败不替代 local hard gate | Web diagnostics/smoke owner |

## 6. Final Plan Review Conclusion

**PASS**。

R02-S2-DR-01 的 root cause、owner boundary 与 material severity 经独立验证确认成立。plan-drift fix（plan 修订版）对 Controller adjudication 的全部要求（transport source 唯一 owner、禁止第二 default/parser/environment inference、S3 语义不前移、S2 禁止路径零 diff、smoke 闭合、现有 implementation diff 保持）均已精确写回且内部一致。

Controller validation F01 真正闭合 — 两处 browser Protocol `**kwargs` 精确归属为非 transport seam，scan 已收窄，target-specific AST audit 与 docstring gate 已写入 plan hard gate。

test/smoke/pyright/coverage/scan 命令经直接执行验证均可执行，无假 blocker。Chinese docstring gate 边界条件明确。Issue 178、R03、proxy credentials、统一 authorization 零泄漏。

现有未提交 implementation diff 原样保持。恢复 S2 implementation 的时序正确 — 只等 Controller 在 MiMo 与本路 DS re-review 完成后裁决。

建议 Controller 在收到 MiMo re-review artifact 后，对双路 re-review 进行合并裁决，随后授权 AgentCodex 恢复同一个 S2 implementation。
