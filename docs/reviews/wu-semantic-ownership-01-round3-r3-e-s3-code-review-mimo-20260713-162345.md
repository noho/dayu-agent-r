# R3-E Slice S3 Code Review（AgentMiMo）

## Scope

- Mode: current changes (S3 diff only)
- Branch: `phaseflow/host-issues-control`
- Base: uncommitted S3 diff
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-mimo-20260713-162345.md`
- Included scope:
  - `dayu/tools/web/web_diagnostics.py`（新增）
  - `dayu/tools/web/web_fetch_orchestrator.py`（diagnostic context 变更）
  - `dayu/tools/web/web_playwright_backend.py`（diagnostic projection 变更）
  - `dayu/tools/web/web_tools.py`（diagnostic logging 变更）
  - `utils/diagnose_web_access.py`（schema v2、storage-state lifecycle）
  - `utils/smoke_web_ci.py`（ledger、negative controls、classifier）
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/tools/web/test_diagnose_web_access.py`
  - `tests/tools/web/test_smoke_web_ci.py`
  - `tests/README.md`
  - S3 artifacts
- Excluded scope: S4 Documents、dayu.tools.doc_tools、dayu.documents、Host/Engine/Fins、tool-security framework、egress policy expansion、aggregate
- Parallel review coverage: 5 个 subagent 并行审查（WebDiagnosticProjection、storage-state lifecycle、smoke ledger、tests/README、Playwright backend）

## Findings

### 001-未修复-高-`final_url` 在 LLM-facing 工具结果中未经 safe projection

- **入口/函数**: `_fetch_web_page_with_requests` (web_tools.py)、`_build_playwright_success_payload` (web_tools.py)
- **文件(行号)**:
  - `web_fetch_orchestrator.py:1617,1689` — `response_url = str(response.url or current_url)` 作为 `"final_url"` 返回
  - `web_tools.py:2380` — `"final_url": fetch_result.get("final_url", url)` 进入 LLM-facing success payload
  - `web_playwright_backend.py:1505,1520` — `final_url = page.url` 作为 `"final_url"` 返回
- **输入场景**: 任何经过 redirect 的 fetch 请求，或目标 URL 含 userinfo/query token/fragment
- **实际分支**: success payload 构造处直接使用原始 `response.url` / `page.url`
- **预期行为**: LLM-facing 工具结果中的 `final_url` 应通过 `project_safe_url_or_empty()` 投影，与诊断日志保持一致
- **实际行为**: 诊断日志（line 2387-2399）正确使用 `completed_text_projection` 投影为 safe URL，但工具结果本身（line 2378-2386）的 `final_url` 是原始 URL，可能包含 userinfo、query token 或 fragment
- **直接证据**:
  - `web_tools.py:2380` — `"final_url": fetch_result.get("final_url", url)` 未经投影
  - `web_tools.py:2387-2399` — 同一函数内诊断日志使用 `completed_text_projection` 投影
  - `web_fetch_orchestrator.py:1617` — `response_url = str(response.url or current_url)` 是原始 URL
- **影响**: 若 redirect 链中目标 URL 含 userinfo、query token 或 fragment，这些敏感值会直接暴露给 LLM。这是语义所有权漂移：`WebDiagnosticProjection.project_safe_url()` 是 safe URL 的唯一 owner，但 LLM-facing 工具结果绕过了它
- **建议改法和验证点**:
  - 在 `web_tools.py` 的 success payload 构造处（line 2378-2386），将 `final_url` 通过 `project_safe_url_or_empty()` 投影后再写入
  - Playwright 路径同理，在 `_build_playwright_success_payload` 或 `_playwright_sync_worker` 返回前投影
  - 验证：构造含 userinfo/query token 的 URL 作为 fetch 目标，验证工具返回值中 `final_url` 不含敏感值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 002-未修复中-`_raise_fetch_failure` 的 `internal_diagnostics` 参数被静默覆盖

- **入口/函数**: `_raise_fetch_failure` (web_tools.py)
- **文件(行号)**: `web_tools.py:1171-1222`
- **输入场景**: 调用方传入 `internal_diagnostics` 参数（如 line 2058-2063 的 timeout 路径）
- **实际分支**: line 1221 用 `projection.to_json()` 覆盖了调用方传入的值
- **预期行为**: 函数签名承诺接收 `internal_diagnostics` 参数，应将其合并到投影结果中或明确拒绝
- **实际行为**: 调用方传入的 `internal_diagnostics`（含 `warmup`、`content_type_probe`、`applied_storage_state_cookie_count` 等）被完全丢弃，`ToolBusinessError` 接收的是 `projection.to_json()`
- **直接证据**:
  - `web_tools.py:1179` — 签名声明 `internal_diagnostics: WebMapping | None = None`
  - `web_tools.py:2058-2063` — 调用方传入丰富调试上下文
  - `web_tools.py:1221` — `internal_diagnostics=projection.to_json()` 覆盖调用方值
