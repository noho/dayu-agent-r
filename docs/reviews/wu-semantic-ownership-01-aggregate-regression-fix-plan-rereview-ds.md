# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Plan — AgentDS 完整 Re-Review

## 0. Review Identity

- **Reviewer**: AgentDS（第二路独立、从零、完整 plan re-review）
- **Re-reviewed target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
- **Re-reviewed hash (SHA-256)**: `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` ✅ 已独立核对，精确匹配 Controller validation 记录的 immutable final plan hash
- **Re-reviewed metrics**: 640 行 / 50,784 bytes ✅ 已独立核对（`wc -l -c`）
- **系统时钟**: `2026-07-18 16:53:52 +0800`
- **Review posture**: constructively adversarial — 独立挑战所有维度，不读取 AgentMiMo review，不启动 subagent/Explore/Task
- **不可变基线**: branch `phaseflow/host-issues-control`，HEAD `ed9bfa9fe071aba0227361c69a938010ce3abe09`

## 1. 完整证据清单

所有证据均已独立、完整读取到 EOF，并用 `wc -l -c` 与 `shasum -a 256` 独立记录精确 metrics：

| # | 证据来源 | 行数 | 字节数 | SHA-256 | 用途 |
| --- | --- | ---: | ---: | --- | --- |
| 1 | `AGENTS.md` | 128 | 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | 项目最高约束、语义所有权、架构硬约束、LLM-facing 文本约束 |
| 2 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 640 | 50,784 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | **本轮 re-review 目标** |
| 3 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` | 81 | 7,457 | `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06` | AR-PLAN-PF01/PF02 唯一授权真源 |
| 4 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md` | 483 | 42,247 | `94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615` | 先前 DS review，用于对比 finding closure |
| 5 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-codex.md` | 90 | 9,320 | `9dee714839efbef9b5743bfe55b7bb7ffc1d923e9906413479716a88c340069e` | AgentCodex fix artifact，AR-PLAN-PF01/PF02 closure 证据 |
| 6 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-controller-validation.md` | 40 | 3,706 | `3ac4e5a526a246722da4ca4c2ec455332f4be3e2aa7a0bc140a5daec9aafc36a` | Controller fix validation |
| 7 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | 65,088 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` | Topic 1–9 最终裁决、design truth writeback |
| 8 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` | 668 | 43,672 | `eb6528c2c1e59d4791a62b5cbb5f90fe84d517db368cd2cae4e51da253cacb11` | AR-F01–F07 direct evidence ledger、219 coverage table |
| 9 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` | 94 | 8,101 | `73dfecd1aed86ca59c44d6b40c012add309b261539b8f25d129a728ae2942539` | Controller 最终 finding disposition |
| 10 | `docs/host/design.md` | 3,696 | 388,584 | `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9` | Host 架构事实（完整到 EOF L3696） |
| 11 | `docs/engine/design.md` | 553 | 39,726 | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` | Engine 边界（完整到 EOF L553） |
| 12 | `docs/tool/design.md` | 134 | 11,240 | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` | Tool config ownership（完整到 EOF L134） |
| 13 | `docs/fins/design.md` | 123 | 7,460 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` | Fins public contract（完整到 EOF L123） |
| 14 | `docs/ui/design.md` | 111 | 7,920 | `5a19c829151777b1d9f3c69f1a9a305396f75c8e73eb5ea31577663c55bed973` | CLI/init/upload entrypoint（完整到 EOF L111） |

## 2. Pre-existing Protected Path Hash Verification

Plan §1 列出的 entry baseline protected paths 与当前实际 SHA-256 比对：

