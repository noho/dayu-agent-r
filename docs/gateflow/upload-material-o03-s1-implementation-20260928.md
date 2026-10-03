# UM-O03-F01 S1 implementation

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol。实施 label：`o03-implement-sol-20260928-01`；日期：2026-09-28；workspace：`/private/tmp/dayu-upload-o03`。

## 基线与范围

- 启动时分支 `codex/upload-material-o03`，HEAD `92927cf5742bd2ba72f61179023af827d3e08675`，`git status --porcelain=v1 --untracked-files=all` 为空。实施后 HEAD 未变；未 stage、commit、push、开 PR、merge 或进入 code review gate。
- 已读 `AGENTS.md`、goal、accepted plan、总控裁决及 Kimi/MiMo 两份最新 plan re-review（`docs/reviews/plan-review-20260928-233054.md`、`docs/reviews/plan-review-20260928-233143.md`）。本次仅改 plan 允许的 CLI owner/直接调用者/测试、按职责 README，另写本实施 artifact；冻结文件未改。
- 动机由当前代码直接成立：旧 Fins 私有 resolver 只判空与规范化，普通文件目标可越过 CLI admission 进入 Service 装配。严重性限于路径用法错误延迟并误分类；没有证据声称已发布错误材料。普通 CLI workspace 参数的文本和最终目标类型归 `dayu/cli/workspace_root.py` 唯一拥有；`init` 的 no-follow 生命周期仍由其自身拥有。

## 实施与修复登记

1. 新建 `dayu/cli/workspace_root.py`：裁剪首尾空白、拒绝空值、`expanduser().resolve(strict=False)`，再用 `stat.S_ISDIR` 对现存最终目标判目录。普通文件及指向文件的 symlink 统一抛出无原路径的 `--base must point to a directory; choose a directory path`；缺失目标及悬空 symlink 继续按原装配规则返回解析目标；其它路径异常透传。模块只依赖标准库，异常由调用者的用法错误工厂构造。
2. `agent_entrypoint.py` 删除旧 resolver、仅供其使用的 base 常量及导出，保留其它文本、SIGINT、override 能力；`session_execution.py` 和 `commands/session.py` 直接导入新 owner，保留原错误投影。
3. `commands/fins.py` 的 direct 与 `upload_filings_from` 两处调用新 owner 并传 `CliFinsUsageError`，删除私有 resolver。`_BASE_OPTION` 仍在两处脚本 argv 生成中使用；未改上传、存储或脚本发布合同。普通文件在 direct Service factory 前及批量计划/发布前拒绝，exit 2。
4. 新增 owner 契约和 AST import 收敛测试；Fins parser/main 测试覆盖文件 base 早拒绝、别名、重复 base 最后值、默认 cwd；`upload_filings_from` 测试覆盖早拒绝与生成脚本的 `--base` token；真实 CLI 子进程测试先核对 checkout 身份，再核对文件 base、快照和目录 symlink 不被类型规则拒绝。
5. `README.md` 只补用户可执行的 base 目录要求、目录 symlink 与 exit 2 说明；`tests/README.md` 补实际新增的测试边界。已读两份 README 的更新约束；本次未改变跨包装配，`dayu/README.md` 无需更新。

## 环境、身份和真实 CLI 证据

- 本 worktree 的 `.venv` 是 Python 3.11.15；`python -m pip show dayu-agent` 返回 `Version: 0.1.4`、`Location: /private/tmp/dayu-upload-o03/.venv/lib/python3.11/site-packages`、`Editable project location: /private/tmp/dayu-upload-o03`。在 `/private/tmp` 且清除 `PYTHONPATH` 的子进程导入核验中：`dayu.__file__=/private/tmp/dayu-upload-o03/dayu/__init__.py`，`sys.executable` 解析目标为 `/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/bin/python3.11`，`sys.prefix=/private/tmp/dayu-upload-o03/.venv`；与测试进程及测试文件动态推导的目标逐项相同，身份检查 exit 0。常驻测试先做此断言，失败即不继续执行 CLI 验收。
- 手工真实 CLI 复验的 cwd 是 `/private/tmp/o03-real-cli-ed9bdd8j`，继承环境清除 `PYTHONPATH`。实际命令：`/private/tmp/dayu-upload-o03/.venv/bin/python -m dayu.cli upload_material --base /private/tmp/o03-real-cli-ed9bdd8j/base --ticker AAPL --forms 10-K --material-name sample --files /private/tmp/o03-real-cli-ed9bdd8j/missing-input.pdf`。退出 `2`；stdout 为空；stderr 逐字为 `dayu-cli upload_material: --base must point to a directory; choose a directory path\n`（末尾换行）。stderr 无 base 绝对路径、缺失上传输入或 `storage_io` 文案。
- 上述复验前后 cwd 顶层快照均仅有 `base`，其字节十六进制前后均为 `6f3033206f726967696e616c2062617365`（`o03 original base`）；无 `material`、portfolio 或额外 workspace 树。parser/main 用禁止调用的 factory 再确认 base 拒绝发生于 Service 装配和上传输入读取前；批量入口用禁止调用的计划生成及发布函数确认早拒绝。
- 一次性错误 checkout 反例：建立 `/private/tmp/o03-fake-dayu.WNvsyi/dayu/__init__.py` 后，从 `/private/tmp` 执行 `PYTHONPATH=/private/tmp/o03-fake-dayu.WNvsyi /private/tmp/dayu-upload-o03/.venv/bin/python -c 'import dayu,pathlib,sys; expected=pathlib.Path("/private/tmp/dayu-upload-o03/dayu/__init__.py").resolve(); imported=pathlib.Path(dayu.__file__).resolve(); print("imported="+str(imported)); print("expected="+str(expected)); print("python="+str(pathlib.Path(sys.executable).resolve())); print("prefix="+str(pathlib.Path(sys.prefix).resolve())); assert imported == expected, "checkout identity mismatch"'`。实际 `imported=/private/tmp/o03-fake-dayu.WNvsyi/dayu/__init__.py`，`expected=/private/tmp/dayu-upload-o03/dayu/__init__.py`，断言退出 `1`。这只演示身份检查能拒绝错误代码树，不进入常驻测试。

