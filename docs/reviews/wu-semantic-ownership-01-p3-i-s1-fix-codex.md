# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 fix report

## Scope

- Gate: `P3-I S1 fix`
- Worker: `AgentCodex`
- Accepted finding fixed: `DS F1`
- Finding summary: `_normalize_system_exit_code` 在 `dayu/web/__main__.py`、`dayu/wechat/main.py`、`dayu/render/render.py` 中重复。

## Root Cause And Owner Boundary

`SystemExit.code` 到整数进程退出码的规范化不是 Web、WeChat 或 render 的业务语义，而是所有 argparse 公开入口共享的层中立运行时语义。原实现把同一事实分别放在三个入口模块的 private helper 中，违反“重复逻辑必须抽取”的项目约束，并增加未来漂移风险。

语义 owner boundary:

- 事实产生者: argparse 在 help 或参数错误路径抛出 `SystemExit`。
- 校验/规范化 owner: `dayu.runtime.argparse_exit.normalize_argparse_system_exit_code`。
- 持久化: 无持久化状态。
- 投影: 三个公开入口的 `main()` 返回规范化后的整数退出码；模块执行路径再由 `raise SystemExit(main())` 投影为进程退出码。

## Changes

- 新增 `dayu/runtime/argparse_exit.py`
  - 提供 typed、standard-library-only 的 `normalize_argparse_system_exit_code(exc: SystemExit) -> int`。
  - 保持原行为: `SystemExit.code` 为 `int` 时原样返回；非整数 code 返回 argparse usage error `2`。
- 更新 `dayu/runtime/__init__.py`
  - 在 runtime 包说明中登记层中立 argparse 退出码规范化能力；包根仍不 re-export。
- 更新 `dayu/web/__main__.py`
  - 删除本地 `_normalize_system_exit_code` 和重复的 usage error 常量。
  - 入口 help/parse 异常路径改用 runtime helper。
- 更新 `dayu/wechat/main.py`
  - 删除本地 `_normalize_system_exit_code` 和重复的 usage error 常量。
  - 入口 help/parse 异常路径改用 runtime helper。
- 更新 `dayu/render/render.py`
  - 删除本地 `_normalize_system_exit_code` 和重复的 usage error 常量。
  - 入口 help/parse 异常路径改用 runtime helper。

未修改 `tests/cli/test_public_package_entrypoints.py`。现有 focused tests 已覆盖三个入口的 help 路径，该路径会触发 argparse `SystemExit(0)` 并经过共享 helper；本次没有改变测试断言所覆盖的公开行为。

## Propagation Audit

- `dayu.web.__main__.main()`:
  - `_build_parser().parse_args(argv)` 抛出 `SystemExit`。
  - `normalize_argparse_system_exit_code(exc)` 返回整数退出码。
  - `main()` 返回该退出码；`python -m dayu.web` 由 `raise SystemExit(main())` 使用同一退出码。
- `dayu.wechat.main.main()`:
  - 顶层 help、子命令 help 和 argparse 解析错误均进入同一 runtime helper。
  - 非 help 的当前不可用诊断路径不经过 helper，仍返回 `EXIT_UNAVAILABLE = 1`。
- `dayu.render.render.main()`:
  - help 和 argparse 解析错误均进入同一 runtime helper。
  - 非 help 的当前不可用诊断路径不经过 helper，仍返回 `EXIT_UNAVAILABLE = 1`。

结论: exit-code normalization 的真源现在只有 `dayu.runtime.argparse_exit`；三个入口的 LLM/user-visible help 与诊断语义未变化；无 durable state、trace、memory 或 audit 输出需要同步迁移。

## Validation

已运行:

```text
source .venv/bin/activate && pytest tests/cli/test_public_package_entrypoints.py -q
```

结果: `12 passed in 0.12s`

```text
source .venv/bin/activate && python -m dayu.web --help
```

结果: exit 0，输出 `dayu-web` help。

```text
source .venv/bin/activate && python -m dayu.wechat.main --help
```

结果: exit 0，输出 `dayu-wechat` help。

```text
source .venv/bin/activate && python -m dayu.render.render --help
```

结果: exit 0，输出 `dayu-render` help。

```text
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果: `0 errors, 0 warnings, 0 informations`

```text
git diff --check
```

结果: clean。

## Remaining Findings Or Blockers

- DS F1: fixed.
- 本 worker 未进入 re-review、未 commit、未 push、未创建 PR。
- 未触碰 S2 terminal cursor 文件。
- 未触碰无关 untracked 文件。
- Web UI、WeChat daemon/service、真实 render 转换能力仍按原计划属于后续 slice，不是本次 DS F1 fix 范围。
