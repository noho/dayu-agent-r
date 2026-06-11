# WU-TOOLS-01-F01-02-R3 PR Review

## Scope

- Mode: PR
- PR: https://github.com/noho/dayu-agent-r/pull/135
- Title: WU-TOOLS-01-F01-02-R3 retire legacy tool adapter
- Head: phaseflow/wu-tools-r3-f08
- Base: main
- Draft: true
- Latest commit: dda17730 (gateflow: record WU-TOOLS-01-F01-02-R3 draft PR)
- Checks: no checks reported on the branch
- Output file: docs/reviews/wu-tools-01-f01-02-r3-pr-review-ds.md
- Included scope: PR diff 135 相对 main 全部 85 files changed (22,526 lines diff)
- Excluded scope: 无
- Parallel review coverage: 无

Design/control sources:
- `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` (R3 plan, PR includes full plan)
- `docs/host/issues-implementation-control.md` (control doc, line 222 R3 entry)
- `docs/engine/design.md:270-329` (Tool call protocol / ToolExecutionOutcome)
- `docs/host/design.md:2020-2129` (ToolRuntime)

## Findings

未发现实质性问题。

### 逐项核对

**1. PR body 准确性**

PR body 描述的三项变更均与 diff 一致：
- `dayu/tools/_legacy_adapter` 目录已删除，Doc/Web/Fins read tools 已迁移到原生 `ToolDefinition` / `ToolCallable`。
- Host cancellation 投影已修复：所有迁移工具在 token 取消时返回 `ToolCancelledOutcome(reason=host_cancelled)`，不再返回 `ToolFailedOutcome(error="tool_cancelled")`。
- WU-TOOLS-01-F04/F05/F06/F07 未出现在 control doc 中（rg 返回空），F04/F05/F06/F07 在 R3 plan section 2 中列为 non-goals 并由 Issues #121/#122 追踪。

PR body 所列验证命令与实际受影响的测试文件一一对应。Notes 中的 Web live/real network smoke（Issues #121/#122）和物理中断（WU-WAIT-03/#92）的 deferral 与 R3 plan section 11 residual risk 一致。

**2. PR diff 包含完整 R3 plan/Slice 0-4/deepreview/bookkeeping**

PR diff 包含 54 个 docs/reviews/ 下的 review artifact，覆盖：
- Plan 阶段：plan review（MiMo + DS + controller adjudication）、plan fix（Codex）、plan re-review（MiMo + DS + controller adjudication）
- Slice 0–4 各阶段：implementation（Codex）、code review（MiMo + DS + controller adjudication）、fix（Codex）、re-review（MiMo + DS + controller adjudication）
- Aggregate deepreview：MiMo + DS + controller adjudication、fix（Codex）、re-review（MiMo + DS + controller adjudication）

PR 也包含 R3 plan artifact `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`（27 处 diff 命中）和 control doc 更新。

**3. Legacy adapter 删除后无生产或测试引用**

