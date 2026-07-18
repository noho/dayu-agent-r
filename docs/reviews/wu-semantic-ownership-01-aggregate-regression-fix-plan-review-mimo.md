# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Plan — AgentMiMo Review

## 0. Gate identity

- 状态：`REVIEW_COMPLETE`。
- umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 review 覆盖 aggregate regression accepted-finding fix plan 的第一路完整独立 plan review。
- review posture：constructively adversarial；独立读取全部 source material 并直接验证代码事实，不复用 Controller validation 或另一 reviewer 结论。

## 1. Review metadata

| 项 | 值 |
| --- | --- |
| system clock | 2026-07-18 |
| reviewed artifact | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` |
| reviewed SHA-256 | `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e`（独立 `sha256sum` 核对通过） |
| reviewed lines / bytes | 610 / 44,252（`wc -l -c` 核对通过） |
| implementation baseline | `ed9bfa9fe071aba0227361c69a938010ce3abe09` |
| aggregate comparison parent | `3410d7422655c56bdf13c643f77c27f40b9d4550` |
| current worktree status | `M docs/host/issues-implementation-control.md`（Controller-owned）；plan、codex、adjudication、controller-validation 为 untracked；staged 为空；HEAD 未变 |

## 2. Source material read

Reviewer 独立完整读取以下 material：

1. `AGENTS.md` — 项目约束、思考纪律、语义所有权、LLM-facing 文本约束、架构/编码硬约束。
2. `docs/host/issues-implementation-control.md` — current gate 与 aggregate adjudication。
3. `docs/phaseflow-umbrella-optimization-control.md` — umbrella slice 切分、风险分级、review 路由、validation profile。
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — 九项 Topic 裁决与 design writeback。
5. 五份 design 真源：`docs/host/design.md`（部分，379KB 超限）、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
6. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` — fresh command/evidence ledger。
7. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` — finding disposition。
8. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md` — six mandatory challenges。
9. 当前 HEAD 代码事实验证（见 §3）。

## 3. Code fact verification

Reviewer 独立验证以下代码事实：

### 3.1 Service import boundary

- `tests/service/test_import_boundary.py` 的 `SERVICE_ALLOWED_IMPORTS` 精确包含 11 项（lines 21-33）：`dayu.fins.direct_events`、`dayu.fins.direct_event_text`、`dayu.fins.domain.enums`、`dayu.fins.ingestion`、`dayu.fins.ingestion_runtime`、`dayu.fins.resolver`、`dayu.fins.service_runtime`、`dayu.fins.ticker_normalization`、`dayu.fins.tools.download_tools`、`dayu.fins.tools.preprocess_tools`、`dayu.fins.tools.upload_tools`。
- 三处越界 import 已确认：
  - `dayu/service/fins_direct.py:25` → `dayu.fins.direct_stream`。
  - `dayu/service/fins_wait_adapter.py:40` → `dayu.fins.tools._ingestion_tool_helpers`。
  - `dayu/service/host_assembly.py:40-44` → `dayu.fins.tools._ingestion_tool_helpers`。

### 3.2 Fins direct_stream / direct_events 结构

- `direct_stream.py` 依赖 `direct_events.py`（单向），定义 `_ValidatedStreamState`（私有 enum）与 `ValidatedFinsEventStream`（公共类）。
- `direct_events.py` 不依赖 `direct_stream.py`，定义 5 个 enum、1 个 exception、4 个 dataclass、6 个私有验证 helper，`__all__` 导出 13 个符号。
- `ValidatedFinsEventStream` 的消费者共 6 处：
  - Production：`dayu/fins/ingestion_runtime.py:46`、`dayu/cli/commands/fins.py:56`、`dayu/service/fins_direct.py:25`。
  - Test：`tests/fins/test_fins_direct_stream.py:24`、`tests/cli/test_fins_commands.py:39`、`tests/service/test_fins_direct.py:26`。
- Plan §3.2 Slice 2 test allowlist 包含 `tests/fins/test_fins_direct_stream.py` 和 `tests/service/test_fins_direct.py`，但**不包含** `tests/cli/test_fins_commands.py`。该文件 `from dayu.fins.direct_stream import ValidatedFinsEventStream` 在 `direct_stream.py` 删除后将立即 ImportError。

### 3.3 Awaiting resolution 结构

