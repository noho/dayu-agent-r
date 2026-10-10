# 下载失败诊断 final closeout

Work unit download-failure-diagnostics-20261010；Gate：final closeout pass；completion status：completed。总控按用户确认的Dayu下载职责与后续reviewer路由授权完成全部gate；无生产新观测或下载。Draft PR：https://github.com/noho/dayu-agent-r/pull/199，OPEN/isDraft=true，未merge/approve/mark ready/request reviewers/comment。

## 改了什么 / root cause

旧运行53=34downloaded+11skipped+8failed，exit0为调用结束，不等于全部成功。代码链先由workflow产生安全reason，CN/HK adapter将说明泛化，public终态只前十行（该运行全为skip）；默认日志使用临时文件且退出关闭，原运行无log-file，失败诊断没有可取得完整契约。这是原因投影、结果裁剪和取得路径的同源缺陷，不仅UI print；8个实际PDF失败的根因仍未知，不推404/网络/窗外。

五生产改动：download_contract公共摘要预算常量同源；direct_events以full typed结果为唯一输入，共享行投影、构造时校验全部FAILED、派生bounded与完整失败JSON；ingestion_runtime全链保留full、claim前受理/取消预构造、公共拒绝安全整体收口及activation request-scoped空结果；cn_pipeline严格保留CN/HK已有安全reason/metadata；CLI默认唯一 `Fins download diagnostics: <json>`，完整失败不按条数截断，摘要显示terminal_disposition。原退出0/1/130、stdout/stderr、quiet业务输出、LLM/durable有界保持其契约。未改网络/下载/重试算法或source schema。

## Gate与commit

| Gate checkpoint | Commit |
| --- | --- |
| accepted plan | a1df000835c61d1acfa383532488746e1487ed7b |
| accepted S1 | 12df3862f979a1fcf7b28300573f45322d21361b |
| accepted aggregate deepreview | 23c1046fe1f4b8ac5e66fab02b855d85d1cb632d |
| draft readiness控制记录 | e7be21828b0c364306427b6e38de2414b7eb8c92 |
| accepted PR review | f7162206076a0757e19e15e36feb7533792c05ec |

PR双路精确review base c65c2aa28fae9c47ad947783d63f7559db7768c4/head e7be21828b0c364306427b6e38de2414b7eb8c92；之后仅本unit控制docs，root核production/tests/README bytes与S1相同。accepted PR review final push session97579真实exit0，GitHub head=f7162206076a0757e19e15e36feb7533792c05ec、draft/open、base稳定，满足draft-PR-pass后才创建本closeout。不把新文档commit伪称新的生产版本review；本artifact与控制记录将另以docs-only checkpoint发布，最终GitHub head及全hash见最终交付答复/PR。

## 验证与docs

- 受影响A14：1497 passed/0 failed/0 skipped，真实exit0；全仓dayu/tests/utils pyright 0 errors/0 warnings/0 informations。
- 五生产文件coverage：output85.58%、direct_events90.23%、download_contract88.42%、ingestion_runtime91.23%、cn_pipeline82.53%，每文件>=80。
- 后续doc-only两次：七文件1003 passed和F5文件9 passed/各全type0，函数逻辑/断言与去doc AST不变；不合并重复case数量。DS aggregate另选184离线通过，明确不是A之外新增总数。
- 更广测试67 failed/5059 passed/14 skipped exit1；原base隔离六文件67 failed/652 passed，同67 case已实证匹配。不能声称全suite绿，14skip未计通过。
- 固定absoluteCLI空来源根、仓库外cwd离线rebuild smoke实际返回0与唯一可解析行，含在受影响集合；未访问生产根或远端故障。
- 三README：根用户取得诊断/通道/退出/日志，Fins owner与完整/有界契约，tests现有测试/离线smoke；无层级装配变化，dayu总览无触发。
- GitHub statusCheckRollup=[]；exact-head check-runs total_count=0；status state=pending,total_count=0,statuses=[]。无CI检查结果，非CI pass；总控允许以绑定本地验证交付draft，CI/merge限制保留。

验证hash与命令/真实终态见implementation/code-fix/doc-fix/R2/slice/aggregate/PR adjudications，coverage和原base67对照见baseline-validation。最终入口实证见fixed-cli JSON，不以旧implementation表或0.1.4版本当最终身份。

## 双路review与canary证据

