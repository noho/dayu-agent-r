# Code Review — R3-E Slice S3（AgentDS）

## Scope

- Mode: current changes（未提交 S3 diff only）
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`（未提交 working tree diff）
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-ds.md`
- Included scope:
  - `dayu/tools/web/web_diagnostics.py`（新增）
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `dayu/tools/web/web_tools.py`
  - `utils/diagnose_web_access.py`
  - `utils/smoke_web_ci.py`
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/tools/web/test_diagnose_web_access.py`
  - `tests/tools/web/test_smoke_web_ci.py`
  - `tests/README.md`
- Excluded scope: S4 Documents、`dayu.tools.doc_tools`、`dayu.documents`、Host/Engine/Fins、tool-security framework、egress policy expansion、aggregate
- Design truth: `docs/host/design.md`、`docs/engine/design.md`
- Control docs: `docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- Plan: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-controller-validation.md`

## Findings

### 1-未修复-低-_probe_content_type 中 HEAD 响应 body 的 content diagnostic 计算后未使用

- **入口/函数**: `_probe_content_type` → HEAD probe 成功路径
- **文件(行号)**: `dayu/tools/web/web_fetch_orchestrator.py:1372`
- **输入场景**: HEAD probe 成功返回（正常 HTTP HEAD 响应）
- **实际分支**: HEAD 方法成功路径（`lease = ...` → `with lease:` → 成功返回 dict）
- **预期行为**: HEAD probe 只返回 content_type / http_status 等探测信息；若需计算 body diagnostic 作为 caller 的 origin evidence，应将结果纳入返回 dict。
- **实际行为**: `response_content = content_diagnostic_from_bytes(bytes(response.content))` (1372行) 计算了响应体的 length+digest，但返回 dict (1373-1379行) 中未包含该值。变量被静默丢弃。
- **直接证据**:
  - 1372行：`response_content = content_diagnostic_from_bytes(bytes(response.content))` 完整读取 HEAD response body 并计算 diagnostic。
  - 1373-1379行：返回 dict 包含 `method`、`content_type`、`http_status`、`final_url`、`redirect_hops`、`ok`，**不含** `response_content`。
  - 对比 `_fetch_and_convert_content` 中 1616行同样计算 `response_content`，而 1692-1693行正确将其投影到返回 dict 的 `response_content_length` / `response_content_digest`。
- **影响**: HEAD response body（通常为空 bytes）被不必要地完整读取并计算 SHA-256，但计算结果被丢弃。不造成安全风险或错误行为，但属于浪费的 I/O 与计算。对正常 HEAD 响应（空 body）影响可忽略；若遇到非标准 HEAD 响应返回非空 body，浪费稍大但仍不影响调用方行为。
- **建议改法和验证点**: 删除 1372行的 `response_content = ...` 赋值，或在返回 dict 中增加 `response_content_length` / `response_content_digest` 并同步更新所有 consumer（当前 HEAD probe consumer 为 `_fetch_and_convert_content` 中 `probe.get(...)` 读取）。建议删除更简单，因为 HEAD probe 本就不应读取 body。
- **修复风险（低）**: 删除该行不影响任何 consumer——当前无 consumer 读取 HEAD probe 返回值的 body diagnostic 字段。
- **严重程度（低）**: 死赋值，不影响 correctness 或 security。

### 2-已通过-WebDiagnosticProjection 唯一拥有 safe URL/content/header/error/network event 投影

- **审查结论**: PASS

**证据**:

1. `WebDiagnosticProjection` (`dayu/tools/web/web_diagnostics.py:149-247`) 是唯一投影 owner。`to_json()` (207行) 明确注释 `ok` 仅是 producer observation，consumer 不得用它单独签发 PASS。completed outcome 强制 backend + content；正文只输出 `content_length` / `content_digest`。

2. `project_safe_url()` (250-278行) 只输出 `scheme + IDNA host + explicit port + path`，删除 userinfo、query、fragment。非法输入抛 `ValueError`。

3. `project_response_headers()` (335-377行) 不保存任意 raw value：敏感 header（authorization、cookie、token 等）只记录名称存在性；Content-Type 只保留规范化 media type；Content-Length 只保留合法非负整数。

4. `failed_projection()` (532-593行) 删除 URL 本体和 userinfo/query values，替换高熵 hex token，经 `redact_sensitive_diagnostic_values` 脱敏后再有界截断。

5. `project_network_event()` (596-630行) 只包含 safe URL、method、resource type、status code，不含 request headers/body。

6. 全文扫描确认：`content_diagnostic_from_text()` / `content_diagnostic_from_bytes()` 只计算 length+digest，不保存原文 prefix。

7. `test_web_diagnostic_projection_removes_secret_content_url_headers_exception_and_network` (`tests/tools/web/test_web_tools_provider.py:103-157`) 独立验证了 sentinel 不出现在投影序列化结果中，且 `raw html`、`@example.com`、`?token=`、`#` 均不出现。

