# TSM 6-K 调查总控裁决与停报

本报告保留调查阶段的历史停点。用户随后核收限定结论并明确授权D1在同一work unit继续修复；最新进展、修复/审核裁决与交付入口见 [D1控制记录](tsm-6k-rejection-20261023-d1.md)。下文的“尚未修复/无PR”等均指当时状态，不覆盖后续授权和成果。

## 结论与当前停点

候选 `fil_0001046179-26-000728` 当前核实的同版归档按既有规则应拒绝；未证实误拒绝、漏选附件或拒绝原件持久化错误。历史 17 候选、16 跳过、1 拒绝、退出 0，以及公共明细 10 / omitted 7 均与既有契约一致。历史分类 GET 实参未捕获，不能恢复；本报告不声称历史全窗已重放。

另确认 D1 数量 warning 误计，与拒绝本身分离。用户明确“若正确拒绝，交回可复核依据后停止”，故没有据附加诊断问题自行启动产品修复或版本升级。D1 是否并入当前条件修复，还是另开 work unit，交 portfolio-manager 明确裁决。

- current gate / next entry point：`code review`，两路完整审核及 F2 复审已收齐，停在 D1 范围裁决。
- 本记录不是 `draft-PR-pass` 或 `final closeout pass`；不把尚未修复的 D1 标成修复完成。
- 源码仍为 `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`，分支 `investigation/tsm-6k-20261022`。
- 包声明及实际安装分发均为 `0.1.5`。无生产/测试改动，无新增工程 commit、push、PR、安装或 merge。

## 可复核依据

[调查报告](tsm-6k-rejection-20261022-investigation.md) 与 [证据索引](/Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/S1-INDEX.md) 保存完整路径、原件及逐文件 SHA256。

