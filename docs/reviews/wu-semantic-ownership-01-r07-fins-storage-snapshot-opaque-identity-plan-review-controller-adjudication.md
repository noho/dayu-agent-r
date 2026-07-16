# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Review Controller Adjudication

## 1. 裁决对象

- immutable plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- reviewed SHA-256：`ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-mimo.md`
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-ds.md`
- design truth：`docs/fins/design.md`
- product decision：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.3 / 6.7

两路 review 均完成全文审查且没有 blocking question。`PASS` / `PASS-WITH-FINDINGS` 只表示可进入 Controller 裁决，不表示允许绕过 accepted finding fix。当前 verdict 是 **FIX REQUIRED / 12 accepted fix groups / 1 rejected candidate / 0 external decision**；implementation 尚未授权。

## 2. 第一性原理与 owner 复核

R07 动机成立：raw opaque identity 仍被当成 path component，consumer 仍用 selected-field hash 和 before/after double read 推断 publication freshness，多文件 consumer 仍可取得跨 publication 文件，cache 又没有资源 borrow/retire/close owner。正确 owner 与 `docs/fins/design.md` 一致：storage 拥有 exact external identity 到 private locator 的映射、source kind、complete source publication revision 和同源 snapshot；read/pipeline consumer 只消费 typed snapshot，不反推 owner 事实。

路径 containment、symlink rejection、filename/local URI 检查、atomic mutation、writer mutex、publication guard、journal recovery、typed provenance/citation/read errors必须保留。opaque domain id 改为 storage-owned private locator 不能削弱这些安全/正确性边界，也不能引入统一 authorization framework。

## 3. Accepted fix groups

### R07-PF-01 — line coverage 口径必须准确

接受 MiMo `R07-PR-F01`。开启 branch collection 后，coverage JSON 的 `summary.percent_covered` 会把 branch 分母计入综合比例，不能标成 AGENTS.md 的逐文件 line coverage。plan 保留 `--branch` 诊断，但门禁必须按 `covered_lines / num_statements` 复算逐文件 line coverage；如另行保留更严格 composite 指标，必须另名且不得替代 line coverage 门禁。

### R07-PF-02 — S3 base F401 必须点名

接受 MiMo `R07-PR-F02`。S3 明确只删除 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO` 两个已记录的 unused imports，禁止把 Ruff 清理扩大到其它 legacy 项。

### R07-PF-03 — revision typed field 与 S2 时序必须一次裁决

合并接受 MiMo `R07-PR-F04` 与 DS `F-R07-DS-04`。`SourceDocumentRevision.digest` 必须在 S2 fresh contract 中改为不暗示 hash 算法的 `token`；S2 同时删除 `sha256:` grammar，只保留 non-empty opaque equality。S2 临时 `get_source_revision` 机械读取 persisted token，S3 删除该 method；不得保留字段别名、compat property 或 SHA-shaped token 以迎合旧校验。增加 owner 级 token 接受/拒绝测试及 `.digest` / SHA grammar 残留 scan。

### R07-PF-04 — lock-only company inventory 不得把 lock stem 当业务 ticker

接受 DS `F-R07-DS-01` 的根因，拒绝其示例状态名成为新 contract。S1 step 2 必须点名 `_published_ticker_directory_names`：lock stem 只发现 private candidate key；business ticker 只能由 target/backup descriptor 恢复并验证。只有 lock、没有可验证 descriptor 时，inventory 返回既有 typed malformed/recovery category 且 business ticker 缺失，绝不能投影 key/stem。增加 lock-only targeted test。

### R07-PF-05 — maintenance cleanup 必须先恢复 external document id

接受 DS `F-R07-DS-02`。S1 明确迁移 `cleanup_stale_filing_documents`：目录 child name 只作 private locator；从 descriptor 得到 exact external id 后再执行既有 `fil_` 业务分类和 valid-id 比较。增加 opaque layout 下 stale filing 删除测试，禁止让 private key 前缀参与业务判断。

### R07-PF-06 — snapshot 静态损坏优先级必须确定

接受 DS `F-R07-DS-03`。在 R06 publication guard + atomic rename 合法写路径下，已打开 inode 内容或 `fstat` 发生变化而 persisted revision/descriptor 未变不是合法 publication race，必须立即按既有 corruption/validation 边界 fail closed；只有 revision/descriptor 真实变化才重取 attempt，不能把静态损坏重试后伪装为 `source_changed_during_read`。增加真实 fd-copy 静默修改 smoke/targeted test。

### R07-PF-07 — SEC fiscal 只更换 source owner，不改文件选择算法

