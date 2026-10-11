# PR200-N1 百分号路径身份修复

- Work unit：`sec-html-image-assets`；沿用已确认 goal、approved plan 的 S1。
- Gate：PR review → fix；状态：N1 已实施并完成本轮最终验证，待独立 re-review/root 裁决；不代表 gate pass。
- Finding：`PR200-N1` accepted / 中；已实施验证待独立复审，最终修复状态由 root 裁决。
- Controller decision：`docs/reviews/pr-200-review-20261012-013721.md`。
- Source head：`db0d0e68557a42ca2b6f33500cd9ffe87033c1e7`；base：`297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- 分支：`fix/sec-html-image-assets`；worker 不 stage/commit/push/PR，不启动 Agent，不写 control/goal/approved plan/review/历史 validation。
- 新证据：`docs/validation/sec-html-image-assets-pr-percent-path-fix.json`。
- 独立临时根：`workspace/tmp/sec-html-image-assets-pr-percent-path-fix-_rrt5q42/`；原业务 workspace、撤回 TCOM worktree 未访问。

## 动机、owner 与最小决策

N1 成立。旧 `_is_same_image_archive` 使用 raw path 组件，文件名提取却再单次解码。
编码 Archives、edgar、data、CIK 或 accession 的合法同申报 URL 因此可被静默忽略，缺图集合
仍可被发布并取得快跳资格。反例是合成输入；没有证据证明两份真实 TSM HTML 包含该输入。

SEC downloader 是图片地址、同申报边界及 canonical 资产身份的唯一 owner。本轮只修改
`dayu/fins/downloaders/sec_downloader.py`：原始地址的控制字符、反斜杠、编码分隔符、非法/二次
编码及候选父点段先被拒绝；`_parse_image_address` 只解码一次并返回 typed 地址，后续首 base
归一、相对路径解析、同申报组件比较和文件名提取使用该 decoded path，不再 unquote。
标准库负责 origin/query/fragment 解析；有限图片路径合并保持 URL 点段及空组件规则，decoded
路径不再序列化给 URL parser，避免字面 `%`、`?`、`#` 等被二次解释。正式请求由 archive 根
与合法单组件资产名重新编码产生。

三个图片入口复用此真源，不新增 wrapper/fallback、不取 basename、不在 workflow/storage/UI
补文件或改 metadata。现有 HTTPS sec.gov/443 无凭据 origin、跨 CIK/accession/前缀、首 base、
首属性、有限 srcset/data、flat 子目录 typed 失败及 NFC/casefold 碰撞契约保留。6-K/rejected/SC13
筛选、版本算法、processed 规则、下载契约 v1.3.0 与包 0.1.4 不变。没有新增 schema、crawler、
CSS/JS/browser、OCR、provider、approved slice、issue 或 goal。

## 源码、测试与文档职责

- 生产仅 downloader；其余六 production owner 的本轮前后 bytes/hash 必须相同。
- `tests/fins/test_sec_html_image_assets.py` 增加三入口的 full/protocol/root URL 和编码首 base
  矩阵，覆盖各 archive 组件及混合 filename 的 literal/encoded 去重、完整 canonical HEAD。
  负例保护跨申报、前缀假匹配、错误/二次编码、编码点段/分隔符、unsafe base/origin。
  正式 workflow 只替换 HTTP 响应及观察原指纹函数，实际 downloader、pipeline、Fs batch
  执行；从本轮 selected HTML bytes 发现编码图片，验证 fresh/ordinary upgrade、必要 404
  旧 publication/processed 保留、retry、完整指纹与持久资产以及 repeat 零请求。
- `tests/fins/test_sec_html_image_assets_real_cli.py` 仅增强 observer 的七 producer 实际导入
  file/code_root/SHA 及逐 child 断言；真实样例、期望矩阵与业务流程不改。
- Fins README 按开发者地址身份 owner 职责补 path 同源契约；tests README 记录现有新 owner
  回归。根 README 命令/用户流程未变，冻结；架构 README 和 LLM-facing 文本无变化。

## 本轮验证与交付契约

激活 `.venv` 后运行受影响测试与全仓 pyright；最终 source/test 冻结后运行 collect、
`tests/fins tests/cli/test_fins_commands.py` broad、全仓 pyright，以及独立 COVERAGE_FILE 的
目录覆盖率目标，七 owner 各 >=80%、excluded 0，不 append/exclude/ignore。

使用原 opt-in validator 在本轮新临时 base 执行两份真实 TSM、24 CLI。baseline 297 git archive
正式旧 CLI 播种，无手工复制 business base、补图或改 metadata；逐 child 区分 baseline/current
七实际 producer 身份，核对完整集合、指纹/版本、URI/size/SHA、4 expected 404、原子保留、retry
与 repeat。真实统计由本轮结果生成，不预填旧 counts。

