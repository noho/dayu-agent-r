# UM-O20-E01：有效格式真实 CLI 补证（进行中）

- Gate：独立 evidence，非 O20-F01 产品修复 pass；日期：2026-09-29。
- 代码：隔离 `/private/tmp/dayu-upload-o20`，branch `codex/upload-material-o20`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；`PYTHONPATH` 显式指向该 checkout，`PYTHONDONTWRITEBYTECODE=1`。解释器 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python` 为 Python 3.11.15；依赖是**主工作区 venv**，不是独立 checkout 安装。Docling 2.127.0、docling-core 2.96.0；`find_spec("arelle")` 为 `None`，`pip show arelle-release` 未找到。
- 隔离证据 root：`/private/tmp/dayu-o20-e01.1NAhyk`。本 artifact 记录可重现观察，原始 stdout/stderr、输入和独立 workspace 文件均留在该目录；没有改写原冻结 evidence。

## 本轮生成的 Docling JSON 正样本

以当前 Docling `DocumentConverter().convert(source.md)` 转换 `# Material evidence\n\nRevenue was 123.\n`，返回 `ConversionStatus.SUCCESS`，再调用 `result.document.save_as_json(fresh_docling.json)`。生成文件 1236 字节、SHA-256 `35c0835d12347293aa0a31588738f16cda064d7922848ae05765d2761615f019`。第一次真实 CLI 使用 `EVID20` ticker，usage exit 2 且未进入上传，原因是 ticker 形态非法；该方法偏差的 `json.stdout/json.stderr` 保留，不算转换证据。

有效正样本真实 CLI：`python -m dayu.cli upload_material --base /private/tmp/dayu-o20-e01.1NAhyk/workspace --ticker AAPL --action create --forms 10-K --material-name fresh_docling_json --files /private/tmp/dayu-o20-e01.1NAhyk/fresh_docling.json --company-name 'Evidence Company'`。退出码 0；`json2.stdout` 依次有 preparing、started、completed、succeeded，摘要 `requested_files=1 stored_files=1`；`json2.stderr` 为空。`portfolio/AAPL/materials/material_manifest.json` 登记 `mat_1c4bd64312d1333929e55a2ab2c714a606fa9a94`，`ingest_complete=true`、`is_deleted=false`。同一 material 目录有原件 `fresh_docling.json`、派生 `fresh_docling_docling.json`、`meta.json`，后两者 meta `files` source 分别 `original`/`docling`，primary 为派生名，两个内容 SHA-256 均为上述 digest。此观察可将 Docling JSON 记为本 HEAD/本依赖环境的 **validated success**；不保证其它 JSON、Docling 版本或抽取准确率。

## 完整 XBRL instance 的当前失败及直接首因

