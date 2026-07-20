# Code Re-Review — R3-E Slice S3 After Fix（AgentDS）

## Scope

- Mode: current changes（未提交 S3 diff after fix）
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`（未提交 working tree diff）
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-rereview-ds.md`
- Reviewed fix batch: F01–F09（controller-adjudicated, codex-implemented, controller-validated）
- Control truth:
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-codex.md`
  - Fix controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-controller-validation.md`
- Plan / Design truth: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`, `docs/host/design.md`, `docs/engine/design.md`
- Included scope: `dayu/tools/web/web_diagnostics.py`, `web_fetch_orchestrator.py`, `web_playwright_backend.py`, `web_tools.py`, `utils/diagnose_web_access.py`, `utils/smoke_web_ci.py`, `tests/tools/web/test_web_tools_provider.py`, `tests/tools/web/test_diagnose_web_access.py`, `tests/tools/web/test_smoke_web_ci.py`, `tests/README.md`
- Excluded scope: S4 Documents、Host/Engine/Fins、`web_egress_policy.py`、tool-security implementation

## Findings

**未发现实质性问题。**

所有 9 个 accepted findings (F01–F09) 均已正确修复，无引入新 correctness / semantic ownership / boundary / test regression。

## Finding Closure Verification

### R3-E-S3-CR-F01：LLM-facing `final_url` 安全投影 — 已关闭

- **Playwright success path**: `_build_playwright_success_payload()` (`web_tools.py:890-894`) 对 `pw_result["final_url"]` 调用 `project_safe_url_or_empty()`。
- **Requests success path**: `_fetch_web_page_business()` 成功 payload (`web_tools.py:2270-2272`) 对 `fetch_result["final_url"]` 调用 `project_safe_url_or_empty()`。
- **Test**: `test_playwright_success_final_url_uses_safe_projection` (`test_web_tools_provider.py:168-185`) 使用含 userinfo、256-bit query token、fragment 的 raw final URL，断言 `final_url == "https://example.com/report"` 且 sentinel 零命中。
- **直接证据**: 两个 LLM-facing success payload 的 `final_url` 字段均已从 raw URL 改为 safe projection。

### R3-E-S3-CR-F02：`_raise_fetch_failure` 不接受任意 caller diagnostics — 已关闭

- **Signature**: `_raise_fetch_failure()` (`web_tools.py:1179-1187`) 不再接受 `internal_diagnostics` 参数。
- **唯一 internal_diagnostics 来源**: `ToolBusinessError(internal_diagnostics=projection.to_json())` (`web_tools.py:1227`)，由 failure owner 的 `failed_projection()` 统一产生。
- **旧 call-site dict 清理**: 所有 `_raise_fetch_failure(...)` 调用不再构造含 `response_excerpt`、`final_url` raw 值等的 `internal_diagnostics={}`。
- **Test**: `test_raise_fetch_failure_accepts_only_owner_projection_inputs` (`test_web_tools_provider.py:188-206`) 使用 `inspect.signature` 锁定参数契约，并断言 error 的 `internal_diagnostics.safe_url` / `error_code` 来自 owner projection。
- **直接证据**: 无任意下游 dict 可绕过 failure projection owner 进入 `ToolBusinessError`。

### R3-E-S3-CR-F03/F08：storage-state post-replace cleanup — 已关闭

- **Ordering fix**: `_StorageStateLifecycle.publish()` (`diagnose_web_access.py:312-315`) 现在顺序为 `os.replace → temp_path=None → published=True → chmod(final)`。`published=True` 紧随 `os.replace` 成功。
- **Cleanup path**: `cleanup_failure()` (320-336行) 检查 `self.published` → 删除 `final_path`。两个 caller（`_build_playwright_profile` 的 `except Exception` 2505行和 `except BaseException` 2522行）均调用 `cleanup_failure()`。
- **Test**: `test_storage_state_post_replace_failure_marks_and_cleans_published_final` (`test_diagnose_web_access.py:400-435`) 用 monkeypatch 在 final `os.chmod` 时抛异常，证明 replace 已成功时 `published=True`、final 存在，随后 `cleanup_failure()` 删除 final 并复位状态。
- **直接证据**: post-replace failure 不再留下孤儿 final 文件。

### R3-E-S3-CR-F04：`_ensure_private_storage_directory` owner-contract tests — 已关闭

- **Test coverage**: 4 个新测试覆盖所有 contract 分支：
  - `test_ensure_private_storage_directory_accepts_existing_private_leaf` (255-265行)：已有 0700 目录原样接受。
  - `test_ensure_private_storage_directory_rejects_non_private_leaf` (268-278行)：已有非 0700 目录 fail closed。
  - `test_ensure_private_storage_directory_rejects_non_directory_path` (281-290行)：普通文件占用路径 fail closed。
  - `test_ensure_private_storage_directory_does_not_harden_intermediate_parents` (293-307行)：嵌套中间目录不变。
- **直接证据**: helper 的所有 public contract 分支均有独立测试。

### R3-E-S3-CR-F05：HEAD NEGATIVE_METHOD 加入 ledger gap contract — 已关闭

- **Pre-child exercise**: `_exercise_pre_child_negative_controls()` (`smoke_web_ci.py:1496`) 新增 `_send_negative_control_request(case.url, method=_HTTP_HEAD_METHOD)`。
- **Handler**: `_handle_fixture_request()` (`smoke_web_ci.py:1291`) 对非 GET method 设置 `NEGATIVE_METHOD`。
- **Ledger gap**: `_fixture_ledger_gap()` (`smoke_web_ci.py:2353`) 的 `required_negative_kinds` 已加入 `NEGATIVE_METHOD`。
- **Observation body**: HEAD negative control 的 response body 为空 bytes (`b""`)，digest 为 SHA-256("")——与 handler 实际对 HEAD 请求不写 body 的行为一致。
- **Live test**: `test_fixture_session_owns_unique_sentinels_negative_controls_and_freeze_order` (52-93行) 通过真实 local server + ledger 验证全部 5 种负控（含 NEGATIVE_METHOD）。
- **Synthetic test**: `test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` (627-645行) 用 `include_method_negative=False` 构造缺失 HEAD method 的 ledger，断言 `fixture_ledger_gap` failure。
- **Test helper**: `_frozen_ledger_for_case()` (`test_smoke_web_ci.py:1590-1655`) 新增 `include_method_negative` 参数，HEAD observation 使用 `method="HEAD"` 和空 bytes digest。
- **直接证据**: method negative control 从 exercise → handler → ledger gap → test 形成完整证据链。

### R3-E-S3-CR-F06：private directory 中间父目录权限 — 已关闭

- **Code**: `_ensure_private_storage_directory()` (`diagnose_web_access.py:2019-2023`) 先 `path.parent.mkdir(parents=True, exist_ok=True)` 用默认 umask 创建中间父目录，再 `path.mkdir(mode=0o700)` + `os.chmod(path, 0o700)` 只收紧 leaf。
- **Test**: `test_ensure_private_storage_directory_does_not_harden_intermediate_parents` (293-307行) 在确定性 `umask 022` 下创建嵌套路径 `tmp/shared/nested/private-state`，断言 shared/nested 为 0755，leaf 为 0700。
- **直接证据**: 中间目录不再被意外强制为 0700。

### R3-E-S3-CR-F07：challenge-control reverse decision test — 已关闭

- **Test**: `test_challenge_control_requires_confirmed_decision` (`test_smoke_web_ci.py:917-945`) 参数化 `challenge_decision ∈ {None, "none", "suspected"}`，全部断言 `status == "failed"` + `bucket == "challenge_control_failed"`。
- **Normal case guard**: `test_confirmed_challenge_cannot_pass_a_normal_local_case` (891-914行) 验证普通 case 含 `challenge_decision="confirmed"` 时失败。
- **直接证据**: challenge-control 的反向 oracle（必须 confirmed）和正向 guard（普通 case 不得 confirmed）均已覆盖。

### R3-E-S3-CR-F09：HEAD probe 死 body diagnostic 删除 — 已关闭

- **Code**: `_probe_content_type()` 的 HEAD 成功路径 (`web_fetch_orchestrator.py`) 不再包含 `response_content = content_diagnostic_from_bytes(bytes(response.content))`。
- **Scope**: `rg -n "response_content" dayu/tools/web/web_fetch_orchestrator.py` 只命中 main fetch path (1615行) 的有效使用与 `_infer_content_text` 的参数 (1426行)，无 HEAD probe 残留。
- **直接证据**: HEAD probe 不再做无意义的 body materialization。

## 回归检查

### 未引入新 correctness / semantic ownership / boundary / test regression

1. **LLM-facing final_url**: 两个 success payload path（requests + Playwright）均经过 `project_safe_url_or_empty()`，不会回退 raw URL。
2. **`_raise_fetch_failure`**: 不再接受 `internal_diagnostics` 参数；所有 15 个 call-site 均验证无该参数传入。
3. **`_FetchContentRuntimeContext`**: 字段 `challenge_decision`/`challenge_signals`/`has_client_rendering_markers` 在 construction 时固定，下游 consumer (`web_tools.py:2208-2210`) 直接读取，不重复调用 `detect_bot_challenge`，语义无漂移。
4. **`_send_negative_control_request`**: 新增 `method` keyword-only 参数，默认 `GET`，现有 GET call sites 不变。
5. **`_frozen_ledger_for_case`**: 新增 `include_method_negative` 参数，默认 `True`，现有 call sites 自动包含 NEGATIVE_METHOD observation。唯一显式 `include_method_negative=False` 的 call site 在 `missing-method-negative-control` 测试，正确预期 failure。
6. **storage-state lifecycle**: `published` 顺序变更不影响 success path（chmod 正常时行为相同），只影响 failure path（post-replace failure 现在可被 cleanup）。
7. **`_ensure_private_storage_directory`**: 中间目录使用 `path.parent.mkdir(parents=True, exist_ok=True)` 替代旧 `path.mkdir(parents=True, mode=0700)`，不影响成功路径（leaf 仍强制 0700），只修复了中间目录被意外收紧的 bug。

### Scope containment

`git diff HEAD --name-only` 仅包含 9 个 S3 文件，均属允许范围：
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

无 S4 Documents (`dayu.tools.doc_tools`, `dayu.documents`)、Host、Engine、Fins、`web_egress_policy.py` 或 tool-security implementation 越界。

### Old field scan

`rg "response_excerpt|_extract_response_snippet|_build_text_excerpt|raw_content_text|_decode_bounded_body_excerpt"` 在生产代码中零命中。`rg "content_prefix|html_prefix|text_prefix|stdout_prefix|stderr_prefix"` 在 `dayu/tools/web/` 和 `utils/diagnose_web_access.py` 中零命中。旧字段仅存在于 `utils/smoke_web_ci.py:1926-1931` 的 `_legacy_diagnostic_field` denylist（设计如此）。

## Open Questions

无。

## Residual Risk

与 implementation artifact §7 和 initial review 一致，无新增：

| 分类 | residual | owner |
| --- | --- | --- |
| accepted contract limitation | SIGKILL/主机崩溃可能留下 owner temp 或未过期 final | `utils/diagnose_web_access.py` — startup reconciliation + TTL |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测 | `dayu.tools.web.web_diagnostics` — digest 仅用于 deterministic fixture 关联 |
| low operational residual | Playwright API 不提供 streaming body iterator | `utils/diagnose_web_access.py` — Content-Length 早拒绝 + 后验 budget |
| validation tooling residual | pytest-cov dotted source 在当前环境触发同进程重复加载 | 仓库 coverage invocation — 等价 coverage 流程证明 90% |
| accepted external boundary | 外部 live URL/search provider 为 diagnostic-only | `utils/smoke_web_ci.py` |

本 fix batch 未改变任何 residual risk 的 owner 或 destination。

## Completion Report

- **Re-review result**: **PASS** — 无 material finding。
- **F01–F09 closure**: 全部 9 个 accepted findings 已正确关闭，含 direct code evidence 与 independent test coverage。
- **Regression**: 无引入新 correctness / semantic ownership / boundary / test regression。
- **Scope**: 无 S4 / Host / Engine / Fins / egress-policy / tool-security 越界。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-rereview-ds.md`
- **Ready for**: Controller final adjudication → S4 / aggregate / closeout。
