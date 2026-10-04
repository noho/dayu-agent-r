# upload_material 第一轮校准：UM-O26 用户裁决

登记日期：2026-09-28。状态：**用户已接受本项及字段归属修正，正式 oracle/scenario 尚未更新**。本项核对固定的美、中、港三份真实材料单文件上传。未发现独立产品修复项；冻结 observed report 的字段归属表述过宽，证据解释修正 `UM-O26-E01` 已接受，不改写原始报告。

## 冻结输入与真实命令

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对的 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

`inputs/input-manifest.json` 记录三份输入均取自用户授权的只读真实材料 corpus，复制到冻结 inputs 后 SHA-256 与来源一致。每条真实 CLI 命令的 cwd 为 run 下 `repo`、stdin=`DEVNULL`，分别使用 CI-owned fresh `--base`，action=`auto`：

| 场景 | 输入及 SHA-256 | 关键业务参数 | 输出 document ID |
| --- | --- | --- | --- |
| UM-R01（US） | `msft-fls-disclaimer.docx`，`975a287731898d5415226caec0293b5f39fd5fb08ab3d7d7e4d042a53483a6fe` | `--ticker MSFT,MSFT.US --forms 8-K --material-name 'FLS Disclaimer' --fiscal-year 2019 --fiscal-period Q2 --company-name 'Microsoft Corp.'` | `mat_a9864e9ea49aff01eb286513d2b4a533425aea49` |
| UM-R02（CN） | `maotai-2025q1.pdf`，`f3197b2a4ef7b617bec762b99613eecaf8ea27d1950d4bed5e9ce5f1943d1128` | `--ticker 600519,600519.SH --forms MATERIAL_OTHER --material-name '贵州茅台 2025Q1 跟踪材料' --fiscal-year 2025 --fiscal-period Q1 --company-name 贵州茅台` | `mat_70f1c12b6d1efe731f38ba55467cbb677f58480a` |
| UM-R03（HK） | `tencent-2019q1-call-notes.pdf`，`a6fcfa940bdbf8c512e249c4ca02185a194fe5c16a9681fc50c09cf111db1dfb` | `--ticker 0700,0700.HK --forms MATERIAL_OTHER --material-name '腾讯 2019Q1 电话会纪要' --fiscal-year 2019 --fiscal-period Q1 --company-name 腾讯控股` | `mat_1784891741790344863048b780f46adc5e6a6b1e` |

精确命令、base、环境见各场景 `command.json`；文件来源和原始字节摘要见 `inputs/input-manifest.json`。三个 `result.json` 均为 exit 0、execution_outcome=success、evidence_status=sufficient、未超时、残留进程 0；`screen.txt` 均为 upload.completed、status=ok、requested=stored=1、stderr 为空。`filesystem-diff.json` 各显示新增一个 material document 的 identity/meta、一个 original blob、一个 Docling JSON blob 和 material manifest，且无删除或修改；`key-json-artifacts.json` 的两个文件条目 SHA-256 与物理 diff 对应，`primary_document` 指向唯一 Docling JSON。SQLite database_count=0；Host/EventLog/Trace/Memory/job 被查询但不存在，这只说明本 direct CLI 运行的观测边界。

公司 owner 的 `portfolio/<ticker>/meta.json` 分别持久化 `ticker=MSFT/600519/0700`、`company_id=MSFT_US/600519_SSE/0700_HKEX`、`market=US/CN/HK`、给定公司名称、`ticker_aliases=[]`。source document `meta.json` 持久化 canonical ticker、company_id、material name、form type、fiscal year/period、document ID、`document_version=v1`、`ingest_complete=true` 和两个文件；material manifest 的对应条目有 document ID、form type、material name、version、指纹与 provenance 等摘要，**没有** fiscal year/period，也没有 aliases/company name。三个实际 document ID 与当前 `build_material_ids(form_type, material_name, fiscal_year, fiscal_period)` 的 SHA-1 seed 规则逐项重算相符；这是代码规则与单次结果的一致性，非同一身份重复上传实验。

## UM-O26-E01：冻结摘要的字段归属解释修正

状态：**用户已接受的证据解释修正，不是产品代码缺陷或修复授权**。冻结 observed report UM-O26 写“canonical ticker、aliases、company、form/name/year/period 写入 source meta/material manifest”，容易被解读成全部字段都存在于这两处。raw JSON 不支持这个合并表述：别名在三次命令中虽被声明，三个持久化 company meta 的 `ticker_aliases` 均为 `[]`；source meta 不含别名，公司名称仅在 company meta；year/period 在 source meta，不在 material manifest。`dayu.fins.ticker_normalization.build_company_ticker_identity` 把与 canonical 等价的后缀形式规范化后去重，因此本三组 `MSFT.US`、`600519.SH`、`0700.HK` 并未形成独立 accepted alias；不能用这三次成功证明“异名 alias 已持久化”或将空列表登记为缺陷。正式 scenario 需逐层断言实际字段，不复制合并摘要。UM-O12 的真实异名 alias 冲突裁决另行保留。

## Accepted 行为与边界

接受限于这三份固定输入、三个市场、所给参数的真实单文件上传成功：一个原件各经 Docling 转换，CLI stored count=1、实际发布两个资产、source meta 与 material manifest 的各自字段一致、document ID 与材料身份规则相符。单文件自动主文件符合已接受 UM-O25；派生件的具体旧 `<stem>_docling.json` 名称不固化为公共契约，以便 UM-O23 的统一命名修复。真实文件的内容抽取准确性属于 Docling 上游，本项只确认转换产物及本项目的持久化契约。三个样本不能外推为所有 DOCX/PDF、所有市场组合、所有别名形态都正确。

本项无独立产品修复登记；`UM-O26-E01` 是已接受的冻结报告解释纠偏。当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品实现。正式 scenario 应引用每个 raw command/result、input manifest、screen、filesystem diff、key JSON，字段断言按真实 owner 分层。

直接证据路径：

- `inputs/input-manifest.json`
- `evidence/real/UM-R01-us-msft-real/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/real/UM-R02-cn-600519-real/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/real/UM-R03-hk-0700-real/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`
