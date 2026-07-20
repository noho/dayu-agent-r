# WU-SEMANTIC-OWNERSHIP-01 / Umbrella aggregate regression Controller 裁决

## Gate 与输入

- Active work unit：`WU-SEMANTIC-OWNERSHIP-01`；这是既有 umbrella 的 aggregate regression gate，不是新 WU。
- Aggregate range：`b1a0631f397967e7530b676a90ef7467d83a1817^..ed9bfa9fe071aba0227361c69a938010ce3abe09`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md`，668 行 / 43,672 字节 / SHA-256 `eb6528c2c1e59d4791a62b5cbb5f90fe84d517db368cd2cae4e51da253cacb11`。
- Controller 已完整读取 artifact，并独立复现两个 Service nodes 为 `2 failed`，复现完整 Web smoke test file 后两个 logging nodes 为 `46 passed, 2 failed`，核对 R05 retained scheduler residual 真源、R03 compact schema、219-file coverage ledger、Windows remote workflow/run 查询和 deferred/no-code边界。

## 第一性原理结论

Aggregate regression 的动机成立：sub-WU accepted evidence 不能替代最终整合树的全量测试、真实入口、跨 owner import、逐文件 coverage 和远端 Windows 证据。当前不能进入 aggregate deepreview；先修复五组本地 actionable findings。已明确 deferred/retained owner 的 scheduler residual不得借 aggregate gate 擅自扩域实现，Windows success也不得由 Darwin skip 或本地 workflow code 代签。

## Finding 裁决

### AR-F01 — ACCEPTED

`tests/service/test_host_admin.py` 的 test-owned `host_runtime` fixture 缺少 R04 已成为当前 schema 必填项的 `wait_poller_policy`，导致本应验证“admin 不加载 models/scenes/tools/secrets”的测试在 ConfigLoader schema gate提前失败。

- owner：test fixture 的 current-schema profile projection；生产 ConfigLoader contract不回退、不设 optional fallback。
- required fix：fixture从当前 schema真源生成完整最小 profile并继续断言 admin isolation；不得在生产 parser增加兼容分支。

### AR-F02 — ACCEPTED

Service import boundary测试稳定报告三处越界：`dayu.service.fins_direct -> dayu.fins.direct_stream`，以及 `fins_wait_adapter` / `host_assembly -> dayu.fins.tools._ingestion_tool_helpers`。

- owner：Fins 对 Service 暴露的 public direct-stream / awaiting-resolution contract；Service只消费 public Fins contract，不读取 Fins internal implementation module。
- required fix：把真正需要跨边界的 type/enum放到其唯一 public Fins owner并迁移消费者；不得扩大 test allowlist、不得 compatibility re-export、lazy import、字符串重算或 Service duplicate enum/protocol。

### AR-F03 — ACCEPTED WITH BOUNDED TEST-HARNESS OWNER

`utils/smoke_web_ci.py` 的 standalone CLI `configure_root=True` 行早于 aggregate 起点，但当前范围显著修改该 utility及其 in-process test file。Controller 运行完整 `tests/tools/web/test_smoke_web_ci.py` 后两个 logging nodes稳定为 `46 passed, 2 failed`，证明 test harness未恢复进程全局 logging state。

- owner：in-process Web smoke test harness isolation；standalone utility的 operator logging行为保持。
- required fix：测试调用边界可靠 snapshot/restore其改变的 root/runtime logger state；不得改变全局 runtime logging产品默认、不得让下游 tests清理前序污染、不得以 test order规避。

### AR-F04 — ACCEPTED

真实 compactor两轮 Host Run均成功并发布 current vNext `context_compaction` artifact，但 `tests/host/test_public_compact_smoke.py` 的 helper仍以已删除的 `candidate_id == llm-compact:{run_id}`猜测归属。

- owner：Host current compact artifact / runner-call manifest测试 oracle。
- required fix：从当前 owner-published run/artifact关联事实定位并断言 artifact，不恢复 `candidate_id`、不做 raw-field guess/fallback/loose scan；真实 smoke必须重新全绿。

### AR-F05 — ACCEPTED AS TEST-COVERAGE CLOSURE

用户指定 range的219个现存 changed production Python中210个达到80%，8个低于80%，1个未命中。九个路径虽然不在 R01—R12 remediation diff中，但属于本 umbrella原 implemented range，且没有可信 accepted逐文件证据可补签。

- owner：对应 Documents/Fins/Host/runtime owner tests。
- required fix：为真实 owner contract补齐测试，使每个路径 fresh line coverage `>=80%`；默认只允许 tests变更。若测试暴露 production defect，立即回 Controller stop condition，不得为涨覆盖率添加 production shim、dead branch、mock-only hook或 `pragma: no cover`。
- exact paths：`dayu/documents/processors/docling_processor.py`、`dayu/fins/pipelines/sec_6k_rules.py`、`dayu/fins/processors/sec_form_section_common.py`、`dayu/fins/processors/sec_report_form_common.py`、`dayu/fins/processors/sec_section_build.py`、`dayu/fins/processors/sec_table_extraction.py`、`dayu/fins/tools/preprocess_tools.py`、`dayu/host/_execution_config_projection.py`、`dayu/runtime/argparse_exit.py`。

### AR-F06 — REJECTED AS CURRENT FIX / RETAINED RESIDUAL

R05 completion truth明确记录 scheduler close / terminal promotion coordination为确定性真实 bug，状态 `RETAINED / UNFIXED / UNWAIVED`，owner是 Host scheduler/lifecycle coordination，destination是后续独立显式 work item，并明确禁止在 R05/其它 owner gate擅自实现。Aggregate coverage再次复现相同六元组，不改变其已裁决 destination。

- current action：不改 `dispatch.py`、`engine_ingest.py`、health gate或 scheduler owner tests。
- validation：canonical non-coverage full suite在 F01—F03修复后必须全绿；coverage measurement采用 R05已接受的精确单-node exclusion，只用于得到219个文件的可靠 coverage，不把 exclusion解释为 residual修复或 waiver。
- final closeout：必须继续披露该 retained residual及 owner/destination。

### AR-F07 — ACCEPTED EXTERNAL RELEASE EVIDENCE BLOCKER

GitHub repo当前 Actions workflows总数 `0`、runs总数 `0`，workflow path查询404；本地无 origin remote，且用户未授权 push。真实 cmd.exe / Windows init evidence不存在。

- current action：保持 `PENDING_RELEASE_BLOCKER`；不得修改产品来伪造 evidence，不得未经授权 push。
- release oracle：使用包含 R11/R12 workflow commits的远端分支，在真实 `windows-latest` 按 artifact中列出的 node/artifact/name-safe oracles成功执行。

### Notes

- AR-N01：本地 `.venv` 补装 PyPA build后 wheel/sdist成功；这是已解决的验证环境前置，不添加项目 runtime/dev依赖。
- AR-N02：committed历史 review artifact whitespace是 note；当前 `git diff --check`通过，不重写历史 artifact。

## 本地 fix ledger

- accepted actionable groups：`5`（AR-F01—F05）。
- rejected as current fix / retained residual：`1`（AR-F06）。
- external release evidence blocker：`1`（AR-F07）。
- deferred/no-code leakage：`0`。
- design-truth contradiction：`0`；scheduler已有明确 owner/destination，不由当前 gate重裁产品语义。

## 下一 gate 与 plan 约束

下一 gate是 AgentCodex plan-only：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`。计划不得超过三个 implementation slices，并至少固定：

1. current-schema/test-oracle closure：AR-F01、AR-F03、AR-F04；
2. public Fins contract / Service boundary closure：AR-F02；
3. 九路径 owner-test coverage closure：AR-F05。

计划必须列出精确 production/test allowlist、AR-F02唯一语义 owner迁移、AR-F04 current artifact关联真源、AR-F03 logger恢复状态、逐文件 coverage命令、canonical full suite、R05 scheduler exact exclusion、真实 compactor/Web/CLI/Fins smokes、full pyright、Ruff、build、scans、README/security/deferred/no-code/Windows gates和stop conditions。Plan经 AgentMiMo / AgentDS双路 review、AgentCodex fix与双路 re-review接受后才能 implementation。

## Gate 决定

**BLOCKED_FOR_ACCEPTED_LOCAL_FINDING_FIX / READY_FOR_AGENTCODEX_PLAN_ONLY。**

aggregate deepreview、accepted deepreview commit、push、PR与umbrella closeout均未授权。
