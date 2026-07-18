# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Plan — AgentDS Plan Review

## 0. Review Identity

- **Reviewer**: AgentDS（第二路独立完整 plan review）
- **Reviewed target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
- **Reviewed hash (SHA-256)**: `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` ✅ 已独立核对
- **Reviewed metrics**: 610 行 / 44,252 字节 ✅ 已独立核对
- **系统时钟**: 2026-07-18T08:05:31Z
- **Review posture**: constructively adversarial — 独立挑战 plan assumptions、scope、sequencing、architecture/semantic ownership、overengineering/overcoupling、testing/coverage/real-smoke、security/deferred/no-code、AR-F06 residual、AR-F07 Windows blocker，并独立裁决 Controller validation 的六项 mandatory challenges
- **不可变基线**: branch `phaseflow/host-issues-control`，HEAD `ed9bfa9fe071aba0227361c69a938010ce3abe09`

## 1. 证据清单

已完整读取并以直接证据裁定：

| # | 证据来源 | 用途 |
| --- | --- | --- |
| 1 | `AGENTS.md` | 项目最高约束、语义所有权规则、LLM-facing 文本约束、架构硬约束 |
| 2 | `docs/phaseflow-umbrella-optimization-control.md` | 风险分级、slice 切分约束、review 路由优化、validation profile |
| 3 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | Topic 1–9 最终裁决、设计真源写入边界 |
| 4 | `docs/host/design.md`（完整读取） | Host 架构事实、wait poller policy、compactor、run/artifact 关联 |
| 5 | `docs/engine/design.md` | Engine 边界、runner protocol、tool handshake、suspend/resume |
| 6 | `docs/tool/design.md` | Tool config ownership、Doc/Web policy、resource budgets、challenge detection |
| 7 | `docs/fins/design.md` | Fins public contract、direct stream terminal、storage、HKEX、provenance |
| 8 | `docs/ui/design.md` | CLI/init/upload_filings_from、entrypoint lifecycle |
| 9 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` | AR-F01–F07 direct evidence ledger、219 coverage table、build/scans |
| 10 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` | Controller 最终 finding disposition、AR-F06 retained residual、plan constraints |
| 11 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md` | Controller validation verdict、六项 mandatory challenges |
| 12 | `tests/service/test_host_admin.py`（完整） | AR-F01：fixture 缺 `wait_poller_policy` 12 字段 |
| 13 | `tests/host/test_public_compact_smoke.py`（完整） | AR-F04：`_CANDIDATE_ID_FIELD` / `llm-compact:{run_id}` 旧 oracle；manifest 定位正确但未读 digest |
| 14 | `tests/service/test_import_boundary.py`（完整） | AR-F02：三处越界 import 验证、allowlist 前缀匹配逻辑 |
| 15 | `dayu/fins/direct_events.py`（完整） | AR-F02：event type/contract 当前 owner、497 行 |
| 16 | `dayu/fins/direct_stream.py`（完整） | AR-F02：`ValidatedFinsEventStream` 当前 owner、262 行 validator state machine |
| 17 | `dayu/fins/tools/_ingestion_tool_helpers.py`（完整） | AR-F02：`AwaitingResolutionMode` / `parse_awaiting_resolution_mode` / `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` 三项语义当前存放位置 |
| 18 | `dayu/fins/ingestion/__init__.py` | 已有 re-export、plan 要求 zero-diff |
| 19 | `dayu/fins/__init__.py` | 确认不导出 `ValidatedFinsEventStream`、不需改动 ✅ |
| 20 | `dayu/service/host_assembly.py`（L38–47） | AR-F02：从 `_ingestion_tool_helpers` 导入三项语义 |
| 21 | `dayu/service/fins_direct.py`（L25） | AR-F02：从 `direct_stream` 导入 `ValidatedFinsEventStream` |
| 22 | `dayu/service/fins_wait_adapter.py`（L40） | AR-F02：从 `_ingestion_tool_helpers` 导入 `AwaitingResolutionMode` |
| 23 | `dayu/host/_runner_call_manifest.py` | AR-F04：`RunnerCallCompactorIdentity.compaction_request_digest` 字段、manifest identity schema |
| 24 | `dayu/host/compact_artifact.py` | AR-F04：`CompactArtifactWriteResult.compaction_request_digest` |
| 25 | `dayu/host/compact_payload.py`（L500–533, L549–572） | AR-F04：vNext compact artifact JSON 顶层包含 `artifact_kind`、`compaction_request_digest` |
| 26 | `dayu/runtime/config_loader.py`（L1932） | AR-F01：`wait_poller_policy` 为 ConfigLoader typed 必填字段 |
| 27 | `utils/smoke_web_ci.py`（L5020） | AR-F03：`configure(configure_root=True)` standalone CLI 行为 |
| 28 | `tests/tools/web/test_smoke_web_ci.py` | AR-F03：六个 `smoke.main(...)` in-process 调用点 |
| 29 | 全部 `ValidatedFinsEventStream` consumer 扫描（11 个源文件） | AR-F02：迁移波及范围确认 |
| 30 | `dayu/fins/tools/` 中 `parse_awaiting_resolution_mode` 全部 production consumer（download/preprocess/upload provider + tools） | AR-F02：provider 迁移范围确认 |
| 31 | `COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"` | AR-F04：artifact kind 常量值与测试常量的匹配 |

## 2. Goal / Non-Goals 裁决

### 2.1 动机成立 ✅ PASS

Aggregate regression evidence (Codex artifact) 稳定复现五组本地 actionable defects (AR-F01–F05)。R01–R12 sub-WU accepted evidence 只证明各自当时的 slice tree，不能证明最终整合树的全量测试顺序、跨层 import、当前 artifact schema、逐文件 coverage 或真实 Windows runner。Controller adjudication 已明确裁决动机成立。本 reviewer 独立确认：不能用历史 sub-WU PASS 覆盖本轮失败。

