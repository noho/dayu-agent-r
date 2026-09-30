# UM-O20-F02：隔离第三方探针原始证据

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol-34235ade
CANARY=gpt-6-sol-34235ade

- 日期：2026-09-29。worktree `/private/tmp/dayu-upload-o20-f02`，HEAD `9735800cb55a40336469593fa2fddae43c9c69ad`。被双路 review 否决的计划改动前 SHA-256：`65c55801fce6432602a7d216f7c18d15c5df57e3228b1b85cc1bf1f830fffd2d`。本文件是唯一新增 worktree 证据；所有可执行探针、合成输入、下载 wheel 和原始双流仅写在独立 `/private/tmp/dayu-o20-f02-probe.AdlwrW/`。没有改冻结 E01、产品、依赖、锁、测试或 README，也没有请求 taxonomy 网络资源、发布 issue 或使用真实用户资料。
- 前置已读：`AGENTS.md`、goal、冻结 E01、同 SHA Kimi/MiMo planreview、总控 adjudication、原计划；直接读取 Docling 2.127.0 `xbrl_backend.py` / `backend_options.py`、Arelle 2.45.3 wheel 内 `ModelInstanceObject.py` / `WebCache.py` / package manager、当前 Dayu 转换调用链。E01 的观察仍按其原始环境解释，下面的新探针不能回填 E01 当时 argv。
- 运行环境：Darwin arm64、Python 3.11.15、pip 26.0.1，主工作区只读解释器 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`；Docling 2.127.0、docling-core 2.96.0、docling-slim 2.127.0。Arelle 2.45.3 wheel 仅装到上述独立临时目录 `arelle2453/`，由 `PYTHONPATH=.../arelle2453:/private/tmp/dayu-o20-e01.1NAhyk/optional244` 供调用；后段旧目录只补该 venv 缺少的 Arelle 传递包。因此此调用是**第三方隔离探针**，不是完整生产安装或 Dayu CLI 成功。

## P1 版本真源、resolver 与 E01 矛盾

本轮从 PyPI 重新下载 `arelle_release-2.45.3-py3-none-any.whl`，SHA-256 `9474d0b01bbcde1d11c08aab831c08915be58507afecdb3fe3c560cd9391ef48`。直接 `unzip -p ... arelle_release-2.45.3.dist-info/METADATA` 得 `Version: 2.45.3`、`Requires-Python: >=3.10`、`Requires-Dist: jaconv<1,>=0`；E01 留存 2.45.3 `optional/.../METADATA` 与 2.44.8 `optional244/.../METADATA` 的 jaconv 声明也均为 `<1,>=0`。故 E01 所写“2.45.3 **声明** `jaconv>=1,<2`”不成立；但 E01 `arelle-deps.stderr` 确有该错误文字，保留其原观察。

本轮完整解析 **Arelle 2.45.3 的所有传递依赖**，不使用 `--no-deps`：

```text
cwd=/private/tmp/dayu-upload-o20-f02
argv=/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m pip install --dry-run --ignore-installed --only-binary=:all: --report /private/tmp/dayu-o20-f02-probe.AdlwrW/arelle-resolver-report.json arelle-release==2.45.3 -c constraints/lock-macos-arm64-py311.txt --index-url https://pypi.org/simple
exit=0
stdout: Would install arelle-release-2.45.3 ... jaconv-0.5.0 ...（22 项，完整原文见 arelle-resolver.stdout）
stderr: pip cache disabled 警告与版本更新提示，无 resolver 错误（完整原文见 arelle-resolver.stderr）
```

报告 `arelle-resolver-report.json` 为 175202 字节、SHA-256 `eb4be3fa941d4581d04946ebe15faa2f616ba6b1c7501c85a111cab4ffe0681b`；environment 为 Darwin/arm64，install 数 22，明确含 `arelle-release 2.45.3` 和 `jaconv 0.5.0`。原始双流 SHA-256：stdout `fee4c794c228fd40a479dac15fb3fe247f3f78ce6bc7c88e1327d50258b45680`，stderr `109f57a9b19d6c5ba023ac812029f39a07493f55c092c26fe6040f4d97f644cc`。这**重开** 2.45.3 候选，但没有证明项目全树或其它平台可解。

附加失败命令：同一解释器执行 `pip install --dry-run --ignore-installed --only-binary=:all: --report /private/tmp/dayu-o20-f02-probe.AdlwrW/full-tree-report.json arelle-release==2.45.3 docling==2.127.0 docling-slim==2.127.0 -c constraints/lock-macos-arm64-py311.txt --index-url https://pypi.org/simple`，exit 1；原始 `full-tree.stdout` SHA-256 `2730c1157018001275be54c72615cba6eb5766c6f37a76efe1ecf0d7791fc3d2`、`full-tree.stderr` SHA-256 `4261805c6a56174312d2d08db01cc2ceea7583115fa821df3f16a9b0cf2f025d`。stdout 末尾显示 `pylatexenc==2.10` 在当前索引没有匹配 binary distribution，stderr 为 `ResolutionImpossible`；失败故无 report 文件。该命令的 `--only-binary=:all:` 比 README 标准安装更严，不能称为项目依赖真实冲突；本轮未完成本项目 editable 全树解析、安装或 `pip check`。E01 的 `arelle-deps.stdout/.stderr` 未保存原始 argv、pip report 或索引响应，故无法从该错误唯一判定是手写错误约束、索引元数据异常还是缓存污染；不得把其中一种猜测写为根因。可确定的是**本轮一手 wheel 与本轮完整 Arelle resolver 均不支持“2.45.3 自身要求 jaconv 1.x”**。

