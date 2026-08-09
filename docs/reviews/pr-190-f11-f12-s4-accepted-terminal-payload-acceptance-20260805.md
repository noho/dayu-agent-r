# PR 190 F11/F12 S4.2 accepted terminal payload acceptance

## Gate result

- Slice：S4.2 production blocker fix
- Baseline：`f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- Controller verdict：`PASS / ACCEPTED_FOR_COMMIT`
- Real-provider observation：尚未重启；旧 bundle 继续保持 immutable / superseded partial evidence

## Accepted contract

完整 `CONTEXT_COMPACTED` canonical payload 继续由 `context_events` 产生和校验；`context_event_payload` 唯一负责把它映射到 EventLog inline 或既有 payload descriptor/blob，并提供严格逆向 resolver。proactive/reactive writer、terminal permit、proactive reconstruction、projection、Memory、compact material、RunInputBuilder 与 public Tool Trace 都从该 resolver 读取同一 durable truth。EventLog inline limit 不变，未删除或截断 canonical 字段。

首轮 review 的唯一 accepted finding `DS-F01` 已在 `DurableCompactArtifactProvider` 真实 consumer boundary 修复；该 provider 在同一 read transaction 内复用严格 resolver。descriptor-backed owner test 锁定 event/artifact/evidence refs、digest 与 corruption fail-closed。

## Review closure

- MiMo 首轮：PASS，但遗漏 `DurableCompactArtifactProvider` consumer。
- DeepSeek 首轮：提出 DS-F01 至 DS-F08。
- Controller 逐项裁决：DS-F01 accepted；DS-F02 至 DS-F08 rejected-with-reason。
- MiMo re-review：PASS，无新 finding。
- DeepSeek re-review：PASS；确认 DS-F01 已关闭，DS-F02 至 DS-F08 的拒绝理由均有当前代码/事务/owner 直接证据。

Durable artifacts：

- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-review-20260805.md`
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-review-20260805.md`
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-review-adjudication-20260805.md`
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-f01-fix-20260805.md`
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-rereview-20260805-234705.md`
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-rereview-20260805.md`

## Validation

- DS-F01 targeted owner test：PASS。
- S4.2 affected regression：798 passed（implementation owner）。
- full Host suite：2425 passed, 2 skipped, 6 deselected（DeepSeek re-review）。
- full-repo pyright：0 errors, 0 warnings, 0 informations。
- changed-file ruff、compileall、`git diff --check`：PASS。
- modified production coverage：82%–92%，新 `context_event_payload.py` 91%，总体 86%。

## Scope and residual risk

- 未修改 `context_events.py`、oracle、scenario 或 registry。
- 未增加 compatibility shim、fallback、loose parser、第二真源或下游补偿。
- 通用 content-addressed artifact 与 SQLite descriptor 的 rollback/GC 生命周期是 pre-existing durable-storage risk，owner 为后续独立 durable-storage work unit；不在 compaction consumer 局部 unlink。
- savepoint retry 与其它 compaction event 的未来 descriptor-backed storage 均不存在于当前 contract；若未来引入，由相应 transaction/event storage owner 同步设计，不预埋兼容路径。

## Next gate

只 stage 本 slice 的 production、tests、README 与 review artifacts，形成 accepted commit 并 push 到 PR 190 现有 head branch。随后从全新 evidence root 重启 S4 real-provider observation；不得回写旧 failure bundle。
