# 巨潮美的下载失败：目标确认

状态：用户已完整核对并确认；授权及当前 gate 以 `cninfo-midea-20261018-control.md` 为准。

## 输入、授权及预检

- 已完整读取 `/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/code-seed-20261017/g0-development-20261018/dayu-task.md`，以及本项目 AGENTS.md、gateflow、sub-agents 技能。
- 原始调用与证据目录：`/Users/leo/workspace/portfolio-manager-v2/orch/jobs/000333-fy2025-income-g0-20261018-132725/download-01/`。已读取 invocation、version、result、diagnostics、stdout、stderr、dayu.log；原始证据不覆盖。
- 预检：原分支 main，工作区干净，HEAD `1b2166305428d894696974519615cfc4a0ca3b20`，与原始失败版本一致。任务文件明确授权新建修复分支，因此已创建 `fix/cninfo-midea-report-identification-20261018`，不需重复申请建分支。
- 用户要求先确认目标；确认后通过外部 runner 派 gpt-6-sol plan/implement/fix，mimo-flash 与 ds-flash 并发独立 review，总控裁决。推进至 draft PR 与 final closeout；merge 另需授权。不设置巡查或 timer。

## 动机与直接证据

动机成立：真实调用退出 1、终态 failed、provider_transport/protocol；全零计数及空 failed_documents 不能证明没有报告，也不能据此指定失败 document_id。

直接代码事实：

- `dayu/fins/downloaders/cninfo_downloader.py:308-355`：发现阶段读取准入年度公告 PDF，调用年度事实解析后才形成候选及准备资产。任一解析失败可在候选结果形成前中止。
- `dayu/fins/pipelines/cn_annual_report_facts.py:14-62`：年度事实 owner 当前只读 PDF 首页，按物理行识别年度报告标签及封闭后缀；文本缺失、冲突或未支持形式均拒绝。
- `dayu/fins/downloaders/cninfo_downloader.py:1003-1010`：解析 ValueError 统一包装为当前诊断信息，不包含具体公告身份或解析原因。
- `dayu/fins/pipelines/cn_download_filing_workflow.py:285`、`:1065` 还复用同一事实 owner，分别涉及下载资产核验及本地年度原件复核；`cn_download_workflow.py:1150-1184` 读取本地年度原件，另一类本地声明失败也会使用同一外层错误文本。
- 当前绝对 CLI 脚本指向本仓库 `.venv/bin/python`，环境存在 editable 安装记录。此证据尚不等于修复后的入口可用性验证。

目前只能确认失败与这些路径相符，尚未定位真实失败公告、响应内容及 parser 拒绝原因；不得把代码限制直接当作本次根因，或猜测失败报告。

## 目标

1. 取回实际查询候选、官方响应/PDF 及解析依据，定位与原始错误同源的根因；若来源已变化，明确记录当前证据与原始事实的可证明边界。
2. 在下载/识别语义 owner 或直接上游校验处修复通用规则，使原 ticker `SZ:000333`、日期 `2025-01-01` 至 `2026-10-18` 的普通增量下载能够正常发现、识别并完成；身份、财年、全文/摘要性质始终准确、一致。
3. 真正无法确认的来源仍明确失败，并留下足以定位来源与拒绝依据的安全诊断，不静默跳过或伪造结果。候选形成前不得虚构 document_id。
4. 检查并覆盖同一 owner 的实际受影响远端发现、下载复核、本地原件复核及增量复用路径；范围以代码和复现证据确定。
5. 提交回归、类型检查、必要文档、双路审核/裁决和实际修复复审，交付 commit、draft PR、风险及当前绝对 CLI 的可用性证据。

## 非目标与边界

- 不改 portfolio-manager 调用方代码、范式、业务产物；不手工修改其受管 workspace。需要写入来源时只通过正式 Dayu 路径。
- 不缩窄日期，不传 forms/overwrite/rebuild 绕过，不做美的/股票代码/公告 ID 特例，不在下游补偿错误事实。
- 不用发布日期推导年度；自然会计年度规则只有经权威依据核实后才可参与识别，不证明具体文件是全文。
- 不顺带重构无关 provider、公共运行时或业务流程，不引入无当前需要的框架、兼容层、schema 迁移或 OCR 基础设施。
- 保持现有分层与仓储唯一写入路径；若实际方案需要改变已确认公共契约、验收标准或重大架构边界，重新确认。
- 重跑使用新日志路径，保留原始证据；外部服务不可用与识别缺陷分别记录，不能以测试通过替代真实调用结论。
- draft PR 不代表当前入口已生效；核实实际导入位置与运行行为。额外部署或 merge 超出当前授权时先报告。

## 成功信号

1. 真实来源身份、查询/响应和原件证据可取回；失败根因有可重复、同源证据，修复前失败与修复后成功可对照。
2. 相同日期及普通增量参数，经当前 `/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli` 正式入口完成下载；结果中的报告身份、年度及原件性质可核验。再次普通增量可正确复用已有来源，不误写或重复下载。对真实外部限制如实说明，未取得必要证据不宣称验收通过。
3. 合法原件布局得到正确识别，摘要、冲突、证据不足与非法响应仍明确拒绝；失败能定位实际来源，不靠放宽筛选掩盖。
4. 激活 `.venv` 后受影响测试及 pyright 通过，修改文件覆盖率目标 >=80%；README 按各文档职责检查并记录更新决定。
5. mimo-flash、ds-flash 对最终组合版本完成独立并发完整审核；accepted findings 修复并复审，所有风险有分类、owner/destination。
6. 已审成果提交/push，draft PR 身份、完整 diff、head/base、标题正文、必要 CI 与最终 push 经总控交付核对，final closeout 留档。未 merge。

## Artifact 位置与后续入口

- 目标确认：本文件。
- 计划、总控核对、实施/验证、裁决、PR 交付核对及 closeout：`docs/reviews/cninfo-midea-20261018-control.md`（确认后建立）。
- 独立审核及必要复审：`docs/reviews/cninfo-midea-20261018-*.md`。
- 原始取证、新日志及 runner 交接材料：`workspace/tmp/cninfo-midea-20261018/`；可追踪摘要、来源与验证结果回写 review artifacts，必要回归 fixture 放在 tests 对应目录。
- 后续交付 URL：draft PR 创建后回写 control artifact，不预设 PR 编号。
- 用户目标确认已完成；继续按 gateflow 自动推进。若明确外部阻塞或超范围决策再报告。
