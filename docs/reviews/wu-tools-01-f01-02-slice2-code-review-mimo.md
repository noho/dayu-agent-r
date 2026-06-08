# WU-TOOLS-01-F01-02 Slice 2 Code Review — AgentMiMo

## Metadata

- **Review target**: WU-TOOLS-01-F01-02 Slice 2 — Web Search Token Propagation And Fetch Coverage
- **Reviewer**: AgentMiMo (independent code review)
- **Date**: 2026-06-08
- **Plan source**: `docs/host/wu-tools-01-f01-02-cancellation-plan.md` §8 Slice 2
- **Implementation artifact**: `docs/reviews/wu-tools-01-f01-02-slice2-implementation-codex.md`

## Reviewed Scope

Production changes:

- `dayu/tools/web/web_tools.py` — +7 lines: `execution_context_param_name` on `search_web` decorator, `execution_context` parameter, `_resolve_execution_cancellation_token` + `_raise_if_tool_cancelled` pre-call checkpoint, token passthrough to `search_public_web`
- `dayu/tools/web/web_search_providers.py` — +49 lines: `cancellation_token` parameter on `search_public_web`, checkpoint at normalization / per-provider-attempt / post-provider-return, `_raise_if_search_cancelled` and `_is_search_cancelled_error` helpers, re-raise on cancel inside except block

Test changes:

- `tests/tools/web/test_web_tools_provider.py` — +373 lines: `_ManualCancellationToken`, 3 new search cancel tests, fetch Playwright token identity assertion, `_context` helper updated for injectable token
- `tests/tools/test_combined_tools_acceptance.py` — +7 lines: token identity assertion in combined ToolRuntime acceptance test

## Validation

| Command | Result |
|---|---|
| `pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q` | **20 passed**, 3 warnings (edgar deprecation, pre-existing) |
| `pyright dayu/tools/web tests/tools/web tests/tools/test_combined_tools_acceptance.py` | **0 errors, 0 warnings, 0 informations** |

## Findings

### F1 — [Observation] `search_public_web` 对外签名新增 positional-or-keyword 参数

`web_search_providers.py:152` — `cancellation_token: CancellationToken | None = None` 作为最后一个参数，现有调用方均使用关键字参数，无兼容性风险。但该参数名义上是 positional-or-keyword，若未来有裸位置调用可能误传。由于当前所有调用方均使用 `cancellation_token=...` 关键字形式，且 `search_public_web` 已经是 `*`-only 风格的 keyword-only 参数（前面有 `*`），此处实际是 keyword-only。

**验证**: `search_public_web` 签名以 `*,` 开头（line 138），所有参数均为 keyword-only。无风险。

**Severity**: Info — 无 action needed。

### F2 — [Observation] checkpoint 在 provider attempt 内部有三处但不覆盖 provider HTTP 请求内部

`web_search_providers.py:190-226` — checkpoint 位于：
1. 归一化后、循环前 (line 187)
2. 每次循环迭代开始 (line 190)
3. try 块内、provider 调用前 (line 192)
4. provider 返回后 (line 226)

provider 内部（如 `_search_with_tavily` 的 `requests.post`）是同步阻塞调用，无法在执行期间观察取消。这是 plan R2 已接受的 residual limitation：使用 timeout budget + checkpoint，不假装可抢占式取消。

**Severity**: Info — 已在 plan 中 accepted residual limitation，无需 action。

### F3 — [Observation] `test_search_web_cancelled_between_provider_attempts_stops_fallback` 的取消时序

`test_web_tools_provider.py:375-477` — 测试通过 monkeypatch `_search_with_tavily` 在 provider 内部设置 `token.cancel(...)` 并抛出 `RuntimeError`。实际的取消阻止发生在 `search_public_web` for 循环的下一次迭代开头（line 190 的 `_raise_if_search_cancelled`），而非 try 块的 except 分支内。这是因为 except 块先检查 `_is_search_cancelled_error(exc)` — 此时异常是 `RuntimeError` 不是 `ToolBusinessError`，所以走 fallback continue；然后循环到下一个 provider 时命中 checkpoint。

这意味着如果取消发生在 provider 成功返回后但在 post-return checkpoint 前（理论上的竞态窗口，实际上同步代码不存在此窗口），行为仍然正确。

**Severity**: Info — 测试覆盖的时序是正确的、可验证的。无 action needed。

## Findings Summary

无 blocking finding。三个 Observation 级别发现均不需 action。

## Checklist Against Review Requirements

| 审查项 | 结论 |
|---|---|
| 1. `search_web` execution_context 未进入 LLM-facing schema，token 来自 BatchToolExecutionContext | **PASS** — `execution_context_param_name` 是 adapter 注入 metadata，不写入 JSON schema `parameters`。token 通过 `_resolve_execution_cancellation_token(execution_context)` 从 context.cancellation_token 取得。 |
| 2. `search_public_web` checkpoint 覆盖 normalization 后、每个 provider attempt 前、provider 返回后；取消停止 fallback | **PASS** — 四处 checkpoint 正确覆盖。except 块中 `_is_search_cancelled_error` 确保取消错误不被 fallback 吞掉。 |
| 3. legacy Web cancellation 投影为 ToolBusinessError(code="tool_cancelled") / ToolFailedOutcome，未改 Host/Engine contract | **PASS** — `_raise_if_search_cancelled` 抛出 `ToolBusinessError(code="tool_cancelled")`，与 fetch 路径 `_raise_fetch_cancelled` 一致。adapter 将其投影为 `ToolFailedOutcome`。未修改 adapter-wide contract。 |
| 4. 无不合适层依赖、无过度耦合、无私有 cancel 状态、无不切实际的中断承诺 | **PASS** — `web_search_providers.py` 导入 `CancellationToken`（contracts 层）和 `ToolBusinessError`（legacy adapter 层），均为下层依赖。无私有状态。不尝试中断同步 `requests`。 |
| 5. 测试覆盖 token identity、pre-cancel、attempt 间取消、fetch Playwright token identity；无测试伪装或 brittle assertion | **PASS** — 4 个新测试覆盖所有 plan 要求场景。token identity 断言使用 `==` 比较同一对象（`received_tokens == [token]`）。combined acceptance 测试断言 `search_tokens == [context.cancellation_token]`。 |
| 6. AGENTS.md：中文 docstring、类型签名、无 Any/object | **PASS** — 新增函数均有完整中文 docstring。类型签名使用 `CancellationToken | None`（Protocol 类型）、`ToolBusinessError`（具体类型）。无 Any/object。 |

## Open Questions

无。

## Conclusion

**PASS** — Slice 2 实现正确覆盖 plan 要求的所有检查点，token 从 BatchToolExecutionContext 到 search_public_web provider 循环的传递链路完整，取消投影保持 legacy Web contract 一致性，测试覆盖四个 plan 指定场景且通过 identity 断言验证。pyright 0 errors。无 blocking finding。