## 验证结果

- Sol 原始实施环境先运行 `source .venv/bin/activate`，再执行 `MIMO_PLAN_API_KEY=test-key python -m pytest tests/cli/test_workspace_root.py tests/cli/test_fins_commands.py tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py -q --cov=dayu.cli.workspace_root --cov-report=term-missing --cov-fail-under=80 --tb=short`；当时观察为 **440 passed、2 skipped、3 个第三方 edgartools deprecation warnings**，命令 exit 0，37.81 秒；新 owner `19 Stmts / 0 Miss / 100% Cover`。这是该环境的历史观测，不是 reviewer 独立全量复验通过的声明。此次 Sol 派发 JSONL 同时含四条失败 `command_execution`，按 sub-agents 协议 `agent_status=failed`；落盘实施仍须作为候选接受审查，不能以末尾完成声明替代派发状态。
- Kimi/MiMo reviewer 沙箱独立运行七文件测试时，三个 `test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 参数化用例在 `pty.openpty()` 报 `OSError: out of pty devices`，发生在产品代码运行前。Kimi 全量结果为 437 passed、2 skipped、3 failed，exit 非 0；MiMo 两次全量结果分别为 436 passed、2 skipped、4 failed 和 437 passed、2 skipped、3 failed，均 exit 1。MiMo 另观察固定共享 smoke root 用例间歇红，但缺少完整失败断言，具体机制未证实。两路 reviewer 的全量运行均不能记为通过，PTY 失败也不能归因为产品缺陷。
- 总控在 O03 checkout/.venv 独立单跑上述三个 PTY 用例，记录为 **3 passed、92 deselected、exit 0**；这是与 reviewer 沙箱不同的运行环境和较窄测试范围，不代替其全量复验结果。S1 review fix `o03-s1-review-fix-sol-20260929-01` 的后续测试和类型检查记录见 `upload-material-o03-s1-code-review-adjudication-20260929.md`。
- 首次未设置 `MIMO_PLAN_API_KEY` 的完整测试运行在 prompt/interactive 的既有配置加载处出现 `missing env MIMO_PLAN_API_KEY`，未到路径逻辑；用仅供测试的占位值 `test-key` 复验后全部通过，没有调用真实模型。未用其它 checkout 的 editable 环境代替本 worktree。
- 首次全量 `python -m pyright dayu/ tests/ utils/` 因本地 `.venv` 缺少 browser extra 而报告 9 个 Playwright import missing errors，位置在未修改的 web 文件。随后在本 worktree 执行 `python -m pip install -e '.[browser]' -c constraints/lock-macos-arm64-py311.txt`（exit 0），最终相同 pyright 命令结果 **0 errors、0 warnings、0 informations**，exit 0。`git diff --check` 通过；`_BASE_OPTION` 定义及两处使用仍在。

## 残余风险与边界

- 目录类型检查与后续装配之间仍可能发生路径类型竞争；权限、父路径非目录和特殊节点的完整诊断分类属于后续独立目标。
- `upload_filings_from --infer` 的现有 FMP 调用仍先于 base 检查；其脚本发布 symlink/containment 合同、`init` 的 no-follow 生命周期均未改。#198、点号元数据与其它 upload_material 项不在本切片。
- 本次实施停在 S1；尚未做 code review、commit 或 PR 汇入，后续由总控及用户掌握。

CANARY=gpt-6-sol-45940399