### 3-已通过-Producer paths 不再展开 success payload/raw content/response_excerpt

- **审查结论**: PASS

**证据**:

1. `_extract_response_snippet()` (`web_fetch_orchestrator.py`) 已删除。`_decode_bounded_body_excerpt()` 已删除。`_build_text_excerpt()` (`web_tools.py`) 已删除。

2. `_FetchContentRuntimeContext` (`web_fetch_orchestrator.py:140-149`) 的旧字段 `final_url: str`、`response_headers: dict[str, str]`、`response_excerpt: str`、`raw_content_text: str` 已替换为 `safe_final_url: str`、`response_headers: WebResponseHeaderProjection`、`content: WebContentDiagnostic`、`challenge_decision: BotChallengeDecision`、`challenge_signals: tuple[str, ...]`、`has_client_rendering_markers: bool`。

3. `_build_fetch_content_runtime_context()` (897-914行) 现在通过 `project_response_headers()` 和 `content_diagnostic_from_bytes()` 构造不可逆证据。

4. `_log_fetch_diagnostics()` (`web_tools.py:1252-1265`) 的签名从 `payload: WebMapping` 改为 `projection: WebDiagnosticProjection`，不再接受任意 payload dict。

5. `_raise_fetch_failure()` (`web_tools.py:1199-1226`) 不再构造含 `url`/`message` 原始字符串的 diagnostics dict；改用 `failed_projection()` 构造安全投影，`internal_diagnostics` 使用 `projection.to_json()`。

6. `_fetch_web_page_business()` 的成功路径 (2381-2401行) 不再把 `success` dict 展开为 log payload；改用 `completed_text_projection()` 只记录长度+摘要。

7. `web_playwright_backend.py` 的异常处理 (532-551行) 使用 `failed_projection()` 的错误消息而非原始 `str(exc)`；`blocked_url` 使用 `project_safe_url_or_empty()` 而非原始 URL。

8. 全文扫描：`response_excerpt`、`raw_content_text`、`html_prefix`、`content_prefix` 在生产代码中均已移除。仅 `utils/smoke_web_ci.py:1926-1931` 的 `_legacy_diagnostic_field()` 中以 denylist 形式保留这些字段名用于拒绝旧 schema artifact。

### 4-已通过-Diagnostic schema v2 producer 与 smoke consumer 同步迁移，旧 schema fail closed

- **审查结论**: PASS

**证据**:

1. `WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"` / `WEB_DIAGNOSTIC_SCHEMA_REVISION = 2` (`web_diagnostics.py:25-29`) 是唯一真源。

2. `utils/diagnose_web_access.py` 的 `_SCHEMA_VERSION` / `_DIAGNOSTIC_SCHEMA_REVISION` (77-78行) 直接从 `web_diagnostics` 常量导入。

3. `utils/smoke_web_ci.py` 的 `_DIAGNOSTIC_SCHEMA_VERSION` / `_MIN_DIAGNOSTIC_SCHEMA_REVISION` (64-65行) 同样从 `web_diagnostics` 常量导入。

4. `_diagnostic_schema_gap()` (`smoke_web_ci.py:1875-1909`) 精确校验 version/revision，不匹配立即返回 gap 描述（非空字符串），无 fallback 到旧 schema。

5. `_legacy_diagnostic_field()` (`smoke_web_ci.py:1912-1945`) 递归拒绝 `content_prefix`、`html_prefix`、`page_text_prefix`、`stderr_prefix`、`stdout_prefix`、`text_prefix` 字段——任何 profile/嵌套层级出现即 fail closed。

6. `_profile_schema_gap()` (`smoke_web_ci.py:1948-1999`) 要求 completed profile 的 `content_length` 为非负整数、`content_digest` 为 `sha256:<64hex>` 格式、`http_status` 必须存在。

7. 测试验证：`test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` (`test_smoke_web_ci.py:564-657`) 中 old schema (`web-diagnostics-v1`) artifact 被正确分入 `diagnostic_schema_gap` bucket。

