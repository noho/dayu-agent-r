# UM-O20-F02：MiMo 第三轮 P0 计划修订记录

- 日期：2026-09-29；工作区 `/private/tmp/dayu-upload-o20-f02`；范围仅为本记录与 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`。
- 基线计划 SHA-256：`b2723237bb528bfb873add47370b8344b7daa814a1e852857b6ccc9df1f043b4`；修订后 SHA-256：`69307018eea754b523cc81fd1055c0e7e427008276a3977edca0267af61bb7c0`。
- 冻结 E01 SHA-256：`f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，修订前后相同；goal、probe、旧 review 与总控 adjudication 未改。
- 依据：`docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md` 的 findings 1–4 与 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 的 O20-PR3-F1～F4。动机成立：原计划 §3 将无法获得 workspace 边界和清单的 Documents runtime 写成独立校验 owner；§5 的两个绝对入口引用未获独立机制证据，证据备份判据不闭合，且 P0-B 的“零出站”措辞强于其验证手段。

## 修订内容

1. **F1**：§1/§3/§5 明确 `XbrlTaxonomyInput(root, zip_name)` 仅为 P0 形态草案。workspace 外、管理员受信输入与 provenance 清单校验所需的唯一 owner、强制点、显式边界输入和可信清单通道尚未闭合；P0 后 S1 implementation plan 必须设计并经双路复审，未闭合则 S1 硬停。Documents runtime 只承担待设计的进程内完整性复验，不能单独声称已能判断 workspace 边界；CLI 参数未冻结。
2. **F2**：§3 分配绝对 `schemaRef` 与绝对 `linkbaseRef` 的 catalog 映射；§5 P0-B 给两者分别设置自包含合成向量，各自先经 Arelle 离线 `--validate --validationExitCode` 合法性检查，再做 Docling Path/Stream 对照并独立记录原始证据。AAPL 相对入口不作为通用证明。
3. **F3**：§5 将可公开证据主档指定为持久主仓下忽略的 `workspace/evidence/upload-material-o20-f02/`，第二份为同仓另一清理目录下忽略的 `output/evidence-backup/upload-material-o20-f02/`。P0 须从临时源迁移并比对源/两份的大小与 SHA-256，遮蔽临时源后仅从第二份再回读；真实重启后抽查留待补证。受限真实 taxonomy/instance 仍由管理员在另一个受控持久归档保存。当前主仓根 `/Users/leo/workspace/dayu-agent-r` 的 `.gitignore:4-5` 经 `git check-ignore -v` 实测命中两处相对路径；目录尚未迁移或回读。
4. **F4**：§5 P0-B 只承诺自包含输入及关闭远程获取的配置级离线；OS 强制零出站规则生效及网络 trace 证据归 P0-C。§4/§6 的三平台 pass/blocked 和有限矩阵口径保持。

## 命令与退出码

以下按本轮实际 shell 调用顺序记录；复合命令的 exit 是整次 shell 调用的退出码，未对未单独采集的内部命令虚构 exit。计划 `apply_patch` 两次及本记录新建一次均成功；它们不是 shell 命令，没有进程 exit 码。

