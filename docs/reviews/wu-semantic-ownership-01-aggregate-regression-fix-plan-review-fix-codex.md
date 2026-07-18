# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix plan review accepted-finding 修复记录

## 1. Gate 身份与证据锁

- 执行时间：`2026-07-18 16:44:08 +0800`（本机系统时钟）。
- 工作单元：`WU-SEMANTIC-OWNERSHIP-01`；本轮是同一 umbrella remediation continuation 的 plan-only accepted-finding fix，不创建新 WU。
- 完整读取的授权真源：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md`，81 行 / 7,457 bytes / SHA-256 `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06`。
- Entry plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，610 行 / 44,252 bytes / SHA-256 `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e`；修改前已精确匹配 Controller 指定 hash。
- Final plan：同一路径，640 行 / 50,784 bytes / SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`。
- Gate 结论：`PLAN_FIX_COMPLETE / IMPLEMENTATION_NOT_AUTHORIZED / READY_FOR_CONTROLLER_VALIDATION_AND_FULL_REREVIEW`。

## 2. Accepted finding 逐项关闭

### AR-PLAN-PF01 — CLI direct-stream test consumer 遗漏

| Controller 要求 | Final plan 闭环 | 结果 |
| --- | --- | --- |
| Slice 2 mutable test allowlist 加入 `tests/cli/test_fins_commands.py` | §3.2 在 Slice 2 精确加入 `M tests/cli/test_fins_commands.py` | CLOSED |
| Focused test 覆盖 CLI consumer | §4.2 focused pytest 命令显式包含该文件 | CLOSED |
| Consumer scan 覆盖 CLI consumer | §4.2 增加新 public owner consumer scan，结果契约要求精确命中三个 production 与三个 test consumers，并显式包含 CLI test | CLOSED |
| Direct-stream stale import scan 覆盖 `dayu tests utils` 且旧 import 零命中 | §4.2、§6.6、§7 与 Slice 2 exit 均固定三个扫描根，要求 `dayu.fins.direct_stream` 零命中并记录 zero-match exit 1 | CLOSED |
| 不保留 compatibility module/re-export/fallback | §2.3、§4.2、checklist 与 stop conditions 保持物理 owner migration，CLI test 只改 import | CLOSED |

### AR-PLAN-PF02 — public-awaiting validation utility 遗漏

| Controller 要求 | Final plan 闭环 | 结果 |
| --- | --- | --- |
| 新增独立 Slice 2 mutable validation-utility allowlist，仅含 public-awaiting utility | §3.3 单独列出 `M utils/smoke_host_public_awaiting_entrypoint.py`；§3.5 要求其它 `utils/**` 全部零 diff | CLOSED |
| Utility 只迁移 `AwaitingResolutionMode` import | §3.3、§4.2、§6.4、stop conditions 与 checklist 均限定从旧 private helper 迁到 `dayu.fins.ingestion.awaiting_resolution`；九个业务/类型用法（源行 455、456、457、786、807、823、839、852、919）与其它行零 diff | CLOSED |
| Slice 2 owner-migration focused gate 运行 public-awaiting smoke | §4.2 real-smoke 命令与 Slice exit 新增 Slice 2 fresh smoke，明确禁止沿用 Slice 1 迁移前结果 | CLOSED |
| Awaiting definition/import scans 覆盖 `dayu tests utils` | §4.2 分开新 owner 唯一定义、新 owner 合法 consumer、旧 private definition 与旧 private import scans；§6.6/§7 要求 final aggregate fresh 重跑 | CLOSED |
| 旧 private import 零命中，不复制 enum/parser/config field，不增兼容路径 | §3.3、§4.2 scan outcome、Slice exit、stop conditions 和 checklist 形成同一精确契约 | CLOSED |

## 3. 未实施建议与 rejected/no-fix 保护

以下候选被 Controller 拒绝、已由原计划覆盖，或不是本轮 plan defect；本次没有把它们改写为 implementation 或扩域授权：

