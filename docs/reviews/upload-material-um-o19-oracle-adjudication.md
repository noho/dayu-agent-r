# upload_material 第一轮校准：UM-O19 用户裁决

裁决日期：2026-09-28。用户先确认“这些格式的文件上传时都要转成docling”，进一步明确“抽取内容是否准确不在项目职责范围内”，随后要求“这项结束了？下一项”。本文件登记该项最终裁决及证据补跑任务 `UM-O19-E01`；补跑已于 2026-09-29 在独立 lineage 完成（见末节），产品代码未因本项修改，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。逐项核对 `evidence/formats/UM-F01-pdf` 至 `UM-F10-xlsx`、`UM-F14-uppercase-suffix`、`UM-F15-symlink-file` 的 `command.json`、`result.json`、`screen.txt`、`key-json-artifacts.json`；F01、F14、F15 另核 `filesystem-diff.json`，F15 与 `matrix-inventory.json`、`inputs/input-manifest.json` 对照。真实 CLI 的 12 次命令均 exit 0、stderr 为空、未超时、残留进程数 0；screen 均显示 `source_kind=material`、`status=ok`、`requested_files=1`、`stored_files=1`。每次 source meta 的 files 恰有一个 `original` 和一个 `docling` JSON；F01 文件系统 diff 亦确认这两种产物确已发布。均为 fresh CI-owned workspace、非 TTY CLI，不代表当前 HEAD 再验证。

| 场景 | exact CLI 输入文件 | source meta 文件记录 |
| --- | --- | --- |
| UM-F01 | `nvda-quarterly-trend.pdf` | 原 PDF + `nvda-quarterly-trend_docling.json` |
| UM-F02 | `vips-earnings-call.docx` | 原 DOCX + Docling JSON |
| UM-F03 | `msft-outlook.pptx` | 原 PPTX + Docling JSON |
| UM-F04 | `cme-10q.htm` | 原 HTM + Docling JSON |
| UM-F05 | `meta-exhibit.html` | 原 HTML + Docling JSON |
| UM-F06 | `meta-exhibit.xhtml` | XHTML 后缀的真实 HTML 字节 + Docling JSON |
| UM-F07 | `tencent-ai-panel.md` | 原 MD + Docling JSON |
| UM-F08 | `xiaomi-prospectus-notes.txt` | 原 TXT + Docling JSON |
| UM-F09 | `hkex-quarterly-results.csv` | 固定真实 XLSX 首表投影的 CSV + Docling JSON |
| UM-F10 | `hkex-quarterly-results.xlsx` | 原 XLSX + Docling JSON |
| UM-F14 | `材料 观察.TXT` | 大写 `.TXT`、中文和空格路径成功；原 TXT + Docling JSON |
| UM-F15 | `probe.txt` | 普通目标 TXT + Docling JSON；**CLI 没有收到 symlink 路径** |

F01/F02/F03/F04/F05/F07/F08/F10 来自冻结的真实材料语料；F06 是 F05 真实 HTML 字节改用 XHTML 后缀；F09 是 F10 固定 XLSX 首表的 CSV 投影；F14 是路径边界 fixture。以上来源以 `inputs/input-manifest.json` 为准。每个 original 对应的 Docling JSON 证明这些运行实际完成了转换和共同发布。

**F15 证据冲突**：`matrix-inventory.json` 中 UM-F15 的 `argv_template` 为 `{input:symlink-material.txt}`，`inputs/input-manifest.json` 记该路径是指向 `probe.txt` 的 run-local symlink；但实际 `command.json` 的 `--files` 参数已是 `.../inputs/probe.txt`，source meta 和 diff 中的 original 也叫 `probe.txt`。因此真实 CLI 只验证了普通 TXT 目标路径。路径在 CLI 调用前的中间环节发生了替换/解析；本项证据尚不能定位具体代码原因，也不能把 F15 标签当作 symlink 输入证据。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

