# SEC HTML 引用图片下载修复：目标确认

- Work unit：sec-html-image-assets。
- Gate：goal confirmation；状态：用户已确认，进入 plan。
- 当前 gate / next entry point：plan；后续 gate 由 control artifact 记录。
- 分支：`fix/sec-html-image-assets`，基线 `297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- Preflight：原分支 main，工作树干净；用户已授权创建新修复分支和新 draft PR。

## 动机与直接证据

修复动机成立：已选中的 SEC HTML 依赖图片承载部分财务表和演示内容，但下载的文件集合未包含这些依赖。现有成功结果只覆盖已枚举文件，不能证明 HTML 依赖齐全。

- `dayu/fins/downloaders/sec_downloader.py:list_filing_files` 枚举 primary、XBRL、HTML 附件及同 filing HTML 补链，没有收集图片依赖。
- `dayu/fins/pipelines/sec_download_filing_workflow.py` Phase A 对 COMPLETE publication 使用 `_can_skip_fast(...) or "integrity_complete"`；Phase B 也无条件跳过 COMPLETE 且非 overwrite 的 publication。因此只增加图片枚举或只提升下载版本，无法保证旧来源在普通增量调用中补齐。
- `dayu/fins/pipelines/sec_pipeline.py:_can_skip_fast/_can_skip` 已有下载版本校验；`sec_download_source_upsert.py` 是下载成功 meta/version 与 processed 重处理标记的 owner，正式下载以 repository batch 发布并在文件失败时回滚。
- 指定 CLI 的 0.1.4 安装是本仓库 editable 安装；当前下载版本为 `sec_pipeline_download_v1.2.0`。
- 原调用证据确认准确 argv、exit 0；source catalog 有 79 份文档。缺图索引完整文件包含 93 行、66 份文档，其中 `financial_content_unresolved=true` 标记 29 行、15 份文档；标记不能替代图片业务内容判断，也不能把这些行全部称为财务表。
- 2019 实例：本地 HTML 与 catalog hash 一致；17 处图片引用对应 15 个去重图片，均未落盘、均未登记。远端 HTML 和三个指定财务页 JPEG GET 均为 200。
- 2025 实例：本地 HTML 与 catalog hash 一致；12 个演示图片均未落盘、均未登记。远端 HTML 和第 001、012 张 JPEG GET 均为 200。
- 远端只抽查上述五张图片，尚未声称全部依赖可获取；详情见 `docs/validation/sec-html-image-assets-remote-preflight.json`。SEC_USER_AGENT 值未输出或保存。

## 目标与成功信号

1. 对正式下载已选择的 SEC HTML，发现其实际引用且属于同申报的图片，正式下载并登记为可通过来源仓储寻址的资产；不按 ticker、accession、样例图片名或 15 份集合硬编码。
2. 为已有下载但未包含图片的来源提供明确、可执行的补齐方式，遵守现有下载版本、来源指纹、文档版本和 processed 重处理规则。
3. 图片属于已接受 HTML 的必要下载依赖，不通过猜测图片是否是财务表、logo 或演示页来静默丢弃。必要依赖发现/下载失败时，结果和诊断如实反映失败，不发布或标记新的完整结果；既有 publication 按事务规则保留。
4. 在独立临时 base 验证真实 TSM 两个实例的新下载、从旧下载状态增量补齐、metadata/URI/hash/文件集合一致、版本与指纹行为、重复执行、必要图片失败诊断；受影响测试和 pyright 通过。
5. 最终给出修复 commit、新 draft PR、双路 reviews 和裁决、验证证据、剩余风险，以及指定实际 CLI 如何启用修复并执行补齐。

## 非目标与边界

- 不做通用爬虫、外站递归、跨申报资源抓取、OCR 或财务数值解析。
- 不改变不相关 6-K 筛选、正文选择和其他来源 provider 语义，不把所有申报图片无条件下载。
- 不新增独立于现有仓储的图片存储、下游补偿或兼容层；优先复用远端描述符、transport、来源资产及事务发布契约。
- 语义 owner：SEC downloader 持有依赖发现、同申报地址边界和 transport；SEC 下载 workflow 持有补齐/跳过/失败状态；source upsert 与 storage 持有指纹/版本发布及可寻址资产。具体最小设计在确认后的 plan 中确定。
- 原业务 workspace 与证据目录只读，仅读取下载证据与来源，不读调用方其他业务文件；验证使用独立临时 base，不手工补文件或覆盖原业务来源。
- 不 clear 当前会话、不改无关工作；只自动推进当前修复分支与 draft PR，merge/部署等另行确认。

## 后续执行契约

用户确认后，总控通过 sub-agents runner 子进程派发：gpt-6-sol 负责 plan/implement/fix，mimo 与 ds-flash 在各 review gate 同时并行 review；plan review 使用 planreview，code/aggregate/PR review 使用 deepreview。总控核对 artifacts 与事实、裁决 findings、执行 gate checkpoint，并持续推进至 final closeout。

## 当前 decision / validation / docs / risks

- Decision：修复成立；用户已明确确认目标契约及五项成功信号并授权自动推进至 final closeout，merge/部署仍另行确认。确认原文："代用户确认该目标契约、非目标、边界和五项成功信号，授权进入 plan，随后按既定 gateflow 自动推进至 final closeout。"
- Validation：preflight、相关 owner 代码、指定证据、两个本地 HTML 与远端抽查已核查；尚未运行实现测试或 pyright。
- Changed files：本目标 artifact 与远端 preflight JSON；生产代码未修改。
- Docs decision：实现时检查 fins/tests/root README 各自更新约束，按实际行为变化更新。
- Blocking open questions：无。目标确认 gate 已通过。
- Residual risks：未核查的图片可用性及补齐/失败/版本行为均 covered by later approved slice（将在用户确认后的 plan 中落实当前目标）；外站/跨申报资源和数值提取 assigned to later work unit（本修复排除，owner 为后续需求提出方，本次不承诺处理）。
- Artifact path：`docs/plans/sec-html-image-assets-goal.md`。
