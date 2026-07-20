# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Plan — AgentMiMo Clean-Room Replacement Review

## 0. Clean-room / routing compliance

- 本 artifact 是 AgentMiMo 对 `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` 的第一路 clean-room replacement review。
- 未读取任何文件名包含 `aggregate-regression-fix-plan-review-mimo` 或 `aggregate-regression-fix-plan-review-ds` 的 review artifact。
- 未启动 Agent、Explore、subagent 或任何并行 reviewer。
- 未采用任何旧 reviewer/subagent 输出；所有结论从零独立推导。
- 所有证据直接从当前 HEAD 代码、测试、配置与文档中采集。

## 1. Plan identity verification

| 项 | 预期值 | 实测值 | 状态 |
| --- | --- | --- | --- |
| 文件路径 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 同左 | ✓ |
| SHA-256 | `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` | `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` | ✓ |
| 行数 | 610 | 610 | ✓ |
| 字节数 | 44,252 | 44,252 | ✓ |
| HEAD | `ed9bfa9fe071aba0227361c69a938010ce3abe09` | `ed9bfa9fe071aba0227361c69a938010ce3abe09` | ✓ |
| Aggregate parent | `3410d7422655c56bdf13c643f77c27f40b9d4550` | 同左 | ✓ |
| Plan status | `PLAN_ONLY / NOT_ACCEPTED / IMPLEMENTATION_NOT_AUTHORIZED` | 同左 | ✓ |

## 2. Sources read

以下全部在本次 clean-room review 中从零完整读取：

1. `AGENTS.md` — 项目级约束（完整读取）。
2. `docs/phaseflow-umbrella-optimization-control.md` — umbrella 优化总控（完整读取）。
3. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Controller discussion，含 Topic 5/6 裁决（完整读取）。
4. `docs/host/design.md` — Host 设计真源（完整读取到 EOF，554 行）。
5. `docs/fins/design.md` — Fins 设计真源（完整读取到 EOF）。
6. `docs/engine/design.md` — Engine 设计真源（完整读取到 EOF，554 行，含 §11 ToolExecutor Handshake Timeout、§12 Suspend 与 Resume）。
7. `docs/tool/design.md` — Tool 设计真源（完整读取到 EOF，135 行，含 §9 Browser Storage State Lifecycle、§10 Tool Authorization）。
8. `docs/ui/design.md` — UI 设计真源（完整读取到 EOF，112 行，含 §1 Public Entrypoint Lifecycle、§2 upload_filings_from、§3 dayu-cli init）。
9. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` — Codex aggregate regression evidence（完整读取，668 行）。
10. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` — Controller adjudication（完整读取）。
11. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md` — Controller validation（完整读取）。
12. `docs/host/issues-implementation-control.md` — 当前 control doc 状态（完整读取）。
13. `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` — reviewed target（完整读取，610 行）。
14. 当前 HEAD 代码、测试、配置与 import graph。
15. `dayu/tests/utils` consumer scans（六组 canonical scans 重跑）。
16. `rg -n 'AwaitingResolutionMode|parse_awaiting_resolution_mode|AWAITING_RESOLUTION_MODE_CONFIG_FIELD' dayu tests utils` — 完整 consumer scan（含 `utils/`）。

## 3. Assumptions

1. Plan 只关闭 `AR-F01`—`AR-F05`；`AR-F06` 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07` 保持 `PENDING_RELEASE_BLOCKER`。
2. 当前 branch `phaseflow/host-issues-control`，HEAD `ed9bfa9`。
3. 当前工作区 Controller-owned changes 不可修改。
4. Plan 经双路 review/fix/re-review 并由 Controller 接受后才可进入 Slice 1 implementation。
5. Service import boundary test 使用前缀匹配，`dayu.fins.ingestion` 前缀覆盖 `dayu.fins.ingestion.awaiting_resolution`。

## 4. Findings

### F-01 [ACCEPTED] AR-F02 direct_stream consumer list completeness — exact allowlist 覆盖验证