| Status | Path | Plan baseline SHA-256 | Current SHA-256 | Match |
| --- | --- | --- | --- | --- |
| ` M` | `docs/host/issues-implementation-control.md` | `93dd662e755b0f7bbfc8ad82045bc54ed61b94d7bf3df22f14c385b242e56100` | `42be332f35b7efe4ca206f6b537f286b9126945c3e7bf0cc5ace25a059921da2` | **AUTHORIZED TRANSITION** (Controller gate update，见 §2.1) |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` | `eb6528c2...` | `eb6528c2...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` | `73dfecd1...` | `73dfecd1...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md` | `bddc028b...` | `bddc028b...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` | `a5876c47...` | `a5876c47...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md` | `94f31570...` | `94f31570...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md` | `2cab2ad9...` | `2cab2ad9...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md` | `2cb04968...` | `2cb04968...` | ✅ |
| `??` | `docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md` | `03c41be0...` | `03c41be0...` | ✅ |

**Gate transition evidence**: `docs/host/issues-implementation-control.md` 的 SHA-256 已从 plan-fix entry baseline `93dd662e...` 变更为当前 `42be332f...`。这是 Controller 在 plan-fix 完成后、fixed-plan re-review gate 期间按职责更新的授权 control document 变更，不是 AgentCodex scope drift 或未授权修改。Controller 已确认当前 control immutable hash 为 `42be332f35b7efe4ca206f6b537f286b9126945c3e7bf0cc5ace25a059921da2`。其余 8 个 pre-existing protected paths 的 SHA-256 全部与 plan §1 baseline 精确匹配。✅

新增的 plan-fix gate artifacts（不在 plan §1 baseline 中，属于本轮 plan-fix gate 产出）：

| Status | Path | SHA-256 | 备注 |
| --- | --- | --- | --- |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-codex.md` | `9dee7148...` | Codex fix artifact，Controller validation 已确认 |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-controller-validation.md` | `3ac4e5a5...` | Controller fix validation |

### 2.1 Gate Transition Evidence

Controller 在 plan-fix 完成后、fixed-plan re-review gate 期间，按 phaseflow 职责对以下路径做了授权更新。这些变更由当前 gate 授权，不是 AgentCodex scope drift，也不是 plan 缺陷：

| Path | Plan-fix entry SHA-256 | Current SHA-256 | 变更性质 |
| --- | --- | --- | --- |
| `docs/host/issues-implementation-control.md` | `93dd662e...` | `42be332f35b7efe4ca206f6b537f286b9126945c3e7bf0cc5ace25a059921da2` | Controller gate tracking 更新 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-controller-validation.md` | absent | `3ac4e5a526a246722da4ca4c2ec455332f4be3e2aa7a0bc140a5daec9aafc36a` | Controller 新建 validation artifact |

这两个路径的 hash 漂移是 **授权 gate transition**，不触发 plan §9 stop condition。当前 re-review gate 的 control immutable hash 为 `42be332f...`，Controller validation hash 为 `3ac4e5a5...`。

## 3. AR-PLAN-PF01 Closure 独立验证

Controller adjudication 对 AR-PLAN-PF01 的五项要求与 final plan 闭环逐项比对：

| # | Controller 要求 | Final plan 证据 | 判定 |
| --- | --- | --- | --- |
| 1 | Slice 2 mutable test allowlist 加入 `tests/cli/test_fins_commands.py` | §3.2 Slice 2 only: `M tests/cli/test_fins_commands.py` | **CLOSED** ✅ |
| 2 | Focused test 覆盖 CLI consumer | §4.2 focused pytest 命令显式包含 `tests/cli/test_fins_commands.py` | **CLOSED** ✅ |
| 3 | Consumer scan 覆盖 CLI consumer | §4.2: "精确命中三个 production 与三个 test consumers，并显式包含 `tests/cli/test_fins_commands.py`" | **CLOSED** ✅ |
| 4 | Direct-stream stale import scan 覆盖 `dayu tests utils`，旧 import 零命中 | §4.2、§6.6、§7 均要求 `dayu.fins.direct_stream` 零命中；§4.2 Slice exit 明确要求记录 zero-match exit 1 | **CLOSED** ✅ |
| 5 | 不保留 compatibility module/re-export/fallback | §2.3 明确 "不在 `dayu/fins/__init__.py`、旧模块、其他模块或 `TYPE_CHECKING` 分支 re-export；不保留 wrapper/facade"；§4.2 只改 import 路径 | **CLOSED** ✅ |

**裁决**: AR-PLAN-PF01 在 final plan 中已精确关闭。五项要求全部有直接 plan 文本证据，无遗漏、无弱化。

## 4. AR-PLAN-PF02 Closure 独立验证

