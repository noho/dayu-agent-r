# PR197-R1/F7 候选计划总控取证与报告纠正

## 身份与裁定范围

- runner：codex / gpt-6-sol，label `pr197-f7-plan-sol-20260930-01`；托管 `10158` 已取得外层 exit0，76 条有效 JSONL，`turn.completed`，stderr 为空，最终消息与实际 canary 匹配。
- 独立 output/stderr/last 位于临时 run_dir `sub-agents.V6YhiY`；具体路径由派发记录定位，不把临时文件当长期唯一真源。
- candidate：`docs/gateflow/pr-197-r1-f7-plan-20260930.md`，SHA256 `4473d2a5e0de4b4cdbd1d8151e1fc9c6d068ff8f320384e9e945887a0d27abcf`。
- 六项输入与 `workspace/tmp/pr197-f7-plan-input-freeze-20260930.json` 匹配。起点 bb11ca22，收尾 60307c15 是已公告、与本任务无关的 F3 文档 checkpoint；不构成相关源码身份漂移。
- 总控实读普通结果、完整性快照、rebuild producer、两投影入口及 `_required_cn_text`，并在 dayu/tests 搜索全部 `_build_result`/旧状态常量调用。三个既有终态、入口子集与 strip 行为与计划一致；不授权任何新业务选择。

## 逐项失败与独立复核

1. `item_1` exit1：末尾 memory 搜索无命中；cwd/canary 已真实读取。没有用 memory 替代生产证据。
2. 最初两个 workspace 类型探针被仓库 exclude 排除，其 exit0 不作有效验证。`item_24` 正例 exit1/7 errors，`item_25` 负例 exit1/3 errors，属于探针 import 路径与已知常量比较问题；修 extraPaths/函数输入后，`item_27` 正例 exit0，`item_28` 负例 exit1/两项 reportArgumentType。
3. 总控激活 venv 独立用同一 strict config 和 `--outputjson` 复核：正例实际分析 1 文件、0 errors，负例实际分析 1 文件、恰两项参数类型错误（普通 str、failed）。JSON 证据保存到 `workspace/tmp/pr197-f7-root-literal_status_positive.py.json` 与对应 negative 文件；这里只验证候选类型写法，不是生产 F7 验收。
4. `item_22` 全量 pyright exit0 仅是该读取窗口的 baseline；F7 尚未实施，不能称修复后的质量门禁。新版提示不改变依赖或结果。
5. **F7-PV01（待修，低）：候选计划第 9 节收尾记录将单独 no-index check 写成 exit0。** `item_34`/`item_38` 实际是多命令组合，记录的 0 是最后命令退出码，不能证明前置 git 子命令为 0。总控单独复核 `git diff --no-index --check /dev/null <candidate>` 为 **exit1，stdout/stderr 均空**：这是新文件相对 /dev/null 的差异退出，没有空白错误输出。计划结构检查与 tracked diff check 是另两项，必须分别报告。
6. 总控第一次复核错误预期 no-index 必须 exit0，断言失败/外层 exit1；随后按真实 diff 语义修正验收，第二次独立复核 exit0。该总控探针错误及恢复保留，不能计第一遍为成功，不是生产 finding。

F7-PV01 必须由后续 Sol plan fix 修正候选计划的事实记录，然后核对新 SHA；这是报告准确性修正，不增加产品目标。当前候选可进入同版双路 Planreview，但未 accepted，不得带着错误事实记录提交 accepted plan。

## 子任务裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: partial
warnings:
  - memory 搜索无命中，不影响 canary 或必要源码取证
  - 初始被排除的类型探针弃用，隔离严格配置正负例已独立复核
  - no-index 子命令被组合命令掩盖，真实差异退出已总控解释
  - 全量 pyright 仅 baseline，产品实施尚未开始
evidence_gaps: []
retry_class: task
```

部分采纳方案和类型/源码取证，事实记录 F7-PV01 待修；不因该报告错误重派 provider，不抹除失败记录。下一入口为 MiMo/Kimi 同版 Planreview，之后合并真实 findings 与 F7-PV01 派 Sol 修订。审查始终以用户既有裁决为准，不改 status、取消、错误、摘要或 manifest 成功判定。