**Plan claim (§2.3, §3.1):** 删除 `dayu/fins/direct_stream.py`，把 `ValidatedFinsEventStream` 物理迁入 `dayu/fins/direct_events.py`，迁移四类 consumers。

**Evidence:** `rg -n 'dayu\.fins\.direct_stream' dayu tests` 命中 6 处：

| 文件 | 行 | import |
| --- | --- | --- |
| `dayu/cli/commands/fins.py` | 56 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |
| `dayu/service/fins_direct.py` | 25 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |
| `tests/service/test_fins_direct.py` | 26 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |
| `tests/fins/test_fins_direct_stream.py` | 24 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |
| `tests/cli/test_fins_commands.py` | 39 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |
| `dayu/fins/ingestion_runtime.py` | 46 | `from dayu.fins.direct_stream import ValidatedFinsEventStream` |

**Plan production allowlist (§3.1) 包含:**
- `M dayu/cli/commands/fins.py` ✓
- `M dayu/fins/direct_events.py` ✓
- `D dayu/fins/direct_stream.py` ✓
- `M dayu/fins/ingestion_runtime.py` ✓
- `M dayu/service/fins_direct.py` ✓

**Plan test allowlist (§3.2) 包含:**
- `M tests/fins/test_fins_direct_stream.py` ✓
- `M tests/service/test_fins_direct.py` ✓

**缺失项:** `tests/cli/test_fins_commands.py`（line 39）不在 Slice 2 test allowlist 中。该文件 import `ValidatedFinsEventStream` 用于 CLI test，删除 `direct_stream.py` 后必须迁移此 import。

**Verdict:** 需要在 Slice 2 test allowlist 中增加 `M tests/cli/test_fins_commands.py`。

### F-02 [ACCEPTED] AR-F02 awaiting_resolution 完整 consumer list — 含 utils/ validation utility

**Plan claim (§2.3):** 从 `_ingestion_tool_helpers` 物理删除 awaiting mode 三项语义，迁到 `dayu/fins/ingestion/awaiting_resolution.py`。

**Evidence:** `rg -n 'AwaitingResolutionMode|parse_awaiting_resolution_mode|AWAITING_RESOLUTION_MODE_CONFIG_FIELD' dayu tests utils` 完整命中：

| 文件 | 符号 | 类型 |
| --- | --- | --- |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 三项定义 | 定义 owner（Slice 2 删除） |
| `dayu/fins/tools/download_provider.py` | `parse_awaiting_resolution_mode` | Fins provider |
| `dayu/fins/tools/preprocess_provider.py` | `parse_awaiting_resolution_mode` | Fins provider |
| `dayu/fins/tools/upload_provider.py` | `parse_awaiting_resolution_mode` | Fins provider |
| `dayu/service/fins_wait_adapter.py` | `AwaitingResolutionMode` | Service |
| `dayu/service/host_assembly.py` | `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` + `AwaitingResolutionMode` + `parse_awaiting_resolution_mode` | Service |
| `tests/service/test_fins_wait_adapter.py` | `AwaitingResolutionMode` | test |
| `tests/service/test_host_assembly.py` | `AwaitingResolutionMode` | test |
| `tests/fins/test_fins_ingestion_tools.py` | `AwaitingResolutionMode` + `parse_awaiting_resolution_mode` | test（Slice 2 + Slice 3） |
| `utils/smoke_host_public_awaiting_entrypoint.py` | `AwaitingResolutionMode`（8 处使用） | **validation utility — 不在任何 slice allowlist** |

**Plan production allowlist (§3.1) 包含:**
- `M dayu/fins/tools/_ingestion_tool_helpers.py` ✓
- `M dayu/fins/tools/download_provider.py` ✓
- `M dayu/fins/tools/preprocess_provider.py` ✓
- `M dayu/fins/tools/upload_provider.py` ✓
- `M dayu/service/fins_wait_adapter.py` ✓
- `M dayu/service/host_assembly.py` ✓
- `A dayu/fins/ingestion/awaiting_resolution.py` ✓

