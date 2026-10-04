# S1 workflow 回归实施记录

## 范围与结论

- 日期：2026-09-15，Asia/Shanghai；记录版本：1。
- 已读 `AGENTS.md`、`docs/plans/midea-q1-full-report.md`、`docs/reviews/plan-review-20260915-203419.md`、`docs/reviews/midea-q1-cache-diagnosis.md`。
- 本子任务仅修改 `tests/fins/test_cn_download_workflow.py` 和本记录；未修改生产、selection 测试或投资目录，未提交。
- 动机成立：CN 财期身份不随 source_id 改变，workflow 的 COMPLETE 默认 skip 保留旧来源；已有 overwrite 足以在同一身份替换选中候选。本子任务验证既有合同，不修改下载语义。
- 保留现有 fixture、事务检查和 processed 重处理标记检查，仅扩展已有两个测试；没有增加重复测试、版本 v1 断言或独立 supersede 承诺。

## 改动与审核依据

### 默认 skip

`test_cn_complete_phase_a_skips_transport_without_source_mutation`：

- 先通过真实 workflow 和仓储写入合成正文 A1，确认持久化 source_id/title/url 及 PDF 与输入一致。
- discovery 改为合成全文 A2，同时改变 URL、ETag 和待下载 PDF 字节。
- 默认增量仍 skipped=1，PDF 下载次数不增；沿用原公司事务 begin/rollback 及 source 无 mutation 断言。
- 全量 source meta 与旧快照相等，PDF 字节不变，因此新候选的来源信息不会悄然覆盖旧正文信息。

### overwrite 与再次 skip

`test_cn_replacement_success_exposes_source_blobs_and_processed_marker_together`：

- 沿用正文 A1、既有 processed、全文 A2 的成功覆盖场景，使用同一 document_id。
- 覆盖后 source_id/title/url、PDF 字节、pdf_sha256 均对应 A2；source_fingerprint 和 remote_fingerprint 与各自 owner helper 的结果一致，且不同于 A1。
- 仓储列出的文件名称精确为该文档 PDF 和 Docling JSON 两项；逐项复算 SHA256 和长度，核对仓储元数据；读取字节与合成输入一致。
- 通过 `source_repository.list_source_integrity` 断言仅一个目标、COMPLETE、无原因。仓储 `_apply_manifest_facts` 对落盘清单与 `FilingManifestItem.from_source_meta` 的规范投影逐项比较，缺项、多项及投影漂移均不能通过。测试消费此公开 owner 合同，不另造清单字段规则，不绕过仓储直接读取受管文件。
- 保留 processed `reprocess_required=True` 断言。
- 再次默认增量 skipped=1、downloaded=failed=0，下载和转换次数不增；全量 source meta、文件列表、PDF 字节及仓储完整性身份不变。

## 来源与可复现链

- 原始来源：当前工作区源码、上述计划和审核记录；运行参数见下节。用例沿用合成 `600519 / 2024 FY` 财期槽位，不冒充美的真实公告或真实 2021Q1 PDF。
- Raw 输入：测试内 `_candidate`、显式“合成测试”标题、`.test` URL、A1/A2、`_PDF_BYTES` 与 `_DOCLING_BYTES`；fake discovery 不负责排序，fake converter 返回固定合成 JSON。
- 计算和审核底稿：上述两个可重复执行测试；通过真实仓储读取各阶段 meta、PDF、文件清单及完整性事实后执行断言。内容与远端 fingerprint 分别复用对应 owner；文件 SHA256 和长度独立计算核对。
- 最终结果：本记录的执行结果来自测试断言与类型检查输出，无手工财务结果。
- 留存例外：用户只授权两个文件，因此不另建 source_manifest/raw/workpapers/outputs 或日志文件；Raw 合成输入及审核逻辑保留在测试文件，落盘状态由 pytest 临时目录承载，可用下述命令重建。本轮没有提取真实财报逐笔数据，不能把合成回归当作真实数据审核。

## 执行验证

在仓库根目录执行：

```sh
source .venv/bin/activate && python -m pytest tests/fins/test_cn_download_workflow.py -q
```

退出码 0；`80 passed in 2.14s`。

```sh
source .venv/bin/activate && python -m pyright tests/fins/test_cn_download_workflow.py
```

退出码 0；`0 errors, 0 warnings, 0 informations`。另有工具版本更新提示，未升级依赖。

```sh
git diff --check -- tests/fins/test_cn_download_workflow.py
```

退出码 0，无空白错误。

## README 与剩余风险

- 已检查 `tests/README.md` 的读者职责和更新边界。没有新增测试层级、运行方式或维护规则；本子任务不改 README。总体 S1 文档协调留给主 Agent，遵守本轮两文件限制。
- 本轮只运行指定测试文件和该文件 pyright；未运行全库检查，未统计生产单文件覆盖率。
- 合成测试不验证 selection 排序、真实网络、真实 Docling 转换、全文财表覆盖或公开 CLI 端到端行为；这些由主 Agent 的 selection 工作和已批准隔离验收处理。
- 当前覆盖只承诺同一身份的完成态替换及清单当前投影一致，不承诺历史版本递增、旧版本留存或独立 supersede；processed 仅被标记重处理，未验证后续重算。
- 交付状态：workflow 回归子任务完成，可供主 Agent 继续 S1 review；不代表完整 S1 或真实财报验收完成。
