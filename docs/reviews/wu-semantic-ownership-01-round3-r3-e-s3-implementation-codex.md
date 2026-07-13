# R3-E Slice S3 Implementation Artifact（AgentCodex）

## 1. 结论与范围

状态：**COMPLETE（implementation only）**。

本轮按已接受计划 `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md` 完成 R3-E Slice S3：Web diagnostic 安全投影、diagnostic schema v2、storage-state lifecycle、父进程 local fixture ledger 与独立 smoke classifier/negative controls 已形成同一 owner 闭环。实现依赖已接受的 R3-E S1 `a20efac7`、S2 `728e73af` 与 control bookkeeping `c2009966`。

本轮没有 commit、push，也没有进入 code review。没有实施 S4 Documents、通用 tool-security framework、aggregate 或 final closeout。

### Scope correction

执行中收到 scope correction 后重新核对工作区：`dayu/tools/web/web_egress_policy.py` 未被本轮修改，也没有把 S3 扩展到 egress policy 或其他非白名单生产文件。所有实现改动均保持在 handoff 允许的 production/consumer/test/README/artifact 文件内；无需回退非白名单文件。

## 2. 第一性原理判断与直接证据

修改动机成立，且风险不是展示层问题：旧 producer 会把可逆正文前缀、raw URL/query、响应头值或展开后的成功 payload 带入日志/diagnostic artifact；旧 storage-state 路径存在隐式输出和直接 final 写入；旧 smoke classifier 又会信任同一 producer 自报的 `ok`。因此 producer 可同时制造错误行为和“成功证据”，无法构成独立 PASS oracle。

本轮把事实放回唯一 owner：

- `dayu.tools.web.web_diagnostics` 产生并校验 Web URL、正文、响应头、错误与 network event 的安全投影；caller 不再自行保存 prefix 或 raw URL secret。
- `utils/diagnose_web_access.py` 拥有 schema v2 artifact 装配和 storage-state 生命周期；它不拥有 Web 安全规则，也不兼容读取旧 schema。
- `utils/smoke_web_ci.py` 父进程拥有 fixture registration、一次性 sentinel、typed in-memory ledger、expected exact bytes 和 PASS classifier；diagnostic child/artifact producer 不能写 ledger，也不能用 `ok=true` 自签 PASS。

直接运行证据：`utils/smoke_web_ci.py --include-playwright --external-limit 0` 的 7 个 local cases 均为 `passed`，包括 HTML requests/tool、PDF requests/tool、Playwright、challenge control 与 assembly config；4 个 search provider cases 保持 `diagnostic_only`；总状态 `passed`、exit code 0。生成目录全文扫描未命中 `token=`、sentinel、敏感 header、旧 prefix 字段、含 userinfo/query 的 HTTP URL。

## 3. Changed files 与 semantic owners

| 文件 | semantic owner / 实现内容 |
| --- | --- |
| `dayu/tools/web/web_diagnostics.py` | 新增 `WebDiagnosticProjection` owner；schema v2/revision 2、safe URL、正文 length+SHA-256、响应头 presence/受限语义、错误脱敏、network event 投影。 |
| `dayu/tools/web/web_fetch_orchestrator.py` | 抓取/转换 producer 只向 diagnostic context 传安全 URL、header projection、正文 length/digest 与 challenge 事实；成功结果携带 exact origin response length/digest。Docling stream name 只从 URL path 推导。 |
| `dayu/tools/web/web_playwright_backend.py` | Playwright backend 的异常、blocked URL 与 cleanup log 统一经过 Web diagnostic projection，不保存 raw URL/query 或正文 excerpt。 |
| `dayu/tools/web/web_tools.py` | 唯一 Web tool producer 同步迁移安全日志与 origin response length/digest；challenge 所需正文只作为瞬时 S2 decision 输入，不进入 diagnostic 持久化。 |
| `utils/diagnose_web_access.py` | schema v2 artifact producer；requests/tool/Playwright profile 使用统一投影；Playwright 主响应 exact bytes budget/digest；storage-state 显式 opt-in、atomic publish、权限、TTL、failure/cancel cleanup 与 startup reconciliation。 |
| `utils/smoke_web_ci.py` | 唯一 Web smoke consumer 同步迁移 schema v2；父进程 fixture ledger、每 case 256-bit token、negative controls、freeze-before-classify 和独立 PASS oracle。 |
| `tests/tools/web/test_web_tools_provider.py` | owner 级 secret/projection/log 测试；覆盖 content/raw HTML/query/userinfo/headers/exception/network event 与 Docling query sentinel。 |
| `tests/tools/web/test_diagnose_web_access.py` | schema v2/no-fallback、storage-state matrix、Playwright exact response body budget/digest 测试。 |
| `tests/tools/web/test_smoke_web_ci.py` | ledger lifecycle/唯一 sentinel/freeze/negative controls、stdio secret、synthetic artifact、browser/Docling independent skip 与 classifier matrix。 |
| `tests/README.md` | 按测试 README 的 Agent 更新约束，更新 Web diagnostic/storage/ledger/smoke 测试职责说明。 |
| `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-implementation-codex.md` | 本 implementation handoff artifact。 |