**Plan test allowlist (§3.2) 包含:**
- `M tests/service/test_fins_wait_adapter.py` ✓
- `M tests/service/test_host_assembly.py` ✓
- `M tests/fins/test_fins_ingestion_tools.py` ✓

**关键缺失:** `utils/smoke_host_public_awaiting_entrypoint.py` 不在任何 slice 的 mutable allowlist 中。详见 F-012 material finding。

**Verdict:** 除 `utils/` validation utility 外，production/test consumers 完整覆盖。

### F-03 [ACCEPTED] Service allowlist prefix matching 验证 — `dayu.fins.ingestion` 覆盖新子模块

**Plan claim (§2.3):** `tests/service/test_import_boundary.py::SERVICE_ALLOWED_IMPORTS` 不增加任何项，因为 `dayu.fins.ingestion` 使用前缀匹配。

**Evidence:** `test_import_boundary.py:86`:
```python
def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)
```

`SERVICE_ALLOWED_IMPORTS` 包含 `"dayu.fins.ingestion"`（line 25），前缀匹配会覆盖 `dayu.fins.ingestion.awaiting_resolution`。`dayu.fins.direct_events` 也在 allowlist 中（line 22）。

**Verdict:** 计划正确。Service boundary oracle 零 diff 且自然通过。

### F-04 [ACCEPTED] AR-F04 compactor test helper — `candidate_id` 确认仍在使用

**Plan claim (§2.4):** 删除 `_CANDIDATE_ID_FIELD` 与 `llm-compact:{run_id}` 逻辑，改用 manifest digest 关联。

**Evidence:** `tests/host/test_public_compact_smoke.py`:
- Line 93: `_CANDIDATE_ID_FIELD = "candidate_id"`
- Line 1785: `expected_candidate_id = f"llm-compact:{run_id}"`
- Line 1794: `if candidate.get(_CANDIDATE_ID_FIELD) == expected_candidate_id`

`_runner_call_manifest_for_run`（line 1799-1819）已使用 `schema_version` / `host_run_id` / `runner_call_kind` 定位 manifest，但 `_compact_artifact_for_run`（line 1775-1796）仍使用 `candidate_id` 匹配。

**Verdict:** 计划诊断准确。当前 helper 的 manifest 定位已是 owner-published fields，但 compact artifact 定位仍依赖已删除的 `candidate_id`。

### F-05 [ACCEPTED] AR-F01 host_admin test fixture — `wait_poller_policy` 确认缺失

**Plan claim (§4.1):** `_write_host_runtime` 缺少 `wait_poller_policy`，ConfigLoader 要求它必填。

**Evidence:**
- `tests/service/test_host_admin.py` `_write_host_runtime`（line 14-50）：不包含 `wait_poller_policy`。
- `dayu/runtime/config_loader.py` line 1932：`wait_poller_policy` 在 required fields 中。
- `dayu/config/host_runtime.json` line 21：production config 包含 `wait_poller_policy`。

**Verdict:** 计划诊断准确。测试 fixture schema 缺陷，不是 production loader 缺陷。

### F-06 [ACCEPTED] AR-F03 Web logging — `configure_root=True` 污染确认

**Plan claim (§2.5):** `utils/smoke_web_ci.py` 的 `configure_root=True` 污染全局 logging，导致同进程后续测试失败。

**Evidence:** Codex aggregate regression §2.1 记录：隔离运行 2 passed，full suite 中 `test_configure_does_not_touch_root_by_default` 和 `test_sec_request_debug_logs_success_response` 失败，同进程隔离后 2 passed。Controller adjudication 独立复现为 `46 passed, 2 failed`。

**Verdict:** 计划诊断准确。Root cause 是 test harness 未恢复 logging state。

### F-07 [MATERIAL ACCEPTED] `utils/smoke_host_public_awaiting_entrypoint.py` — Slice 2 删除 helper 后 pyright 与 public-awaiting smoke 必然失败