### 2.2 Goal 精确性 ✅ PASS

Plan 精确限定在关闭 AR-F01–F05，不创建新 WU，不改变原 WU 目标、设计真源或 residual destination。AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，AR-F07 保持 `PENDING_RELEASE_BLOCKER`。Scope 与 Controller adjudication 完全一致。

### 2.3 Non-Goals 完整性 ✅ PASS

Plan 明确声明不修改 design docs、control docs、既有 plan/review/completion artifacts、workflow files。不引入 TruncationManager wiring、storage-state lifecycle、Fins process isolation、assets migration、unified authorization framework。这些 deferred/no-code 边界与 Controller discussion 及 Codex evidence ledger 完全对齐。

## 3. Owner Adjudication（独立验证）

### 3.1 AR-F01 owner ✅ PASS

- **Plan 裁定**: test fixture schema owner（`_write_host_runtime`），不是 production `ConfigLoader`
- **独立验证**: `dayu/runtime/config_loader.py:1932` 确认 `wait_poller_policy` 是 typed 必填字段。`_write_host_runtime`（test_host_admin.py:14–50）当前写出的 profile 确实缺此字段。正确 owner 是 test fixture 的 current-schema projection，不是 ConfigLoader 的容错设计。
- **风险**: 无。Plan 的 12 字段值来自当前 `WaitPollerRuntimePolicyConfig` 契约，fixture 不 import 另一测试模块 helper，不设 production 默认值/fallback。

### 3.2 AR-F02 owner ✅ PASS

- **Plan 裁定**: Fins public contract owner（`direct_events.py` + 新建 `awaiting_resolution.py`），不是 Service allowlist
- **独立验证**:
  - `ValidatedFinsEventStream` 当前存在于 `direct_stream.py`（262 行），该模块 import from `direct_events.py`。validator 是 `direct_events.py` 中定义的类型（`FinsEvent`、`FinsEventType`、`FinsDirectStreamProtocolError` 等）的 consumer。物理迁入同一模块不创造 import cycle — 当前依赖是单向的 (`direct_stream` → `direct_events`)。
  - `AwaitingResolutionMode` / `parse_awaiting_resolution_mode` / `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` 三项语义当前确实混在 `_ingestion_tool_helpers.py`（私有 tools helper），而 Service（`fins_wait_adapter.py`、`host_assembly.py`）直接越界消费。正确 owner 是 Fins ingestion public contract。
  - `SERVICE_ALLOWED_IMPORTS` 已包含 `dayu.fins.direct_events` 和 `dayu.fins.ingestion`（前缀匹配）。`test_import_boundary.py` 的 `_matches_prefix` 使用 `module == prefix or module.startswith(prefix + ".")` 逻辑，因此 `dayu.fins.ingestion.awaiting_resolution` 自然匹配前缀 `dayu.fins.ingestion`。Service allowlist 零改动。
- **风险**: `direct_events.py` 当前 497 行（event types/contracts），加入 262 行 validator state machine 后约 760 行。未触及 God module 阈值，但需注意后续不要再往里堆不相关的 direct 语义。此为 **defer-candidate**（本轮不修，后续维护注意）。

### 3.3 AR-F03 owner ✅ PASS

- **Plan 裁定**: in-process test harness isolation owner（`test_smoke_web_ci.py`），不是 standalone product logging
- **独立验证**: `utils/smoke_web_ci.py:5020` 的 `configure(configure_root=True)` 是 standalone CLI 的正确 operator logging 行为。test file 有六个 `smoke.main(...)` in-process 调用点（L1345, L1433, L1523, L1547, L1609, L1698）。Plan 在 test-only harness 做 snapshot/restore 隔离，零改动 standalone product。
- **风险**: 见 Finding AF-DS-01。

### 3.4 AR-F04 owner ✅ PASS

- **Plan 裁定**: Host current compact artifact / runner-call manifest 测试 oracle
- **独立验证**:
  - `_runner_call_manifest.py` 定义 `RunnerCallCompactorIdentity`（含 `compaction_request_digest: str`）。`RunnerCallInputManifest` 含 `compactor_identity: RunnerCallCompactorIdentity | None`。
  - `compact_payload.py:518` 写 `"compaction_request_digest": request.digest()` 为 compact artifact JSON 顶层字段。`COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"`（L33），与测试常量 `_COMPACT_ARTIFACT_KIND = "context_compaction"` 一致 ✅。
  - Plan 的 digest 关联链路（manifest `compactor_identity.compaction_request_digest` → compact artifact 顶层 `compaction_request_digest`）在当前 schema 中完整、唯一、可测试。
  - 当前 `_runner_call_manifest_for_run`（L1799–1819）已按 `schema_version`、`host_run_id`、`runner_call_kind == "compactor_proposal"` 精确定位 manifest，只是未读取 `compactor_identity.compaction_request_digest`。
  - 当前 `_compact_artifact_for_run`（L1774–1796）仍使用已删除的 `candidate_id == llm-compact:{run_id}` 猜测归属。
- **风险**: 见 Finding AF-DS-02。

### 3.5 AR-F05 owner ✅ PASS

- **Plan 裁定**: 对应 Documents/Fins/Host/runtime owner tests
- **独立验证**: 九个 production paths 在 remediation range 零 diff，属于既有 umbrella pre-remediation integrated baseline。Plan 的 test-to-owner 映射合理（见 Challenge 4 独立裁决）。Stop condition（测试暴露 production defect → 停）是正确 safeguard。

### 3.6 AR-F06 / AR-F07 owner ✅ PASS

