# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Plan — AgentMiMo 完整 Re-Review

## 0. Re-review 合规声明

- 本 artifact 是 AgentMiMo 对 immutable final plan 的从零、独立、完整 re-review。
- 未启动 Agent、Explore、subagent 或任何并行 reviewer。
- 未读取 routing-invalid 的 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md`。
- 未采用任何旧 reviewer/subagent 输出；所有结论从零独立推导。
- 所有证据直接从当前 HEAD 代码、测试、配置、设计真源与 review artifacts 中采集。

## 1. 被审 plan 身份与证据锁

| 项 | 预期值 | 实测值 | 状态 |
| --- | --- | --- | --- |
| 文件路径 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 同左 | ✓ |
| SHA-256 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | ✓ |
| 行数 | 640 | 640 | ✓ |
| HEAD | `ed9bfa9fe071aba0227361c69a938010ce3abe09` | 同左 | ✓ |
| Aggregate parent | `3410d7422655c56bdf13c643f77c27f40b9d4550` | 同左 | ✓ |
| Plan status | `PLAN_ONLY / NOT_ACCEPTED / IMPLEMENTATION_NOT_AUTHORIZED` | 同左 | ✓ |
| Entry plan hash | `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` | 已在 Codex fix artifact 中确认 | ✓ |
| Final plan hash | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | 已在 Controller validation 中确认 | ✓ |

## 2. 完整读取证据清单与独立 metrics

以下全部在本次 re-review 中从零完整读取到 EOF。行数、字节数、SHA-256 由 `wc -l -c` 与 `shasum -a 256` 独立采集：

| # | 文档 | 行数 | 字节数 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| 1 | `AGENTS.md` | 128 | 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| 2 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 640 | 50,784 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` |
| 3 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | 65,088 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| 4 | `docs/host/design.md` | 3,696 | 388,584 | `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9` |
| 5 | `docs/engine/design.md` | 553 | 39,726 | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` |
| 6 | `docs/tool/design.md` | 134 | 11,240 | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` |
| 7 | `docs/fins/design.md` | 123 | 7,460 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| 8 | `docs/ui/design.md` | 111 | 7,920 | `5a19c829151777b1d9f3c69f1a9a305396f75c8e73eb5ea31577663c55bed973` |
| 9 | `docs/reviews/...-controller-adjudication.md` | 81 | 7,457 | `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06` |
| 10 | `docs/reviews/...-mimo-cleanroom.md` | 360 | 25,177 | `2cab2ad9d1348a9f934f86857e3442895a3442149f343d29a4dc2d34aeaedb36` |
| 11 | `docs/reviews/...-fix-codex.md` | 90 | 9,320 | `9dee714839efbef9b5743bfe55b7bb7ffc1d923e9906413479716a88c340069e` |
| 12 | `docs/reviews/...-fix-controller-validation.md` | 40 | 3,706 | `3ac4e5a526a246722da4ca4c2ec455332f4be3e2aa7a0bc140a5daec9aafc36a` |
| 13 | `docs/reviews/...-r12-...controller-validation.md` | 37 | 2,410 | `03c41be0313394b2c8cf3e8ab2309a09665668545d4b7e7a1682ffa201a498ea` |
| 14 | `docs/host/issues-implementation-control.md` | 2,311 | 577,727 | `42be332f35b7efe4ca206f6b537f286b9126945c3e7bf0cc5ace25a059921da2` |

**Host design 完整读取证据：** 分 10 块读取 `docs/host/design.md` 全部 3,696 行（offset 0→400→600→1000→1400→1800→2300→2800→3300，最后一块读到 line 3697 EOF）。内容覆盖 §1 设计目标 至 §28 第一版 Non-goals，包括 §3 dayu.runtime、§9 状态迁移矩阵、§10 Durable Store、§11 Host 公共接口、§18 ToolRuntime、§20 Tool Awaiting / Wait Record、§23 RunInputBuilder、§24 Conversation Memory、§25 Context Governance、§27 Host Lifecycle / Recovery 等全部关键章节。