明确格式上传契约：对 PDF、DOCX、PPTX、HTM、HTML、XHTML、MD、TXT、CSV、XLSX 这些受支持的 material 文件，**每个文件都必须进入 Docling 转换**；一次成功发布必须同时保存该文件的 original 和对应 Docling JSON，不能只保存 original 就报告成功。F01～F10 的具体输入均观察到这一结果；F14 另观察到大写 `.TXT`、中文和空格路径也完成转换与发布。单个样本不能证明任意同后缀内容均可成功转换；F06/F09 的派生输入来源须保留在 scenario 说明中，`.TXT` 的成功不泛化为所有大写后缀。

Docling 对原文的识别/抽取准确率由上游负责，不是本项目的 upload_material oracle 或产品修复条件。本项目负责正确传入原文件、处理转换失败、保存并投影实际转换结果；若发现失真，先排除本项目传入、写入或读取环节的错误。确认是 Docling 本身的识别问题后，保留输入、版本和输出证据向上游提 issue，不在本项目写特例修正抽取内容。

F15 仅接受其普通 `probe.txt` 上传成功这一事实；**不接受 run-local symlink 文件路径已验证的结论**，不把 F15 作为 symlink accepted scenario。符号链接路径可否作为材料文件输入，需要新证据。

## 已裁决证据修复项

### UM-O19-E01：F15 symlink 输入真实 CLI 补证

状态：**补证方向已接受并在独立 lineage 完成；证据收集修复，非产品代码修复**。

动机：计划场景与 exact argv 不一致，原始 F15 运行没有触达欲验证的 symlink 输入边界。不能靠场景标签、目标文件成功或最终文件系统结果反推 CLI 曾接收 symlink 路径。

owner：校准矩阵的命令展开/执行与证据采集边界，负责把计划输入按原路径传给 CLI，并记录未改写的 exact argv；产品 CLI 自己是否规范化路径是后续被测行为，不由采集器代做。

补证要求：先定位并修正计划模板到 `command.json` 的路径替换，确保新隔离 evidence root 中 `command.json --files` 明确为 `.../inputs/symlink-material.txt`；确认其指向的目标仍在该 root 内，保留 lexical symlink、target、hash；真实 CLI 重跑并采集双流、screen、exit、文件系统前后 diff、key JSON、durable/SQLite/process、manifest 与 digest。根据真实结果再裁决 symlink 接受或拒绝，冻结 F15 原始证据不改写，并明确补证 lineage。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。F01～F10 与 F14 可作为“各已测格式成功上传时原件和 Docling JSON 同时发布”的 accepted scenario 候选，待后续统一 registry 登记；F15 作为普通 TXT 成功证据可保留，但 symlink coverage 暂停。UM-O20 的 XBRL/XML/JSON converter 失败域另项处理，不从本项成功域外推。

## 裁决替代关系

本裁决取代冻结 observed report UM-O19 将 F15 归为 symlink 成功的过宽推断；原始 evidence 不改写，正式 registry/readiness 待后续统一登记。

## E01 后续补证状态（2026-09-29）

在独立 PR197 集成 checkout HEAD `45444785` 的 fresh evidence root `/private/tmp/dayu-o19-e01-formal.x8gq0rcm`，以未 `resolve()` 的 argv 数组把 lexical `inputs/symlink-material.txt` 直接传给真实 CLI；`command.json` 保留该 exact `--files` 值。运行 exit0、stderr 空，CLI path owner 随后规范为目标 `probe.txt`，source meta/manifest 同时发布该原件及 `probe_docling.json`。完整方法、前后树与边界见 `docs/gateflow/upload-material-o19-e01-evidence-20260929.md`；冻结 F15 原证据仍仅证明普通目标路径，不追溯改写。此补证不定义悬空/越界链接或保留 lexical 链接名的产品合同，O04/O23 资产路径规划仍须同源核对。