Controller adjudication 对 AR-PLAN-PF02 的五项要求与 final plan 闭环逐项比对：

| # | Controller 要求 | Final plan 证据 | 判定 |
| --- | --- | --- | --- |
| 1 | 新增独立 Slice 2 mutable validation-utility allowlist，仅含 public-awaiting utility | §3.3 单独列出 `M utils/smoke_host_public_awaiting_entrypoint.py`；§3.5 要求其它 `utils/**` 全部零 diff | **CLOSED** ✅ |
| 2 | Utility 只迁移 `AwaitingResolutionMode` import | §3.3: "九个业务/类型使用位置与其它行必须保持不变；不得复制 enum、parser 或 config field"；§4.2 限定 import 迁移 | **CLOSED** ✅ |
| 3 | Slice 2 owner-migration focused gate 运行 public-awaiting smoke | §4.2 real-smoke 命令 + Slice exit: "Owner 迁移后的 public-awaiting smoke 必须在 Slice 2 fresh 通过；不得沿用 Slice 1 在迁移前的结果" | **CLOSED** ✅ |
| 4 | Awaiting definition/import scans 覆盖 `dayu tests utils` | §4.2 四组独立 scans：新 owner definition、新 owner consumer、旧 private definition、旧 private import；§6.6/§7 要求 final aggregate fresh 重跑 | **CLOSED** ✅ |
| 5 | 旧 private import 零命中，不复制 enum/parser/config field，不增兼容路径 | §3.3、§4.2 scan outcome、Slice exit、stop conditions、checklist (§10) 全部一致 | **CLOSED** ✅ |

**裁决**: AR-PLAN-PF02 在 final plan 中已精确关闭。五项要求全部有直接 plan 文本证据，无遗漏、无弱化。Controller validation §3 独立确认了相同的 closure。

## 5. Rejected/No-Fix 建议防偷带独立审查

AgentCodex fix artifact §3 明确列出所有被 Controller 拒绝或已由原 plan 覆盖的候选，并确认没有改写为 implementation 授权。逐项独立验证：

| 候选 | Controller/Codex disposition | Final plan 中是否被偷带？ | 证据 |
| --- | --- | --- | --- |
| Logging handler/registry 深度 | 不扩充 production logging 路径 | **未被偷带** | §2.5 仍限定 test-only harness；§3.5 item 2 `dayu/runtime/log.py` 与 `tests/conftest.py` 均为 protected zero-diff |
| Compactor parent id 措辞 | 不重复加条款 | **未被偷带** | §2.4 step 2 保持不变（`parent_host_run_id == host_run_id`） |
| SEC/Docling coverage feasibility | 不预扩 allowlist / 不降 threshold | **未被偷带** | §3.2 Slice 3 allowlist 仍为 6 个文件；§4.3 仍要求 80%；stop condition 保持不变 |
| `direct_events.py` module width | 不新增抽象/拆分 | **未被偷带** | §2.3 仍为物理迁入单一模块；无新 abstraction |
| Per-slice validation 成本 | 不复用旧结果 | **未被偷带** | §5 每 slice 独立 review/fix/re-review；§6 每 slice fresh gates |
| External provider availability | 不增 mock PASS/fallback | **未被偷带** | §4.2 Slice exit: "external provider 不可用时保留完整 failure evidence 并由 Controller 裁决，不能改成 mock PASS" |
| AR-F06 exclusion 移除条件 | 不替未来 WU 设计 | **未被偷带** | §8 AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` |
| Ruff baseline 列表 | 不复制进 plan | **未被偷带** | §6.3 仍为规范化 exact-set delta，无 literal 144-finding 列表 |
| Provider import 措辞 | 不重复语义 | **未被偷带** | §2.3、§3.1、§4.2 保持一致 |
| DS `test_fins_ingestion_runtime.py` | Controller 拒绝（direct scan 证明不 import `direct_stream`） | **未被偷带** | §3.2 Slice 2 test allowlist 不含该文件 |
| 初始 routing-invalid mimo.md | 不作为独立 evidence | **未被偷带** | §1 未将其列入 source of truth |

**裁决**: 全部 rejected/no-fix 候选均未被偷带进 final plan。AR-F06 状态保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，AR-F07 状态保持 `PENDING_RELEASE_BLOCKER`。Security/deferred/no-code ledger 与原 plan 及 Controller adjudication 完全一致。

## 6. 完整三 Slice Plan 重新审查

### 6.1 Motivation 重新审查 ✅ PASS

Plan §2.1 的动机陈述成立且与 Controller adjudication 精确对齐：
- Aggregate regression 不是重复验证：R01–R12 sub-WU accepted evidence 只证明各自当时的 slice tree，不能证明最终整合树。
- 五组本地 actionable defects (AR-F01–F05) 已稳定复现，不可用历史 sub-WU PASS 覆盖。
- AR-F06 有独立 scheduler/lifecycle destination，AR-F07 依赖远端 Windows runner。

**直接证据**: Codex aggregate regression artifact §9 的 failure ledger、Controller adjudication §10 "第一性原理结论"。

### 6.2 Scope 重新审查 ✅ PASS

Plan §0 明确限定 scope：
- 只处理既有 umbrella aggregate regression 的 Controller accepted findings (AR-F01–F05)
- 不创建新 WU，不改变原 WU 目标、设计真源或 residual destination
- 三个固定 implementation slices
- AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`
- AR-F07 保持 `PENDING_RELEASE_BLOCKER`