1. SEC ticker map / submissions 绑定 CIK `1046179`、目标 accession、披露日和主文件，未从 accession 前缀反推归档身份。
2. 目录、index-headers 和完整 submission 共同确认只有一个 TYPE=6-K 文档；无 EX-99/XBRL/其它业务附件，primary 无 HTML 补链。
3. 当前原文、当前分类 GET、拒绝 artifact 预取及历史副本同为 59847 字节，SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2`。正文为月末持股等六类事项，不是季度业绩公告。
4. 真实生产提取输入 `max_lines=120`，得到 5 个非空行、4343 字符；分类 `NO_MATCH`；无阳性且无 EX-99/XBRL，预筛返回 `(False, NO_EX99_OR_XBRL, tsm-monthend6kx20261022.htm)`。不存在保留信号被 120 行或 4000 字符窗口截掉的证据。
5. maintenance/source 仓储读回拒绝 artifact / registry 一致，active=[]，原件同 hash；typed terminal 正确计为 rejected。
6. 当前单日真实 CLI、严格离线重放及缓存轮均退出 0。总控另以无观察器的公开 `python -m dayu.cli` 入口交叉验证退出 0、stderr 为空、1 候选/1 拒绝/failed=uncertain=0。

上游只读证据包：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/dayu-tsm-rejection-20261022/upstream-evidence/`。隔离证据：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/tsm-6k-20261022/`。调用方原 base 和运行记录均未修改。

## 完整审核与总控判断

| 审核 | 实际 runtime / 退出 | artifact / 结论 |
| --- | --- | --- |
| mimo-flash 完整审核 | Claude，外层/runtime 0；session `55fbb400-6fbc-4514-9225-4b3cb2574b24` | [完整审核](../reviews/code-review-20261022-235934.md)：支持限定的正确拒绝结论；确认 D1；无拒绝证据交付 blocker |
| ds-flash 首次尝试 | Claude，外层/runtime 1；API 403 | 未形成审核；不计入双路 pass，原始日志保留 |
| ds-flash 完整审核 | 用户明确改用 Codex；外层/runtime 0；session `01a16451-fac5-7640-882c-28831630389a` | [完整审核](../reviews/code-review-20261022-235631.md)：支持限定结论；确认 D1；提出 F2 文档符号错误 |

两路实际独立审核有并行运行区间，未把 DS 的失败尝试冒充审核。完整日志分别为 `controller/review-mimo.jsonl`、`review-ds.jsonl`、`review-ds-codex.jsonl` 及各自 stderr；DS 失败另保存 `review-ds-claude-failure.json`。

总控已读两路完整 artifact、全部 final answer 与真实退出；按具体证据裁决，未以模型一致或退出 0 替代证据。MiMo 未逐行走读 40KB 取证脚本、部分身份/索引 body 未逐字节展开，已如实列为未覆盖；DS 覆盖脚本与完整生产链，总控另核无注入 CLI、原文哈希、输入、仓储及源码不变。该差异不妨碍当前限定判断，不能外推为全仓审核。

| Finding | 总控裁决 | 修复状态 | owner / destination |
| --- | --- | --- | --- |
| D1 / DS F1 / MiMo 1：数量 warning 把 filtered skipped 计为有效落盘 | `accepted`，严重度中（P2） | `未修复` | SEC 确认 disposition / 数量诊断 owner；portfolio-manager 裁决当前单元或后续 work unit |
| DS F2：总控记录引用不存在的 `download_filing_stream` | `accepted` | `已修复`，两路窄复审均已核验 | 总控记录 owner；不改生产代码 |

D1 同源根因为 `warn_insufficient_filings` 按内部 `status in {downloaded, skipped}` 累加，忽略确认行的 rejected 语义。无注入单日运行 active=0、terminal rejected=1，warning 却称“有效落盘数 1”。原历史全窗未触发该 warning，不用它解释历史拒绝。MiMo 评低、DS 评中；总控取中：除误导排障外，同一计数条件可把真实有效 2 + 被拒绝 1 算成 3，使不足警告不触发；不涉及错误收录、丢失或终态误计。

F2 是总控自有治理记录的一处函数名更正，真实函数为 `sec_download_filing_workflow.run_download_single_filing_stream`，定义行 182、调用在 `sec_pipeline.py:1027`、拒绝行在该函数 426 处。更正前版本、单行 diff、当前精确快照和 SHA256 保存在 `controller/review-input-snapshot/`、`F2-document-fix.diff/.json`、`F2-review-input.md`；原完整审核仍适用于未变的业务事实。

F2 双路窄复审：DS [通过](../reviews/code-review-20261023-000253.md)，MiMo [通过](../reviews/code-review-20261023-000633.md)，两者外层/runtime 均实际退出 0。DS session `01a16459-3d80-7ea3-9b14-d8936e08cd0a`，MiMo session `2c38a365-7c60-4179-8219-c8908b60c974`。已读取两份完整 artifact 与 final answer，均确认修复状态为已修复、旧完整审核对未变事实仍有效；不把 F2 pass 当作 D1 已修复。日志为 `controller/F2-review-ds.jsonl` / `F2-review-mimo.jsonl` 及对应 stderr。仅更正引用，不重新进行相同整套验证。

## 验证与版本查询

- 同基线 43 项 6-K 回归通过；103 项发现/诊断回归通过；S1 补充 129 项回归通过。测试组有重叠，不累加为独立测试总量。所有实际命令、stdout/stderr、退出码见 controller 日志和 `S1-COMMANDS.md`。
- 激活 `.venv` 后全量 pyright 为 0 errors / warnings / informations；一次性脚本另以专用配置实际包含 1 文件，pyright 0 错。早期探针失败和被 exclude 排除的检查未作成功证据。
- 最后核对生产代码/测试/pyproject/根 README 无 diff，9 个关键源码哈希与基线 provenance 一致。未修改产品或用户工作流，不触发 README 更新。
- 实际安装位置：`/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages`；模块来自本 checkout。查询命令（在仓库根）：

```bash
.venv/bin/python -E -P -c 'from importlib.metadata import version; print(version("dayu-agent"))'
```

已观察值为 `0.1.5`；未把源码声明或候选 wheel 冒称新安装版本。若获准修 D1，目标包拟升 `0.1.6`，修复、验证、审核及 draft PR 同单元交付；当前没有可 sync 的新工程 commit/包。live 安装和 merge 仍须各自明确授权，安装时按当前 README“从源码安装”执行。

## 风险、未完事项与范围提案

| 项目 | 分类 | owner / destination |
| --- | --- | --- |
| D1 尚未修复，是否纳入当前工程不明 | requiring new issue or explicit user decision | portfolio-manager 裁决；SEC disposition/数量诊断 owner 实施 |
| 历史实际输入、descriptors 与完整初始 base 不可恢复 | requiring new issue or explicit user decision，现有用户确认已接受限定结论，非新阻塞 | 总控；若另需更强历史结论，再派只读取证，当前不冒称恢复 |
| “跳过落盘”措辞对 active / rejected artifact 有歧义 | assigned to later work unit | SEC 工作流诊断 owner；可在 D1 后续范围中评估，非原件丢失 finding |
| 当前结论只覆盖已保存字节和基线规则 | assigned to later work unit | 后续 downloader/规则变更 owner 按新版本重新验证；不保证未来远端内容 |
| 本轮未请求保留月末事项或全部 6-K | 非待决需求，按用户既有非目标排除 | 不新增政策，不要求用户再次确认非目标 |

具体范围选项：

1. 按“正确拒绝后停止”结束本候选调查；D1 另派 work unit，当前不升级包、不创建工程 PR。
2. 明确将 D1 纳入当前条件修复：确认“warning 有效数=0、拒绝数仍=1，真正已完整缓存仍计为有效”，在确认 disposition owner 边界复用唯一投影；不在 CLI/warning 下游对本文件特判，不改变 6-K 保留政策。按既定 gpt-6-sol writer、MiMo/DS 双路审核、0.1.6 和 draft PR 流程推进。

本任务所有派发均已取得真实退出码；在途 Agent / runner / 直接托管子进程为 **0 / 0 / 0**。停报通知通过 tmux-agents 发给 portfolio-manager，结果在发送/捕获后补记。当前等待的只是 D1 范围裁决，不是尚在运行的 Agent。

## 停报通知记录

已重新 discovery / status / capture 确认 `portfolio-manager-v2-0:1.1` 的空输入框后，独立发送以“Dayu上游工程总控”开头的通知，包含结论、证据绝对路径、D1 未完事项、版本/分支、停点及本任务在途数量 0/0/0；未 clear 会话。发送工具退出 0。随后 wait_idle 20 秒超时，不能视为对方完成或授权；capture 确认通知独立提交、未混入用户输入，portfolio-manager 已表示正在核对 D1 是否属于已有条件修复授权。捕获时尚无明确范围裁决，不据此启动修复。
