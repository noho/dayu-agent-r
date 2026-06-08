# WU-TOOLS-01-F01-02 Slice 2 Code Review — AgentDS

## Metadata

| 字段 | 值 |
|---|---|
| Review ID | WU-TOOLS-01-F01-02-SLICE2-DS-001 |
| Reviewer | AgentDS |
| Date | 2026-06-08 |
| Plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` Slice 2 |
| Implementation artifact | `docs/reviews/wu-tools-01-f01-02-slice2-implementation-codex.md` |
| Design sources | `docs/host/design.md`, `docs/engine/design.md` |
| Review type | Code correctness, contract compliance, test quality, AGENTS.md compliance |

## Reviewed Scope

| File | Change Type |
|---|---|
| `dayu/tools/web/web_tools.py` | `search_web` 新增 `execution_context` 注入与 pre-call checkpoint |
| `dayu/tools/web/web_search_providers.py` | `search_public_web` 新增 `cancellation_token` 参数与 4 个 checkpoint；新增 `_raise_if_search_cancelled` / `_is_search_cancelled_error` helpers |
| `tests/tools/web/test_web_tools_provider.py` | 新增 3 个 search cancel 测试；扩展 fetch cancel 测试验证 token identity；新增 `_ManualCancellationToken` 测试双精度；类型注解补充 |
| `tests/tools/test_combined_tools_acceptance.py` | 验收测试扩展：验证 ToolRuntime 路径下 search_web 收到 context cancellation token |
| `docs/host/issues-implementation-control.md` | Controller 状态更新（不作为实现 correctness 重点） |

## Validation

### 测试运行

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：**20 passed, 3 warnings in 1.03s**

- 3 个 warning 全部来自 `edgar` 依赖的 deprecated module 提示，非本次改动引入。

### pyright

```bash
source .venv/bin/activate && pyright dayu/tools/web/ tests/tools/web/ tests/tools/test_combined_tools_acceptance.py
```

结果：**0 errors, 0 warnings, 0 informations**

## Findings

### Finding 1 (Low) — `_raise_if_search_cancelled` hint 消息语义可细化

**文件**: `dayu/tools/web/web_search_providers.py:281`

**证据**:

```python
hint="[continue_without_web] The host cancelled this web search; continue without web search unless the user asks to retry.",
```

与 `_raise_fetch_cancelled`（`web_tools.py:497`）的 hint 对比：

```python
hint="[continue_without_web] The host cancelled this web fetch; continue without this page unless the user asks to retry.",
```

**分析**: fetch hint 明确提示 "continue without **this page**"，精确定位到单个资源的取舍；search hint 写的是 "continue without **web search**"，对 LLM 而言可能被解读为"放弃整个 web search 能力"而非"跳过当前这次检索"。两者语义粒度不均匀。

**严重性**: Low — 不影响功能正确性，`[continue_without_web]` 前缀已足够让 LLM 理解取消语义。仅建议对齐。

**修复建议**: 将 search hint 改为 `"continue without this web search unless the user asks to retry."` 以与 fetch hint 保持一致的网页资源级粒度。

---

### Finding 2 (Info) — 循环内 checkpoint 190-192 存在紧邻重复检查

**文件**: `dayu/tools/web/web_search_providers.py:189-192`

**证据**:

```python
for candidate_provider in _candidate_providers(resolved_provider):
    _raise_if_search_cancelled(cancellation_token)       # line 190
    try:
        _raise_if_search_cancelled(cancellation_token)   # line 192