8. 旧字段扫描：`rg -n "response_excerpt|content_prefix|html_prefix|body_prefix|stdout_prefix|stderr_prefix|web-diagnostics-v1|schema_version.*v1"` 在生产代码 `dayu/tools/web/` 和 `utils/diagnose_web_access.py` 中均为零命中；仅在 smoke 的 denylist 中出现，符合预期。

### 5-已通过-Storage-state lifecycle 默认零写入、显式 opt-in atomic write、权限/TTL/cleanup/reconciliation

- **审查结论**: PASS

**证据**:

1. 默认零写入：`_resolve_storage_state_paths()` (`diagnose_web_access.py:1964-1996`) 只在显式 `--storage-state-out` 非空时启用输出；`storage_state_dir` 只解析已有 owner 命名输入，不隐式启用输出 (1980-1984行)。若 `--storage-state-ttl-seconds` 不为零但没有 `--storage-state-out`，抛 `ValueError` (1994-1995行)。

2. Atomic write：`_StorageStateLifecycle.publish()` (271-318行) 使用 `os.open(temp_path, O_WRONLY | O_CREAT | O_EXCL, 0o600)` → `flush()` → `os.fsync()` → `os.chmod(temp, 0o600)` → `os.replace(temp, final)` → `os.chmod(final, 0o600)`。没有直接写 final path。

3. 权限：`_ensure_private_storage_directory()` (1999-2020行) 新目录创建为 `0o700`；已存在目录必须预先 `0o700`，不修改共享目录。temp/final 文件均为 `0o600`。

4. TTL：`_reconcile_storage_state_directory()` (2023-2060行) 按 `st_mtime + ttl_seconds <= now` 删除过期 final；只扫描 owner prefix/suffix (`_STORAGE_STATE_FINAL_PREFIX` / `_STORAGE_STATE_TEMP_PREFIX`)。

5. Failure/cancel cleanup：`cleanup_failure()` (320-336行) 删除本 run temp 和已发布 final。`_build_playwright_profile` 的 `except Exception` (2502行) 和 `except BaseException` (2519行) 均调用 `storage_lifecycle.cleanup_failure()`。

6. Startup reconciliation：`_prepare_storage_state_lifecycle()` (2063-2097行) 在 opt-in 时调用 `_reconcile_storage_state_directory()`。

7. 不承诺 SIGKILL：文档和代码中无 SIGKILL cleanup 承诺。Implementation artifact 明确记录为 accepted contract limitation。

8. 测试验证：
   - `test_storage_state_default_publish_is_zero_write` — 未 opt-in 时无目录/temp/final 创建。
   - `test_storage_state_atomic_publish_permissions_and_cleanup` — 验证 0700/0600、fsync、os.replace、cleanup 删除 final。
   - `test_storage_state_replace_failure_removes_run_temp` — 验证 publish 失败后 temp 被清理、final 不存在。
   - `test_storage_state_cancel_path_cleans_temp_and_published_final` — 验证 KeyboardInterrupt 路径 cleanup。
   - `test_storage_state_startup_reconciliation_is_owner_scoped_and_ttl_bounded` — 验证孤儿 temp 删除、过期 final 删除、fresh/unrelated 文件保留。

### 6-已通过-Smoke parent-owned fixture ledger lifecycle、freeze-before-classify、独立 PASS oracle

- **审查结论**: PASS

**证据**:

1. Parent-owned ledger：`ParentFixtureLedger` (`smoke_web_ci.py:365-451`) 由 `_running_local_fixture_server()` (1372-1425行) 在 context manager 入口创建，与 `_LocalFixtureServer` 共生。handler (`_LocalFixtureRequestHandler.do_GET`, 1130行) 只通过 `_append_fixture_observation()` 向 ledger 追加 typed observation。

2. Child 前注册、server 停止后 freeze、freeze 后 classify：
   - `_running_local_fixture_server()` 在 `yield session` 前创建 ledger 并注册 cases (1386-1410行)。
   - `finally` 块中先 `server.shutdown()` / `server.server_close()` / `thread.join()`，再 `ledger.record_lifecycle("server_stopped")`，最后 `ledger.freeze()` (1421-1425行)。
   - `_fixture_ledger_gap()` (2290-2347行) 要求 `ledger.lifecycle[-2:] == ("server_stopped", "frozen")`。
   - `_classify_child_result()` → `_classify_loaded_artifact()` 只在取得 frozen ledger 后运行。

