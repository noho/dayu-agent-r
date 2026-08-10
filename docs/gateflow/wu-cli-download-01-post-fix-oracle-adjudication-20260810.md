# `dayu-cli download` post-fix Oracle 裁决

## 1. 身份与证据

- Work unit：`WU-CLI-DOWNLOAD-01`
- 产品 HEAD：`3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- 观察报告：`/Users/leo/workspace/.dayu-cli-ci/download-postfix-20260810T041254Z/observed-behavior.md`
- 观察报告 SHA-256：`be0c3c4cbc6a7b27877bd156cd7528ef33bd87f9e8fe097f8fdc09299886f6a6`
- 当前状态：`adjudicated-pending-fix-and-rerun`

本文件只记录用户对 post-fix 真实运行的裁决以及由裁决产生的修复项和覆盖 gap。修复、补跑并再次裁决前，不得把 download Oracle、scenario registry 或 readiness 标记为 ready。

## 2. 已接受观察

- O01：静态 usage、limits、CSV 拒绝与重复 option last-wins，接受。
- O02：US/CN/HK alias 与 bare ticker canonicalization，接受。
- O03：SEC 日期 hard bounds 与 SC13 选择边界，接受。
- O04：普通 download/overwrite 不删除未选择的历史 filing，接受。
- O06：CN/HK missing period 独立投影，不伪造 candidate outcome，接受。
- O07：SEC User-Agent fail-closed 与 provider transport failure 分类，接受。
- O08：download 可并发，只有 SEC 使用跨进程 shared throttle，接受。
- O09：三个阶段的一次 Ctrl+C 协作取消、canonical cancelled terminal、exit 130、清理与原样重跑，接受。
- O10：physical/meta size 或 digest 不一致时，无论是否带 `--overwrite` 都自动修复，接受。
- O11：业务 summary/outcome、bounded rows、logging 与 secret/contact 不泄漏，接受。
- O13：单 operation downloaded+provider-failed 暂无安全、可重复公开触发方式，接受登记为 `defensive/unreachable`；owner test 不冒充 full-real PASS，未来自然出现时补录真实证据。
- O14：atomic publication 微窗口暂无生产后门以外的稳定触发方式，接受登记为 `defensive/unreachable`；公开可操作取消与 recovery owner tests 不冒充真实 publication kill。
- O15：接受其 closeout 方法，但 DL-F12、DL-F13、DL-F14 修复并补跑前不得生成 download readiness PASS。
- O16：A股裸默认窗口的9份真实下载、Docling 转换、manifest/meta 持久化、约五年默认窗口和 production process 可消费性，接受；其错误的 effective forms/missing 另登记为 DL-F14。

## 3. DL-F12：`--overwrite` 与 `--rebuild` 必须互斥

### 用户裁决

O05 观察到的 `--overwrite --rebuild` 组合成功行为不正确。

### 冻结目标行为

- `--overwrite` 与 `--rebuild` 是互斥的公开 download options。
- 同时提供时必须在业务 operation、网络访问和 workspace 写入前作为 usage error 拒绝，exit 2，并提供可行动的错误说明。
- `--overwrite` 单独使用时仍表示重新获取并原子替换本次选中的远端 source。
- `--rebuild` 单独使用时仍表示只基于本地完整 source 重建 download-owned meta/manifest；不联网、不覆盖 source bytes、不运行 process、不修改 processed/reprocess 状态。
- 原 scenario 中的组合成功 case 必须删除，以 mutual-exclusion rejection case 替代；不得保留兼容分支。

### 修复后必跑

- `--overwrite --rebuild` 与反向 argv 顺序均 exit 2、无网络、无 workspace 业务写入。
- SEC 与至少一个 CN/HK source 分别重跑 plain、`--overwrite`、`--rebuild`，并继续检查 source/meta/processed、日志与实际产物。

## 4. DL-F13：腾讯 HK Q2/Q4 结果材料漏选

### 直接证据

- 腾讯官方业绩页列出“腾讯公布二零二五年第二季业绩”，发布日期为 2025-08-13；它不同于本轮下载到的 2025-08-26 中期报告。
- 腾讯官方业绩页列出“腾讯公布二零二五年年度及第四季业绩”，发布日期为 2026-03-18；它不同于本轮下载到的 2026-04-09 2025年年度报告。
- O12 的裸 `0700` 结果只有 FY 2021～FY 2025、Q1 2025、H1 2025、Q3 2025、Q1 2026，并把 Q2/Q4 报为 missing。

### 用户裁决

O12 当前行为不正确。腾讯实际发布的 Q2 与合并年度/Q4 结果材料不能被报为 missing；Q2 不能由 H1 报告替代，合并年度/Q4 业绩公告也不能由后来发布的年度报告替代。

用户进一步冻结港股通用材料身份：中期报告为 H1、年度报告为 FY、中期业绩公告为 Q2、年度业绩公告为 Q4；这是港股普遍采用的材料/期间映射，不要求公告标题或正文额外出现“第二季度/第四季度”字样。腾讯特定事实只在于其四类材料均已由真实来源和实际产物证明存在且彼此独立。该映射仍不表示 Q1～Q4 都是所有港股发行人的 mandatory missing 集合；Q1/Q3 等其它季度材料继续按发行人实际披露发现。

### 修复边界

- 先从 HKEX 原始候选、provider discovery、期间分类、候选选择与 storage identity 的直接数据定位唯一 root cause；不得预设是 scraper、分类器或 summary 的单一问题。
- 修复必须落在实际拥有错误语义的 owner boundary，不得在 CLI summary 下游伪造 Q2/Q4，不得用腾讯特例、标题硬编码或兼容 alias 补救。
- 如果同一披露同时承载年度与第四季业务信息，必须由正式文档/期间 contract 明确其 identity 与 period projection；不能让一个 manifest 单值字段偶然丢失另一业务期间，也不能无依据复制文档。
- 不得把 Q1～Q4 硬编码为所有港股发行人的 mandatory material；missing 只能表达当前市场/发行人/请求下适用但未发现的期间。

### 修复后必跑

- fresh workspace 裸运行 `dayu-cli download --ticker 0700`。
- 对照腾讯官方披露，实际检查 Q2 结果、H1 中期报告、Q4 结果和 FY 年报均被正确发现、分类、下载、转换和持久化。
- 对账 screen、summary、missing periods、PDF/Docling JSON、filing manifest、meta、source URL 与后续可消费性。

## 5. DL-G05：A股裸默认窗口真实观察

已在 fresh workspace 对 `600519` 完成与 O12 等价的 A股高成本裸命令覆盖。完整报告：`/Users/leo/workspace/.dayu-cli-ci/download-cn-bare-calibration-0uNsYI/observed-behavior.md`。

真实执行：

```text
dayu-cli download --base /Users/leo/workspace/.dayu-cli-ci/download-cn-bare-calibration-0uNsYI/workspace --ticker 600519
```

观察到 exit 0，`discovered=9 downloaded=9`，实际存在9份 PDF、9份 Docling JSON、9条 complete manifest，并由 production process 成功消费 FY 2025。有效窗口为 `2021-06-11..2026-08-10`；实际材料为 FY 2021～FY 2025、Q1 2025、H1 2025、Q3 2025、Q1 2026。

### 用户裁决

A股规则只要求年度、半年度、前3个月和前9个月报告，即 `FY,H1,Q1,Q3`。当前 CLI 却把 `FY,H1,Q1,Q2,Q3,Q4` 投影为 effective forms，并把制度上不适用的 Q2/Q4 显示为 missing。

用户接受实际下载/转换/持久化/可消费性与默认窗口选择；A股 bare-default forms/missing UI 判为不正确。

## 6. DL-F14：市场适用的默认 forms 与 missing 语义

### 冻结 CI/Oracle 规则

- A股默认集合是 `FY,H1,Q1,Q3`。独立 Q2/Q4 在该市场制度下不适用，不得进入 effective forms，也不得显示为 missing。
- 港股主板 effective/missing 基础集合仍为 FY/H1；材料身份按 `年度报告=FY`、`中期报告=H1`、`中期业绩公告=Q2`、`年度业绩公告=Q4` 冻结。Q1/Q3 等其它季度结果按发行人实际披露发现，不能冻结为所有港股发行人的必有文档。
- “可选披露”不等于“允许系统漏选”：当选定发行人实际发布了季度材料时，CI 必须用发行人/交易所公开来源核对 discovery、分类、下载与持久化。
- 腾讯 `0700` 已确认实际发布2025年 Q2，以及合并年度/Q4业绩材料；DL-F13 必须继续修复，不能因为港股季度披露 optional 而关闭。

### 修复边界

- market-specific form policy owner 必须产生市场适用的默认集合和 missing eligibility；CLI 只投影 typed truth，不得自行隐藏 Q2/Q4。
- 不得把 A股 Q2/Q4作为 H1/FY兼容 alias 暗中保留，也不得为腾讯或 `0700` 写 ticker/title 特例。
- HK discovery/classification 必须基于 provider 原始候选与正式期间语义识别发行人实际材料；mandatory baseline 与实际可选材料 discovery 是两个独立判断。

### 修复后必跑

- fresh A股 bare-default：effective forms 只含 `FY,H1,Q1,Q3`，不存在错误 Q2/Q4 missing；实际产物和本次已接受的9份选择结果对账。
- fresh 港股主板 baseline issuer：effective/missing 仍只承诺 FY/H1；实际材料可观察为 FY 年度报告、H1 中期报告、Q2 中期业绩公告和 Q4 年度业绩公告。没有 Q1/Q3 等其它 optional quarter 时不得误报产品失败。
- fresh 腾讯 `0700`：实际 Q2、H1、合并年度/Q4业绩材料和年度报告分别正确发现、分类、下载、转换和持久化；不存在把 H1/FY当作 Q2/Q4替代的情况。

## 7. DL-F12～F14 修复后补跑裁决与 DL-F15

修复后产品 HEAD 为 `54dd750a2e300e943eb25d9e49c09d31145ef1fb`；真实观察报告为
`/Users/leo/workspace/.dayu-cli-ci/wu-cli-download-02-postfix-20260810-A9vLZQ/evidence/observed-behavior.md`，
SHA-256 为 `7ca07d76a6d0d5ed37a5c4b54917f08262bd8a5203bf2d31cc7781da4fa2e666`。

用户接受以下 post-fix 行为：

- DL-F12：`--overwrite` 与 `--rebuild` 两种 argv 顺序均在业务执行前 exit 2，单独使用时语义不变。
- DL-F14/CN：裸 `600519` effective forms 为 `FY,H1,Q1,Q3`，9/9 下载转换并由 production process 9/9 消费，且不报告 Q2/Q4 missing。
- DL-F13/HK：港股通用分类 `中期报告=H1`、`年度报告=FY`、`中期业绩公告=Q2`、`年度业绩公告=Q4` 正确；腾讯四份目标材料的 source、URL、document、PDF、Docling、meta、manifest 与正文期间证据均独立且充分。

补跑同时发现 DL-F15：Docling attempt chain 在第一次转换失败后复用同一个 `DocumentStream`。第一次 converter 已关闭底层
`BytesIO`，第二次 backend 因而稳定出现 `I/O operation on closed file`，使声明的 backend/device fallback 失效。正确 owner
是 `dayu/documents/docling_runtime.py::convert_pdf_bytes_with_docling` 与其 attempt 输入装配边界；每个 attempt 必须从 immutable
raw PDF bytes 新建独立 stream。修复后须用真实首次失败触发后续 attempt，并证明成功转换、无 closed-stream 错误、实际产物完整且
后续 process 可消费。
