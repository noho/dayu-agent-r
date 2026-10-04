RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-dc946802

# S3 集中修复 US3-C01

label：upload-material-unified-s3-closeout-sol-20261003-01。状态：实施交付完成、正式同版 review 待总控；未作 gate pass 裁决。

唯一 workspace/branch 与冻结 HEAD/main 已核对。`initial-freeze.json`：11819 inputs、11816 protected 全部吻合；仅按冻结路径核 SHA，无额外文件发现。所有本轮票据在 `workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/`。原 finding、supplement、control、首轮报告及 receipts 保持原字节。

本轮实际 stdlib 操作证据见 `stdlib-boundary-command`。US3-C01 动机成立，owner 为 Documents `_verify_archive`；factory 只复用 typed 配置错误映射。除坏容器/CRC/method99，当前 ZIP 打开/读取同一输入边界的 unsupported extraction version/flags、截断 EOF、deflate zlib.error、bzip2 OSError、lzma.LZMAError 也应收束并保 cause。这些属于本项全部 ZIP 输入异常的直接补充反例，仍在三文件范围，不开新 slice，不增加资源规则。构造和读取分别限定 catch；不捕 Exception/RuntimeError/TypeError，不捕 Documents 校验代码自身 NotImplementedError。

首次读取冻结 SHA 清单直接 cat 导致工具输出截断；未据截断结果作核收，随后独占逐项 verifier 全量精确核验成功。未扫描 freshvenv 或其它私有文件；冻结路径核验不扩展到清单之外。

本轮直接补证 ZIP64 member header offset 超出 C ssize_t：`zip64-counterexample-command` actual exit1、2failed，Documents/public factory 都泄漏 OverflowError。直接 traceback 为 ZipFile.open → _SharedFile.read → BytesIO.seek；此为同项 ZIP 输入错误，不增加白名单。必须在成员 open/read 窄边界收束 OverflowError；报告即时登记，原失败票据保留。修复前的 `owner-tests-command` 73pass、pyright0、`positive-cli-command` CLI0 是中间源码事实，不冒最终源码验收。


## 最终交付状态与所有权

US3-C01 全部已登记反例及同一 ZIP 输入操作的成立补例已在三文件范围完成实施验证，状态：已修复（实施交付），正式同版 review/re-review 裁决待总控。停止于 S3 集中实施，不自裁 gate pass。未派发子 Agent，未 stage/commit/push/PR/merge，不改 main、分支或 worktree。

唯一生产修改为 Documents `dayu/documents/xbrl_config.py` 的 `_verify_archive`。实际 ZIP 构造只捕 BadZipFile、NotImplementedError、UnicodeError；实际 member open/read 只捕 BadZipFile、NotImplementedError、UnicodeError、EOFError、OSError、OverflowError、zlib.error、LZMAError。EOFError 来自当前 stdlib `_read2` 的显式截断异常；本轮实际截断 header 走 BadZipFile，没有把未执行的 EOF 分支称为单独实证。BZIP2 的实际损坏流异常为 OSError。ZIP64 OverflowError 已用实际完整 ZIP 索引/manifest 两面复现，收束后完整四面闭合。

捕获区域不包围 Documents `_relative`、path/size/hash 校验或其它 owner 逻辑。未捕 broad Exception、RuntimeError、TypeError；未列硬编码支持 method 表，未新增 enum/errorcode、Fins 特例、资源闭包解析器、Docling patch、runtime API、依赖或 OS 规则。归一 message 使用明确中文业务语义，底层 cause 原样保留。

原因层级：loader / prepare / worker 复验均为 `XbrlConfigurationError.__cause__ = 实际 stdlib 输入异常`；公共 factory 为 `DoclingConversionError(kind=CONVERTER_CONSTRUCTION).__cause__ = XbrlConfigurationError`，其下一层仍为实际 stdlib 异常。Fins 原映射源码未改。

