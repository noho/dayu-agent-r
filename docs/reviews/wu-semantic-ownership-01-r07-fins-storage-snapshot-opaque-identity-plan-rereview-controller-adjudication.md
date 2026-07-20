# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Re-Review Controller Adjudication

## 1. Immutable target 与 verdict

- fixed plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- immutable SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
- AgentMiMo re-review：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-mimo.md`，SHA-256 `c596afbbe267ce2431e733c85a32c21cdb00356598e9ba3e166bc0fa9070faa8`
- AgentDS re-review：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-ds.md`，SHA-256 `02d661c2ec95206a31e51ea0a6c9d3624d303577f33d1a143f0d0065499eb732`
- Controller fix validation：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-controller-validation.md`

两路均对 fixed plan 全文和当前代码证据完成 complete re-review，结论均为 `PASS`，共同确认 `R07-PF-01..12` 全部关闭、0 个新 material finding、0 blocking question。Controller 最终裁决：**PASS / R07 PLAN ACCEPTED FOR EXACT-SCOPE LOCAL COMMIT**。

这只接受 R07 plan gate，不接受 implementation，不关闭 R07 或 umbrella，不授权 R08—R12、deferred Issue、统一 authorization、push 或 PR。

## 2. 原 findings 最终 ledger

| original finding | final disposition |
|---|---|
| MiMo `R07-PR-F01` | **CLOSED by R07-PF-01**：逐文件 line coverage 改用 `covered_lines / num_statements`。 |
| MiMo `R07-PR-F02` | **CLOSED by R07-PF-02**：只删除 `QueryDiagnosis` / `SEARCH_MODE_AUTO`。 |
| MiMo `R07-PR-F03` | **REJECTED WITH DESIGN EVIDENCE**：source repository 拥有 source kind；optional 0/1/2 typed storage resolution 替代 consumer filing-first guess。 |
| MiMo `R07-PR-F04` | **CLOSED by R07-PF-03**：S2 breaking `digest -> token`，无 compat/SHA grammar。 |
| DS `F-R07-DS-01` | **CLOSED by R07-PF-04**：lock stem 只发现 private candidate；business ticker 只从 descriptor 恢复。 |
| DS `F-R07-DS-02` | **CLOSED by R07-PF-05**：maintenance 先恢复 exact external id，再做业务规则。 |
| DS `F-R07-DS-03` | **CLOSED by R07-PF-06**：revision 未变时 fd/content/fstat 异常立即 corruption fail closed。 |
| DS `F-R07-DS-04` | **CLOSED by R07-PF-03**：token type 与临时 `get_source_revision` 时序一致。 |
| DS `F-R07-DS-05` | **CLOSED by R07-PF-07**：SEC 只换 snapshot path owner，existing filename selection 不变。 |
| DS `F-R07-DS-06` | **CLOSED by R07-PF-08**：creation lock 内 double-check 与 losing snapshot close。 |
| DS `F-R07-DS-07` | **CLOSED by R07-PF-09**：9 tools completed/failed/cancelled/citation runtime JSON recursive test。 |
| DS `F-R07-DS-08` | **CLOSED by R07-PF-10**：delete/reset snapshot absence storage-owner test。 |
| DS `F-R07-DS-09` | **CLOSED by R07-PF-11**：list-only 两个 typed projections，无 N+1/batch API。 |
| Controller process finding | **CLOSED by R07-PF-12**：S3 complete-tree review 与 umbrella aggregate deepreview 不重复、不遗漏。 |

DS 三个 open questions 也已关闭：S2 删除 field hash builder；blob-first 在首 payload 前创建/验证 descriptor；cross-document diagnosis 只处理 cached candidate。

## 3. 新 observations 裁决

### MiMo `R07-RR-F01` — no-action design confirmation

该条没有反例，只复述 Controller 已拒绝的 required-source-kind 方案。fixed plan 的 typed 0/1/2 storage resolution 与 `docs/fins/design.md` 的 source repository owner一致；不产生 fix 或 residual。

### DS `NEW-OBS-01` — no additional plan fix

`_remove_manifest_items` 当前调用 `_normalize_document_id`，但它不是未覆盖路径：

1. plan §3.2 已把 7 个 storage 文件 / 115 个 `_normalize_ticker/_normalize_document_id` 命中列为 S1 全量分类对象；
2. `_fs_storage_infra.py` 在 S1 exact production allowlist；
3. §7.1 step 4 覆盖 maintenance cleanup 完整调用链，step 5 明确删除旧 `_normalize_document_id` contract；
4. §8.3 source scan 要求所有残留逐项分类，§8.2 full pyright 必须 0；
5. 该 helper 只需对 manifest 已持有的 exact external id 做 exact comparison，不引入新 owner、contract、file 或测试边界。

因此它是 implementation checklist observation，不是 plan 缺陷。S1 implementation handoff、Controller validation和双路 cumulative review必须显式核对该调用已迁移；不得把遗漏留到后续 slice，也不得保留 normalizer shim。

## 4. Accepted plan boundary

Accepted plan 固定以下 implementation truth：

- S1：storage-owned opaque external identity ↔ private locator mapping 覆盖 target/staging/backup/locks/recovery/company/source/blob/processed/rejected/maintenance/manifest；fresh schema，无 migration/fallback。
- S2：storage complete publication owner产生 persisted opaque token并返回同源 stable snapshot；bounded retry只处理真实 publication change，静态损坏保持 typed corruption。
- S3：read/cache/citation只消费 snapshot，resource borrow/retire/close闭合；删除 hash/double-read/provider guess；list-only不做 N+1。
- containment、symlink、filename/local URI、atomic write/fsync、writer/publication lock、journal/recovery、typed provenance/citation/read errors全部保留。
- SEC fiscal 只迁移 snapshot source，不改变 financial/XBRL业务推断；R08及后续 owner不提前实现。
- S1/S2 是未提交累计 checkpoints；S3 complete-tree双路 final code review通过后才有一个 R07 accepted implementation commit。跨 R01—R12 aggregate deepreview仍在所有 remediation sub-WU 后执行。

## 5. Exact accepted-plan commit closure

本 gate 的 accepted local commit 只允许下列 11 个路径：

```text
docs/host/issues-implementation-control.md
docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md
docs/reviews/wu-semantic-ownership-01-r07-plan-entry-controller-validation.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-mimo.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-ds.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-codex.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-controller-validation.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-mimo.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-ds.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-controller-adjudication.md
```

Commit 前必须再次确认 fixed plan SHA、全部 untracked artifact whitespace、staged exact paths 与 staged `git diff --check`。不得混入 product/tests/README/design/old artifact/`workspace/tmp`。

Accepted-plan commit 后必须用单独 control transition 记录实际 SHA，再派发 R07-S1 implementation；不得用预期 SHA 冒充 accepted commit。