- `AwaitingResolutionMode`、`parse_awaiting_resolution_mode`、`AWAITING_RESOLUTION_MODE_CONFIG_FIELD` 全部定义在 `dayu/fins/tools/_ingestion_tool_helpers.py`。
- Production consumers：`download_provider.py`、`preprocess_provider.py`、`upload_provider.py`（各 import `parse_awaiting_resolution_mode`）；`fins_wait_adapter.py`（import `AwaitingResolutionMode`）；`host_assembly.py`（import 全部三项）。
- Test consumers：`tests/fins/test_fins_ingestion_tools.py`、`tests/service/test_host_assembly.py`、`tests/service/test_fins_wait_adapter.py`。
- **非 allowlist consumer**：`utils/smoke_host_public_awaiting_entrypoint.py:87` import `AwaitingResolutionMode`。`utils/` 不在 production 或 test allowlist 任一范围内。
- `dayu/fins/ingestion/__init__.py` 存在，当前 `__all__` 包含 12 个符号（均来自 `observation_handle.py`），不包含 awaiting mode 三项。

### 3.4 Compactor test oracle

- `tests/host/test_public_compact_smoke.py:93` 定义 `_CANDIDATE_ID_FIELD = "candidate_id"`。
- `_compact_artifact_for_run`（lines 1774-1796）使用 `f"llm-compact:{run_id}"` 构造 `expected_candidate_id`，通过 `candidate.get(_CANDIDATE_ID_FIELD)` 匹配。
- `_runner_call_manifest_for_run`（lines 1799-1819）已使用 `schema_version`、`host_run_id`、`runner_call_kind == "compactor_proposal"` 三重过滤。
- 文件中**零引用** `compaction_request_digest`。
- Plan §2.4 的四步关联链路（manifest → digest → compact artifact → content assertions）是正确的迁移方向。

### 3.5 Host admin fixture

- Plan §4.1 声称 `_write_host_runtime` 需要写出 12 字段的 `wait_poller_policy`。已确认 `ConfigLoader` 将其列为必填（blame R04）。Plan 的 12 字段列表与 Controller adjudication 一致。

## 4. Review assumptions

1. 当前 HEAD `ed9bfa9` 是稳定 implementation baseline，不因本 review 改变。
2. Controller adjudication 的 7 项 finding disposition（AR-F01—AR-F07）是已接受的真源，本 review 不重新裁决 finding 有效性。
3. `docs/host/design.md` 因体积限制（379KB）只读取了部分内容；关键 claim 通过 `docs/engine/design.md`、`docs/fins/design.md` 和代码事实交叉验证。
4. 本 review 假设 Controller validation 的六项 mandatory challenges 是必须独立裁决的 checklist，不自动 PASS。

## 5. Controller validation mandatory challenges 独立裁决

### Challenge 1：`direct_events.py` 合并 validator 后是否形成 import cycle、过宽 public module 或隐藏的额外 consumer，及 awaiting mode 新 owner 是否真能保持 Service allowlist 零改动

**裁决：PASS（with accepted-candidate concern about module width）**

- **Import cycle**：`direct_stream.py` 依赖 `direct_events.py`（单向），合并后依赖消失，无 cycle 风险。
- **过宽 public module**：`direct_events.py` 当前 `__all__` 导出 13 个符号。加入 `ValidatedFinsEventStream` 与 `_ValidatedStreamState`（私有）后增至 14 个公共符号。这些类型属于同一 direct-event/terminal-contract 领域，聚合合理。但 §6 finding #6 记录了关于长期模块宽度的 accepted-candidate concern。
- **隐藏的额外 consumer**：验证确认 6 处消费者（§3.2），plan §3.2 Slice 2 test allowlist 覆盖 4 处（2 production + 2 test），遗漏 2 处（`tests/cli/test_fins_commands.py` 与 `utils/smoke_host_public_awaiting_entrypoint.py`）。见 §6 finding #1 和 #2。
- **Service allowlist 零改动**：`dayu.fins.direct_events` 已在 allowlist，validator 迁入后 Service import 路径从 `dayu.fins.direct_stream` 变为 `dayu.fins.direct_events`，无需改 allowlist。Awaiting mode 新 owner `dayu.fins.ingestion.awaiting_resolution` 命中现有 `dayu.fins.ingestion` 前缀匹配，同样无需改 allowlist。**PASS**。

### Challenge 2：logger registry snapshot/restore 是否能在所有场景下完整恢复

**裁决：PASS（needs-evidence on boundary cases）**

