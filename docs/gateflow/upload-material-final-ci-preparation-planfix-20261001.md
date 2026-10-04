RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-4055dd46

# CI-PREP-A1 最终 CI 预备 proposal 文档修复交付

label：`pr197-final-ci-planfix-sol-20261001-01`。实际运行模型的独立 metadata 未提供，故记为 unknown；不从 provider 名、角色或 canary 推断。canary 来自本轮指定文件的真实工具读取，逐字内容见证据 `02-canary.stdout`。本报告只交 root 审核修复候选，不是 planreview 通过、accepted final plan、CI pass 或最终 PR closeout。

## 身份与权限边界

workspace `/Users/leo/workspace/dayu-agent-r`；唯一 branch `codex/upload-material-oracle`。首次 HEAD `4f0b5b046e194d361fb0ccc798bfd26a8be4db7e`；修复时及末核 HEAD `20f7a5ac48fa87aca212ab32ff0968f406888dcb`；main 始终为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。HEAD 变化经只读 ancestry 和 name-status 验证，是现有 root 文档 checkpoint，四个路径均属 docs，未含本 proposal；其中 receipt 被纳入 commit，但其工作树冻结字节仍匹配，不能把 commit 路径变更误判为本轮输入字节漂移。路径证据 `21-checkpoint-paths.stdout`，身份见 `03/04/19/20/29/30` 对应证据。

本 Agent 没有修改 Git、stage/commit/push/PR/main、branch/worktree、产品/test/README/config/正式 registry/裁决/旧报告/root controller；没有网络、真实 CLI 服务、Docling/OCR、private input 或子 Agent。PR197 OPEN/draft 是任务输入，本轮禁止网络，未冒称 live PR 独立核验。没有读取并行 reviewer 新产出；git status 仅做路径级记录。

## 动机、根因与语义 owner

动机成立，但仅属 root 已登记的低级别计划映射错误，不能据此扩大产品修复或重审 F3。

- root receipt L53 的 `CI-PREP-A1` 明确指出两个 scope 混绑；本轮读取冻结 receipt，未修改该登记。
- 冻结 F3 goal L7、L11–18：开发分析脚本显式样本输入，四个原脚本及必要 utils helper；root receipt 确认 accepted slice 为五个分析 utils。F3 code/aggregate accepted 事实保持。
- 独立读取冻结源码 `dayu/cli/workspace_root.py` L16–46：`resolve_workspace_root` 解析 workspace 文本与路径，拒绝空值/现存非目录。UM-O03 正式裁决 L62–68 的 owner 与之同源：公共 workspace 路径解析/校验边界。
- 根因在 proposal 的依赖映射 owner：O03 行写 `O03-F01/F3`，§6 写 `O03/F3 workspace与共享CLI入口`，把分析输入路径修复和生产 workspace 解析并列。正确修复是纠正文档来源绑定，无需改产品、F3 名称或新造 WU。

证据：`10-root-receipt`、`11-f3-goal`、`12-workspace-owner`、`14-o03-adjudication` 的分流文件；大读取显示窗口截断，完整 stdout 保留，关键目标又以 `15/16/17` 独立读取。

## 最小变化与前后证据

唯一既有文件：`docs/gateflow/upload-material-final-ci-preparation-plan-20261001.md`；两行变化，行数不变。

| 位置 | 修复前关键绑定 | 修复后关键绑定 |
|---|---|---|
| L58 O03 表行 | `O03-F01/F3 及最终路径 owner` | `O03-F01，owner=dayu.cli.workspace_root.resolve_workspace_root`，明确 F3 分析 utils 显式输入不属此依赖 |
| L155 §6 | `O03/F3 workspace与共享CLI入口`；`F3 accepted` | O03 绑定真实 workspace owner；F3 五个分析 utils 显式输入独立，保留 `code/aggregate accepted` |

O03 predicate 与全部输入场景字节未改：fresh/已有目录、默认 cwd、相对/绝对、别名、重复 base、空格/Unicode、CI 内 symlink、普通文件、链接环；§6 命令列表及全部回归信号未改：upload_material、upload_filing、download、process/process_filing/process_material、upload_filings_from 输出路径按 final owner。未缩 CI 范围，也未顺带机械改历史状态窗口或删除待完成 CI 场景。原 proposal 的旧 canary/历史 HEAD 保留，仅代表原交付窗口。

完整原件/current diff：`24-original-current-diff.stdout`；修复前后关键行：`15-proposal-targets.stdout`、`27-key-lines-after.stdout`。`28-scope-freeze-after.stdout` 逐件列出 45 项 expected/current/original SHA，断言 changedonefile 与 changed_lines=[58,155]。

## 验证与非零解释

每个正式命令以独立新 prefix 保存 `.command.json` / `.stdout` / `.stderr` / `.innerexit`；失败证据保留，没有覆盖。启动只读发现随后以新 prefix 复读保全。验证依据内层 exit，不把包装 exit 当验证结果。