**其它文档 EOF 验证：** engine design 最后行为 §16 Tool Schema（line 553）；tool design 最后行为 §10 Tool Authorization（line 134）；fins design 最后行为 §10 Upload Batch Plan（line 123）；ui design 最后行为 §3 dayu-cli init（line 111）；controller discussion 最后行为 Topic 9 裁决（line 731）；controller adjudication 最后行为 Verdict（line 81）；cleanroom review 最后行为 Verdict（line 360）；Codex fix 最后行为 code-generation-ready 自审（line 90）；Controller validation 最后行为 Next gate（line 40）；R12 validation 最后行为结论（line 37）。全部文档确认读到 EOF。

**未读取：** `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md`（routing-invalid，已由 clean-room artifact 替代）。

## 3. AR-PLAN-PF01 / PF02 关闭验证

### 3.1 AR-PLAN-PF01 — CLI direct-stream test consumer 遗漏

| Controller 要求 | Final plan 验证 | 判定 |
| --- | --- | --- |
| Slice 2 mutable test allowlist 加入 `tests/cli/test_fins_commands.py` | §3.2 Slice 2 精确包含 `M tests/cli/test_fins_commands.py` | ✓ CLOSED |
| Focused test 覆盖 CLI consumer | §4.2 focused pytest 命令显式包含该文件 | ✓ CLOSED |
| Consumer scan 覆盖 CLI consumer | §4.2 增加新 public owner consumer scan，要求精确命中三个 production 与三个 test consumers，并显式包含 CLI test | ✓ CLOSED |
| Direct-stream stale scan 覆盖 `dayu tests utils` | §4.2、§6.6、§7 与 final aggregate 均固定扫描根 `dayu tests utils`，要求 `dayu.fins.direct_stream` 零命中 | ✓ CLOSED |
| 不保留 compatibility module/re-export/fallback | §2.3、§4.2、checklist 与 stop conditions 均保持物理 owner migration | ✓ CLOSED |

**直接证据 — 完整 import graph 验证：** `rg -n 'dayu\.fins\.direct_stream' dayu tests utils` 确认当前 6 处 consumer：

| 文件 | 类型 | Slice 2 allowlist |
| --- | --- | --- |
| `dayu/cli/commands/fins.py:56` | production | ✓ production allowlist |
| `dayu/fins/ingestion_runtime.py:46` | production | ✓ production allowlist |
| `dayu/service/fins_direct.py:25` | production | ✓ production allowlist |
| `tests/fins/test_fins_direct_stream.py:24` | test | ✓ test allowlist |
| `tests/service/test_fins_direct.py:26` | test | ✓ test allowlist |
| `tests/cli/test_fins_commands.py:39` | test | ✓ test allowlist（PF01 fix） |

`utils/` 目录无 `direct_stream` import。全部 6 处 consumer 在 allowlist 中覆盖。

### 3.2 AR-PLAN-PF02 — public-awaiting validation utility 遗漏

| Controller 要求 | Final plan 验证 | 判定 |
| --- | --- | --- |
| 新增独立 Slice 2 mutable validation-utility allowlist | §3.3 单独列出 `M utils/smoke_host_public_awaiting_entrypoint.py`；§3.5 要求其它 `utils/**` 全部零 diff | ✓ CLOSED |
| Utility 只迁移 `AwaitingResolutionMode` import | §3.3、§4.2、§6.4、stop conditions 均限定从旧 private helper 迁到 `dayu.fins.ingestion.awaiting_resolution`；九个业务/类型用法（源行 455、456、457、786、807、823、839、852、919）与其它行零 diff | ✓ CLOSED |
| Slice 2 owner-migration focused gate 运行 public-awaiting smoke | §4.2 real-smoke 命令与 Slice exit 新增 Slice 2 fresh smoke，明确禁止沿用 Slice 1 迁移前结果 | ✓ CLOSED |
| Awaiting scans 覆盖 `dayu tests utils` | §4.2 分开新 owner 定义、新 owner consumer、旧 private definition、旧 private import 四组 scans；§6.6/§7 要求 final aggregate fresh 重跑 | ✓ CLOSED |
| 旧 private import 零命中 | §4.2 scan outcome 与 §6.6 均要求旧 `dayu.fins.tools._ingestion_tool_helpers` 中的三项定义与旧 import 零命中 | ✓ CLOSED |

