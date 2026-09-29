# PR #197 完整 diff 审查：总控裁决

## 授权、范围与锁定快照

- 用户要求在继续后续 WU 前，总控对完整 PR #197 做一轮 PR review，并更新下一 Agent 交接 prompt；MiMo 与 ds-flash 两路同时并行 review，gpt-6-sol 只负责可能需要的 plan/implement/fix。总控独立核查结构化运行结果、证据链与发现项；本轮不 merge/mark ready/approve/comment。
- 2026-09-29 线上只读快照：`noho/dayu-agent-r` PR #197，title `draft: Dayu 修复集成（upload_material / 下载链路）`，base `main`=`fac32ecbff9bfe792b63ee9667c8697826b631f4`，head `codex/upload-material-oracle`=`2c1d0a712593e7b3e917d2c680f45a6d790095fd`，OPEN/draft/CLEAN/MERGEABLE，45 commits、255 changed files、32891 additions/339 deletions、`statusCheckRollup=[]`。以上是当前快照，不是最终合并日保证。
- 主工作树 `/Users/leo/workspace/dayu-agent-r` 在旧 `7234d42d` 且有 40 项工作树变化，不能作为完整 PR review 对象。两路各用干净独立 clone `/private/tmp/dayu-pr197-fullreview-mimo` 与 `/private/tmp/dayu-pr197-fullreview-dsflash`，HEAD 均锁 `2c1d0a71`；各有隔离 editable Python 3.11 venv，仓库外导入 `dayu.__file__` 确认指向各自 checkout。创建 worktree 曾因共享 `.git/worktrees` 权限失败，改用本地 clone，未改主工作树。
- 当前 diff 中 31 个 `dayu/` 文件、22 个实际 Python test 文件（`tests/` 总变更条目 43，含 fixtures）、11 个 `utils/` 脚本、constraints/配置/README 和 161 个 `docs/` 条目。#198 既有 PR review 只审其局部修复及交界，不抵整 PR review。

## 外部派发与待收结果

- MiMo `pr197-fullreview-mimo-20260929-01`：`sub-agent-preflight setup_status=ok`，显式 `--cwd /private/tmp/dayu-pr197-fullreview-mimo`，独立 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.jWET69/` output/stderr/canary，runner session `26407` 在途。完整 task `/private/tmp/dayu-pr197-fullreview-mimo-task-20260929.md`。
- ds-flash `pr197-fullreview-dsflash-20260929-01`：`sub-agent-preflight setup_status=ok`，显式 `--cwd /private/tmp/dayu-pr197-fullreview-dsflash`，独立 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.LDxOAq/` output/stderr/canary，runner session `19893` 在途。完整 task `/private/tmp/dayu-pr197-fullreview-dsflash-task-20260929.md`。
- 两路均只准新增 `docs/reviews/pr-197-review-<真实 timestamp>.md`，不得改代码/旧 artifact 或用沙箱 `gh`；线上事实由总控核对。审查完成前必须核进程 exit、Claude JSON terminal、stderr 白名单、canary 与真实 artifact、shell 命令失败记录，不能以自述代替 gate。

## 总控独立验证与初始观察

- 当前 PR checkout 全量 `pyright dayu/ tests/ utils/`：0 errors/0 warnings/0 informations、exit0。22 个变更的 Python test 文件同版隔离 venv 组合验收在途，未出 terminal 前不计通过。
- `git diff --check <main>...<head>` exit2，唯一输出为 `tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log:4` 的新增 EOF 空行；这是 fixture 日志的空白卫生问题，不当作业务 finding。后续裁决是否修该行；不得把全 PR diff check 说成通过。
- 首次 22 个变更 Python test 文件组合验收：**2127 passed / 2 skipped / 1 failed**。唯一失败为生成脚本真实 CLI 测试的 `/bin/sh` 子进程导入 `docling_core.types.doc.items` 失败。总控沿同一执行链核证：生成脚本使用 PATH 中的 `python`，首次验证仅以 venv 的绝对 `python` 启动 pytest，**没有 activate 使 PATH 指向 venv**；子进程因此落到 `/opt/homebrew/bin/python3` 的 `docling-core 2.71.0`，低于 PR 的 `pyproject.toml` 下界 2.96.0/受控 lock 2.96.0。本 checkout 隔离 venv 的 `docling-core 2.96.0` 实际含 `types.doc.items`。`source /private/tmp/dayu-issue198-pr197-testvenv/bin/activate` 后单独重跑该测试 **1 passed**。这是本轮 controller 环境配置失误，不登记产品修复；已在同一激活环境重跑整套 22 文件，待 terminal 后记最终结果。
- 最终组合重跑：先 `source /private/tmp/dayu-issue198-pr197-testvenv/bin/activate`，再对 PR diff 中 22 个变更 Python test 文件执行 pytest，**2128 passed / 2 skipped / 3 warnings，exit0，108.25s**。隔离 editable Python 指向当前 PR checkout；两个 skip 是平台条件项，三个 warning 是 edgar 弃用提示。此结果覆盖变更测试文件，不等于全仓所有测试通过。
- 本轮尚无两路有效审查结论或总控 findings 裁决；任何新修复项立即追加本文件和主队列 `upload-material-issue-198-repair-sequence-20260928.md`，明确 owner、状态和下一 gate。