## P2 自包含 typed dimension：合法性与 Docling 直接复现

合成 `typed.xml`（948 字节，SHA-256 `a0e3238addf2d368a0a92a9a49cfc221cf35ced9ef96c52e63421a0f635fe40a`）与同目录 `typed.xsd`（870 字节，SHA-256 `a75d6fd1083d3223288bba99f7e7da271a1b0f78c8cde9d5451dba39b1acab91`）无 SEC/FASB taxonomy；schemaRef=`typed.xsd`。XSD 声明 `Revenue`、`RegionAxis` 的 `xbrldt:typedDomainRef="typed.xsd#t_RegionDomain"` 和 `RegionDomain`；instance 含带 `xbrldi:typedMember dimension="t:RegionAxis"` 的 context、USD unit 与该 context 的 numeric `Revenue=123`。合成命名域 `example.invalid` 只作标识；远程获取始终关闭。两份完整原始 XML 在临时目录，因样本极小，可由该两个文件直接重跑。

Arelle 自身离线验证（不是自制 parser）：

```text
env=PYTHONPATH=/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453:/private/tmp/dayu-o20-e01.1NAhyk/optional244 PYTHONDONTWRITEBYTECODE=1
argv=/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m arelle.CntlrCmdLine --file /private/tmp/dayu-o20-f02-probe.AdlwrW/typed.xml --validate --internetConnectivity offline --validationExitCode --logLevel INFO
exit=0
stdout=[info] loaded in 0.01 secs ... typed.xml\n[info] validated in 0.00 secs ... typed.xml
stderr=空
```

原始 `arelle-validate.stdout` SHA-256 `e51c57832a9db4b377affff1a1773ce85a1e4aac43169526ecf8fcd8aa46319e`，stderr 为空文件 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。`--validationExitCode` 加 exit 0 与无 validation error 是本微型 instance 的**Arelle 2.45.3 离线合法性证据**；不代表其它 taxonomy 或内容准确率。

