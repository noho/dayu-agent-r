# WU-TOOLS-01-F01-02-R3 Aggregate Deepreview Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: aggregate deepreview adjudication
- Date: 2026-06-10
- Base: `main` / `caaa559e`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-ds.md`
- Accepted slice commits:
  - plan: `7b465e19`
  - Slice 0: `a5ab5364`
  - Slice 1: `1bbc45fe`
  - Slice 2: `ac0c7303`
  - Slice 3: `2a914234`
  - Slice 4: `a24f6dc9`

## Verdict

Aggregate deepreview requires a fix gate.

DS 提出的 Doc/Web cancellation message governance finding 与 R3 已接受的 Fins 修复同源，必须在当前 WU 关闭。MiMo 的若干 finding 中，只有低风险、直接属于当前 native migration correctness / boundary / bookkeeping 的项进入本轮 fix；长同步网络物理中断、外部 API 边界增强、测试扩面和普通 cleanup 不扩大到当前 gate。

## Finding Adjudication

| ID | 来源 | 裁决 | 理由 / Fix 要求 |
|---|---|---|---|
| AGG-DS-F1 | DS Finding 1：Doc/Web 预取消和深层取消可能把 `CancellationToken.cancel_reason()` 原样投影到 LLM-facing message | accepted | 与 Slice 3 已接受的 Fins cancellation governance 修复同源；Doc/Web 必须使用固定安全取消消息，不得把 `run_id`、`session_id`、`payload_ref`、`digest`、`correlation_id`、`cancellation_token` 等治理字符串带入 outcome message/hint；补 Doc/Web 等价测试。 |
| AGG-MIMO-F1 | MiMo Finding 1：Doc `file_path` 指向目录时落入 `execution_error` | accepted | 当前 native path projection 漏掉 file 参数 `is_file()` 校验，导致 LLM-facing 错误不可恢复；应在 `_project_doc_paths` 中对非 `directory` 路径返回 `invalid_argument`，并补测试。 |
| AGG-MIMO-F2 | MiMo Finding 2：Web exception fallback 路径进入 Playwright 前缺少取消检查 | accepted | `_try_playwright_fallback` 是统一入口，低风险补 `_raise_if_host_cancelled(cancellation_token)` 可关闭所有 fallback call sites 的资源浪费窗口；补覆盖已取消 token 不启动 fallback 的测试。 |
| AGG-MIMO-F3 | MiMo Finding 3：同步 `_fetch_and_convert_content` 内部无法物理中断 | deferred-with-owner | R3 非目标明确不做外部长事务物理取消设计；当前路径受 `request_timeout_seconds` bounded wait 约束。后续 owner 为 WU-WAIT-03 / GitHub Issue #92 或未来 Web async fetch hardening。 |
| AGG-MIMO-F4 | MiMo Finding 4：`ToolBusinessFailure` 导出但无消费者 | accepted | `dayu.runtime` 是公共运行时基础设施，未消费导出会扩大契约表面；移除该类型和 `__all__` 导出，不保留兼容 alias。 |
| AGG-MIMO-F5 | MiMo Finding 5：`search_public_web` 冗余取消检查 | rejected-with-reason | 纯 cleanup，不影响 R3 correctness / boundary；不扩大当前 fix。 |
| AGG-MIMO-F6 | MiMo Finding 6：Doc loop cancellation interval 偏大 | deferred-with-owner | 属于取消响应调优，不是当前 adapter retirement correctness；后续可由 Doc tools maintenance 或 WU-WAIT cancellation hardening 评估。 |
| AGG-MIMO-F7 | MiMo Finding 7：外部 search result `None` 被 `str(None)` 投影 | deferred-with-owner | 真实外部 API response hardening 属于 Web provider robustness 后续，不阻塞 R3；destination 为 Web tools maintenance / live smoke owner。 |
| AGG-MIMO-F8 | MiMo Finding 8：Doc line scan snippet 粒度不匹配 | deferred-with-owner | 这是 LLM 结果质量增强，不是 current contract regression；destination 为 Doc tools search quality follow-up。 |
| AGG-MIMO-F9 | MiMo Finding 9：Doc provider 配置错误路径测试缺失 | deferred-with-owner | 测试扩面合理但不阻塞 R3；destination 为 Doc provider maintenance test hardening。 |
| AGG-MIMO-F10 | MiMo Finding 10：`host_cancelled_outcome(message=None)` 未测 | deferred-with-owner | 低风险覆盖率补充，非 R3 行为缺陷；destination 为 runtime helper test hardening。 |
| AGG-MIMO-F11 | MiMo Finding 11：array 无 `items` schema 未测 | deferred-with-owner | 低风险覆盖率补充，非 R3 行为缺陷；destination 为 runtime helper test hardening。 |
| AGG-MIMO-F12 | MiMo Finding 12：Doc `_required_*` 使用 `assert` | rejected-with-reason | 这些 helper 只消费已 schema-projected 参数，且本 WU 未引入 `python -O` 运行要求；不作为当前 defect。 |
| AGG-MIMO-F13 | MiMo Finding 13：Fins `_meta_cache` 无线程锁 | rejected-with-reason | 当前 provider 以同一 event loop 内共享 `asyncio.Lock` 串行化 Fins read callable，无跨 event loop 共享证据；不据此改动。 |
| AGG-MIMO-F14 | MiMo Finding 14：总控 F01-03 非目标残留 F04/F05/F06/F07 引用 | accepted | 用户明确要求总控删除 F04-F07 并改由对应 issue 追踪；残留引用必须改为 GitHub Issues #121 / #122。 |
| AGG-MIMO-F15 | MiMo Finding 15：R3 accepted slice commit 未记录 | accepted | Phaseflow 要求 control doc 记录 accepted commits；补 R3 row / status 记录 plan 与 Slice 0-4 commit。 |
| AGG-MIMO-F16 | MiMo Finding 16：`Log.verbose` 死代码 | rejected-with-reason | 普通 cleanup，不属于当前 gate 必要修复。 |
| AGG-MIMO-F17 | MiMo Finding 17：`dayu/tools/__init__.py` docstring 过时 | accepted | `_legacy_adapter` 已删除，包级 LLM/开发者可读说明不能继续声称 OLD adapter；更新为当前 native provider/tools 边界。 |

## Required Fix Scope

AgentCodex fix gate 只允许修改：

- `dayu/runtime/tool_call_projection.py`
- `dayu/tools/doc_tools.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/__init__.py`
- `tests/runtime/test_tool_call_projection.py`（仅在移除 `ToolBusinessFailure` 需要调整时）
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-fix-codex.md`

不得修改 Engine / Host state machine，不得恢复 legacy adapter，不得新增兼容 alias，不得处理 deferred/rejected finding。

## Required Validation

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`
- `rg "WU-TOOLS-01-F04|WU-TOOLS-01-F05|WU-TOOLS-01-F06|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md`

## Residual Risk Destination

- Web live / real network smoke remains with GitHub Issues #121 / #122 and is not a deterministic R3 blocker.
- Physical interruption of already-running synchronous HTTP / browser work is deferred to WU-WAIT-03 / GitHub Issue #92 or future Web cancellation hardening.
