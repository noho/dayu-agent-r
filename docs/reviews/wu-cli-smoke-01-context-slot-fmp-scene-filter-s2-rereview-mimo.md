# S2 Code Re-Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `a124e0a8`（workspace changes since this commit, including staged, unstaged, and untracked files）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-rereview-mimo.md`
- Included scope: All S2 implementation files and S2 fix files
- Excluded scope: S1 scene 条件块过滤（已 commit `2824ee59`）、S3 prompt assets/manifests 清理
- Parallel review coverage: 无

## Review Context

- Initial review: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-mimo.md`
- DS review: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-fix-codex.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-implementation-codex.md`

## Controller Accepted Fixes Verification

### DS F1: timeout validation after missing API key fallback

**Status: ✅ Fixed and verified**

**Evidence:**
- `dayu/service/scene_context.py:129-131`: `api_key` 的检查在 `fmp_timeout_seconds` 校验之前
  ```python
  api_key = _optional_stripped_text(request.fmp_api_key)
  if api_key is None:
      return None
  if not math.isfinite(request.fmp_timeout_seconds) or request.fmp_timeout_seconds <= 0:
      raise ValueError("fmp_timeout_seconds must be positive finite seconds")
  ```
- `tests/service/test_entrypoint_runtime.py:191-214`: 测试 `test_build_entrypoint_context_slot_values_falls_back_without_fmp` 覆盖了 `ticker="V"`, `fmp_api_key=None`, `fmp_timeout_seconds=0` 的场景，返回 ticker-only subject 而非抛出异常

**Verification result:** 当 `fmp_api_key` 为 `None` 时，FMP 不会被调用，timeout 不会被消费；此时非法超时值不会触发异常，直接返回 `None`。符合"不调用就不校验"的最小权限原则。

### DS F2 / MiMo 01: `_interactive_context_slot_values` return type `dict[str, JsonValue]`

**Status: ✅ Fixed and verified**

**Evidence:**
- `dayu/cli/commands/interactive.py:899`: 返回类型已改为 `dict[str, JsonValue]`
  ```python
  def _interactive_context_slot_values() -> dict[str, JsonValue]:
  ```

**Verification result:** 与 `_prompt_context_slot_values`（`prompt.py:652`）和 `_session_context_slot_values`（`session.py:647`）的返回类型注解保持一致。类型系统接受，运行时行为不变。

### MiMo 02: invalid prompt --ticker CLI E2E usage-error test

**Status: ✅ Fixed and verified**

**Evidence:**
- `tests/cli/test_prompt_command.py:1727-1741`: 新增测试 `test_prompt_invalid_ticker_exits_with_usage_error_without_traceback`
  ```python
  exit_code = cli_main.main(("prompt", "--base", str(tmp_path), "--ticker", "!@#$", "请总结"))
  captured = capsys.readouterr()

  assert exit_code == EXIT_USAGE_ERROR
  assert "dayu-cli prompt" in captured.err
  assert "无法识别的 ticker 形态" in captured.err
  assert "!@#$" in captured.err
  assert "Traceback" not in captured.err
  assert "Traceback" not in captured.out
  ```

**Verification result:** 测试验证了非法 ticker `"!@#$"` 在 CLI adapter 层被正确捕获为 `CliCommandUsageError`，返回 `EXIT_USAGE_ERROR`，错误消息清晰，且不包含内部异常栈。

### MiMo 03: manual prompt runtime fixtures include current_time where mirroring real CLI slot shape

**Status: ✅ Fixed and verified**

**Evidence:**
- `tests/cli/test_prompt_command.py:1301-1304`: 手动构造的 `context_slot_values` 包含了 `current_time`
  ```python
  context_slot_values={
      "fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。",
      "current_time": _PROMPT_CURRENT_TIME_TEXT,
      "base_user": "本地 CLI 用户",
  },
  ```
- 其他手动构造的 fixtures（SIGINT after accepted run id、SIGINT before accepted run id、shared `_prepare_prompt_runtime` helper）也已同步更新

**Verification result:** 测试 fixture 与真实 CLI 路径生成的 slot values 结构一致，消除了隐性结构差异。

### MiMo Residual Coverage: FMP second-hop search-name failure coverage

**Status: ✅ Fixed and verified**

**Evidence:**
- `tests/fins/test_fmp_company_info_resolver.py:156-175`: 新增测试 `test_resolve_company_info_wraps_search_name_failure_after_symbol_success`
  ```python
  client = _FakeFmpHttpClient(
      (
          _FakeResponse(
              url_part="search-symbol",
              body=json.dumps([{"symbol": "V", "name": "Visa Inc."}]),
          ),
      )
  )
  resolver = FmpCompanyInfoResolver(api_key="test-key", http_client=client)

  with pytest.raises(FmpCompanyInfoResolutionError, match="search-name") as exc_info:
      resolver.resolve_company_info("V")

  assert isinstance(exc_info.value.__cause__, RuntimeError)
  assert len(client.calls) == 2
  assert "search-symbol" in client.calls[0][0]
  assert "search-name" in client.calls[1][0]
  ```

**Verification result:** 测试覆盖了 search-symbol 成功但 search-name 失败的场景，验证了第二跳失败时 `FmpCompanyInfoResolutionError` 的包装和因果链。

## New Findings

未发现实质性问题。

## Validation Results

```bash
source .venv/bin/activate && pytest tests/fins/test_fmp_company_info_resolver.py
# 8 passed

source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 91 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py
# 48 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q
# 2 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Warnings 为已有 `edgar` deprecation warning，与本次变更无关。

## Open Questions

无。

## Residual Risk

1. **无真实 FMP 网络 smoke。** 自动测试使用 fake HTTP client 覆盖了 FMP resolver 的全部逻辑路径，但未验证真实 FMP API 的响应格式、网络延迟和认证行为。Plan 已将此分类为 optional smoke，不阻塞 S2。
2. **`base_user` 残留。** 三个 CLI command 仍硬编码 `DEFAULT_BASE_USER = "本地 CLI 用户"` 和 `CONTEXT_SLOT_BASE_USER = "base_user"`。当前 prompt/interactive/wechat manifest 仍要求此 slot。S3 将负责全局清理。
3. **`current_time` 生成但未被当前 prompt manifest 消费。** `build_entrypoint_context_slot_values` 总是生成 `current_time` slot，但当前 `prompt.json` manifest 的 scene `.md` 可能尚未包含 `{{current_time}}` placeholder。S3 将负责对齐 prompt assets/manifests。

## Conclusion

**Pass**

所有 controller accepted S2 code review findings 已正确修复并通过验证。未发现新 blockers。

- DS F1: timeout validation order 已修复，符合最小权限原则
- DS F2 / MiMo 01: `_interactive_context_slot_values` 返回类型已统一
- MiMo 02: invalid ticker CLI E2E 覆盖已补充
- MiMo 03: manual fixtures 已对齐真实 CLI slot shape
- MiMo Residual Coverage: FMP second-hop failure 覆盖已补充

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-rereview-mimo.md`
- **Conclusion**: Pass
- **Unresolved accepted findings**: 0
- **New blockers**: 0
- **Residual risks**: 3（无真实 FMP smoke、base_user 残留、current_time 未消费）