- Plan §2.5 的设计要求全面：snapshot root/named logger 的 level、handlers、filters、propagate、disabled、registry identity；finally 中恢复；卸载并关闭新增 handlers；清除新建 logger entries。
- Python `logging` 模块的 handler 关闭语义、`Logger.manager.loggerDict` 清理和 `disabled` flag 恢复在边界情况下有微妙行为（例如 handler 持有 file/socket 资源、logger disabled 后 re-enable 丢失 level 设置）。Plan 要求 harness contract test 覆盖成功和失败路径，这降低了风险。
- **needs-evidence**：实际实现是否能在 `SystemExit` + 新增 named logger + handler 持有资源的组合场景下无泄漏，需要看实现和测试代码。Plan 设计方向正确，但不预判实现质量。

### Challenge 3：runner-call manifest 到 compact artifact 的 digest 关联是否在 current schema 中唯一、严格、可测试

**裁决：PASS**

- Code verification 确认 `_runner_call_manifest_for_run` 已使用 `schema_version` + `host_run_id` + `runner_call_kind` 三重过滤。
- Plan 要求从 manifest 的 `compactor_identity.compaction_request_digest` 读取 SHA-256 digest，并在 compact artifact 集合中以 `artifact_kind == "context_compaction"` + `compaction_request_digest` 精确匹配。
- 这是 owner-published exact field equality，不是 guess/fallback。唯一性由 `host_run_id` → 单一 manifest → 单一 digest → 单一 compact artifact 保证。
- Plan 要求新增 deterministic fail-closed cases（missing manifest、duplicate manifest、missing artifact、duplicate artifact、wrong/missing digest），覆盖了异常路径。**PASS**。

### Challenge 4：Slice 3 六个测试文件是否足以通过 public/owner-observable contract 覆盖九个 production paths

**裁决：PASS（with needs-evidence on SEC processor depth）**

- 4 个 SEC processors 共享 `tests/fins/test_processor_read_consistency.py`，可能导致某些 processor 专有分支覆盖不足。§6 finding #3 记录此 concern。
- `dayu/runtime/argparse_exit.py` 当前未命中，新建 `tests/runtime/test_argparse_exit.py` 覆盖 int codes / None / string / other → usage error 2，简单且充分。
- `dayu/host/_execution_config_projection.py` 由 `tests/host/test_effective_execution_config.py` 覆盖，按 plan 描述包含 optional/required JSON scalar matrix、round-trip、missing/wrong/unknown/tampered fail-closed，owner contract 方向正确。
- `dayu/documents/processors/docling_processor.py` 由 `tests/documents/test_processors.py` 覆盖，plan 列出 10+ 行为家族。
- Plan 设置了 stop condition：若测试暴露 production defect 或只有 private implementation mirroring 才能达到 80%，立即停止。这是正确的安全阀。

### Challenge 5：219-path ledger、R05 single-node coverage exclusion、Ruff immutable baseline 和 Slice 1 临时 import-boundary failure 是否可执行且不会被误签为 waiver/PASS

**裁决：PASS（with minor issue on Ruff baseline）**

- 219-path ledger：Plan §6.2 明确 `git diff --name-only --diff-filter=ACMR 3410d742..FINAL_ACCEPTED_HEAD` 生成集合，必须恰好 219 个。Slice 3 exit 预期 `219/219 >=80%`，明确 `dayu/fins/direct_stream.py` 删除 + `dayu/fins/ingestion/awaiting_resolution.py` 新增，总数不变。可执行。
- R05 single-node exclusion：Plan §6.2 精确到 `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`，且明确 canonical non-coverage suite 仍必须执行该 node。不构成 waiver。
- Ruff immutable baseline：Plan 声称"当前 full Ruff immutable baseline 是 144 findings"，但未提供具体集合。实现者需要自行采集。§6 finding #4 记录此 minor issue。
- Slice 1 临时 import-boundary failure：Plan §4.1 明确声明 Slice 1 只允许 `test_import_boundary.py::test_service_does_not_import_forbidden_layers` 保持已知失败，且"这个临时预期不是 waiver，Slice 2 exit 后不得再存在"。可执行且不构成误签。

### Challenge 6：三 slice 顺序是否是最小可验证闭环，及每 slice 全量验证成本是否仍符合 umbrella optimization control

**裁决：PASS**

