# WU-CLI-INIT-01 S4 Scope-Correction Plan Review (DS)

## Metadata

- **Review target**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- **Goal boundary**: `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- **Reviewer**: AgentDS (Claude Code / DeepSeek)
- **Date**: 2026-07-30
- **HEAD baseline**: `cf72af5d`（已确认）
- **Dirty files**: 7 files, 1674 insertions / 117 deletions（与 plan §3 一致）

## Review Scope

按用户指令，本 review 只检查三个维度：

1. Plan 是否仍含并发竞态/TOCTOU/descriptor/ctime/nlink/loader snapshot/新增事务或回滚状态机；
2. 是否遗漏 Goal 明确的 preserve 补缺、overwrite/reset ordinary-file root repair 及最终 tree；
3. 最小 file-vs-directory cleanup 分派是否只是现有机制必要扩展。

不读取另一 reviewer 的产出，不实现、不提交。

## Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|---|---|---|
| A1 | Plan 已排除所有 out-of-scope 并发/TOCTOU/descriptor/ctime/nlink 契约 | §1.1, §5, §11.1 多处明确列出排除项；§11.3 停止条件 #3 阻止实现中重新引入 | 成立 |
| A2 | `config_file_names()` 返回稳定 tuple，足以供 staging 遍历 | `git show HEAD:dayu/runtime/config_loader.py` 第 943 行确认：`def config_file_names() -> tuple[str, ...]` | 成立 |
| A3 | `PathIdentity.mode` 已有 `st_mode`，可区分 regular file vs directory | `git show HEAD:dayu/cli/init_workspace.py` 第 137-155 行确认 `PathIdentity` 含 `mode: int`，由 `os.stat(..., follow_symlinks=False).st_mode` 填充 | 成立 |
| A4 | `_cleanup_private_path` 是 file-vs-directory delete 的唯一 owner | 第 1267 行确认函数签名及 quarantine+rmtree 流程；plan 只在此处扩展 dispatch | 成立 |
| A5 | 现有 `backup_records: list[tuple[ManagedRootSnapshot, Path, PathIdentity]]` 可承载 regular-file backup | `PathIdentity` 是文件类型无关的 identity struct；`os.replace` 对任意文件类型原子操作 | 成立 |
| A6 | S1–S3 已提交内容不会被 revert 破坏 | Plan §7 明确以 HEAD 为逐文件真源，只反转未提交 S4 hunks；每步骤后 `git diff --exit-code HEAD -- <file>` 验证 | 成立 |
| A7 | `ConfigLoader` public contract 不需要修改即可支持补缺 | Plan §3 对 `config_loader.py` 全部撤销；§4.1 补缺逻辑位于 `init_workspace.py`，只读 `config_file_names()` 返回的文件名列表 | 成立 |

## Material Findings

### 1-未修复-低-apply_patch 工具依赖未定义

- **位置**: §7 "使用 apply_patch 安全撤销 partial diff"
- **问题类型**: 不可直接实施
- **当前写法**: Plan 要求 "用小步、逐文件 `apply_patch`"，"通过 `apply_patch` 写入该文件的精确 inverse hunks"
- **反例/失败场景**: `apply_patch` 不是标准 Unix 工具，也不是 Python 标准库。若 implementation agent 的运行环境没有该工具，或工具行为与 plan 假设不符，S4-SC1 的精确撤销流程无法按描述执行。手工 inverse patch 的上下文行号匹配容易因空格/换行差异失败。
- **为什么有问题**: Plan 将 implementation 关键路径绑定到一个未定义的外部工具，违反 "code-generation-ready" 标准——implementation agent 收到此 plan 后需要自行设计替代方案。
- **直接证据**: Plan §7 第 2-3 步反复引用 `apply_patch`，但未在任何位置定义该工具的名称、来源、参数契约或失败行为。
- **影响**: 实施 Agent 可能执行不精确的 revert、引入新 diff，或被迫偏离 plan 改用 `git checkout` 等被 plan 明确禁止的命令。
- **建议改法和验证点**:
  1. 在 plan 中明确 `apply_patch` 指代的具体工具（如 `git apply --reverse`、`patch -R`、或 Codex 内置能力），附最小调用示例；
  2. 或改为 `git show HEAD:<file> > <file>` + Write 整文件覆盖（仅对 full-revert 文件安全），对 selective 文件则接受 `git diff HEAD -- <file> | patch -R -p1` 后验证。
- **修复风险（低）**: 只需在 §7 补充一行工具定义或替换为已知命令。
- **严重程度（低）**: 不影响 plan 的业务逻辑正确性，不影响 scope/ownership/contract 裁决；仅影响 S4-SC1 步骤的可直接执行性。Plan 已内置 `git diff --exit-code` 验证，即使 patch 工具选择不当也会被验证捕获。

### 2-未修复-低-_cleanup_private_path 中 _require_ordinary_directory 的松弛未显式说明

- **位置**: §4.2 第 7 点与 §2 "file-vs-directory backup cleanup" 行
- **问题类型**: 切片过粗
- **当前写法**: Plan 说 "只扩展 `_cleanup_private_path(...)` 的最终删除分派"，"regular file 时对 quarantine 执行 `os.unlink`"
- **反例/失败场景**: 当前 `_cleanup_private_path` 在第 1293 行调用 `_require_ordinary_directory(path, actual_identity, ...)`——该函数在 `stat.S_ISLNK(identity.mode) or not stat.S_ISDIR(identity.mode)` 时抛出 `InitWorkspaceError`。若 implementation agent 只在 quarantine 后增加 `os.unlink` 分支而不处理此前置校验，regular file 会在进入 quarantine 之前就被 `_require_ordinary_directory` 拒绝，永远到不了 `os.unlink` 分支。
- **为什么有问题**: Plan 对 cleanup dispatch 的描述聚焦于最终删除动作，但略去了前置 identity 校验同样需要适配 regular file。这不是 plan 错误——它没有说要新增 `_PrivatePathShape` 或第二套 helper——但缺少一行显式说明会让 implementation agent 可能漏掉这个必要的松弛点。
- **直接证据**: `git show HEAD:dayu/cli/init_workspace.py` 第 1293 行 `_require_ordinary_directory(...)` 调用；第 1462-1475 行该函数对 `not stat.S_ISDIR(identity.mode)` 直接抛出。
- **影响**: 实施 Agent 可能实现不完整，导致 regular-file cleanup 在 quarantine 前失败；需一轮 review 回退修正。
- **建议改法和验证点**: 在 §4.2 第 7 点或 §2 cleanup 行补充一句："`_require_ordinary_directory` 调用在 expected identity 为 regular file 时替换为 `_require_ordinary_file`（或在现有函数内增加 regular file 放行分支），symlink/reparse/special 拒绝不变。"
- **修复风险（低）**: 一行说明即可消除歧义。
- **严重程度（低）**: 不影响 plan 的整体正确性——semantic owner 判断正确（`_cleanup_private_path` 是正确 owner），只是 implementation detail 略欠显式。实施 Agent 阅读现有代码后会自然发现此点；提前写明可避免一次 review round-trip。

## Open Questions

None。用户已明确裁决所有 blocking questions（§11.1），Goal boundary 已冻结。

## Residual Risks

| Risk | Classification | Tracking |
|---|---|---|
| 外部进程并发修改 workspace | Out of scope（用户裁决） | 不在本 WU 追踪 |
| Windows reparse 平台能力 | 沿用 S1–S3 baseline（§11.2） | CI owner 负责 |
| `apply_patch` 工具可用性 | 低风险，有验证步骤兜底 | Finding #1 |
| `_require_ordinary_directory` 松弛遗漏 | 低风险，review 可捕获 | Finding #2 |
| 现有 transaction fault coverage | 由既有 tests 持续覆盖（§4.6） | 无需新增 |

## Conclusion

**PASS**

Plan 已正确完成 scope correction：

1. **不含 out-of-scope 项**：TOCTOU、descriptor pinning、ctime/nlink stable state、loader snapshot API、typed manifest、新 transaction/rollback state machine 均被显式排除，并设有停止条件防止实现中重新引入。
2. **不遗漏 Goal 定义项**：PRESERVE 根配置补缺（§4.1/4.3）、OVERWRITE ordinary-file root repair（§4.2/4.4）、RESET ordinary-file root repair（§4.2/4.5）、最终 tree 验证（§4.3-4.6 及 §9.2 断言）全部覆盖。
3. **Cleanup 分派最小**：仅基于已有 `PathIdentity.mode` 在 `_cleanup_private_path` 增加 `os.unlink` vs `shutil.rmtree` 分派；不新增 type、helper、backup 扩展或安全契约。

两个 low-severity findings 均不构成 plan 级 blocker——#1 是实施工具链澄清，可在 implementation 前一行修正；#2 是现有代码阅读后自然解决的实施细节。两个都不改变 plan 的架构裁决、owner 分配或 scope boundary。

Plan 可以进入 implementation gate。