**边界检查**:
- 没有新增 production path 超出 §3.1 allowlist
- 没有新增 test path 超出 §3.2 allowlist
- 没有修改 design docs、control docs、既有 artifacts
- 没有修改 workflow files

### 6.3 Sequencing 重新审查 ✅ PASS

三 slice 顺序 Slice 1 → Slice 2 → Slice 3 是最小依赖闭包：

1. **Slice 1 必须先执行**: 建立 current-schema/test oracle (AR-F01, AR-F04) 和 in-process isolation (AR-F03)。这些都是 test-only 变更。若先做 Slice 2 (production migration)，AR-F01/F03/F04 的 failures 会与 AR-F02 的 import changes 交织，review 无法分离。

2. **Slice 2 必须居中**: 物理 owner migration (AR-F02) 改变 production import graph。Slice 3 的 coverage tests 依赖 Slice 2 的稳定 import graph 和 canonical suite 全绿。

3. **Slice 3 必须最后**: test-only coverage closure (AR-F05) 在稳定整合树上补齐。若提前到 Slice 1，import 路径变更后需重新调整 coverage tests。

三 slice 不能合并：Slice 1 和 Slice 3 虽然都是 test-only，但 Slice 3 依赖 Slice 2 的生产变更。Slice 1 和 Slice 2 风险级别不同（test-only vs. production migration），分 slice review 符合 umbrella optimization control 的高风险要求。

**验证**: 与 Controller adjudication §11 "下一 gate 与 plan 约束" 的三个 slice 顺序要求完全一致。

### 6.4 Owner Boundary 重新审查 ✅ PASS

逐一验证五个 AR 的 owner adjudication：

**AR-F01** (§2.2, §4.1):
- Owner: test fixture `_write_host_runtime` 的 current-schema profile projection
- 不是: production `ConfigLoader` 的容错设计
- Plan 行为: fixture 写出完整 12 字段 `wait_poller_policy`，不给 production 加默认值/fallback
- 符合 AGENTS.md: "代码必须改在 owner boundary 或其直接上游输入校验处"

**AR-F02** (§2.3, §4.2):
- Owner: Fins public contract (`direct_events.py` + 新建 `awaiting_resolution.py`)
- 不是: Service allowlist 放宽
- Plan 行为: 物理 owner migration，不扩大 allowlist，不 re-export
- 符合 AGENTS.md: "多个消费者需要同一语义时，必须复用同一个 source of truth"
- 与 `docs/fins/design.md` §7 "Direct Stream Terminal Contract" 一致：Fins-owned validator 判定一次

**AR-F03** (§2.5, §4.1):
- Owner: in-process test harness isolation (`test_smoke_web_ci.py`)
- 不是: standalone product logging (`utils/smoke_web_ci.py`)
- Plan 行为: test-only snapshot/restore，standalone product 零 diff
- 符合 AGENTS.md: "禁止局部止血"