## 4. Contract closure evidence

### 4.1 Diagnostic projection 与 schema v2

- `WebDiagnosticProjection.to_json()` 明确 `ok` 仅是 producer observation；completed profile 强制 backend + content，正文只输出 `content_length` / `content_digest`。
- `project_safe_url()` 只输出 scheme、规范化 host、显式 port 与 path，删除 userinfo、query、fragment。
- `project_response_headers()` 不保存任意 raw value；敏感 header 只记录名称存在性，Content-Type 只保留规范化 media type，Content-Length 只保留合法非负整数。
- `failed_projection()` 删除 URL 本体、userinfo/query values、高熵 hex 与 runtime 识别的敏感值；network event 只包含 safe URL、method、resource type、status。
- `utils/diagnose_web_access.py::_load_diagnostic_payload()` 精确要求 schema version/revision 2；`utils/smoke_web_ci.py::_diagnostic_schema_gap()` 同步精确校验并递归拒绝旧 prefix 字段，没有旧 schema fallback、loose parsing 或 compatibility shim。
- stdout/stderr 只经 `content_diagnostic_from_text()` 投影为 length/digest 后记录，不保存 prefix。

### 4.2 Storage-state lifecycle

- 默认 `storage_state_out` 为空，`storage_state_dir` 只能解析已有 owner-named input，不能隐式启用输出，形成默认零写入。
- 显式 output 必须同时给出正 TTL，且 final filename 必须与当前 URL host 的 owner 命名一致。
- `_ensure_private_storage_directory()` 对新目录创建并确认 `0700`；已存在目录必须预先为 `0700`，不擅自修改共享目录。
- `_StorageStateLifecycle.publish()` 使用同目录 owner-named random temp、`O_EXCL` + `0600`，序列化后 `flush()` / `fsync()`，再用 `os.replace()` 原子发布并确认 final `0600`；没有直接写 final path。
- 成功 final 按 TTL 保留；普通 exception、body-limit failure 与 `BaseException` cancel 路径删除本 run temp/已发布 final。
- opt-in startup 只扫描并删除本 owner prefix/suffix 的 orphan temp 与过期 final，不触碰其他文件。
- 不承诺 SIGKILL/主机崩溃即时 cleanup；只承诺下一次 opt-in startup reconciliation + TTL，与 accepted plan 一致。

### 4.3 Parent-owned ledger 与 independent smoke oracle

- `_running_local_fixture_server()` 在 child 启动前创建 `ParentFixtureLedger`，与 `ThreadingHTTPServer` 共生；handler 只追加 typed in-memory observation。
- 每个 local case 用 `secrets.token_hex(32)` 生成独立 256-bit token并置于 URL query；ledger 仅记录 token SHA-256、method、normalized path、response kind/digest、accepted/rejected，并设置 256 条有界上限与 dropped count。
- 父进程在 child 前执行 missing/wrong/unknown-path 负控，child 后执行 replay 负控；fixture 均拒绝并追加 negative observation。
- context 退出时先 shutdown/server_close/join，再记录 `server_stopped` 并 `freeze()`；所有 classifier 只在 context 退出、取得 frozen ledger 后运行。
- `_fixture_ledger_gap()` 要求对应 token/path 恰好一条 GET accepted observation、response kind/digest 与父进程 registration 一致、ledger 无丢弃、必需负控全部 rejected。
- `_exact_response_artifact_gap()` 独立比较 artifact 的 origin `content_length/content_digest` 与父进程 actual registered bytes；随后再验证 required backend execution evidence。
- synthetic `ok=true` 但缺 ledger、错误 digest/length、负控意外 accepted、wrong backend、Playwright 未执行、旧 schema 均不能 PASS。只有父进程独立确认可选 Playwright/Docling 依赖缺失时才允许 skipped/exit 0。
- normal fixture 的 confirmed challenge 失败；专用 challenge-control 必须观察到 confirmed。旧 comparison oracle 中 challenge 会优先进入 challenge bucket，不再被 all-success 掩盖。
- summary 不持久化 raw ledger/raw token/header，只保存 case 派生状态、计数、布尔与 digest 安全事实；safe URL 不含 query。

## 5. Tests 与 validation results

