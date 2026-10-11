# SEC HTML 图片依赖修复 Gateflow 控制记录

- Work unit：sec-html-image-assets。
- Branch：fix/sec-html-image-assets；base：297bfbbc67b7d7468e3dfb6669a3385c4dd10d18。
- Binding scope：docs/plans/sec-html-image-assets-goal.md，用户已确认全部目标/非目标/边界/五项成功信号。
- Status：active。
- Current gate / next entry point：accepted plan commit。
- Active review loop：plan review。
- 本任务无外部 issue 编号，按 bug fix work unit 执行；不创建 issue 或对外 comment。
- 原业务 workspace/证据目录只读；正式真实验证只写独立临时 base。
- Routing：gpt-6-sol plan/implement/fix；mimo + ds-flash runner 子进程并行 planreview/deepreview；总控裁决、验证和 checkpoint。

## Gate history

| Gate | Artifact / evidence | Decision / validation |
| --- | --- | --- |
| goal confirmation | docs/plans/sec-html-image-assets-goal.md；docs/validation/sec-html-image-assets-remote-preflight.json | 用户明确确认；目标成立；branch clean baseline 已核查，远端抽查通过 |
| plan | docs/plans/sec-html-image-assets-plan.md | gpt-6-sol runner实际退出0，agent_status completed；1个S1，覆盖下载依赖/Phase A-B门控/rebuild版本真源/事务/真实验证；待双路planreview |

### plan review：进行中裁决

- ds-flash：实际退出0，artifact `docs/reviews/plan-review-20261011-180741.md`，结论fail。工具异常为已恢复的搜索/命令与closed stdin错误，不影响最终artifact；未以runner机械状态替代业务审查。
- `SECIMG-A1`：accepted / 未修复。总控已核对 `test_sec_earnings_repair.py` 的 MockTransport URL白名单与注册集合/指纹断言，以及 META cover 的img依赖。必须在plan fix纳入该既有测试文件，使用明确标识的确定性mock图片供数并按完整描述符集合迁移断言/focused命令；不修改生产筛选规则、不伪称mock字节为官方真实资产。
- `SECIMG-A2`：accepted / 未修复，仅需澄清与测试断言。沿plan已有完整集合发现之后的 `remote_files_equivalent` 规则，不另造版本或空指纹兼容分支；明确GET/发现/失败先于该晚期跳过的行为。
- `<base href>`：needs-more-evidence，待合并mimo审核及总控图像URL语义判断；不能直接采纳“忽略base”的下游猜测。
- mimo：仍在途，必须取得实际退出和artifact才可裁决当前review gate，不能提前进入fix/accepted plan。

### plan review：合并最终裁决

- mimo已实际退出0、artifact `docs/reviews/plan-review-20261011-180739.md`，结论fail。
- 最终decision真源：`docs/reviews/plan-review-20261011-183624.md`，前述进行中记录为历史。
- accepted / 未修复：SECIMG-A1、SECIMG-A2、SECIMG-001、SECIMG-002（合并base open question）。
- SECIMG-003：rejected-with-reason，保持平铺资产owner边界与明确失败诊断，不新增目录资产契约；真实案例出现时按独立需求处理。
- 下一入口fix，只派发gpt-6-sol修改plan；修后mimo+ds-flash同时re-review。

### plan fix

- gpt-6-sol实际退出0、agent_status completed、validation_status passed，无工具异常；日志 `agent-run.IVM9ffkS/output.jsonl`（系统TMPDIR）。
- Artifacts：`docs/plans/sec-html-image-assets-plan.md`、`docs/plans/sec-html-image-assets-plan-fix.md`。
- 四accepted项已由worker修订，状态为待独立re-review，未创建accepted plan commit。
- Production/test code仍未修改；下一入口re-review，由mimo和ds-flash同时审核修订并回写各自原finding状态。

### plan re-review pass

- Artifacts：`docs/reviews/plan-review-20261011-184431.md`（mimo）、`docs/reviews/plan-review-20261011-184432.md`（ds-flash），runner均实际退出0、validation_status passed，无异常；原review已回写。
- accepted最终状态：SECIMG-A1、SECIMG-A2、SECIMG-001、SECIMG-002均已修复（计划级）；SECIMG-003 rejected-with-reason，状态证据失效。总控最终回写在 `plan-review-20261011-183624.md`。
- SHA-256复验前后不变：plan `aa377b3a34294b204a226b67e1df9ac08fae4695f41367fe4f83d385802ac873`，fix `1a4bd5853d394ec6b158c485a7c5dbcf83678eab1c3a989b9e3cc29c8a0c4750`。
- Review loop通过，无阻塞/未分类risk；下一入口accepted plan commit，然后implementation S1。实现与真实验证尚未执行。

Plan runner日志：`/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/agent-run.VpcIvyJL/output.jsonl`。runner validation_status needs_review 的两项工具异常已核对：搜索过不存在的旧存储文件路径，随后恢复到实际文件；`git diff --no-index --check /dev/null <新增plan>`返回1且无错误输出，为新增差异的正常状态。没有遗留阻塞，不以runner退出0替代plan审查。

## Findings / residual risks

- 当前没有已裁决 finding。
- 两实例全部图片远端可用性及下载/补齐/失败/版本行为：covered by later approved slice，须在 plan/implementation 落实已确认成功信号。
- 外站/跨申报/OCR/数值提取：assigned to later work unit；owner 后续需求提出方，destination 后续独立需求，本次 scope 排除。

## 修改前验证基线

- 激活 `.venv` 后运行 `python -m pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_download_failure_diagnostics.py -q`：264 passed，3 个既有第三方 deprecation warnings，9.32s。
- 激活 `.venv` 后运行 `pyright`：0 errors、0 warnings、0 informations。
- 基线日志位于 `workspace/tmp/sec-html-image-assets-tests-baseline.log` 与 `workspace/tmp/sec-html-image-assets-pyright-baseline.log`；摘要为 durable evidence，临时日志不提交。
- GitHub repository 已确认：`noho/dayu-agent-r`，默认分支 main。

## Authorization

- 新工作分支、新 draft PR、按 Gateflow checkpoint commit/push 已授权。
- merge、部署、mark ready、request reviewers、外部 comment/issue 等未授权。