正样本候选是 repo 既有 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928_htm.xml`，根元素 `<xbrl>` 且相对 taxonomy/xsd/linkbase 文件同目录齐备，instance SHA-256 `1bf6615f47d53f87b10fd036b647fbb4e9ad59db51667761b42ee6666bb2241c`。真实 CLI `--base /private/tmp/dayu-o20-e01.1NAhyk/workspace-xbrl --ticker AAPL --action create --forms 10-K --material-name xbrl_instance --files <该绝对路径> --company-name 'Evidence Company'` 退出 1；`xbrl.stdout` 显示 `failure_kind=content failure_code=docling_converter_execution requested_files=1 stored_files=0`；`xbrl.stderr` 为空；目录只有 company identity/meta，无 material 原件、Docling 派生、manifest。

同一解释器对同一 instance 直接调用第三方 `DocumentConverter().convert(path)` 的 `xbrl-backend.stderr` 明确在 Docling 2.127.0 `xbrl_backend.py` 导入 `arelle.Cntlr` 时抛 `ModuleNotFoundError: No module named 'arelle'`，再抛 `ImportError: The 'arelle-release' package is required to process XBRL documents. Please install it using pip install 'docling-slim[format-xml-xbrl]'`。因此**本次当前部署失败的直接首因**是 XBRL 可选运行依赖缺失；不能由当前实验回填冻结五次的当时首因，也尚不能声称安装依赖后完整 instance 一定成功。

## 后续与边界

- `UM-O20-F02` 的条件已触发：当前产品 capability 列出 `XML_XBRL`，标准安装 `pyproject.toml` 依赖未包含 `arelle-release`，此环境实际无法处理有效候选 instance。需独立 Gateflow goal/plan 选择使安装依赖与 capability 一致的最小方案，并在隔离安装/完整 taxonomy 样本上验证；不能只改 O20-F01 文案，也不能把用户文件错误当真实首因。
- E01 尚未完成全部要求：可选依赖安装后的 XBRL 正样本复测、taxonomy 网络/本地配置快照、SQLite/durable/process 证据与负样本复跑待补。当前 XBRL 不能记 validated success。

## 隔离依赖复试（01:13，仍非产品修复）

为检验“仅装可选包即可恢复”的假设，只向本证据 root 安装包，未修改主工作区 `.venv` 或项目依赖。`pip install --no-deps --target optional arelle-release` 取最新 2.45.3；再尝试装其声明依赖时解析器报 `jaconv>=1,<2` 无可用版本（PyPI 可见最高 0.5.0），故该最新版本在本次索引/平台不能成为可解析的完整安装。`--no-deps` 的直接转换先因缺 `isodate` 失败，仅说明该不完整 pilot 无效。

取 Docling 2.127.0 允许区间内的 `arelle-release==2.44.8` wheel，其元数据要求 `jaconv>=0,<1`；把 2.44.8 与 `bottle 0.13.4`、`isodate 0.7.2`、`jaconv 0.5.0`、`pyparsing 3.3.3`、`truststore 0.10.4` 仅装到 `optional244/`，其余依赖来自主 venv。以 `PYTHONPATH=optional244` 对同一 instance 直接调用 Docling，Arelle 导入已越过，但仍退出 1：`docling.backend.xml.xbrl_backend.XBRLDocumentBackend.__init__` 抛 `OperationNotAllowed`，明确要求 `enable_local_fetch=True` 或 `enable_remote_fetch=True` 才可加载 taxonomy；封装后为 `DocumentLoadError`/`ConversionError`。Dayu `build_docling_pdf_converter()` 只配置 PDF，XML_XBRL 保留 Docling 默认 option，因此两种 fetch 默认均为 False。当前 sample 的 schemaRef 指本地 `aapl-20240928.xsd`，该 xsd 又 import 多个 SEC/FASB/XBRL 网络 taxonomy；仅安装依赖仍不能证明一般 instance 成功。

这将 F02 的真实修复边界扩展为“**可解析的版本上限 + taxonomy 获取策略 + 输入/文件隔离 + capability 同源**”，不是单补一行依赖。上传路径目前按原始文件字节交给 Docling `DocumentStream`，XBRL backend 将 instance 复制进临时目录；即使开启 local fetch，原文件同目录 sidecars 能否随流提供亦须实证，不能从磁盘 fixture 存在推断。远程 taxonomy 获取涉及运行时网络/信任边界，不能在文案修复里暗开。完整可支持方案与暂时撤回 XBRL capability 的选择须独立 goal/plan 裁定。

## Docling 上游转换边界补证（01:34）

在同一隔离 `optional244` 依赖叠层，对磁盘上完整 AAPL fixture 显式构造第三方 `XBRLFormatOption(backend_options=XBRLBackendOptions(enable_local_fetch=True, enable_remote_fetch=False, taxonomy=<fixture 目录>))`，再调用第三方 `DocumentConverter`。此实验绕过 Dayu，不表示产品已配置该策略；它保留原 instance 与本地 xsd/linkbase 的相对位置，远程 taxonomy fetch 仍关闭。Arelle 初始化已通过，实际在 Docling 2.127.0 的 `xbrl_backend.py:344` 转换维度时 `dim_value.memberQname` 为 `None`，抛 `AttributeError: 'NoneType' object has no attribute 'localName'`，外层为 `RuntimeError: Pipeline SimplePipeline failed`；原始诊断保留在 `xbrl-local-taxonomy.stderr`。这直接证明对这份 instance，“装齐可解析的依赖并启本地 taxonomy”仍不保证成功；但未证明失败究竟由缺远程 taxonomy 导致无成员 QName，还是 Docling 后端对有效 explicit/typed dimension 的独立缺陷，不能把这个栈归因成唯一首因。后续若选择支持路径，应在受控完整 taxonomy 条件下复测，并把可归因的 Docling 内容抽取/转换缺陷整理为上游 issue 证据；项目不编写替代 XBRL 解析器。

## Docling 字节流与本地 taxonomy 的对照补证（约 05:10，本地时间）

在同一 Python 3.11 主工作区 venv 与隔离 `optional244` Arelle 叠层，不改仓库依赖、不改 Dayu 代码。构造一份极简合成 `simple.xml`/`simple.xsd`（含 `Revenue=123`，文件及 SHA-256 分别为 `/private/tmp/dayu-o20-e01.1NAhyk/simple-xbrl/simple.xml` `f65adbd60540881f33f0c1a2b55689a006812f18a36edd8164c8a4a9eb1f23ca`、`simple.xsd` `a977583e238165275c1a483d8f6b05c377d9629e752c1b4797bee7de9b5cd199`）。它只是调用机制探针，未作为独立合规 XBRL fixture 验证。直接第三方 Docling 2.127.0，三组都设置 `enable_local_fetch=True, enable_remote_fetch=False`：

| 输入/配置 | 第三方返回 | `export_to_markdown()` |
| --- | --- | --- |
| 合成 instance 磁盘 Path、`taxonomy=<合成目录>` | `ConversionStatus.SUCCESS` | `# simple.xml` 与 `<!-- missing-key-value-item -->`，没有 `123`。 |
| 同一合成 instance 的 `DocumentStream(BytesIO)`、不传 taxonomy | `SUCCESS` | 仅 `# instance.xml`，没有 `123`。 |
| repo AAPL 完整 instance 的 `DocumentStream(BytesIO)`、不传 taxonomy | `SUCCESS` | 仅 `# instance.xml`。 |

