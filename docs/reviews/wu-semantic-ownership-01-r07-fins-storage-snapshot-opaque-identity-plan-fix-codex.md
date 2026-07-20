# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Finding Fix — AgentCodex

## 1. Gate、输入与结论

- 工作单元：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 sub-WU `R07`，不是新 WU。
- 当前 gate：accepted plan finding fix 完成，停在 Controller validation；未进入双路 re-review 或 implementation。
- reviewed plan SHA-256：`ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`。
- fixed plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`。
- **fixed plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。**
- 裁决输入已完整读取：`AGENTS.md`、Controller adjudication、AgentMiMo/AgentDS 两路完整 plan review、reviewed plan、`docs/fins/design.md`、Controller discussion Topic 6.3/6.7。
- 第一性原理复核：R07 动机成立。直接根因是 storage-owned opaque identity、source kind、complete publication revision 与同源 snapshot 被 path consumer、selected-field hash、before/after double read 和 filing-first probing替代；正确修复边界仍是 storage owner，不需要新增 authorization、batch snapshot 或文件分类 framework。
- 结果：Controller accepted 的 `R07-PF-01..12` 已全部写入同一 fixed plan；未修改 product、tests、README、design、control 或既有 review artifact，未 implementation、stage、commit、push 或创建 PR。

## 2. Accepted finding closure

| finding | fixed plan 位置 | 具体关闭内容 |
|---|---|---|
| `R07-PF-01` | §8.1 lines 595—603 | 保留 `coverage run --branch` 仅作诊断；门禁改为逐文件 `covered_lines / num_statements` 复算 line coverage，明确 `summary.percent_covered` 不得替代 line gate，另记 composite/branch 指标必须另名。 |
| `R07-PF-02` | §7.3 lines 494—496 | S3 精确点名只删除 `QueryDiagnosis`、`SEARCH_MODE_AUTO` 两个 base F401；禁止扩大清理其它 legacy Ruff 项。 |
| `R07-PF-03` | §2 line 88；§5.2 lines 236—241；§7.2 lines 428—429、454；§8.3 lines 663—671 | 明确 S2 一次性 `SourceDocumentRevision.digest -> token`；仅接受非空 opaque token；S2 同时删除 selected-field hash 与 `sha256:` grammar；临时 `get_source_revision` 只机械构造 `SourceDocumentRevision(token=...)`，S3 删除 method；禁止 alias、compat property、双字段或 SHA-shaped 兼容值，并增加 token owner test 与 `.digest`/SHA residual scan。 |
| `R07-PF-04` | §5.1.6 line 230；§7.1 step 2 line 341；targeted test line 383 | `_published_ticker_directory_names` 的 lock stem 只发现 private candidate key；business ticker 只可由已验证 target/backup descriptor 恢复。lock-only 且无 descriptor 时沿用既有 typed malformed/recovery category、business ticker 缺失，不投影 key/stem且不新造状态名；新增 lock-only owner test。 |
| `R07-PF-05` | §7.1 step 4 line 343；targeted test line 384 | `cleanup_stale_filing_documents` 先从 descriptor 恢复 exact external document id，再应用既有 `fil_` 业务分类与 valid-id 比较；private child key 不参与业务判断；新增 opaque layout stale filing cleanup test。 |
| `R07-PF-06` | §5.3 lines 257—260；targeted test line 462；§8.4 item 4 line 689 | 固定静态损坏优先级：只有 persisted revision/descriptor 真实变化才重取 attempt；未变化时 inode 内容、`fstat`、EOF、declared size/hash 异常立即按既有 corruption/validation 边界 fail closed，不得伪装为 `source_changed_during_read`；增加真实 fd-copy 静默修改验证。 |
| `R07-PF-07` | §0.2 line 29；§5.4 line 267；§7.2 step 5 line 432 | 冻结 `_build_download_local_file_map` 的 descriptor business filename lowercase map 与 `_pick_download_xbrl_file` 的既有排序、suffix、XML fallback 排除规则；唯一变化是 temp paths 同源于一份 full snapshot；明确不引入 `has_xbrl_instance` 内容嗅探分类或新 schema。 |
| `R07-PF-08` | §5.5.1 line 273；§7.3 lines 519、530；targeted test line 552；§8.4 item 5 line 690 | 同 document creation lock 内 double-check matching cached entry；已有 entry 时 losing 调用关闭自己取得的 full snapshot并 borrow existing，否则只构建/发布一个 processor；新增同 revision initial cache miss 并发测试并验证 losing snapshot close。 |
| `R07-PF-09` | §3.7 line 203；§8.3 line 680 | runtime exposure test 明确覆盖 9 个 read tools 的 completed、failed、cancelled 及各自 citation 路径，并递归遍历全部 nested JSON key/value；禁止 revision/private key/absolute temp path/`local://` 泄露，不能只做源码 grep。 |
| `R07-PF-10` | §5.2.4 line 239；S2 targeted test line 457 | source delete/reset 后 source、token 与 snapshot resource 同时不存在，snapshot read 明确 `FileNotFoundError`；新增 storage-owner targeted test。S3 原 cache retire/close test 保持独立，不替代 storage contract test。 |
| `R07-PF-11` | §0.2 line 28；§5.5.3 line 275；§7.3 lines 520—521；targeted test line 572 | `list_documents` 继续组合 filing/material 两个 `list_source_document_ids` typed list projections；禁止 per-document snapshot N+1、batch snapshot API 与 filing-first guess。仅单 document read保留 optional `source_kind=None` 的 0/1/2 storage resolution。 |
| `R07-PF-12` | §10.2 lines 724—726 | S3 cumulative review 明确成为 R07 完整树唯一一次双路 final code review；finding fix、Controller validation、双路 complete re-review 后直接 adjudication/accepted implementation commit，不再安排 R07-only aggregate deepreview。跨 R01—R12 umbrella aggregate deepreview仍保留在全部 remediation sub-WU 完成之后。 |

