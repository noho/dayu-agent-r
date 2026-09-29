# Issue #198 合入既有 draft PR #197 的集成验证

- Gate：`ready-to-open-draft-PR` 后的既有 PR 集成准备；PR `https://github.com/noho/dayu-agent-r/pull/197` 当时为 OPEN/draft，base `main`、head `codex/upload-material-oracle`、远端 head `9735800cb55a40336469593fa2fddae43c9c69ad`。本文件是合并快照验证记录，不宣告 PR review 或 final closeout pass。
- #198 accepted deepreview commit `cc6ee444`，其 S1/S2/aggregate 均已通过独立 Gateflow 证据；当前隔离 PR 集成工作树 `/private/tmp/dayu-issue198-pr197-integration` 原 HEAD 为远端 PR head。用户主工作树含其它未提交改动，未直接操作其 branch/index。

## 分叉与合并

- 总控 `git merge-base --is-ancestor 9735800c cc6ee444` 返回假；共同基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。PR 侧含点号元数据、O03、O20 等既有提交，#198 侧为计划、S1、S2 与 aggregate 四个提交；不能用 #198 head 直接覆盖远端 PR head。
- 相对共同基线 PR 侧改 67 文件，#198 侧改 56 文件，重叠 `README.md`、`dayu/cli/commands/fins.py`、`dayu/fins/README.md`、`tests/README.md`、`tests/cli/test_fins_commands.py` 五文件。先做只读 `git merge-tree` 预览，再在独立分支运行 `git merge --no-commit --no-ff cc6ee444`；Git 自动合并五文件、无冲突，停在未提交索引。`git diff --cached --check` 退出 0；没有覆盖 PR 旧提交或强推。
- 合并后 #198 增量相对原 PR head 为 61 文件（含计划/review 证据），代码和测试沿 #198 accepted owner 路径；重叠文件的 `fins.py`、CLI 测试及 README 均经下述实际验证覆盖。未改其他 WU 产品逻辑。

## 合并快照验证与环境归因

- 共享主 `.venv` symlink 下执行八个受影响测试文件：`862 passed / 1 failed`，失败仅 `test_real_upload_material_cli_rejects_file_base_from_this_checkout`。该 PR 既有 O03 测试在子进程中显式移除 `PYTHONPATH` 并要求 `dayu.__file__` 来自当前 checkout；共享 `.venv` 的 editable install 指向用户主工作树，因此导入身份断言失败。这是隔离 worktree 的验证环境错配，不是 #198 代码路径失败；单项 `-vv --tb=short` 直接显示期望 `/private/tmp/dayu-issue198-pr197-integration/dayu/__init__.py`，实际 `/Users/leo/workspace/dayu-agent-r/dayu/__init__.py`。
- 创建仅供验证的 `/private/tmp/dayu-issue198-pr197-testvenv`，通过本地 editable install 指向当前集成 checkout，并以只读 `.pth` 复用主环境依赖。独立 cwd 的 `dayu.__file__` 读回为当前 checkout；同一八文件命令在该 venv 下 **863 passed / 3 warnings，退出 0**。该 venv 在 `/private/tmp`，不进入仓库或 PR，不改变用户主 `.venv` 安装。
- `source .venv/bin/activate` 后全量 `python -m pyright dayu/ tests/ utils/`：**0 errors / 0 warnings / 0 informations，退出 0**。合并索引 `git diff --cached --check` 通过。根 README、Fins README、tests README 的更新符合各自触发读者：下载 typed/安全诊断、CLI 用法与测试覆盖说明；与 PR 原有 O03/O20 内容自动合并，无额外用户可见合同变更。

## 残余与下一 gate

- #198 aggregate OQ1 的 storage reason constructor invariant、插桩组合取消时序敏感、CNInfo 单日日期等均已在 `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md` 归独立 WU；不在 PR 集成中加 Fins 下游 fallback。
- 下一步创建本地集成 merge commit，确认 PR head 无外部竞态后 push 到同一 `codex/upload-material-oracle` 远端分支；更新 PR body 的 `Closes #198`（完整解决时由用户 merge 自动关闭），保持 draft。随后按 Gateflow 双路做**合并后线上 PR #197** review、裁决/修复/复审、accepted PR review commit 与 final push。用户自己 merge；不得 mark ready。
