# R1–R3 D3 head noscript 窄修回执

日期：2026-10-20。分支 `fix/public-original-read-r1-r3-20261020`，修前及交付 HEAD 均为
`6da0b8706f92a0e1eb361bebf5a529c97d2f9d40`；本次改动未提交。

## 范围、授权与停点

已读根 AGENTS.md、Gateflow、指定 goal-confirmation、plan、code-adjudication、authorization-update、
code-fix 回执，并核对正式“第一轮受影响面复审裁决”：两路已收齐、11 项已核销，D3 部分修复，主控放行本次窄修，未放行 PR。
本回执只交付该 finding 的 writer 修复/验证事实，不改已有审核、目标、计划、控制、裁决、实施或旧修复回执。
唯一 writer 未派 agent、未调用其它模型，未通讯、安装、commit/push/PR/merge，未查调用方环境或入口，
未新增下载、上传、预处理或修改财报原件；所有本轮仓储运行仅使用测试生成的隔离 Fs。

当前 writer 实施/验证已完成并冻结，D3 在 writer 自验层为**已修复**，正式 accepted 状态仍由主控和双路受影响面复审核销。
下一入口是 `fix -> 受影响面 re-review`；本回执及实际退出不代表 review-pass、draft-PR-pass 或 final closeout。
后续工程交付、经 tmux 报 portfolio-manager、等待核收及明确安装通知、按 README 安装指定精确源码版本的顺序，
沿 authorization-update 保留，由主控接续；本次 writer 不通讯、不安装，merge 仍另授权。

## 直接根因与唯一 owner

动机成立，且无需扩大 parser 改造。`OriginalStructure._scan` 在新 HTML 起始标签前调用 `_close_optional`；
当前开放节点为 head 时，`incoming not in _HEAD_CONTENT` 就会按规则结束 head。
修前该集合没有 noscript，于是合法 `<head>…<noscript><link …></noscript>` 在 noscript 起点提前结束 head：
noscript 的 parent/ancestors 错误指向 html，却可报 complete；后续显式 `</head>` 又被当 unmatched closing tag，误报 partial。
直接证据是主控 `controller-noscript-probe/{receipt,omitted,explicit}.json`，其源码 SHA 与本轮修前快照相符，
以及本轮真实公开入口的修前失败日志。没有使用 MiMo 的 head/p 输入作为合法 HTML 正例。