**Plan 缺陷:** `utils/smoke_host_public_awaiting_entrypoint.py` 是 Slice 2 exit gate 要求的真实 public-awaiting smoke（plan §4.2 "Focused tests / import-owner scans / real smoke" 明确列出）。该文件 line 87 从 `dayu.fins.tools._ingestion_tool_helpers` import `AwaitingResolutionMode`。Slice 2 的 §3.1 production allowlist 包含 `M dayu/fins/tools/_ingestion_tool_helpers.py`（删除三项语义），但 §3.2 test allowlist 和 §3.1 production allowlist 均不包含 `utils/smoke_host_public_awaiting_entrypoint.py`。

**Evidence — 完整 import graph:**

`utils/smoke_host_public_awaiting_entrypoint.py` 的 `AwaitingResolutionMode` 使用点（8 处）：
- Line 87: `from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode`
- Line 455: `f"poll={AwaitingResolutionMode.POLL.value} "`
- Line 456: `f"manual={AwaitingResolutionMode.MANUAL.value} "`
- Line 457: `f"callback={AwaitingResolutionMode.CALLBACK.value}"`
- Line 786: `mode=AwaitingResolutionMode.MANUAL,`
- Line 807: `mode=AwaitingResolutionMode.POLL,`
- Line 823: `mode=AwaitingResolutionMode.POLL,`
- Line 839: `mode=AwaitingResolutionMode.POLL,`
- Line 852: `mode=AwaitingResolutionMode.CALLBACK,`
- Line 919: `mode: AwaitingResolutionMode,`

**Failure cascade if plan executes without fix:**

1. Slice 2 删除 `_ingestion_tool_helpers.py` 中的 `AwaitingResolutionMode` 定义。
2. `utils/smoke_host_public_awaiting_entrypoint.py:87` import 失败 → **full pyright 报错**（plan §6.3 要求 0 errors）。
3. Slice 2 exit gate 的 public-awaiting smoke 命令 `python utils/smoke_host_public_awaiting_entrypoint.py ...` 运行失败 → **Slice 2 exit 不通过**。
4. §6.6 stale-import scan `rg -n 'class AwaitingResolutionMode|def parse_awaiting_resolution_mode|AWAITING_RESOLUTION_MODE_CONFIG_FIELD' dayu` 仍会命中旧定义（如果只删除而非迁移），但 utility 的 import 本身已 broken。

**AGENTS.md 合规:** `dayu/render/` 和 `utils/` 下的脚本默认无需测试、无覆盖率要求（AGENTS.md §测试与验证）。修改 `utils/` 脚本不违反测试/覆盖率约束。

**Required fix:** 给 Slice 2 增加精确 mutable validation-utility path `M utils/smoke_host_public_awaiting_entrypoint.py`，把 `AwaitingResolutionMode` import 迁到新 public owner `dayu.fins.ingestion.awaiting_resolution`，并把 public-awaiting smoke 加入 Slice 2 exit 门禁与 stale-import scan。

**Stale-import scan 增强:** §6.6 第二组 scan `rg -n 'class AwaitingResolutionMode|def parse_awaiting_resolution_mode|AWAITING_RESOLUTION_MODE_CONFIG_FIELD' dayu` 应扩展为 `rg -n 'class AwaitingResolutionMode|def parse_awaiting_resolution_mode|AWAITING_RESOLUTION_MODE_CONFIG_FIELD' dayu tests utils`，确保 `utils/` 中无残留旧 import。

**Verdict:** Material accepted finding。Plan 当前 allowlist 无法执行 Slice 2 exit gate。

### F-08 [OBSERVATION] Slice 2 test allowlist — `tests/cli/test_fins_commands.py` 缺失

同 F-01。该文件 import `ValidatedFinsEventStream`，删除 `direct_stream.py` 后必须迁移。不在当前 Slice 2 test allowlist 中。

**Verdict:** 需补充到 §3.2 Slice 2 test allowlist。

### F-09 [OBSERVATION] AR-F05 九路径 production zero-diff — 计划正确标记

