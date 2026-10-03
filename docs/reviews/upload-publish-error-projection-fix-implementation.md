# Implementation Artifact: Slice S1 — `upload_filings_from` CLI 错误投影修复

- gate: implementation（Slice S1，唯一 slice）
- work unit: `upload_filings_from --output` workspace 外目标 CLI 错误投影修复
- plan: `docs/plans/upload-publish-error-projection-fix.md`（D1–D5）
- 日期: 2026-09-18

## 派发记录

| runtime | provider | instance | 权限 | exit | subtype/is_error | artifact |
| --- | --- | --- | --- | --- | --- | --- |
| claude-agent-run | glm | impl-glm-01 | bypassPermissions（prompt 限定两文件 + 仅 pytest/pyright/只读 git 命令；permission_denials 为空） | 0 | success / false | `$TMPDIR/sub-agents.Gr8IuF/impl-glm-01.json` |

## 改动文件（总控 git status 复核，范围与 plan §4 一致）

1. `dayu/cli/commands/fins.py`
   - D3：`dayu.cli.upload_script` import 按字母序加入 `UploadScriptPublishError`；
   - D1：`run_fins_direct_command` except 链在 `FinsDirectStreamProtocolError` 之后、`KeyboardInterrupt` 之前插入 `UploadScriptPublishError` 分支，`render_cli_error(f"dayu-cli {args.command_name}: {exc}")` + `return EXIT_FAILURE`，不加 `_LOGGER.exception`（D2）；
   - D5：`_run_upload_filings_from` docstring `:raises` 补 `UploadScriptPublishError` 一行。
2. `tests/cli/test_upload_filings_from_command.py`
   - D4a：新增 `test_upload_filings_from_publish_contract_errors_project_specific_message`，三变体（internal symlink / 父目录不存在 / 目标类型非法）逐一断言 `EXIT_FAILURE` + 对应消息片段 + target 无文件 + 无 `.{target.name}.*.tmp` 残留；公共断言抽取为模块级私有 helper `_assert_publish_contract_failure`（符合 CLAUDE.md 重复逻辑抽取与模块级私有辅助函数约束）；

   > 状态回写（aggregate deepreview A4）：code review F1/F2 修复后，tmp 命名 glob 断言已替换为 workspace 条目集合快照（`after == before`，owner 级零副作用不变量），并参数化 `expect_target_absent`（变体 1/2 断言 `not target.exists()`，变体 3 断言 `not target.is_file()`）。最终代码状态以 code review artifact 与 `git diff` 为准。
   - D4b：既有 escape 用例末尾追加 `assert not (tmp_path / "outside.sh").exists()`（既有断言未动）；
   - D4c：新增 `test_upload_filings_from_unknown_failure_uses_generic_message`，monkeypatch `publish_upload_script` 抛 `RuntimeError("internal-boom-detail")`，断言通用文案 + stderr 不含内部消息。

## GLM 申报偏差（总控裁决）

1. D4a 增加 `monkeypatch.setattr(upload_script.os, "name", "posix")`：变体 3 依赖默认文件名 `upload_filings_AAPL.sh`，沿用同文件既有默认名依赖测试惯例（149/248/297/348 行）。**采纳**：跨平台确定性必要手段，属既有惯例。
2. 公共断言抽取 helper + `workspace.rglob` 兼容 parent 不存在场景。**采纳**：符合编码硬约束。
3. 验证命令在 `source .venv/bin/activate` 后运行：未激活 venv 时同文件既有 smoke 测试 `test_posix_generated_script_runs_real_cli_into_temp_storage` 在基线即失败（PATH 上裸 python 的 docling_core 旧版问题）。**采纳**：CLAUDE.md「修改后必做」本就要求 activate 后运行；GLM 已实测该失败先于本改动存在。

## 总控独立复验（非 agent 自述）

| 命令 | 结果 |
| --- | --- |
| `pytest -q tests/cli/test_upload_filings_from_command.py` | 21 passed, 2 skipped（基线 1 failed, 18 passed, 2 skipped → 原失败转绿 + 2 新用例） |
| `pytest -q` 六文件验收集合 | 266 passed, 2 skipped（基线 263 passed + 1 转绿 + 2 新增，数字吻合） |
| `pyright`（全仓） | 0 errors, 0 warnings, 0 informations |

diff 复核：except 分支位置、无 log、docstring、测试断言与 plan D1–D5 逐项一致；未触碰其它文件/分支/测试；无 git 写操作。

## Residual Risks（全部已分类）

1. symlink 变体 Windows 受限环境风险 — assigned to later work unit（沿用仓库惯例）。
2. 既有 smoke 测试对 venv 激活的依赖 — 基线既有行为，非本 slice 引入（tracked：本 artifact 记录；如 CI 需要可另立 work unit）。

   > 状态回写（aggregate deepreview open question 2）：GLM 申报的「venv 解释器差异」理由链未被独立证实；aggregate deepreview 实测观测到的失败形态为共享目录 `workspace/tmp/r11-posix-real` 残留导致的 source_kind 断言失败（pre-existing，基线对照确认）。无论哪种解释，均属环境风险、与本 diff 无关；venv 激活运行是 CLAUDE.md「修改后必做」的既定要求。
3. `str(exc)` 无界投影 — deferred-with-owner（plan §9）。
4. `--base` symlink 使 root-symlink 检查不可达 — deferred-with-owner（plan §9）。
5. `render_upload_script` 的 `ValueError`（CLI 路径不可达）与 publisher `OSError` 透传仍走 generic 分支 — assigned to later work unit（plan §9 第 2 项；aggregate deepreview A5 补齐本清单遗漏）。

## Completion Status

Slice S1 实现完成，全部 validation 通过。下一 gate：code review（DS + MiMo 两路并行）。