| 命令 | 结果 |
| --- | --- |
| `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "diagnostic or log or redaction"` | PASS：8 passed，114 deselected。 |
| `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q` | PASS：29 passed。 |
| `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q` | PASS：37 passed；仅 3 条既有 edgar deprecation warnings。 |
| `source .venv/bin/activate && pytest tests/tools/web -q` | PASS：186 passed，2 skipped；仅 3 条既有 edgar deprecation warnings。 |
| `source .venv/bin/activate && pytest tests/tools/web -q --cov=dayu.tools.web.web_diagnostics --cov-report=term-missing` | **环境/工具链失败，exit 2**：pytest-cov 用 dotted source 在 collection 前导入 eager `dayu.tools.web` package，随后测试收集再次进入 pandas/NumPy，当前 Python/NumPy 环境报 `ImportError: cannot load module more than once per process`。未修改非白名单 `dayu/tools/web/__init__.py` 规避。 |
| `source .venv/bin/activate && coverage run -m pytest tests/tools/web -q` | 等价不预导入 dotted package 的复核 PASS：186 passed，2 skipped。 |
| `source .venv/bin/activate && coverage report -m dayu/tools/web/web_diagnostics.py` | 新 owner 模块 175 statements、18 missing、**90%**，满足单文件 >=80% 门槛。 |
| `source .venv/bin/activate && pyright` | PASS：0 errors，0 warnings，0 informations。 |
| `source .venv/bin/activate && git diff --check` | PASS。 |
| `source .venv/bin/activate && python utils/smoke_web_ci.py --output-dir workspace/tmp/r3e-s3-final-smoke --include-playwright --external-limit 0 --run-label r3e-s3-final` | PASS：7 local passed，0 failures，0 skips，4 search diagnostic-only，exit 0。 |

覆盖率指定命令的失败发生在 test collection/import 层，替代执行对同一测试集合和同一文件采集到 90%；因此它不表示 S3 product/test failure，但作为 validation tooling residual 原样保留，不宣称该精确 invocation 已通过。

## 6. README decision

测试文件发生变化，触发 `tests/README.md` 检查。阅读其 `Agent 更新约束` 后，确认 diagnostic schema v2、storage lifecycle、parent ledger 与 live smoke hard-gate 规则属于该 README 面向测试维护者的职责，因此已更新相关 Web test/smoke 段落。

本轮没有产品安装、初始化、正式 CLI/Web/WeChat 入口或分层装配变化，不触发根 `README.md` / `dayu/README.md`；没有修改 Engine、Host、Fins、Config 或 Documents 生产目录，不触发其 README。

## 7. Residual risks（分类）

| 分类 | residual | owner / destination | 当前裁决 |
| --- | --- | --- | --- |
| accepted contract limitation | SIGKILL/主机崩溃可能留下 owner temp 或尚未过期 final。 | `utils/diagnose_web_access.py` storage-state lifecycle；当前 destination 为 startup reconciliation + TTL。若未来要求无下次启动也强制删除，应进入独立 secure-artifact cleanup WU。 | S3 不作虚假即时 cleanup 承诺。 |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测；敏感 header value 因此不计算 digest，只记录 presence。 | `dayu.tools.web.web_diagnostics`。 | digest 仅用于 deterministic fixture/内容关联，不是机密保护承诺。 |
| low operational residual | Playwright API 不提供 response body streaming iterator；local/private diagnostic 先按 Content-Length 早拒绝，再对实际 `response.body()` bytes 强制 budget 后验校验。 | `utils/diagnose_web_access.py` diagnostic Playwright profile；若上游提供 streaming transport，再迁移到流式 owner。 | 超限 bytes 不会得到成功 artifact/PASS；不扩大为 S2 或通用资源框架。 |
| validation tooling residual | pytest-cov dotted source 在当前 eager package + NumPy 环境触发同进程重复加载。 | 仓库 coverage invocation/toolchain；不属于 S3 owner。 | 保留失败证据；等价 coverage 流程证明新增模块 90%。不越界修改 package initializer。 |
| accepted external boundary | 外部 live URL/search provider 仍受网络与凭据影响。 | `utils/smoke_web_ci.py` external/search diagnostic-only classifier。 | 不作为 local hard PASS oracle。 |

## 8. Explicit exclusions / handoff

- 未修改 `dayu/tools/web/web_egress_policy.py`，未扩展 S1 egress policy。
- 未携带 S2 codec/challenge/parser implementation；本轮只消费其已接受 contract，并更新旧 smoke/diagnostic oracle。
- 未修改或进入 S4 Documents、`dayu.tools.doc_tools`、`dayu.documents`。
- 未新增通用 tool-security framework；未实施 upload allowlist、SSRF policy framework、TLS policy、symlink-safe upload 或 LLM-facing security schema。
- 未进入 aggregate、code review 或 final closeout。
- 未 commit，未 push。