**AR-F04** (§2.4, §4.1):
- Owner: Host current compact artifact / runner-call manifest 测试 oracle
- Plan 行为: manifest `compactor_identity.compaction_request_digest` → compact artifact `compaction_request_digest` 精确关联
- 删除 `candidate_id` 猜测，不恢复 `llm-compact:{run_id}` fallback
- 与 `docs/host/design.md` compactor artifact schema 一致

**AR-F05** (§4.3):
- Owner: 各 production owner 对应的 test owners
- Plan 行为: test-only coverage，production 零 diff
- Stop condition: 暴露 production defect → 立即停止

### 6.5 Over-Coupling 重新审查 ✅ PASS

**跨层穿透检查**:
- Slice 1: `tests/` → 不涉及生产分层
- Slice 2: Fins internal migration，import 路径变更不改变分层 `UI -> Service -> Host -> Engine`
- Slice 3: `tests/` → 不涉及生产分层

**双向依赖检查**:
- `direct_events.py` 迁入 validator 后的 import graph 已验证零 import cycle（DS 先前 review §4 Challenge 1）
- 新 `awaiting_resolution.py` 只被 consumers import，自身不 import 任何 `dayu.fins` 内部模块

**共享可变状态检查**:
- 无新共享状态引入
- ValidatedFinsEventStream state machine 保持不变
- AwaitingResolutionMode 是纯 enum + parser，无 mutable state

**过宽公共契约检查**:
- Plan 明确禁止 re-export、wrapper、facade
- Service 只消费 typed contract（`ValidatedFinsEventStream`、`AwaitingResolutionMode`），不重复实现
- 无新 abstraction layer、builder、protocol 或 generalization

### 6.6 State Machine 重新审查 ✅ PASS

**Per-slice review/fix/re-review state machine** (§5):
1. AgentCodex implementation → Controller path verification
2. AgentMiMo + AgentDS 双路完整 code review
3. Controller 逐条裁决 → AgentCodex 只修 accepted findings
4. 修复后重跑 focused tests + full gates
5. AgentMiMo + AgentDS 双路完整 re-review
6. Controller 最终 slice validation → 接受后才能下一 slice

此 state machine 完整、无跳跃、无 shortcut。每个 slice 的 exit criteria 精确（§4.1/§4.2/§4.3 Slice exit）。

**Aggregate regression state machine** (§7):
- 三 slice 全部接受后，重新 aggregate regression（不拼接旧结果）
- AgentMiMo + AgentDS 双路 aggregate deepreview
- Controller 裁决 → Codex fix → 双路 re-review → Controller 宣告 local pass

### 6.7 Test/Coverage 重新审查 ✅ PASS

**Slice 1 tests** (§4.1):
- `test_host_admin.py`: 补全 fixture + 收紧断言 ✅
- `test_smoke_web_ci.py`: 模块级 logger snapshot/restore helper + contract test ✅
- `test_public_compact_smoke.py`: 删除 candidate_id，digest 关联 + 6 deterministic fail-closed cases ✅

**Slice 2 tests** (§4.2):
- 5 个 test files import 路径更新 + `test_import_boundary.py` 零 diff ✅
- Direct-stream/awaiting owner scans 覆盖 `dayu tests utils` ✅

**Slice 3 tests** (§4.3):
- 6 个 test files（1 新建），从 public/owner contract 补齐 coverage ✅
- Stop condition 防止 production defect / private mirroring ✅

**Coverage** (§6.2):
- 精确单-node exclusion (R05 scheduler) ✅
- Line coverage 独立计算（`covered_lines / num_statements * 100`）✅
- 最终 ledger: 219/219 ≥80% ✅

**Real smokes**:
- Slice 1: real compactor, Web standalone, public awaiting ✅
- Slice 2: Fins upload/download/process, R03 semantic ownership, public awaiting fresh ✅
- Slice 3: same as Slice 2 + affected-owner paths ✅
- 全局: live browser cleanup, POSIX script/CLI/init, HKEX evidence 复核 ✅

### 6.8 Security 重新审查 ✅ PASS

