# 正式PR197集中fix总控核收

## 身份与生命周期

唯一workspace /Users/leo/workspace/dayu-agent-r、branch codex/upload-material-oracle；head44c1892e7361dba799154fc01b2a4dfe43407e75、main fac32ecbff9bfe792b63ee9667c8697826b631f4、index unchanged。codex/gpt-6-sol，label upload-material-unified-formal-pr-fix-sol-20261003-01，session85155托管actual outer0，80有效JSONL events/turn.completed。实际命令终态及失败见formal-pr-fix-validation.json，全部轨迹和独立stdout/stderr/last-message及双备份齐，校验值逐字match。

## 根核证与边界

7授权utils改变，第8schema producer未改；9382protected zero drift，source88 production/tests/locks同字节。root全文读全部实际diff、完成/partial/delete producer与消费者真实字段、采集器及AST检查算法、完整报告/summary、成功失败两receipt/source/streams。仅静态类型、直接第三方方法及必要中文docstring；无新JSON校验/默认/排序/输出/异常策略，纯JSON consumers不运行时加载Docling模型。

UPR-R01真实DoclingDocument owner和直接iterate_items成立。UPR-R02递归签名裸容器已消除，共用producer types、最小DensityRow/DiagnosticRow以及complete/delete视图成立。复审必须核静态视图/cast与真实producer字段链一致（包括SampleSummary读取计数与最终derived字段），不将cast当runtime验证。此处核收实施证据，不替同版双复审或提前PRpass。

全pyright第一次PID4925 actual1/21可选字段报错；第二次PID4979 actual0/0errors0warnings0infos，实际Popen.wait、独立两流/前后源SHA/最终SHA一致。原失败源码8件/采集器/票据/日志完整保留，root另备一份。唯一非零item_16由item_23同owner类型补全恢复；不豁免错误或配置降级。初源码合并读/source88列表输出截断不采全文声明，后定点读取/完整stdlib88字节核恢复。报告说版本提示在stderr不准确：两stderr实际空，提示在stdout，仅报告文字收窄，不改原证据。

AST核对剥离类型/docstrings/恒等cast、same-dict别名及旧getattr方法绑定；在实际已读等价变动范围内成立，不证明任意新cast安全。recursive AST无bare/object/Any，实际消费者import没有docling/dayu.documents/dayu.fins模块加载。utils免测试/cov，本轮未pytest/OCR/XBRL/CLI；671与S3证据只samehash继承，不重复充分验收。README无职责触发。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [item_16初pyright1已owner修复并item_23恢复0, 初读取截断必要来源已恢复, report stderr说明收窄]
evidence_gaps: []
retry_class: none
```

## 状态与下一入口

UPR-R01/R02实施已验证，最终已修状态待同版MiMo/DS delta复审/root回写；current gate=re-review PR review。基线完整PRmain...44已审；本次只冻结7utils新delta＋8source身份，复用原41961行实际核收，不再重复全文；当前remote仍44不冒其含本地fix。双审accepted后protected PRreview commit/普通push/newhead readback/draftPRpass/finalcloseout，继而独立完整CLI/oracle/scenarios。

Residual：静态cast不runtime验证是现有数据消费边界，不升级新parser；CLI/registry后置assessment；LinuxWindows部署已批准后续平台WU；第三方API维护Documents依赖owner；财务准确性Docling上游#4437。无新slice/goal/平台承诺。
