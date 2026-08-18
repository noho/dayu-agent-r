# UF-FIX09 Aggregate Deepreview 裁决

## Gate

- Gate：aggregate deepreview
- Base：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- 冻结 target：`d40ac173fd308b3329ed7216e0c26b9951663cdc`
- 冻结 base..target diff SHA-256：`2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`
- AgentMiMo：`docs/reviews/uf-fix09-aggregate-deepreview-20260812-221109.md`
- AgentDS：`docs/reviews/code-review-20260812-220949.md`

## Findings 裁决

### R1 — 不接受为 finding：partial batch cancellation 已由唯一 publication owner 完整回滚

- 来源：AgentDS AGG-01。
- 裁决：rejected as observation；不是 residual risk。
- 直接证据：所有 source/file 写入均绑定同一 batch；`publish_prepared_upload` 只负责准备并返回 typed summary，唯一生产 caller 通过 `commit_prepared_upload_batch` 接管 terminal lifecycle。cancelled summary 在该 owner 内触发同一 batch rollback，且现有 deterministic tests 覆盖 rollback 与 residue。
- 理由：finding 本身也确认实际行为正确。假设未来新增绕过唯一 owner 的 caller 不构成当前缺陷；仓库级 caller inventory 已证明当前不存在该路径。

### R2 — 不接受为新 finding：callable transport 与 canonical token 收窄是冻结 plan 已裁决的显式 trade-off

- 来源：AgentDS AGG-02。
- 裁决：rejected as duplicate of S2 R1；不是 residual risk，不修改代码。
- 直接证据：accepted plan §11.1 明确 adapter request 中运输的是同一个 `FinsJobCancellationChecker` concrete object，它同时满足普通 workflow checkpoint 所需的 callable contract 与 converter 所需的 `CancellationToken`；进入 converter 前由 `_canonical_cancellation` fail-closed 收窄并原样传递 identity。S2 初轮 finding、controller 裁决和双路 re-review 已完整审查并接受该设计。
- 理由：共享 download transport 同时服务 SEC（只需要 callable）和 CN/HK（转换时需要 canonical token）。Python 类型系统没有交集类型；把共享字段标成 `CancellationToken` 会丢失 `__call__` 静态契约，标成 ingestion-owned `FinsJobCancellationChecker` 会造成 pipeline 对上层 runtime owner 的反向依赖。当前实现没有 adapter、fallback、第二取消源或 identity 替换，纯 callable 在 converter 边界被明确拒绝，契约是 fail-closed 而非 loose compatibility。

## 共同结论

- 两路均确认唯一 Fins Docling converter owner、依赖方向、旧 CN runner 删除、全部当前 Fins caller 迁移、immutable bytes、child construction、closed IPC outcome、process-group terminate/grace/kill/reap/close、download 行为、upload filing/material 共用、publication first-committer、direct/durable terminal、SIGINT canonical cancelled、类型与 README 均符合 accepted plan。
- process/read 只消费已发布 Docling JSON，不构造或调用 converter；本 work unit 已做读取一致性回归，生产迁移不适用。
- Web fetch 仍直接使用 `dayu.documents.docling_runtime`，没有 Fins cancellation token，也不能反向依赖 Fins owner；按 accepted plan 有直接证据归入 later work unit。

## Validation

- Slice 级最终影响矩阵：`525 passed`。
- 真实 Docling integration：`1 passed`。
- 全量 pyright：`0 errors, 0 warnings, 0 informations`。
- 修改 owner `ingestion_runtime.py` coverage：`91%`；shared converter：`95%`；其它显著修改 owner：`86%–95%`。
- 旧 runner/旧 symbol：零生产残留。
- `git diff --check`：通过。

## Docs Decision

- 根 `README.md`、`dayu/fins/README.md`、`tests/README.md` 已按职责做最小更新。
- 分层与装配关系未变化，不更新 `dayu/README.md`；Host/Engine/config 生产目录未改，不更新其 README。

## Residual Risks

- `fixed in current slice`：S1/S2/S3 所有 accepted findings 已修复并通过原 reviewer re-review。
- `covered by later approved gate`：UF-PF09 fresh evidence 与 final validation。
- `assigned to later work unit`：company meta 独立事务、Web fetch cancellation、非 POSIX descendant governance、格式/help/XBRL/multi-file 等冻结非目标。
- `requiring user decision`：无。
- 未分类风险：无。

## Completion Status

两路 aggregate deepreview 均无需要修改的 material finding。AGG-01 是当前正确 rollback 行为的未来调用方观察；AGG-02 是 S2 已裁决并冻结在 plan §11.1 的同一类型 trade-off。

AgentCodex 已在 `docs/gateflow/uf-fix09-aggregate-fix-confirmation-20260812.md` 完成 no-op fix confirmation：冻结 target 与 digest 不变，focused owner tests `4 passed`，focused pyright `0 errors`，无生产代码或测试修改。

同一冻结 target 的双路 aggregate re-review 已完成：

- AgentMiMo：`docs/reviews/uf-fix09-aggregate-rereview-20260812-222742.md`，无 finding，确认 R1/R2 裁决与全部 accepted finding 闭环。
- AgentDS：`docs/reviews/code-review-20260812-222603.md`，无 material finding，确认 R1/R2 no-op 裁决及 cross-slice completeness。

Aggregate deepreview gate accepted。无 blocking question、accepted finding、未分类风险或 requiring-user-decision 项；下一入口为 accepted deepreview commit，随后执行 UF-PF09 与 final validation。