## ds-flash 第一条有效审查与 finding 即时登记

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] deepseek-flash[1m]"
retry_class: none
```

- `pr197-fullreview-dsflash-20260929-01` 进程 exit0；Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、136 turns；canary `ds-flash-e4c65142` 与独立 expected 逐字一致，stderr 只有白名单提示，artifact 记录 shell 命令自身 exit0（预期失败探针用 wrapper 捕获）。独立 review `docs/reviews/pr-197-review-20260930-000803.md`，锁同一 base/head；31 个变更 dayu 文件/22 个测试模块实际覆盖，docs、utils 与 fixture 部分覆盖并明确列限。本路内容不是总控通过结论，待 MiMo 与直接代码核证。
- **PR197-R1/F1 中／待裁决**：生成脚本 `python` 依赖 PATH，reviewer 在未激活项目 venv 的系统 Python（docling-core 2.71.0，低于 PR 2.96.0 下界）复现 import 失败。总控已独立复现激活隔离 venv 后 1 passed、22 文件组合 2128 passed；README 安装入口先要求 `source .venv/bin/activate`。需裁决是否为真实受支持工作流缺陷，不能把不满足声明依赖的 PATH 环境失败直接算 PR 新 bug；也不能无依据把生成脚本永久绑定 `sys.executable`。当前只登记候选。
- **PR197-R1/F2 低／待裁决**：新增 `tests/fins/test_fins_ingestion_runtime.py` 循环外使用只在循环内赋值的 `result`；系统 pyright 1.1.408 报 `reportPossiblyUnboundVariable`，隔离 venv 1.1.409/内置 1.1.413 报 0。`pyproject.toml` dev 依赖下界为 1.1.0；需独立复现、决定是否由 test owner 移入循环/明确首例绑定，避免工具版本漂移。直接运行时三元素固定非空，无业务行为风险。
- **PR197-R1/F3 低／待裁决**：数个新增 `utils/` 分析脚本硬编码操作者私有语料绝对路径与样例持仓/文档身份，缺样本根参数。需核脚本是否仅为一次性私有验证且是否应随生产仓库发行，再判 portability/privacy 修复或 deferred owner；不改变生产路径。
- **PR197-R1/F4 低／待裁决**：HK `resolve_cn_download_ids` 对每候选遍历既有 filing 并逐条 `get_source_meta`（各自 publication guard）；同一 run 在 accepted id、repair sort、逐候选三处重复调用，静态 O(S·D) I/O。总控已实读三处调用与 owner helper；需核 selected 的真实上界和缓存时序/并发语义后再定修复，不用危险 stale cache 局部止血。
- Reviewer 还列 HK discovery 年度锚点、mismatch→rebuild 恢复、macOS Intel 支持范围、`--overwrite` 生效前提、6-K 标题形态五个 Open Questions，以及 docs/utils/fixture 未全读、无 CI 等 residual。总控须逐项分类，不能因 reviewers 命名为 OQ 就自动忽略产品事实。

## 总控第一性原理核证（第二路仍在途）

- **PR197-R1/F1 中／rejected-with-reason（代码缺陷不成立）**：`dayu/cli/commands/fins.py` 的脚本 `python -m dayu.cli` 在 base 和 PR head 均如此，PR 没有引入解释器选择变化；PR 的 `pyproject.toml` 已明确将 Docling Core 下界升至 2.96.0，受控 lock 亦为 2.96.0。失败子进程来自未激活 venv 的系统 Python，实测其 Docling Core 为 2.71.0，属**不满足当前安装前置**；根 README §1.1 的安装命令显式 `source .venv/bin/activate`，项目 AGENTS.md 修改后验证也要求先 activate。总控在激活隔离 venv 后同一真实脚本测试 1 passed，全部变更 Python tests 2128 passed。把生成脚本改写为生成时的绝对 `sys.executable` 会把可移植脚本绑定到可能随后移动/删除的 venv，并非更好 owner 方案。§5.3 运行示例可在未来文档维护时重复环境前置，但本轮无证据证明受支持流程下的产品缺陷；不创建 F1 修复任务。
- **PR197-R1/F2 低／accepted／待修**：总控用 `/opt/homebrew/bin/pyright` 1.1.408 在当前 PR checkout 对 `tests/fins/test_fins_ingestion_runtime.py` 独立复现第 6421 行 `result is possibly unbound`、exit1；隔离 venv pyright 1.1.409/内置 1.1.413 0 errors。新增代码在固定三项 tuple 循环后使用循环内变量，不应使声明支持 `pyright>=1.1.0` 的工具链版本出现红门禁。test owner 层把取消 disposition 断言放入循环或显式绑定目标结果即可，不改产品语义；待 MiMo 同版意见后交 gpt-6-sol 最小修与两路复审。
- F3/F4 与五个 Open Questions 仍待 MiMo 和直接证据完成裁决；本段不会因第二路未回就宣告 PR 通过。
- **PR197-R1/F3 低／accepted／待修或用户处置**：总控实读 `utils/docling_schema_regression.py`、`build_semantic_digests.py`、`verify_missing_tokens.py` 的私有样本根常量及 `ab_ocr_compare.py` 的六份绝对样本 locator；这些新脚本无 sample-root/manifest 输入，无法在其它工作区复用。仓库线上 `visibility=PUBLIC`，base 快照 `git grep` 对同一路径 0 命中，PR head 的新增 utils/部分 docs 含操作者路径和样本身份。正确 owner 是分析脚本输入，不是生产 Fins/Docling；最低限度应使脚本以显式样本根/清单运行并移除当前 tree 的私人路径。**历史提交与已公开 PR 内容不会因普通后续 commit 而消失**，若用户需要历史级清除，必须另作明确决策；本轮不强推或篡改历史 artifact。MiMo 第二路未回前保持修复路线待定。
- **PR197-R1/F4 低／accepted／deferred-with-owner 候选**：总控实读 `_select_candidates_for_a4` 在显式 `start_date` 下返回窗口内全部候选，无固定 5 年/2 年数量上界；HK `resolve_cn_download_ids` 对每个候选枚举 D 个 filing 并逐项 `get_source_meta`。仓储 `list_document_ids` 和每次 `get_source_meta` **各自**获取 publication guard；accepted id、repair sort、逐候选调用可放大到 O(S·D) 级锁/I/O。动机成立。把结果简单 memoize 可能跨并发发布得到旧身份，正确修法应在 storage owner 提供同一 publication guard 下的批量只读快照或明确运行期一致性协议，再由下载身份 owner 消费；不在本轮为低性能项冒险做局部缓存。后续 WU `fins-hk-download-identity-batch-read` 候选，待 MiMo 结果和最终裁决。

## MiMo 第二条有效审查与最终裁决（2026-09-30）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "[claude-code:unrecognized_model] mimo-v2.6-pro[1m]"
retry_class: none
```

