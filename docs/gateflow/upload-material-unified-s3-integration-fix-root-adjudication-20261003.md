# S3 T03/T04 集中修复：总控核收

唯一分支 codex/upload-material-oracle，HEAD a514dea14c0ce66722da034502f3af54a54c3238，main fac32ecbff9bfe792b63ee9667c8697826b631f4。gpt-6-sol/codex label upload-material-unified-s3-integration-fix-sol-20261003-01，托管 write_stdin(session72184) 实际 outer0；56有效JSONL/turn.completed、22 command_execution/一个授权file_change，全部可见完成item已核，模型事件未暴露则unknown。canary匹配；stderr为空；完整轨迹与逐receipt核验在 workspace/tmp/upload-material-unified-repair-20261002/s3-integration-fix-01/root-audit/，原TMP及双 runner-streams 副本SHA相等。

三个hunk符合唯一test owner：两处patch在工厂绑定消费点，配置校验/真实runtime/市场runner/存储/observation/job及calls和failure断言未削弱；四个旧事实变独立断言并新增配置事实，保持schema与公共projection相等，不改变生产文案。root直接读取factory、service_runtime消费点、旧/新test和diff。生产472文件及其它12375保护输入零漂移。84源码清单只有该test SHA变化，其余83相同。

实际完整该文件144 passed/0failed/0skipped，JUnit逐case核；全量.venv pyright0errors/0warnings。四份receipt（fullfile、pyright、readback恢复、结束交付）均实际waittrue/exit0，逐command/stdout/stderr SHA及source绑定 e47e6373be4a195e9587b308293891a25df07e8cbbdf9024ab7fbe7f76e748dc。旧41文件、38生产覆盖>=80与真实XBRL五case只按源SHA/JUnit继承，旧2834pass7fail3skip保持failed，不称新整轮单次绿色。README职责已读，无新层级/产品语义无需改。

## 可观测失败及裁决

JSONL38 item_19 readback actual1：把该XBRL文件全部10个测试当作5外部样本。40 item_20枚举真实JUnit；45 item_23在新readback-02按名称精确选择5例，全部receipt/sourceSHA恢复0。首次工具只返回合并输出，原独立双流不可恢复，不伪造；命令/失败实际文本保原full trace和独占failed目录。恢复完整双流核验加root直接XML/hash扫描足够验收，不需要新增用户裁决或issue；作者requiring new issue or explicit user decision残余在此改裁为fixed in current slice的工具恢复warning。

另有作者报告执行前functions.exec语法错误，原JSONL没有独立命令执行记录，不能把自报复建tool-result文件冒原工具事件；没有启动的进程不造exit。52 item_27 end-scan-and-delivery-02实际wait0已经产生并核完整报告/扫描/receipt，必需证据无缺口，不依赖该自报错误文件支持产品通过。初始目录枚举截断已定点恢复，pyright版本升级提示未改变依赖。root实际source/diff-check复核，不用复合命令最后cat的0代替中途check。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: partial
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [readback_external_selection_recovered, original_failed_step_combined_output_only, reported_preexecution_syntax_error_not_independently_visible, pyright_version_notice]
evidence_gaps: []
retry_class: none
```

partial仅限定自报执行前编排语法错误不在可见事件；22实际命令及file_change轨迹完整。采纳实施交付作为复审输入，T03/T04已修待同版双复审，不提前S3pass。旧R01/R02/D01六源码SHA相同，继承其root/双审。Raw EOF为既批全slice后aggregate证据项，仍未实施、不新slice；Linux/Windows延期/Docling#4437/既有FTP等技术残余原owner保持。完整CLI/正式registry仍WU closeout后独立阶段。下一入口 re-review S3 T03/T04。