- `dayu/tools/_legacy_adapter/` 目录不存在（`git ls-tree dda17730 --name-only` 返回空）。
- `tests/tools/test_legacy_tool_adapter.py` 不存在。
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` 返回空（docs/ 除外）。
- `tests/host/test_import_boundary.py` 中 `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES`（原本豁免三个 adapter 文件）已删除。
- `tests/tools/test_combined_tools_acceptance.py` 中原 `test_migrated_providers_and_adapter_do_not_import_old_runtime` 已改为 `test_native_providers_do_not_import_old_runtime`，使用 `_native_tool_source_paths()`。

**4. Doc/Web/Fins cancellation 与 schema 边界**

Cancellation 正确性（三条 provider 均已验证）：

- **Doc tools** (`dayu/tools/doc_tools.py`): sync helper 通过 `_raise_if_doc_cancelled(cancellation_token)` 抛出 `_DocCancelledError`，callable 在 `except _DocCancelledError` 分支调用 `host_cancelled_outcome(...)` 返回 `ToolCancelledOutcome(reason=host_cancelled)`。`_DocCancelledError` 捕获位于 `_DocFileAccessError` 和通用 `Exception` 之前。
- **Web tools** (`dayu/tools/web/web_tools.py`): `_call_search_web` 在 `except WebSearchCancelledError` 返回 `host_cancelled_outcome(...)`，`_call_fetch_web_page` 在 `except WebToolCancelledError` 返回 `host_cancelled_outcome(...)`。两个 callable 的取消异常捕获均位于 `ToolBusinessError` 和通用 `Exception` 之前。
- **Fins tools** (`dayu/fins/tools/fins_tools.py`): 使用 `_host_cancelled_from_token(...)` → `host_cancelled_outcome(...)`，在 pre-cancel、post-lock-cancel、以及 `ToolBusinessCancelled` catch 均返回 `ToolCancelledOutcome(host_cancelled)`。
- 三处均无遗留 `ToolFailedOutcome(error="tool_cancelled")` 路径。

Schema 边界（治理字段不泄露）：

- Doc/Web/Fins 的 LLM-facing schema 均不包含 `execution_context`、`cancellation_token`、`run_id`、`session_id`、`correlation_id` 等治理字段。
- `cancellation_token` 仅作为 callable 内部参数传递给同步 business helper，不进入 tool schema parameters 定义。
- Doc provider path projection (`_project_doc_paths`) 拒绝 allowed_roots 外的路径，在进入业务逻辑前 fail closed。
- Web provider URL 类型校验在 lock 获取前完成。

Concurrency（provider 级串行）：

- 三个 provider 均使用 `asyncio.Lock()` 在 builder 函数内创建，同一 provider 内所有 callable 共享同一个 lock 实例。
- Lock 获取时序：参数校验 → pre-cancel check → `async with provider_lock` → post-lock cancel check → 业务逻辑。参数非法不排队等 lock。

**5. 总控已进入 PR review gate 并记录 PR URL**

`docs/host/issues-implementation-control.md` 第 144 行显示：
```
| implementation status | WU-TOOLS-01-F01-02-R3 draft PR created after accepted aggregate deepreview; draft PR https://github.com/noho/dayu-agent-r/pull/135; awaiting PR review gate |
```
第 222 行 WU-TOOLS-01-F01-02-R3 状态为 `PR review`，包含完整的 accepted commit 链和 draft PR URL。

**6. 无 F04-F07 residual work unit 条目**

`rg "WU-TOOLS-01-F0[4567]" docs/host/issues-implementation-control.md` 返回空。F04/F05/F06/F07 仅在 R3 plan section 2 中以 non-goals 出现。

**7. 错误类型迁移**

- Doc: `_DocPathFailure`、`_DocCancelledError`、`_DocFileAccessError` 均为 `dayu/tools/doc_tools.py` 本地定义。
- Web: `ToolBusinessError`（含 `url`/`next_action`/`http_status`/`internal_diagnostics`）、`WebSearchCancelledError`、`WebToolCancelledError` 均为 `dayu/tools/web/web_tools.py` 本地定义，不从 legacy adapter 导入。
- Fins: `ToolBusinessCancelled` 从 `dayu.runtime.tool_call_projection` 导入，Fins read runtime / search engine 的 legacy `ToolArgumentError`/`ToolBusinessError` 已被替换。`rg "from dayu.tools._legacy|_legacy_adapter|ToolBusinessError|ToolArgumentError" dayu/fins/tools/` 返回空。

**8. 本地验证结果与 PR 声明的验证命令一致**

- Pytest 指定集合：115 passed, 3 edgar deprecation warnings（与 PR body 列出的测试文件集合一致）。
- Pyright：0 errors。
- `git diff --check`：passed。
- `rg legacy adapter symbols dayu tests`：no matches。

## Open Questions

无。

## Residual Risk

1. Web live/real network smoke（Playwright browser 启动后取消、真实搜索 provider fallback、真实页面 fetch truncate、storage state/channel 组合）未在本 PR 覆盖——已由 GitHub Issues #121 (CN/HK Docling CI pipeline/smoke) 与 #122 (SEC/Fins CI pipeline/smoke) 跟踪，owner 明确。
2. 物理中断已运行的同步 HTTP/browser 工作（`asyncio.to_thread` 内阻塞）仍为 deferred——owner WU-WAIT-03 / GitHub Issue #92，PR Notes 已显式记录。
3. Tools Discovery `allow_empty` 语义与 Fins `include_read_tools=false` 返回空工具集的交叉——已转入 GitHub Issue #133 (`WU-TOOLS-01-F03-R4`)，R3 plan section 2 标记为 non-goal。
4. F08 documents processor registry 命名清理——仍为 deferred-with-owner（WU-TOOLS-01-F08），不在 R3 scope 内。