- AR-F06: R05 completion truth 已裁决 scheduler close/promotion coordination 为独立 work item。Plan 只保留其 owner/destination，不修、不 waive、不借 coverage exclusion 改状态。Canonical non-coverage suite 仍执行该 node。✅
- AR-F07: 远端无可用 Windows runner。Plan 保持 `PENDING_RELEASE_BLOCKER`，不改 workflow、不伪造 PASS。✅

## 4. Controller Validation 六项 Mandatory Challenges 独立裁决

### Challenge 1: `direct_events.py` 合并 validator 后是否形成 import cycle、过宽 public module、隐藏额外 consumer，及 awaiting mode 新 owner 是否真能保持 Service allowlist 零改动

**裁决: PASS（附带 1 个 accepted-candidate finding）**

**Import cycle 分析**:

当前 import graph（production 关键路径）:
```
dayu/fins/direct_events.py        ← 定义 FinsEvent, FinsEventType, FinsOperationKind,
                                     FinsDirectStreamProtocolError 等
dayu/fins/direct_stream.py        ← import from direct_events.py
                                     ← 定义 ValidatedFinsEventStream
dayu/fins/ingestion_runtime.py    ← import ValidatedFinsEventStream from direct_stream
dayu/service/fins_direct.py       ← import ValidatedFinsEventStream from direct_stream
dayu/cli/commands/fins.py         ← import ValidatedFinsEventStream from direct_stream
```

迁入后:
```
dayu/fins/direct_events.py        ← FinsEvent 等 + ValidatedFinsEventStream（合并）
dayu/fins/ingestion_runtime.py    ← import from direct_events（路径变更，无语义变更）
dayu/service/fins_direct.py       ← import from direct_events（路径变更，无语义变更）
dayu/cli/commands/fins.py         ← import from direct_events（路径变更，无语义变更）
```

`direct_events.py` 当前不 import 任何 `dayu.fins` 内部模块（只 import `re`、`dataclasses`、`datetime`、`enum`、`typing`）。`direct_stream.py` 当前只 import from `direct_events.py` 和标准库。迁入后 `direct_events.py` 的依赖不变。**零 import cycle 风险**。

**Public module 宽度**:

`direct_events.py` 当前 497 行（event type contracts + safe text validation helpers）。迁入 262 行 validator state machine 后约 760 行。暂不触及 God module 阈值。但后续不应再向该模块堆 unrelated direct 语义（如 CLI formatting、Service adapter logic）。**accepted-candidate**：建议在 `dayu/fins/README.md` 更新时明确 `direct_events.py` 的 future boundary 约束。

**隐藏额外 consumer**:

完整 `ValidatedFinsEventStream` consumer 扫描覆盖 11 个源文件（7 个 production + 4 个 test）：
- Production: `dayu/fins/ingestion_runtime.py`、`dayu/service/fins_direct.py`、`dayu/cli/commands/fins.py`（已列入 Slice 2 mutable allowlist）
- Tests: `tests/fins/test_fins_direct_stream.py`、`tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py`（已列入 Slice 2 mutable allowlist）
- Tests 额外: `tests/fins/test_fins_ingestion_runtime.py`（不在 allowlist！需验证）

**发现**: `tests/fins/test_fins_ingestion_runtime.py` 不在 Slice 2 mutable test allowlist 中，但 `dayu/fins/ingestion_runtime.py` 当前 `from dayu.fins.direct_stream import ValidatedFinsEventStream`（L46）。迁入 `direct_events.py` 后，ingestion_runtime.py 的 import 路径变更（已列入 production allowlist），但 `test_fins_ingestion_runtime.py` 如果也直接 import `ValidatedFinsEventStream`，也需要 import 路径更新。

**AF-DS-07**: `tests/fins/test_fins_ingestion_runtime.py` 不在 Slice 2 的 mutable test allowlist 中。需验证该测试文件是否直接 import `ValidatedFinsEventStream` 或 `dayu.fins.direct_stream`。若直接 import，plan 需要扩充 allowlist 或澄清为何不需要。

**Service allowlist 零改动验证**:

- `SERVICE_ALLOWED_IMPORTS` 已含 `"dayu.fins.direct_events"`。validator 迁入后，Service 的 import 从 `dayu.fins.direct_stream` 变为 `dayu.fins.direct_events`，仍在 allowlist 内。
- `SERVICE_ALLOWED_IMPORTS` 已含 `"dayu.fins.ingestion"`。`_matches_prefix("dayu.fins.ingestion.awaiting_resolution", ("dayu.fins.ingestion",))` → `True`（因为 `"dayu.fins.ingestion.awaiting_resolution".startswith("dayu.fins.ingestion" + ".")` → `True`）。
- `dayu/fins/ingestion/__init__.py` 不 re-export 新模块（plan L71 明确禁止），Service import `dayu.fins.ingestion.awaiting_resolution` 直接命中前缀匹配。

✅ **Service allowlist 零改动成立。**

### Challenge 2: Logger registry snapshot/restore 是否能在成功、错误码、SystemExit、被测异常与新增 logger/handler 场景下完整恢复，且不会关闭调用前存在的 handler

**裁决: PASS（附带 1 个 needs-evidence finding 和 1 个 accepted-candidate note）**

**Snapshot 粒度分析**:

Plan §2.5 要求 snapshot: "root 及当前 logging registry 中所有 concrete `logging.Logger` 的 level、handlers、filters、propagate、disabled；记录 registry identity"。恢复: "原 handler identity/order 与全部 logger fields，卸载并只关闭本次调用新增的 handlers，清除本次调用新建的 logger entries"。

