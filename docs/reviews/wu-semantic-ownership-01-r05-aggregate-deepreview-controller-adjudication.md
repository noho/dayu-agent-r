# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Deepreview Controller Adjudication

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，也不是重新打开历史 sub-WU。
- internal remediation sub-WU：R05 wait observation/state-machine ownership。
- R05 entry base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- accepted S1 commit：`c5af5613b21673864fff072a132ac56a46cc9836`。
- accepted S2 commit：`ff7b0b1825491ee3690a45d56a059c5da00af7aa`。
- aggregate product transaction：16 paths，digest `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`。
- aggregate validation：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md`。
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md`。
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md`。
- Controller verdict：`PASS / ZERO_ACCEPTED_CURRENT_FINDING / ZERO-CHANGE FIX RECORD REQUIRED`。

两路 reviewer 都完整审查了 Topic 5 裁决、S1/S2 组合行为、plan supersession、durable construction owner、验证证据、安全保留项和 deferred boundary，均返回 PASS，当前 material finding 为零。按照用户指定的 aggregate `deepreview -> fix -> re-review` 顺序，即使没有产品修复，也必须先由 AgentCodex留下零产品改动 fix record，再经过 Controller 验证和两路 full aggregate re-review；本裁决不授权直接接受 R05 aggregate。

## 2. Finding ledger 裁决

### 2.1 Accepted current findings

无，数量为 `0`。

R05 当前产品 transaction 已满足 Topic 5：provider mode 与 runtime policy 分属配置 owner；Service 不从 scene/name 构造默认 policy；poll/abandon observation timeout 只记录 transient diagnostic、释放 claim 并 backoff；late publication 由既有 token/generation fence 阻断；仅 authoritative typed lost outcome 可进入 LOST；Engine handshake timer 不拥有已接受 awaiting 长事务。

### 2.2 No-fix observations

| observation | Controller disposition | 直接理由 |
|---|---|---|
| DS-AGG-OBS-01：`dayu/host/durable/options.py` 未声明 `__all__` | `NO_CURRENT_DEFECT / NO_FIX` | 当前符号均由精确模块 import 使用，没有 package re-export 或顶层稳定 API 承诺。机械增加 `__all__` 不修复 correctness、ownership 或 public contract，只会制造无依据 diff。 |
| DS-AGG-OBS-02：缺少 scheduler close + poll timeout + late result 跨 owner 压力测试 | `OUTSIDE_R05_OWNER / NO_R05_FIX` | 该组合的未覆盖边界依赖已确认的 scheduler lifecycle 缺口。当前先添加组合测试既不能提供正确 terminal coordination oracle，也可能把独立 scheduler owner 偷带进 R05。它应成为 scheduler residual 修复时的 mandatory verification，而不是 R05 当前测试 shim。 |
| smoke timing margin、单次 backoff cap、Engine 既有 branch coverage | `LOW / NO_FIX` | durable/event 同步提供直接 happens-before，现有总 deadline 有 headroom；smoke 只验证首轮 backoff；Engine production 在 R05 no diff。 |

### 2.3 Retained residuals

| residual | 真实性与分类 | owner / destination | 当前裁决 |
|---|---|---|---|
| scheduler close / terminal promotion coordination | 确定性真实 material bug；但不属于 R05 wait observation owner，且不是 R05 blocker | Host scheduler/lifecycle coordination owner；后续独立显式 work item，umbrella final closeout 必须保留明确入口；不得归 Issue 175 | `RETAINED / UNFIXED / UNWAIVED`。`dispatch.py`、`engine_ingest.py` 与 scheduler tests 不得在 zero-change gate 修改。后续修复必须覆盖 close + promotion + poll timeout/late result 组合验证。 |
| cancelled abandon 在 provider 永不提供 terminal evidence 时长期 capped retry | 真实终止性 residual；R05 正确地没有从 timeout 猜 LOST | future Host durable evidence policy owner；后续显式 contract/design work | `RETAINED / UNFIXED / UNWAIVED`。在 authoritative durable evidence 缺失时不得新增 retry-count/timestamp fallback 或猜测 LOST。 |

### 2.4 Deferred / no-code boundaries

- Issue 175 Fins Docling process isolation：保持既有 owner，本 R05 不实施。
- callback transport：保持 deferred；不得宣传没有 authenticated transport 的 callback mode。
- unified tool authorization / permission schema：不实施。
- R06+、Issues 142/151/177/178：不偷带。
- 现有 token fence、claim CAS、capacity/close deadline、filesystem containment、allowed paths、Web 防御、DNS/peer proof、resource budgets、atomic write 与 process fencing 均不得删除或放宽。

### 2.5 Final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | CLOSED / NO PRODUCT FIX |
| no-fix observation | 3 组 | CLOSED WITH REASON |
| retained residual | 2 | OPEN AT EXPLICIT LATER OWNER；R05 中未修、未 waive |
| blocker | 0 | NONE |

## 3. Controller 复核

Controller 完整读取两份 review artifact 并复核：

1. 两路均以完整 16-path transaction、accepted plan 与全量 S1/S2 evidence chain 为基线，不是只读取摘要；
2. Topic 5 的 config、Service composition、Host timeout transaction、publication fence、typed LOST 与 Engine handshake boundary 组合闭环；
3. `HostDurableStoreOptionsSource` 只定义 durable construction 所需九字段，`project_host_durable_store_options` 是唯一 typed projection，未让下层 import 上层 opener type，也未为 smoke 扩张 public API；
4. plan 中的 private `dropped_count` smoke 和 Ruff `165` 预期分别被已接受 S2 finding 与 touched-file cleanup 合法 supersede；当前 public/durable owner-state proof 与 Ruff `162` 均有完整 review chain；
5. aggregate functional、两组 changed-file coverage、fresh public smoke、full pyright、changed/full Ruff、source/security/no-diff scans 和 deterministic scheduler residual probe 都有 Controller 直接证据；
6. scheduler residual 是真实跨 owner bug，不因本 aggregate PASS 而消失；cancelled long-retry 也未被 timeout-to-LOST shortcut 掩盖；
7. R05 没有实现 Issue 175、callback、统一 authorization 或 R06+。

## 4. Zero-change fix 要求

AgentCodex 只能新增：

`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`

必须：

1. 记录 accepted current finding 为零，因此正确 fix 是零产品改动；不得把 observation 或 residual 擅自升级为 R05 产品修改；
2. 冻结并复算 aggregate 16-path product transaction，证明 path/content digest 仍为 `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`；
3. 记录创建 artifact 前后完整 worktree status，并证明除本 artifact 外，product/test/design/README/control/既有 artifacts 均未变化；不得覆盖两路 review artifact 或本裁决；
4. 复核 `git diff --check`、R05 no-diff owners、timeout-only symbol deletion、private smoke diagnostics、duplicate durable projection、deferred/security source scans；
5. 只引用 aggregate validation 已通过的测试、coverage、pyright、Ruff 与 fresh smoke，不冒充重新运行；
6. 明确两项 retained residual 的 owner/destination、未修/未 waive 状态，以及 scheduler residual 后续 mandatory combination verification；
7. 不 stage、不 commit、不 push，不修改 control，不进入 R06。

## 5. 下一 gate

下一 gate：AgentCodex R05 aggregate zero-change fix record。Controller 验证后，必须进入 AgentMiMo / AgentDS 双路 full aggregate re-review。只有两路 re-review 与 Controller 最终裁决关闭全部当前 findings，并确认 residual/deferred/safety boundary 未漂移，才可进入 R05 aggregate accepted local commit 和 completion gate。

R05、R06-R12 与 umbrella WU 当前均未完成；scheduler fix、Issue 175、callback、统一 authorization、push 与 PR 均未授权。