**Plan §3.4 item 6:** 九个 AR-F05 production owners 在所有 slices 中必须 zero-diff。

这些文件不在 §3.1 production allowlist 中，且 Slice 3 production allowlist 严格为空（§4.3）。计划明确要求测试暴露 production defect 时 STOP。

**Verdict:** 计划约束一致。

### F-010 [OBSERVATION] Coverage 219-path ledger — `direct_stream.py` 删除 + `awaiting_resolution.py` 新增

**Plan §4.3:** 最终 aggregate ledger 预期集合变化是原 219 中删除 `dayu/fins/direct_stream.py`、新增 `dayu/fins/ingestion/awaiting_resolution.py`，总数仍为 219。

当前 219 files 中 `dayu/fins/direct_stream.py` line coverage 97.78%（PASS）。删除后新增 `awaiting_resolution.py` 需要 >=80% coverage。Slice 2 的 tests 必须覆盖新模块。

**Verdict:** 计划预期合理，但需要 Slice 2 exit 时验证新模块 coverage。

### F-011 [OBSERVATION] 三 slice 顺序符合 umbrella optimization control

**Plan §4:** Slice 1 -> Slice 2 -> Slice 3 顺序固定。

按 umbrella optimization control §slice 切分约束：
- Slice 1：不同 validation matrix（test fixture / harness / oracle），不同 failure blast radius（不改 production）。
- Slice 2：不同 semantic owner（Fins public contract），不同 failure blast radius（改 production + Service boundary）。
- Slice 3：不同 validation matrix（coverage-only，production zero-diff）。

三 slices 有明确切分理由，且不超过 umbrella 建议的 3-slice 默认值。

**Verdict:** 符合 optimization control。

## 5. Six mandatory challenges 裁决

Controller validation 定义六项 mandatory challenge。以下逐项裁决：

### Challenge 1: `direct_events.py` 合并 validator 后是否形成 import cycle、过宽 public module 或隐藏的额外 consumer

**裁决:** 无 import cycle 风险。

- `direct_stream.py` 当前 import `direct_events.py`（line 14-21：`FinsDirectStreamProtocolError`, `FinsDirectStreamProtocolErrorKind`, `FinsEvent`, `FinsEventType`, `FinsOperationKind`, `FinsResultSummary`）。合并后这些类型在同一模块内，消除跨模块依赖。
- `direct_events.py` 当前不 import `direct_stream.py`。合并后不会引入反向依赖。
- `direct_events.py` 当前已有 `FinsDirectStreamProtocolError`、`FinsOperationKind` 等类型。`ValidatedFinsEventStream` 是同一 direct event/terminal contract 的自然延伸。
- 隐藏 consumer 检查：`rg` 确认只有 6 处 import `direct_stream`，全部在 plan allowlist 中（需补充 `tests/cli/test_fins_commands.py`）。
- `direct_events.py` 当前 92.21% coverage；合并后需确保新增 validator code 被现有或新 tests 覆盖。

**Verdict:** PASS。合并自然，无 cycle，无隐藏 consumer。

### Challenge 2: Logger registry snapshot/restore 完整性

**裁决:** Plan §2.5 设计方向正确。

- 要求 snapshot root 及所有 concrete `logging.Logger` 的 level、handlers、filters、propagate、disabled。
- 要求 `finally` 中恢复并只关闭新增 handlers。
- 要求覆盖 success、返回错误码、`SystemExit`、被测异常场景。
- 要求不复制 production 列表，不写特例 logger。
- 要求增加 harness contract test。

**Observation / needs evidence:** Python `logging` 模块的 `logging.Logger.manager.loggerDict` 是进程全局状态。如果 `smoke.main()` 创建了 named logger（通过 `logging.getLogger("some_new_name")`），这些 logger 会留在 registry 中。Plan 要求"清除本次调用新建的 logger entries"，但 Python logging 不提供原生 `removeLogger` API；需要从 `manager.loggerDict` 中删除或标记为 `PLACEHOLDER`。

