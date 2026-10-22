# TSM 6-K 拒绝调查与条件修复

## 当前状态

- 当前工程进展及最新gate以 [D1控制记录](tsm-6k-rejection-20261023-d1.md) 为准；调查限定结论已核收，用户明确将D1纳入同一work unit，已完成修复/验证及双路完整审核、必要复审，推进同一draft PR。
- 分支：`investigation/tsm-6k-20261022`。
- 基线：`26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`，包版本 `0.1.5`。
- Preflight：原分支 main、工作区干净；用户已明确授权新工作分支，已创建。
- 本单元调查/修复/审核Agent与runner均已实际退出；在途 Agent / runner / 直接托管子进程：0 / 0 / 0（提交前时点）。

## 目标确认提案

目标：以候选 `fil_0001046179-26-000728` 的远端原文、附件集合和实际预筛输入为直接证据，判断普通增量拒绝是否符合既有规则，以及持久化和终态诊断是否如实。只修复已证实的既有能力缺陷。

动机：退出 0、拒绝 1 既不能证明系统错误，也不能证明拒绝正确。拒绝副本内容是月末持股、质押、资产、资本拨款、债券、注销事项披露，尚无证据证明它应按季度业绩保留。调查成立；工程修复尚未成立。

成功信号：可复核地绑定候选身份、远端版本、完整附件发现、实际输入及规则判定；若正确拒绝，交回依据后停止；若证实缺陷，完成 owner 边界最小修复、回归/pyright、双路独立审核和总控裁决、包小版本升级及同一 draft PR 交付。

边界：证据包只读，历史 base 仅用于定位；复现使用本仓库隔离调查目录。不得修改调用方原件/运行记录，不扩大 6-K 保留政策，不给全部 6-K 放行，不引入兼容层或下游补偿。live 安装等待明确 sync to live，merge 另需授权。

条件路由：确认后按 sub-agents 派 gpt-6-sol 做调查计划及必要实现/修复；mimo-flash、ds-flash 同时独立审核最终证据/组合改动；总控裁决。涉及重大契约/架构/状态语义决策时另执行适用 planreview。

## 直接证据与所有权

- 只读证据：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/dayu-tsm-rejection-20261022/upstream-evidence/`。
- 13 个 manifest 条目的大小和 SHA256 均已逐项核验一致；原文 59847 字节，SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2`。
- 原始 argv 为公开 CLI 普通增量；未传 forms/overwrite/rebuild。索引 URL 目前仍只是未经验证的构造线索。
- `dayu/fins/pipelines/sec_6k_rules.py` 是 6-K 分类语义 owner：候选收集、头部提取、分类与阳性选择。
- `dayu/fins/pipelines/sec_filing_collection.py:classify_6k_remote_candidates` 逐候选下载字节，调用头部提取与同一分类真源。
- `dayu/fins/pipelines/sec_pipeline.py:_precheck_6k_filter` 先接受 XBRL；否则分类候选，接受阳性；无阳性且无 EX-99 时返回 `NO_EX99_OR_XBRL`。调用参数 `max_lines=120`。
- `dayu/fins/README.md` 记录既有季度业绩强信号，扫描上限和预告/经营更新排除规则保持不变。
- 副本可读正文披露 2026 年 9 月持股等六类月末事项，不含链接。此事实不等同已验证远端同版或附件完整性。

## 未决项与风险

- 尚未核实远端归档 CIK、完整附件集合及远端同版绑定；实际历史预筛输入未留在现有包内。分类：requiring new issue or explicit user decision；owner：总控；destination：确认后的调查，证据不足不得定性误拒绝或正确拒绝。
- 新保留政策不在授权范围。若出现政策缺口，分类：requiring new issue or explicit user decision；owner：portfolio-manager；destination：单独裁决。
- 本阶段未改生产代码、未运行复现/测试、未升级版本、未创建 PR、未安装 live。

## 通知记录

