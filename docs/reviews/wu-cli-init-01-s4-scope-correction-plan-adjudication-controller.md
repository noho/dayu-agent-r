# WU-CLI-INIT-01 S4 Scope-Correction Plan Adjudication

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- Gate：`scope-correction plan review adjudication`
- 唯一目标边界：
  `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Reviewed plan：
  `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- Reviewer artifacts：
  - `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-review-mimo.md`
  - `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-review-ds.md`
  - `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-rereview-mimo.md`
  - `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-rereview-ds.md`
- Decision：`PASS`
- 下一入口：`S4 implementation`

## Controller 范围裁决

用户要求严格按照 Goal Confirmation 实施。S4 的最终范围固定为：

1. PRESERVE 补齐五类缺失根配置和既有 package-owned 缺失项，同时保留用户内容；
2. OVERWRITE 可修复 ordinary regular file 占据的 `config`，重建 config 并保留
   `.dayu`；
3. RESET 可修复 ordinary regular file 占据的 `config` / `.dayu`，重建 init-owned
   roots 并保留 portfolio、assets 与其它非 init-owned roots；
4. malformed ordinary config 在 PRESERVE 中不得被覆盖，必须保持原 tree 并失败；
   显式 OVERWRITE / RESET 可按 owner 恢复；
5. 复用现有 transaction、backup、publication 和 rollback，不新增或改写其状态机；
6. 只为 ordinary-file backup cleanup 增加基于既有 `PathIdentity.mode` 的最小
   `os.unlink` / `shutil.rmtree` 分派；
7. 验收以最终真实 tree、bytes、digest、identity 和 ConfigLoader 可加载结果为准，
   不依赖 CLI 自报 mode。

以下内容明确不属于本 work unit，当前尚未提交的相关实现必须删除：

- 并发文件系统 mutation、TOCTOU、race barrier；
- descriptor pinning、逐层 fd-relative reader、`O_NONBLOCK` reader；
- `st_ctime_ns` / `st_nlink` stable-state contract；
- ConfigLoader snapshot/bytes API 与 typed filename manifest；
- `_PrivatePathShape`、backup tuple shape 扩展；
- 新 transaction、rollback、fault boundary 或 fault matrix。

symlink、dangling symlink、special file、Windows reparse 和非法 lock identity 只维持
现有静态拒绝，不扩展 recovery 范围。

## Findings 裁决

### MiMo 首轮 findings

1. `_descriptor_stable_state` 与 ctime/nlink 残留：`ACCEPTED`。
   修订计划明确删除 helper，不做 pre/post `fstat`，不读取或比较 ctime/nlink。
2. backup tuple / rollback loop 路径不明确：`ACCEPTED`。
   修订计划固定 HEAD 3-tuple，rollback signature/unpacking 无净 diff，cleanup 直接
   从 `expected_identity.mode` 派生。
3. `_load_target_min_context_window(...)` 恢复不够显式：`ACCEPTED`。
   修订计划明确恢复 HEAD path-loader contract，并列出全部 fd reader 类、常量和
   helper 的删除范围。

MiMo focused rereview：`PASS`，三项均关闭。

### DeepSeek 首轮 findings

1. `apply_patch` 未定义：`REJECTED`。
   Codex 内置 `apply_patch` 是当前环境明确提供的文件编辑工具；继续使用该工具，
   禁止 shell 重定向、`cat` 或 Python 写文件绕过。
2. cleanup 前置 directory-only 校验未写明：`ACCEPTED`。
   修订计划明确只在 `_cleanup_private_path(...)` owner 内接受 expected ordinary
   regular file 或 ordinary directory，不向其它 directory-only caller 扩散。

DeepSeek focused rereview：`PASS`，无 material finding。

### Controller 补充

撤销流程末尾的最终无-diff清单曾错误包含 `commands/init.py` 和对应测试。修订后只要求
以下两个 revert-only 文件对 HEAD 无净 diff：

- `dayu/runtime/config_loader.py`
- `tests/runtime/test_config_loader.py`

其余五个 allowed code/test files 只允许出现修订计划列明的最小业务 diff。

## Gate decision

两路 focused rereview 均为 `PASS`，没有 blocking open question。S4
scope-correction plan 获准进入 implementation。

Implementation Agent 必须先用 `apply_patch` 把七个 partial files 精确恢复到
`cf72af5d`，验证无 diff 后，再按 accepted plan 添加最小 S4 业务增量。不得继承此前
amendment 的竞态或增强事务设计。
