# upload_material 第一轮校准：UM-O20 用户裁决

裁决日期：2026-09-28。用户对本项建议明确回复“同意你的裁决建议。下一项。”本文件登记 accepted 行为、已接受的 public-contract 修复方向 `UM-O20-F01` 和补证任务 `UM-O20-E01`；`UM-O20-F02` 仅接受其条件性处置原则，具体产品修复仍待补证确定原因后裁决。各项均未实施；不代表 upload_material readiness。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。逐项核对下列五次真实 CLI 的 `command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`。五次均通过后缀门禁、进入 upload.started，随后 exit 1；screen 均为 `failure_kind=content`、`failure_code=docling_converter_execution`、`requested_files=1`、`stored_files=0`。stderr 为有界失败说明。文件系统只留下公司 identity/meta 和目录 scaffolding，没有 material 文档、原件、Docling JSON 或 manifest publication；无超时、无残留进程。workspace SQLite 与 Host/EventLog/Trace/Memory/job 查询为 queried-but-absent。

| 场景 | 输入与来源 | 直接结果 |
| --- | --- | --- |
| UM-F11-xbrl | 真实 XBRL XML **linkbase** 字节投影为 `.xbrl` | converter execution failure；无 material publication |
| UM-F12-xml | 同一真实 XBRL XML **linkbase** 的 `.xml` 原件 | 同上 |
| UM-F13-json | 真实投资语料中的普通 source `meta.json` | 同上 |
| UM-S21-simple-json-content | `{"kind":"material","period":"2025Q1"}` 普通 JSON fixture | 同上 |
| UM-S22-simple-xml-content | `<material><period>2025Q1</period></material>` 普通 XML fixture | 同上 |

静态 owner 核对：`dayu/documents/docling_runtime.py` 的共享 capability 把 `.xml/.xbrl` 映射为 `XML_XBRL`，把 `.json` 映射为 `JSON_DOCLING`；`dayu/fins/upload_format_contract.py` 的 filing help 已说明前者仅是 XBRL XML 候选、后者仅是 Docling JSON 候选，但同一 owner 生成的 material help 只罗列后缀、没有说明子类型。冻结 CLI 对上述五份内容的底层异常已投影成安全的 `docling_converter_execution`，未保留可证明每次具体后端首因的 debug evidence。

保留的校准 `.venv` 内 Docling 2.120.3 源码显示：JSON 后端按 `DoclingDocument` schema 解析；XBRL 后端要求 XBRL **instance**，并依赖可选 `arelle-release` 和 taxonomy 获取配置。当前保留 `.venv` 用 `importlib.util.find_spec("arelle")` 查询为 `None`；这可说明当前保留环境的能力缺口，但没有 run-time dependency snapshot，不能仅凭当前查询断言五次运行当时的异常首因。F11/F12 的 linkbase 根元素并非 XBRL instance；S22 普通 XML 也不是；F13/S21 不是 Docling JSON。这些是输入与所声明子类型不匹配的直接事实，不能把“语法有效”误作“支持的内容格式有效”。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

接受“五份已测输入进入转换、返回 typed content failure、未发布 material”作为实际运行观察；**不接受**冻结报告仅由这些样本推出“`.xbrl/.xml/.json` 的有效受支持内容均不能转换”的结论。维持既有格式语义：`.json` 只指 Docling JSON，`.xml/.xbrl` 只指 XBRL instance 候选；不为普通 JSON/XML 或单独 XBRL linkbase 增加本地转换器，也不把 Docling 的内容抽取准确率纳入项目职责。

公开 material 帮助文本应说明这些子类型，并明确后缀通过只代表候选资格。至于 XBRL instance 与 Docling JSON 在可部署产品环境中能否真正成功，当前五个输入无法证明，需用符合后端要求的样本及依赖快照补证；补证前不把这两类列为已验证成功域。如果 XBRL 运行依赖在产品环境缺失，项目必须让产品 capability 与实际部署能力一致，而不是把所有有效实例以“文件损坏”呈现。

## 已裁决修复方向与补证项

### UM-O20-F01：material 格式说明与共享 capability 同源

状态：**修复方向已接受，尚未实施**。

动机：filing help 写明 `.xml`/`.json` 的子类型限制，而 material help 只展示后缀列表；相同共享 capability 在两个入口对用户表达不同的格式语义。普通 JSON/XML 被允许进入转换后仅得到“文件无法解析或已损坏”，用户难以知道格式子类型不符。

语义 owner：`dayu.documents.docling_runtime` 的 Docling format capability 定义实际格式；`dayu.fins.upload_format_contract` 的唯一帮助/schema 投影负责把该事实转为 CLI、tool、batch 可读说明。修复应在这一共享投影处进行，不在 CLI 或某一个 LLM tool 中各自加字符串特例。

修复要求：material 的文件说明显式写明 `.json` 为 Docling JSON，`.xml/.xbrl` 为 XBRL instance 候选，任意 JSON/XML 或单独 linkbase 不因扩展名匹配就被承诺可转换；所有公开入口从共享投影读取，不得出现不同承诺。具体 public failure 分类若需改变，应由 converter/format failure owner 根据直接错误原因设计，不从文件名或通用 `content` code 反推。

### UM-O20-E01：符合声明子类型的真实 CLI 补证

状态：**补证方向已接受，尚未实施**。

在新的隔离 evidence root，以本轮产生的真实 Docling JSON 作 `.json` 正样本，以完整 XBRL instance 和所需 taxonomy/dependency 配置作 `.xml/.xbrl` 正样本，记录实际输入来源/hash、精确 argv、运行时依赖版本与可选包、底层有界诊断、双流/exit、文件系统 diff、meta/manifest、durable/SQLite/process 和证据 digest。另保留普通 JSON/XML/linkbase 的负样本。新结果显式 supersede 本项过宽推断，不改写原证据。只在真实 CLI 的正样本成功后，把对应格式登记为 validated success；若失败，定位具体 owner 原因再定产品修复。

### UM-O20-F02：XBRL runtime 能力与部署依赖一致

状态：**条件性处置原则已接受；具体修复待 UM-O20-E01 查明原因后再裁决，尚未实施**。

动机：共享 capability 当前宣称 `XML_XBRL`，保留校准环境却查无 Docling XBRL 后端要求的 `arelle` 包，说明有部署能力失配风险；原始五次运行未捕获足够诊断来证明具体失败是否由此导致。

语义 owner：Docling runtime 装配/产品 capability 与包依赖声明共同承担可部署的转换能力；Fins material 仅消费该能力，不能用下游 fallback 伪装支持。

条件性处置原则：若有效 XBRL instance 在受支持部署中因缺失可选依赖或 taxonomy 配置而失败，则补齐并验证端到端转换能力，或从产品 capability/所有公开入口统一移除 `XML_XBRL`，直到确有可用实现；不能只改帮助文本仍允许一个稳定不可用的格式进入转换。具体路径待补证后裁决。此项不要求项目编写 XBRL 内容抽取器。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。F11～F13/S21/S22 的 typed 失败和零 material publication 可保留为特定不匹配输入的证据，但不能替代正样本，也不能把“通用 JSON/XML 都失败”提升为格式总体失败 oracle。UM-O19 的已测格式成功域不受本项影响。

## 裁决替代关系

本裁决取代冻结 observed report UM-O20 “语法有效样本失败，所以格式声明应提供通用转换或移除后缀”的推断；保留原始运行事实，区分子类型、部署能力和上游解析。正式 registry/readiness 待后续统一登记。