**Status:** 这是 observation / needs-evidence，不是 plan blocker。没有直接证据证明当前 plan 无法实施；需要实现时验证 `smoke.main()` 是否创建新 named logger 以及 registry 清理的可行性。

**Verdict:** PASS。Plan 设计方向正确，logging registry 限制为 observation。

### Challenge 3: Runner-call manifest 到 compact artifact 的 digest 关联唯一性

**裁决:** Plan §2.4 设计严格。

- Manifest 定位使用 `schema_version` + `host_run_id` + `runner_call_kind`（已由现有 `_runner_call_manifest_for_run` 验证）。
- 从 manifest 的 `compactor_identity.compaction_request_digest` 读取 SHA-256 digest。
- Compact artifact 定位使用 `artifact_kind == "context_compaction"` + top-level `compaction_request_digest` equality。
- 断言 `parent_host_run_id == host_run_id`。
- 禁止 candidate_id、文件名、顺序、mtime、loose scan。

**Verdict:** PASS。设计严格且可测试。duplicate/malformed fail-closed 路径在 plan 的 deterministic cases 中覆盖。

### Challenge 4: Slice 3 六个测试文件覆盖九个 production paths 的可行性

**裁决:** Plan §4.3 的测试策略合理。

九个 production paths 和对应测试文件：

| Production owner | Test file | 风险 |
| --- | --- | --- |
| `docling_processor.py` (63.46%) | `tests/documents/test_processors.py` | 需要 Docling payload 测试 |
| `sec_6k_rules.py` (67.56%) | `tests/fins/test_sec_pipeline_download.py` | 需要 SEC pipeline 测试 |
| `sec_form_section_common.py` (78.23%) | `tests/fins/test_processor_read_consistency.py` | 需要 section 构建测试 |
| `sec_report_form_common.py` (65.14%) | 同上 | 需要 report form 测试 |
| `sec_section_build.py` (77.56%) | 同上 | 需要 section build 测试 |
| `sec_table_extraction.py` (66.16%) | 同上 | 需要 table extraction 测试 |
| `preprocess_tools.py` (75.81%) | `tests/fins/test_fins_ingestion_tools.py` | 需要 preprocess 测试 |
| `_execution_config_projection.py` (76.43%) | `tests/host/test_effective_execution_config.py` | 需要 config projection 测试 |
| `argparse_exit.py` (未命中) | `tests/runtime/test_argparse_exit.py` (新建) | 需要 argparse exit 测试 |

**风险点:**
- `docling_processor.py` 从 63.46% 到 80% 需要覆盖较多分支。Plan 要求"不得直接复制 production 算法到期望值"，这意味着测试必须通过 public processor 结果断言，而非 mirror 内部逻辑。
- `sec_table_extraction.py` 从 66.16% 到 80% 同理。
- Plan 的 stop condition 要求：测试暴露 production defect 时立即停止。

**Verdict:** PASS。六文件足以覆盖九路径，但实现难度不可低估。Plan 的 stop condition 是正确防线。

### Challenge 5: 219-path ledger、R05 single-node exclusion、Ruff baseline 和 Slice 1 临时 failure 可执行性

**裁决:**

