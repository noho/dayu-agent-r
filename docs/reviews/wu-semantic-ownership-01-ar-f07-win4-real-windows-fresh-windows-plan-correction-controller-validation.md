# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW Fresh Windows Plan Correction Controller Validation

## Verdict

`PASS / WIN4-RW-RF01 PLAN-CORRECTED / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`

## Inputs

- Controller evidence adjudication: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-evidence-controller-adjudication.md`
- AgentCodex correction artifact: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-codex.md`
- Corrected plan: `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
- Baseline plan SHA-256: `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`
- Corrected plan: `1124` lines / SHA-256 `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`
- AgentCodex artifact: `134` lines / SHA-256 `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb`

## Controller Checks

1. Root cause与remote evidence同源：两个fresh run的唯一共同失败确实位于同一test assertion，并发生在process exit、company meta、唯一filing id、snapshot identity/source kind与nonempty descriptors通过之后。
2. Fins owner证据成立：`DoclingUploadService`发布raw与Docling entries并选择Docling JSON为`primary_document`；public snapshot投影该Fins truth。Corrected plan没有把当前具体Docling filename升级为未来contract。
3. Public consumer足够：`SourceSnapshotFileDescriptor`公开`name`与`sha256`；target node已有`hashlib`、fixture bytes、source path与descriptors，无需新helper/import/schema/oracle字段或private path。
4. Corrected owner split成立：primary只要求exact name唯一命中descriptor；raw source只要求exact basename唯一descriptor且public SHA-256匹配fixture bytes。两者明确允许不同。
5. Scope精确：未来implementation只允许`test_windows_generated_script_runs_real_cli_into_temp_storage`现有snapshot assertion block；product/Fins/storage、其它tests、README、design、workflow、control与oracle JSON block全部冻结。
6. Propagation完整：owner contract、allowed/forbidden path、one-slice sequencing、negative cases、validation/scans、README decision、fresh rerun、diagnostic-first stop与completion report已一致修正。
7. Security/deferred/no-code边界不变：R12 canary contract、trusted-local Config/Host durable state、Tool Trace/audit/public/LLM/operator non-disclosure、Gemini quota与Issue 142/151/175/177/178均未改写。

## Fresh Validation

- `git diff --check`: pass。
- Full pyright: `0 errors, 0 warnings, 0 informations`（AgentCodex fresh）。
- Old-error wording scan: zero。
- Hardcoded expected Docling primary scan: zero。
- Product/test/README/design/workflow hashes: unchanged。
- Controller control/evidence files: not overwritten。
- Staged tree: empty。

## Finding State

- `WIN4-RW-RF01`: `ACCEPTED / PLAN-CORRECTED / IMPLEMENTATION-OPEN`。
- Product defect: `0`。
- Design contradiction/open question: `0`。
- Current local blocker: `0`。
- AR-F07 release blocker: remains until corrected implementation、review/aggregate gates与fresh clean R11/R12 closure。

只授权AgentMiMo与AgentDS并发完整review corrected plan和全部直接 owner evidence。Implementation仍未授权。