规范依据为 WHATWG HTML 的 [head 内容模型](https://html.spec.whatwg.org/multipage/semantics.html#the-head-element)、
[noscript 内容模型](https://html.spec.whatwg.org/multipage/scripting.html#the-noscript-element) 和
[in head 处理规则](https://html.spec.whatwg.org/multipage/parsing.html#parsing-main-inhead)：
noscript 是可置于 head 的 metadata content；禁用脚本时其 head 内容可含 link/style/meta，不能因 noscript 起点结束 head。
本轮合法输入使用 link；body 中的 p 只用于 body noscript 对照。
这里核定的是位置保真的原文结构边界，不新增脚本执行模式或浏览器 DOM 重建承诺。

原文结构 processor 是该语义的唯一 owner。生产只在 `_HEAD_CONTENT` 补入 `noscript` 并说明意图；
没有修改 `_close_optional` 的其它规则、结构投影、runtime、tool、Host、S1 schema 或共享 `dayu.runtime`，
没有下游 fallback、兼容分支或平行解析器。既有 head 内容集合的其它成员及 XML 独立模式保持原样。

## 实际变更与公开回归

- `dayu/fins/processors/original_content.py`：上述集合补全及中文意图注释，没有新增或修改生产函数签名。
- `tests/fins/test_original_read_review_regressions.py`：新增两个严格类型、含中文参数/返回/异常 docstring 的测试函数，共五个参数实例。
  四个正例组合显式/省略 `</head>` 与有/无 head noscript，全部保留独立 body noscript；
  断言 noscript/link/title/head/body/p 的 exact parent、完整 ancestors、闭合位置、complete 和空 diagnostics。
  一例缺少 noscript 结束标签，断言 mismatched_nesting、partial、unknown 边界及 link 的未知父链，不能被合法边界修复吞掉。
  全部经真实 `Fs` 发布及 `DefaultFinsRuntime.create(...).get_read_runtime()` 枚举/选件/读取，未 mock parser/runtime 结果。
  正例另核实际含 BOM 字节的 hash/size、所有节点 opening/content/closing 的公开 span 回读、文本和结构跨页拼接无漏重。
- `tests/README.md`：只在现有原文回归条目补充已落地断言范围。

同一新增测试在修前得到 **3 failed / 2 passed**，修后 **5 passed**，未放宽断言。
缺少 noscript 闭合的反例仍为 partial/unknown；其原先多出的 unmatched_closing_tag 随同一 owner 修复消除，
不是新增浏览器容错目标。原 head/colgroup/optgroup/ruby、XML 大小写、未知结构/引用和分页规则通过整个原文测试组保留。

## 实际命令、退出与完整原始日志

证据根 `W=workspace/tmp/public-original-read-r1-r3-20261020/`。本轮所有日志均为新 `code-fix-2-*` 文件，旧日志原样保留。
每项标签对应 `.command.json`（完整 argv/cwd/实际 Python/开始时间）、`.execution.json`（实际退出/耗时/结束时间）、
`.stdout` 和 `.stderr`（完整原始输出）；runner 的屏幕尾部输出不替代完整文件。
所有测试、coverage 和类型检查均先执行 `source .venv/bin/activate`，未升级依赖。

| 标签（相对 W，省略 code-fix-2-） | 实际结果 | 退出 |
| --- | --- | ---: |
| noscript-before | 新五例：3 failed / 2 passed / 47 deselected；合法 head 的两种失败与未知边界误诊断如实保留 | 1 |
| noscript-after | 新五例：5 passed / 47 deselected | 0 |
| tests-final | 三个完整原文测试文件 + 真实 process/Host 联合测试：99 passed，35.35 秒（外层 36.166 秒） | 0 |
| pyright-final | 全量 pyright：0 errors / 0 warnings / 0 informations，外层 43.783 秒 | 0 |
| coverage-combine / coverage-json / coverage-report | 本次独占父子数据合并、完整全包 JSON/报告；合并有下述警告 | 各 0 |
| freeze / reuse | 完整源码快照/指纹、旧证据逐项核验 | 各 0 |
| diff-check / diff-check-final | `git diff --check` | 各 0 |
| final-check | 初次一致性检查检出 control.md 在读取期间的外部更新，见下节；不是测试失败 | 1 |
| final-check-2 / final-check-3 | 核明外部文档差异并记录前后版本后，902 份冻结文件全部相符；回执写入后再次核验仍相符 | 各 0 |

核心命令的完整可执行形式如下；其它 argv 见上述对应文件：

```bash
source .venv/bin/activate
python workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-run.py code-fix-2-noscript-before python -m pytest tests/fins/test_original_read_review_regressions.py -k noscript --basetemp workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-pytest-before -q
# 只补完 processor 的集合后，同一命令使用新标签 noscript-after / 独占 basetemp code-fix-2-pytest-after。
export COVERAGE_FILE="$PWD/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-coverage/.coverage"
export COVERAGE_PROCESS_START="$PWD/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-coverage/.coveragerc"
python workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-run.py code-fix-2-tests-final coverage run --rcfile "$COVERAGE_PROCESS_START" -m pytest -p no:pytest_cov tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py tests/fins/test_original_read_review_regressions.py tests/host/test_fins_original_read_truncation_fetch_more.py --basetemp "$PWD/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-pytest-final" -q
python workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-run.py code-fix-2-pyright-final pyright
coverage combine --rcfile "$COVERAGE_PROCESS_START" --keep "$PWD/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-coverage"
coverage json --rcfile "$COVERAGE_PROCESS_START" -o "$PWD/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-2-coverage/coverage.json"
coverage report --rcfile "$COVERAGE_PROCESS_START" -m
```

实际覆盖率三条也由 runner 记录，argv 与上面一致。测试仅有三条既存 edgartools deprecation；
pyright stderr 仅新版提示。未忽略、扩散或绕过类型错误。
`W/code-fix-2-runtime-receipts.json` 逐项登记 **8 份完整原始返回**的路径/hash/size：
本轮五份 head/body/partial 回归回执，加真实 process/Host 的文本、结构/namespace/facts、facts 跨页三份联合回执。
原始 JSON 均保留在 `W/code-fix-2-pytest-final/` 对应真实测试目录，不以 Python 正向替代 process/Host 验证。

## 完整文件覆盖率与警告

本轮仅修改一个生产完整文件，独占配置复用原配置字节：`source=dayu/fins`、
`concurrency=multiprocessing`、`parallel=true`；无新增 omit/exclude，未混入旧测量数据，未用改动行或包平均缩小分母。

| 完整生产文件 | 执行 / statements | 覆盖率 | 排除 |
| --- | ---: | ---: | ---: |
| `dayu/fins/processors/original_content.py` | 391 / 402 | **97.2637%** | 0 |

缺失行完整列为 `229, 242, 252, 275, 384, 388, 465, 524, 536, 573, 719`。
`W/code-fix-2-coverage-summary.json` 保存实际完整执行行/缺失行/分母和对应源码 SHA；
`W/code-fix-2-coverage/{coverage.json,.coverage*}` 及全包 report stdout 全部保留。
全包平均 27% 是本次窄集合对未修改包的采集结果，不作为单文件门槛。

合并警告指向 `.coverage.Mac-Studio_local.pid22432.XVexGQ0x`（53,248 bytes）。
只读检查 SQLite integrity=ok，但 coverage_schema/meta/所有测量表均零行；原文件、警告与
`W/code-fix-2-coverage-warning-inspection.json` 保留，未修写/删除数据，也不猜测形成根因。
其余有效数据已经在 402 个 statements 的完整分母上超过 80%；空测量库不会使生产行从分母消失。

## 验证版本、逐文件 hash 与可取回快照

`W/code-fix-2-source-before/` 保存开工源码及只读 gate/review 文档；
`W/code-fix-2-source-final/` 保存 **902 份**完整 dayu/tests/utils Python、配置、相关 README 和 gate/review 文件，
包括全量 pyright 的源码范围。逐文件 SHA/size 在 `W/code-fix-2-files-final.json`，
版本、限定 writer diff、实际环境/全部安装依赖分别在 `code-fix-2-version-final.json`、
`code-fix-2-final.diff`、`code-fix-2-validation-env.json`。未变夹具/原件不重新复制或改写，既存版本仍由原证据取回。

manifest SHA-256：`7d2b634487af808fd0535fbc23600212e8730900e516d4126989da1781edc072`。
writer diff SHA-256：`b561db8a253049b1ff15fd09bcd4adf18ab3e4686c455ae1fffcc5ba0f92042b`。

| 本轮 writer 文件 | SHA-256 | bytes |
| --- | --- | ---: |
| `dayu/fins/processors/original_content.py` | `162cb733ebe1585df11ae26f1c6d5ad6338e0eb850f1bdcaec1f79984ad24ccb` | 37296 |
| `tests/fins/test_original_read_review_regressions.py` | `739d70b2cf6b128706ff51e043fd491a470517962e33be766650f00777cae44e` | 34395 |
| `tests/README.md` | `ec16a088ea130c0b1fa775cc2b372c2949222c06bf2addb3f7c96e74878e521d` | 150019 |

最终 `code-fix-2-final-check-2` 对 902 文件核验：snapshot_mismatches 和 current_source_mismatches 均为空。
hash 不替代保存字节，完整文件均可在上述快照目录取回。冻结后没有再改生产、测试、README 或配置。

只读文档观察需单列：开工至冻结间 `control.md` 外部变化仅将旧 gate 文字标为历史、更新 D3/11 项状态与最新安装授权边界；
writer 没有写该文件。初次严格检查因此退出 1；前后完整版本和
`code-fix-2-controller-document-observation.diff` 原样保存，差异 SHA 为
`55affb0011baafacc7b9970e005d067aa2ee36a39ea0f31cb222eb884ee62c06`。
其余开工只读文档均未变，冻结后的 control 也与快照一致；该描述性变化不影响源码、验证参数或放行裁决，
故明确记录观察而不重跑业务测试，不声称整个工作树都由本 writer 产生。

## 旧证据复用的实际适用性

`W/code-fix-2-reuse.json` 保存实际 argv/退出、依赖比对、182 模块的保存字节/指纹比对，
`code-fix-2-reuse-response-files.json` 核验 API-8 **1,774** 份完整响应的 SHA/size，均无不符。
API-8 标签仍为旧 HEAD `cd37d575…`；本次按保存源码/指纹核定适用性，不把该标签误写为本轮修前 HEAD。
API-8 的 182 模块当前仅 `original_content.py` 改变，181 模块及记录依赖版本全等；旧 writer 34 份快照全部可取回、hash 相符，
当前只变化上表三文件。L1 文本 owner 仍是 `fins_tools.py`，provider 仅概览，二者均未修改。

只读拼接 API-8 已保存的公开文本返回，重得 AAPL/ASML/ATAT/FUTU/MSFT/TSM 主件/YUMC/TSM 附件八份完整原文，
含 BOM 的 bytes hash/size 全部等于 API 资产身份，八份均无 `<noscript` 起始候选（大小写不敏感）。
因此本次集合新增成员不改变这些输入的结构路径：

- 原文/hash/span/全量文本分页、ASML cold/warm 拼齐及 EOF、TSM 主件/附件 identity 与 href 定位仍适用。
- 七份锚的结构、namespace、facts/context 与 MSFT 三 occurrence、TSM SGML 的 partial/unknown 断言仍适用。
- 未变的六批 53 次重放、ATAT/FUTU 表格和既存 CN/HK PDF/Docling 正向、storage/选件/缓存与输入未改写证据仍适用。
- 历史耗时/RSS 是 API-8 的测量事实，不冒称本轮新测量或新增 SLA；旧真实 API 没有 head noscript，不能证明新反例正确。

本次 head noscript 新反例、body 对照、partial/unknown 和 hash/span/分页交互由当前公开 runtime 回归提供，
真实 process/Host 三类续读联合测试本次重验。没有重跑整轮 1,774 API 或 1,453 测试。
旧完整测试 `1 failed / 1452 passed`、迁移真实 barrier 后整文件 `55 passed` 的实际退出与证据仍保留；
未变部分按既有正式裁决及实际影响复用，不能改称本轮一次全绿。新 99 项与当前全量 pyright 是本轮实跑事实。

## README decision

已读 Fins README“Agent更新约束”和 tests README“README 更新边界”。
Fins README 已正确承诺 HTML 合法省略闭合、XML 大小写及 partial/unknown，修复只是兑现该契约，
不新增稳定接口或能力边界，故无需改写或罗列 parser 元素细节。
tests README 在现有回归条目补上实际新增行为，属于现有测试事实职责。
安装、CLI、配置/prompt、层次装配和 Host/Engine 生产机制无变化，不触发其它 README 更新。

## 分类残余风险、owner 与 destination

| 项目 | 分类 / 当前事实 | owner / destination |
| --- | --- | --- |
| D3 head noscript 边界、显式/省略 head、body 对照及未知边界 | fixed in current slice；writer 自验已修复，正式状态待复审核销 | 原文 processor writer → 本回执；主控 → 指定双路受影响面复审，未获 review-pass |
| D1/D2/D4/C1/C2/C3/C4/M1/T1/T2/L1 | fixed in current slice（前轮正式核销）；本次无生产变更，复用证据并重验原文/Host 直接交互 | 原 owner 不变；主控 → 聚焦本次影响面，不重新开放未变修复 |
| 空 coverage 子库形成原因 | assigned to later work unit；原始数据/警告保全、完整分母达标，非 parser 功能阻塞 | 测试/coverage runtime owner → 需要追查采集器生命周期时使用本次只读检查与原库；当前不扩共享 runtime |
| S1 实际供应商接受 itemless concepts schema | assigned to later work unit；沿正式 deferred-with-owner，当前未验证 vendor | Provider/Engine owner + 项目协作助手 → 调用方后续补验接续；不增加本线安装门槛 |
| CSS/脚本执行、浏览器 DOM、跨资产 document set、XBRL transformation/业务解释 | assigned to later work unit；本轮仍只保原文结构/引用 | Fins capability owner / 调用方 → 新需求独立立项；不据本次合法边界回归扩展承诺 |
| LRU 非总字节硬上限、同步 I/O/第三方段无硬中断、SEC 无 durable original_main、OLD 同输入动态对照未做 | assigned to later work unit；沿旧实施/裁决风险，未变 | Fins runtime / storage provenance owner / 总控 → 既有容量、硬时限、来源与对照接续 |
| 双路复审、独立 draft PR 工程核对、核收/安装通知及源码安装、merge | covered by later approved slice（复审/交付/条件安装）；merge requiring new issue or explicit user decision | 主控 → 先复审核销再按授权交付；项目协作助手 → 核收/明确安装通知；用户 → merge 另授权；本 writer 按本次限制冻结交付 |

本次范围内无未解决生产反例或未分类风险；验证通过不替代独立审核。
