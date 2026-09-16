# Implementation S1：midea-q1-full-report

- gate：implementation S1；next entry point：code review。
- base：d30a07c870e3602638d8943ab71a5eaa3e01fc9b；branch：codex/upload-material-oracle。
- plan：`docs/plans/midea-q1-full-report.md`；plan review：`docs/reviews/plan-review-20260915-203419.md`。
- 用户约束：不提交、不推送、不改投资 workspace；生产仅改 selection owner。

## 改动与决策

- `dayu/fins/pipelines/cn_report_selection.py`：新增模块级私有 key，按修订、日期、非正文、ID、URL 选择。替换嵌套 key；保留正文来源、修订规则、日期规则和语言/摘要过滤。无 schema/public API/state machine 变更。
- `tests/fins/test_cn_report_selection.py`：参数化 Q1/Q3、全文/普通标题、修订组、两个方向输入；唯一正文；更正/较新正文优先；同分 ID/URL 稳定。
- `tests/fins/test_cn_download_workflow.py`：AgentCodex 扩展两个现有测试，默认 skip 保留旧来源，覆盖更新来源和完整文件集合、hash/fingerprint、manifest 当前投影及 processed 重处理标记，再次增量不变。子产物：`docs/reviews/midea-q1-workflow-implementation.md`。
- README：根用户手册说明补源 overwrite；Fins 开发手册说明选择 owner 合同；测试手册说明 focused 运行入口。

## 已完成验证

- 未改代码的真实公开 CLI：discovered=1/downloaded=1，落盘 9 页正文 source_id=1209870319。
- 改后同一隔离 workspace 普通 CLI：downloaded=0/skipped=1，冻结的 PDF/Docling/meta/manifest/company meta 全部字节不变。
- 同一 CLI 加 `--overwrite`：downloaded=1，source_id=1209870320、17 页完整报告。
- 随后普通 CLI：skipped=1，上述冻结文件全部字节不变。
- 全新隔离 workspace 普通 CLI：downloaded=1，source_id=1209870320，PDF hash 与覆盖下载一致。
- PDF SHA256：正文 `6487428b3b848029094a10972771207270cb36a85e42b81b04ae2ff5a89f6939`；全文 `f68e946df248e9b3cf27ad684910928431ae112605a23f1e3429808637e1b4b6`。
- 每轮唯一 doc ID、两文件 exact set、每文件 hash/size、pdf_sha256、content fingerprint、Q1/2021/provider identity、manifest 当前投影均通过；额外 HEAD Raw 重放 remote_fingerprint 也全部通过。
- `workspace/tmp/midea-q1-cli/workpapers/reconciliation-v1.json` 为总勾稽底稿，最终 JSON 位于同目录树 `outputs/reconciliation-v1.json`。
- selection+downloader：129 passed；selection 单文件覆盖率 91%；workflow：80 passed；全量 pyright：0 errors（最终全部合并后再次检查记录在 final-pyright.txt）。

## PDF 内容验收与例外

主 Agent 通过仓储读取公开 CLI 原文，冻结 Raw 后用 pypdfium2 渲染。全文第 11–12 页视觉确认资产负债表、2021年3月31日、合并与公司列、人民币千元单位，货币资金、短期/长期借款和股本行存在。此处只做来源内容覆盖检查，不转录财务数值，不替代投资底稿。

环境没有 Poppler，使用已安装 pypdfium2 提取和渲染；最初调用 pdftotext 失败未改 Raw，随后通过 `snapshot.py before-v1 --audit-only` 仅重做审核层。所有 Raw 保留未覆盖。

图片财表没有对应文本层，Docling JSON 第 11–12 页存在表结构但中文行名不完整，搜索“货币资金”无命中。不得把这理解为原文未披露，也不得把生成 JSON 当作财务字段审核通过。

本轮保留既有日期投影：巨潮 raw announcementTime 对应 UTC 2021-04-29 16:00，Dayu filing_date 为 2021-04-29，PDF 路径/官方本地披露日期为 2021-04-30；独立验证命令必须保留两天窗口。source meta 的 report_date 仍为 null，财期由 fiscal_year=2021、fiscal_period=Q1 表达；2021-03-31 为本轮原图核实的报表日期，没有手工写回 Dayu 元数据。

## Residual risks 分类

- fixed in current slice：同日正文/全文错选及输入顺序不稳定。
- covered by later approved gate：独立 code review、aggregate deepreview 和证据清单修订，由主 Agent 裁决并收口。
- assigned to later work unit：图片财表 OCR/结构化提取质量，owner 为 Docling/财表提取链路维护者；本轮只补原始来源，不扩大为转换器修改。
- assigned to later work unit：投资 workspace 补源及 G1 原表审核，owner 为原投资 workflow 主 Agent；必须独立验证后执行。
- 保留的范围边界：不同日期/修订级别沿用版本优先级，不能声称任意报告完整性已自动识别；overwrite 不承诺历史版本递增/留存，本轮审计依赖保留的 Raw。
- 用户明确约束：accepted slice commit 仅可 no-commit；不进入实际 push/PR。

## 完成状态

S1 实现与真实验证完成，等待 code review。不得据此提前宣布 aggregate deepreview 或 PR gate pass。