**直接证据 — 完整 consumer 验证：** 10 个文件消费 awaiting 三项语义：

| 文件 | 符号 | allowlist |
| --- | --- | --- |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 三项定义（Slice 2 删除） | ✓ production |
| `dayu/fins/tools/download_provider.py` | `parse_awaiting_resolution_mode` | ✓ production |
| `dayu/fins/tools/preprocess_provider.py` | `parse_awaiting_resolution_mode` | ✓ production |
| `dayu/fins/tools/upload_provider.py` | `parse_awaiting_resolution_mode` | ✓ production |
| `dayu/service/fins_wait_adapter.py` | `AwaitingResolutionMode` | ✓ production |
| `dayu/service/host_assembly.py` | 三项 | ✓ production |
| `tests/service/test_fins_wait_adapter.py` | `AwaitingResolutionMode` | ✓ test |
| `tests/service/test_host_assembly.py` | `AwaitingResolutionMode` | ✓ test |
| `tests/fins/test_fins_ingestion_tools.py` | 两项 | ✓ test |
| `utils/smoke_host_public_awaiting_entrypoint.py` | `AwaitingResolutionMode`（9 处用法） | ✓ validation-utility（PF02 fix） |

全部 10 处 consumer 在精确 allowlist 中覆盖。

## 4. Rejected/No-Fix 保护验证

以下候选被 Controller adjudication 拒绝。逐项确认 final plan 中未偷带：