- 三 slice 顺序（test oracle → Fins migration → coverage）满足依赖关系：先修复导致 suite 失败的 test defects，再修复 architecture boundary，最后在稳定整合树补齐 coverage。
- Phaseflow umbrella optimization control 对 High Risk 建议完整 gate，本 plan 的每 slice 双路 review/fix/完整 re-review 符合要求。
- 三 slice 数量在 Medium Risk 建议的 2-3 个范围内。每个 slice 有不同的 semantic owner（test harness / Fins contract / production coverage）、不同 validation matrix 和不同 failure blast radius，切分理由成立。
- Slice 1 和 Slice 3 都是 test-only，理论上可合并；但 Slice 1 修复 suite-blocking defects 而 Slice 3 只增 coverage，合并会增加 review 范围并掩盖中间状态。分开更安全。**PASS**。

## 6. Findings

### Finding #1 — accepted-candidate：Plan 不可直接实施 — Slice 2 删除 `direct_stream.py` 后 canonical suite 将 collection/import failure，exact allowlist 又禁止修改该 consumer

**严重性**：HIGH — plan non-actionability blocker。
**证据（rg 独立核对）**：

```text
$ rg -n 'from dayu\.fins\.direct_stream import' dayu tests
dayu/service/fins_direct.py:25:from dayu.fins.direct_stream import ValidatedFinsEventStream
tests/service/test_fins_direct.py:26:from dayu.fins.direct_stream import ValidatedFinsEventStream
dayu/cli/commands/fins.py:56:from dayu.fins.direct_stream import ValidatedFinsEventStream
tests/cli/test_fins_commands.py:39:from dayu.fins.direct_stream import ValidatedFinsEventStream
dayu/fins/ingestion_runtime.py:46:from dayu.fins.direct_stream import ValidatedFinsEventStream
tests/fins/test_fins_direct_stream.py:24:from dayu.fins.direct_stream import ValidatedFinsEventStream
```

共 6 处 consumer。Plan §3.1 Slice 2 production allowlist 包含 3 处 production consumer（`fins_direct.py`、`fins.py`、`ingestion_runtime.py`）。Plan §3.2 Slice 2 test allowlist 包含 2 处 test consumer（`test_fins_direct_stream.py`、`test_fins_direct.py`）。**第 6 处 `tests/cli/test_fins_commands.py:39` 不在任何 slice 的 mutable test allowlist 中。**

Plan §3.1 `D dayu/fins/direct_stream.py` 在 Slice 2 执行删除。该模块删除后，`tests/cli/test_fins_commands.py` 的 `from dayu.fins.direct_stream import ValidatedFinsEventStream` 将立即 `ModuleNotFoundError`。Pytest collection 阶段即失败，不是单个 test node 失败。

**影响链**：
1. Slice 2 implementation 完成后，§6.1 canonical non-coverage full suite `pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli` 将在 collection 阶段失败。
2. Slice 2 exit 条件要求"0 failed"（§4.2），此 failure 阻塞 exit。
3. Plan §6.4 要求 diff 精确匹配 slice allowlist，不允许额外路径。即使实现者发现此问题，也不能自行将 `tests/cli/test_fins_commands.py` 加入 diff，因为这违反 exact allowlist 约束。
4. 结果：plan 在当前形式下不可直接实施。实现者要么违反 allowlist 自行修复（违反 plan gate），要么停在 Slice 2 exit 无法推进。

**补充确认**：`tests/fins/test_fins_ingestion_runtime.py` 不在上述 rg 命中列表中，确认该文件不 import `direct_stream`，不存在同类问题。

**分类**：accepted-candidate。
**修复方向**：将 `tests/cli/test_fins_commands.py` 加入 §3.2 Slice 2 mutable test allowlist。该文件只需将 import 路径从 `dayu.fins.direct_stream` 改为 `dayu.fins.direct_events`（与 `dayu/cli/commands/fins.py` 同一迁移），属于 Slice 2 物理 owner migration 的机械 consumer 更新。同时在 §4.2 Slice 2 focused tests 命令中增加 `tests/cli/test_fins_commands.py`，并在 consumer scan 中覆盖该路径确认无残留旧 import。

### Finding #2 — accepted-candidate：`utils/smoke_host_public_awaiting_entrypoint.py` 不在任何 allowlist 中