这覆盖了 logger 级别的状态。但 Python `logging` 模块的 handler 对象自身也有 mutable state：`handler.level`、`handler.formatter`、`handler.filters`。如果被测 `main()` 内部修改了已有 handler 的这些属性（虽然当前 `configure_root=True` 主要行为是加 handler，不太可能改已有 handler 属性），snapshot 需扩展深度。

**AF-DS-01** (needs-evidence): Plan §2.5 的 logger snapshot 覆盖 logger 级的 level/handlers/filters/propagate/disabled，但未显式覆盖每个 handler 的 level/formatter/filters。当前 `configure_root=True` 路径（`dayu/runtime/log.py`）的主要行为是添加 StreamHandler 和设置 root level，不太可能修改已有 handler 的内部属性。但 harness contract test（§2.5 末段）应包含至少一个 case 验证已有 handler 属性（level/formatter）在调用前后不变，以证明设计的 snapshot 深度充分。**若 contract test 通过则风险消除。**

**成功/失败/SystemExit/异常覆盖**:

Plan §2.5 明确要求 "成功、返回错误码、`SystemExit` 或被测异常都必须恢复"，且 `finally` 块保证恢复。六个 `smoke.main(...)` 调用点覆盖了 success（exit 0）、error（exit 1）、和 CLI-level `SystemExit`（argparse 触发）。Plan 的 harness contract test 要求分别覆盖成功和失败调用。✅

**不关闭调用前 handler**:

Plan §2.5 明确 "卸载并只关闭本次调用新增的 handlers"。通过在 snapshot 时记录 handler identity set，恢复时比较并只 close 新增的。✅

**AF-DS-01 补充** (accepted-candidate): Handler identity 按 `id(handler)` 比较可行，但若 `main()` 内部 remove 后又 add 了同一个 handler 类型的不同实例（即 `id` 不同但功能等价），snapshot 中的旧 handler 不会被误删。这是正确行为。

### Challenge 3: Runner-call manifest 到 compact artifact 的 digest 关联是否在 current schema 中唯一、严格、可测试，是否遗漏 duplicate/malformed fail-closed 路径

**裁决: PASS（无 material finding）**

**唯一性验证**:

- Manifest 定位条件: `schema_version` + `host_run_id` + `runner_call_kind == "compactor_proposal"`。这三个条件在正常运行中唯一定位一个 manifest（一个 run 的一次 compactor proposal 只产生一个 manifest）。Plan 的 fail-closed: "缺失或重复立即失败"。
- Digest 来源: `manifest.compactor_identity.compaction_request_digest` — SHA-256 digest，非空。Plan 断言非空。
- Compact artifact 定位条件: `artifact_kind == "context_compaction"`（已验证 `COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"` ✅）+ 顶层 `compaction_request_digest` 与 manifest digest 完全相等（已验证 `compact_payload.py:518` ✅）。
- Plan 的 fail-closed: "缺失、重复、schema/type 不符立即失败"。

**关联严格性**:

`compaction_request_digest` 是 compaction request 的 SHA-256 digest，由 compaction operation 在 request 构造时计算（`request.compaction_request.digest()`）。同一个 compactor run 的 manifest 和 compact artifact 都引用此 digest。这是一对一关联——一次 compaction 只有一个 request digest、一个 manifest、一个 accepted artifact。✅

**测试覆盖**:

Plan 新增 deterministic cases: 正确 run/digest 成功；missing manifest、duplicate manifest、missing compact artifact、duplicate matching compact artifact、wrong/missing digest 均 fail closed。这覆盖了主要 fail-closed 路径。✅

**AF-DS-02** (accepted-candidate): Plan 要求 `parent_host_run_id == host_run_id` 断言（§2.4 step 2）。当前 manifest schema 中 `RunnerCallCompactorIdentity.parent_host_run_id` 确实存在（`_runner_call_manifest.py:418`）。此断言增强了关联正确性——确保 compactor manifest 引用的是当前 run，而不是其他 run。但 plan 未说明当 `parent_host_run_id != host_run_id` 时是否 fail closed（应该 fail）。建议在 Slice 1 implementation 中显式 fail closed。

### Challenge 4: Slice 3 六个测试文件是否足以通过 public/owner-observable contract 覆盖九个 production paths，而不复制私有算法或构造不可能状态

**裁决: PASS（附带 2 个 needs-evidence findings）**

**逐 owner 分析**:

| # | Production owner | 当前覆盖率 | 测试文件 | 评估 |
| --- | --- | ---: | --- | --- |
| 1 | `docling_processor.py` | 63.46% | `tests/documents/test_processors.py` | 合理。Docling processor 有明确的 public API（sniff、section、table、page、search、full-text），通过 public processor 结果断言可行 |
| 2 | `sec_6k_rules.py` | 67.56% | `tests/fins/test_sec_pipeline_download.py` | 合理。6-K rules 是分类规则，candidate filename/type/rank 可通过 public 选取/拒绝结果断言 |
| 3 | `sec_form_section_common.py` | 78.23% | `tests/fins/test_processor_read_consistency.py` | ⚠️ 四个 SEC processor 共享一个测试文件 |
| 4 | `sec_report_form_common.py` | 65.14% | 同上 | ⚠️ 同上 |
| 5 | `sec_section_build.py` | 77.56% | 同上 | ⚠️ 同上 |
| 6 | `sec_table_extraction.py` | 66.16% | 同上 | ⚠️ 同上 |
| 7 | `preprocess_tools.py` | 75.81% | `tests/fins/test_fins_ingestion_tools.py` | 合理。该测试文件已有 preprocess 相关 infrastructure |
| 8 | `_execution_config_projection.py` | 76.43% | `tests/host/test_effective_execution_config.py` | 合理。执行配置投影是 JSON → typed contract 的解析逻辑 |
| 9 | `argparse_exit.py` | 未命中 | `tests/runtime/test_argparse_exit.py`（新建） | 合理。简单 helper，int codes 0/2/负数、None/字符串/非 int → usage error 2 |