Plan §6.7 的 security ledger 覆盖完整：
- Doc path containment/output truncation
- Web DNS/private/proxy/redirect/diagnostic
- Host digest/EventLog/opaque ref
- Wait late-publication fence
- Fins transaction/atomic swap/path/opaque id/direct validator
- CLI POSIX quoting/init containment/process fencing

与 Codex aggregate regression artifact §7 security ledger 对齐。Secret scan 要求零 value match。

### 6.9 Deferred/No-Code 重新审查 ✅ PASS

Plan §6.7 的 deferred/no-code ledger：
- Issue 177 (TruncationManager wiring): DEFERRED ✅
- Issue 178 (storage-state lifecycle): DEFERRED ✅
- Issue 175 (Fins process isolation): DEFERRED ✅
- Issue 142/151 (assets/migration): DEFERRED ✅
- Topic 8 (Engine 240 chars): NO_CODE ✅
- Codex F-13 (128-char runner code): NO_CODE ✅
- Topic 9 (unified authorization): NO_CODE ✅

全部与 Controller discussion 和 Codex evidence 一致。没有将 deferred item 偷带进 implementation scope。

### 6.10 Stop Conditions 重新审查 ✅ PASS

Plan §9 的 stop conditions 全面覆盖：
- Semantic owner 不一致 → STOP
- 需要新增 allowlist 外 path → STOP
- AR-F05 暴露 production defect → STOP
- Service boundary 必须扩大 allowlist → STOP
- Import cycle → STOP
- Current compact artifact 无唯一 digest 关联 → STOP
- Logger state 无法完整恢复 → STOP
- Canonical suite 非零 (Slice 2+) → STOP
- Coverage 需额外 node exclusion → STOP
- 219 集合不是精确 219 → STOP
- Pyright 新增错误 → STOP
- Ruff baseline 扩散 → STOP
- Protected zero-diff path 变化 → STOP
- Staged state 非空 → STOP
- Controller-owned worktree hash 漂移 → **✅ 已裁决为授权 gate transition（§2.1）**

### 6.11 Residual Risks 重新审查 ✅ PASS

Plan §9 的 residual risks：
- AR-F06: 真实 scheduler/lifecycle bug，不因本 plan 消失 ✅
- AR-F07: 依赖真实 remote Windows runner ✅
- AR-F05: 大型 SEC/Docling owner 的 80% 门槛可能需要较多 cases ✅

## 7. Material Findings

### 7.1 本轮新 Finding

**无。** 经完整独立重新审查，final plan（640 行，SHA-256 `7e91421b...`）在 motivation、scope、sequencing、owner boundary、over-coupling、state machine、test/coverage、security、deferred/no-code、stop conditions 和 residual risks 全部维度均无新 material finding。

先前检测到的 `docs/host/issues-implementation-control.md` hash 变更已被 Controller 澄清为授权 gate transition（§2.1），不构成 plan finding。

### 7.2 先前 DS Review Findings 状态

| 先前 ID | 描述 | 当前状态 | 裁决 |
| --- | --- | --- | --- |
| AF-DS-01 | Logger handler 级别 state 未显式纳入 snapshot | 仍为 needs-evidence | Slice 1 implementation 时由 contract test 验证；plan §2.5 已要求 "预置 root 与至少一个 named logger 的非默认状态" |
| AF-DS-02 | `parent_host_run_id != host_run_id` 时 fail-closed 未显式说明 | 仍为 accepted-candidate | Plan §2.4 step 2 已写 `parent_host_run_id == host_run_id` 断言，不等时 test oracle 应 fail；不影响 plan 级正确性 |
| AF-DS-03 | 四个 SEC processor 共享一个测试文件 | 仍为 needs-evidence | Slice 3 implementation 前需评估；plan stop condition 是正确 safeguard |
| AF-DS-04 | `sec_report_form_common.py` 和 `sec_table_extraction.py` 增量较大 | 仍为 needs-evidence | 同上；plan stop condition 防止为 coverage 而降低测试质量 |
| AF-DS-05 | Per-slice full validation 成本 | 仍为 accepted-candidate | 符合 umbrella optimization control high-risk 要求；非 plan defect |
| AF-DS-06 | Slice 2 real smokes 依赖外部 provider | 仍为 accepted-candidate | Plan 已保护：external provider 不可用时保留 evidence 交 Controller 裁决 |
| AF-DS-07 | `tests/fins/test_fins_ingestion_runtime.py` 不在 Slice 2 allowlist | **CLOSED (REJECTED)** | Controller 通过 direct scan 证明该文件不 import `direct_stream`；Codex fix artifact §3 确认不加入 allowlist |
| AF-DS-08 | AR-F06 coverage exclusion 移除条件未定义 | 仍为 accepted-candidate | 不影响当前 plan；建议在 aggregate closeout 时明确 |