- **影响**: 接口契约违反；调用方花费计算成本构造诊断数据，这些数据被静默丢弃。若将来有人期望这些诊断数据出现在日志 artifact 中，会发现它们不存在
- **建议改法和验证点**:
  - 方案 A：在 `_raise_fetch_failure` 签名中移除 `internal_diagnostics` 参数以消除误导
  - 方案 B：将调用方数据合并到投影结果中（仅保留已投影过的字段如 `safe_url`、`response_headers.to_json()` 等）
  - 验证：搜索所有 `_raise_fetch_failure` 调用点，确认传入的 `internal_diagnostics` 字段是否确实被丢弃
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 003-未修复中-`publish` 中 `os.replace` 成功后 `published=True` 前的 chmod 失败导致 final 残留

- **入口/函数**: `_StorageStateLifecycle.publish` (diagnose_web_access.py)
- **文件(行号)**: `utils/diagnose_web_access.py:305-318`
- **输入场景**: `os.replace` 成功后 `os.chmod` 抛异常（如权限问题）
- **实际分支**: 时序为 `os.replace` → `self.temp_path = None` → `os.chmod`（可能失败）→ `self.published = True`
- **预期行为**: `os.replace` 成功后，`self.published` 应立即为 True，确保 `cleanup_failure()` 能删除 final
- **实际行为**: 如果 `os.chmod` 在 line 314 抛异常，`self.published` 仍为 False。调用方的 `cleanup_failure()` 检查 `self.published`（为 False），不会删除 final。最终残留一个权限可能不正确的 final 文件
- **直接证据**:
  - `utils/diagnose_web_access.py:312` — `os.replace(temp_path, final_path)` 成功
  - `utils/diagnose_web_access.py:313` — `self.temp_path = None`
  - `utils/diagnose_web_access.py:314` — `os.chmod(final_path, _PRIVATE_FILE_MODE)` 可能失败
  - `utils/diagnose_web_access.py:315` — `self.published = True` 不会执行
  - `utils/diagnose_web_access.py:320-334` — `cleanup_failure()` 检查 `self.published`
- **影响**: chmod 失败时 final 文件残留在磁盘上，`cleanup_failure()` 无法清理
- **建议改法和验证点**:
  - 将 `self.published = True` 移到 `os.replace` 之后、`os.chmod` 之前：
    ```python
    os.replace(temp_path, final_path)
    self.temp_path = None
    self.published = True
    os.chmod(final_path, _PRIVATE_FILE_MODE)
    ```
  - 验证：monkeypatch `os.chmod` 使其在 `os.replace` 之后抛异常，断言 `cleanup_failure` 能删除 final 文件
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 004-未修复低-`_ensure_private_storage_directory` 零测试覆盖