## 3. 未采纳项与边界证明

1. **未采纳 MiMo `R07-PR-F03` 的必填 `source_kind` / read-runtime解析建议。** §5.3 继续保留 optional typed参数：storage在同一 publication guard 内做0个=`FileNotFoundError`、1个=exact typed kind、2个=invariant ambiguity failure；§5.5.3、§7.3又把 list-only 路径与单文档解析分开，未恢复filing-first policy。
2. **未采纳 DS 对 `has_xbrl_instance` 内容嗅探/新分类 schema 的建议。** fixed plan中该名称只出现在§0.2、§5.4、§7.2的明确禁止语句；SEC fiscal只保留既有 filename/suffix/XML fallback选择。
3. **未新增 batch snapshot API。** §0.2、§5.5.3、§7.3均明确禁止；`list_documents` 只复用既有两个 typed list projections。不存在 `list_source_snapshots` 或等价新协议。
4. **未采纳 lock-only 新状态名示例。** fixed plan不含 `recovery_pending`；无descriptor时沿用既有 typed malformed/recovery category且不产生business ticker。
5. **未保留 digest 兼容。** `digest` 仅用于描述当前问题与breaking rename；目标contract明确只有 `token`，禁止alias、property、双字段与SHA-shaped兼容值。S2删除hash grammar，S3删除临时method。
6. **未新增第二 mapping owner。** blob-first仍遵守§5.1.7“首个payload前创建/验证document descriptor”；没有reverse registry、catalog或blob-side mapping contract。
7. **未扩展 cross-document diagnosis。** §5.5.7仍只对cached candidate取得lightweight snapshot并在borrow内查询；不为未缓存文档构建processor或新增批量接口。
8. **未重复安排 R07-only aggregate deepreview。** §10.2只保留S3 complete-tree final code review；文本中对“R07-only aggregate deepreview”的出现是明确禁止语句。umbrella aggregate deepreview仍由跨R01—R12后续gate拥有。

## 4. Scope diff 与保护性复核

本次 AgentCodex 实际写入闭集只有：

```text
docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md
docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-codex.md
```

preflight 已存在且未由本次修改的工作树项：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-mimo.md
?? docs/reviews/wu-semantic-ownership-01-r07-plan-entry-controller-validation.md
```

保护性文件完成前基线/完成后复核SHA-256一致：

| file | SHA-256 |
|---|---|
| `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| `docs/host/issues-implementation-control.md` | `070997027fd4dd65fd1410c7724124c643907e938eee183da66cb314c1fde9c2` |
| Controller adjudication | `c7e67d2a10d6211cd87bfc8914b4fe3aa6c983826493a5b525d2881f238052e6` |
| AgentDS review | `d95881f59b00e7968af945088f8529169a4d2ee7d5f762c992157447732e92a3` |
| AgentMiMo review | `a6fbd82670b46c5e872f0cba812587d1dd96f2c236063352aff8d867f9fb9211` |
| plan-entry Controller validation | `5f5eccc76f0d896998a2ad4ac56b7f5c5a816314418d55c886f9e408107fef46` |
| Controller discussion | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |

没有 product/test/README/design/control/既有review artifact写入；没有stage、commit、push或PR动作。

## 5. Validation

- fixed plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- `git diff --check`：PASS。
- 因plan与fix artifact当前均为untracked，另分别执行 `git diff --no-index --check /dev/null <file>`：无whitespace diagnostics；命令返回1仅表示存在预期的新增文件diff，不表示check失败。
- `git status --short` / scope：只有preflight既有项加上上述两个授权写入文件；无product、tests、README、design或其它artifact新增变化。
- tests / pyright：未运行；本gate只修改Markdown plan/artifact，没有production或test实现，且用户明确禁止进入implementation。

## 6. Stop condition

**状态：PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION。**

下一步只能由Controller完整读取fixed plan与本artifact、复核同一SHA和12项closure。未获Controller validation前，不派发双路complete re-review，不进入implementation，不修改control，不stage/commit/push/PR。