### 7.3 无 Material Finding 区域

以下维度经完整独立重新审查后，无新 material finding：

- **Goal/Non-Goals**: ✅ 精确对齐 Controller adjudication
- **AR-F01–F05 owner adjudication**: ✅ 五个 AR 的 owner 判定正确
- **AR-F06 residual**: ✅ no-code retained，exclusion 精确
- **AR-F07 blocker**: ✅ Windows external gate
- **Slice 顺序**: ✅ 最小可验证闭环
- **Production/test/validation-utility/README allowlists**: ✅ 精确、cross-checked
- **Protected zero-diff paths**: ✅ 7 组精确列出
- **Import cycle 风险**: ✅ 零风险
- **Service allowlist**: ✅ 零改动验证通过
- **Compactor digest association**: ✅ 唯一、严格、完整
- **Coverage 命令**: ✅ 单 node exclusion、line coverage 独立计算
- **Pyright/Ruff/Build/Scans**: ✅ 完整、可执行
- **Per-slice review/fix/re-review state machine**: ✅ 完整
- **Aggregate regression/deepreview gate**: ✅ 完整
- **Plan acceptance checklist** (§10): ✅ 18 项全部满足（基于 plan 文本独立核对）

## 8. Open Questions

1. **AF-DS-03/04**: Slice 3 SEC processor coverage 的 fixture/infrastructure 是否足够支撑四个 owner 的独立 contract tests？Slice 3 implementation 前需评估，但 plan stop condition 已覆盖此风险——若不足，触发 stop 交 Controller 重新裁决。

## 9. Residual Risks

1. **Slice 3 SEC processor coverage**: 四个 processor 从 65–78% 提升到 ≥80% 可能因 fixture 复杂度触发 stop condition（plan 设计的正确行为）。若触发，需 Controller 重新裁决 production owner 与 allowlist。
2. **External provider availability**: SEC EDGAR/HKEXnews 在 real smoke 期间不可用时，smoke gate 需 Controller 裁决（plan 已保护此路径）。
3. **Ruff baseline 变化**: 若外部提交合法改变 144-finding baseline，Controller 需先记录新 immutable set。
4. **AR-F06**: 真实 scheduler/lifecycle bug，不因本 plan 消失。本轮保持 no-code residual。
5. **AR-F07**: 依赖真实 remote Windows runner，不能在本地关闭。

## 10. Final Verdict

### 总体裁决

**PASS / READY_FOR_CONTROLLER_FINAL_ADJUDICATION**