3. Child/artifact producer 不能写 ledger：ledger 是父进程内存对象，不暴露给子进程；handler 只追加 observation，不接受 child 的任意写入。

4. PASS 必要条件（`_classify_loaded_artifact`, 2407-2663行）：
   - `child_returncode == 0` (非 PDF Docling skip 或 browser package missing 时)
   - `_diagnostic_schema_gap()` 返回空
   - `_fixture_ledger_gap()` 返回空（唯一 accepted request + response kind/digest 匹配 + 全部负控被拒绝）
   - `_exact_response_artifact_gap()` 返回空（artifact content_length/digest == 父进程 expected bytes）
   - `backend` 匹配 `fixture_case.expected_backend`
   - 非 challenge control 时 `challenge_decision != "confirmed"`
   - challenge control 时 `challenge_decision == "confirmed"`

5. 每 case 独立 256-bit token：`_new_fixture_case()` (878-894行) 使用 `secrets.token_hex(32)` 生成 token。`test_fixture_session_owns_unique_sentinels_negative_controls_and_freeze_order` (52-93行) 验证每个 case token 唯一且长度 64。

6. Ledger 不可变：`freeze()` 后 `append()` / `record_lifecycle()` 抛 `RuntimeError`。测试验证 (`test_smoke_web_ci.py:90-91`)。

7. Summary 不持久化 raw ledger/token/header：`SmokeCaseResult.to_json()` (677-699行) 只保存 case_name、case_kind、url（已 safe）、status、bucket、evidence_path、suggested_next_step、reason、exit_code。

### 7-已通过-Negative controls 覆盖 missing/wrong/replay/unknown path、synthetic ok、wrong backend、browser missing 独立确认、Docling skip

- **审查结论**: PASS

**证据**:

1. Missing token negative control：`_exercise_pre_child_negative_controls()` (1468-1487行) 发送空 token 请求 → `_handle_fixture_request()` 中 `not token` → `NEGATIVE_MISSING_TOKEN`。

2. Wrong token negative control：发送 `secrets.token_hex(32)` 新 token → `matched_case is None` → `NEGATIVE_WRONG_TOKEN`。

3. Unknown path negative control：发送 `_LOCAL_NEGATIVE_PATH` → `not path_cases` → `NEGATIVE_UNKNOWN_PATH`。

4. Replay negative control：`_exercise_post_child_replay_control()` (1490-1503行) 在 child 返回后用同一 token 重放 → `token_digest in server.accepted_token_digests` → `NEGATIVE_REPLAY_TOKEN`。

5. `_fixture_ledger_gap()` (2337-2347行) 要求全部四种 negative kind 均出现在 rejected observations 中，任一缺失即返回 gap。

6. Synthetic ok 不能 PASS：`test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` 中 synthetic artifact 无 frozen ledger → `fixture_ledger_gap` failure。

7. Wrong digest/length 不能 PASS：同一测试中 wrong digest 被分入 `content_oracle_mismatch`。

8. Wrong backend 不能 PASS：`_classify_loaded_artifact` 2598行检查 `backend != expected_backend` → failure。

9. Browser missing 独立确认：`_playwright_package_missing_independently()` (2375-2388行) 由父进程使用 `importlib.util.find_spec("playwright")` 独立判断。`test_browser_package_missing_is_independently_verified_skip` (712-749行) 验证该路径为 skip/exit 0。

10. Docling skip 独立确认：`_docling_package_missing_independently()` (2391-2404行) 同样由父进程独立判断。

11. Challenge+ok 不能 all_success：`_classify_diagnostic_bucket()` (2613-2673行) 在 `playwright_sampled and challenge_detected` 时优先返回 `playwright_challenge_detected`，不会落入 `all_success`。`test_comparison_bucket_matrix` 验证了 challenge detected 场景映射到 `playwright_challenge_detected`。

### 8-已通过-Tests 断言 owner contract，不保留旧偶然行为

- **审查结论**: PASS

**证据**:

1. 旧测试 fixture 中 `response_excerpt` 字段已全部移除：`test_fetch_private_url_can_be_allowed_with_explicit_config` (2394行)、`test_fetch_playwright_fallback_receives_channel_and_storage_state_path` (4701行)、`test_web_provider_serializes_search_and_fetch_business` (4991行) 等均不再包含 `response_excerpt`。