**严重性**：MEDIUM — smoke gate blocker。
**证据**：`utils/smoke_host_public_awaiting_entrypoint.py:87` 包含 `from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode`。Plan §3.1 production allowlist 只包含 `dayu/` 路径，不包含 `utils/`。§3.2 test allowlist 只包含 `tests/` 路径。`utils/smoke_web_ci.py` 在 §3.4 protected zero-diff paths 中被保护，但 `smoke_host_public_awaiting_entrypoint.py` 不在 protected paths 中。
**影响**：Slice 2 的 `dayu/fins/tools/_ingestion_tool_helpers.py` 被修改（删除三项语义），但此 utils 文件仍 import 旧路径。Plan §4.2 的真实 smoke 命令 `python utils/smoke_host_public_awaiting_entrypoint.py ...` 将 ImportError 或 import 旧路径。
**分类**：accepted-candidate。
**修复方向**：将 `utils/smoke_host_public_awaiting_entrypoint.py` 加入 §3.1 Slice 2 production allowlist（或在 §3.4 声明为需要更新的 utils 文件），并更新其 import 路径。注意 `utils/smoke_host_public_r03_semantic_ownership.py` 也可能有类似问题，需验证其 imports。

### Finding #3 — needs-evidence：四个 SEC processors 共享单个测试文件的覆盖深度

**严重性**：LOW — coverage risk，有 stop condition 保护。
**证据**：Plan §4.3 列出 `tests/fins/test_processor_read_consistency.py` 覆盖 `sec_form_section_common.py`（78.23%）、`sec_report_form_common.py`（65.14%）、`sec_section_build.py`（77.56%）、`sec_table_extraction.py`（66.16%）四个 production owner。当前 baseline coverage 显示各文件覆盖差距大（65%—78%），说明未覆盖分支各异。
**影响**：单个测试文件需要同时为四个不同 processor 的不同未覆盖分支补充 owner-contract cases。若某些 processor 的未覆盖分支需要深层 fixture 或复杂 mock，可能导致部分文件达到 80% 而其他文件不足。
**分类**：needs-evidence。
**缓解**：Plan §4.3 stop condition 明确"若只有修改 production/直接耦合不稳定私有实现才能达到 80%，立即停止 Slice 3"。这是一个有效安全阀。实现者需要在 Slice 3 开始前先对每个文件做 focused coverage analysis，确认可测分支是否足够。

### Finding #4 — needs-evidence：`direct_events.py` 合并后模块宽度

**严重性**：LOW — 可维护性 concern，不阻塞 implementation。
**证据**：`direct_events.py` 当前 13 个公共符号 + 6 个私有 helper。加入 `ValidatedFinsEventStream` 后公共符号增至 14 个，加上 `_ValidatedStreamState`（私有）。这些类型属于同一 direct-event/terminal-contract 领域。
**影响**：模块仍然内聚，不违反 AGENTS.md "禁止 God object" 约束。但如果未来 direct event 领域继续扩展，可能需要拆分。当前规模可接受。
**分类**：needs-evidence（长期演进风险，不影响本轮实现）。
**缓解**：本轮只迁 owner，不重设计。若模块后续膨胀，可由未来 refactor 处理。

### Finding #5 — needs-evidence：logger snapshot/restore 边界行为

**严重性**：LOW — 实现质量 concern。
**证据**：Plan §2.5 的设计全面，但 Python `logging.Logger.manager.loggerDict` 清理、`Logger.disabled` flag 恢复和 handler 资源释放的边界行为需要实际实现验证。
**影响**：若实现不完善，可能导致测试间状态泄漏或资源泄漏。
**分类**：needs-evidence。
**缓解**：Plan 要求 harness contract test 覆盖预置非默认状态 + 成功/失败调用 + 断言完全恢复。这是正确方向。

### Finding #6 — deferred-candidate：Ruff immutable baseline 未在 plan 中建立

**严重性**：INFO — 不阻塞 implementation。
**证据**：Plan §6.3 声称"当前 full Ruff immutable baseline 是 144 findings"，但未提供具体的 `(filename, row, column, code, message)` 集合。
**影响**：实现者需要在 Slice 1 开始前自行采集 baseline 集合。这是可执行的额外步骤，但增加了实现者的判断负担。
**分类**：deferred-candidate（实现者自行处理）。

### Finding #7 — deferred-candidate：Slice 2 中 Fins tools providers 的 import 迁移未在 plan 中显式说明

**严重性**：INFO — 机械迁移，不阻塞。
**证据**：`download_provider.py`、`preprocess_provider.py`、`upload_provider.py` 各自 import `parse_awaiting_resolution_mode` from `dayu.fins.tools._ingestion_tool_helpers`。Slice 2 删除该符号后，这三个文件需要更新 import 路径。它们已在 §3.1 production allowlist 中（`M dayu/fins/tools/download_provider.py` 等），但 plan §4.2 的 implementation 文字只提到"从 tools 私有 helper 删除三项语义，迁移三个 provider"，未明确说明 provider 自身的 import 路径也需要更新。
**影响**：实现者需要理解这属于"迁移三个 provider"的一部分。方向明确，只是文字可更精确。
**分类**：deferred-candidate（实现者自行理解）。