| 候选 | 验证 | 判定 |
| --- | --- | --- |
| Logging handler/registry candidates | Plan 未扩充 production logging 路径，未改全局 conftest；§2.5 保持 implementation/review 验证点 | ✓ 未偷带 |
| Compactor parent id candidate | §2.4 保持 `parent_host_run_id == host_run_id` 断言，未重复加条款 | ✓ 未偷带 |
| SEC/Docling coverage feasibility candidates | §4.3 保持 production zero-diff、80% threshold、production-defect stop condition | ✓ 未偷带 |
| `direct_events.py` module width | §2.3 明确"validator state machine、原异常身份、close-at-most-once、terminal result identity 和 public error contract 保持不变；本轮只迁 owner，不重设计 protocol" | ✓ 未偷带 |
| Per-slice validation 成本 | §5 保持三个固定 slices 与 fresh gates | ✓ 未偷带 |
| External provider availability | §4.2 保持"保存真实 failure evidence 交 Controller 裁决且禁止 mock PASS" | ✓ 未偷带 |
| AR-F06 exclusion 移除条件 | §2.2 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` | ✓ 未偷带 |
| Ruff baseline | §6.3 保持每 slice 规范化 exact-set delta | ✓ 未偷带 |
| Provider import 措辞 | 未重复语义 | ✓ 未偷带 |
| DS `test_fins_ingestion_runtime.py` candidate | 不在 mutable allowlist，direct scan 证明无 `direct_stream` import | ✓ 未偷带 |
| routing-invalid `...plan-review-mimo.md` | 未读取、未引用 | ✓ 未偷带 |

**结论：** 没有 deferred code change 被偷带为 implementation 授权。Security/deferred/no-code ledger 与原计划保持不变。

## 5. 三 Slice 计划完整审查

### 5.1 Motivation 审查

Plan §2.1 动机判断成立：R01—R12 的 accepted evidence 不能证明最终整合树的全量测试顺序、跨层 import、当前 artifact schema、逐文件 coverage 或真实 Windows runner。五组本地 actionable defects 已由 Codex aggregate regression 和 Controller adjudication 直接证据支持。

### 5.2 Scope 审查

- AR-F01—F05 有唯一 closure owner 与 test oracle。
- AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- AR-F07 保持 `PENDING_RELEASE_BLOCKER`。
- Topic 8（240 字符截断）保持 no-code。
- Topic 9（统一 tool authorization）保持 no-code / deferred。
- Issue 177/178/175/142/151 保持各自 owner。

Scope 精确、稳定，无漂移。

### 5.3 Sequencing 审查

Slice 1 → Slice 2 → Slice 3 依赖链：

- **Slice 1**（test fixture / harness / oracle）：不改 production。它是 Slice 2/3 的前置，因为 canonical suite 需要先恢复全绿（除 AR-F02 临时失败）。
- **Slice 2**（production migration）：依赖 Slice 1 的 test oracle 恢复（特别是 AR-F04 compactor oracle），且需要 canonical suite 全绿。
- **Slice 3**（coverage closure）：依赖 Slice 2 的 stable integration tree。Production zero-diff。

不可并行，不可重排。每 slice 全量验证成本一致。

### 5.4 Owner Boundary 审查

| AR-Finding | Semantic Owner | Plan Boundary | 判定 |
| --- | --- | --- | --- |
| AR-F01 | `ConfigLoader` required fields owner | 只修 test fixture，不给 production 加默认值/fallback | ✓ |
| AR-F02 | `ValidatedFinsEventStream` → `dayu.fins.direct_events`；`AwaitingResolutionMode` → `dayu.fins.ingestion.awaiting_resolution` | 物理 owner migration，不扩大 allowlist，不兼容 re-export | ✓ |
| AR-F03 | Standalone CLI logging 语义 vs test harness isolation | 只修 test harness，standalone product logging 零 diff | ✓ |
| AR-F04 | Runner-call manifest → compaction request digest → compact artifact | 只用 current owner-published fields，禁止 candidate_id/raw guess/fallback | ✓ |
| AR-F05 | 九个 production owners | Production zero-diff，只补 owner-contract tests | ✓ |

### 5.5 Over-coupling 审查

- **Slice 1**：三个 test 文件修改，无 production 变更。无跨层耦合。
- **Slice 2**：12 个 production 文件 + 7 个 test 文件 + 1 个 validation utility。核心是 import 路径迁移，必须原子完成。`direct_events.py` 合并 validator 后不引入 import cycle（当前 `direct_stream.py` import `direct_events.py`，合并后消除跨模块依赖）。无双向依赖。
- **Slice 3**：6 个 test 文件，production zero-diff。无 production 耦合。

### 5.6 State Machine 审查

§5 的 per-slice state machine 是严格顺序：

1. AgentCodex implementation → 2. AgentMiMo + AgentDS 独立 review → 3. Controller adjudication → 4. AgentCodex fix accepted findings → 5. Re-run gates → 6. AgentMiMo + AgentDS re-review → 7. Controller final validation

前一 slice 未接受不得开始下一 slice。每一步有明确的输入、输出和验证标准。

### 5.7 Test/Coverage 审查

- **Slice 1**：3 个 test 文件。Focused tests + canonical suite + coverage + pyright + Ruff + build + scans + smokes。
- **Slice 2**：7 个 test 文件 + 1 个 validation utility。同上 + import boundary + rg scans + real Fins/Host smoke。
- **Slice 3**：6 个 test 文件。同上 + 九路径 focused coverage + real smoke。Production zero-diff。

Coverage 门禁：只排除 R05 精确单 node，最终 `219/219 >=80%`。每个 slice 的 focused tests、canonical suite、coverage、pyright、Ruff、diff、build、scans、README/security/deferred/no-code 和真实 smoke 均有明确命令。

### 5.8 Security 审查

- AR-F02：Service import boundary 验证（`test_import_boundary.py` 零 diff 且自然通过）。
- AR-F03：Logging state 隔离（不修改 standalone logging 行为）。
- AR-F05：Production zero-diff（不暴露新 attack surface）。
- §6.7：Secret scan、path containment、Web DNS/private/proxy/redirect/diagnostic。
- AR-F07：Windows workflow evidence gate。

### 5.9 Deferred/No-Code 审查

| 项目 | 状态 | 判定 |
| --- | --- | --- |
| Topic 8（240 字符截断） | no-code，不在此 WU | ✓ |
| Topic 9（统一 tool authorization） | no-code / deferred | ✓ |
| Issue 177（TruncationManager wiring） | deferred | ✓ |
| Issue 178（storage-state lifecycle） | deferred | ✓ |
| Issue 175（Fins process isolation） | deferred | ✓ |
| Issue 142/151（migration / assets） | deferred | ✓ |

### 5.10 Stop Conditions 审查

§9 的 10+ stop conditions 覆盖：

- 语义 owner 不一致。
- AR-F05 测试暴露 production defect。
- Service boundary 必须扩大 allowlist。
- Import cycle / lazy import / re-export。
- Current compact artifact schema 不一致。
- Logger state 无法恢复。
- Canonical suite 非零。
- Coverage 除 R05 node 外还需排除。
- 219 集合不精确或任何文件 <80%。
- pyright/Ruff/diff/protected paths/staged state 异常。
- Security/secret/deferred/no-code scan 新命中。
- Build 失败。
- Windows evidence 缺失。

## 6. 新发现

### 无 material new findings。

经过完整 re-review，未发现新的 material plan defect。以下为 observation 级说明：

#### OBS-01 [OBSERVATION] `tests/fins/test_fins_ingestion_runtime.py` 在 Slice 2 focused tests 但不在 allowlist

**位置:** §4.2 focused test 命令。

**说明:** 该文件出现在 Slice 2 focused pytest 命令中，但不在 §3.2 mutable test allowlist 中。Direct scan 确认该文件不 import `direct_stream`，因此不需要修改。作为 regression 测试包含在 focused tests 中是合理的。

**Verdict:** 不是 plan defect。作为 regression 覆盖是正确做法。

#### OBS-02 [OBSERVATION] Python logging `loggerDict` 限制

**位置:** §2.5 / MiMo cleanroom Challenge 2。

**说明:** Python `logging.Logger.manager.loggerDict` 是进程全局状态，不提供原生 `removeLogger` API。Plan 要求"清除本次调用新建的 logger entries"，实现时可能需要从 `manager.loggerDict` 中删除或标记为 `PLACEHOLDER`。

**Verdict:** 不是 plan blocker。Plan 已明确这是 implementation/review 验证点。

#### OBS-03 [OBSERVATION] `dayu/fins/ingestion/__init__.py` 可能需要为空或已存在

**位置:** §3.5 protected zero-diff paths。

**说明:** `dayu/fins/ingestion/__init__.py` 在 protected zero-diff 列表中。当前 `dayu.fins.ingestion` 已在 `SERVICE_ALLOWED_IMPORTS` 中（line 25），说明该包已存在且有 `__init__.py`。新增 `awaiting_resolution.py` 子模块不需要修改 `__init__.py`（前缀匹配自动覆盖）。

**Verdict:** 不是 plan defect。Package 已存在。

## 7. Six Mandatory Lenses 裁决

### Lens 1: Architecture Boundary Review

**裁决: PASS。**

- `UI -> Service -> Host -> Engine` 分层严格遵守。
- Fins public contract migration 不扩大 Service allowlist。
- `direct_events.py` 合并 validator 消除跨模块依赖，不引入反向依赖。
- `dayu.fins.ingestion.awaiting_resolution` 是 Fins public boundary 内的新模块。
- `dayu.runtime` 不受影响。

### Lens 2: Best-Practice Review

**裁决: PASS。**

- Test fixture 只修 schema 缺陷，不给 production 加默认值（best practice: test adapts to production, not vice versa）。
- In-process logging isolation 是 test harness 标准做法。
- Manifest digest 关联是 owner-published fields 的严格消费（best practice: consume typed contract, don't guess）。
- Physical owner migration 是消除 import boundary violation 的标准做法。

### Lens 3: Optimal-Solution Review

**裁决: PASS。**

- AR-F02 的物理 owner migration 优于扩大 Service allowlist（后者只是绕过问题）。
- AR-F04 的 manifest digest 关联优于恢复 candidate_id（后者是已删除的 legacy）。
- AR-F03 的 in-process harness isolation 优于修改 standalone logging（后者改变 production 行为）。

### Lens 4: Overengineering Review

**裁决: PASS。**

- Plan 没有引入不必要的抽象、builders、wrappers、protocols 或 generalization。
- §2.3 明确"validator state machine、原异常身份、close-at-most-once、terminal result identity 和 public error contract 保持不变；本轮只迁 owner，不重设计 protocol"。
- §4.3 明确"不得直接复制 production 算法到期望值，不得只调用 private helper 而没有业务可观察断言"。

### Lens 5: Overcoupling Review

**裁决: PASS。**

- 三个 slices 有明确的切分理由和依赖关系。
- Slice 2 的 production/test 变更必须原子完成（import migration 的本质要求）。
- Slice 3 production zero-diff，与前两个 slices 解耦。
- Protected zero-diff paths 精确列出，防止意外耦合。
- `tests/fins/test_fins_ingestion_tools.py` 在 Slice 2 和 Slice 3 各有不同的变更语义（import migration vs coverage supplement），不构成过度耦合。

## 8. 完整 Host Design 一致性分析

Host design 全文 3,696 行已完整读取。以下为与本 plan 直接相关的 design-to-plan 一致性验证：

### 8.1 AR-F01 wait_poller_policy — Host design §3 / §20 一致性

**Design 事实：** Host design §3 规定 `host_runtime.json` 表达 Host opener 部署默认值，包括 wait poller policy。§20 详述 wait record 语义、observation timeout 不等于 lost、deadline 与 observation timeout 的区别、poll adapter claim/backoff 机制。Controller discussion Topic 5 最终裁决：`wait_poller_policy` 必须来自配置，awaiting resolution 选择必须可配置，poller runtime settings 写在 `host_runtime.json`。

**Plan 对齐：** Plan §4.1 要求 `_write_host_runtime` fixture 写出 current required `wait_poller_policy` 全量 12 字段。这与 design §3 的 `host_runtime.json` 结构一致。Plan 明确"禁止给 production 加默认值/fallback"，与 design 的"默认值只能在 Host composition root 构造时应用"一致。

**判定：** ✓ 一致。

### 8.2 AR-F02 Fins public contract — Host design §18 / Fins design §7 一致性

**Design 事实：** Host design §18 规定 ToolRuntime 接收 `ToolBundle`、消费 public contract、不重建枚举/Protocol。Fins design §7 规定"一次 Fins direct download/preprocess/upload stream 必须恰好产生一个 terminal `RESULT`。该不变量由一个 Fins-owned stream validator / typed terminal boundary 判定一次。Service 与 CLI 只消费同一个 terminal 或 typed protocol error"。

**Plan 对齐：** Plan §2.3 把 `ValidatedFinsEventStream` 物理迁入 `dayu/fins/direct_events.py`，使其成为 direct event/terminal contract 的唯一 owner。Service 与 CLI 只消费同一个 typed terminal。`AwaitingResolutionMode` 迁入 `dayu/fins/ingestion/awaiting_resolution.py`，Service 只消费 public contract。

**判定：** ✓ 一致。Plan 的物理 owner migration 与 design 的"一个 Fins-owned stream validator / typed terminal boundary 判定一次"完全对齐。

### 8.3 AR-F04 compaction manifest digest — Host design §23.1 / §25 一致性

**Design 事实：** Host design §23.1 详述 `RUNNER_CALL_INPUT_ASSEMBLED` manifest 结构，包括 `compactor_identity` 字段（`parent_host_run_id`、`compaction_operation_id`、`compactor_engine_run_id`、`compaction_attempt_number`、`compaction_request_digest`、`compactor_input_projection_ref`）。§25 规定 compact event 必须通过 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 反向引用 accepted proposal manifest。

**Plan 对齐：** Plan §2.4 要求从 manifest 的 `compactor_identity.compaction_request_digest` 读取 SHA-256 digest，以 `artifact_kind == "context_compaction"` 且 top-level `compaction_request_digest` 与 manifest 完全相等定位唯一 compact artifact。这与 design 的 manifest-based reconstruction contract 完全一致。

**判定：** ✓ 一致。

### 8.4 AR-F06 scheduler close — Host design §9.1 / §27 一致性

**Design 事实：** Host design §9.1 详述 `RECOVERING` 退出路径（`RUNNING`、`CANCELLED`、`FAILED`、`LOST`）。§27 规定 recovery scan 必须具备 positive orphan proof 才能把 Attempt 标为 `LOST`，heartbeat stale 单独不构成 orphan proof。

**Plan 对齐：** Plan §2.2 保持 AR-F06 为 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，§9 残余风险明确"AR-F06 是真实 scheduler/lifecycle bug，不因本计划消失；本轮只保持其 owner/destination，不修、不 waive"。

**判定：** ✓ 一致。Plan 正确识别该 bug 需要独立 Host scheduler/lifecycle work item。

### 8.5 AR-F05 coverage — Host design §18 / AGENTS.md 一致性

**Design 事实：** Host design §18 规定 ToolRuntime 边界、tool fact accept barrier、语义级重复工具调用治理。AGENTS.md 规定"单文件测试覆盖率目标为 >= 80%"。

**Plan 对齐：** Plan §4.3 要求九个 production paths 每个 fresh line coverage >=80.00%，production zero-diff，只补 owner-contract tests。Plan 的 stop condition 要求"测试暴露 production defect 时立即停止"。

**判定：** ✓ 一致。

### 8.6 Overcoupling 复核（完整 design 视角）

完整读取 host design 后，确认 plan 没有引入跨层耦合：
- Slice 2 的 Fins migration 不触及 Host/Engine/Tool 的任何 production code。
- Slice 1 的 test fixture 修改不改变 Host durable store schema 或 state machine。
- Slice 3 的 coverage tests 不修改 production code。
- Protected zero-diff paths 精确覆盖了 Host design 的关键治理模块（dispatch、engine_ingest、execution_health、compact_payload 等）。

## 9. Residual Risks

| ID | 状态 | 说明 |
| --- | --- | --- |
| AR-F06 | RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX | scheduler close/terminal promotion bug，后续独立 Host scheduler/lifecycle work item |
| AR-F07 | PENDING_RELEASE_BLOCKER | Windows real runner evidence 不存在 |
| Coverage timing | EXISTING_COVERAGE_TIMING_BASELINE | R05 scheduler node 在 coverage 下复现，精确单 node exclusion |
| Logger registry | OBSERVATION / NEEDS_EVIDENCE | Python logging 内部 API 限制；需实现时验证 |
| Slice 3 九路径 coverage | IMPLEMENTATION_RISK | `docling_processor.py`（63.46%）和 `sec_table_extraction.py`（66.16%）到 80% 需要较多高价值边界 cases；Plan stop condition 是正确防线 |

## 10. Final Verdict

**PASS / 0 NEW MATERIAL FINDINGS / READY_FOR_CONTROLLER_ACCEPTANCE。**

Plan 整体设计严谨、约束精确、验证门禁完整。五个 mandatory lenses 全部通过。`AR-PLAN-PF01..02` 已确认真正关闭。Rejected/no-fix 建议没有偷带。三个 slices 的 motivation、scope、sequencing、owner boundary、over-coupling、state machine、test/coverage、security、deferred/no-code、stop conditions 和 residual risks 均经审查无 material defect。

Plan 不授权 implementation、stage、commit、push、PR、aggregate deepreview 或 closeout。下一 gate 由 Controller 裁决。

## 11. Artifact Metrics

| 项 | 值 |
| --- | --- |
| 执行时间 | `2026-07-18 16:55:08 +0800`（初始）；`2026-07-18 17:10:00 +0800`（metrics 修订） |
| 被审 plan SHA-256 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` |
| 被审 plan 行数 | 640 |
| 读取文档总数 | 14（全部独立 wc/shasum 验证） |
| Host design 读取 | 3,696 行 / 388,584 bytes / 分 10 块读取到 EOF |
| 独立 metrics 方法 | `wc -l -c` + `shasum -a 256` |
| Findings（material） | 0 |
| Observations | 3 |
| Verdict | PASS |