直接 Docling 调用的完整 Python argv 为 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python /private/tmp/dayu-o20-f02-probe.AdlwrW/docling_probe.py`，环境同上。脚本 SHA-256 `40fb1b77b4652b0be8279f74ff6dad287423ffb675e438c2985e24f28cbf7f9b`，只建 `DocumentConverter(allowed_formats=[XML_XBRL], format_options={XML_XBRL: XBRLFormatOption(backend_options=XBRLBackendOptions(taxonomy=<上述目录>, enable_local_fetch=True, enable_remote_fetch=False))})`，依次送同一 XML 的 `Path` 和 `DocumentStream(BytesIO)`。进程 exit 0 是**探针脚本捕获异常后的 exit**，不是转换成功；`docling-probe.stdout` 两次均记 `RuntimeError("Pipeline SimplePipeline failed")`，`cause=AttributeError("'NoneType' object has no attribute 'localName'")`。`docling-probe.stderr` 两段完整栈都落在 Docling `xbrl_backend.py:344` 的 `dim_value.memberQname.localName`。原始双流 SHA-256：stdout `a39373cecc4073c0005a7c2dcea9a387a30f106ce1086c7969828f760badddd0`，stderr `e72c8e78c24a03f00d3f01fbda5c68541ba1a715315324ddc944368efa2c038d`。

Arelle 2.45.3 `ModelInstanceObject.py:1504-1513` 只在 `isExplicit and xValid >= VALID` 时给 `memberQname`，typed 时按设计给 `None`；Docling 2.127.0 无 typed 分支即解引用。这把**合法 typed dimension 的 Docling 导出崩溃**定位为 Docling owner。相反，explicit 成员在 `xValid < VALID`（例如 taxonomy 缺失或失验）时也可能给 `None`，这是另一支，不能凭相同异常栈宣称它同样是 typed 缺陷。E01 AAPL 夹具离线 Arelle 加载探针 `arelle-aapl.stdout/.stderr` 给出 `fact_count=1108`、`error_count=0`，首批 typed 行 `xValid=6, memberQname=null`，explicit 行 `xValid=4, memberQname=us-gaap:CommonStockMember`；未执行完整 AAPL taxonomy 许可/闭包审计。对同一合成 XML 的 `DocumentStream` **去掉 taxonomy** 的第三方对照，exit 0、`ConversionStatus.SUCCESS`、Markdown 只有 `# instance.xml`（原始 `no-taxonomy.stdout/.stderr`，stdout SHA-256 `26bd0bc70c6b1720d686eb5a214b57c4126e7c2e86cee19fda480239990371b8`，stderr 为空）。因此缺 sidecar 可表现为无事实的标题成功，不能当 XBRL 正样本。

## P3 taxonomy/sidecar 与强制访问边界

一手源码：Docling `XBRLBackendOptions.taxonomy` 只接受**目录**，backend `xbrl_backend.py:125-148` 将整个目录 `copytree` 到私有临时目录；仅收集复制后目录**顶层**的合法 `.zip` 作为 Arelle `taxonomyPackages`；`DocumentStream(BytesIO)` 固定落为 `instance.xml`，可能覆盖同名 sidecar。Arelle package manager 要求 zip 中 `META-INF/taxonomyPackage.xml`，并从 `META-INF/catalog.xml` 读取 OASIS `rewriteURI/rewriteSystem` 映射；本轮**未完成 zip+catalog 的可用性实测**。本轮成功验证的是裸目录相对 `typed.xsd` 的 Arelle 加载，Docling 亦确实读到 typed fact 才在维度导出处崩溃。Dayu `DoclingUploadService` 只把 bytes+name 传给闭合 `DoclingConversionConfig`/进程转换器；现有 CLI `--files` 的每个文件都会各自转换，没有 sidecar 配置通道，不能用添加 XSD 为第二材料文件代替。

合成文件逃逸探针：`trusted/typed.xml` 的 schemaRef 改为 `file:///private/tmp/dayu-o20-f02-probe.AdlwrW/outside-sentinel.xsd`，后者是由合成 XSD 复制的唯一外部 sentinel，位于 `trusted/` 外。使用同一 Arelle `--validate --internetConnectivity offline --validationExitCode`，exit 0，原始 `file-escape.stdout/.stderr` 留存；随后同一 offline `Cntlr` 模型检查 `facts=1, concepts=59, errors=[]`，`taxonomy_docs=['/private/tmp/dayu-o20-f02-probe.AdlwrW/outside-sentinel.xsd']`（`file-escape-inspect.stdout/.stderr`）。这是**确实加载受信根外合成 XSD**的直接证据，证明 `workOffline`、Docling 临时目录和预扫描都不能充当文件读取边界；没有读取真实敏感文件。Arelle `WebCache.py:545-610` 对非 HTTP(S) URL 直接返回本地路径，`:1033-1064` 的 `getheaders/geturl/retrieve` 仍有 `opener.open`，故 `workOffline` 也不能单独充当所有网络 API 的强制沙箱。本轮未建立网络端点 trace，不能宣称网络零请求已由 OS 证明。

