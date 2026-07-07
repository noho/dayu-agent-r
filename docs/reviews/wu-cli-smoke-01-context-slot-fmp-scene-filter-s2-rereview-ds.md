# Code Re-Review (S2 Fix Verification)

## Metadata

- **Reviewer**: AgentDS (S2 code re-review)
- **Work unit**: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- **Review target**: workspace changes after S2 fix (Codex fix artifact)
- **Initial DS review**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-ds.md`
- **MiMo review**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-mimo.md`
- **Fix artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-fix-codex.md`
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes (re-review after S2 fix)
- **Base**: workspace changes post-fix vs pre-fix baseline
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-rereview-ds.md`
- **Included scope**: 13 files modified by the S2 fix (identical scope to fix artifact)
- **Excluded scope**: S1 files, unmodified production modules, future S3 scope
- **Parallel review coverage**: 无；单 reviewer 逐条验证

## Controller-Accepted Findings: Fix Verification

### Finding DS F1: timeout validation after missing API key fallback

**Status: ✅ 已修复**

`dayu/service/scene_context.py:129-133` — `_resolve_company_name_for_subject` 中 `api_key` 的 None 检查（第 129-131 行）现在位于 timeout 校验（第 132-133 行）之前。控制流为：

```
normalize_ticker → None? return None → api_key? None? return None → validate timeout → call FMP
```

对应测试覆盖：`test_entrypoint_runtime.py:206-214` — `ticker="V"`, `fmp_api_key=None`, `fmp_timeout_seconds=0` 返回 ticker-only subject 而非抛出异常。

验证结果：代码路径正确，timeout 只在确定会调用 FMP 时才被校验。Scene context 层的 timeout 校验（`ValueError`）与 resolver 层的内置校验（`FmpCompanyInfoResolutionError`）语义分层正确：前者面向用户输入合法性（由 CLI 捕获转为 `CliCommandUsageError`），后者面向编程正确性。

### Finding DS F2 / MiMo 01: `_interactive_context_slot_values` return type

**Status: ✅ 已修复**

`dayu/cli/commands/interactive.py:899` — 返回类型声明已从 `dict[str, str]` 改为 `dict[str, JsonValue]`，与 `prompt.py`（`_prompt_context_slot_values`）和 `session.py`（`_session_context_slot_values`）一致。运行时行为不变（返回值仍为 `{CONTEXT_SLOT_BASE_USER: DEFAULT_BASE_USER}`，两者均为 `str`）。`JsonValue` 导入已在第 66 行添加。

### Finding MiMo 02: invalid prompt --ticker CLI E2E usage-error test

**Status: ✅ 已修复**

`tests/cli/test_prompt_command.py:1727-1741` — 新增 `test_prompt_invalid_ticker_exits_with_usage_error_without_traceback`：
- 传入 `--ticker "!@#$"` 调用 `cli_main.main`
- 断言 `exit_code == EXIT_USAGE_ERROR`
- 断言 stderr 包含 `"dayu-cli prompt"`、`"无法识别的 ticker 形态"`、`"!@#$"`
- 断言 stdout 和 stderr 均不含 `"Traceback"`

测试正确覆盖了 CLI adapter 层对非法 ticker 的端到端处理。

### Finding MiMo 03: manual prompt runtime fixtures include current_time

**Status: ✅ 已修复**

以下手动构造 `EntrypointRuntimeRequest` 的 fixtures 现在均包含 `"current_time"` key：

| 位置 | 行号 | 覆盖场景 |
|---|---|---|
| `test_prompt_command.py` | 1303 | SIGINT after accepted run id |
| `test_prompt_command.py` | 1805 | SIGINT before accepted run id |
| `test_prompt_command.py` | 1905 | `_prepare_prompt_runtime` helper |
| `test_entrypoint_runtime_prompt_path.py` | 270 | prompt-path missing required slot negative fixture |
| `test_entrypoint_runtime_prompt_path.py` | 342 | `_prepare_prompt_runtime` helper |

fixture 结构与真实 CLI 路径（`prompt.py:236-239` 通过 `build_entrypoint_context_slot_values` 生成）一致。

### MiMo Residual Coverage: FMP second-hop search-name failure

**Status: ✅ 已修复**

`tests/fins/test_fmp_company_info_resolver.py:156-175` — 新增 `test_resolve_company_info_wraps_search_name_failure_after_symbol_success`：
- `_FakeFmpHttpClient` 仅包含 `search-symbol` 的成功响应
- 第二跳 `search-name` 时 fake client 抛出 `RuntimeError("missing fake response for ...")`
- 断言异常被包装为 `FmpCompanyInfoResolutionError`（match `"search-name"`）
- 断言 `__cause__` 为原始 `RuntimeError`
- 断言两次 HTTP 调用均实际发生且端点正确

测试正确覆盖了第一跳成功但第二跳失败的路径。

## Validation

```
tests/fins/test_fmp_company_info_resolver.py:                     8 passed
tests/cli/test_{prompt,interactive,session}_command.py:          91 passed
tests/service/test_entrypoint_runtime*.py:                        48 passed
tests/service/test_import_boundary.py + test_weak_typing_guard:   2 passed
pyright:                                                           0 errors, 0 warnings
git diff --check:                                                 passed
```

全部 149 个测试通过（初始 S2 实现 147 个，fix 新增 2 个：invalid ticker E2E 和 FMP second-hop failure）。pyright 零报错。Warnings 均为已有 `edgar` deprecation warning，与本次变更无关。