13 类真实反例共覆盖四面：坏容器、CRC、method99、unsupported extraction version、compressed patched flag、strong encryption flag、deflate 压缩流、BZIP2 压缩流、LZMA 压缩流、中央目录 UTF8、local header UTF8、截断 header、ZIP64 偏移。每类 Documents 用实际部署先加载/准备合法 snapshot，再写真实损坏 ZIP、重绑 file size/hash 与 manifest digest，分别核 loader/prepare/worker；factory 也读同类真实部署与清单。worker 的 manifest file size/hash 更新只为了抵达 archive 校验，完整成员内容声明保留。没有 fake owner error 或下游补偿。四种当前 stdlib 支持的压缩（stored/deflate/bzip2/lzma）真实合法包在 loader/prepare/worker 全部通过。

## 本轮 changed files SHA-256

下列 SHA 是最终 owner 测试、全仓类型检查及最终默认 CLI 使用的同版源码；本轮只改三个允许产品/测试文件，另写本报告和独占 ignored 技术目录。

| 文件 | 最终 SHA-256 |
| --- | --- |
| `dayu/documents/xbrl_config.py` | `941de0dbda162318e5c1a249f8df0b7f6ce7a34dca121d65067652166fb20d13` |
| `tests/documents/test_xbrl_config.py` | `d46a8ef2f2038612bdfee019ddb4e2b8a6115bfe2e5b27fddc307d89c1ad042a` |
| `tests/fins/test_docling_converter_factory.py` | `aac77de6c907aa121118c49764c00a7ded946b7546b823404e794004a87d89af` |

报告自身 SHA 另存独占 `delivery.json`，避免自引用。首次源码 owner SHA 为 d59cc33f4482a54c2d0d59f949e469d22e7ae58382466d0ebbd85ae0002222dc，method99 补证绑定此 SHA；首轮 finding/supplement 保原字节。本轮 own helper 原 runner 逐字复制，source/hash 在 `helper-source.json`，旧文件/输出没有覆盖。

## 本轮 actual commands / 双流 / wait / exit

运行前均 `source .venv/bin/activate`；测试、真实 CLI 和脚本复用首轮完整标准 `standard-venv/bin/python`（Python 3.11.15），没有重新安装。全仓类型命令为激活环境 `python -m pyright --pythonpath <该 fresh Python 绝对路径>`，沿原 pyrightconfig 的 dayu/tests/utils，未改变 include/exclude/ignore。所有运行设置 PYTHONDONTWRITEBYTECODE=1 防止改动旧环境/源码缓存；COVERAGE_FILE、basetemp、JUnit、coverage JSON 均独占。helper 检查另用本轮 explicit 非空 include/extraPaths config，不冒根配置排除 workspace 后的空检查。

每一验证命令通过复制的 run_command.py 创建新目录，以 owned Popen 真实 wait 保存 stdout/stderr 两流、command/receipt，不用 compound 末尾 0 掩盖失败。必要环境摘要与完整 argv/cwd/UTC/owned PID/实际 wait/exit 在 `command-ledger.json`，包含中间成功和所有失败；不是完整环境转储。本轮独占 native CLI 经正常 require_escalated 执行生产策略，无 bypass。

