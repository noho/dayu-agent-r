# upload_material 修复范围与最终真实 CI 收口约束

## 用户最新大目标（权威）

2026-10-01 用户要求核实完全按 CI 后本人裁决登记的修复项执行、完全遵守现成裁决；如有偏离纠正。任务大目标是完成修复项后重跑 CI，确定 oracle 和 scenarios。本文件将该终点显式加入当前总控队列，不用各WU代码测试/closeout代替最终CLI验收。

用户最终裁决 > 对应正式adjudication > 已接受goal/plan > 旧CI建议/Agent建议/当前实现。不能为使现有代码通过修改用户oracle，不能重开已裁决项或用未反对表示同意。

## 当前执行范围核对与纠正

1. 原36项逐项裁决形成的22个accepted upload_material修复方向，外加用户已明确批准的受控XBRL推进原则；每项依正式adjudication以及后续明确选择（名称240 Unicode码点、overwrite强制转换、Docling后manifest登记才成功等）实现。
2. #198按用户授权联合修复，已有final closeout及授权评论；不重开完成项。
3. 用户后来明确要求优先修PR197完整review成立F2–F7，之后回原upload队列。这是追加授权，当前F3/F4/F5/F6/F7即属于此优先范围，不冒称全都来自原UM矩阵。
4. 其它独立残余表/待goal条目是持久候选索引，**不自动纳入本轮必实施清单或计作已批准WU**。只有已有明确用户裁决/accepted goal的条目按真实依赖执行。需新业务规则、历史迁移或durable schema取舍必须另获具体裁决。
5. 必要review修复必须直接违反已有批准目标/合同、在其owner边界最小修正、立即登记并经总控裁决和同版双审；不得借review持续扩产品目标。F6-P1的SEC同根因由root直接证明若保留将使统一公共冲突提示错误，按已批准F6必要产生层修正，尚只补计划、未实施。

目前核对未发现已实施F4改写用户upload裁决；F3在审源码、F6在写计划，不能据此宣称全部产品行为已符合。先前handoff仅显式推进各WU门禁，缺少“最终真实CLI CI→oracle/scenarios→readiness”的整体终点，本次已纠正。修复闭环数量不能代替本大目标完成。

## 固定最终收口顺序

1. 完成上述已批准修复及必要review fix，按Gateflow核验测试/类型/README、同版双审及总控裁决；所有成果进入唯一 `codex/upload-material-oracle`，PR197保持draft、用户merge、main不动。
2. 解析最终被测commit SHA，核对local/tracking/live/PR head一致；只读CI验证快照不承担开发。冻结本次场景定义、用户裁决引用、输入/corpus digest和执行policy。
3. 遵循 `docs/cli_ci.md`，为本次upload_material完整mandatory范围新建真实CLI evidence run。范围/profile由实际inventory和readiness proof重新校验；不得用旧registry_status、局部smoke、mock单元测试或历史160次执行代替当前完整真实CI。受影响其它命令按实际依赖纳入回归，并明确范围；不悄悄重写已冻结其它命令oracle。
4. 保全command、stdout/stderr、exit、screen、文件系统前后、workspace/log/DB/Trace/process/durable等必需真实证据；明确attempted/executed/not-run/blocked/gap，旧Raw保持原字节，新run显式supersede lineage。
5. 将新实际结果逐项映射到用户已经接受的裁决：违反既有oracle即failure并最小修复/必要复跑；真正未裁新行为记oracle-review-required/needs-more-evidence，禁止自行选新业务语义。
6. 依据用户裁决与新证据正式登记/核对 `docs/cli_ci_oracles.json` 与 `docs/cli_ci_scenarios.json`、accepted版本/稳定predicate映射/场景覆盖/readiness proof。新版本替代需保留旧版本及lineage，不原地篡改旧oracle。完成判断必须含完整mandatory矩阵及proof核验，不能只报tests绿或PR MERGEABLE。
7. 汇报最终修复项状态、CI primary verdict、oracle/scenarios映射及readiness、仍有明确owner的残余和必要待裁项，用户手工merge。以上任一步未完成不得报告本大目标完成。

## 实时registry观察与当前工作

用户进一步明确：现有两个registry只完成download和upload；upload_material尚未完成正式登记和验收。root当前实际读取：两个正式registry字面status均ready，但 `oracles`/`scenarios` 当前没有 upload_material 条目。它们不能为新增upload_material范围提供ready证明；最终收口必须核对其scope并补正式登记及proof，不借用其它命令的ready结论。

当前checkpoint `a821da03911d76796e7ca53de2f9a813a56d595a`，local/tracking/live/PR已独立readback一致、main不变；F4 slice75fec已推，aggregate待槽位；MiMo65815/Kimi87199正在审F3；Sol50829仅补F6计划。F5混合确定/不确定报告的Q1仍未收到具体选择；本次总目标澄清不等于选择其中一种。

## 当前review中新观察的边界

root受控四模块CLI探针发现循环链接out-root在Path.resolve处报RuntimeError/exit1而未进入中文argparse拒绝边界，记录在 `workspace/tmp/pr197-controller-collection-20261001/f3-out-root-loop-probe/commands.json`。仅登记为F3输入owner的review候选，未自创独立WU、未修改代码、未改变oracle；在当前code review中按已接受输入错误合同裁决必要性后才决定是否属于本F3最小fix。它不得以“发现新问题”无限扩本轮产品范围。
