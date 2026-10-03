# 用户工作区 250 份 docling json 重转换（docling 2.127）

- 日期：2026-09-17
- 目标工作区：`/Users/leo/Documents/_2我的投资/workspace`（用户生产工作区）
- 发起人裁决：① 新版更差的文档保留旧版不替换；② 不冻结上传；③ 旧版全量备份到工作区外
- **备份保留决策（2026-09-17 追加）**：备份 `workspace-docling-backup-20260917/`（1.3 GB，250 份升级前产物）**已按用户裁决删除**——portfolio 是可再生产物，且 118 份保留件的工作区文件本身仍是旧版；132 份已发布件因此失去便捷回退能力（旧版可重建：从 git 历史恢复 constraints 并装回 docling 2.90 重转）
- 过程数据：`workspace/tmp/docling-reconvert/`
- 状态：**已完成**（250/250 处理完毕，132 发布 / 118 保留，全库 owner 校验 COMPLETE）

## 0. 摘要

| 项 | 结果 |
|---|---|
| 处理份数 | 250 / 250（全部有终态，无失败项） |
| 发布新版 | **132 份** |
| 保留旧版 | **118 份**（未修改一个字节，已与备份逐份核对） |
| 全库完整性 | 250/250 `COMPLETE`（owner 校验器），无 `REPAIR_REQUIRED` / `UNSAFE` |
| 转换 CPU 总耗时 | 15.8 小时（5–10 路并行，墙钟约 3.9 小时） |
| 备份 | 250 份 / 1321.4 MB，独立复核 250/250 一致 |

## 1. 关键发现：任务书给定的 `process_filing` 路径不成立

任务书假定「`dayu-cli process_filing --overwrite` 会重建 processed 产物并原子发布 meta」，据此可以「先把候选 json 放进去、再让 CLI 发布」。**该前提经实测证伪**，证据三条：

1. **`process_filing --overwrite` 不重跑 docling 转换。** 在临时副本工作区对其执行后，`_docling.json` 与 `meta.json` 的 SHA-256 **零变化**，只新增 processed 产物（`sections.json` / `tables.json` / `tool_snapshot_meta.json`）。代码侧对应 `dayu/fins/ingestion_runtime.py:_preprocess_one_document`——它只读 source snapshot、调用 `DoclingProcessor`（`load_from_json` 消费者），并只写 processed 仓储。
2. **先把文件换掉再跑 CLI 会直接失败。** 替换 `_docling.json` 后，owner 校验器把该 source 判为 `REPAIR_REQUIRED`（`size_mismatch` + `digest_mismatch`）；随后 `process_filing --overwrite` 报 `failed=1`。根因是 `dayu/fins/storage/_fs_source_snapshot.py` 的 `_require_complete_source_for_snapshot_unguarded` 只允许读取 `COMPLETE` source。
3. **工作区从未被 process 过。** 250 份 filing 的 `processed/` 目录条目数为 0。

**规范路径裁决（用户）**：改用 storage owner 公开协议发布——转换走生产同源入口，发布走 `begin_batch` → `store_file` → `update_source_document` → `commit_batch`，派生字段复用 pipeline owner helper。这也是唯一能同时满足「纯本地 + 逐份质量门前置 + 不直改文件/meta」的路径：另一条能重跑 docling 的 CLI 路径 `download --overwrite` 必须联网重下 PDF、按 ticker 整批覆盖，无法逐份质量门。

## 2. 执行方式

工具：`workspace/tmp/docling-reconvert/`（均为临时脚本，未改生产代码，未 commit）

| 脚本 | 职责 |
|---|---|
| `docling_reconvert.py` | 单份/批量/清单三模式：读 source → 生产同源转换 → 质量门 → 通过则 batch 内原子发布；带 resume 账本 |
| `backup_docling_json.py` | 阶段 A 备份与 sha256 manifest |
| `verify_workspace.py` | 用 storage owner 校验器做全库完整性分类 |
| `summarize_run.py` | 结果账本统计 |
| `run_shard.sh` | 阶段 D 分片驱动 |

