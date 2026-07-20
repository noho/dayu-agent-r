# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix plan review Controller 裁决

## Gate 身份与证据锁

- Active work unit 仍是 `WU-SEMANTIC-OWNERSHIP-01`；这是同一 umbrella remediation continuation 的 aggregate regression accepted-finding fix plan gate，不是新 WU。
- Reviewed plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，610 行 / 44,252 bytes / SHA-256 `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e`。
- AgentMiMo 合规 clean-room replacement：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md`，360 行 / 25,177 bytes / SHA-256 `2cab2ad9d1348a9f934f86857e3442895a3442149f343d29a4dc2d34aeaedb36`。
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md`，483 行 / 42,247 bytes / SHA-256 `94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615`。
- 初始 `...plan-review-mimo.md` 因 reviewer 启动内部 Explore/subagents 而 routing-invalid；后续覆盖尝试又读取了该无效 artifact。它不作为本 gate 的独立 review evidence，最终由新路径 clean-room artifact 替代；其线索只有在 Controller/clean-room reviewer直接复现后才进入裁决。
- Controller 对所有 candidate 重新读取当前 source/import graph；reviewer verdict 不自动授权 plan acceptance或 implementation。

## 直接 consumer 证据

### Direct stream

当前 `dayu.fins.direct_stream.ValidatedFinsEventStream` 有且只有六个直接 import consumer：三个 production、三个 test。Plan production allowlist覆盖三个 production consumer，test allowlist只覆盖 `tests/fins/test_fins_direct_stream.py` 与 `tests/service/test_fins_direct.py`，遗漏：

```text
tests/cli/test_fins_commands.py:39
```

Slice 2 删除 `dayu/fins/direct_stream.py` 后，该文件会在 pytest collection 阶段产生 `ModuleNotFoundError`；exact allowlist又禁止实现 Agent自行修改。因此这是 plan non-actionability defect。

### Awaiting resolution mode

完整 `dayu tests utils` scan证明 production/test consumers除一项外均在 Slice 2 allowlist；遗漏项是：

```text
utils/smoke_host_public_awaiting_entrypoint.py:87
```

它从 private `_ingestion_tool_helpers` import `AwaitingResolutionMode` 并在八个业务/类型位置使用。Slice 2 删除该定义后，full pyright必然出现 unresolved import，final aggregate public-awaiting smoke也无法启动；当前 exact allowlist禁止修复该 validation utility。这是第二个 plan non-actionability defect。Plan 目前只在 Slice 1、即 owner迁移之前运行该 smoke，不能证明 Slice 2新 public owner接通。

## Finding disposition

### 接受：AR-PLAN-PF01 — CLI direct-stream test consumer遗漏

合并 MiMo clean-room `F-01/F-08` 与 DS `AF-DS-07` 的真实部分，接受为一个 HIGH plan fix：

- 把 `M tests/cli/test_fins_commands.py` 加入 Slice 2 mutable test allowlist。
- Slice 2 focused test命令必须包含该文件。
- direct-stream stale-import scan覆盖 `dayu tests utils`，要求旧模块 import零命中。
- 只改 import到 `dayu.fins.direct_events`；不保留 compatibility module/re-export/fallback。

DS 把风险指向 `tests/fins/test_fins_ingestion_runtime.py` 的部分被拒绝：direct scan证明该文件没有导入 `direct_stream`。DS 又称 CLI test已在 allowlist，与 plan文本直接矛盾；以当前 source和 plan exact allowlist为准。

### 接受：AR-PLAN-PF02 — public-awaiting validation utility遗漏

接受 MiMo clean-room `F-02/F-07/F-012` 为一个 HIGH plan fix：

- 新增 Slice 2精确 mutable validation-utility allowlist，只允许 `M utils/smoke_host_public_awaiting_entrypoint.py`。
- 该 utility只把 `AwaitingResolutionMode` import迁到 `dayu.fins.ingestion.awaiting_resolution`，不复制 enum/parser/config field、不添加兼容路径。
- Slice 2 owner-migration focused gate必须运行 public-awaiting smoke；aggregate gate继续运行，不能只沿用 Slice 1迁移前结果。
- awaiting-definition/import scans扩展到 `dayu tests utils`，区分唯一新 owner定义与合法 consumers，并要求旧 private import零命中。
- `utils/smoke_web_ci.py` 等其它 utils路径仍保持 zero-diff。

### 不接受为 plan fix

- **Logging handler/registry candidates**：当前 `dayu.runtime.log.configure` 只移除自有 marker handler、设置 logger level/propagate、添加新 handler和设置指定 third-party logger level；不修改调用前已有 handler的 level/formatter/filters。Plan 已明确 snapshot/restore logger registry、恢复原 handler identity/order、只关闭新 handler、清理新 logger entries，并要求 success/error/SystemExit/exception contract tests。`loggerDict` 的实现细节是 Slice 1 implementation/review验证点，不证明 plan不可实施；不扩充 production logging路径或全局 conftest。
- **Compactor parent id candidate**：Plan §2.4 已明确断言 `parent_host_run_id == host_run_id`，不等即 fail closed；无需重复措辞。
- **SEC/Docling coverage feasibility candidates**：Plan 已列 owner-observable behavior families、九 production owners零 diff、每文件80%和 production defect/private-mirroring stop condition。实现工作量不是 plan defect，不预先扩测试文件 allowlist、不降 threshold。
- **`direct_events.py` module width**：validator、typed events和terminal protocol error属于同一 Fins direct terminal contract；没有当前 God module或耦合证据。为未来宽度新增抽象/拆分与本 remediation 的去过度设计目标冲突。
- **Per-slice validation成本/复用旧结果**：用户明确要求每次修改后 fresh affected/full gates；不得以成本为由复用变更前结果。当前三 slice仍是最小 owner/依赖闭环。
- **External provider availability**：Plan 已要求保存真实 failure evidence交 Controller裁决且禁止 mock PASS；无需新 fallback。
- **AR-F06 exclusion移除条件**：该 residual已有未来独立 Host scheduler/lifecycle destination。本 plan只允许 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，不替未来 WU设计完成条件。
- **Ruff baseline候选**：Plan 已要求每 slice开始采集规范化完整144-finding set并做 exact delta；无需把易漂移的整套列表复制进 plan。
- **Provider import措辞/新 awaiting owner coverage**：Plan已明确迁移三个 providers，Slice 2又要求除 Slice 3九路径外所有 aggregate production paths（含新 owner）line coverage `>=80%`；无需重复。

## Final ledger

- Accepted plan-fix groups：`2`（`AR-PLAN-PF01..02`）。
- Rejected/no-fix/covered candidates：其余全部；没有 deferred code change。
- Local blocker：`0`；design contradiction：`0`；unclassified residual：`0`。
- `AR-F06` 状态不变：`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07` 状态不变：`PENDING_RELEASE_BLOCKER`。

## Verdict / next gate

**FAIL_PENDING_PLAN_FIX / READY_FOR_AGENTCODEX_PLAN_ONLY_FIX。**

只授权 AgentCodex 修改 reviewed plan并新增 plan-fix artifact，精确关闭 `AR-PLAN-PF01..02`。不得修改 product、tests、README、workflow、control、review artifacts或其它 utils；不得 implementation、stage、commit、push、PR、deepreview。修后必须由 Controller验证完整 plan，再由 AgentMiMo/AgentDS对完整修订版并发 re-review。