| 验证 | 结果 |
|---|---|
| 初始冻结 45 current + 45 originals，freeze digest | prefix06，innerexit0，全部匹配 |
| 目标报告写前不存在 | prefix07，innerexit0；创建时再次以 exclusive write 校验 |
| F3 goal、workspace owner、正式 O03 裁决与 root receipt | prefix10–14/17，innerexit0 |
| checkpoint ancestry、路径、branch/main、冻结字节再次核验 | prefix19–23，innerexit0；仅文档 checkpoint，45 对仍匹配 |
| 实际原件/current diff | prefix24，innerexit1 是存在两处 diff 的正常返回；不是验证失败 |
| 原件/current `--no-index --check` | prefix25，innerexit1，stdout/stderr 均空，无 whitespace 诊断；该模式有差异时返回1 |
| worktree `git diff --check -- proposal` | prefix26，innerexit0，stdout/stderr 空 |
| 新增报告 `--no-index --check` | prefix34及末次prefix37，innerexit1为新增文件差异，stdout/stderr空，无whitespace诊断 |
| 精确 scope/末次冻结 | prefix28，innerexit0；44/44 readonly current 与45/45 originals未变，freeze未变，只有允许 proposal 改两行 |
| pytest / pyright / coverage | N/A：文档-only，无代码或新持久 Python 脚本，按本轮协议未运行；不声称0files类型通过 |
| README | N/A：没有代码、用户工作流、入口或架构行为变化，未命中更新触发 |
| 真实 CLI CI / oracle/scenarios/readiness | not-run / 未实施；属于后续 approved slice |

逐项异常：

1. prefix18 innerexit1：写入前要求 HEAD 仍等于初始 SHA 的断言遇 root 文档 checkpoint，未执行任何 proposal 写入。首次判断过严；按用户明确豁免只读核 ancestry、docs 路径及全部冻结字节后，以新 prefix23 成功完成。原失败 stdout/stderr/exit 完整保留。
2. prefix24/25 innerexit1：均是 no-index 检测差异的正常返回。prefix25 的外层包装错误预期0，断言停止后续命令；不是 whitespace 失败。随后以新 prefix26 完成实际 worktree diffcheck，prefix28 完成范围与字节核验，不伪写 prefix25 成0。
3. prefix34/37新增报告的no-index diffcheck同样innerexit1、双流空，是新增文件差异的正常返回，不是whitespace失败。除上述明确解释的非零外，其余已登记命令内层均0；初次大输出只是 UI 显示截断，完整分流文件未截断，关键段已重新读取。没有 CI 失败可报告，因为本轮没有执行 CI。

## 输入与产物 SHA-256

以下路径为项目相对路径，证据均在 `workspace/tmp/pr197-final-ci-planfix-sol-20261001-01/`。

| 对象 | SHA-256 |
|---|---|
| freeze.json | `16231c86c139f46f4f8513535b7a252b77f5f96a984cb228793e2eb5a109cf6d` |
| 原 proposal / originals copy | `72c0205a1c2b9737c9cf235154d3dbc166cc0de776ea20760fbdd57db76dbd71` |
| 修复候选 proposal | `74f1423fe8c4f09475cfb723e1388ce7f4021b4bb7c26a752646dc8bdadb2b7a` |
| AGENTS.md | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| F3 goal | `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935` |
| workspace_root.py | `b78ceecb7aae4ab28b6ae78998f6b1c83df7f34d9259fa1fe1495339084790af` |
| root receipt | `a6feda20ebd41aea323d97d069840d1dd4e96b6ed049bba4bad695d03f88c67a` |
| UM-O01–06 正式裁决 | `b7b825f334b63f6afeabd95d520d868479222ffe25b9147404927fbc47f3a810` |

全部45项输入的首末/current/original SHA 见 prefix06 与 prefix28；后续交付末核仍逐件验证。报告本身与所有证据/原件的 hash 见新增 `delivery-manifest-final.json`（先前 `delivery-manifest.json` 保留为报告补充前的历史快照），该 manifest 不纳入自身避免自引用。授权写集合：仅修改上述 proposal、仅新增本报告、仅在本轮独占目录新增证据；changedonefile指45冻结既有输入中唯一变化，不把新增报告/证据或 root checkpoint混入。

## 残余分类、owner 与 destination

| 分类 | owner / destination | 当前边界 |
|---|---|---|
| covered by later approved slice | root / 同版 MiMo/Kimi 独立双路审查及裁决 | 本文仅修复候选；双审/root仍待，不自判 final plan accepted，不推进 gate |
| covered by later approved slice | root最终CI收口 / 完整mandatory matrix、来源hash、finalSHA、真实CLI、正式oracle/scenarios/readiness | 后续完成全部 approved 修复再重建；不以160上限或mock替代，不重开36语义裁决 |
| covered by later approved slice | F6独立冻结368队列 / 同版aggregate审查与root | 本任务无输入写重叠，未读取并行reviewer产物，未宣告其完成 |
| requiring explicit user decision | 用户业务选择/F5既有队列 / mixed known/unknown Q1 | 具体选择仍待用户，不代选 |
| covered by later approved slice | root corpus/Documents runtime / 真实市场与XBRL候选来源、依赖taxonomy/OS冻结 | 来源仍未冻结，不能伪造成功或把旧候选当新run正样本 |
| evidence limitation | root证据lineage / 新run完整重建 | 旧Raw用户已删除；不恢复虚构旧字节，31裁决/36语义保持 |
| covered by later approved slice | root PR197 / 最终同版review与PR closeout | accepted F3 code/aggregate不等于所有PR收口完成 |

本轮文档候选修复完成，停止并交 root；没有将低级别计划纠正扩成产品任务，没有接受最终矩阵或执行 CI。