| 本轮票据目录尾名 | actual exit | wait | stdout SHA | stderr SHA |
| --- | --- | --- | --- | --- |
| `final-freeze-command` | 0 | true | `8e801e4f2ec1e252e0778bd9ddb84f87d0e971b9f273288ce3191fe89461be51` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-full-pyright-command` | 0 | true | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-helper-pyright-command` | 0 | true | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-owner-tests-command` | 0 | true | `ba54c2ebbb5079c365682f90661b2a054a5f9a6faac21dc442e0dcd8dfb5d011` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-positive-cli-command` | 0 | true | `5eca6af62c2d26b864c8940928b56e857e5a43ca93bc03beb65757e21ff10ae5` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-source-audit-command` | 0 | true | `6924f30d6bb4fd2fe153ebfd16d7fbb62c911876062eec1b9906a9dfae944d9b` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `final-stdlib-boundary-command` | 0 | true | `c315f8fa77fe05a336db84c5e5e00b5c827ac3ee23eda732979d9e4257d62971` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `full-pyright-command` | 0 | true | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `helper-pyright-command` | 1 | true | `8f5e06a7b1f3253ba92b04df1895bc30c99eca8a2007f32e5fe5146a569a0879` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `helper-pyright-recovery-command` | 0 | true | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `inherited-evidence-command` | 1 | true | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `6b38b5c478af7ce35a2a7a260e27afe317b81e06a707fb97cb627d8da5a7f956` |
| `inherited-evidence-recovery-command` | 0 | true | `878c9bc7a67111433d13e20a671e43dcf0e6eab88e4fef950d2edd405b5c7c3f` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `initial-freeze-command` | 0 | true | `34eb5265fd56d9f2e6a99f87ed2e1ce3a9da339c5a03f6f2ff0b11bf80feca74` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `owner-tests-command` | 0 | true | `0c5fc2cd030ef2789e96364b4004b95c1569e576efabeaad093e93560ea99f7a` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `positive-cli-command` | 0 | true | `5eca6af62c2d26b864c8940928b56e857e5a43ca93bc03beb65757e21ff10ae5` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `public-readback-command` | 0 | true | `0b714b556d3e9c4346caaa9a89157e1a945ed94950526ed8ebc75d119917f7de` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `stdlib-boundary-command` | 0 | true | `c8679b97ee8837550e8853b9d4fe24344187dce734db66299c629ebf74877f96` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `zip64-counterexample-command` | 1 | true | `1d19439412e089377fa0615ee94ab1112f900b6b512cf0f8d18b9e23cbab058c` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

最终关键真实 argv（原字节参数另在各 command.json；下面按 shell quoting 展示 argv）：

`final-owner-tests-command`：

```bash
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python -m pytest -p no:cacheprovider --basetemp=workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/final-owner-pytest-temp --junitxml=workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/final-owner-junit.xml --cov=dayu.documents.xbrl_config --cov-report=json:workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/final-owner-coverage.json --cov-report=term-missing tests/documents/test_xbrl_config.py tests/fins/test_docling_converter_factory.py -q
```

`final-full-pyright-command`：

```bash
python -m pyright --pythonpath /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python
```

`final-positive-cli-command`：

```bash
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/dayu-cli upload_material --base /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/final-positive-base --ticker MLAC --action auto --forms MATERIAL_OTHER --material-name 'S3 concentrated MLAC' --company-name 'Mountain Lake Acquisition Corp.' --files /private/tmp/dayu-xbrl-s3-admin-qmid1407/mlac-20251231.xml
```

`public-readback-command`：

```bash
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/public_readback.py
```

`final-helper-pyright-command`：

```bash
python -m pyright --project workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/helper-pyrightconfig.json --pythonpath /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python
```

`final-freeze-command`：

```bash
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01/freeze_check.py final
```

`final-source-audit-command`：

```bash
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python -c 'import hashlib,json; from pathlib import Path; own=Path("workspace/tmp/upload-material-unified-s3-closeout-sol-20261003-01"); binding=json.loads((own/"final-source-binding.json").read_bytes()); assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected for path,expected in binding["source_sha256"].items()); print(json.dumps({"all_final_source_and_admin_hashes_match":True,"count":len(binding["source_sha256"]),"source_sha256":binding["source_sha256"]},indent=2))'
```

## 最终测试、类型、覆盖与继承边界

最终两 owner test files：75 passed，0 skipped，actual exit0。JUnit 为 `final-owner-junit.xml`；专用 coverage `final-owner-coverage.json`：owner 242/252 statement 命中，96.031746%。13 类坏输入的完整 cause 类型与非空原始 message 均断言。

最终全仓 `final-full-pyright-command`：actual exit0，0 errors / 0 warnings / 0 informations。原配置 SHA 为 661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c，末核一致。最终 helper 类型为 `final-helper-pyright-command` 同样0。工具升级提示不冒类型错误或消除原双流。

其余八生产源码逐字 hash 与首轮冻结相同，只精确继承旧覆盖；原 owner 95.934959% 被本轮 96.031746% 替换。原 668pass/1既有 opt-in PDF skip 是首轮事实，本轮没有重跑该全套，也未将旧类型/安装/OS票据冒本轮执行。

| 生产文件 | coverage | 证据来源 |
| --- | --- | --- |
| `dayu/documents/docling_runtime.py` | 91.063830% | inherited unchanged source only |
| `dayu/documents/xbrl_config.py` | 96.031746% | new final owner tests |
| `dayu/fins/pipelines/cn_pipeline.py` | 93.681917% | inherited unchanged source only |
| `dayu/fins/pipelines/docling_converter_factory.py` | 100.000000% | inherited unchanged source only |
| `dayu/fins/pipelines/docling_process_converter.py` | 93.750000% | inherited unchanged source only |
| `dayu/fins/pipelines/sec_pipeline.py` | 87.447699% | inherited unchanged source only |
| `dayu/fins/service_runtime.py` | 81.147541% | inherited unchanged source only |
| `dayu/fins/upload_format_contract.py` | 93.023256% | inherited unchanged source only |
| `dayu/runtime/macos_sandbox.py` | 85.087719% | inherited unchanged source only |

首轮 11 组 command/stdout/stderr/receipt 全部逐字对比原 `command-ledger-final.json` 成功：标准安装/pip-check、Arelle offline、Path/Stream after-C01、真实生产 positive、XML关系/取消 final05、必要 kernel、原最终668回归/全仓类型。其实际 argv、四份 SHA、对应 exit/wait 逐项在 `inherited-evidence.json`；标准安装 resolver report、metadata index、admin-input-v2、原 coverage、首轮报告/finding/supplement 的 hash 同文件列出。

冻结 identity 的 input-map 并未包含首轮所有 receipt JSON，故这些 receipt hash 依据是原 ledger，不能虚称它们均由 identity-map 直接绑定；原报告、产品/测试及 helpers/freshenv 等确有 identity-map 的文件仍逐项核对。`identity_bound` 显式区分这两类证据。只有八个未改生产源码精确继承覆盖，本轮 ZIP owner 使用新证据；首轮真实正例/安装/OS 证据按既定授权继承，不从新 error normalization 推跨平台或新 OS 保证。

## 最终真实默认 CLI 与公共 readback

最终 CLI 没有取证 monkeypatch：fresh `dayu-cli upload_material`、DAYU_XBRL_CONFIG 指向既有只读管理员 config、MLAC 官方原件，发布到本轮 `final-positive-base`。CLI owned PID 58649，actual wait=true，exit0。本轮未采样 worker 终态，不声明 worker0；首轮正常 worker 被原 close 回收 -9 与 CLI0 是不同事实，按原票据继承，不改生命周期或额外要求 worker0。

公共 `FsMaterialUploadStateRepository.read_material_upload_state`、`FsSourceDocumentRepository.get_source_meta/read_source_snapshot/get_source_document_locator` 与 `LocalFileStore.get_object` 读取完整原件/JSON/meta/manifest；locator 提供 storage key，不手拼 private layout。`public-readback.json`、`public-readback-command`：
- status：`complete`。
- company_present：`True`。
- document_id：`mat_45d9482c7fed80bea7f599b491873449eee6355f`。
- primary：`mlac-20251231.xml_docling.json`。
- original_sha256：`04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`。
- original_bytes：`328110`。
- docling_sha256：`03cff17b63d3a532de6a8e33778b39bf0317e9ae682a8c119098ddf6ba4a1f33`。
- docling_bytes：`1950364`。
- docling_schema：`DoclingDocument`。
- manifest_key：`portfolio/MLAC/materials/material_manifest.json`。
- manifest_sha256：`c16a00245e06f38923ebaacea7d65d5a2105b902776c09c957723231a3495efd`。
- consistency_verified：`True`。

manifest 只有该材料一行；ID/internal ID/primary/amended/ingest_complete/form/material_name/is_deleted/version/fingerprint 与公共 meta 一致，meta 两文件 size/hash 与实际完整 bytes 一致；amended=false、active、version=v1。JSON 按 DoclingDocument schema 实际解析，不将转换成功冒准确性保证。原件原 SHA 与管理员配置/manifest 原 SHA 均在 `final-source-binding.json`，`final-source-audit-command` 末核一致；不写改管理员根、原资源双备份或首轮目录，不将许可 taxonomy 加入 Git。

## 首末冻结、README 与范围核收

initial-freeze/final-freeze：HEAD=a514dea14c0ce66722da034502f3af54a54c3238，main=fac32ecbff9bfe792b63ee9667c8697826b631f4，branch=codex/upload-material-oracle，workspace=/Users/leo/workspace/dayu-agent-r。input_count=11819、protected_count=11816，initial 全输入 hash 相同，final 除允许三文件的新 SHA 外全部保护无漂移。identity/allowed/map/plan 五项绑定 SHA 首末相同，详见两 freeze.json。

已读取 tests README 开头职责和根/dayu/Fins README 的 Agent 更新约束及现有 XBRL段落。当前错误归一修复已有配置错误/construction 合同，不变用户入口、schema、安装、默认配置或架构；测试仍属原 owner 分层，因此 README 无新职责内容，保持原字节。Documents 无 README 不新建。

末次 git status 还出现运行期间新增、未在首个 status 中出现的三份未跟踪文件：`upload-material-unified-s3-first-delivery-root-adjudication-20261003.md`、`upload-material-unified-s3-readme-input-boundary-finding-20261003.md`、`upload-material-unified-s3-source-and-evidence-root-audit-20261003.md`（均位于 docs/gateflow）。本轮未写/读/修改这些文件，不能归入本轮 changed files；将这一工作树观察交总控核归属，不据其名字或内容作裁决。原冻结保护文件仍全部相同。

## 失败保全与恢复

- `zip64-counterexample-command`：actual exit1，2failed。实际坏 ZIP/manifest 两面原 OverflowError；在 owner member open/read 捕此精确类型后最终75pass恢复，原因链保留。
- `helper-pyright-command`：actual exit1、10errors；六个实际源码取证私有属性无 typeshed 声明，加四个 helper config 缺 repo import path。改 own 取证为 AST读取真实 stdlib 源码，不调用私有属性、无 getattr/Any/ignore；own config 加显式 repo extraPaths，恢复0；加继承helper后最终显式检查亦0。
- `inherited-evidence-command`：actual exit1，collector KeyError，因为误假定首轮 receipts 都在 input-map。修采集声明：command/receipt/双流按原 ledger 严格核 SHA，identity-map 实际存在的条目另严格比较；明确缺 map 绑定，而非伪造或 fallback 产品语义。新 `inherited-evidence-recovery-command` 成功，旧失败双流/receipt 原样保全。
- 初次大清单 cat 输出截断是读取呈现限制，不以截断结果验收；独占 verifier 首末逐项核验替代该读取方式。中间73pass/CLI0/pyright0 保留，但最终使用 ZIP64修复后的75pass/新baseCLI0/最终pyright0。

原失败及首轮全部历史输出保持不变；未因耗时 kill、换 provider、重装依赖或重跑昂贵矩阵。

## Residual 分类与下一入口

| 项目 | 分类 / owner / destination |
| --- | --- |
| US3-C01 全部 ZIP 输入异常 | fixed in current slice：Documents owner，实施及必要证据完成，正式同版双审/re-review裁决待总控。 |
| Linux / Windows | assigned to later work unit：后续平台部署验证 owner，安装/OS隔离矩阵未验，不外推本机结果。 |
| Docling 抽取准确性 / typed contexts | tracked by existing upstream issue：Docling #4437；本轮不patch或声明任意XBRL准确性。 |
| FTP actual request | existing UP-RR-T01 技术证据限制：无精确OS拒绝 → unknown；仍沿已决边界，不开新issue或新增业务拒绝。 |
| runtime公开XSD / 其它XML关系 | 已接受当前边界：runtime XSD allowed；无指定request的关系仅not-attempted；本轮未重跑矩阵、不重裁。 |
| 正式 S3 同版双路 review / aggregate / PR197 gates | 必需后续 gate，由总控安排；本报告不作为 gate pass，不由实施者执行。 |
| 完整 upload CLI CI / 正式 registry | assigned to later work unit：修复WU后独立 campaign/registry owner，不是本轮验收扩展。 |

无新白名单需求或未修 ZIP blocker；不扩大22 residual、不处理S1/S2或其它业务裁决。交付后停止，由总控核完整结构化结果并安排同版双路 slice review。
