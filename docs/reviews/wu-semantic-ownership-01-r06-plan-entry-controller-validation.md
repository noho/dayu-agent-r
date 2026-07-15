# WU-SEMANTIC-OWNERSHIP-01 R06 plan-entry Controller validation

## 1. Gate identity

- active work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：R06 Fins 显式 transaction 与完整 source 发布。
- transition base：`9c07b88d9e855f19f0b828f671022119cc5599a1`。
- plan artifact：`docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`，共 563 行，SHA-256 为 `f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`。
- 本记录只裁定是否进入双路 plan review；不接受计划，不授权 implementation、stage、commit、push 或 PR。

## 2. Motivation and owner validation

动机成立，严重性没有被高估。Controller 重新核对当前生产代码后确认：

1. public `BatchToken` 暴露 owner/task-scope 与物理 path；mutation 实际 authority 却来自 `ContextVar`、当前 task/thread 和 `_require_batch_owner()`，显式 token 与 ambient identity 同时拥有同一写权限事实；
2. `_execute_with_auto_batch()` 允许 mutation 在无 token 时自动开事务，也允许通过 ambient owner 加入已有事务；
3. Source protocol 重复声明 batch lifecycle，全部业务 mutation protocol 缺少 required `batch=`；
4. `stage_source_document()`、`ingest_complete=false`、blob 前置 meta acknowledgement 与 producer stable re-entry 共同把 transaction staging 泄漏进正式 source 业务 schema；
5. 当前 `target -> backup -> staging -> target` 两次 rename 存在真实在线 target 缺失窗口，journal recovery 不能替代在线 reader 可见性证明。

这些证据与 Controller discussion Topic 6.1/6.2 及 `docs/fins/design.md` 直接一致。唯一 semantic owner 是 `dayu.fins.storage`：显式 token 拥有 transaction authority，storage core 拥有 active state、staging、完整性校验、publication 与 recovery；producer 只拥有 publication unit 边界和完整业务输入。

## 3. Plan completeness validation

Controller 已完整读取最终 563 行计划并确认其已具备进入对抗性 review 的最低闭环：

- public token 精确收窄为 opaque transaction identity 与 ticker，active state、路径、lock、journal phase 留在 storage internal state；
- begin/commit/rollback 只由 `BatchingRepositoryProtocol` 声明，所有业务 mutation 使用 keyword-only、non-optional `batch: BatchToken`，无 optional/default/ambient/compat seam；
- writer transaction/ticker mutex 与短时 publication swap guard 已分离：长下载、Docling、staging 和 validator 不阻塞 published read，commit/recovery physical swap 短窗才阻塞一次 published materialization/open；
- complete-source validator、blob-first staging、一次 final source mutation、old/new crash invariant 和 `ingest_complete=false` 删除边界明确；
- 当前 CN/SEC/Docling/rebuild/company/maintenance producer、callback 与 composition root 已逐条枚举；
- S1/S2/S3 被明确为同一 breaking cutover 的累计代码生成顺序，不允许把中间不完整 tree 当成 deployable/green，也不引入兼容 commit；
- focused/full tests、逐 changed production file `>=80%` coverage、full pyright、scoped/full Ruff、diff/source/security scans、真实 filesystem crash/online-reader smoke、README decision、stop condition 与 R07 handoff均有明确 gate；
- R07 snapshot/revision/opaque identity、R08-R11、Issue 142/151/175/177/178、统一 authorization 与旧 schema compatibility 均未被授权。

Controller 独立复核当前 base：full pyright 为零；full Ruff statistics 为 162 个既有错误，和计划记录一致。当前 plan gate 只有 plan artifact 与本 validation/control artifact 写入，产品、测试、README、design truth 均无 diff。

## 4. Allowlist refinement adjudication for review

计划基于当前真实调用图提出了 umbrella R06 row 之外的窄化候选：

- `dayu/fins/storage/local_file_source.py`：让一次 `Source.open()` 在 publication swap guard 内成功打开稳定 fd；
- `dayu/fins/service_runtime.py`：production shared repository set / batching composition；
- `dayu/fins/downloaders/sec_downloader.py`、`cn_download_protocols.py`、CN/SEC pipeline facade、download/upload workflow/state：显式 batch callback 与 top-level lifecycle propagation；
- processor/read consistency 与 SEC downloader 等直接 owner tests：证明 online rename barrier、签名迁移和 callback token propagation。

这些候选均有直接调用链证据，若一律拒绝会迫使实现保留 Source lifecycle facade、captured batch closure、ambient lookup 或无法通过类型检查。因此 Controller 接受把它们交给双路 plan review 挑战，但此处不提前接受为 implementation allowlist。reviewer 必须逐项证明它是 required minimal set；任何无直接 mutation/composition/read-open 证据的路径都应从计划删除。

## 5. Mandatory adversarial review questions

双路 reviewer 除完整 plan review 外，必须明确回答：

1. publication swap guard 如何在多 core / 多进程下共享同一 owner，同时避免 public read 互相嵌套时对非 reentrant file lock 自死锁；guard 应只存在于最外层 materialization，还是需要清晰的 guarded/unguarded helper boundary；
2. `LocalFileSource.open()` 的 stable-fd 方案与仍返回 path 的 `materialize()` 是否形成未声明缺口；若后者确属 R07 长生命周期 snapshot，计划必须准确写明 residual，不能同时声称 R06 已覆盖所有 Source read；
3. complete-source validator 的 staged-tree/manifest 闭包是否由当前 schema 与 storage owner 直接支撑，是否存在 producer/read/test 重复判定或无业务依据的 mandatory rule；
4. CN/SEC upload + Docling transaction 边界是否已经 code-generation-ready，计划中不得留下“implementation 再裁决”的开放产品/owner条件；
5. S1/S2/S3 累计 breaking cutover 是否与 phaseflow review/验证步骤一致，是否存在不可审的超大 diff，或反向要求 optional/default/compat 中间态；
6. 新增 production/test allowlist 是否完整且最小，callback 是否把 batch 作为显式实参而不是 closure capture；
7. plan 内 baseline snapshot 是否只消费总控唯一 baseline 机制，changed-file lint hygiene 是否会产生与 R06 无关的清理 churn。

## 6. Verdict

`PASS / READY_FOR_DUAL_PLAN_REVIEW`

计划尚未 accepted，implementation 尚未授权。下一 gate 是 AgentMiMo / AgentDS 对同一 immutable plan target 做并发完整 plan review；所有 finding 仍须由 Controller 逐项裁决。