部分接受 DS `F-R07-DS-05`。plan 必须冻结当前 `_build_download_local_file_map` / `_pick_download_xbrl_file` 的可观察选择语义：仍按 snapshot descriptor 中声明的业务 filename 建立 lowercase map、排序并按既有 suffix / XML fallback 排除规则选择 instance/schema/linkbase；唯一改变是所有 temp paths 来自同一 full snapshot。拒绝把 `has_xbrl_instance` 内容嗅探或新文件分类 schema 引入本 slice；这会越过“不改 fiscal 推断算法”的边界。

### R07-PF-08 — cache miss serialization 必须在 creation lock 内 double-check

接受 DS `F-R07-DS-06`。S3 明确：获取同 document creation lock 后再次检查 matching cached entry；如已有可借 entry，关闭当前调用自行取得的 full snapshot并借 existing entry；否则只构建并发布一个 processor。并发 targeted test 必须覆盖同 revision 的初始 cache miss，而不只覆盖 revision change，且证明 displaced/losing snapshot 被关闭。

### R07-PF-09 — runtime recursive exposure test 补齐 cancellation 路径

部分接受 DS `F-R07-DS-07`。原 plan §3.7、§8.3 和 targeted node 已要求递归遍历运行时 JSON，因此“只有源码 grep”的前提不成立，不新增另一套扫描框架；但 §8.3 必须与 §3.7 对齐，明确 9 个 read tools 的 completed/failed/cancelled 及 citation 路径都递归遍历 key/value，禁止 revision/private key/absolute temp path/`local://` 泄露。

### R07-PF-10 — delete/reset 后 snapshot absence 必须有 storage-owner test

接受 DS `F-R07-DS-08`。S2 增加 source delete/reset 后 snapshot 明确 `FileNotFoundError`、token/resource 同时不存在的 targeted test；S3 继续单独证明 cached entry 被 retire/close，不能用 cache test 替代 storage contract test。

### R07-PF-11 — list-only source-kind projection 不得变成 N+1 snapshot

接受 DS `F-R07-DS-09` 的澄清需求，拒绝新增 batch snapshot API。`list_documents` 继续对 storage-owned `list_source_document_ids` 做 filing/material 两个 typed list projections 并组合业务列表，不对每个 document 调 per-document snapshot，也不恢复 filing-first guess。单 document read 才使用 snapshot 的 0/1/2 typed source-kind resolution。

### R07-PF-12 — R07 完整树只做一次双路 final code review

Controller 直接接受流程修正。当前 §10.2 在 S3 cumulative complete-tree code review 后又安排一次等价的 R07-only aggregate dual deepreview，重复同一审查边界。按用户确认的 umbrella 优化流程，S3 cumulative review 必须就是 R07 的完整 code review；fix、Controller validation、双路 complete re-review 通过后即可 adjudication 和 accepted implementation commit。跨 R01-R12 的 aggregate deepreview 仍只在所有 remediation sub-WU 完成后执行，不得删除或提前冒充。

## 4. Rejected / duplicate / observation

### MiMo `R07-PR-F03` — rejected with design evidence

不把 `source_kind` 改为必填，也不把解析留给 read runtime。`docs/fins/design.md` 明确 Source repository 拥有 source kind；当前 filing-first probing 正是 consumer 用查询顺序猜 storage 事实。plan 选择在同一 publication guard 下对 0/1/2 个 mapping 做 not-found / exact typed kind / invariant ambiguity 判定，符合唯一 owner，也不会让 list-only 路径做 N+1（由 R07-PF-11 明确）。未来偏好策略不应改变已有 source 的 typed kind。

### DS open questions

- `_build_source_revision`：plan S2 step 2 已明确删除 selected-field hash builder；无需推迟到 S3。
- blob-first descriptor：§5.1.7 与 S1 状态规则已明确首个 payload 前创建/验证 descriptor；实现 review 必须按该规则验证，不新增第二 mapping owner。
- cross-document diagnosis：当前只遍历 cached candidates；plan §5.5.7 已明确对 cached candidate 取 lightweight snapshot 后在 borrow 内查询，不要求为未缓存文档构建 processor。

DS 对 `percent_covered` 的说明与 coverage.py branch-mode 实际口径不符，由 R07-PF-01 纠正。其余 review confirmation 作为 positive evidence，不产生 fix。

## 5. Fix boundary 与下一 gate

AgentCodex 只可修改：

- `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- 新的 R07 plan-fix artifact

不得修改 product、tests、README、design truth、control、已有 review artifact，不得 stage/commit，也不得开始 implementation。fix artifact 必须给出 R07-PF-01..12 的逐项位置、最终 plan SHA、scope diff 与未采纳项证明。

Controller 完整读取并验证 fixed plan 后，AgentMiMo / AgentDS 必须对同一新 immutable SHA 做双路 complete re-review。只有 12 组 finding 全部关闭且无新 accepted finding，才可进入 accepted-plan local commit。
