# Aggregate 同版 MiMo 复审总控核验

## 终态与必要取证

唯一workspace `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`，HEAD ec54351e58e66cd5d00b009c862589b109064ade，main fac32ecbff9bfe792b63ee9667c8697826b631f4 未动。label upload-material-unified-aggregate-rereview-mimo-20261003-01；runtime claude/provider mimo，init model mimo-v2.6-pro[1m]、actual assistant model mimo-v2.6-pro（后缀显示与事件记录分别保留，不猜）。托管44370已返回outer0；7382有效JSONL events、70工具逐结果配对、result success/is_error=false/71turns；指定读取逐字match。stderr仅精确SDK warning。

正式报告 docs/reviews/code-review-20261003-112958.md（SHA e469b17698af61bc0ee587792b25df78717f40b15ecffb41b8d99330e0fc733a）与own-summary全文root已读。完整逐调用trace/双backup分别见 aggregate-rereview-01/root-audit/mimo-full-tool-trace.json、mimo-runner-backups.json；root覆盖receipt见mimo-root-coverage.json。Root实际查看全部70命令/结果/失败及关键代码与票据；没有is_error工具结果。

Root把21次实际Read输出与冻结mimo-recovery.diff每行对照，8236/8236逐字相等，无遗漏/截断；包括全部31tests+6配置/职责README真实改动逻辑，原7完整tests按同SHA实际旧事件精确继承，不冒本轮重读。AGENTS实际Bash294/deepreview实际607全文读；fix.diff全文、完整changedCLIhandler/真实损坏测试、material staticadmit/state chain、缺身份隔离用例、owner/helper与no-runner实际走读可核。142冻结输入实际初末scan与root当前独立scan均zero，source88包含其中。

四项 UA-R01/R02/R03/UA-E01 已验证修复，无新finding。Raw2997实际解码原191字节/SHA70a0f357…；3080实际逐字段与HEAD比较，仅manifest0-based21/24变化/其余24相同，并实际核current size/SHA、guide/decodedoriginal身份、validation仅pyrightkey变化；root此前独立exactbytes再次保真。671同版tests/type0/两prod82.4411/90.6587来自集中fix原11receipts，root已全核。

## 工具呈现缺口与声明裁决

- event3684/call_b80e94d003404c34a0137f87：grep JUnit单行输出120.3KB触发persisted-output，不能声称完整XML已读。本预览已含两coverage实值及tests671/errors0/failures0/skipped0头，5828之后用bounded提取核12材料/4缺身份case完整名字；root实际解析完整JUnit671case及原SHA/receipt验证补核，不需要重跑或全文dump120KB。必需结果已恢复，未采“大输出全阅读”声明。
- event3167读取了真实command/receipt/双流但循环找旧sha键名（真正SHA为receipt.sha256），未独立核该嵌套每字段；报告“receipt SHA一致”由142全冻结身份扫描及root原11票据字节核支持，不冒本路已运行不存在的字段比较。
- own3863真前台pytest、立即exit文件0/16passed/stderr空，只有12损坏与4缺身份，不含no-runner，报告R02所称runtime测试只能指缺身份这个模块。no-runner事实来自原671JUnit和真实生产共享owner，不冒ownprobe重跑该case；own command事后摘要不当独立PID采集器。
- 模型后缀/actual字段由root上面的事件值补核，关闭报告OpenQuestion，不触发provider切换。
- 历史生成narrative全文明确excluded，非“后续全审”新承诺；同版全42/OS/外部5cases已经S3验证，本轮不重复不是延期新验收。只Linux/Windows按用户正式延期；完整PR真实代码差异必须随后gate核。
- 测试helper is_material布尔表达式是封闭PreparedDoclingUpload联合中material-only两变体的既定语义，root亲读helper1012–1068及联合246–279验证。可读性偏好不构成合同违例，不扩大当前修复。
- Root自己输出误逐systemevent打印None造成呈现截断，随后只打印实际model/全部70toolmap/关键结果+8236逐字程序对照恢复；另一个旧amendment文件名locator失败已用rg定位并全文读真实 upload-material-xbrl-runtime-boundary-goal-amendment-20261002.md。探索找旧PR临时py脚本rg无匹配不承担任何验证，不虚称有该工具。

## 总控裁决与分类

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: partial
warnings: [recovered large JUnit presentation, narrowed SHA comparison and own-probe claims, corrected actual model metadata, SDK warning]
evidence_gaps: []
retry_class: none
```

partial仅拒采非关键过宽声明，四项修复及MiMo31/6必要scope恢复证据可采纳；两路报告均无新finding。fixed in current slice：四修复与两原审scope缺口已闭合。assigned to later work unit：平台部署Linux/Windows和未来依赖维护owner Documents/platform；CLI/正式registry为本总控WU后独立执行，既有22残余不扩大。tracked by existing issue：Docling抽取#4437。当前无新未分类风险，下一总控aggregate最终裁决/checkpoint，不停普通gate。