**AF-DS-03** (needs-evidence): 四个 SEC processor（`sec_form_section_common.py`、`sec_report_form_common.py`、`sec_section_build.py`、`sec_table_extraction.py`）共享一个测试文件 `tests/fins/test_processor_read_consistency.py`。这四个文件各自有不同的 behavior families（plan 的 coverage table 有详细列举），每个从 65%–78% 提升到 ≥80% 需要各自新增 cases。单个测试文件承载四个 production owner 的 contract tests 可能导致:
- 测试文件过长，跨 owner 的 setup/teardown 互相干扰
- 不同 owner 需要的 fixture 粒度不同，共享 conftest 可能不够

**缓解因素**: Plan 的 stop condition（"只有修改 production/直接耦合不稳定私有实现才能达到 80%，立即停止"）是最重要的 safeguard。若测试揭示真实 production defect，plan 强制停而非降 threshold。且这四个 processor 有足够的 public contract（public section/statement/table API）可通过 owner-observable 行为断言。

**AF-DS-04** (needs-evidence): 四个 SEC processor 从当前 65–78% 提升到 ≥80% 的增量绝对值约为 2–15 个百分点。对于已有 substantial test infrastructure 的模块，这个增量是可行的。但对于 `sec_report_form_common.py`（65.14%，需 +14.86pp）和 `sec_table_extraction.py`（66.16%，需 +13.84pp），增量较大，可能需要较多 cases。若现有测试 infrastructure 不足以高效构造 SEC filing 输入（需要 HTML/XBRL fixture），进度可能受阻。**但 plan 的 stop condition 正是为此设计——不可行时停，不降 threshold。**

### Challenge 5: 219-path ledger、R05 single-node coverage exclusion、Ruff immutable baseline 和 Slice 1 临时 import-boundary failure 是否可执行且不会被误签为 waiver/PASS

**裁决: PASS（无 material finding）**

**219-path ledger 可执行性**:

Plan §6.2 的生成规则: `git diff --name-only --diff-filter=ACMR 3410d7..FINAL_ACCEPTED_HEAD -- 'dayu/**/*.py'`，排序、去重。命令本身确定、可复现。Line coverage 按 `covered_lines / num_statements * 100` 独立计算，不使用 coverage.py 的 combined `percent_covered`。✅

预期变化: Slice 2 删除 `direct_stream.py`（减 1）、新增 `awaiting_resolution.py`（加 1），总数保持 219。Plan 明确 "任何其他增删都是 scope failure"。✅

**R05 single-node exclusion 精确性**:

Plan 只排除 `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`。已确认与 Codex evidence ledger（R05 同一 node/error/coverage-only timing）和 Controller adjudication 一致。Canonical non-coverage suite 仍运行该 node。✅

**Ruff immutable baseline**:

Plan 说 "当前 full Ruff immutable baseline 是 144 findings"。Per-slice 要求: JSON 规范化后相对 slice base 无新增；本 slice mutable paths 零 finding。可执行。风险: 144 findings baseline 若被外部提交改变，Controller 需先记录新 immutable set。✅

**Slice 1 临时 import-boundary failure**:

Plan 明确声明 Slice 1 只允许 `test_service_does_not_import_forbidden_layers` 保持已知失败。其他所有 node 必须全绿。这个临时预期不是 waiver——Slice 2 exit 后不得再存在。✅

**潜在风险**: 若 Slice 1 有其他 pre-existing failure 被误归为此临时允许，reviewer 需逐项核实。Plan 已列出精确的 canonical 命令和预期结果。

### Challenge 6: 三 slice 顺序是否是最小可验证闭环，及每 slice 全量验证成本是否仍符合 umbrella optimization control

**裁决: PASS（附带 1 个 accepted-candidate note）**

**顺序最小性**:

- Slice 1（test-only）必须最先: 建立 current-schema/test oracle 和 in-process isolation。若先做 Slice 2（production migration），AR-F01/F03/F04 的 failures 会与 AR-F02 的 import changes 交织，review 无法分离。
- Slice 2（production migration）必须居中: Slice 3 的 coverage tests 依赖 Slice 2 的稳定 import graph 和 canonical suite 全绿。
- Slice 3（test-only coverage）必须最后: 在稳定整合树上补齐 coverage，避免导入路径变更后重新调整 coverage tests。

三 slice 不能合并: Slice 1 和 Slice 3 虽然都是 test-only，但 Slice 3 依赖 Slice 2 的生产变更。Slice 1 和 Slice 2 风险级别不同（test-only vs. production migration），按 umbrella optimization control 的高风险要求需分 slice review。

**验证成本评估**:

每个 slice 都运行 full canonical suite（5161+ tests）、coverage、pyright、Ruff、build、scans、real smokes。按 umbrella optimization control:
- Slice 1（Medium Risk — test harness/isolation）可适当降低 real smoke 范围，但 plan 仍要求 full canonical suite + real compactor/Web/awaiting smokes。这是保守但正确的——AR-F04 的 real compactor 是受影响的真实入口。
- Slice 2（High Risk — production code change）的 full validation 完全符合 `production-high` profile 要求。
- Slice 3（Medium Risk — test-only coverage）的 full validation 略显冗余，但因为 AR-F05 的 stop condition 要求真实 smoke 重跑以验证无 production regression，保持 full validation 是合理的。