- Logging handler/registry：不扩充 production logging 路径，不改全局 `conftest`；`loggerDict` 细节仍是 Slice 1 implementation/review 验证点。
- Compactor parent id：不重复加条款；§2.4 已明确 `parent_host_run_id == host_run_id` 且不等时 fail closed。
- SEC/Docling coverage feasibility：不预扩 production/test allowlist，不降低单文件 80% threshold，保持 production-defect/private-mirroring stop condition。
- `direct_events.py` module width：不新增抽象、拆分或未来型 generalization。
- Per-slice validation 成本：不复用变更前/前一 slice 结果，保持三个固定 slices 与 fresh gates。
- External provider availability：不增 mock PASS 或 fallback；仍保存真实 failure evidence 交 Controller 裁决。
- AR-F06 exclusion 移除条件：不替未来 Host scheduler/lifecycle WU 设计；状态保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- Ruff baseline：不把易漂移的 144-finding 完整列表复制进计划；保持每 slice 规范化 exact-set delta。
- Provider import 措辞/新 awaiting owner coverage：不重复语义；三个 providers 迁移与新 owner `>=80%` 要求保持不变。
- DS 关于 `tests/fins/test_fins_ingestion_runtime.py` 的 direct import 候选：不加入 mutable allowlist；当前 direct scan 证明该文件不 import `direct_stream`，其既有 focused runtime 覆盖保持。
- 初始 routing-invalid `...plan-review-mimo.md`：不作为独立 review evidence，不从其单独引入任何 fix。

没有 deferred code change；security/deferred/no-code ledger 与原计划保持不变。`AR-F07` 继续为 `PENDING_RELEASE_BLOCKER`，不修 workflow，不用 Darwin/mock 代签 Windows evidence。三个 slices、final `219/219 >=80%`、AR-F06/07、security/deferred/no-code 与所有其它 rejected/no-fix dispositions 均未改变。

## 4. Scope 与 hash checks

### 4.1 本轮允许变化

| Path | Entry | Final | 判定 |
| --- | --- | --- | --- |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | `??` / SHA-256 `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` | `??` / SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | 唯一修改路径 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-codex.md` | absent | `??` | 唯一新增路径 |

### 4.2 Pre-existing protected status/hash

| Status | SHA-256（entry = final） | Path |
| --- | --- | --- |
| ` M` | `93dd662e755b0f7bbfc8ad82045bc54ed61b94d7bf3df22f14c385b242e56100` | `docs/host/issues-implementation-control.md` |
| `??` | `eb6528c2c1e59d4791a62b5cbb5f90fe84d517db368cd2cae4e51da253cacb11` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` |
| `??` | `73dfecd1aed86ca59c44d6b40c012add309b261539b8f25d129a728ae2942539` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` |
| `??` | `bddc028b58eda529a295e70fa6652613265c55b32af511fb7e446db16037a4d4` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md` |
| `??` | `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` |
| `??` | `94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md` |
| `??` | `2cab2ad9d1348a9f934f86857e3442895a3442149f343d29a4dc2d34aeaedb36` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md` |
| `??` | `2cb0496819ac6709d3d53d85fb27f468b3ce790a0628f9b29d8645713de1cf20` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md` |
| `??` | `03c41be0313394b2c8cf3e8ab2309a09665668545d4b7e7a1682ffa201a498ea` | `docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md` |

### 4.3 Validation ledger

- Plan 与新 artifact 独立 whitespace check：`PASS`。
- `git diff --check`：`PASS`。
- `git diff --cached --name-status`：`PASS`，输出为空。
- Exact path/status/hash protection：`PASS`；扣除上表 pre-existing protected 集合后，仅有 plan entry hash 变更与本 artifact 新建，所有 protected hash 均不变。
- Implementation tests / pyright / Ruff / build / product smokes：`NOT RUN BY PLAN-ONLY CONSTRAINT`。
- Stage / commit / push / PR / implementation / subagent / deepreview：`NOT PERFORMED`。

## 5. Code-generation-ready 自审

- Motivation：PF01/PF02 均由当前 source/import graph 直接证据支持，且原 exact allowlist 确实会阻止 implementation agent 修复必然失效的 consumers；严重性评估成立。
- Semantic owner：Direct terminal contract 唯一 owner 仍是 `dayu.fins.direct_events`；awaiting closed contract 唯一 owner 仍是 `dayu.fins.ingestion.awaiting_resolution`。新增的 test/utility 只消费 public contract，不产生、重算或兼容语义。
- Actionability：Slice 2 的 path/status、唯一允许改动、focused tests、owner/consumer/stale scans、public-awaiting smoke、exit criteria、final aggregate 重跑与 stop conditions 均已自足，implementation agent 不需扩域或二次设计。
- Scope stability：仍为三个固定 slices；219-file set、AR-F06/07、security/deferred/no-code 与 rejected/no-fix dispositions 不变。
- 结论：对 `AR-PLAN-PF01..02` 的 plan-only fix 已精确关闭，修订计划达到 `code-generation-ready`；但在 Controller 验证、AgentMiMo/AgentDS 对完整修订版双路 re-review 与 Controller 明确接受前，implementation 仍未授权。
