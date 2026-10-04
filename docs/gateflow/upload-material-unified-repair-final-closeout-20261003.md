# upload_material 统一修复 WU final closeout

## 状态、范围与变更

**final closeout pass / work unit completed**。用户批准的剩余17修复标签及O20F02受控XBRL在一个WU、三个完整行为slices实施，不按finding/文件拆WU。现成逐项业务裁决及后续明确选择为真源，CLI CI/oracle/scenario不并入本WU。

- S1：完整参数/材料稳定身份前置准入、240Unicode码点名称、财政字段独立可省、form/文件名统一owner、exact primary与角色指纹、空字节/Docling失败统一typed五字段、仓储材料primary合同。
- S2：auto/create/update/delete与amended/overwrite，Docling生成及manifest提交才成功，跳过按完整性核；同bytes metadata-only与overwrite实际重转、writer条件发布/同身份并发/取消可信终态、公司事实独立。
- S3：macOS arm64/Python3.11受控真实XBRL支持；标准依赖/可信taxonomy manifest与完整性、受控复制/worker复验、允许明列runtime只读/公开XSD，拒用户workspace/私有内容/出站网络。没有新增资源图parser/Docling抽取质量门槛。
- Aggregate：真实CLI命令名称诊断、死常量、测试目录隔离、原191字节Raw可逆载体与引用保全。
- 正式PRreview：两项utils owner类型与裸dict签名集中收口；纯静态形状，原统计/排序/输出/异常保持。两路实际同版复审、总控核完整轨迹和source/票据，不以两票一致代裁决。

binding plan/control与正式UM裁决、各slice/aggregate/PRfindings登记保持，不重裁已完成F2–F7/#198，不顺带实现22独立残余。旧Raw与失败票据不覆写；CLI旧Raw已删除的事实仍保。

## Gate与验证证据

| checkpoint | commit |
|---|---|
| accepted plan | 6c49f818efd5a11b4dbd91d9a44f3bcfb2c01e58 |
| S1 | f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235 |
| S2 | a514dea14c0ce66722da034502f3af54a54c3238 |
| S3 | ec54351e58e66cd5d00b009c862589b109064ade |
| aggregate | 44c1892e7361dba799154fc01b2a4dfe43407e75 |
| accepted PR review | b1c675e75748abdcd8989cf6dffba257427feda5 |

S1宽验证2175passed/3skip，19prod各>=80/fullpyright0；S2宽2643passed/3skip，28prod各>=80/type0，末owner81pass/core96.15%；S3当前完整42受影响文件2841passed/3skipped、38prod各>=80、全pyright0；真实受控XBRL positive与4negative合计5pass无skip。三skip为2Windowscmd+optionalPDF，非XBRL失败豁免。

Aggregate当前671passed/0skip/3既有edgarwarnings，两个生产文件coverage82.44/90.66%、fullpyright0。原union01 NumPy collection failed保留；同source--cov恢复671，不声称已定位NumPy根因，不改依赖求绿。原失败票据和完整current JUnit/cov/dualstreams/argv/PIDwait/source身份均保。PR纯utils fix首fullpyright21错误版原件保，次PID4979/Popen.wait实际0/0errors，current8source前后同hash；生产88source与aggregate同hash，上述业务验证合法继承，未重复执行/不冒CLIcampaign。

同版PR baseline mainfac...44完整1059path：158人工维护文件41961diff行，26fixture仅Raw/provenance，875历史治理叙事不全文；原MiMo2条未修改context遗漏由root实际补，计数范围如实保。491fixdelta两路均实际全Read，UPR-R01/R02已修；MiMo未来访问texts_delta假设finding明确rejected-with-reason，无现存错误读取/投影。全部accepted项已修并复审，无blocking问题、无未分类residual。正式PRreview27文件checkpoint/index逐SHA/cachedcheck0/Gitblob回读0，普通push实际0；local/tracking/live/PR同b1c675e7，8source与所审fixedsourceexact相等，draft-PR-pass成立。

详情：`evidence/upload-material-unified-repair-20261002/{s3-final-validation,aggregate-fix-validation,formal-pr-fix-validation,formal-pr-rereview-ds-coverage,formal-pr-rereview-mimo-coverage,pr-review-checkpoint,pr-review-push-readback}.json`；各slice/aggregate/formal-pr-final-root-adjudication及findingregister。子Agent真实工具失败/掩盖/临时写边界偏离已root登记收窄，不冒中间均成功；完整streams双备份逐SHA保。

## 文档与PR / issue

根README、dayu/Fins/tests职责README按真实用户流程/层边界/测试范围更新；typedutils增量无新README职责触发。plan/control/全部实施、复审、root裁决与证据身份已进入唯一开发分支。

PR：https://github.com/noho/dayu-agent-r/pull/197 ，保持OPEN/draft，用户手工merge。不新PR/ready/approve/review-request/merge；main local/remote/PRbase fac32ecbff9bfe792b63ee9667c8697826b631f4未改；全部开发在唯一workspace `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`。MERGEABLE/CLEAN/checks[]仅当前观测，不未来merge保证。

#198既有已闭环范围未重开；实时body含唯一 `Closes #198`，授权既有closeoutcomment实际serverreadbackSHA0d9ce292651ed5f1e53b494cc67a612eb7b8e751eeeeda8e04a685c05beda7b9，https://github.com/noho/dayu-agent-r/issues/198#issuecomment-5893424991 ，指向draft197且明确remainingowner/用户merge后关闭预期。未重复发布comment，issue保持OPEN直至用户merge。

## 剩余风险、owner与下一入口

- Linux/Windows XBRL实装/隔离验证：用户明确延期，owner平台后续WU；仅macOS已验收，不声明跨平台pass。
- Docling抽取准确性及其上游问题：Docling owner/#4437；项目只承诺转换与typed失败、非抽取质量；XML graph/任意机制闭包未承诺。
- 22独立residual及历史CNInfo日期迁移：原owner/候选索引后续WU，未授权自动加入。
- 原旧upload_material CLI Raw：用户确认已删除，历史不可读事实保；新campaign明确supersedinglineage，不能补造旧证据。
- **下一入口：独立完整upload_material CLI CI calibration-real→冻结facts-only report→MiMo/DS双路建议→root依现成裁决正式登记oracle/scenario→readiness验证/普通checkpoint/push到draft197。** 未开始，没有full-real-pass或registryready声明；修复WU完成不是整体任务完成。真正新未裁predicate须用户裁决，既决项不再问。

本summary后纯治理checkpoint不改变产品/所审8source；后续CI target须以其最终真实local/tracking/live/PR一致SHA冻结，不能沿用b1c审查SHA冒最终代码版本。普通gate继续推进，不停机。