转换口径与生产一致：`dayu.documents.docling_runtime.convert_pdf_bytes_with_docling` + `json.dumps(ensure_ascii=False, indent=2)`。发布口径复用 `build_content_fingerprint` / `build_cn_file_entry`，meta 只改 `files[docling]` 条目、`source_fingerprint`、`document_version`、`updated_at`，其余业务字段原样保留；PDF entry 与其 `etag`/`last_modified`/`ingested_at` 完全不动。

## 3. 质量门

按任务书口径：**merged 文本数字多重集**（`texts[].text` ∪ `tables[].data.table_cells[].text`）计数 + **结构计数**（`texts` / `tables` / `pictures`）逐项比较，新不小于旧则发布，否则保留并记录。

`merged` 口径的意义在本次数据中得到验证：**97 份保留件的 `texts` 块数下降但字符数反而增加**——若只按 `texts` 单口径判断会把「分块合并」误判为内容丢失，而若只按字符数判断又会放过真实退化。两个口径同时保留是必要的。

## 4. 全量结果

### 4.1 按 ticker

| ticker | 发布 | 保留 | 保留率 |
|---|---|---|---|
| 3690（美团） | 4 | 39 | 91% |
| 000333（美的） | 9 | 18 | 67% |
| 600938 | 1 | 5 | 83% |
| 0700（腾讯） | 22 | 25 | 53% |
| 9992（泡泡玛特） | 13 | 10 | 43% |
| 0883 | 16 | 7 | 30% |
| 1179 | 23 | 5 | 18% |
| 9961（携程） | 18 | 4 | 18% |
| 9898 | 16 | 3 | 16% |
| 0300 | 10 | 2 | 17% |

### 4.2 保留原因分布（一份可命中多项）

| 原因 | 份数 |
|---|---|
| `texts` 减少 | 109 |
| 数字减少 | 27 |
| `pictures` 减少 | 11 |
| `tables` 减少 | 1 |

### 4.3 保留件的性质分层（**关键**）

| 类别 | 份数 | 含义 |
|---|---|---|
| 分块合并（块数减、字符数未减） | **97** | 新版把多个文本块合并为更少块，字符总量未下降 |
| 内容减少（块数与字符数同降） | **12** | 真实内容减少，但幅度全部 < 0.5%（最大 0.46%） |
| 数字/图片减少 | 9 | 数字或图片数量下降 |

数字减少的 27 份中，**仅 6 份幅度 ≥ 2%**，且集中在 000333：

| 文档 | 数字变化 | 降幅 | 缺口 |
|---|---|---|---|
| `fil_cn_f27f89fb932e05afe65f190154b668fe0ae51063` | 2139 → 1416 | 33.8% | 1277 |
| `fil_cn_be7430d8983cc759ba706…` | 1744 → 1195 | 31.5% | 993 |
| `fil_cn_f151c6b703769c8efa629…` | 1277 → 1057 | 17.2% | 418 |
| `fil_cn_0436e1724640d9d22…`（3690） | 9079 → 8675 | 4.5% | 460 |
| `fil_cn_7bb9e65377e4b8a5f1911…`（9992） | 10862 → 10455 | 3.8% | 463 |
| `fil_cn_906392b8f12567c87467f…`（3690） | 8076 → 7910 | 2.1% | 190 |

已知退化样本 `fil_cn_8492e1288ed5d24ee05fb7b95983b0bb0ea1c443`（泡泡玛特 2025 年报附注 25）如实被拦：数字 11399 → 11212（缺口 397，32 种 token），与 `docs/reviews/docling-regression-8492e128-rootcause.md` 的根因结论一致。

### 4.4 已发布 132 份的收益

| 指标 | 份数 |
|---|---|
| 数字增加 | 83 |
| 文本块增加 | 111 |
| 表格增加 | 9 |
| 图片增加 | 1 |
| 数字持平 | 49 |

已发布文档的 merged 文本字符合计净增 **+50,263**。

## 5. 验证证据

