# Code Review — WU-TOOLS-01-F01-02-R3 Aggregate Deepreview (AgentDS)

## Scope

- **Mode**: current changes (aggregate deepreview)
- **Branch**: `phaseflow/wu-tools-r3-f08`
- **Base**: `main` (merge-base `caaa559e`)
- **Commit range**: `7b465e19..a24f6dc9` (Slice 0–4)
- **Review artifact**: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-ds.md`

### Included scope

所有 `git diff main...HEAD` 覆盖的文件，按 plan 的五个 slice 组织：

- **Slice 0** — `dayu/runtime/tool_call_projection.py`（新增 current ToolCallable 参数校验与 outcome 构造 helper）+ 测试 `tests/runtime/test_tool_call_projection.py`
- **Slice 1** — `dayu/tools/doc_provider.py`、`dayu/tools/doc_tools.py`（Doc 5 工具原生 current callable）+ 测试 `tests/tools/test_doc_tools_provider.py`
- **Slice 2** — `dayu/tools/web/provider.py`、`dayu/tools/web/web_tools.py`、`dayu/tools/web/web_search_providers.py`（Web 2 工具原生 current callable）+ 测试 `tests/tools/web/test_web_tools_provider.py`
- **Slice 3** — `dayu/fins/tools/provider.py`、`dayu/fins/tools/fins_tools.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/read_runtime_helpers.py`、`dayu/fins/tools/search_engine.py`（Fins 9 工具原生 current callable）+ 测试 `tests/fins/test_fins_storage_provider.py`
- **Slice 4** — 删除 `dayu/tools/_legacy_adapter/**` 与 `tests/tools/test_legacy_tool_adapter.py`；更新 `tests/README.md`、`dayu/fins/README.md`、`tests/host/test_import_boundary.py`、`tests/tools/test_combined_tools_acceptance.py`
- **Design/control sources** — `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`
- **Review artifacts** — 各 Slice 的 code review / rereview / controller adjudication markdown（`docs/reviews/wu-tools-01-f01-02-r3-slice*-*.md`）

### Excluded scope

- `docs/reviews/` 下的历史 slice review artifacts（只读其结论，不复审）
- Web live smoke / Playwright live network 场景（plan 明确由 Issues #121/#122 追踪，本 review 只验证 deterministic pytest 覆盖的路径）
- `dayu/config/` 下 prompt 资产（本 WU 不涉及）
- `dayu/documents/processors/` 共享文档基础能力（非本 WU 变更）

### Parallel review coverage

本次 aggregate review 未拆分为 parallel subagent，由 AgentDS 统一沿真实代码路径逐条走读全部五个 slice 的关键入口、取消链路、错误投影、lock ordering、schema 边界与测试断言。

## Findings

### 1-未修复-低-Doc/Web 预取消路径可将 Host cancel_reason 原样暴露给 LLM，缺少与 Fins 等价的治理字段隐藏

- **入口/函数**: `dayu/tools/doc_tools.py:_doc_cancelled` (L1620–1637)、`dayu/tools/web/web_tools.py:_host_cancelled_from_token` (L1393–1416)
- **文件(行号)**: `dayu/tools/doc_tools.py:1633-1636`、`dayu/tools/web/web_tools.py:1410-1415`
- **输入场景**: Host 调用 `cancellation_token.cancel(reason)` 时，`reason` 包含 `run_id=...`、`session_id=...`、`payload_ref=...` 等 Host 治理标识字符串。
- **实际分支**: Doc 的 `_doc_cancelled` 将 `cancellation_token.cancel_reason()` 拼接到 LLM-facing `message`（`"文档工具调用已被取消。取消原因: {reason}"`）；Web 的 `_host_cancelled_from_token` 直接将 `cancel_reason()` 作为 `message`（`token.cancel_reason() or "工具调用已取消"`）。两条路径均无治理术语过滤。
- **预期行为**: 按 plan 第 7 节决策 4，"`host_cancelled_outcome` … message / hint 不暴露 Host 内部字段"。Fins 的 `_cancelled_from_token`（`dayu/fins/tools/fins_tools.py:906-932`）通过 `del cancellation_token` 刻意丢弃 token 并只用固定安全消息 `"财报读取工具调用已被取消。"`，且 `tests/fins/test_fins_storage_provider.py:787-830`（`test_cancelled_read_outcomes_hide_host_governance_reason`）显式验证了治理字段隐藏。
- **实际行为**: Doc 和 Web 的预取消路径缺少等价过滤。若 Host 将 `run_id`、`session_id` 等写入 `cancel_reason`，这些字符串将原样进入 LLM 可见的 outcome message。
- **直接证据**:
  - Doc `_doc_cancelled` (L1633–1636): `reason = cancellation_token.cancel_reason()` → 拼接进 message
  - Web `_host_cancelled_from_token` (L1410–1415): `message=token.cancel_reason() or "工具调用已取消"`
  - Fins `_cancelled_from_token` (L926): `del cancellation_token` + 固定 message `"财报读取工具调用已被取消。"`
  - Fins test `test_cancelled_read_outcomes_hide_host_governance_reason` (L787–830): 使用含 `run_id=run-secret session_id=session-secret ...` 的 `_HOST_GOVERNANCE_CANCEL_REASON`，断言治理字段全部被隐藏
  - Doc/Web 测试中不存在等价治理字段隐藏断言
- **影响**: 低 — 实际 Host 设置 `cancel_reason` 时通常不会放入治理字段，且 ToolResultMeta 本身不含治理信息。但若 Host 侧某条路径误将内部诊断写入 cancel_reason，Doc/Web 会比 Fins 先泄漏。不对称性也增加了未来维护者在不理解 Fins 设计意图时把 Fins 改为"也暴露 cancel_reason"的回归风险。
- **建议改法和验证点**: 对齐三个 provider 的预取消消息策略：统一使用固定安全消息，或统一从 cancel_reason 中过滤掉 `_HOST_GOVERNANCE_FORBIDDEN_TERMS`（`run_id`、`session_id`、`correlation_id`、`payload_ref`、`digest`、`cancellation_token`）后再拼接。补 Doc/Web provider 测试中与 Fins `test_cancelled_read_outcomes_hide_host_governance_reason` 等价的治理字段隐藏断言。
- **修复风险（低）**: 修改限于 callable 边界的 message 构造，不改变 outcome type/reason/contract。测试只需新增断言，不改现有正向或错误路径。
- **严重程度（低）**: 预取消路径触发频次低，Host 实际 cancel_reason 通常不含治理字段；ToolResultMeta 不含治理字段。本质是三个 provider 的行为不对称性，不是正确性缺陷。

## Open Questions

- Doc 和 Web 的深层取消路径（`_DocCancelledError` / `WebToolCancelledError`）中的 message 由深层业务 helper 构造；这些 message 是否也可能包含从 `cancel_reason()` 派生的文本？当前 Doc `_doc_cancelled` 确实使用了 `cancel_reason()`，而 Web 的 `_raise_fetch_cancelled`（`web_tools.py:537-559`）也使用 `cancel_reason()`。如果深层取消路径的 message 被投影到 outcome 且包含治理字段，影响面与预取消路径相同。当前 Fins 深层取消路径中的 `FinsReadCancelledError.message` 来源需要交叉验证（由 `read_runtime` 内部 checkpoint 控制，非本 review 可完整覆盖的链路）。

- Web `_call_fetch_web_page` 中 URL 安全检查（private URL 拒绝）发生在 `_fetch_web_page_business` 内部（即 lock 持有期间），与 plan 决策 3 "完成 … URL 基础校验之后" 进入 lock 的意图不完全一致。当前 URL 检查是纯本地计算（不涉及网络 I/O），不造成 lock 持有时间问题，但若未来 URL 检查引入外部 DNS/WHOIS 查询，lock 持有会膨胀。这暂不属于本 WU 的材料缺陷。

## Residual Risk

### 测试覆盖缺口

| 缺口 | Owner/Destination | 说明 |
|---|---|---|
| Doc/Web 治理字段隐藏测试缺失 | 本 WU 后续 fix（如 controller 接受 Finding 1） | Fins 已覆盖 `test_cancelled_read_outcomes_hide_host_governance_reason`；Doc/Web 无等价断言 |
| Web live smoke（Playwright browser、真实网络 provider fallback） | Issues #121/#122 | Plan 明确记录为 residual tracking；deterministic pytest 无法替代 |
| Web `_fetch_web_page_business` 内部 URL 安全检查在 lock 内执行 | 维护关注点 | 当前纯本地计算无危害；若未来扩展为网络调用需调整 lock 范围 |

### 已验证通过的关键路径

| 验证项 | 结果 |
|---|---|
| `rg "_legacy_adapter\|LegacyToolDeclarationCollector\|adapt_collected_tools" dayu tests` | 无命中 |
| `rg "WU-TOOLS-01-F04\|WU-TOOLS-01-F05\|WU-TOOLS-01-F06\|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md` | 无命中；F04–F07 已由 Issues #121/#122 承接 |
| `pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py` | 108 passed，3 edgar deprecation warnings |
| `pyright` | 0 errors |
| `git diff --check` | passed |
| Doc/Web/Fins schema 不含 `execution_context`、`cancellation_token`、`run_id`、`session_id`、`correlation_id` | 已由 provider tests + combined acceptance tests 断言 |
| Host 取消返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` | Doc/Web/Fins 三个 provider 的预取消测试均可复现 |
| 业务错误返回 `ToolFailedOutcome`，非 `ToolCancelledOutcome` | Doc（`invalid_argument`/`permission_denied`/`file_not_found`）、Web（`search_provider_unavailable`/`ToolBusinessError`）、Fins（`invalid_argument`/`file_not_found`/`FinsReadBusinessError`）均已按错误类别分别断言 |
| 取消 outcome 均携带 `ToolResultMeta(tool_name, started_at, finished_at)` | 三个 provider + runtime helper 测试均断言 |
| Provider lock 遵循 plan：每个 provider 内共享一把 `asyncio.Lock()`，参数/路径校验在 lock 外 | 代码逐行走读确认；Doc/Web combined acceptance 有并发串行测试 |
| Fins read 通过 `DefaultFinsRuntime.create(workspace_root=...)` → `get_read_runtime()` 进入存储边界 | provider.py L61–64 + 测试 fixture 通过 `build_fs_repository_set` 构造 |
| `tests/README.md` 已移除 legacy adapter 描述并更新为原生 provider | diff 确认 |
| `dayu/fins/README.md` 已更新 `register_fins_read_tools` → `build_fins_read_tool_definitions` | diff 确认 |
| `tests/host/test_import_boundary.py` 已移除 `_legacy_adapter` reserved-name 防御引用 | diff 确认 |
