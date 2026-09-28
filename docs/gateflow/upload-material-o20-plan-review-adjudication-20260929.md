# UM-O20-F01 计划审查裁决

- Gate：plan review → fix；工作区 `/private/tmp/dayu-upload-o20`，基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- MiMo 独立审查 `docs/reviews/plan-review-20260929-014020.md`：退出 0，JSON `subtype=success`、`is_error=false`，canary `mimo-ec8113a1`，stderr 仅模型名白名单提示；结论 fail。Sol 原 plan 派发有失败 command event，故其文字只作为候选，以上代码事实由审查独立复核。
- Kimi 因本额度窗口 HTTP 403 尚无有效审查；此次裁决不构成双路 gate pass。

## 逐项裁决与修复登记

1. **F1 接受**。计划吸收主工作区 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`：本 HEAD/当前依赖下有效 Docling JSON 真实上传成功；完整 XBRL instance 当前部署失败，首因缺 Arelle，补 2.44.8 后默认 taxonomy fetch 关闭仍阻断，进一步本地 fetch 试验触发第三方 `memberQname=None` 异常。区分已证事实与 E01 未完成项。F01 只给“候选资格、不保证转换”的非承诺说明，因此当前证据本身不触发停止条件 3；若为了准确文本必须改 capability、装配或依赖，则停止 F01。F02 已触发且独立，不能进入本切片。
2. **F2 接受**。目标段删去未获 goal 确认的“运行环境”文案承诺。计划钉死新增两句的精确文字与插入位置：在现有“后缀通过只表示具备转换资格，不保证文件内容转换成功。”之后、“delete 不得提供文件。”之前插入“`.json` 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl` 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。”文案不得承诺任何有效输入或部署一定成功；环境归因交 F02。
3. **F3 接受**。filing 文案按已确认 goal 逐字维持，不在计划中无保留宣称“准确”。filing `.xbrl` 限定缺口、linkbase 边界和 filing/material 术语一致性登记为 `UM-O20-F02` 所需所有公开入口清算问题；F01 不越界改 filing。
4. **F4 接受**。验证命令纳入计划自称的 SEC/CN workflow 与 Docling upload service 测试文件；完成信号明确 batch 只按同一 capability 作后缀准入，本无独立内容格式文案。
5. **F5 接受**。实施环境按 README 锁约束建立本地 Python 3.11 `.venv`，报告区分此前主工作区 venv 基线与本地实施验证。单文件覆盖率选用 tests/README 记载的 `coverage run/report --include` 惯例，或者明确 pytest-cov 口径及其 80% 阈值，不能混用数字。

开放问题 Q1 并入 F3；Q2 以上两句已用“格式的 JSON 文档”和“财报实例文档”给当前任务必要的短释，不扩写 filing；Q3 接受现有 argparse 排版上限，只要求实际 help 语义连续可读，若读不清则在已批准文案范围内调整断句并复审；Q4 依 F4。R1→F02，R2→E01，R3/R4/R5 保留。修订后双路 plan re-review；未获 Kimi 有效结果前不实施。

## MiMo 修订计划复审（2026-09-29 02:06）

MiMo `docs/reviews/plan-review-20260929-020447.md` 退出 0，JSON `subtype=success`、`is_error=false`、canary `mimo-31701302` 匹配，stderr 仅白名单提示；结论 **pass、无未修复 finding**。固定两句与本裁决逐字一致、E01 的 JSON 成功/XBRL 失败环境边界、F01/F02 停止条件、filing 原文保持、batch/SEC/CN/Docling 回归以及锁定本地 venv/coverage 身份均经该路独立重证。reviewer Q1 建议真实 CLI help 断言先做空白归一以避免折行假失败，接受为 implementation 测试口径；owner help 原文字段仍须逐字断言。filing 与 material 的 Docling JSON 同义措辞差异交 F02 术语清算。Sol 修订派发有三条非零 command，`agent_status=failed`，本审查不替代 Kimi 第二路；产品未实施。
## 双路复审与计划接受裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-020447.md` 与 Kimi `docs/reviews/plan-review-20260929-023440.md` 均退出 0、JSON success、canary 匹配、stderr 仅白名单模型名提示；各自独立确认 F1–F5 已按本裁决落实，无未修复阻塞 finding。Kimi 提出的 help 自动折行观察交实施时采用 owner 原文逐字断言、CLI help 以归一空白或片段顺序断言；不得让终端宽度成为误报。filing/material 对 XBRL 的术语清算属独立 F02，不扩大 F01 goal。

总控裁决 **plan review gate pass**，当前候选计划可作为 accepted plan checkpoint。Sol 原 plan/fix 的失败命令状态保持 `agent_status=failed`，接受依据是双路独立内容审查与总控核对，不追认派发成功。下一 gate：accepted plan commit → Sol F01 implementation。F02 仍待用户对 XBRL 部署能力目标的独立裁决，不在本切片暗改 capability。
