# WU-CLI-PROMPT-01 S3 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S3 — Shared lightweight startup bootstrap`
- Owner: `controller`
- Timestamp: `2026-07-31 18:43:41 +0800`
- Prerequisite accepted commit: `ccf836f0`

## Root cause 与语义 owner

`dayu-cli` console script 原来直接指向 `dayu.cli.main:main`，而 `dayu.cli.main` 在函数调用前会 eager import parser、全部 command 及其 Service/Host/Engine/Fins 依赖。`python -m dayu.cli` 的 `__main__` 也在模块顶层 eager import 同一 application。两条公开入口因此都在 `KeyboardInterrupt -> 130` owner 建立前存在较长 import gap。

公共 process bootstrap 是 startup interruption 的唯一 owner。它必须先以轻量模块建立中断边界，再在边界内加载和调用 application；prompt command 仍只拥有 Run 阶段 monitor，不承担 process startup signal 语义。

## 修改文件

- `dayu/cli/__main__.py`
  - 移除重型顶层 `dayu.cli.main` import。
  - `run_module()` 在同一 `try` 内 lazy import `main` 并执行完整 application。
  - 任意阶段透出的 `KeyboardInterrupt` 统一返回 130；其它异常不被泛化吞掉。
- `pyproject.toml`
  - `dayu-cli` console script 改为 `dayu.cli.__main__:run_module`，与 module invocation 共用 owner。
- `tests/cli/test_arg_parsing.py`
  - 在 lazy application import、标准流配置、parser、日志资源准备阶段分别注入中断。
  - 断言 130、空 traceback 输出，且 primary runner 不会启动。
- `tests/cli/test_prompt_command.py`
  - 在 runtime prepare、Host open、Session ensure commit 前和 prompt monitor install 阶段注入中断。
  - 断言 Host context/Session attachment 精确关闭；提交前无 Session API；monitor 尚未安装完成时已完整创建的 Session 保留 Host 事实，但没有 submit/cancel Run 或半初始化 Run/attempt。
- `tests/cli/test_public_package_entrypoints.py`
  - pyproject 与 wheel entry point 精确断言新 bootstrap owner。

## Scope 判定

没有搬动业务模块、修改 prompt/interactive command contract、建立 signal registry、增加 Host rollback 或伪造 cancellation。已原子完成的 durable Session 仍由 Host owner 管理；测试只要求中断点之后不开始 Run submission，并验证已打开资源正常关闭。

## 验证证据

1. 定向 bootstrap tests：
   - `pytest -q tests/cli/test_arg_parsing.py -k 'run_module or module_run_function'`：`5 passed`。
   - `pytest -q tests/cli/test_prompt_command.py -k 'startup_interrupt'`：`4 passed`。
2. 受影响完整回归与覆盖率：
   - `pytest -q tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_public_package_entrypoints.py tests/cli/test_import_boundary.py --cov=dayu.cli.__main__ --cov-report=term-missing`
   - `153 passed`；`dayu/cli/__main__.py` 覆盖率 `90%`。
3. 静态类型：
   - `pyright dayu/cli/__main__.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_public_package_entrypoints.py`
   - `0 errors, 0 warnings, 0 informations`。
4. package entry：
   - 执行 editable reinstall 后，`.venv/bin/dayu-cli` 生成代码导入 `dayu.cli.__main__.run_module`。
   - `.venv/bin/dayu-cli --help` 与 `python -m dayu.cli --help` 均成功。
5. 真实 process probe：
   - 冻结 console 入口的 0.05 秒 elapsed SIGINT 时序连续 5 次均为 exit 130，stdout/stderr 为空、无 traceback，workspace 无文件。
   - `python -m dayu.cli` 在 bootstrap 已开始的 0.20 秒 probe 为 exit 130、空输出、workspace 无文件。
6. `git diff --check`：通过。

## 真实 process 边界说明

一次额外的非冻结诊断把 `python -m dayu.cli` 信号发送在进程启动后 0.05 秒，其中部分样本发生在 Python 尚未开始执行 `dayu.cli.__main__` bytecode 前，OS 直接报告 `-2`。纯 Python bootstrap 无法拥有 interpreter 执行任何项目代码之前的 signal；冻结 P47/PC-CN-01..06 使用安装后的 `dayu-cli`，对应 0.05 秒 console probe 已稳定 5/5。模块入口从开始执行项目 bootstrap 起的 import/application gap由 owner-level 注入测试与 0.20 秒真实 probe 覆盖。

## README 判定

startup interruption 的用户/测试 contract 已按 accepted plan留到 S6 更新；本 slice 不提前修改 README。

## 残余风险与后续验证

- 最终仍须按 P47、PC-CN-01..06 的 exact installed-console argv、elapsed timing、filesystem/SQLite before-after 重放；本 slice probe 不代替 frozen harness 全证据。
- Python interpreter 尚未执行任何项目 bytecode 前的原始 OS signal不属于 CLI bootstrap 可控制区间；冻结场景不使用该 module-form pre-bytecode 窗口。

## Gate 结论

S3 实现和 owner-level/installed-console 验证完成，进入独立 `deepreview` gate。