新 JSON 记录精确 argv/cwd/exit/log SHA、11 source/test final hashes、final commands 的 before/after
不变证据、inventory size_bytes/SHA、真实/coverage counts 和所有失败/恢复。旧五 validation JSON
只读历史，完整 hash/count 原样、`reused_as_final_result=false`；新 JSON 待 root/独立复审。

## Residual risks / owner / destination

- N1：fixed in current slice，已完成本轮实现/验证，仍待独立 re-review；owner SEC downloader，
  destination 本 artifact/new validation → root/new mimo+DS PR re-review。
- R3：assigned to later work unit；SEC transport/workflow 维护者；独立远端重校验/validator/指纹策略需求。
- R4：assigned to later work unit；SEC downloader/Fins storage 维护者；有真实样本的目录资产地址及 CSS/JS/browser/legacy 编码需求。
- R5：assigned to later work unit；后续需求提出方；外站、跨申报、OCR、财务数值提取独立需求。
- R6：assigned to later work unit；SEC transport 维护者；HTTP 200 内容校验及 HEAD/GET validator 同响应身份需求。
- R7：assigned to later work unit；Fins processor/分析能力维护者；图片 OCR、财报数值及真实 processed 重算验收。
- C2：rejected-with-reason / 未采纳；Fins storage/展示维护者；有样本的全局 Unicode 文件名展示契约，不重开。
- DS-OQ2/RR10：assigned to later work unit；SEC downloader/workflow 维护者；独立公共 typed transport 契约需求。
- DS-RR9-real-shapes：assigned to later work unit；SEC downloader/tests 维护者；有真实新形态样本的独立验收需求。
- OBS-1：root rejected-with-reason；既有无凭据 origin 合同保留，有样本的扩展归 SEC downloader 独立需求。

无新增未分类风险、blocking owner/scope question。下一入口由 root 根据新同源证据派发独立
re-review；worker 不提前标记 N1 最终已修复、PR review pass 或 final closeout。

## 最终本轮结果与恢复记录

- 受影响 owner：852 passed；图片 owner 694，pipeline owner 158。
- collect 4169；broad 4160 passed / 9 skipped；全仓 pyright 0 errors / 0 warnings / 0 informations。
- 真实 2 passed / 0 skipped；24 CLI，4 expected exit1 + 20 exit0；目标 27 / 完整 filing 28 图；112 逐图读回，168 实际 producer 身份核对。
- 11 source/test final hashes 在所有 final commands 前后不变；六下游 production owner bytes 未改，五历史 JSON 原 hash/count 保持、全部 reused_as_final_result=false。

| Owner | Clean coverage | Excluded |
| --- | --- | --- |
| dayu/fins/downloaders/sec_downloader.py | 95.05% | 0 |
| dayu/fins/pipelines/sec_download_filing_workflow.py | 84.16% | 0 |
| dayu/fins/pipelines/sec_pipeline.py | 89.54% | 0 |
| dayu/fins/pipelines/sec_rebuild_workflow.py | 85.82% | 0 |
| dayu/fins/pipelines/sec_download_state.py | 82.71% | 0 |
| dayu/fins/pipelines/sec_safe_meta_access.py | 90.70% | 0 |
| dayu/fins/pipelines/sec_download_source_upsert.py | 88.64% | 0 |

保留了首轮实现丢失相对路径前导空组件的回归失败；仅 Ctrl-C 中断本轮 owned 测试进程，原日志/启动记录/runner exit130 保留，不虚构未捕获的 child 退出码或结束身份。修正后完整 owner/broad/类型/真实验收通过。新增测试首轮误将 HTTP status 与默认描述符比较，随后改为断言身份与原完整指纹；正式 workflow 首轮错误期待 10-K 也请求类型索引，按既有选择规则修正测试，没有修改生产筛选。旧代码 red-proof 因上述 fixture 错误不能作为独立正式 N1 根因证明，直接根因沿原 mimo 探针，新正式 Fs tests 提供本轮副作用证明。

broad/real 首启动把 argparse --settings 放到 REMAINDER label 后，未启动 pytest；配置前移后分别独立完整重跑。旧五 JSON、mimo 原失败 fixture/修正日志未改。辅助初始化括号/import 语法错误、不存在文件检索和 ps 受限均已记录/恢复，不计 final pass；没有广泛 pkill、扫描或写旧 FIFO、清会话。真实 CLI 样例矩阵保持，没有把合成编码路径称为官方内容。

无未恢复的必要验证失败；未做 OCR、真实 processed 转换、远端定时重校验、新真实 srcset/base 形态验收，按上文既有 owner/destination 保留。未提交/推送/改 PR；新精确 PR head、双路 re-review、最终状态和 gate 由 root 完成。
