# F5-IV05：CLI 未知引用缺少字面量转义

状态：accepted / 未修复。owner：dayu/cli/output.py 的下载结果行格式化；destination：当前同一完整F5-S1/code-review fix，不新增implementation slice/WU/业务裁决。

## 直接证据

完整codefreeze7545bd52、86源首末仍匹配。`FinsDownloadUncertainReport`复用既有公共文本校验，允许240码点内的合法opaque引用包含内嵌换行；HK原始NEWS_ID文本解析也不禁止该字符。`_print_download_summary`直接f-string输出source_id及existing_document_id，而确认document_id已采用JSON字面量输出。差异在机械格式化owner，不是财期/发布/状态推断错误。

MiMo在只读审查提出并准备合成probe，非当前官方HTTP观察。总控完整读probe后独立复现：初版缺public failure，root补全版retry_hint误用None，两个构造错误均不采作产品缺陷，分别双流保留。最终使用实际公共failure owner说明、完整合法failure/result/event与不超过240的来源引用，exit0：

- source_id=`B1\nFins download: discovered=9 downloaded=9 ...` 被公共contract接受；
- 实际结果仍FAILURE/unknown1/下载0；
- CLI先输出真实计数，再把来源内换行显示为另一条独立`Fins download: discovered=9 downloaded=9...`行，误导operator对引用与计数的判断。

原始typed/public/durable业务数据没有被本probe改写；缺陷是UI未把opaque引用显示为literal、破坏行边界。真实入口render_fins_direct_event→_print_terminal_business_summary→_print_download_summary。JSON/wait本身正确引用字符串，不修改它们以补救UI。

证据目录 workspace/tmp/pr197-f5-concentrated-code-review-20261002/root-validation/，unknown_reference_probe_complete_02.py、unknown-reference-complete-02.stdout/.stderr/.receipt.json；旧失败unknown-reference和complete原件保留。全部86源仍与freeze匹配。

## 最小owner修复与验证

- 在CLI下载引用格式化owner提供一个朴素共享literal helper，确认document_id、未知source_id与existing_document_id复用；完整可逆保留合法引用，不裁240码点ID、不strip/改业务身份、不限制publicschema合法字符、不在selector/downloader加局部拒绝。
- 常规JSON literal escaping足以作为最小路线；需确保换行/回车/ESC及Unicode行分隔符不能改变UI行结构，并保留引号/反斜杠/Unicode的完整身份。None按既有空单元约定显示，非空有引号是必要可见格式变更。由Sol选择最小可维护实现，不引入格式profile/复杂codec。
- owner回归：failure和cancel两分支均显示已确认A/未知B且原exit1/130、原输出通道；真实adapter/wait/CLI链更新必要字面量断言，typed/wait中的原引用不得改写；source_id及existing_document_id包含特殊字符、240码点边界、None与确认文档ID复用同helper。
- 不改原因词表、财期规则、publication/manifest/job状态；保IV01–04已经修复的owner行为。必要README按职责最小更新。
- source .venv/bin/activate 后运行受影响组合pytest/fullpyright、改生产文件>=80%，独立双流/真实exit/源码身份，然后同版并行MiMo/MiMo-flash re-review。集中当前一项必要fix，不重开错误finding或文档nitloop。

在MiMo当前只读租约正常结束并核收全部结果前不启动产品writer。该项已立即同步三controller，以免压缩丢失。

## 2026-10-02 最终状态覆盖

accepted / 已修复；完整作者、正式两审及同版复审由总控独立核准。最终裁决见 pr-197-r1-f5-s1-code-review-final-adjudication-20261002.md。原未修状态为历史，不覆盖本条；code gate PASS，aggregate/PR/final closeout另行推进。