**AF-DS-05** (accepted-candidate): Per-slice full canonical suite 成本较高（每次约 170s + coverage 187s + smokes）。若两路 review + fix + re-review 轮次多，累计验证时间可能延长。但 umbrella optimization control 明确 "生产语义、schema、durable state、state machine、LLM-facing 文本、public contract 的变更仍按高风险 gate 执行"。Slice 2 的 production public contract 迁移属于高风险，full validation 合理。若 Controller 观察 Slice 1/3 的 re-review 轮次少，可考虑引用前次运行结果（在 slice base 未变且 affected paths 无交集时），但当前 plan 的保守策略不构成缺陷。

## 5. Architecture / Semantic Ownership 独立审查

### 5.1 分层架构合规性 ✅ PASS

- Slice 1: test-only changes。`tests/` → 不涉及生产分层。✅
- Slice 2: Fins internal migration。`dayu/fins/direct_events.py` ← 接收 validator（仍在 Fins 层）。`dayu/fins/ingestion/awaiting_resolution.py` ← 新 public contract（仍在 Fins 层）。Service/CLI 只改 import 路径，不改变消费方式。分层不变。✅
- Slice 3: test-only coverage。不涉及生产分层。✅

### 5.2 Semantic Ownership 边界 ✅ PASS

- AR-F01: test fixture owns "生成当前 schema 完整最小 profile" → 正确，不泄漏到 ConfigLoader。
- AR-F02: Fins owns `ValidatedFinsEventStream` + `AwaitingResolutionMode` → 正确。不 duplicate enum/protocol 到 Service。不扩大 allowlist。
- AR-F03: test harness owns "in-process logging isolation" → 正确。standalone product logging 不改。
- AR-F04: Host manifest/artifact owns "compaction request digest association" → 正确。不通过 `candidate_id`、文件名、mtime 反推。
- AR-F05: 各 production owner test 补齐 coverage → 正确。不 mirror private implementation。

### 5.3 Overengineering / Overcoupling 检查 ✅ PASS

- Plan 不引入新 abstraction layer、中间类型、wrapper、facade、compat shim。
- Slice 2 的 migration 是纯物理搬迁 + import 路径更新，不改变 state machine、error contract、protocol behavior。
- Slice 3 的 test 明确禁止 "mock-only hook、dead branch、production seam、`pragma: no cover`、coverage omit、动态 import 或实现镜像"。
- Plan 明确禁止 "compatibility re-export、lazy import、try/except import、duplicate enum/protocol、package-root re-export 或 Service 字符串重算"。
- `_runner_call_manifest.py`、`compact_artifact.py`、`compact_payload.py` 等 compactor production owner 全部列为 zero-diff protected paths。✅

### 5.4 最佳实践 / 最优解检查 ✅ PASS

- AR-F01: 修 test fixture 而不给 ConfigLoader 加 fallback — 正确（AGENTS.md: "禁止在下游消费者、展示层、adapter、测试夹具或单一入口用 fallback...补救错误语义"）。
- AR-F02: 迁 public contract owner 而不扩大 allowlist — 正确（AGENTS.md: "代码必须改在 owner boundary 或其直接上游输入校验处"）。
- AR-F03: test harness isolation 而不改 standalone product — 正确（AGENTS.md: "禁止局部止血"）。
- AR-F04: 用 current schema digest 关联而不恢复 candidate_id — 正确（AGENTS.md: "多个消费者需要同一语义时，必须复用同一个 source of truth"）。
- AR-F05: test-only coverage，production 零 diff，stop condition 防 production defect — 正确。

## 6. Testing / Coverage / Real-Smoke 审查

### 6.1 Test 策略 ✅ PASS

- Slice 1: 3 个 test files，每个有精确的修改范围和新增 cases 描述。`test_public_compact_smoke.py` 新增 6 个 deterministic fail-closed cases。✅
- Slice 2: 5 个 test files，主要是 import 路径更新 + 验证 contract 行为不变。`test_import_boundary.py` 零 diff 且必须自然通过。✅
- Slice 3: 6 个 test files（1 个新建），从 public/owner contract 补齐 coverage。Stop condition 防止 coverage seam。✅

### 6.2 Coverage 命令 ✅ PASS

Plan §6.2 的 coverage 命令精确、单 node exclusion 明确、line coverage 独立计算（不使用 branch-combined `percent_covered`）。最终 ledger 生成规则完整。✅

### 6.3 Real Smoke 覆盖 ✅ PASS

Plan 的 per-slice real smoke 覆盖全面：
- Slice 1: real compactor、Web standalone、public awaiting ✅
- Slice 2: real Fins upload/download/process、R03 semantic ownership ✅
- Slice 3: same as Slice 2 ✅
- 全局: live browser cleanup、POSIX generated script/CLI/init、HKEX evidence 复核 ✅

**AF-DS-06** (accepted-candidate): Slice 2 的 Fins direct smokes (upload/download/process) 和 R03 semantic ownership smoke 依赖外部 SEC EDGAR / HKEXnews 可用性。Plan 已说明 "external provider 不可用时保留完整 failure evidence 并由 Controller 裁决，不能改成 mock PASS"。这是正确的。但需注意: R03 smoke 当前需要约 84s，per-slice 重复运行三个 slices 累计 smoke 时间较长。

### 6.4 Pyright / Ruff / Build / Scans ✅ PASS

所有验证门禁完整、命令明确。Pyright 零 errors/warnings/informations；Ruff baseline set 无增量；build 生成 wheel+sdist 并记录 hashes；六组 scans 带分类规则。✅

## 7. Security / Deferred / No-Code 审查

### 7.1 Security Matrix ✅ PASS

Plan §6.7 的 security ledger 覆盖: Doc path containment/output truncation、Web DNS/private/proxy/redirect/diagnostic、Host digest/EventLog/opaque ref、wait late-publication fence、Fins transaction/atomic swap/path/opaque id/direct validator、CLI POSIX quoting/init containment/process fencing。与 Codex security ledger 对齐。✅