1. **owner 完整性分类**：全库 250 份 `COMPLETE`，`reason_counts` 为空（`workspace/tmp/docling-reconvert/verify-final.json`）。
2. **保留文档零改动**：把工作区 250 份 `_docling.json` 与备份 manifest 逐份比对——未变 118 份、已变 132 份，**与账本的 withheld/published 数量完全一致**，即没有任何一份保留件被写入过。
3. **发布后 CLI 可消费**：对已发布文档执行 `process_filing --overwrite`，`processed=1 / failed=0`（对照组：未同步 meta 的裸替换为 `failed=1`）。
4. **meta 与 manifest 一致**：发布后 `files[docling]` 的 `sha256`/`size`/`etag`/`last_modified` 与实际文件一致，`filing_manifest.json` 同步更新（`document_version`、`source_fingerprint`）。
5. **幂等与确定性**：同一份文档两次转换产出的候选字节 SHA-256 完全相同。
6. **纯本地**：`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 下转换成功；全过程仅网络依赖为 0（旧版 PDF 全部复用工作区字节，未触发重新下载）。
7. **无转换回退**：全部 250 份均由尝试链第 1 档（`docling-parse` + `auto` device）完成，0 次 backend 回退，因此新旧差异不是后端切换造成的。

## 6. 备份

- 路径：`/Users/leo/Documents/_2我的投资/workspace-docling-backup-20260917/`
- 内容：250 份 `_docling.json`，保留 `portfolio/<ticker>/filings/id-*/` 相对结构；`manifest.json` 记录 `relative_path` / `size` / `sha256` / `source_mtime`
- 体量：1321.4 MB；独立复算复核 250/250 一致

## 7. 风险与残留

| 项 | 说明 |
|---|---|
| **`document_version` 规则复刻** | source fingerprint 变化即递增（`v1`→`v2`）的规则在 download 与 upload 两条 pipeline 中各自私有实现；本工具按同一语义显式复刻了一份。若 owner 规则变更需同步。所有已发布文档因此递增了一次版本号（内容确实变化）。 |
| **质量门口径的保守性** | 按任务书口径，118 份被保留，其中 97 份实为「分块合并」而非内容丢失。是否对这批放宽口径复审，待用户裁决；放宽时需注意 12 份真实内容减少与 27 份数字减少件的区分。 |
| **上游回归未修复** | 保留的直接原因是 docling 2.118+ 的表格/文本回归（`docs/reviews/docling-regression-8492e128-rootcause.md`、`docling-upstream-issue-draft-20260917.md`）。本次只是避免把退化引入工作区，未修复上游。 |
| **3690 保留率 91%** | 该 ticker 39/43 被保留，等于这批文档在 2.127 下几乎没有可用收益，需评估是否值得单独上报上游样本。 |
| **`processed` 产物未重建** | 工作区 250 份 filing 的 processed 目录本为空，本次未生成 processed 产物；若后续需要，用 `dayu-cli process_filing --overwrite` 按 ticker 执行即可（source 均为 COMPLETE）。 |
| **过程数据占用** | `workspace/tmp/docling-reconvert/candidates/` 保留 250 份候选（1.3 GB），可用于复审或回滚比对；确认无需后可删除。 |
| **大文档耗时** | 282–345 页的年报单份转换需 20–42 分钟（CPU），是本轮墙钟时间的主要来源；若后续需要重跑，建议保持按文档级并行（本轮 10 路并行时总 CPU 约 18–26 核）。 |

## 8. 保留件口径复审（追加分析）

数据源：结果账本 + 工作区旧 json + 候选 json，两侧事实**独立重算**并与账本交叉核对（118/118 完全一致，无偏差）；行级明细见 `workspace/tmp/docling-reconvert/review-criteria.json`。全程只读，未改工作区、未发布任何文档。

### 8.1 口径定义

- **口径 A（现行）**：merged 数字 token **总数**不减 **且** `texts` / `tables` / `pictures` 计数均不减。
- **口径 B（内容）**：merged 数字 token 总数不减 **且** merged **字符数**不减。
- **口径 B\***（"多重集不小于"的严格解读）：数字 token **多重集包含**（每个 token 计数不减）且 merged 字符数不减。

**字符口径的选择**：采用 **`texts[].text` ∪ `tables[].data.table_cells[].text` 的字符总数**，与数字多重集用同一个文本集合。理由是升级的主要变化之一就是「文本块被识别为表格」，若只统计 `texts` 拼接字符数会把「移入表格」误判为内容下降。

### 8.2 交叉表（118 份保留件）

| 象限 | 份数 |
|---|---|
| A 过 B 过 | 0 |
| A 过 B 不过 | 0 |
| **A 不过 B 过** | **88** |
| 都不过 | 30 |

A 过 B 过的两栏恒为 0 是集合定义使然——118 份即「A 不过」的补集。作为反向检查，已发布的 132 份在 B 下**全部仍然通过**（字符数无一倒退），说明口径 B 不是"放水"：它只是把判据从「块数」换成「内容量」。

### 8.3 97 份「分块合并」类细目

| 指标 | 值 |
|---|---|
| 字符数环比变化 | 最小 **+4**、中位数 **+223**、最大 **+5035**（**全部为正**，无一份字符数持平或下降） |
| 其中数字总数减少的份数 | **9** 份（占该类 9%） |

即：97 份里 88 份是"块数变少但内容变多、数字不变"的纯分块变化；余下 9 份虽字符增加，但数字总数下降，属于必须继续保留的对象。

### 8.4 另两类在口径 B 下的复判

| 类别 | 份数 | B 通过 | B 不过 |
|---|---|---|---|
| 内容减少（块数与字符数同降） | 12 | 0 | **12** |
| 数字/图片减少 | 9 | 0 | **9** |

两类**全部仍不过**——B 口径没有放过任何一份真实内容下降或数字下降的文档。9 份「数字/图片减少」的实际失分点是数字总数下降（-2 至 -7）与图片减少（如 51→50），与其分类一致。

### 8.5 若按口径 B 发布的风险量化

| 指标 | 值 |
|---|---|
| 预计新增发布 | **88 份** |
| 其中数字**净减少**的份数 | **0 份** |
| 严格口径 B\* 下仍通过 | 50 份 |
| B 通过但 B\* 不过 | 38 份 |

那 38 份的差异是 **token 级微差**而非总量下降：

| 指标 | 值 |
|---|---|
| 缺失 token 总量 | **138 个**（38 份合计） |
| 每份缺失 | 最小 1、中位 **2**、最大 21 |
| 这些文档的新版数字总量 | 243,863 |
| **缺失率** | **0.057%** |

缺失样本形如 `5%`、`169`、`-25`、`202255`、`(2`（后者是数字分词伪影）。作为量级对照：本轮确认的上游退化样本 `fil_cn_8492e128…` 在 11,399 个 token 中缺失 **397 个**（3.5%），是这 38 份平均水平的约 60 倍。

**结论**：口径 B 的"新增发布"恰好等于「分块合并且数字总数不减」的 88 份；真实内容下降（12 份）与数字下降（30 份）无一被放过。残余风险面是 38 份存在合计 138 个（0.057%）token 级微差，其中多数可能是格式/分词差异而非数据丢失，但**未逐个人工核验**，这一点属于本分析的已知边界。

### 8.6 明细产物

| 路径 | 内容 |
|---|---|
| `workspace/tmp/docling-reconvert/review-criteria.json` | 118 份行级明细（`stem` / `ticker` / `gate_reasons_a` / `a_pass` / `b_pass` / `b_strict_pass` / `char_delta` / `number_delta` / `missing_number_tokens` 等）+ 全部汇总 |
| `workspace/tmp/docling-reconvert/analyze_criteria.py` | 复现脚本（只读，可直接重跑） |

## 9. 产物清单

| 路径 | 内容 |
|---|---|
| `workspace/tmp/docling-reconvert/full-run.jsonl` | 250 份逐份账本（指标、质量门结果、发布事实） |
| `workspace/tmp/docling-reconvert/withheld-list.json` | 118 份保留清单（分类、指标对比、旧 sha256） |
| `workspace/tmp/docling-reconvert/summary.json` / `summary.md` | 统计汇总 |
| `workspace/tmp/docling-reconvert/verify-final.json` | 全库 owner 完整性分类结果 |
| `workspace/tmp/docling-reconvert/candidates/` | 250 份候选 docling json（1.3 GB） |
| `workspace/tmp/docling-reconvert/probe-workspace/` | 阶段 B 路径实测用的临时工作区副本 |
| `/Users/leo/Documents/_2我的投资/workspace-docling-backup-20260917/` | 旧版全量备份 + manifest |