- **入口/函数**: `_ensure_private_storage_directory` (diagnose_web_access.py)
- **文件(行号)**: `utils/diagnose_web_access.py:1999-2020`
- **输入场景**: storage-state 目录创建路径
- **实际分支**: 三种路径（新建目录、已存在合规目录、已存在不合规目录拒绝）均无测试断言
- **预期行为**: 关键安全边界函数应有测试覆盖
- **实际行为**: 测试文件中没有任何引用 `_ensure_private_storage_directory`
- **直接证据**: `grep -r "_ensure_private_storage_directory" tests/` 返回零结果
- **影响**: 目录权限 0700 校验逻辑未被测试保护，回归风险
- **建议改法和验证点**:
  - 补充三个测试用例：
    1. 目录不存在时，创建并设为 0700
    2. 目录已存在且权限为 0700 时，不抛出
    3. 目录已存在但权限非 0700 时，抛出 `ValueError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 005-未修复低-NEGATIVE_METHOD 未纳入 ledger gap 校验

- **入口/函数**: `_fixture_ledger_gap` (smoke_web_ci.py)
- **文件(行号)**: `utils/smoke_web_ci.py:2337-2342`
- **输入场景**: smoke fixture ledger 校验
- **实际分支**: `required_negative_kinds` 只包含 4 种负控类型，不包含 `NEGATIVE_METHOD`
- **预期行为**: 所有负控类型都应在 ledger gap 校验范围内，或明确说明排除理由
- **实际行为**: `NEGATIVE_METHOD` 类型的负控没有被主动测试（`_exercise_pre_child_negative_controls` 只发送 GET 请求），也不在 `required_negative_kinds` 中
- **直接证据**:
  - `utils/smoke_web_ci.py:2337-2342` — `required_negative_kinds` 不含 `NEGATIVE_METHOD`
  - `utils/smoke_web_ci.py:1468-1487` — `_exercise_pre_child_negative_controls` 只发送 GET 请求
- **影响**: HEAD 请求会落入 `NEGATIVE_METHOD` 分支（handler 层 line 1289），但 ledger 不验证这一事实。当前不影响 PASS 判定，但属于契约完整性 gap
- **建议改法和验证点**:
  - 方案 A：在 `required_negative_kinds` 中加入 `NEGATIVE_METHOD`，并在 `_exercise_pre_child_negative_controls` 中额外发送一个 HEAD 请求
  - 方案 B：在 `_fixture_ledger_gap` docstring 中明确说明排除理由
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 006-未修复低-`mkdir(parents=True, mode=0o700)` 污染中间父目录权限

- **入口/函数**: `_ensure_private_storage_directory` (diagnose_web_access.py)
- **文件(行号)**: `utils/diagnose_web_access.py:2019`
- **输入场景**: `storage_state_dir` 是多层嵌套路径（如 `~/.dayu/storage_states/web/`）
- **实际分支**: `Path.mkdir(parents=True, mode=0o700)` 递归创建每一层中间目录，每层都应用 `0o700`
- **预期行为**: 只有最终目录应为 0700，中间父目录应使用默认权限
- **实际行为**: 中间目录也会被设为 0700，可能影响同父目录下其他进程或工具的访问
- **直接证据**: `utils/diagnose_web_access.py:2019` — `path.mkdir(parents=True, mode=_PRIVATE_DIRECTORY_MODE)`
- **影响**: 中间目录权限被意外收紧，可能影响其他工具访问
- **建议改法和验证点**:
  - 先以默认权限创建中间父目录，再单独以 0700 创建最终目录：
    ```python
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
    os.chmod(path, _PRIVATE_DIRECTORY_MODE)
    ```
  - 验证：构造三层嵌套路径 `tmp/a/b/c`，断言中间目录 `a`、`b` 的权限不是 0700
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 007-未修复低-challenge case 缺少 "decision 不是 confirmed 时必须失败" 的测试覆盖

- **入口/函数**: `_classify_loaded_artifact` (smoke_web_ci.py)
- **文件(行号)**: `tests/tools/web/test_smoke_web_ci.py:887-909`
- **输入场景**: challenge case 的 `challenge_decision` 不是 "confirmed"
- **实际分支**: 测试只覆盖了 "普通 case 被错误标记为 confirmed challenge 时必须失败"
- **预期行为**: 反向场景也应有测试覆盖
- **实际行为**: 没有测试覆盖 "challenge case 的 decision 不是 confirmed 时必须失败"
- **直接证据**: `_diagnostic_payload_for_case` (line 1647-1648) 对 `local_challenge_control` case 总是设置 `challenge_decision="confirmed"`
- **影响**: 如果 `_classify_loaded_artifact` 行 2614 的 `!= "confirmed"` 判断被删除或误改，不会有测试捕获这个 regression
- **建议改法和验证点**:
  - 增加一个测试用例：构造 challenge case 的 payload 但设置 `challenge_decision="none"`（或删除该字段），断言 `_classify_child_result` 返回 `status="failed"` 且 `bucket="challenge_control_failed"`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 008-未修复低-缺少 post-replace failure 的 cleanup 测试

- **入口/函数**: `_StorageStateLifecycle.publish` (diagnose_web_access.py)
- **文件(行号)**: `tests/tools/web/test_diagnose_web_access.py:302-331`
- **输入场景**: `os.replace` 成功后后续步骤失败（如 chmod 失败）
- **实际分支**: 现有测试 `test_storage_state_replace_failure_removes_run_temp` 只验证 replace 阶段失败
- **预期行为**: 应有测试覆盖 replace 成功后 cleanup_failure 删除 final 的场景
- **实际行为**: 测试矩阵缺少 post-replace failure 路径
- **直接证据**: 测试文件中无 post-replace failure 场景
- **影响**: Finding 003 中的 bug 未被测试保护
- **建议改法和验证点**:
  - 补充测试：replace 成功后模拟后续失败，验证 `cleanup_failure` 删除 final
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

| 分类 | residual | owner / destination | 当前裁决 |
| --- | --- | --- | --- |
| accepted contract limitation | SIGKILL/主机崩溃可能留下 owner temp 或尚未过期 final。 | `utils/diagnose_web_access.py` storage-state lifecycle；当前 destination 为 startup reconciliation + TTL。 | S3 不作虚假即时 cleanup 承诺。 |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测；敏感 header value 因此不计算 digest，只记录 presence。 | `dayu.tools.web.web_diagnostics`。 | digest 仅用于 deterministic fixture/内容关联，不是机密保护承诺。 |
| low operational residual | Playwright API 不提供 response body streaming iterator；local/private diagnostic 先按 Content-Length 早拒绝，再对实际 `response.body()` bytes 强制 budget 后验校验。 | `utils/diagnose_web_access.py` diagnostic Playwright profile；若上游提供 streaming transport，再迁移到流式 owner。 | 超限 bytes 不会得到成功 artifact/PASS；不扩大为 S2 或通用资源框架。 |
| validation tooling residual | pytest-cov dotted source 在当前 eager package + NumPy 环境触发同进程重复加载。 | 仓库 coverage invocation/toolchain；不属于 S3 owner。 | 保留失败证据；等价 coverage 流程证明新增模块 90%。不越界修改 package initializer。 |
| accepted external boundary | 外部 live URL/search provider 仍受网络与凭据影响。 | `utils/smoke_web_ci.py` external/search diagnostic-only classifier。 | 不作为 local hard PASS oracle。 |

## Verified Safe Patterns

以下审查点经 subagent 并行验证确认安全：

1. **WebDiagnosticProjection 唯一拥有 safe URL**: `project_safe_url()` 正确删除 userinfo/query/fragment，使用 `urlsplit` 解析后只重建 `scheme://authority/path`
2. **project_response_headers() 只记录 presence**: allowlist 只含 `cache-control`、`content-length`、`content-type`、`retry-after`；敏感 header 只记录 name，value 被丢弃
3. **failed_projection() 正确脱敏**: 提取 `sensitive_url_values(url)`，替换原始 URL 为 safe 版本，删除高熵 hex，调用 runtime redact primitive
4. **stdout/stderr 经 `content_diagnostic_from_text()` 投影**: 只产出 `WebContentDiagnostic(length, digest)`，不保存原文
5. **storage-state 默认零写入**: `final_path is None` 时 `publish` 直接 return，`output_enabled` 为 False
6. **显式 opt-in 才 atomic write**: 需要 `--storage-state-out` + 正 TTL，且 final 必须是 owner 命名
7. **flush/fsync/os.replace**: 标准 atomic write 模式
8. **startup owner-named cleanup**: 只扫描 `_STORAGE_STATE_TEMP_PREFIX`/`_STORAGE_STATE_FINAL_PREFIX` 命名的文件
9. **parent-owned fixture ledger 在 child 前注册**: `_running_local_fixture_server` 行 1386-1416
10. **server stop 后 freeze**: 行 1421-1425，`server.shutdown()` → `server_close()` → `join()` → `record_lifecycle("server_stopped")` → `freeze()`
11. **freeze 后才 classify**: `_run_local_cases` 行 3880-3894
12. **child/artifact producer 不能写 ledger**: `ParentFixtureLedger.freeze()` 行 446 设置 `_frozen=True`，`append()` 行 423 检查后抛出 `RuntimeError`
13. **PASS 基于 ledger + expected bytes + backend + negative controls**: `_classify_loaded_artifact` 行 2550-2633
14. **Playwright backend 三条异常路径统一经过 `failed_projection`**: safety error / 通用异常 / 超时
15. **Tests 断言 owner contract**: 覆盖 secret/projection/log、content/raw HTML/query/userinfo/headers/exception/network event、Docling query sentinel
16. **README 更新符合 reader boundary**: 保持在 tests/ 现有事实边界内

## S4/tool-security/egress-policy 越界确认

经全文件扫描确认：无 S4 Documents、tool-security framework、egress policy expansion 越界。所有变更保持在 S3 白名单文件内。

---

**Review 结论**: 发现 2 个中等严重度问题（002、003）和 1 个高严重度问题（001），其余为低优先级。建议修复 001-003 后再进入 S4。