| 阶段/路由 | 报告 | 真实结果 / token |
| --- | --- | --- |
| S1最终 gpt-6-astra | docs/reviews/code-review-20261010-152859.md | exit0/turn.completed；gpt-6-astra-ab5b6054逐字match |
| S1最终 ds-flash | docs/reviews/code-review-20261010-153232.md | exit0/turn.completed；ds-flash-73304fb5逐字match |
| aggregate gpt-6-astra | docs/reviews/code-review-20261010-154751.md | exit0/turn.completed；gpt-6-astra-f3475c79逐字match |
| aggregate ds-flash | docs/reviews/code-review-20261010-155018.md | exit0/turn.completed；ds-flash-f3d29708逐字match |
| PR gpt-6-astra | docs/reviews/pr-199-review-20261010-160216.md | exit0/turn.completed；gpt-6-astra-5562dc29逐字match |
| PR ds-flash | docs/reviews/pr-199-review-20261010-160054.md | exit0/turn.completed；ds-flash-6e804c03逐字match |

完整preflight/托管session/run_dir/JSONL hash、所有非零命令及恢复、stderr warnings、required evidence与root独立核验在slice/aggregate/PR adjudication。S1 DS closed stdin与PR两路MCP403缺请求轨迹如实标partial，但全部必要证据独立完整；不抹去失败。DS PR bullet使辅助parser报false，root唯一token与actualcat逐字匹配，不改token。mimo两次和临时一次mimo-flash拒绝未产出报告，不计pass；用户新授权gpt-6-astra完成该路缺失/后续review，provider-decision及拒绝JSON归档。不使用内置子Agent。

Finding状态：P1—P4计划已修；C1/C2/R1/R2代码/中文文档均已修并双路复审；DF-01 rejected-with-reason（历史实施表非最终身份）；aggregate/PR无accepted未修，fix/re-review均明确no-op pass，无blocking question。

## 旧运行能恢复与不能恢复

old-evidence JSON SHA008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2记录全部8ID、published_meta missing；原stdout hash/53分类计数及8 PDF file_failed阶段已核。仓储公开接口只读当时45published、无read_error，未执行recovery/discovery/download；canonical metadata摘要d2010a1e5d30be536dd4f24b1cc53490ddeec68a875ad2e03d611e712b502b50。此不是45份内容逐字验收。具体原因、URL、披露/报告日期、期间不能从留存材料恢复，均未知。新观测不能当旧证据。

保留现有来源，未修改调用方workspace/Raw/范式/审核包/批准，初次交接要求证据之后按用户收窄不再读取业务文件。本轮没有overwrite、整批重跑、直接获取PDF或业务侧审核动作。

## 固定入口与继续步骤

`/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli` editable=true，shebang为本仓Python3.11；root从/private/tmp实际导入五模块，最终source hash与S1/aggregate/PR已审版相同。docs/gateflow/download-failure-diagnostics-fixed-cli-20261010.json SHAe4aba8f777ee7a28731c05fab87a73f1a78e77ca7d0436087228a921a525ff02。此入口当前可加载修复，无需重装；其它安装环境须采用修复commit，不宣称部署或merge。

继续命令及两通道/退出码捕获见download-failure-diagnostics-continuation-20261010.md。模板未执行，APPROVED_START/END及可选forms必须由巡检线先明确新获取范围与影响；现有CLI无按旧8ID重试参数，不能盲重跑原整批。批准后检查唯一JSON、完整failed_documents、计数、metadata未知与terminal_disposition/failure，退出0不能单独通过。腾讯业务G0恢复/通知workflow-run-tencent由巡检线核实后做，本单元不代批G5/G6、不发送外部消息。

## Remaining risks / owner / destination

| 规范分类 | 风险与owner/destination |
| --- | --- |
| fixed in current slice | 下载诊断丢失与C1/C2/R1/R2，当前单元证据闭合 |
| assigned to later work unit | 67原base失败→CLI/Service六文件相关owner；14资源平台skip→集成owner；SEC原因→来源owner；极端规模→性能owner；CI配置/真实checks→仓库CI owner |
| requiring new issue or explicit user decision | 旧8原因等未来观测/生产范围→巡检线；未捕获/崩溃历史及双原因治理→公共契约owner另定范围；merge/approve/ready/部署等→用户 |
| covered by later approved slice | N/A |
| tracked by existing issue | N/A |

Issue link/closeout comment：N/A，用户未指定issue，未创建或评论外部issue。无unclassified residual、accepted未修或missing required artifact。Next entry point：用户另行授权merge等；巡检线核实固定入口/证据并决定生产观测范围与业务恢复，不将本draft交付作为业务批准。