| # | 命令或调用内容 | exit / 结果 |
| --- | --- | --- |
| 1 | `rg -n 'upload-material-o20\|O20\|F02\|dayu-agent-r' /Users/leo/.codex/memories/MEMORY.md` | 0；仅见旧 upload_material 条目，未作本次事实依据 |
| 2 | `pwd; rg --files -g 'AGENTS.md' -g '*goal*' -g '*E01*' -g '*adjudication*' -g 'upload-material-o20-xbrl-runtime-plan-20260929.md' -g 'plan-review-o20-f02-rereview3-mimo-20260929.md' -g '.gitignore' \| sort` | 0 |
| 3 | `cat /private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.TiD0uQ/canary.txt` | 0；逐字内容 `gpt-6-sol-088f915d` |
| 4 | `git status --short; git rev-parse --show-toplevel; shasum -a 256 docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` | 0；基线计划 SHA 匹配 |
| 5 | `cat AGENTS.md` | 0 |
| 6 | `cat docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md; shasum -a 256 docs/gateflow/upload-material-o20-e01-evidence-20260929.md; cat docs/gateflow/upload-material-o20-e01-evidence-20260929.md` | 0；E01 digest 匹配 |
| 7 | `cat docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md; cat docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` | 0 |
| 8 | `cat docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` | 0 |
| 9 | `cat .gitignore; git -C /Users/leo/workspace/dayu-agent-r rev-parse --show-toplevel; git -C /Users/leo/workspace/dayu-agent-r check-ignore -v workspace/evidence/upload-material-o20-f02/ output/evidence-backup/upload-material-o20-f02/` | 0；主仓两路径分别命中 `.gitignore:4` 和 `:5` |
| 10 | `cat docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md` | 0 |
| 11 | `cat docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` | 0 |
| 12 | `nl -ba docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md \| sed -n '1,145p'` | 0 |
| 13 | `cat /Users/leo/workspace/dayu-agent-r/.gitignore; git -C /Users/leo/workspace/dayu-agent-r status --short -- workspace/evidence/upload-material-o20-f02 output/evidence-backup/upload-material-o20-f02; ls -ld /Users/leo/workspace/dayu-agent-r /Users/leo/workspace/dayu-agent-r/workspace /Users/leo/workspace/dayu-agent-r/output` | **1**；原样错误：`ls: /Users/leo/workspace/dayu-agent-r/output: No such file or directory`。这是尚未执行 P0 创建第二份目录的当前状态；真实忽略规则已独立核实，故不触发计划修订停止条件 |
| 14 | `rg -n -C 5 'rereview3\|第三轮\|F1\|F2\|F3\|F4\|P0\|workspace\|provenance' docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` | 0 |
| 15 | `sed -n '112,205p' docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md` | 0 |
| 16 | `git -C /Users/leo/workspace/dayu-agent-r check-ignore -v workspace/evidence/upload-material-o20-f02/ output/evidence-backup/upload-material-o20-f02/; git -C /Users/leo/workspace/dayu-agent-r rev-parse --git-common-dir; git -C /Users/leo/workspace/dayu-agent-r rev-parse --is-inside-work-tree; test -d /Users/leo/workspace/dayu-agent-r/output; printf 'output_dir_exists=%s\n' "$?"` | 0；末尾明确打印 `output_dir_exists=1`，不误报目录已存在 |
| 17 | ``rg -n '未闭合的形态草案\|绝对 `schemaRef`\|S1 硬停' docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`` | 0；第一轮文字修订已落盘 |
| 18 | `sed -n '9,59p' docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` | 0；全文相关段落人工复核 |
| 19 | `python3 -c '...'`（只读检查七条必要措辞及尾随空格） | 0；`required_missing=[]; trailing_whitespace_lines=[]` |
| 20 | `shasum -a 256 docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md docs/gateflow/upload-material-o20-e01-evidence-20260929.md; git -C /Users/leo/workspace/dayu-agent-r check-ignore -v workspace/evidence/upload-material-o20-f02/ output/evidence-backup/upload-material-o20-f02/; git status --short` | 0；新计划 SHA、E01 原 digest 与两条忽略规则均匹配 |
| 21 | `sed -n '1,135p' docs/gateflow/upload-material-o20-f02-plan-fix-pr3-20260929.md` | 0；新记录人工复核 |
| 22 | `python3 -c '...'`（只读核对计划/E01 SHA、记录引用的新 SHA 与本记录尾随空格） | 0；`record_has_plan_sha=True; trailing_whitespace_lines=[]` |
| 23 | `git status --short; git -C /Users/leo/workspace/dayu-agent-r check-ignore -v workspace/evidence/upload-material-o20-f02/ output/evidence-backup/upload-material-o20-f02/; shasum -a 256 docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md docs/gateflow/upload-material-o20-e01-evidence-20260929.md docs/gateflow/upload-material-o20-f02-plan-fix-pr3-20260929.md` | 0；状态仅比基线新增本记录，计划/E01 digest 不变 |

## 验证与残余

- 只做文档结构、关键措辞、尾随空格、SHA、主仓忽略规则与工作区状态核验。本 worktree 无 `.venv`，且没有产品代码、测试、依赖或 README 修改；未运行产品测试和 pyright。没有执行 P0 安装、探针、taxonomy 加载、证据迁移/备份/回读、真实重启、外部 issue 操作或 Git 发布。
- P0-A 的完整安装和三平台验证、P0-B 的三个合成引用图与真实财报、P0-C 的 OS 强制隔离与 trace 均未执行，按原计划保持 blocked；主仓两个证据目录的创建、不同清理目录留存与回读也未验证。S1 实施接口仍待 P0 后设计并复审。本文及修订计划均不声明 XBRL 产品支持，也不改变上游 #4437 与 E01 原文。