- 已向 `portfolio-manager-v2-0:1.1` 发送目标确认通知并执行 wait_idle / capture；未收到确认，不把 idle 当作完成。
- pane title 为 portfolio-manager、current command 为 node；capture 显示 Codex 界面。未执行 clear。
- 发送时与用户正在编辑的 G0 指令混入同一输入，属于总控操作失误。随后 capture 显示用户仍在输入，因此停止进一步发送，避免再次干扰。以本文件的独立目标提案为确认依据；混入文本不视为用户授权。
- 停点仍为 goal confirmation；本任务在途 Agent / runner / 子进程 0 / 0 / 0。
- 用户要求重发后，重新 discovery / status / capture，确认目标输入框为空，再发送完整独立通知。capture 已确认通知独立提交，未混入用户文字；portfolio-manager 表示正在核对目标记录，尚待明确确认回传。已执行 wait_idle / capture，不把对方 working 状态视为确认完成。

## 授权更新

用户已明确核对本文件并确认目标、边界、成功信号、分支与基线，授权进入 plan 并按既定模型路由完成调查和条件修复。历史实际输入无法还原时必须标明限制，当前重建不得冒称历史捕获；新保留政策另行报裁决；live 安装和 merge 仍等待明确授权。

## 基线验证（总控）

被验证代码：基线 commit，无生产代码修改。运行目录为本仓库；日志保存于 `/Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/controller/`。

- `source .venv/bin/activate` 后运行 `pytest -q tests/fins/test_sec_pipeline_download.py -k '6k'`；退出 0，43 passed / 115 deselected，1.70 秒。stdout / stderr / 退出码：`baseline-6k-tests.stdout`、`baseline-6k-tests.stderr`、`baseline-6k-tests.exit`。仅有现存 edgartools 弃用提示。
- `source .venv/bin/activate` 后运行 `pyright`；退出 0，0 errors / 0 warnings / 0 informations。对应 `baseline-pyright.stdout`、`baseline-pyright.stderr`、`baseline-pyright.exit`。工具另提示新版本可用，未升级依赖。
- 适用性：支持基线已有 6-K owner/预筛/拒绝持久化与公开结果投影断言，以及全仓现有类型检查；不证明该候选的远端附件完整性或历史实际预筛输入。
- 补充运行 `pytest -q tests/fins/test_sec_downloader.py tests/fins/test_download_failure_diagnostics.py --basetemp=workspace/tmp/tsm-6k-20261022/controller/pytest-base -o cache_dir=workspace/tmp/tsm-6k-20261022/controller/pytest-cache`；退出 0，103 passed，7.19 秒。日志 `discovery-diagnostics-tests.stdout/.stderr/.exit`；覆盖发现/类型索引/补链及完整失败与有界摘要 owner 契约。仅有相同 edgartools 弃用提示。
- 查询安装分发 metadata 观察为 `0.1.5`，位置 `/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages`，实际导入模块为本 checkout 的 `dayu/__init__.py`。查询方法与本轮关键源码哈希记录于 `controller/provenance.json`，没有安装动作。

## Plan 总控核对

计划：`docs/gateflow/tsm-6k-rejection-20261022-plan.md`。gpt-6-sol runner 外层 / runtime 均退出 0；session `01a1642e-a910-7e23-982c-43f5ba89520e`；完整日志 `/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/agent-run.B7SxDxu7/output.jsonl`，stderr 为同目录 `stderr.log`。两个原生命令失败为走读中查询退出，计划交付无阻塞；不以 runner 0 代替验收。

总控决定：计划通过，以下收敛为 binding 实施修正：

