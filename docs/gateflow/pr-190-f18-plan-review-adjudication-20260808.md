# PR 190 F18 Plan Review Adjudication

## Gate decision

- Work unit：F18。
- Gate：`plan-review`。
- Reviewed plan：`docs/gateflow/pr-190-f18-plan-20260808.md`。
- Independent reviews：
  - `docs/reviews/plan-review-20260808-145152.md`（AgentDS，`fail`）；
  - `docs/reviews/plan-review-20260808-145239.md`（AgentMiMo，`fail`）。
- Controller verdict：`fail`，全部四组 material finding 接受；plan 返回 AgentCodex 修订，修订后必须由两路原 reviewer
  独立 re-review。

本裁决不授权产品修改、真实 provider 调用、B2 observation、B2 裁决、提交或推送。

## Controller direct verification

Controller 没有用 reviewer 自报替代直接核验，已确认：

1. `docs/host/design.md` 只把 context / memory / compactor policy 定义为单个 `open_host` 的 construction-time
   inputs，并冻结同一 Host handle 内的 per-Run override 闭集；当前 public Session、slot、attach 与 durable schema 中没有
   Session-level execution-profile / memory-policy manifest，也没有跨 opener mismatch rejection。Trial2 的 profile transition
   合法性当前是 **unspecified**，不是已证明 illegal 或 supported。
2. Trial2 唯一物理 SQLite 已推进到 sequence 327。segment11 `sqlite-before.json` 虽记录 command 前 EventLog count
   `324`，但只是 selected typed rows export，不包含完整 payload、idempotency、projection checkpoint、outbox、audit 与 runtime
   state，因此不是 transaction-consistent restore source。外部 evidence root 中没有 sequence 324 的 physical SQLite backup，
   也没有当次 `candidate_source_failed` logger/traceback capture。
3. 原 immutable DB 与 synthetic sequence-326 clone 上，使用 production assembly、当前 constrained memory policy 及 13 个
   production tool schemas直接调用 candidate owner，结果均为 `candidate_prepared`。这只反证“现存空 constrained snapshot
   必然导致 candidate failure”，不能恢复或证明原 sequence 327 的具体 cause。
4. sequence 325 的 durable tool truth 是 `USER_INPUT_ACCEPTED.effective_tool_set`：exact tool names、business bundle
   digest、effective schema digest、source refs、display names 与 tool snapshot ref。该 Run 在 Attempt/manifest 之前失败，
   segment11 不存在 runner-call manifest；plan 不得引用不存在的 source of truth。
5. B1 public evidence 已有冻结 digest：observed report
   `de7ee64de11140add816facf9926c2cf17aa13a4176bd873bc0f91ed20b70f79`、observation summary
   `dfe3604bba8c7f8bda6b0d8a80639a87ac77a2d1c03f0e7baa28236e554d7c0a`、public digest manifest
   `567d5539d9e745e78379093117275231c7b96ab5ac03536f13aec9475e476153`、secret scan
   `6f33e30ced5dbbcc96c6cadcc93bf1c5c2ad3d261c5f3386ccbec74c3ba52ba8`。B1 scenario 更新必须只投影
   report/summary 中的 B1 section 与 B1 public Tool Trace refs；不得把同一 mixed bundle 中的 B2 refs 当作 B1 accepted
   evidence。

## Finding adjudication

### F18-PA-01 — Session 跨 opener profile contract 未定义

- 来源：DS-F18-PR01、MIMO-F18-PR-001。
- 裁决：`accepted`，严重程度 `high`。
- 理由：handle-level construction freeze 不能外推成 Session-level durable freeze。fixed-profile fresh observation 是用户已要求的
  正式 setup，但不能反向证明 Trial2 setup illegal。
- plan 修复：删除 setup-illegal 预判；把 cross-opener transition 明确登记为 unresolved contract question。若后续要支持、拒绝或
  新增 Session-level typed manifest，必须重新 goal/design confirmation，本 F18 不暗中扩 contract。

### F18-PA-02 — 原 sequence 324/326 exact replay 不可实施

- 来源：DS-F18-PR02、MIMO-F18-PR-002。
- 裁决：`accepted`，严重程度 `high`。
- 理由：没有 point-in-time consistent physical snapshot 或原 logger；SQL rollback clone 和 fresh public follow-up 都是
  counterfactual experiment，不能承载原异常的因果裁决。
- plan 修复：删除“完整治理重放可解锁”的 hard gate。保留既有 direct owner experiments，但必须标记其证明边界。F18 的
  root-cause verdict 固定为 `blocked-by-non-recoverable-owner-cause-evidence`；不得增加猜测性产品修复或公共 typed cause，
  不得执行真实 B2 provider observation。

### F18-PA-03 — 工具真源、B1 evidence identity 不精确

- 来源：DS-F18-PR03、MIMO-F18-PR-003。
- 裁决：`accepted`，严重程度 `medium`。
- 理由：不存在 target Run runner manifest；B1 mixed report 不能被整体解释成 B1-only accepted evidence。
- plan 修复：工具重放证据改为 sequence 325 `effective_tool_set` 与 runtime fail-closed validation；B1 slice 冻结上节四个
  public digest 与 B1-only relative refs，并逐字段断言 B2 scenario 的 status、adjudication identity、applicable identity 与
  overall readiness 不变。

### F18-PA-04 — 正式观察计划不够 bounded、不可直接执行

- 来源：DS-F18-PR04、MIMO-F18-PR-004。
- 裁决：`accepted`，严重程度 `high`（当前 work unit），修复风险 `low`。
- 理由：在 root-cause gate 已因不可恢复证据关闭后，继续细化或运行三条真实链没有授权基础，也会消耗 provider 而不能满足用户
  的 sequencing 约束。
- plan 修复：当前 F18 删除正式 observation execution slice；只把三链 matrix、provider budget、precondition、stop/seal 与
  publication requirements记录为 blocked follow-up input，不在本 work unit 运行。B2 保持 `unadjudicated`，overall readiness
  保持非 ready。

## Required revised plan

修订 plan 只能包含两个可执行 slice 与一个 blocked closeout：

1. **B1 adjudication projection**：按已有 accepted record 方式更新 scenario、Oracle history/summary、CLI CI handbook 与
   adjudication report；绑定精确 public digest/B1-only refs；保留 cold analyzer 与 provider request id limitation；不改变 B2 或
   readiness。
2. **F18 owner investigation closeout**：把 immutable typed state、direct owner replay反证、缺失的原 logger/consistent snapshot、
   cross-opener contract unspecified 与禁止推断的结论写入 tracked、脱敏、人类可读 root-cause report。产品代码、schema、测试与
   observation tooling均保持零改动。
3. **Blocked B2 closeout**：implementation verdict 可以是 B1 docs/registry change accepted；real observation verdict 必须是
   `not-run-root-cause-gate-closed`；B2 Oracle status 保持 `unadjudicated`，overall readiness 保持非 ready。不得把 blocker 写成
   product pass 或 scenario pass。

修订后若两路 plan re-review 通过，才可进入上述文档/registry implementation；本 work unit 不再尝试恢复原异常或运行真实
provider。
