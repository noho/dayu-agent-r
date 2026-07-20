# R3-E Slice S3 Code Re-Review（AgentMiMo）

## Scope

- Mode: current changes (S3 diff after fix)
- Branch: `phaseflow/host-issues-control`
- Base: uncommitted S3 diff
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-rereview-mimo-20260713-164624.md`
- Included scope:
  - `dayu/tools/web/web_diagnostics.py`
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `dayu/tools/web/web_tools.py`
  - `utils/diagnose_web_access.py`
  - `utils/smoke_web_ci.py`
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/tools/web/test_diagnose_web_access.py`
  - `tests/tools/web/test_smoke_web_ci.py`
  - `tests/README.md`
  - S3 artifacts
- Excluded scope: S4 Documents、Host/Engine/Fins、`web_egress_policy.py`、tool-security framework
- Parallel review coverage: 2 个 subagent（F01-F09 逐项验证、scope/boundary 扫描）

## Reference Documents

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-codex.md`
- Fix controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-controller-validation.md`

## Finding Closure Verification

| Finding | 描述 | 状态 | Direct Evidence |
| --- | --- | --- | --- |
| F01 | LLM-facing `final_url` bypasses safe URL projection | **已关闭** | `web_tools.py:2268-2273` requests payload 使用 `project_safe_url_or_empty()`；`web_tools.py:890-898` Playwright payload 同理。测试 `test_playwright_success_final_url_uses_safe_projection` 和 `test_web_diagnostic_projection_removes_secret_content_url_headers_exception_and_network` 覆盖 userinfo/query/fragment 删除。 |
| F02 | `_raise_fetch_failure` accepts diagnostics it silently drops | **已关闭** | `web_tools.py:1179-1187` 签名不再含 `internal_diagnostics`。所有 ~15 处 call-site 只传 `url/error_code/message/hint/next_action/http_status`。`ToolBusinessError.internal_diagnostics` 只接收 `projection.to_json()`。测试 `test_raise_fetch_failure_accepts_only_owner_projection_inputs` 用 `inspect.signature` 锁定。 |
| F03/F08 | storage-state publish can leave final after post-replace failure | **已关闭** | `diagnose_web_access.py:312-315` 时序为 `os.replace → published=True → chmod(final)`。测试 `test_storage_state_post_replace_failure_marks_and_cleans_published_final` 模拟 chmod 失败，断言 `published is True` 且 `cleanup_failure()` 删除 final。 |
| F04 | private directory helper lacks owner-contract tests | **已关闭** | `test_diagnose_web_access.py:244-307` 覆盖新建目录 0700、已有合法 0700、非法 0755 拒绝、非目录路径拒绝四个场景。 |
| F05 | `NEGATIVE_METHOD` not part of smoke ledger gap | **已关闭** | `smoke_web_ci.py:1496` 发送 HEAD 请求；`smoke_web_ci.py:2349-2355` `required_negative_kinds` 包含 `NEGATIVE_METHOD`。集成测试验证 `_fixture_ledger_gap` 返回空。 |
| F06 | private directory creation applies 0700 to intermediate parents | **已关闭** | `diagnose_web_access.py:2019-2023` 先 `path.parent.mkdir(parents=True, exist_ok=True)`（默认 umask），再 `path.mkdir(mode=0700)` + `os.chmod`。测试 `test_ensure_private_storage_directory_does_not_harden_intermediate_parents` 断言中间目录 0755、leaf 0700。 |
| F07 | challenge-control reverse decision lacks test | **已关闭** | `test_smoke_web_ci.py:916-945` 参数化覆盖 `[None, "none", "suspected"]` 三种 decision，均断言 `failed / challenge_control_failed`。 |
| F09 | HEAD probe computes unused body diagnostic | **已关闭** | `web_fetch_orchestrator.py:1326-1418` `_probe_content_type` 不含 `response_content` 变量或 `content_diagnostic_from_bytes` 调用。 |

## Findings

未发现新实质性问题。

## Open Questions

无。

## Residual Risk

沿用 S3 implementation artifact 已记录的 accepted residual risks，无新增：

| 分类 | residual | owner / destination |
| --- | --- | --- |
| accepted contract limitation | SIGKILL/主机崩溃可能留下 owner temp 或尚未过期 final。 | `utils/diagnose_web_access.py` startup reconciliation + TTL。 |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测。 | `dayu.tools.web.web_diagnostics`，仅用于 fixture 关联。 |
| low operational residual | Playwright API 不提供 response body streaming iterator。 | `utils/diagnose_web_access.py` diagnostic Playwright profile。 |
| validation tooling residual | pytest-cov dotted source 在当前环境触发同进程重复加载。 | 仓库 coverage invocation toolchain；不属于 S3 owner。 |
| accepted external boundary | 外部 live URL/search provider 仍受网络与凭据影响。 | `utils/smoke_web_ci.py` external/search diagnostic-only classifier。 |

## Scope & Boundary Confirmation

- `git diff --name-only` 只包含 S3 允许的 10 个生产/测试/README 文件 + S3 artifacts。
- 无 S4 Documents（`dayu/documents/`、`dayu/tools/doc_tools.py`）。
- 无 Host/Engine/Fins 修改。
- 无 `dayu/tools/web/web_egress_policy.py` 修改或 egress policy 扩展。
- 无 tool-security、upload allowlist、SSRF、symlink-safe upload、security schema 实现。
- `web_egress_policy` 关键词仅出现在已有 `WebEgressPolicy` 类的 import/使用引用中，不是对 policy 文件的修改。

---

**PASS。** F01-F09 全部已关闭，无新 correctness / semantic ownership / boundary / test regression。S3 准备接受。