- `pr197-fullreview-mimo-20260929-01` 进程 exit0；Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、119 turns，canary `mimo-d5ea0a39` 与 expected 逐字一致，stderr 仅上述白名单诊断；artifact `docs/reviews/pr-197-review-20260930-002934.md`，锁 base `fac32ecbf`/head `2c1d0a71`，结束时仅新增该 artifact、无产品改动。它审查全部 31 个变更生产模块与 22 个变更测试文件，历史 docs、utils 算法与 fixture 字节部分覆盖。ds-flash 的独立 artifact `docs/reviews/pr-197-review-20260930-000803.md`；总控结论为 `docs/reviews/pr-197-review-20260930-003634.md`。三个 artifact 与本裁决需一起进入 PR #197。
- MiMo F1 与 ds-flash F2 均指 test `result` possibly-unbound；总控维持 `PR197-R1/F2` **低／accepted／待修**。MiMo 标中是因为本机 `source .venv/bin/activate && pyright` 命中系统 1.1.408；隔离 venv 的 `.venv/bin/python -m pyright` 1.1.409/内置 1.1.413 为 0。版本偏差不抹掉声明 `pyright>=1.1.0` 范围内的门禁错误，也不把纯测试类型问题升为业务中断。Sol 后续在 test owner 最小修，两版复核。
- **PR197-R1/F5 中／accepted／待独立 goal**：MiMo F2 将 ds-flash HK 年度锚点 Open Question 升为 finding。总控实读 `select_hkexnews_report_candidates` 只用本次远端 `unique` 标题计算 `annual_ends`，`rebuild_hk_periods` 则在 ticker batch 中用本地 COMPLETE 年度来源计算锚点；`resolve_hk_report_period` 在只写“三个月+截止日”的标题、空锚点时返回 `None`，selected 差集随后可报告 missing。两入口的同一财期语义依查询窗口/本地缓存组合漂移；`test_hk_selection_uses_annual_announcements_before_period_filtering` 只覆盖年度公告在同一远端 batch，不能覆盖窄窗口加本地锚点。此前“三个月→Q1”的无证据捷径会误判，不能恢复。owner 为 HK 年度证据与下载财期投影；新 WU `fins-hk-fiscal-anchor-consistency` 先定本地 COMPLETE 与远端锚点的可信、时序/并发、冲突规则，并区分“有报告但证据不足”与“无报告”。mismatch/rebuild 提示在同一 WU 核对，不在下游补猜。
- **PR197-R1/F6 中／deferred-with-owner（既有残余）**：MiMo F3 指 `SourceIntegrityRevisionConflictError` 在 public 侧落 EXECUTION、`reason_code=None`，包括 post-repair `SelectedSourceRepairRequired` 变换后的路径。代码与测试证明行为确实如此；但 `issue-198-download-failure-projection-plan-20260928.md:92,126`、S1 adjudication 与 final closeout 均已明确把它留给 `fins-download-storage-sibling-errors`，S1 测试故意锁现状。该行为不能宣称正确，但也不能作为 #198 新回归或已闭环路径被遗漏。由既有 WU 的 goal confirmation 区分损坏需修复与并发冲突可重试两种事实，决定 reason/hint 与 telemetry；在该 WU 中更新当前残余断言。当前 PR 仍有此未修风险。
- **PR197-R1/F7 低／accepted／待独立 goal**：MiMo F4 指 `cn_pipeline.py` import workflow 私有 `_INTEGRITY_FAILED_STATUS`，而 `ok/cancelled` 在 adapter 本地定义；总控实读生产导入与校验。当前行为正确、pyright 可捕获简单重命名，但三值构成跨 workflow→adapter 结果协议，分散 owner 易致未来词表漂移。独立 WU `fins-download-status-contract-owner` 在 `cn_download_models` 或直接协议 owner 收敛封闭类型/常量和测试；不为了旧路径加兼容 re-export。优先级低于 F5 与 F2。
- **PR197-R1/F4 低／accepted／deferred-with-owner 正式化**：两路同源发现 HK 每候选对既有来源 meta 做 O(S·D) 重复读盘/持锁。维持前节直接证据与 `fins-hk-download-identity-batch-read` WU；MiMo 的单轮 memoize 建议若无 publication 一致性证明不能直接实施。由 storage owner 提供批量同一快照，下载身份 owner 使用；不在本轮代码审查中修改产品。
- **PR197-R1/F3 低／accepted／待修正式化**：ds-flash 独立发现的四个新增分析脚本私有绝对路径，MiMo 部分覆盖 utils 未能反证。总控已直接读参数入口和 repo PUBLIC 状态，维持现行树参数化修复。普通后续提交不会抹去线上历史，历史清除需另作明确裁决；不擅自强推。
- ds-flash F1 生成脚本 PATH 问题维持 **rejected-with-reason**：base 原有 `python` 命令，错误环境 Core 2.71.0 低于 PR 2.96.0，README §1.1 和 AGENTS.md 要求激活项目 venv；激活后单例及 22 文件组合通过。MiMo也将此列非 PR 回归 Open Question。macOS Intel 支持范围在 `docs/plans/docling-2-127-upgrade.md` 有明确决定且 README 同步；`--overwrite` 刷新路径 README 已说明；6-K 某标题漏判在 base 已存在且无真实受影响样本，本轮不立 PR 修复项。

## 本轮门禁与交接结论

- 用户本轮请求是“先做一轮 PR review，然后更新交接 prompt”；没有授权本轮顺延执行这些新 WU 的 Gateflow 实施。Sol 为后续 plan/implement/fix 角色，本轮未派 Sol，未改生产代码/测试。所有 accepted/deferred 修复已同时写进本文件与主队列，避免上下文压缩丢失。
- 完整 diff 审查结论为 **fail / 需修复与独立 goal**。F2/F3 为直接待修；F5 为中等语义缺陷先做 goal；F7 低优先 owner；F4/F6 已归独立 WU。修复后两路按同一新 head 复审；最终手工 merge 前再读 live PR head、冲突与测试，不能沿用本轮 `MERGEABLE`。
- 总控验证为 22 个变更 Python test 文件激活 venv 后 **2128 passed/2 skipped/3 warnings**，当前 venv 模块 pyright 0，系统 1.1.408 在 F2 为 1 error。`git diff --check` 的 `final-pyright.log` 单处 EOF 空行未清理；无 CI checks、全仓 pytest、coverage 或远端网络验证。审查范围与风险详见总控 review artifact。