- 计划所称“本轮用户收窄为只产出计划”仅指总控给计划 Agent 的子任务，不代表用户缩减整体授权。
- 保留一个调查 slice 和全部关键证据断言；不新增通用工具或多子命令接口。只在 `workspace/tmp/` 写本次一次性脚本与隔离输出，脚本实际运行后须单独 pyright 检查；原建议的 utils 工具不是交付要求。
- 远端 capture 先做身份/原索引/候选直接核查；成功后按必要程度做真实公开 CLI、当前输入透明观察、仓储读回及严格离线重放。不为复现历史 17/16/1 复制调用方 active 缓存或制造历史初态。
- 用户补充 SEC 身份在 `~/.zshrc`；总控通过 `zsh -ic` 验证 `SEC_USER_AGENT_CONFIGURED`。实施可加载现有配置，不输出身份值、不改 `.zshrc`。
- 已有 43 项 6-K 测试与全量 pyright 的基线证据可复用；依实际调查辅助脚本/实质变动补验证，不机械重复相同检查。
- 不改变公共契约、架构、schema 或状态机，独立 planreview 不适用。条件修复若出现重要决策再评估；范围内修复继续推进，新增保留政策单独裁决。

无 blocking open question 阻止调查。历史输入、远端完整性与同版、单日初态差异的证据限制按计划记录；它们是 S1 待解决/明确的限制，尚不等于需要用户裁决。下一入口为 S1 调查实施，未成立的工程修复不提前实施。

## 总控追加：无观察器的真实 CLI 验证

原因：S1 首次捕获已得到正确预筛/仓储/terminal，但其观察器在关闭注入 HTTP 客户端时抛出 RuntimeError，CLI 实际退出 1，不能将 terminal.exit_code=0 冒充命令退出 0。该初次尝试保留，不覆盖。为区分观察器影响与生产行为，总控独立运行无注入、无 monkeypatch 的公开模块入口：

```bash
zsh -ic 'source .venv/bin/activate; export TMPDIR=/Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/controller/clean-cli/tmp; python -m dayu.cli --base /Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/controller/clean-cli/base --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/controller/clean-cli/dayu.log download --ticker TSM --start 2026-10-22 --end 2026-10-22'
```

本次无 forms/overwrite/rebuild；仅收窄单日、全新隔离 base，未复制历史缓存，不能称作原 17 候选完整重放。实际 shell/CLI 退出 0，stderr 为空；日志记录同候选 `NO_EX99_OR_XBRL`，1 候选、1 rejected、failed/uncertain 均 0。stdout/stderr/exit-code.txt/dayu.log 与提取的 terminal.json 全部保存于 `workspace/tmp/tsm-6k-20261022/controller/clean-cli/`。代码仍为基线，未安装/修改产品。原命令的 stdout/stderr 重定向及退出码采集均已实际执行，证据文件保留实际输出。

仓储经 `FsFilingMaintenanceRepository` / `FsSourceDocumentRepository` 公开方法读回，记录于同目录 `persistence.json`：active IDs 为空；拒绝原件为 59847 字节，SHA256 与上游副本一致；artifact / registry 均为 `6k_filtered / NO_EX99_OR_XBRL`。

## 调查中发现的附加诊断问题 D1（待完整审核和范围裁决）

同一候选的无注入隔离运行（上节 clean-cli/dayu.log）出现“季报（10-Q/6-K）有效落盘数 1”，而仓储 active IDs 为空、公开终态 rejected=1 / downloaded=0 / skipped=0。直接代码链为：`sec_download_filing_workflow.run_download_single_filing_stream` 在拒绝原件成功保存后产生 `status=skipped, skip_reason=6k_filtered`；`sec_download_diagnostics.warn_insufficient_filings` 第 94–99 行仅按 form 和 `status in {downloaded, skipped}` 计算季报有效数，未使用与 summary 相同的 rejected 语义。因此该数量警告把 filtered skipped 算成有效落盘。公开 typed summary 已正确区分 rejected，这不是误拒绝根因，也不是终态 17/16/1 计数错误。

该错误在新单日隔离状态下直接复现；原历史全窗没有触发该数量警告，不能声称原日志曾输出同一错误。保留范围/分类策略不需要改变。

范围冲突需明确处理：用户一方面要求“诊断如实”和修复已证实既有能力缺陷，另一方面明确“若正确拒绝，交回可复核依据后停止”。若最终审核支持本候选正确拒绝，总控将把 D1 与拒绝结论分开交回，报告具体修复缺口，请 portfolio-manager 裁决 D1 是纳入当前条件修复（并升级 0.1.6、同一 draft PR）还是另一个 work unit；不会用这一附加问题自行扩大保留政策或违背正确拒绝停点。