2. 旧 `status` 字段断言已迁移为 `outcome`：`test_requests_profile_closes_session_on_request_exception` (606行) 从 `profile["status"] == "request_exception"` 改为 `profile["outcome"] == "failed"` + `profile["error_code"] == "request_exception"`。

3. 旧 header redaction 测试已迁移为 header projection 测试：`test_header_projection_never_persists_raw_values` (501-525行) 从断言 `redacted["Authorization"] == "<redacted>"` 改为断言 `redacted["sensitive_names"] == [...]` 且 secret 值不在序列化结果中。

4. 旧 browser diagnostic-only 行为已改为 failure：`test_local_browser_case_without_playwright_execution_is_failure` (680-709行) 验证缺少 Playwright execution evidence 时 status 为 `failed` 而非 `diagnostic_only`。

5. Old schema 测试从"兼容"变为"拒绝"：`test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` 中 v1 schema artifact 被分入 `diagnostic_schema_gap` failure。

6. 旧 `challenge+ok -> all_success` 行为已修正：challenge detected 优先进入 `playwright_challenge_detected` bucket。

7. 测试覆盖率：`web_diagnostics.py` 90%（186 passed, 2 skipped），满足 >=80% 单文件门槛。

### 9-已通过-README 更新符合 tests/README reader boundary

- **审查结论**: PASS

**证据**:

`tests/README.md` 的变更仅修改了两处：
1. Web tools provider 测试描述 (175行)：新增 "Web diagnostic schema v2 对正文/HTML/stdio 只保留 length + digest、safe URL 删除 userinfo/query/fragment、响应头只保留存在性与受限语义、storage state 默认零写入及显式 opt-in 的原子发布/权限/TTL/startup reconciliation" 说明。
2. Web live smoke 段落 (178行)：更新为描述父进程内存 ledger、256-bit query sentinel、freeze-before-classify、负控等新的 smoke oracle 机制。

两处修改均在 tests/README.md 面向"测试维护者"的职责范围内。未修改根 README、dayu/README 或其他 README，与 plan §10 的 README trigger 决策一致。

### 10-已通过-确认没有 S4/tool-security/egress-policy 越界

- **审查结论**: PASS

**证据**:

1. `dayu/tools/web/web_egress_policy.py` 不在当前 diff 中——对照 `git diff HEAD --stat` 和 implementation artifact §8 的 explicit exclusions。

2. `dayu/tools/doc_tools.py`、`dayu/documents/` 不在 diff 中——S4 Documents scope 未被触及。

3. 未新增通用 tool-security framework、upload allowlist、SSRF policy framework、TLS policy、symlink-safe upload 或 LLM-facing security schema。

4. Host/Engine/Fins 文件不在 diff 中。

5. `rg -n "tool[-_ ]security|upload allowlist|SSRF|symlink-safe|security schema|file authority"` 在生产 diff 文件中零命中（仅 implementation artifact 中作为 explicit exclusion 声明出现）。

## Open Questions

无。

## Residual Risk

| 分类 | residual | owner | 当前裁决 |
| --- | --- | --- | --- |
| accepted contract limitation | SIGKILL/主机崩溃可能留下 owner temp 或尚未过期 final | `utils/diagnose_web_access.py` storage-state lifecycle | S3 不作虚假即时 cleanup 承诺；startup reconciliation + TTL |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测 | `dayu.tools.web.web_diagnostics` | digest 仅用于 deterministic fixture/内容关联，非机密保护承诺 |
| low operational residual | Playwright API 不提供 response body streaming iterator | `utils/diagnose_web_access.py` diagnostic Playwright profile | 先 Content-Length 早拒绝，再后验 actual bytes budget |
| validation tooling residual | pytest-cov dotted source 在当前 eager package + NumPy 环境触发同进程重复加载 | 仓库 coverage invocation/toolchain | 等价 coverage 流程证明新增模块 90%；不越界修改 package initializer |
| accepted external boundary | 外部 live URL/search provider 仍受网络与凭据影响 | `utils/smoke_web_ci.py` external/search diagnostic-only classifier | 不作为 local hard PASS oracle |

以上 residual risks 均已在 implementation artifact §7 和 controller validation §Residual classification 中记录，本轮 code review 无新增 risk。

## Completion Report

- **Review result**: 1 finding（低严重度），9 项 checkpoint 全部 PASS。
- **Material findings**: 无。唯一 finding（`_probe_content_type` 死赋值）不影响 correctness、security 或 stability。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-ds.md`
- **Ready for**: Controller adjudication → S4 / aggregate / closeout。
