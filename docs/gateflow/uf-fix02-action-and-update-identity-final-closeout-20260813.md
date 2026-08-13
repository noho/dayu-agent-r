# UF-FIX02 action-and-update-identity — Final Closeout

## Closeout decision

**FINAL CLOSEOUT PASS（仅修复范围）。**

本 work unit 完成 filing identity / action resolution / published-deleted state / complete-set replacement 的
owner-boundary 修复、tests-first 实现、双路 plan review、双路 slice review、双路 aggregate deepreview、README
同步与本地提交。没有创建 PR、push、切换 main、merge 或更新远端。

## Accepted implementation

- explicit `update` 必须命中 existing filing identity；`overwrite` 不授予 upsert。
- logical deleted source 不可被 fingerprint skip；`auto` 用完整输入重新发布 active source。
- existing full-input update 与 create-overwrite 在同一 caller-owned batch 中执行 exact identity
  reset → blob-first → final create，形成 old-or-new 的完整文件集合替换。
- reset 前 source meta 是 version、`first_ingested_at`、`created_at` 的唯一派生真源。
- strict canonical `is_deleted` 读取收敛到 `dayu.fins.storage.require_source_meta_is_deleted(...)`，snapshot
  与 upload consumer 复用。
- SEC / CN / HK workflow 继续以 fresh authoritative request 驱动 prepare；可预判冲突在 Docling conversion
  与 batch mutation 前 fail closed。

## Review status

- Plan review：AgentMiMo / AgentDS 双路 PASS。
- S1 / S2 code review 与 re-review：双路 PASS；accepted findings 全部闭环。
- Aggregate deepreview：
  - `docs/reviews/code-review-uf-fix02-aggregate-mimo-20260813.md`：PASS。
  - `docs/reviews/code-review-20260813-191952-uf-fix02-aggregate-ds.md`：PASS。
- 没有未关闭的 correctness / stability / maintainability finding。

## Final verification

- owner / boundary focused：`321 passed, 3 warnings`。
- UF-FIX01 / storage atomicity / cancellation regression：`343 passed, 3 warnings`。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- 已接受的逐修改生产文件 coverage：
  - `docling_upload_service.py`：`87%`；
  - `ingestion_runtime.py`：`90–91%`；
  - `source_meta_contract.py`：`100%`；
  - `storage/__init__.py`：`100%`；
  - `_fs_source_snapshot.py`：`86%`。
- `_resolve_upsert_mode` 在 Python 源码零命中；无 compat shim。
- frozen digests 保持：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`；
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- `docs/host/design.md`、`docs/engine/design.md`、frozen evidence 与 registry 均未修改。

三条 warning 均来自既有 edgar deprecated import，不是本 work unit 引入。

## UF-PF02 scope correction

按用户最新 scope，UF-PF02 focused-real 不属于本次 AgentController 任务，**未执行**，移交主 Agent 在修复
完成后单独执行。本次尝试只产生过一个未执行的 `workspace/tmp/uf_pf02_focused_real.py` skeleton 与对应
`.pyc`；二者已精确删除。没有创建 evidence root、真实 CLI observation、manifest、report、digests、
completion 或 secret scan，也没有更新 frozen evidence / oracle / scenario registry。

## Residual risks

- source corruption / broader deleted-state repair：UF-FIX08。
- multi-file primary / collision：UF-FIX07。
- fresh read 到 publication 的 same-request race：UF-FIX10。
- material create-existing typed admission：后续独立 material action-contract / UF-PF12。
- UF-PF02 focused-real：移交主 Agent，尚未执行。
- frozen conformance registry refresh：后续统一执行。

以上 residual 均有明确 owner，未由本 diff 新增或恶化。
