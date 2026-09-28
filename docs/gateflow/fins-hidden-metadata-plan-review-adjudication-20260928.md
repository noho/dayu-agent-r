# 安全点号元数据 plan review 总控裁决

- Gate：`plan review -> fix`；work unit：`fins-hidden-metadata-integrity`。
- 两路 artifact：`docs/reviews/plan-review-20260928-224855.md`（Kimi）、`docs/reviews/plan-review-20260928-225630.md`（MiMo）。总控已读取完整 review、goal、plan 与 storage 直接代码证据。两路均确认语义 owner 位于 `_fs_source_integrity.py` 的两个业务枚举点、声明文件优先、安全点号物理树忽略、symlink/特殊文件失败关闭、exact/whole/snapshot/commit 同源。

## 外部派发核验

| label | runtime/provider | setup_status | agent_status | tool_evidence | canary_status | warnings | retry_class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dotfile-plan-sol-20260928-01` | `codex/gpt-6-sol` | ok | completed | yes | match | [] | none |
| `dotfile-planreview-kimi-20260928-01` | `claude/kimi` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 白名单提示 | none |
| `dotfile-planreview-mimo-20260928-01` | `claude/mimo` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 白名单提示 | none |

三路各用显式 `--cwd /private/tmp/dayu-upload-dotfile` 和独立 output/stderr/canary；均退出 0。Sol JSONL 有 `turn.completed`、81 个成功 command execution、无失败事件、空 stderr；Kimi/MiMo JSON 均 `subtype=success`、`is_error=false`、有 `result`，分别 37/41 turns。canary 与 expected 逐字匹配；两路 review 只写各自 artifact。

## Findings、裁决与修复登记

| 来源 | 裁决 | 理由与修复要求 | 状态 |
| --- | --- | --- | --- |
| MiMo F1：隔离 pyright 原命令必现 missing-venv 诊断 | **accepted** | 验证代码树身份是 gate 证据条件。plan 改为在隔离 worktree 建 `.venv` 指向主工作区现成 venv 的本地符号链接，按 AGENTS.md `source .venv/bin/activate`；Python/pytest/CLI 运行显式 `PYTHONPATH` 为本 worktree 并在工作区外 cwd 校验 `dayu.__file__`；pyright 用实测干净的 `--venvpath /Users/leo/workspace/dayu-agent-r` 指向依赖 venv，同时显式分析本 worktree 的 `dayu/ tests/ utils/`，要求无 missing-venv 诊断。若任一身份/诊断无法证明本工作树，才从零建本地锁定依赖 venv；不得以主工作区源树测试替代。 | 未修复 |
| MiMo F2：反向矩阵缺 root×exact 与 document×whole | **accepted** | goal 要求 exact/whole 同源，plan 补四象限 owner 断言：root whole typed `UNSAFE_PUBLICATION`，root exact `UNSAFE + CROSS_SOURCE_INCONSISTENCY`/repair-blocked，document exact `UNSAFE_FILESYSTEM_ENTRY` 且无 revision，document whole 不进 complete inventory且 snapshot/commit 拒绝。覆盖点号 symlink/特殊文件，不能只用非点号 corruption grid 替代。 | 未修复 |
| Kimi R1：超大隐藏树扫描成本 | **deferred-with-owner** | 当前 goal 接受安全点号目录递归检查且不设任意上界；实施/closeout 记录成本风险，不临时加白名单、缓存或大小限制。 | 无当前修复 |
| Kimi R2 / MiMo R1：扫描中的文件系统竞争 | **deferred-with-owner** | goal 非目标明确不提供全局无竞态保证；storage 继续逐条 lstat 和失败关闭，closeout 记录既有 TOCTOU 水位。 | 无当前修复 |
| MiMo R2：rejected/control 区的点号元数据仍会阻塞独立清理路径 | **deferred-with-owner** | 命名空间不属于本 source kind 根/文档目标，另登记 `fins-rejected-control-hidden-metadata` 后续 work unit；当前 README/closeout 不得声称全仓点号元数据免疫。 | 后续 work unit |
| MiMo Q2：覆盖率证据 | **accepted** | plan 将 `>=80%` 的单文件覆盖率目标核对写入实施验证，不以候选测试行数代替；若既有大文件达不到目标，记录差异及未覆盖分支，不为数字写镜像测试。 | 未修复 |

MiMo 关于 material `.rejections` 与 filing control 的不对称：**rejected-with-reason** 作为新修复项；既有 `_is_allowed_filing_control` 仅把 filing 的该名视为控制条目，material 的安全点号目录按普通忽略规则处理，与 goal 和现有 source kind owner 一致。Kimi 建议额外 upload-state 回归：**accepted** 为实施验证范围补充，沿既有测试集合核对消费者，不新开 slice。MiMo 报告误把另一个历史 `plan-review-20260928-193002.md` 当本轮 Kimi 同伴，但声明未读取；本轮实际 Kimi artifact 为 `plan-review-20260928-224855.md`，不影响独立结论。

本轮 **plan review 未通过**，当前 gate `plan review -> fix`。Sol 只修 plan，Kimi/MiMo 双路 re-review 通过后方可实施。主工作区已有候选 storage/test/README hunk 仍未经本 work unit code review；最终汇入 PR #197 前须隔离提交和综合审查。

## 双路 plan re-review：总控终裁与执行规约

Kimi `docs/reviews/plan-review-20260928-232008.md` 为 `pass`；MiMo `docs/reviews/plan-review-20260928-233739.md` 为 `pass-with-risks`。总控完整读取两份 artifact 并抽查 storage owner 的四象限分类与验证命令。两路均独立确认原 accepted F1/F2/Q2 与 upload-state 范围**已修复（计划层）**，未发现设计/owner/scope 阻塞。两路进程退出 0，JSON `subtype=success`、`is_error=false`，canary 逐字匹配；Kimi/MiMo 分别 25/51 turns，stderr 仅精确白名单 `[claude-code:unrecognized_model]` warning；各调用显式 `--cwd /private/tmp/dayu-upload-dotfile`、独立 output/stderr。Sol plan fix JSONL 有一次失败的探索性 pyright 命令事件，按协议 `agent_status=failed`，落盘 plan 只作为候选；两路复审重新实测了正确命令，不倒改派发状态。

MiMo 本轮两个低严重度命令规格 finding 均 **accepted，已修复于本执行规约，实施时验证**：

1. 本 worktree 使用 `.venv` 指向主 venv 的链接时，按 plan 的 `--venvpath /Users/leo/workspace/dayu-agent-r` 命令；若链接身份检查失败而启用真正本地 `.venv` fallback，pyright 必须改用 `--venvpath /private/tmp/dayu-upload-dotfile`（或去掉该 flag 让 worktree config 绑定本地 `.venv`），其余 `--project` 与绝对分析对象不变。实施 artifact 记录实际 venv 身份与命令；不得在本地 fallback 时沿用主 venv 参数。MiMo 已独立验证参数语义与配置路径，当前默认链接方案无需进入 fallback。
2. 单文件覆盖率使用路径式 `--cov=dayu/fins/storage/_fs_source_integrity.py`，在本 worktree 根运行受影响 pytest 并从输出读取该文件百分比，目标至少 80%；禁止用实测会触发 numpy 重复加载错误的模块式 `--cov=dayu.fins.storage._fs_source_integrity` 冒充覆盖率证据。MiMo 已实测路径式可正常收集、基线为 85%。实施 artifact 记录精确命令、百分比与缺行。

MiMo 关于 document 枚举插入点的 open question 作为 code review 核对点：已声明名称优先，非普通项仍归 `UNSAFE_FILESYSTEM_ENTRY`，未声明非点号项原错误原因不得漂移；snapshot/commit 拒绝的类型与消息按现有 owner contract 精确断言。README 限定“未声明、安全的点号元数据”，不得扩大到 rejected/control 区。超大隐藏树成本与 TOCTOU 归本 work unit closeout；rejected/control 区归 `fins-rejected-control-hidden-metadata` 后续 work unit。

**裁决：plan review gate pass。** 当前/下一 gate 为 `accepted plan commit`，随后唯一 S1 `implementation`。上述命令规格已在本裁决 artifact 给出确定执行值，未改动已受审 plan 的业务设计；实施结果与代码仍须双路 code review，不把计划通过当成修复完成。