此对照的原始机器输出 `/private/tmp/dayu-o20-e01.1NAhyk/xbrl-variant-probe.stdout`，独立 stderr `/private/tmp/dayu-o20-e01.1NAhyk/xbrl-variant-probe.stderr` 为 0 字节，进程 exit0。调用是第三方 converter，不是 Dayu 真实 CLI；合成例是否完整符合 XBRL 规范未另证。Docling 的 `XBRLDocumentBackend` 对 `BytesIO` 只在其临时目录落一个 `instance.xml`，而 `taxonomy` 目录会整体复制进该临时目录；`enable_local_fetch=True` 单独打开时，字节流缺原 sibling taxonomy 仍可返回只有标题的成功状态。故不能据 `SUCCESS` 推断已解析事实，也不能让项目从 Markdown 是否含 `123` 自设抽取准确率 gate。项目可控制的依赖安装、fetch/输入隔离与 capability 说明仍需独立裁决；抽取准确性或 `memberQname` 根因只可在可复现后交 Docling 上游。

额外边界：本次源码阅读只证明 Docling 把 `enable_remote_fetch=False` 映射到 Arelle `webCache.workOffline=True`，且 `enable_local_fetch=True` 是准许加载 taxonomy 的入口条件；**没有**证明 Arelle 对用户 XML 中任意绝对 `file:` 引用做了沙箱限制。因此不能仅凭「远程关闭、实例复制到临时目录」就宣称本地读取受限。F02 设计如需打开 local fetch，必须以受控引用/进程文件系统边界的直接测试证明隔离，不能把转换 `SUCCESS` 当作安全性证据。
