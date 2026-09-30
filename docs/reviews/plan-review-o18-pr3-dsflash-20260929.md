RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-d8a71a12

# UM-O18-F01 PR3 候选计划独立 plan review（ds-flash 备份路）

- 审查者：ds-flash（Kimi 额度不足时的独立备份计划审查路，非 Kimi 路本身）。
- 工作区：绝对 `/private/tmp/dayu-upload-o18`；分支 `codex/upload-material-o18`；只读审查，未修改任何计划、目标、裁决、产品、测试、README 或旧 review，未实施、未 commit、未 push、未派发子 Agent。
- 本 artifact 是本次唯一新增文件；未写另一路 review 文件。

## 一、身份核验（全部一手实测）

| 对象 | 期望 | 实测 | 判定 |
| --- | --- | --- | --- |
| 目标计划 `docs/gateflow/upload-material-o18-amended-plan-20260929.md` | SHA-256 `0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce` | 逐字一致 | 身份匹配 |
| O12 计划 `/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md` | 计划 §1/§7 引用 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60` | 逐字一致 | 引用准确 |
| O12 plan gate 结论 | 计划称「已过 plan gate，产品未实施」 | 实读 O12 裁决末节「第五修订版双路复审总控裁决」：Kimi/MiMo 同 SHA 均 `pass-with-risks`，总控判 **plan gate pass**，且明确「产品 implementation 必须待 O16/O05 accepted+integrated 后基于实际 HEAD 重核」 | 与计划一致；O12 计划页首「本版仍待双路 re-review」是 10:00 落盘时的旧状态，不推翻 10:41 裁决 |
| state 计划 `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md` | 计划 §1/§7 引用 `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`，且「本版计划 gate 未双路闭合、产品未实施」 | SHA 逐字一致；实读 state 裁决末节：Kimi 该路有效 `pass-with-risks`，MiMo 同 SHA 内容无 finding 但结构化失败，已按新 label `state-plan-prc4-mimo-rereview-20260929-01` 重派**在途**，「只在本轮 MiMo 结构化及内容有效后判双路 plan gate」 | 与计划一致（未闭合） |
| state 计划第 103 行引用 | 计划称该行明定 material tombstone + create 无 overwrite 保持现有 storage 拒绝 | `sed -n '103p'` 逐字命中该行 | 引用准确 |
| O12 guard 段行号引用 | plan-fix-pr3 称 O12 「storage 同版状态与分阶段 guard」第 43～47 行 | 实读 43/45/47 行为 `MaterialUploadPublishedState` 定义、状态类型 owner 强制、双 precondition 注册与 skip 只读 guard | 引用准确 |

命令执行说明：全部 shell 命令自身 exit0；两处非零均为**预期零匹配**并已显式捕获判断——① `grep -n "class FinsUploadTerminalDisposition" dayu/fins/domain/enums.py` 零匹配（该 enum 实际定义在 `dayu/fins/ingestion_runtime.py:319`，已改读真实位置）；② `ls docs/reviews/ | grep -iE "dsflash|pr3"` 零匹配，确认本次输出路径为新文件。未运行任何故意失败命令。

## 二、结论

**fail（plan gate 不通过）**：两条 medium finding 未闭合前不得进入 O18 implementation，也不得据本计划宣称实施配方可产出所需证据。pr3 修订方向本身成立——PR3-F2～F9 逐项已落文，且我已独立从代码核对其关键事实依据（见第四节「已核验并排除」）——但新文本在**验收配方的可执行性**与**真源可证伪性**上留了两个中等问题，属于「实施期会撞到冻结门」的类型。

未触发停止条件：目标计划 SHA 与全部上游证据身份相符，owner 可闭合，八格未出现不可裁决矛盾。

## 三、Material findings

### F1（中，blocking）交错配方 ① 的 batch/注册次序与 ticker writer lock 互斥，按字面无法执行

计划 §6 ① 原文：「A 持 O12 同版 admission，完成合法公司阶段并 **prepare metadata-only、注册 expected source 与 post-company meta**；B 针对同一 material 成功 commit 切换标记；A 随后 commit，必须由 storage typed stale 拒绝」。

**一手证据（直接代码）**：

- `dayu/fins/storage/_fs_storage_infra.py:417` `begin_batch` 在 `:454` 调用 `self._acquire_ticker_lock(external_ticker)`，并在 `:465` 把该 token 存进 `_ActiveBatchState.writer_lock_token`，直到 `commit_batch`(`:533`) / `rollback_batch`(`:1379`，释放点 `:1516`) 才释放——即 **ticker writer lock 覆盖整个 batch 生命周期**。
- `_fs_storage_infra.py:1759-1777`：`_acquire_ticker_lock` 以 `blocking=True` 取**跨进程**锁；`:436` 的 `_reserve_batch_ticker` 先取本地 reservation。同实例/跨进程对同一 ticker 的第二个 batch 都不能在第一个 batch 存续期间完成注册或 commit。
- O12 计划第 47 行：注册「只检查 typed identity/batch 归属并**记录到 `_ActiveBatchState`**」——注册是 batch-scoped 动作，必须先有 open batch。

**推论**：既然 `注册` 蕴含 `begin_batch`（⇒ 持有 writer lock），步骤「A 注册 …；B 成功 commit …」不可同时成立。B 的 `begin_batch` 会阻塞在 A 的 writer lock 上；若测试用 barrier/timeout 表达，结果是**挂起或串行化**，而不会走到 guard 得到 typed stale。也就是说，配方 ① 按其字面**永远无法观察到它要求的那条断言**。

**同一段内 ②③④ 不受影响（已逐一核对）**：
- ② skip 无 batch，走只读 guard，B 可在 A 报告前自由 commit ✓；
- ③ delete：`docling_upload_service.py:447-453` 的 `prepare_upload` 对 delete **直接返回 `_PreparedDeleteMutation`，不建 batch**；batch 由调用方在 `commit_prepared_upload_batch` 处开启（`sec_upload_workflow.py:562-568`）✓；
- ④ 常规/overwrite 内容发布同理，`prepare_upload` 期间不持锁（含 Docling 转换长窗口）✓。

即 ③④ 的「A prepare → B commit → A batch/commit」天然可行，唯独 ① 多写了一个位于 B 之前的 batch-scoped「注册」。这不是措辞含混可以带过的：O12 line 65/69 明定漂移窗口是「admission 后、**材料 commit 前**（含公司 commit 前已发生的漂移）」，其可行实例正是 B 落在 A 的 `begin_batch` 之前（A 的 batch 在 `begin_batch` 时 copytree 已含 B 的 tree，A 仍按 admission 业务 meta staging ⇒ guard 全值不等 ⇒ typed stale）。配方 ① 必须把**注册/开 batch 挪到 B 的 commit 之后**。

**要求修订**：§6 ① 明确固定时序为「A admission →（A 合法公司阶段 commit）→ A `prepare_upload` 构造 metadata-only mutation → **B 成功 commit 切换标记** → A `begin_batch` + 注册 expected source/post-company → A commit → storage guard typed stale」；并显式声明「因 `begin_batch` 持 ticker writer lock 至 commit/rollback，B 的 commit 必须落在 A 开 batch 之前，否则配方不可执行」。①③④ 的「post-company meta 在 A 公司阶段后漂移」变体同样需按此定位漂移窗口。

### F2（中，blocking）canary 与验收配方无法证伪「`published_amended` 从请求推断」

计划 §3 line 37 明定「逐表面合同…**也不从请求推断已发布值**」，§4.3 明定「不能把 A 的旧 `previous_meta` 静默覆盖 B 的发布」，§4.5/§8 反复要求投影「不得从请求、事件字符串或 processed 快照重算」。但计划唯一的真实验收配方（§6 canary 表 11 步）**每一步的期望 `published_amended` 都等于该步请求携带的 `amended`**：

| 步 | 请求 `--amended` | 期望 `published_amended` | 请求值 vs 期望值 |
| --- | --- | --- | --- |
| 1 | 缺省 false | false | 相等 |
| 2 | true | true | 相等 |
| 3 | true | true | 相等 |
| 4 | 缺省 false | false | 相等 |
| 5 | true | true | 相等 |
| 6 | true | true | 相等 |
| 7 | 缺省 false | false | 相等 |
| 8（delete） | 缺省 false | **最后发布 false** | 相等（前一步 v2 的标记恰为 false） |
| 9 | true | true | 相等 |
| 10 | true | true | 相等 |
| 11 | true | true | 相等 |

步 8 是唯一可能暴露差异的终态（`deleted` 的 `published_amended` 应取删除前最后发布事实），但步 7 刚把标记发成 false，请求缺省也是 false，**两种实现的期望值完全相同**。因此在 O18 规则下（同内容异标记必走 `metadata_updated`，永不 `skipped`），本配方在结构上**不可能**区分「从已发布真源投影」与「回显请求」。

同一缺口存在于 `failed`/`cancelled`：§3 line 60/64 要求二者 `published_amended` 必为 JSON `null`（「null 也不代表 false」），而 §6 canary 没有任何 failed/cancelled 步骤，`null ≠ 请求 true` 这条最尖锐的判别式也未被真实 CLI 覆盖。

**为什么是 material 而非可选**：binding goal 成功信号 3 要求「source meta 与 material manifest 的 amended 值…及用户可见结果一致」，本 WU 的全部动机就是「请求与已发布事实分叉」；一条无法证伪该分叉的配方不能支撑完成报告，且按 §8「真实交错不能证明…时停止」的同源标准，本项属未覆盖。

**要求修订**：在 canary 增加至少一步**请求标记 ≠ 最后发布标记**且终态报告**已发布值**的步骤。最小且自然的形态：在某个 `amended=true` 发布格之后执行 `--action delete` **不带 `--amended`**，期望 `deleted` 且 `published_amended=true`（若实现回显请求会得 false，立即可证伪）；再补一步真实 `failed`（或 `cancelled`）断言 `published_amended=null` 而非该步请求值。owner 测试层面同样需一条「请求值 ≠ 已发布值」的否定断言，不能只用「两者相同」的样例。

### F3（低）`deleted` 终态 `published_amended` 的真源未钉死

计划 §3 line 59 只写「取 tombstone 上最后发布 meta」，§4.5 写「用上传服务的 typed publication outcome/已发布 source meta 形成」。但当前三条相关契约都拿不到它：

- `dayu/fins/storage/repository_protocols.py:944-964` `delete_source_document(...) -> None`（无 meta 回传），`_fs_source_document_core.py:858-889` 同；`docling_upload_service.py:585-603` 的 delete 分支 `UploadOperationResult.payload` 只含 `document_id/internal_document_id/deleted`，不含 meta；
- `docling_upload_service.py:1382-1438` `commit_prepared_upload_batch` 只回传 `CompanyMetaCommitOutcome`（公司侧），没有 source 侧 publication outcome；
- delete 不改 `amended`（`_fs_source_document_core.py:1862-1872` 只写 `is_deleted`/`deleted_at`/`updated_at` 再 `_prepare_complete_source_meta`），故正确真源是 **O12 guard 已验证的 `expected_source_state.source_meta["amended"]`** 或 O12 提供的等价 typed source outcome，而 commit 之后再去普通读取 tombstone meta 会与并发 restore/再发布竞争（正是 §4.3 禁止的「准备期普通读取」同源风险）。

计划未指出该真源，实施期极易退化为「从请求或 `previous_meta` 取」或「commit 后重读」。**要求**：在 §3/§4.5 明确 delete 的 `published_amended` 来自 guard 已验证的同版 source 业务 meta（或 O12 明名的 source publication outcome），并禁止 commit 后重读与请求回落。

### F4（低）与 O14/O15 state plan 的 `active + update/auto 相同内容 → skipped` 验收行未对齐

state 计划第 81/83/102 行把「active + update/auto，相同内容并有合法公司更新意图 → `skipped`；材料零 diff」写成 O14/O15 的 owner 测试与**真实 CLI 矩阵**验收行（第 83 行还要求「active + update/auto 同内容 skipped 且有合法公司意图时…材料 skip 经自己的只读 guard 后报告」）。O18 落地后该行必须**以 amended 相等为前提**：§6 canary 步 4（`--action update`、同字节 X、缺省 `--amended`）期望 `metadata_updated` 而非 `skipped`，与 state 计划该行的粗粒度表述在字节层面同形。

需要按证据说明这**不是**产品矛盾：state 计划第 26 行已明写「**O18 amended**、内容去重、Docling、O33 auto 并发 skip…**不进入本项**」，第 126 行也把 O18 amended 列为他人 work unit。因此这是**顺序/协调项**：O14/O15 先实现并以其自身矩阵验收（此时 amended 维度不存在，断言成立），O18 再扩展 skip 条件。风险在于 state 的 S1/S2 测试与真实 CLI 行若被当作不变量保留，会与 O18 的 `metadata_updated` 格冲突，或迫使实现保留两套 skip 语义。

**要求**：在 §7 增一条 O14/O15 集成清理项——O18 集成后，state 计划第 81/83/102 行的「相同内容 → skipped」以 amended 相等为适用前提，O14/O15 的实现与测试不得把不带该前提的粗粒度 `skipped` 固化为不变量；合流时按八格回归。

### F5（信息，非阻塞）③④ 的断言主体是 O12 guard 的 owner contract

§6 ③④ 的结论句「A 的 delete/内容 batch 在 source/post-company 双 guard 比较处 typed stale 拒绝」描述的是 O12 storage guard 的行为（typed conflict 由 O12 在 `commit_batch` 首次 backup/swap 前的 guard 内抛出，见 O12 计划第 47 行），不是 O18 的 owner 事实。O18 侧应锁的 owner 结论是同段已列出的另一半：「A 不得报告 `metadata_updated`/`deleted` 成功、B 的 source meta/manifest/original/派生资产与版本不回退、`published_amended` 不从陈旧 admission 投影」。建议 §6 明确该分工，避免 O18 测试重复 O12 验收或固化 O12 私有 guard 行为（与项目「测试必须断言 owner 级 contract」同源）。

## 四、已核验并排除的假设（按指定重点逐项）

1. **全 material mutation batch 的 source/post-company 双 guard**：计划 §2/§4.3 已把 metadata-only、delete、常规与 overwrite 内容发布统一纳入「每个 material mutation batch 同时注册两项 typed precondition」，拟 skip 走同一 guard 的只读比较。与 O12 计划第 43/45/47 行实读一致（**batch-generic**，非仅 metadata-only），且 O12 的注册/比较位于 storage `commit_batch`，与 `replace_source_meta` 是否已是条件提交契约无关——故 O18 §2 对 `replace_source_meta` 的保留判断成立。**除 F1 的时序问题外，闭合**。
2. **只读 skip**：计划 §4.3 与 O12 第 47 行末句「material skip 无 mutation 时在同一 storage guard 下只读比较 expected source/company 后才报告 skipped，不以空 batch 重发布 ticker tree」一致；skip 不建材料 batch 与 `docling_upload_service.py:479-499` 现状（无 batch 直接返回）相容。**闭合**。
3. **delete/content 交错**：`prepare_upload` 在 delete 与非 delete 两条路径上都不持 batch（`:447-453`、`:501-557`），batch 由 `commit_prepared_upload_batch` 邻接处开启（`sec_upload_workflow.py:562-568`、`cn_pipeline.py:1207-1211`）。③④ 的时序可行且与 O12 第 65/69 行「公司 commit 前已发生的 source 漂移」窗口一致。**除 F1 外闭合**。
4. **read tool 两个真实表面**：`read_runtime.py:607-639` `_parse_source_document_meta` 被 `:2542-2575` `_collect_source_documents_by_kind` 消费，material 与 filing 都会走到 `:632` 的 `amended`（当前 `default=False`），`:2564` 每项带自身 `source_kind`，`:2478-2516` 把 filing/material 合并为一个列表——混合 `documents` 按 item `source_kind` 分支的事实依据成立。`:725-773` `_collect_list_document_recommendations` 确实只产出 ID/null 槽位，无 amended。`:869-946` 的另一处推荐基于**过滤前全量**文档，与计划表述一致。真 owner `fins_tools.py:387-419` `_build_list_documents_definition` 已在条件白名单。**闭合**（计划对「read 详情」的收窄正确：`read_runtime.py:185/494` 的 `_SourceDocumentMeta`/`_SourceDocumentSummary` 均为内部 typed 投影，非 LLM-facing 详情）。
5. **processed 快照与 current 发布事实**：writer 实测 `_fs_processed_core.py:550-589`（`:580` `amended=bool(merged_meta.get("amended", False))` 宽松取值，随 `ProcessedManifestItem` 入 processed manifest）。当前发布标记确从 source meta 取（`read_runtime.py:2546→2571`），processed 只供能力标志（`:2766-2776`，仅财务字段）。`DocumentSummary.amended`（`document_models.py:868/900`）唯一的仓储出口 `fs_processed_document_repository.py:146→162` 由 `list_processed_documents` 提供，**生产零调用**（仅 `tests/fins/test_hk_period_rebuild.py`、`tests/fins/test_fins_storage_atomicity.py` 引用）。故计划 §8 的停止条件与独立 WU `fins-material-processed-amended-projection` 登记方式正确，且当前**未**触发停止条件。**闭合**。
6. **O13 首次/重复 delete**：`_fs_source_document_core.py:1859-1860` 只判 `meta_path.exists()`（tombstone 的 meta 仍在），重复 delete 会走到 `:1863-1865` 重新盖 `deleted_at`/`updated_at` 后成功——即「健康重复 delete 仍为 `deleted`、非零文件 `skipped`」成立，计划 §3 line 86/§6/§7 的判定与 O13 owner 划分（O18 不改 `deleted_at`/`updated_at`）与 state 计划第 26 行一致。`requested=stored=0` 与 `service_runtime.py:313`（`len(request.files)`，delete 恒空）一致；`_resolve_upload_status`（`sec_upload_workflow.py:635-650`、`cn_pipeline.py:1901-1916`）确为「uploaded→ok，其余原样透传」，`metadata_updated` 可透传并由 `ingestion_runtime.py:326` 的 `__post_init__` 闭集校验接住。**闭合**。
7. **依赖链与停止条件**：O12 已过 plan gate（见第一节）；O14/O15 state gate 确未双路闭合（MiMo 修复性复审在途）；O16/O05 传递前置与 O12 裁决「产品 implementation 必须待 O16/O05 accepted+integrated」一致；计划 §8「任一未就绪即停 implementation，不降级为 best-effort」与依赖状态匹配。**闭合**。
8. **动机与直接证据抽查**：material 路径确无 amended——`service_runtime.py:198-240` `_run_material_upload` 未传，`sec_upload_workflow.py:537-557` material `prepare_upload(meta=...)` 无 `amended`；`sec_upload_workflow.py:191-210/224-233/284-303`、`cn_pipeline.py:820-870/1850-1875` 的 `raw_request.amended` 全部属 **filing** 路径，未与计划 §2 冲突。`ingestion_runtime.py:7797-7830` `_upload_request_summary` 现对 filing 与 material **共用**裸键 `amended`，与计划「material 改 `requested_amended`、filing 保持」的改动方向一致。`upload_tools.py:276-280/344/361` 共享 schema 的 `amended` 默认 false 仍在白名单内。material `identical_skip_safe` 恒 True（`docling_upload_service.py:1723-1735`）、`_can_skip_upload`（`:1616-1648`）overwrite/repair/tombstone 分支、`_resolve_document_version`（`:1745-1770`）同指纹保版——八格逐格与现行代码行为相容，PR3-F6 删除「不可达不安全指纹例外」正确。`_build_upsert_meta`（`:288-331`）九字段投影与 metadata-only「零转换、保内容版本」的关系可闭合。**闭合**。
9. **`MaterialManifestItem` 现状**：`document_models.py:1029-1103` 当前**无** `amended` 字段，`from_source_meta` 用 `_optional_str`/`meta.get(...) is True` 宽松读取；`_fs_source_integrity.py:1235` 用它做 canonical manifest 比较，`:1092-1094` 的严格 bool 校验仅属 filing identity 投影。故计划「新增必填精确 bool + 严格投影 + 新 schema 起库」是真实变更而非既有事实。**闭合**。

## 五、残余风险与未覆盖项

- **R1（F2 衍生）**：即使补上 delete/failed 步骤，canary 仍为单进程单时刻串行，不能替代 §6 的可控 barrier 交错；二者分工需在计划中保持。
- **R2**：`_UPLOAD_TERMINAL_DISPOSITIONS`（`ingestion_runtime.py:327-333`）是 filing/material **共享**闭集，新增 `metadata_updated` 后 filing 路径也不会被该 map 拒绝。计划只对 `published_amended` 做了 source-kind 精确限制，未要求 `metadata_updated` 对 filing fail closed。当前 filing 无产生该状态的路径，风险低；若要求对称，应在 §3 写明。
- **R3**：O13 的 `deleted_at`/`updated_at` 重盖行为（`_fs_source_document_core.py:1863-1865`）在 O18 后仍存在于「重复 delete 也要走带双 guard 的材料 mutation batch」路径上；O18 明确不改，A09 类幂等由 O13 另行验收。合流时需确认重复 delete 的 batch 语义与 O13 时间幂等不互相固化。
- **R4**：`ProcessedManifestItem.amended` 与 `DocumentSummary.amended` 仍为宽松 `bool(...)`/默认 False，且 `_fs_processed_core.py` 与 `document_models.py` 的 processed 侧不在 O18 白名单；若未来出现生产消费者，必须按 `fins-material-processed-amended-projection` 的 owner 修复，不得在 read/tool 下游重算。
- **R5**：`prepare_upload` 为 filing/material 共享签名（`docling_upload_service.py:370-385`，`selection: FinsUploadFilingFiles | FinsUploadMaterialFiles`）。计划要求「material typed 输入携带 amended」且「保持 filing 函数签名和身份计算不变」，实施时需在同一函数内按 source kind 收窄而不是新增第二个默认/来源；filing 的 `amended` 仍只在 `meta` 内（`sec_upload_workflow.py:232`），不得因此产生第二个 filing 真源。
- **R6**：本 review 只做静态一手核对与 SHA/引用核验，**未运行** pytest、pyright 或真实 CLI；计划中的 canary 是未来实施配方而非本轮结果，本 artifact 不改变该事实。
- **未覆盖**：US/CN/HK 真实市场依赖离线可满足性；O16/O05 的实际集成版本与 owner 重核（计划 §8 已列为完成报告必列项）；O14/O15 修复性复审的最终结论（在途）。

## 六、裁决建议

- 判 **plan gate fail**：F1、F2 为 blocking，须由 Sol 一次修计划后同 SHA 双路复审。
- F1 与 F2 都属「验收配方可信度」而非方向问题，修订面小且不触碰已确认的八格、三域键名、O12/O14/O15 硬依赖与用户已裁决的 `--overwrite` 行为；不建议放宽或改写任何用户已确认行为。
- F3/F4 建议与 F1/F2 同轮修订（同为一句到两句话的 owner/时序定义）；F5 为分工说明，可在同轮一并落入。