## Adversarial Failure Pass

对 fix 引入的变更逐路径进行对抗性验证：

### 路径 1：`_resolve_company_name_for_subject` 边界条件

| 输入组合 | ticker | api_key | timeout | 预期行为 | 实际走读确认 |
|---|---|---|---|---|---|
| 全部合法 | "V" | "sk-..." | 5.0 | 调用 FMP | `scene_context.py:135` ✓ |
| 无 ticker | None | "sk-..." | 5.0 | 返回 None | `scene_context.py:128` ✓ |
| 无 api_key | "V" | None | 5.0 | 返回 None | `scene_context.py:131` ✓ |
| 无 api_key + 非法 timeout | "V" | None | 0 | 返回 None（不抛异常） | `scene_context.py:131` 先返回 ✓ |
| 合法 api_key + 非法 timeout | "V" | "sk-..." | 0 | ValueError | `scene_context.py:133` ✓ |
| 合法 api_key + NaN timeout | "V" | "sk-..." | NaN | ValueError | `math.isfinite(NaN)` → False ✓ |
| 合法 api_key + Inf timeout | "V" | "sk-..." | inf | ValueError | `math.isfinite(inf)` → False ✓ |
| 空白 api_key | "V" | "  " | 5.0 | 返回 None | `_optional_stripped_text("  ")` → None ✓ |

所有边界条件行为正确。timeout 校验与 `FmpCompanyInfoResolver.__init__` 的内置校验使用相同条件（`not math.isfinite(...) or ... <= 0`），校验一致性成立。

### 路径 2：无效 ticker E2E 测试完整性

测试断言覆盖了 exit code、错误消息格式、原始输入保留、无 traceback 泄漏（stdout 和 stderr 双侧检查）。测试使用 `cli_main.main` 直接调用，走完整 CLI → Service → scene_context 链路。覆盖充分。

### 路径 3：FMP 第二跳失败测试

测试验证了两跳调用的实际发生（`len(client.calls) == 2`）、端点的正确性（`search-symbol` 在前，`search-name` 在后）、以及异常链的完整性（`__cause__` 为原始 `RuntimeError`）。`_FakeFmpHttpClient` 在无匹配响应时抛 `RuntimeError`，resolver 在所有 `Exception` 路径上均包装为 `FmpCompanyInfoResolutionError`。覆盖充分。

### 路径 4：session 命令 slot 生成一致性

`session.py` 的 `_session_context_slot_values` 现在调用 `build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=None))`，不再硬编码 `"未指定具体公司"`。生成的 slot values 包含 `fins_default_subject`（空字符串）、`current_time`（当前上海时间）和 `base_user`。与 prompt 路径使用相同的 Service 入口，确保 slot 格式统一。无回归风险。

### 无新引入问题

对抗性验证未发现 fix 引入的新缺陷、新边界条件漏洞或新回归风险。所有 fix 均为最小化、针对性修改，不改变已有正常路径行为。

## Architecture Boundary Verification

Fix 未改变架构边界。`session.py` 新增的 `from dayu.service.scene_context import ...` 是 Service 内部模块间依赖，不穿透 Service 层边界。原有架构约束全部保持：

| 约束 | 状态 |
|---|---|
| Service → Fins public resolver | ✅ 不变 |
| Service → Fins ticker_normalization | ✅ 不变 |
| Service 不导入 Fins storage/pipelines | ✅ 不变 |
| Service 不导入 Host/Engine internals | ✅ 不变 |
| Runtime 无变更 | ✅ 不变 |
| Fins 包根不 re-export resolver | ✅ 不变 |
| CLI 读 FMP_API_KEY 在边界 | ✅ 不变 |
| Import boundary 白名单 | ✅ 不变（已在初始 S2 更新） |

## Findings

未发现实质性问题。

所有 5 个 controller-accepted findings 已正确修复，fix 实现与 fix artifact 描述一致，无遗漏、无过度修复、无新引入问题。

## Open Questions

无。

## Residual Risk

Fix 未解决的 residual risks（与初始 DS review 一致，全部推迟到 S3）：

1. **无真实 FMP 网络 smoke**：所有 FMP HTTP 调用通过 fake client 模拟，未验证真实 FMP API 响应格式兼容性。
2. **`current_time` slot 生成但 prompt manifest 未消费**：`build_entrypoint_context_slot_values` 始终生成 `current_time` slot，但当前 prompt scene manifest 可能尚未声明该 slot。
3. **`base_user` slot 仍保留**：三个 CLI command 仍传递 `base_user`，待 S3 全局移除。
4. **默认 HTTP client 无 User-Agent**：`_UrllibFmpHttpClient` 未设置 User-Agent 请求头。

## Conclusion

**Pass** — 0 blocking findings, 0 new findings。所有 5 个 controller-accepted S2 findings 已正确修复并通过验证。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-rereview-ds.md`
- **Conclusion**: Pass
- **Accepted findings fixed**: 5/5
  - DS F1: timeout validation order ✅
  - DS F2 / MiMo 01: interactive return type ✅
  - MiMo 02: invalid ticker E2E test ✅
  - MiMo 03: manual fixtures current_time ✅
  - MiMo residual: FMP second-hop failure coverage ✅
- **Unresolved accepted findings**: 无
- **New blockers**: 无
- **Residual risks**: 4（与初始 review 一致，全部推迟到 S3）
