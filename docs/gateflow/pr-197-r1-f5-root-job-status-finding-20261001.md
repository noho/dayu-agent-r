# F5-IV04：持久化下载结果的 job 状态校验缺口

状态：中／accepted／未修复；同一F5-S1必要owner校验。不是新业务裁决，不扩通用job重构。owner=`dayu/fins/ingestion_runtime.py:_validate_record_operation_fields`（`_record_to_json` writer和`_record_from_json` reader共用）。

## 直接事实

用户binding/accepted plan规定uncertain>0整体FAILURE、jobFAILED，取消/F6优先且A保全。当前真实 `_run_download_job` 正常路径已正确选FAILED；本finding不宣称该路径现已错误，不以推测代替事实。

但fresh持久化owner只验证JSON完整结构/source/ticker/CANCELLED投影和SUCCEEDED非空，未检查SUCCEEDED不能含unknown。root用隔离真实FS jobstore显式构造合成typed known1/uncertain1、terminal partial_failure，save_job(status=SUCCEEDED)正常成功，随后actualread_job也返回succeeded且uncertain_count=1。没有执行真正download/network/PDF/provider，没有产品写。源码72SHA前后保持。

实证：`workspace/tmp/pr197-f5-interrupted-source-audit-20261001/root-job-status-probe.json`；激活.venv后Python exit0。持久化writer和reader允许同一未知事实同时投影为job成功，破坏唯一owner在durable/业务状态的一致性；一个上游错误调用即可存入不合法状态。不能以正常runtime已有分支正确为由让边界允许矛盾事实。

## 最小修复与验证

在现有共用record校验owner明确拒绝DOWNLOAD+SUCCEEDED+uncertain_count>0，不从durable JSON改写job状态/删除B/重算财政。严格拒绝错误输入，运行时继续产生正确FAILED/取消投影。使用已经validated的必填uncertain_count，不默认值/compatibility读取。不将这一规则机械扩到已有正常partial download语义，也不误拒收口异常导致jobFAILED却保留成功typed摘要的合法情形。

owner级回归覆盖真实store写入、freshreader与atomic succeeded入口拒绝矛盾记录，以及正常known+unknown FAILED、取消保全、无unknown原正常部分成功/真空、收口异常后FAILED保完整typed结果的合法读写。writer/reader复用同一现有校验，不下游wait/CLI纠错。

与IV01/02/03和诊断accepted项集中交付，不另开slice；此root报告不接受未完整实施交付或代码门禁。其它job状态/摘要规则若没有现成依据不顺带扩展。

## 2026-10-02 最终状态覆盖

accepted / 已修复；完整作者、正式两审及同版复审由总控独立核准。最终裁决见 pr-197-r1-f5-s1-code-review-final-adjudication-20261002.md。原未修状态为历史，不覆盖本条；code gate PASS，aggregate/PR/final closeout另行推进。
