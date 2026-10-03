# UM-O03-F01：workspace root 目标类型 goal confirmation

- 日期：2026-09-28；work unit：`UM-O03-F01`；Gate：`goal confirmation`。
- 隔离工作区：`/private/tmp/dayu-upload-o03`，分支 `codex/upload-material-o03`，基线 `8d8d494f`，preflight 时 `git status --short` 为空。最终代码须汇入用户指定的 PR #197 分支 `codex/upload-material-oracle`，本 worktree 不开新 PR，用户手工 merge。
- 用户接受的裁决来源：主工作区 `/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 的 `UM-O03-F01`；该文件含未提交的冻结 oracle 裁决，不能把冻结 CLI 观察当作当前 HEAD 的通过证据。

## 动机与直接代码证据

动机成立。`dayu/cli/commands/fins.py:_resolve_workspace_root` 只拒绝空字符串，再用 `Path.expanduser().resolve(strict=False)` 返回路径；`_run_fins_direct_command_async` 将结果交给 `FINS_DIRECT_SERVICE_FACTORY`，未在 CLI 路径 owner 边界分类“目标是普通文件”。冻结 UM-018 因而以通用 `storage_io`/exit 1 收口，无法指示用户修正 `--base`。`dayu/cli/agent_entrypoint.py:resolve_workspace_root` 也是 CLI 共享解析入口，当前同样只检查文本；`init` 有自己更严格的 no-follow/symlink 生命周期校验，不能机械复用其规则。问题根因在请求路径目标类型与 CLI 错误语义的缺失，不在 material 仓储。

## 目标与成功信号

- CLI workspace root 的共用解析/校验 owner 对**已存在且解析目标不是普通目录**的 `--base` 给出明确、可操作、路径安全的用法错误；至少覆盖普通文件，不把它映射为存储 I/O 故障。适用于使用该公共路径契约的 CLI 入口，Fins direct `upload_material` 是本次验收入口。
- 非法目标在装配 Service、读取上传文件、调用 converter 或发布任何 material 前拒绝。用户原有普通文件内容和路径保持不变；没有业务发布或额外 workspace 目录。按 CLI usage 错误语义验证退出码，不固化冻结 `storage_io` 行为。
- 保留现有正常路径语义：重复 `--base` 最后值生效、相对路径/默认 cwd、空格/Unicode、指向目录的 symlink 以及尚不存在路径的当前装配规则。对 symlink 的最终目标类型作判断，不把正常目录 symlink 当非法文件。`init` 自身明确拒绝 symlink 的生命周期合同保持不变。
- 测试在 owner 边界固定目标类型行为；隔离真实 CLI 用普通文件 `--base` 复验错误、文件不变和无发布，并回归上述正常路径。修改代码后按 AGENTS.md 跑受影响测试、pyright 与 README 职责检查。

## 边界与非目标

- 先由 plan 判定唯一 owner 以及 Fins 私有 `_resolve_workspace_root` 与 `agent_entrypoint.resolve_workspace_root` 的收敛方式；不得只在 `upload_material` 下游展示层加补丁，也不得通过 `getattr`、字符串解析或仓储异常重分类弥补。
- 不改变财报仓储协议、来源/发布状态、上传材料的业务验证、Docling 转换或文件内容提取。`init` 的 bootstrap、symlink 禁止和原子性流程不纳入本 work unit；其它特殊路径/权限竞争若现有证据不足，须在 plan 标为风险或另行 goal confirmation，不借本例扩大。
- 不为旧 `storage_io` 文案或退出码做兼容。只改 owner 边界、直接消费者和必要测试/文档。

## 开放问题与状态

非 blocking 的设计问题：共享 CLI helper 是否应直接执行目录类型校验，以及 Fins 私有解析函数是否应消除以避免逻辑漂移；由 plan 基于 import 边界和现有调用者决定。不存在需要用户补充的行为裁决。用户已接受 O03 修复方向并要求全部修复进入 PR #197，本 goal 与之同范围，记为 **goal confirmation pass**。下一入口：`plan`，需由 gpt-6-sol 在本隔离 worktree 完成，Kimi/MiMo 两路独立 review 后方可实施。