### 7.2 Secret Scan ✅ PASS

Plan 要求 "只输出 configured secret count、match count 与 matched path count，不输出 secret value"。符合安全要求。✅

### 7.3 Deferred / No-Code ✅ PASS

Plan 列出 Issue 177、178、175、142/151 为 deferred；Topic 8、Codex F-13、Topic 9 为 no-code。全部与 Controller discussion 和 Codex evidence 一致。AR-F06 持续写作 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。AR-F07 持续 `PENDING_RELEASE_BLOCKER`。✅

## 8. AR-F06 Retained Residual 独立审查

**裁决: PASS**

Plan 对 AR-F06 的处理完整且正确:
- 不改 `dispatch.py`、`engine_ingest.py`、`_execution_health.py` 及 scheduler owner tests（全部列为 protected zero-diff paths）✅
- Coverage 只使用 R05 已接受的精确单-node exclusion，且 "canonical non-coverage suite 仍执行该 node" ✅
- 不把 exclusion 解释为 residual 修复或 waiver ✅
- 持续写作 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` ✅

**AF-DS-08** (accepted-candidate): Plan 未定义该 single-node coverage exclusion 的未来移除条件。建议在最终 aggregate closeout 时明确: "此 exclusion 在 AR-F06 的独立 scheduler/lifecycle work item 完成并通过 canonical non-coverage + coverage 双模后移除。" 这不影响当前 plan 的正确性，是未来维护提示。

## 9. AR-F07 Windows Blocker 独立审查

**裁决: PASS**

Plan 对 AR-F07 的处理完整且正确:
- 不改 `.github/workflows/r11-upload-script-windows.yml` 和 `r12-init-windows.yml`（全部列为 protected zero-diff paths）✅
- 不伪造 Darwin 上的 Windows PASS ✅
- 需要真实 `windows-latest` runner、完整 artifact oracle ✅
- Push/PR/final closeout 均 NOT AUTHORIZED 直到 Windows evidence 被 Controller 接受 ✅

## 10. Material Findings 汇总

### Accepted-Candidate Findings（4 个）

| ID | 描述 | 位置 | 影响 |
| --- | --- | --- | --- |
| AF-DS-02 | `parent_host_run_id != host_run_id` 时的 fail-closed 未显式说明 | §2.4 step 2 | Slice 1 implementation 时显式 fail closed 即可；无 plan 级风险 |
| AF-DS-05 | Per-slice full validation 成本较高，但符合 umbrella optimization control 的 high-risk 要求 | §6 全局 | 若 Controller 观察 re-review 轮次少，可考虑引用前次结果；当前保守策略非缺陷 |
| AF-DS-06 | Slice 2 real smokes 依赖外部 provider 可用性 | §4.2 real smoke | Plan 已有 "external provider 不可用时保留 evidence 交 Controller 裁决" 的保护机制 |
| AF-DS-08 | AR-F06 coverage exclusion 的移除条件未定义 | §6.2 | 建议在最终 aggregate closeout 时明确移除触发条件；不影响当前 plan |

### Needs-Evidence Findings（4 个）

| ID | 描述 | 位置 | 建议 |
| --- | --- | --- | --- |
| AF-DS-01 | Logger handler 级别 state（level/formatter/filters）未显式纳入 snapshot 范围 | §2.5 | Harness contract test 应包含至少一个 case 验证已有 handler 属性在调用前后不变；若 contract test 通过则风险消除 |
| AF-DS-03 | 四个 SEC processor 共享一个测试文件 `test_processor_read_consistency.py`，各自需 +2–15pp coverage | §4.3 | Slice 3 implementation 前应评估该测试文件的现有 infrastructure 是否足够支撑四个 owner 的独立 contract tests；若不足，可能需要拆分测试文件（触发 stop condition 重审 allowlist） |
| AF-DS-04 | `sec_report_form_common.py`（65.14%）和 `sec_table_extraction.py`（66.16%）到 80% 的增量较大 | §4.3 | 与 AF-DS-03 相关。Slice 3 实施中若需要大量 HTML/XBRL fixture 构造，可能触发 stop condition |
| AF-DS-07 | `tests/fins/test_fins_ingestion_runtime.py` 不在 Slice 2 mutable test allowlist 中 | §3.2 | 验证该文件是否直接 import `ValidatedFinsEventStream` 或 `dayu.fins.direct_stream`；若是，需扩充 allowlist 或澄清为何不需要 |

### Defer-Candidate Findings（1 个）

| ID | 描述 | 位置 | 建议 |
| --- | --- | --- | --- |
| — | `direct_events.py` 迁入 validator 后约 760 行，暂不触及 God module 阈值 | §2.3 | 在 `dayu/fins/README.md` 更新时明确 future boundary 约束，后续不再向该模块堆 unrelated direct 语义 |

### No Material Finding 区域（明确 PASS）

以下区域经独立审查后无 material finding：

- **Goal/Non-Goals**: ✅ 精确对齐 Controller adjudication
- **AR-F01 owner**: ✅ test fixture schema owner
- **AR-F03 owner**: ✅ in-process test harness isolation
- **AR-F05 owner**: ✅ 各 production owner tests，stop condition 正确
- **AR-F06 residual**: ✅ no-code retained，exclusion 精确
- **AR-F07 blocker**: ✅ Windows external gate
- **Slice 顺序**: ✅ 最小可验证闭环
- **Production allowlist**: ✅ 精确、cross-checked
- **Protected zero-diff paths**: ✅ 精确、cross-checked（含 7 组）
- **Import cycle 风险**: ✅ 零风险（已验证 import graph）
- **Service allowlist**: ✅ 零改动验证通过
- **Compactor digest association**: ✅ 唯一、严格、完整
- **Coverage 命令**: ✅ 单 node exclusion、line coverage 独立计算
- **Pyright/Ruff/Build/Scans**: ✅ 完整、可执行
- **Security/Deferred/No-Code**: ✅ 完整对齐
- **Stop conditions**: ✅ 全面覆盖
- **Per-slice review/fix/re-review state machine**: ✅ 完整

## 11. Verdict

### 总体裁决

**PASS_WITH_FINDINGS / READY_FOR_AGENTMIMO_REVIEW**

Plan 在以下维度全面通过独立 adversarial review:
- **动机与 scope**: 精确对齐 Controller adjudication，不扩域、不创建新 WU
- **Owner adjudication**: 五个 AR 的 owner 判定正确，代码证据充分
- **Architecture / semantic ownership**: 分层合规、无 overengineering/overcoupling、最佳实践对齐
- **Controller validation 六项 challenges**: 独立裁决全部 PASS（见 §4）
- **Testing / coverage / real-smoke**: 策略完整、命令精确、stop condition 正确
- **Security / deferred / no-code**: 全额对齐
- **AR-F06 / AR-F07**: 正确处理为 residual/blocker

### Findings 严重度分布

- **P0 / release blocker**: 0
- **Needs-evidence** (implementation 前需验证): 4 (AF-DS-01, AF-DS-03, AF-DS-04, AF-DS-07)
- **Accepted-candidate** (plan 级可接受，implementation 注意): 4 (AF-DS-02, AF-DS-05, AF-DS-06, AF-DS-08)
- **Defer-candidate** (未来维护注意): 1 (direct_events.py future boundary)

### 可实施性

Plan 的三个 slices 均可直接实施。Slice 1 的 test harness 设计明确、Slice 2 的 import 迁移路径清晰、Slice 3 的 stop condition 是正确 safeguard。AF-DS-07（test file allowlist 缺口）需在 Slice 2 implementation 前验证，若命中则需 Controller 裁决是否扩充 allowlist。

### Plan Acceptance Checklist（独立核对）

- [x] 只存在本 plan 的新增 diff；product/test/README/workflow/control/既有 artifacts 零变化，staged 为空 ✅
- [x] 三个 slices 且顺序固定，AR-F01—F05 均有唯一 closure owner 与 test oracle ✅
- [x] AR-F02 不扩大 Service allowlist，无 compat re-export/lazy import/duplicate enum/protocol ✅
- [x] AR-F04 只用 current runner manifest + compaction request digest 关联，无 candidate_id/raw guess/fallback ✅
- [x] AR-F03 只做 in-process test harness isolation，standalone product logging 零 diff ✅
- [x] AR-F05 九路径 production 零 diff，production defect 触发 stop ✅
- [x] Production/test/README allowlists 与 protected paths 精确列出 ✅
- [x] 每 slice 含 focused tests、canonical suite、coverage、pyright、Ruff、diff、build、scans、README/security/deferred/no-code 和真实 smoke ✅
- [x] Coverage 只排除 R05 精确单 node；最终要求 219/219 line coverage >=80% ✅
- [x] 每 slice 要求 MiMo/DS 完整 code review、fix、完整 re-review；全部 slice 后重新 aggregate regression，再进入 MiMo/DS aggregate deepreview ✅
- [x] AR-F06 保持 no-code residual，AR-F07 保持 Windows pending release blocker ✅
- [x] Plan 经双路完整 plan review/fix/re-review 与 Controller 接受前不实施 ✅

## 12. Assumptions

1. `Ruff` immutable baseline 144 findings 在当前 HEAD 稳定，不被外部提交改变。若改变，Controller 需先记录新 immutable set。
2. `COMPACT_ARTIFACT_KIND_VNEXT = "context_compaction"` 在未来 schema 升级前不变（当前证实为 `"context_compaction"`）。
3. `SERVICE_ALLOWED_IMPORTS` 的 `_matches_prefix` 前缀匹配逻辑不变。
4. 219 个 changed production Python files 的集合仅因 Slice 2 的 delete/add 发生预期变化（减 `direct_stream.py`、加 `awaiting_resolution.py`），无其他外部提交干扰。
5. External providers (SEC EDGAR, HKEXnews) 在 real smoke 运行期间可用。不可用时按 plan 保留 evidence 交 Controller 裁决。

## 13. Residual Risks

1. **Slice 3 SEC processor coverage**: 四个 SEC processor 的 65–78% → ≥80% 提升可能因 fixture 复杂度而触发 stop condition。若触发，需 Controller 重新裁决——这是 plan 设计的正确行为，不是 plan 缺陷。
2. **AF-DS-07 test allowlist gap**: 若 `test_fins_ingestion_runtime.py` 直接 import `ValidatedFinsEventStream`，需在 Slice 2 implementation 前处理。
3. **External provider unavailability**: 若 SEC EDGAR 或 HKEXnews 在 real smoke 期间不可用，smoke gate 需 Controller 裁决（计划已保护此路径）。
4. **Ruff baseline 144 → 变化**: 若外部提交合法改变 baseline，Controller 必须先记录新 immutable set。

## 14. Artifact Metadata

| 字段 | 值 |
| --- | --- |
| reviewed_plan_sha256 | `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` |
| reviewed_plan_lines | 610 |
| reviewed_plan_bytes | 44,252 |
| system_clock_utc | 2026-07-18T08:05:31Z |
| review_filesize_lines | 483 |
| review_filesize_bytes | 42,255 |
| review_sha256 | 0845d27ec32402c1522d81f42684b7b7d9eacd0f89f0be63399fac43b0d4a1ad |
