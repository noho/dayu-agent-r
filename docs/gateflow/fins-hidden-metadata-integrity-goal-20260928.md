# Fins source integrity：安全点号元数据 goal confirmation

- Gate：`goal confirmation`；日期：2026-09-28；work unit：`fins-hidden-metadata-integrity`。
- 隔离工作区：`/private/tmp/dayu-upload-dotfile`，分支 `codex/upload-material-dotfile`，基线 `8d8d494f`。preflight 时工作树为空。闭环代码最终汇入用户指定的 draft PR #197，用户手工 merge。
- 主工作区已有未提交的 storage inspector、测试与 README 候选改动；它们是待审查输入，不是本 work unit 已通过的实现。issue #198 的失败投影与本 work unit 分开裁决、提交。

## 动机与直接证据

动机成立，但范围仅限 source integrity 的业务命名空间判定。2026-09-25 的隔离下载复验记录显示，已发布 Q1 filing 目录残留空 `.claude/.cc-writes`，`_validate_physical_structure` 将其判为 `unsafe_filesystem_entry`，进而使 whole-kind preflight 抛 `UNSAFE_PUBLICATION`；清除该环境元数据后 7/7 来源恢复 complete（`docs/gateflow/cninfo-empty-announcement-parse-final-closeout-20260925.md`）。当前 HEAD 的 `_inspect_source_kind_unguarded` 还会将 source 根下未声明的点号普通文件或目录视为不可归属项。代码直接证据是两处枚举循环分别要求 root 条目为带 identity 的目录、document 条目为已声明的普通文件。安全工具元数据不代表来源业务内容，因而有必要在 storage owner 内统一界定其忽略条件；不能在 CLI 或 download 投影层把完整性失败改写成成功。

## 目标、成功信号与 owner

- `dayu.fins.storage` 的 source integrity inspector 在 source kind 根和 source 文档目录，忽略**未声明**的安全点号元数据：点号普通文件、以及递归只包含普通文件/目录的点号目录。已声明业务文件即使以点号开头，也必须继续按 manifest、内容和指纹校验。
- 点号命名不能掩盖 symlink、特殊文件或不可读取/不稳定的物理条目。直接或嵌套隐藏链接与特殊文件仍失败关闭；失败事实由 storage owner 产生，不由消费者猜测。
- exact、whole、snapshot、batch publication 与 commit 使用同一 inspector 判定。隔离真实仓储与 owner 测试确认安全元数据不改变已发布来源的 complete、revision、快照和提交；非法条目仍产生当前封闭完整性失败。
- 修改后按项目约束运行受影响测试、pyright，检查 `dayu/fins/README.md`、`tests/README.md` 和根 `README.md` 的读者职责与实际行为。

## 非目标、边界与开放问题

不改变 manifest/schema、来源业务文件名称规则、文件内容抽取、下载 provider、#198 的 public failure/CLI 文案，也不全局忽略所有点号路径。source 根的 manifest/control 文件仍按原规则处理；文件系统 TOCTOU 与其它非点号异物的分类不借本例扩大。候选代码是否充分验证隐藏树中的特殊文件、已声明点号文件和各调用路径，由 plan/review 基于直接代码证据裁决。若正确 owner 或忽略条件无法在 storage inspector 唯一表达，停止实施并重新确认目标。

用户已要求现有点号元数据候选修复闭环后同其它修复进入 PR #197；本目标沿该范围，记为 **goal confirmation pass**。下一 gate：由 gpt-6-sol 生成最小 plan，Kimi/MiMo 双路独立 review 后才实施。