- **219-path ledger:** Plan §6.2 使用 `git diff --name-only --diff-filter=ACMR 3410d74..FINAL_ACCEPTED_HEAD -- 'dayu/**/*.py'` 生成。Codex 已确认 219 个。Slice 2 删除 `direct_stream.py` + 新增 `awaiting_resolution.py` 后仍为 219。可执行。
- **R05 single-node exclusion:** `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`。Plan 明确只用于 coverage measurement，canonical non-coverage suite 仍执行该 node。可执行。
- **Ruff baseline:** 当前 144 findings。Plan 要求完整集合相对 slice base 不得新增，mutable paths 必须 0 finding。可执行。
- **Slice 1 临时 failure:** `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 在 Slice 1 保持已知失败（因为 AR-F02 尚未实施）。Plan 明确这不是 waiver，Slice 2 exit 后不得再存在。可执行。

**Verdict:** PASS。四项均可执行且有明确验证标准。

### Challenge 6: 三 slice 顺序是否是最小可验证闭环

**裁决:**

- Slice 1 修 test fixture / harness / oracle，不改 production。它是 Slice 2/3 的前置，因为 canonical suite 需要先恢复全绿（除 AR-F02 临时失败）。
- Slice 2 迁 Fins public owner，改 production。它依赖 Slice 1 的 test oracle 恢复（特别是 AR-F04 compactor oracle），且需要 canonical suite 全绿。
- Slice 3 补 coverage tests，不改 production。它依赖 Slice 2 的 stable integration tree。

依赖链：Slice 1 (test oracle) -> Slice 2 (production migration) -> Slice 3 (coverage closure)。不可并行，不可重排。

每 slice 验证成本：
- Slice 1：focused tests + canonical suite + coverage + pyright + Ruff + build + scans + smokes。
- Slice 2：同上 + import boundary + rg scans + real Fins/Host smoke。
- Slice 3：同上 + 九路径 focused coverage + real smoke。

每 slice 全量验证成本一致，符合 umbrella optimization control 的 "production-high" profile。

**Verdict:** PASS。三 slice 是最小可验证闭环。

## 6. Open questions

1. **`tests/cli/test_fins_commands.py` 未在 Slice 2 test allowlist 中。** 该文件 import `ValidatedFinsEventStream`（line 39），删除 `direct_stream.py` 后必须迁移。建议 Controller 补充到 §3.2 Slice 2 test allowlist。
2. **`dayu/fins/ingestion/awaiting_resolution.py` 新模块的 coverage。** 219-path ledger 需要该模块 >=80%。Slice 2 的 tests 必须覆盖新模块的定义和使用。Plan 未明确列出该模块的 coverage 来源测试，但 Slice 2 的 focused tests 包含 `tests/fins/test_fins_ingestion_tools.py` 和 `tests/service/test_fins_wait_adapter.py`，预计可覆盖。

## 7. Residuals

| ID | 状态 | 说明 |
| --- | --- | --- |
| AR-F06 | RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX | scheduler close/terminal promotion bug，后续独立 work item |
| AR-F07 | PENDING_RELEASE_BLOCKER | Windows real runner evidence 不存在 |
| Coverage timing | EXISTING_COVERAGE_TIMING_BASELINE | R05 scheduler node 在 coverage 下复现，精确单 node exclusion |
| Logger registry | OBSERVATION / NEEDS_EVIDENCE | Python logging 内部 API 限制；不是 plan blocker，需实现时验证 |

## 8. Verdict

**PASS_WITH_THREE_ACCEPTED_FINDINGS / READY_FOR_CONTROLLER_ADJUDICATION。**

Plan 整体设计严谨、约束精确、验证门禁完整。六个 mandatory challenges 全部通过。发现三个需要 Controller 裁决的 accepted findings：

1. **F-01/F-08:** `tests/cli/test_fins_commands.py` 需补充到 Slice 2 test allowlist。
2. **F-012 (material):** `utils/smoke_host_public_awaiting_entrypoint.py` 从 `_ingestion_tool_helpers` import `AwaitingResolutionMode`（8 处使用），Slice 2 删除该定义后 pyright 与 public-awaiting smoke 必然失败。需给 Slice 2 增加 `M utils/smoke_host_public_awaiting_entrypoint.py`，迁到新 public owner，并把 public-awaiting smoke 加入 Slice 2 exit 与 stale-import scan。
3. **F-02 (updated):** 完整 consumer scan（含 `utils/`）确认 10 个文件消费 awaiting 三项语义；除 F-012 的 `utils/` 路径外，production/test consumers 均在 allowlist 中。

Logging registry caveat 保持 observation / needs-evidence 状态，不是 plan blocker。

Plan 不授权 implementation、stage、commit、push、PR、aggregate deepreview 或 closeout。下一 gate 由 Controller 裁决 findings 后决定。