## 7. Residual risks

Plan §9 的 residual risks 审查：

- **AR-F06 RETAINED / UNFIXED / UNWAIVED**：Plan 正确保持 no-code residual。Coverage exclusion 精确到单个 test node，canonical non-coverage suite 仍执行该 node。不构成 waiver。**PASS**。
- **AR-F07 PENDING_RELEASE_BLOCKER**：Plan 正确保持外部 Windows evidence gate。不伪造 PASS。**PASS**。
- **AR-F05 大型 SEC/Docling owner 的 80% 门槛**：Plan 设置 stop condition，正确。**PASS**。
- **219 集合稳定性**：Plan 预期 `dayu/fins/direct_stream.py` 删除 + `dayu/fins/ingestion/awaiting_resolution.py` 新增，总数不变。正确。**PASS**。

## 8. Overengineering / overcoupling / best practice 审查

- **AR-F02 物理 owner migration vs. allowlist expansion**：Plan 选择物理迁移而非扩大 allowlist。这是正确的语义所有权方向：问题在 Fins public contract owner 放错边界，不在 Service allowlist 太窄。符合 AGENTS.md "代码必须改在 owner boundary" 约束。**PASS**。
- **AR-F03 test-only harness vs. standalone logging 改动**：Plan 只改测试，不动 standalone 产品 logging。符合"bug fix 禁止局部止血"——root cause 是测试未隔离，不是产品 logging 行为错误。**PASS**。
- **AR-F04 current schema oracle vs. candidate_id 恢复**：Plan 删除 `llm-compact:{run_id}` guess，使用 owner-published digest equality。符合 AGENTS.md "禁止从 raw fields 反推语义"。**PASS**。
- **Slice 切分**：三 slice 按不同 semantic owner / validation matrix / blast radius 切分，符合 Phaseflow umbrella optimization control 的切分约束。不按文件/finding 机械切分。**PASS**。

## 9. Security / deferred / no-code 审查

- Plan §6.7 的 security/secret/deferred/no-code ledger 设计完整，与 Controller codex artifact §7/§8 一致。
- Protected zero-diff paths（§3.4）精确覆盖 scheduler、standalone logging、config owner、compact owners、boundary traps、nine production owners、workflow files。
- AR-F06 scheduler path 保护明确：不得加入 retry、sleep、xfail、skip、timeout 放宽或 test-order 特例。
- **PASS**。

## 10. Verdict

**CONDITIONAL PASS — 2 accepted-candidate findings must be resolved before implementation.**

Plan 在 goal/non-goals、owner adjudication、scope lock、slice 顺序、architecture boundary、semantic ownership、测试/coverage/smoke 门禁、AR-F06 retained residual、AR-F07 Windows blocker 等维度均通过 constructively adversarial 挑战。

两项 accepted-candidate findings 阻塞 implementation：

1. **Finding #1**（HIGH）：`tests/cli/test_fins_commands.py` 不在 Slice 2 test allowlist，`direct_stream.py` 删除后将导致 ImportError。
2. **Finding #2**（MEDIUM）：`utils/smoke_host_public_awaiting_entrypoint.py` 不在任何 allowlist，`_ingestion_tool_helpers.py` 语义删除后将导致 smoke gate 失败。

四项 needs-evidence findings 不阻塞 implementation，但实现者需在对应 slice 验证时确认：
- Finding #3：四个 SEC processors 共享单个测试文件的覆盖深度。
- Finding #4：`direct_events.py` 合并后模块宽度。
- Finding #5：logger snapshot/restore 边界行为。
- Finding #6：Ruff immutable baseline 未在 plan 中建立（deferred）。

一项 deferred-candidate finding：Finding #7（Slice 2 providers import 迁移说明）。

## 11. Artifact measurement

```text
artifact_wc_lines: 0000000250
artifact_wc_bytes: 0000023185
artifact_sha256: 5ecd544eadf11eb172ff3c9248b8b2672e9eb6551b6134deaa88e4d17ab66c84
```

Review command：

```bash
wc -l -c docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md
shasum -a 256 docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md
```
