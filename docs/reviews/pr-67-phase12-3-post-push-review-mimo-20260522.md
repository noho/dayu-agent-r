# PR #67 Phase 12.3 Post-Push Review

审查 Agent：AgentMiMo
日期：2026-05-22
审查对象：PR #67 `docs/phase12-design-discussion` -> `main`，head commit `a3d36e8`
审查范围：Phase 12.3 全量 diff + post-push pyright fix 验证

## 结论

**PASS**

无 blocking finding。所有 P12.3 gate criteria 满足，post-push pyright fix 有效。

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `python -m pyright utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `python -m pyright dayu/runtime dayu/service dayu/host tests/runtime tests/service tests/host` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 4 passed |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 115 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_import_boundary.py tests/engine/test_weak_typing_guard.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 34 passed |
| `pytest tests/engine/test_config_models.py tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` | 15 passed |
| `rg '"max_tokens"' dayu/config/models.json` | 无输出 |
| `rg 'agent_policy_profiles\|agent_policy_profile_id' dayu/config dayu/runtime dayu/service tests/runtime tests/service` | 仅 negative test 字符串 |
| `rg 'usage_enabled\|collect_usage\|include_usage\|supports_usage' dayu tests` | 仅 Engine OpenAI payload 实现与测试 |
| `python -m json.tool dayu/config/models.json` | OK |
| `python -m json.tool dayu/config/execution_profiles.json` | OK |

## P12.3 决策合规

| 决策点 | 状态 | 证据 |
|--------|------|------|
| 无旧 `agent_policy_profiles` / `agent_policy_profile_id` schema | PASS | production 代码无命中；仅 negative test 字符串 |
| 无默认 `max_tokens` runner hint | PASS | `models.json` 无 `max_tokens`；`RunnerOptionHintConfig` 只有 `temperature`/`top_p`/`stream` |
| usage 无 config override | PASS | 无 `usage_enabled`/`collect_usage`/`supports_usage` production 配置 |
| Service 显式选择 execution profile | PASS | `_select_execution_profile_id` 只根据 explicit override 或 `default_execution_profile_id` |
| `supports_stream_usage` 门控流式 usage | PASS | 仅出现在 `models.json` model config 与 Engine OpenAI payload 实现 |
| Host public open_host/handle 字段未变更 | PASS | 仅内部 command options 映射逻辑重构，public handle 方法签名不变 |
| 默认 `RunnerCallOptions.max_tokens` 为 `None` | PASS | Service assembly 默认路径唯一写 `max_tokens=None` |
| Engine usage event contract 不变 | PASS | `UsageReportedData`/`RunnerUsageRecordedData` 字段未修改 |
| `provider_request_id` 为可选关联信息 | PASS | usage projection signal payload 中 `provider_request_id=None`，不从 Engine contract 读取 |

## Post-Push Pyright Fix 验证

- **修复内容**：移除 `utils/smoke_host_public_multiturn.py:701` 对已删除 `diagnostics.agent_policy_profile_id` 的引用；新增 `tests/runtime/test_smoke_host_public_multiturn_assembly.py::test_assembly_diagnostics_output_uses_current_agent_policy_sources` 测试。
- **Pyright**：`python -m pyright utils/smoke_host_public_multiturn.py` 0 errors。
- **测试**：4 passed，断言 diagnostics 输出不含 `agent_policy_profile` 且包含 `agent_policy_sources=`。
- **有效性**：PASS。

## Findings

### P3 — Trailing whitespace in docs (cosmetic)

**严重性**：P3 (cosmetic)
**范围**：docs/reviews/ 多个 artifact 文件

`git diff --check` 报告以下文件有 trailing whitespace 或 blank line at EOF：

- `docs/host/phase12-3-config-usage-governance-plan.md`（行 3-7）
- `docs/reviews/phase12-3-plan-rereview-controller-adjudication-20260522.md`（行 36 EOF）
- `docs/reviews/phase12-3-plan-rereview-ds-20260522.md`（行 3-6）
- `docs/reviews/phase12-3-plan-review-controller-adjudication-20260522.md`（行 73 EOF）
- `docs/reviews/phase12-3-plan-review-ds-20260522.md`（行 3-7）
- `docs/reviews/phase12-3-slice3-code-review-ds-20260522.md`（行 37）
- `docs/reviews/phase12-3-slice4-code-review-ds-20260522.md`（行 3-5, 59, 86-89）
- `docs/reviews/phase12-3-slice4-code-review-mimo-20260522.md`（行 3-5）
- `docs/reviews/phase12-3-slice4-implementation-codex-20260522.md`（行 3-5）
- `docs/reviews/phase12-3-slice4-rereview-ds-20260522.md`（行 3-7）
- `docs/reviews/phase12-3-slice4-rereview-mimo-20260522.md`（行 3-5）

**影响**：无功能影响。仅文档格式。
**建议**：可选清理，不阻塞 PR 合并。

### P3 — implementation-control.md line 1813 残留旧 schema 引用 (informational)

**严重性**：P3 (informational)
**位置**：`docs/host/implementation-control.md:1813`

```
- `execution_profiles.json` 使用 ... 与 `agent_policy_profiles`。
```

此行在 Phase 12 原始设计记录 section，Phase 12.3 section（行 1893-1894）已正确描述删除。不误导当前使用。

**影响**：无。历史设计记录。
**建议**：可选标注为历史记录，不阻塞。

## Residual Risks

| 风险 | 分类 | 说明 |
|------|------|------|
| docs/reviews/ trailing whitespace | cosmetic | 可后续清理 |
| implementation-control.md 历史行残留旧术语 | informational | Phase 12.3 section 已覆盖 |
| `provider_request_id` 始终为 `None` | later phase | Engine usage event contract 当前不含此字段，后续 phase 按需扩展 |
| Context Governance usage observation diagnostic 未接入真实 estimator | later phase | 当前为 post-call diagnostic 数据，后续 Run/compaction 治理参考待实现 |

## Scope 与变更量

- 270 files changed, +33524 / -2392
- 涉及 Phase 12.1（runtime assembly schema correction）、Phase 12.2（service assembly helper）、Phase 12.3（config/usage governance）全量
- 新增模块：`dayu/runtime/config_loader.py`、`dayu/runtime/assembly.py`、`dayu/service/host_assembly.py`、`dayu/config/execution_profiles.json`、`dayu/config/models.json` 等
- 旧模块删除：`dayu/config/llm_models.json`、`dayu/config/run.json`
