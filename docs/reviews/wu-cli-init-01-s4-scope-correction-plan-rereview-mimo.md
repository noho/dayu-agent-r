# WU-CLI-INIT-01 S4 Scope-Correction Plan Rereview — MiMo

## Review target

- **Artifact**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`（修订版）
- **唯一目标边界**: `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- **Reviewer**: AgentMiMo
- **Date**: 2026-07-30
- **前序 review**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-review-mimo.md`

## Scope

Focused rereview：只验证前序 findings 01/02/03 是否已在修订版 plan 中关闭，并检查修订未重新扩大 Goal。

## Finding 01 验证：`_regular_file_digest` ctime/nlink descriptor stable state

**状态: CLOSED**

修订版新增：

- §4.3 item 4: "最终删除当前 partial implementation 的 `_descriptor_stable_state(...)`；regular digest 不做 pre/post `fstat`，不读取或比较 `st_ctime_ns` / `st_nlink`，不建立'稳定读取'新契约；并发 mutation 明确不在本 WU"
- §5 "明确不新增" 列表增加 "descriptor-stable regular-file digest"
- §6 S4-SC2 Exact production changes: "删除 `_descriptor_stable_state(...)`；regular-file digest 只复用现有 no-follow identity/mode 验证并普通读取 SHA-256，不做 pre/post `fstat`，不读 ctime/nlink"

修订明确指导实现 agent：简化 `_regular_file_digest` 只做 identity check + SHA-256 read，移除 `_descriptor_stable_state` 函数。前序 finding 的矛盾已消除。

## Finding 02 验证：backup tuple 扩展与 rollback loop

**状态: CLOSED**

修订版新增：

- §4.3 item 6: "`backup_records` 保持 HEAD 的 3-tuple `tuple[ManagedRootSnapshot, Path, PathIdentity]`，不得增加 shape；`_rollback_or_raise(...)` 的签名、tuple unpacking 与 restore loop 对 HEAD 无净 diff"
- §4.3 item 8: "不新增 `_PrivatePathShape` 或其它 shape protocol，不给 backup tuple 增加 shape，不修改 rollback loop；`_post_publication_cleanup(...)` 的签名及调用不传 `expected_shape`；file-vs-directory 真源只由 `_cleanup_private_path(...)` 直接从既有 `expected_identity.mode` 派生"
- §6 S4-SC2 Exact production changes: "`backup_records` 保持 HEAD 3-tuple，`_rollback_or_raise(...)` signature/unpacking 无净 diff，`_post_publication_cleanup(...)` 不传 shape"

修订明确给出了实现路径：cleanup dispatch 在 `_cleanup_private_path` 内部用 `expected_identity.mode` 派生，不改 backup tuple 结构。前序 finding 的矛盾已消除。

## Finding 03 验证：`_load_target_min_context_window` 签名变更

**状态: CLOSED**

修订版新增：

- §3 `commands/init.py` 行: "`_load_target_min_context_window(...)` 恢复 HEAD path-loader contract"
- §4.2 完整新增 section: 列出 `_load_target_min_context_window` 恢复 HEAD 签名（`workspace_root: Path`）、恢复 `ConfigLoader.load_execution_profiles(workspace_config_dir=...)` 调用、删除 fd reader 类/常量/helpers 的完整清单
- §6 S4-SC2 Exact production changes: "`_load_target_min_context_window(...)` 及 execution-profile loader 调用恢复 §4.2 的 HEAD path-loader contract，移除全部 fd reader 类/常量/helpers"

修订显式列出了需要撤销的函数、类和常量。前序 finding 的遗漏已消除。

## Goal 扩大检查

修订版 plan 未重新扩大 Goal：

- §4.2（execution-profile loading 恢复）是撤销 S4 out-of-scope overreach，恢复 HEAD 已有行为，不是新增 Goal item
- §4.3 item 7（`_cleanup_private_path` 的 directory-only assertion 调整）是 ordinary-file recovery 的必要技术变更，且明确限定 "不把这一放宽扩散到其它 directory-only caller"
- 所有修订与 Goal 的 "ordinary partial/corrupt state 可通过适用的 preserve/overwrite/reset 路径恢复" 和 "preserve 保留用户内容、补齐缺失 managed files" 成功信号一致

## Conclusion

**PASS**

三个 findings 均已在修订版 plan 中关闭，修订未重新扩大 Goal。plan 可进入 implementation。