强制机制实测：macOS arm64 有 `/usr/bin/sandbox-exec`，对仅拒绝上述合成 sentinel 读取的最小 profile 执行 `/bin/cat` 时 exit 71，stderr=`sandbox-exec: sandbox_apply: Operation not permitted`，stdout 空（`sandbox.stdout/.stderr`）；故本托管环境**无法验证**此机制，更不能把它当可部署三平台方案。`docker` CLI 存在但 `docker info` exit 1，daemon socket 不存在；仓库无 `.github/workflows`。Linux/Windows 真实 runner、本地文件与网络双边界执行轨迹均未取得。任何 OS 机制候选须在真实对应平台证明，不能由 macOS 推断。

## 探针结论与未证清单

1. 2.45.3 Arelle 的真实 jaconv 要求可由本机完整 Arelle 依赖解析；2.44.8 不能再因 E01 那条错误解释被提前锁为唯一候选。E01 当时错误的精确成因因 argv 缺失仍为未证。
2. 自包含、Arelle 验证通过的 typed instance 在 Docling 2.127.0 + Arelle 2.45.3 Path/Stream 两路直接复现导出崩溃；上游 owner 指向 Docling。用户已条件授权向真正上游提 issue；本轮用户明确禁止发送，后续复核最小证据包后按该授权处理，无需重复授权 gate。
3. 受控 taxonomy 文件/网络强制边界、三平台安装、zip/catalog、真实财报有效正样本、Dayu CLI material manifest 成功均**未证明**。因此原计划 S1/S2 成功承诺必须撤下，后续只能先走 evidence/probe slice 与同版双路 plan review。

修订计划最终 SHA-256：`4d01db5528156e30ea177b8c76fb2e081f7d505bbe08c2d92417f138462f9deb`（`upload-material-o20-xbrl-runtime-plan-20260929.md`）。此 SHA 是下一次同版 Kimi/MiMo plan review 的唯一计划输入；本轮不执行该 review。

## 总控后续补证：项目全树 macOS arm64 dry-run

总控在 Sol 探针退出后另行执行 README 1.1 节相同 extras 与 macOS arm64 lock 的**有依赖**解析：`/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m pip install --dry-run --ignore-installed --report /private/tmp/dayu-o20-full-resolver-20260929/report.json -e '.[test,dev,browser]' arelle-release==2.45.3 -c constraints/lock-macos-arm64-py311.txt --index-url https://pypi.org/simple`，cwd `/Users/leo/workspace/dayu-agent-r`，stdout/stderr 独立保存同目录 `stdout.log`/`stderr.log`，进程 exit0。pip report 172 个待安装项，environment CPython 3.11.15/Darwin arm64，选中 `dayu-agent 0.1.4`、`docling 2.127.0`、`docling-slim 2.127.0`、`docling-core 2.96.0`、`arelle-release 2.45.3`、`jaconv 0.5.0`。report SHA-256 `5acab0b9012d47e1637a707a965539e54bbcb6a51e3f423e6db76c834bab417a`；stdout `852911e43d2521cfb34a3ad1054258856cce9a0f6e9458791cb82f61f1a643b6`；stderr `109f57a9b19d6c5ba023ac812029f39a07493f55c092c26fe6040f4d97f644cc`，stderr 仅 pip cache 不可写和版本提示。此前 `--only-binary=:all:` 的 pylatexenc 失败是额外方法条件造成，本次真实 README extras 解析在本平台没有依赖冲突。此补证仍**不是** fresh venv 实际安装/`pip check`，不证明 Linux/Windows lock、隔离边界或 CLI 转换成功；P0-A 尚未完成。