```

**分析**: line 190（循环入口 checkpoint）与 line 192（try 块内 provider 前 checkpoint）之间仅有 `try:` 语法语句，无任何副作用操作或异步挂起点。在无并发修改 `cancellation_token` 状态的前提下，line 192 的检查结果必然与 line 190 一致。这不构成 bug，但属于防御性冗余。在首次迭代中，line 187（normalization 后 checkpoint）与 line 190 之间也无实质工作，构成三重紧邻检查。

**严重性**: Info — 不影响正确性，`is_cancelled()` 是 O(1) 属性读取。保留也可以接受作为 defense-in-depth。

**修复建议**: 如需精简，可去掉 line 192 的重复检查，仅保留 line 190（循环入口）和 line 226（provider 返回后）。或者保留当前写法，在代码注释中说明 intent。

---

### Finding 3 (Info) — `_raise_if_search_cancelled` 位于 `web_search_providers.py` 引入新模块依赖

**文件**: `dayu/tools/web/web_search_providers.py:17-18`

**证据**:

```python
from dayu.contracts.cancellation import CancellationToken
from dayu.tools._legacy_adapter.tool_errors import ToolBusinessError
```

**分析**: `web_search_providers.py` 此前不依赖 `dayu.contracts.cancellation` 和 `dayu.tools._legacy_adapter`。新增的两条 import 均为合法依赖：
- `dayu.contracts.cancellation` — 最底层公共契约，符合架构约束。
- `dayu.tools._legacy_adapter.tool_errors` — tools 层内部 sibling 模块引用，不跨越 `dayu.runtime` / `dayu.engine` / `dayu.host` 层边界。

Plan Section 7 明确要求沿用 legacy `ToolBusinessError` 模式。无架构违规。

**严重性**: Info — 合规，记录供审计。

---

### Finding 4 (Pass) — `execution_context` 未进入 LLM-facing schema

**验证**: `search_web` 的 `parameters` JSON schema（`web_tools.py:1047` 定义）仅包含 `query`、`domains`、`recency_days`、`max_results`。`execution_context` 通过 `@tool(execution_context_param_name="execution_context")` 由 adapter 注入，不在 schema `properties` 中。`search_public_web` 的 `cancellation_token` 是内部 keyword-only 参数，也不经 LLM 路径。

**测试覆盖**: `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` 断言搜索结果无 `ok` 字段（schema pollution guard），且 `search_tokens == [context.cancellation_token]` 验证 token identity。

结论：**PASS**，与 Plan Section 6 "Schema Changes: 无 tool JSON schema 参数变更" 一致。

---

### Finding 5 (Pass) — Checkpoint 覆盖完整，取消停止 fallback

**验证**: `search_public_web` checkpoint 分布：

| 位置 | 行号 | 覆盖场景 |
|---|---|---|
| normalization 后、循环前 | 187 | pre-provider guard |
| 每个 fallback iteration 入口 | 190 | attempt 间取消 |
| provider 调用前 | 192 | 单次 attempt 前取消 |
| provider 成功后、filter/return 前 | 226 | 结果 discard |
| except 块内 | 228-229 | cancel error 不吞咽、不放行 fallback |

**测试覆盖**:
- `test_search_web_cancelled_before_provider_returns_tool_cancelled` — pre-cancel 不调用 provider（`search_calls == []`），返回 `ToolFailedOutcome(error="tool_cancelled")`
- `test_search_web_cancelled_between_provider_attempts_stops_fallback` — tavily 失败后取消，duckduckgo 不执行（`attempted_providers == ["tavily"]`），返回 `ToolFailedOutcome(error="tool_cancelled")`

结论：**PASS**，与 Plan Slice 2 Invariants 一致。

---

### Finding 6 (Pass) — Legacy cancellation 投影未改 Host/Engine contract

**验证**:
- `_raise_if_search_cancelled` 抛出 `ToolBusinessError(code="tool_cancelled")`（`web_search_providers.py:278`）
- legacy adapter `_build_failed_outcome` 将其投影为 `ToolFailedOutcome`（`definition_adapter.py:374-382`）
- 不引入 `ToolCancelledOutcome`，不改 adapter-wide 投影逻辑

**测试覆盖**: 所有 cancel 测试均断言 `isinstance(outcome, ToolFailedOutcome)` 和 `outcome.result.error == "tool_cancelled"`。

结论：**PASS**，与 Plan Section 7 和 Risk R3 决策一致。

---

### Finding 7 (Pass) — Token identity 贯穿全链路

**验证**:

1. `search_web` → `search_public_web` 路径：`_resolve_execution_cancellation_token(execution_context)` → 传 `cancellation_token=cancellation_token` 到 `search_public_web`（`web_tools.py:1095,1112`）

2. `fetch_web_page` → Playwright fallback 路径：
   - `web_tools.py:1239-1240`: `cancellation_token` 写入 `playwright_fallback_kwargs`
   - `web_tools.py:1250-1251`: `cancellation_token` 写入 `warmup_kwargs`
   - `web_tools.py:1268-1269`: `cancellation_token` 写入 `probe_kwargs`

**测试覆盖**:
- `test_search_web_receives_execution_context_and_passes_cancellation_token` — monkeypatch 的 `fake_search_public_web` 记录 `received_tokens`，断言 `received_tokens == [token]`
- `test_fetch_playwright_cancel_projects_to_cancelled_failure` — monkeypatch 的 `fake_fetch_and_convert_with_playwright` 记录 `received_playwright_tokens`，断言 `received_playwright_tokens == [token]`
- `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` — 通过 ToolRuntime 路径记录 `search_tokens`，断言 `search_tokens == [context.cancellation_token]`

三个测试各自覆盖了不同注入路径（直接 callable、adapter 内 Playwright fallback、ToolRuntime 端到端），且均使用 identity 断言（`== [token]`），非 brittle value assertion。

结论：**PASS**。

---

### Finding 8 (Pass) — 无层依赖违规、无过度耦合、无私存 cancel 状态

**验证**:
- 无 `dayu.runtime` / `dayu.engine` / `dayu.host` 反向依赖
- 无 `Any`、`object`、无类型参数
- 无模块级全局 cancel 状态；`_raise_if_search_cancelled` 只读 token，不写
- `search_public_web` 内 token 检查是协作式观察，不管理 cancel 生命周期
- 不试图中断 `requests` 同步阻塞调用（Plan Section 8 明确：`Do not attempt to cancel in-flight requests beyond existing timeout`）

结论：**PASS**。

---

### Finding 9 (Pass) — AGENTS.md 合规

**验证项目**:

| 约束 | 状态 |
|---|---|
| 中文 docstring（函数/类/模块） | PASS — `_raise_if_search_cancelled`、`_is_search_cancelled_error`、`_ManualCancellationToken`、所有新增/修改函数均有完整中文 docstring |
| 类型签名完整（无 `Any`/`object`） | PASS — 所有参数和返回值均有完整类型注解 |
| 禁止胶水 seam / lazy import | PASS — 无可疑 import |
| 禁止魔法数字/字符串 | PASS — `"tool_cancelled"` 是 adapter contract 字面量，属工具 schema 例外 |
| 模块级私有辅助函数 | PASS — `_raise_if_search_cancelled`、`_is_search_cancelled_error` 均为模块级 |
| README 触发判断 | PASS — `dayu/tools/web/` 不在 README 触发目录列表中；`tests/` 触发已检查 `tests/README.md`，无新增测试层级/运行方式/维护约定变更 |

结论：**PASS**。

---

### Finding 10 (Pass) — 测试质量与覆盖

**测试覆盖矩阵**:

| 测试 | 覆盖场景 | 断言质量 |
|---|---|---|
| `test_search_web_receives_execution_context_and_passes_cancellation_token` | token identity 经 adapter 路径传递到 `search_public_web` | identity assertion `== [token]` |
| `test_search_web_cancelled_before_provider_returns_tool_cancelled` | pre-cancel 不调用 provider | `search_calls == []`; `error == "tool_cancelled"` |
| `test_search_web_cancelled_between_provider_attempts_stops_fallback` | attempt 间取消停止 fallback | `attempted_providers == ["tavily"]` |
| `test_fetch_playwright_cancel_projects_to_cancelled_failure` (修改) | Playwright 收到同一 token object | `received_playwright_tokens == [token]` |
| `test_toolruntime_executes_representative_provider_tools_and_accepts_facts` (修改) | ToolRuntime 端到端 search_web token 传递 | `search_tokens == [context.cancellation_token]` |

**无测试伪装或 brittle assertion**:
- 无 source-only 断言（如检查 `__code__.co_varnames`）
- 无不验证行为的 mock 存在性断言
- 所有 identity 断言均验证同一 Python object，不依赖序列化/反序列化等效
- `_ManualCancellationToken` 实现了 `CancellationToken` Protocol 的完整观察面，`cancel()` 仅作为测试 setup 手段

结论：**PASS**。

---

## Open Questions

1. **`_raise_if_search_cancelled` 的 `hint` 语义粒度**（Finding 1）：是否需要将 "continue without web search" 细化为 "continue without this web search"？当前不影响功能。

2. **紧邻 checkpoint 冗余**（Finding 2）：line 190 / 192 的紧邻双 checkpoint 是否有意为之（defense-in-depth）？若是，建议加一行注释说明意图；若否，可精简。

## Conclusion

**Verdict: PASS**

Slice 2 实现严格遵循 Plan 的 exact changes、invariants、call paths / data flow 和 error handling。`execution_context` 正确通过 adapter 注入且不进入 LLM-facing schema。`search_public_web` 的 4 个 checkpoint 覆盖 normalization 后、provider 循环入口、provider 调用前、provider 返回后，并在 except 块中正确区分 cancel error 与 provider failure，防止 fallback 泄漏。取消继续投影为 `ToolBusinessError(code="tool_cancelled")` → `ToolFailedOutcome`，不改 Host/Engine/adapter contract。测试覆盖 token identity 三路径（直接 callable、Playwright fallback、ToolRuntime 端到端）、pre-cancel 短路、attempt 间 fallback 停止。pyright 0 errors。无层依赖违规、无 `Any`/`object`、无私有 cancel 状态。

仅 Finding 1（hint 语义粒度）和 Finding 2（紧邻 checkpoint 冗余）为 Info/Low 级别，均非阻塞项。
