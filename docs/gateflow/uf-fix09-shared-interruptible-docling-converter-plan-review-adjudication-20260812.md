# UF-FIX09 plan review 综合裁决

## Gate 元数据

- gate：`plan review adjudication`
- work unit：`UF-FIX09 shared-interruptible-docling-converter`
- controller：`AgentController`
- reviewed baseline：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- frozen plan：`docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-20260812.md`
- frozen plan SHA-256：`3622306371a12de49bbcc50f3c643e09dcd9ab24bcf3b0a4752503ef119ae3af`
- first review：`docs/reviews/plan-review-20260812154406.md`（AgentMiMo）
- second review：`docs/reviews/plan-review-20260812-154453.md`（AgentDS）
- adjudicated at：`2026-08-12T15:49:11+08:00`
- completion status：`PLAN ACCEPTED — READY FOR IMPLEMENTATION SLICE S1`

## Scope 与裁决原则

本裁决只判断冻结 plan 是否已达到 code-generation-ready；不修改生产代码、测试、README 或
oracle/scenario registry。两个 reviewer 基于同一 digest 独立完成，裁决以直接代码证据、根
`AGENTS.md` 的唯一语义 owner/朴素 typed contract 约束，以及用户冻结边界为准。

## Accepted findings：交 AgentCodex 修正 plan

1. **取消输入真源（MiMo F01、DS F01）— accepted。** 删除新的
   `DoclingCancellationInput`。shared converter 直接接收层中立
   `dayu.contracts.cancellation.CancellationToken | None`；direct/durable composite checker
   必须实现该 canonical contract 并从同一个加锁状态派生，不允许 lambda、callback adapter、
   双取消接口或仅为 converter 新增的 wrapper。plan 需列出跨线程可见性及 reason/time 的
   数据来源。
2. **child failure descriptor（MiMo F02、DS F04）— accepted。** child 必须在 target 内分别
   捕获 construction、execution、result serialization 失败，写 exact failure descriptor 后
   正常返回；只有没有可信 descriptor 的 runtime failure、异常退出或 signal crash 映射
   `CHILD_CRASH`。descriptor 本身不能编码时按 IPC/child crash 的可观察事实闭合，不得解析
   exception string。plan 需给出每类产生点、父进程 mapping 与测试。
3. **async bridge 与 cancellation wiring（MiMo F03、DS F03）— accepted。** 明确现有 pipeline
   sync facade 在 producer thread 用其既有 `asyncio.run(async stream)` 建立唯一私有 loop，
   service 不建 loop；async stream `await prepare_upload`，并把同一个 composite
   `CancellationToken` 原样传至 service/converter。说明 `_DirectStreamCancellationState` 的
   `threading.Lock` 是跨线程可见性 owner，禁止新增第二 flag。
4. **publication/terminal first-committer（MiMo F04、F15；DS F06）— accepted。** 明确最后
   pre-commit checkpoint、caller-owned batch rollback、`commit_batch` 成功点、commit exception
   的 unknown/failure 处理；commit 成功后 service/workflow 不再读取 cancel 并必须返回
   completed disposition。direct 与 durable terminal owner 均按该 summary 原子提交，runner
   返回后的 late cancel 不得重解释已提交结果。增加 commit 前、commit 成功后、commit 抛错、
   summary claim 前后 barrier 测试，且明确 rollback 只由 batch owner 执行一次。
5. **可独立通过的 slices（MiMo F05/F06、DS F02）— accepted。** S1 不能删除 protocol 后让
   download workflow broken。重划 S1/S2，使每个 slice commit 的 imports、focused tests、
   pyright 都成立，且最终不保留 compatibility alias/re-export/wrapper。每个既有测试文件的
   修改归属需列清，不允许同一 owner 迁移被拆成不可验证的中间状态。
6. **shared instance 装配（DS F07）— accepted。** 明确 `DefaultFinsRuntime` 在创建 download
   adapter pipeline、CN upload pipeline、SEC upload pipeline 前只构造一次
   `ProcessDoclingConverter`，分别注入；两个 `CnPipeline` 是否仍独立必须写明，但它们必须持有
  同一 converter identity。standalone construction 只能默认构造同一 concrete owner，不能
  形成第二实现。
7. **focused-real conversion-start 证据（MiMo F07）— accepted。** 在不增加测试专用生产 hook
   的前提下，定义可重复的真实 child/conversion sampling protocol，并区分 worker 已 spawn 与
   Docling conversion 已进入；保存 PID/PGID/descendant 与信号时间线。`5.05s` 是冻结的
   signal-to-terminal acceptance budget，必须记录各 cleanup phase，失败不得调高阈值。
8. **terminal status closed mapping（MiMo F08）— accepted。** 列出当前合法 upload summary
   status 到 `COMPLETED/FAILED/CANCELLED` 的 exact mapping 与唯一校验点；禁止
   `strip().lower()`、未知值默认 completed 或 UI 过滤。不要为本 WU 引入与此映射无关的新
   schema。