建议修复方向供裁决：数量诊断复用唯一 filing disposition / rejected 判断真源，排除拒绝行；必要时收敛现有重复语义，不能在 CLI 展示层特判此文件。验证有效数应为 0 且拒绝计数仍为 1，阳性/已有完整缓存仍正确计数。此处是具体提案，不代表已修改或放行。

## S1 实施验收与完整审核入口

- 调查实施 gpt-6-sol runner 外层 / runtime 均退出 0，session `01a16437-56e4-7ac0-ba06-70f2c41cf3ea`，实际用时 1481.20 秒。完整 stdout/stderr 日志位于 `controller/investigator.jsonl` / `investigator.stderr`。
- 已读取完整 final answer、[调查报告](tsm-6k-rejection-20261022-investigation.md)、`S1-INDEX.md` 与权威结果。早期探针失败逐项保留，不能作为成功证据；当前采用 `capture-clean`、`replay-clean`、`cache-clean` 及 `diagnostic-proof-configured`，各实际退出 0。
- 总控核对：远端身份、唯一附件集合、主文档同字节、实际分类输入、预筛、仓储读回、公开终态及历史有界投影相互支持。无观察器 clean-cli 另行交叉验证。生产代码/测试未修改，包仍 0.1.5。
- 验证：S1 补充 129 项回归通过；脚本专用 pyright 实际包含 1 文件，0 errors。复用上述同基线 43 项 6-K、103 项发现/诊断及全量 pyright；这些组有重叠，不累加为独立测试总量。
- 文档决定：只新增调查/治理记录和隔离辅助脚本，无产品能力、入口或测试约定变化，不修改 README。
- D1 为未修复的真实诊断计数问题，保留到审核后做范围裁决；不能拿无代码改动直接标 review pass 或 work unit completed。历史输入无法恢复按用户已授权的限定结论处理，不再重复请求同一前提确认；新的保留政策既未请求也未实施，不把它列为必答问题。
- 独立完整审核使用 Deepreview：mimo-flash、ds-flash 同时复核最终组合及真实生产链。next entry point 保持 code review，等待两路 artifact 和总控逐项裁决。

## 审核收集完成与停报

两路完整审核均实际退出 0，支持当前同版正确拒绝的限定结论并确认 D1。DS 首次 Claude runtime 403 未形成审核；按用户明确要求改用 Codex runtime 后完成，与 MiMo 独立并行，失败尝试保留。

总控自有记录 F2 函数名错误已更正，MiMo/DS 两路窄复审均实际退出 0，确认单行改动定位正确、旧完整审核仍适用。被复审的精确控制器版本保存在 `controller/F2-review-input.md`；本段仅追加 gate/运行状态事实，不改变已审业务判断、规则或证据。

总控完整裁决、审核 artifact、实际版本/查询方式、风险 owner 与范围选项见 [停报裁决](tsm-6k-rejection-20261022-adjudication.md)。D1 为 accepted / 未修复；本轮不宣称所有诊断均已修复，不进入 draft-PR-pass / final-closeout-pass。依用户“正确拒绝后停止”交回证据，并请 portfolio-manager 裁决 D1 纳入当前条件修复还是另开 work unit。未改生产代码/测试、未升版本、未创建工程 commit/PR、未安装或 merge。本任务所有 Agent / runner / 直接托管子进程均已实际退出，在途数量 0 / 0 / 0。

## D1 范围裁决已收到

用户已明确核收限定拒绝结论，并授权D1纳入同一work unit继续最小修复；原正确拒绝停点对过滤调查已满足。后续目标、owner方案核对、0.1.6版本/验证/双路审核及draft PR交付跟踪于 [D1控制记录](tsm-6k-rejection-20261023-d1.md)。历史停报与失败尝试保持原样，不把旧验证当作D1修复通过；live安装与merge仍分别等明确授权。