Final plan（640 行，SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`）在以下维度全面通过独立、从零、完整 adversarial re-review：

- **AR-PLAN-PF01/PF02 closure**: 两个 accepted plan-fix finding 均已精确关闭，五项 Controller 要求逐项有直接 plan 文本证据
- **Rejected/no-fix 保护**: 全部 rejected/no-fix 候选均未被偷带进 final plan；AR-F06/F07 状态不变；security/deferred/no-code ledger 保持一致
- **Motivation**: 成立，与 Controller adjudication 精确对齐
- **Scope**: 精确限定在 AR-F01–F05，不扩域、不创建新 WU
- **Sequencing**: Slice 1 → Slice 2 → Slice 3 是最小依赖闭包
- **Owner boundary**: 五个 AR owner 判定正确，符合 AGENTS.md 语义所有权规则和 design docs
- **Over-coupling**: 无跨层穿透、无双向依赖、无过宽公共契约、无新 abstraction
- **State machine**: Per-slice review/fix/re-review + aggregate regression/deepreview 完整
- **Test/coverage**: 策略完整、命令精确、stop condition 正确
- **Security/deferred/no-code**: 全额对齐
- **Stop conditions**: 全面覆盖所有已知 failure mode；control document hash transition 已由 Controller 确认为授权 gate update
- **Residual risks**: 正确识别并 tracking

### Gate Transition Evidence

Controller 在 plan-fix 完成后对 `docs/host/issues-implementation-control.md` 的更新是授权 phaseflow gate tracking，已记录新 immutable hash `42be332f...`。Controller 新建的 validation artifact SHA-256 `3ac4e5a5...` 也已记录。其余 8 个 pre-existing protected paths 全部 hash 匹配。

### Plan Acceptance Checklist（独立核对）

- [x] 只存在本 plan 的新增 diff；product/test/README/workflow/control/既有 artifacts 零变化，staged 为空 ✅（control doc 授权更新除外）
- [x] 三个 slices 且顺序固定，AR-F01—F05 均有唯一 closure owner 与 test oracle ✅
- [x] AR-F02 不扩大 Service allowlist，无 compat re-export/lazy import/duplicate enum/protocol；Slice 2 test allowlist 包含 `tests/cli/test_fins_commands.py` ✅
- [x] Slice 2 独立 validation-utility allowlist 仅含 `M utils/smoke_host_public_awaiting_entrypoint.py`，只迁移 `AwaitingResolutionMode` import ✅
- [x] AR-F04 只用 current runner manifest + compaction request digest 关联，无 candidate_id/raw guess/fallback ✅
- [x] AR-F03 只做 in-process test harness isolation，standalone product logging 零 diff ✅
- [x] AR-F05 九路径 production 零 diff，production defect 触发 stop ✅
- [x] Production/test/validation-utility/README allowlists 与 protected paths 精确列出 ✅
- [x] 每 slice 含 focused tests、canonical suite、coverage、pyright、Ruff、diff、build、scans、README/security/deferred/no-code 和真实 smoke ✅
- [x] Coverage 只排除 R05 精确单 node；最终要求 219/219 line coverage >=80% ✅
- [x] 每 slice 要求 MiMo/DS 完整 code review、fix、完整 re-review；全部 slice 后重新 aggregate regression，再进入 MiMo/DS aggregate deepreview ✅
- [x] AR-F06 保持 no-code residual，AR-F07 保持 Windows pending release blocker ✅
- [x] Plan 经双路完整 plan review/fix/re-review 与 Controller 接受前不实施 ✅

### Plan 可实施性

Plan 的三个 slices 均 code-generation-ready。Slice 1 的 test harness 设计明确、Slice 2 的 import 迁移路径清晰、Slice 3 的 stop condition 是正确 safeguard。

### Pre-existing Accepted Finding Closure Summary

| Finding | Status | Evidence |
| --- | --- | --- |
| AR-PLAN-PF01 | **CLOSED** | §3.2, §4.2, §6.6, §7 |
| AR-PLAN-PF02 | **CLOSED** | §3.3, §4.2, §6.4, §6.6, §7 |
| AF-DS-07 (先前) | **CLOSED (REJECTED)** | Controller direct scan 证据 |

## 11. Artifact Metadata

| 字段 | 值 |
| --- | --- |
| re-reviewed_plan_sha256 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` |
| re-reviewed_plan_lines | 640 |
| re-reviewed_plan_bytes | 50,784 |
| system_clock | 2026-07-18T16:53:52+0800 |
| prior_ds_review_sha256 | `94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615` (483 行 / 42,247 bytes) |
| controller_adjudication_sha256 | `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06` |
| codex_fix_artifact_sha256 | `9dee714839efbef9b5743bfe55b7bb7ffc1d923e9906413479716a88c340069e` |
| controller_fix_validation_sha256 | `3ac4e5a526a246722da4ca4c2ec455332f4be3e2aa7a0bc140a5daec9aafc36a` |
| new_findings | 0 |
| open_questions | 1 |
| verdict | PASS / READY_FOR_CONTROLLER_FINAL_ADJUDICATION |

---

**AgentDS re-review gate 完成。** 未修改 plan、control、代码、测试、README 或任何其他 artifact。未 stage、commit、push、PR 或运行 implementation tests。等待 Controller 对本 re-review 的最终裁决及 AgentMiMo re-review 结果。