9. **删除旧 upload conversion seam（MiMo F12）— accepted。** 明确删除
   `DoclingUploadConverter`、`convert_with_docling` 和 `_convert_bytes_with_docling`；仅保留
   upload publication checkpoints 所需的 canonical `CancellationToken`，不保留 callback
   alias。
10. **per-call process state（MiMo F14）— accepted。** 明确每次 convert 调用创建独立 handle、
    temp 与 IPC；shared concrete instance 无 operation 可变状态。该说明只证明 owner 可共享，
    不把同请求并发扩入本 WU。

## Rejected or already-covered findings

1. **MiMo F09 (`fast` mode)** — rejected as non-material。当前 WU 只承诺不漂移的 accurate
   config；plan fix 应删除未被当前 caller 使用的 `fast` 承诺，而不是扩展测试范围。
2. **MiMo F10（upload 不再拿 dict）** — already covered。plan 已规定 child 唯一序列化、
   consumer 只使用 `json_bytes`；可在修订时保留一句明确说明，但不构成独立 finding。
3. **MiMo F11（公开 runtime `error_type`）** — rejected。该字符串不是稳定 Fins 业务语义；
   public error 只保留 closed kind 和 exit code，禁止从 runtime 文本反推分类。
4. **MiMo F13（README 读取顺序）** — already covered。S3 修改前重新读取目标 README 约束即可。
5. **DS F05（CI 抖动）** — no plan expansion。2 秒 harness margin 作为当前 acceptance budget
   保留；真实失败必须按 phase evidence 阻塞，而不是先假定环境问题或放宽。
6. **DS F08（integration test 当前较短）** — rejected as non-material。文件大小不证明测试
   缺口；应按真实 process contract 扩写到足以证明即可。
7. **DS F09（company meta）** — assigned to later work unit。plan 已正确识别为冻结非目标；
   本 WU 只证明 source publication 无半提交，并在 residual risk 中保留该事实。

## Docs decision

本 gate 只修改 Gateflow/review artifacts。实施阶段仍按 plan 与 README 内约束检查
`dayu/fins/README.md`、`tests/README.md`、根 `README.md`；当前没有分层装配语义改变需要修改
`dayu/README.md`。

## Validation

- 两路 review 的 target digest 均与冻结 SHA-256 一致。
- 已读取两份完整 artifact，共 733 行。
- 已交叉核对 `CancellationToken`、direct/durable upload terminal 路径、现有 process runtime
  primitive、plan S1/S2 边界及 UF-PF09 registry 要求。
- 未运行测试/pyright：本 gate 只有文档裁决，implementation 尚未开始。

## Residual risks 与 owner

| 风险 | 分类 | owner / 下一步 |
| --- | --- | --- |
| accepted findings 尚未写回 plan | fixed in current plan-fix gate | AgentCodex |
| 修订 plan 是否消除 slice/terminal 歧义 | covered by plan re-review | AgentMiMo + AgentDS |
| company meta 先提交 | assigned to later work unit | company-meta refresh work unit |
| 非 POSIX descendant group guarantee | assigned to later work unit | runtime platform work unit |
| UF-PF09 真实机器 timing/model 行为 | covered by approved S3/final validation | AgentController |

## Completion

当前无须用户决策的 blocking question。AgentCodex 已只修改同一 plan，落实上述 10 组
accepted findings；修订后 plan 为 936 行，SHA-256 为
`c95e01ac34f6482e17f6d2de1a8e9f65d8b90506ab02097c8ad2d8c4b1b83e71`。AgentCodex 与总控均复核
`git diff --check` 无告警，且没有生产代码、测试、README 或 registry 变更。下一步须以该新
digest 同时交两路 reviewer re-review；在 accepted finding 全部闭环前不得创建 plan acceptance
commit。

## Re-review acceptance

- AgentMiMo re-review：`docs/reviews/plan-review-20260812-160847.md`，结论 `pass`，accepted
  finding closure `10/10`，new material finding `0`，unresolved `0`。
- AgentDS re-review：`docs/reviews/plan-review-20260812-160907.md`，结论 `pass`，accepted
  finding closure `10/10`，new material finding `0`，unresolved `0`。
- 两路均校验 frozen revised plan SHA-256
  `c95e01ac34f6482e17f6d2de1a8e9f65d8b90506ab02097c8ad2d8c4b1b83e71` 一致，且没有读取对方
  本 gate 新 artifact 后再改变输入。
- 总控额外核验 `BatchingRepositoryProtocol.commit_batch/rollback_batch` 已存在于
  `dayu/fins/storage/repository_protocols.py`，不存在 reviewer 记录的潜在 storage capability
  blocker。
- 最终裁决：plan 已达到 code-generation-ready；无未分类风险、blocking question 或未闭环的
  accepted finding。下一 gate 为 AgentCodex implementation slice `UF-FIX09-S1`。
