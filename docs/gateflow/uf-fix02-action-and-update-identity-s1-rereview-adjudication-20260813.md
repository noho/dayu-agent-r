# UF-FIX02 action-and-update-identity — S1 Re-review Adjudication

## Gate context

- Gate：`S1 re-review adjudication`
- Accepted plan commit：`56d159cb4bf13baf82858bb237b2f73075eaf717`
- AgentMiMo review：`docs/reviews/code-review-20260813-192100-uf-fix02-s1-rereview-mimo.md`
- AgentDS review：`docs/reviews/code-review-20260813-182233-uf-fix02-s1-rereview-ds.md`

## Controller decision

**S1 ACCEPTED。**

两路独立复审都给出 `PASS`。DS-02、DS-03、DS-04 已按首轮裁决关闭；DS-01 保持
`deferred-with-owner`，当前 diff 未新增或恶化 material action-contract 缺口。

## Evidence accepted

- S1 focused suite：`428 passed, 3 warnings`。
- UF-FIX01 regression suite：`343 passed, 3 warnings`。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- 修改生产文件 coverage：`ingestion_runtime.py 91%`、`docling_upload_service.py 86%`、
  `storage/__init__.py 100%`、`_fs_source_snapshot.py 86%`、
  `source_meta_contract.py 100%`。
- frozen registry/design no-touch 与 `git diff --check` 均通过。

## Review finding adjudication

### DS re-review Finding 1：根 README 尚未描述 update/overwrite 用户语义

- Decision：**accepted，deferred to S2 closeout**。
- Severity：低；不阻塞 S1 correctness acceptance。
- Reason：S1 已改变最终用户可见的 missing-update 行为，故“根 README 不触发”的原判断不成立；
  approved plan 的 README trigger 应执行。为避免在 S1 写入半套 action 语义、随后在 S2 再次改写，
  根 README 由 S2 closeout 一次性说明：explicit update 要求 existing target、overwrite 不提供 upsert、
  auto 对 logical deleted source 的恢复，以及 update 的 complete-set replacement。
- Owner：S2 implementation / final README gate。
- Required verification：S2 code review 必须把根 README 更新作为 blocking checklist；未更新则 S2 不得
  accepted。

## Residual ownership

- material create-existing typed admission：后续独立 `upload_material action-contract` work unit。
- complete-set replacement 与 `_resolve_upsert_mode` 删除：S2。
- loose deleted reader / corruption repair：UF-FIX08。
- same-request fresh recheck race：UF-FIX10。
- multi-file primary/collision：UF-FIX07。
- frozen UF-A08 evidence refresh：后续统一 conformance refresh。

无未分类 residual risk，无 Gateflow stop condition。下一 gate：`S1 accepted commit`，随后进入 S2。
