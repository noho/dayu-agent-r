# P10.5 Aggregate Re-Review — AgentMiMo

## Verdict

**PASS**。blocking findings count = 0。

controller adjudication AG1-AG4 已完整收口，`dayu.host` 包根不再暴露低层符号，测试与 README 同步更新。

## Review Questions 回答

### Q1: 包根是否不再暴露 AG1-AG4 符号？

**PASS。**

`dayu/host/__init__.py` 中：

- `__all__` 不包含 `start_run`、`create_host_command_handle`、`HostCommandHandle`、`HostCommandFacet`、`HostCommandHandleOptions`、`HostLocalExecutionOptions`、`StartRunRequest`。
- 模块级 import 中也无这些符号（无 `from dayu.host.command import start_run` 等）。

运行时验证：

```
start_run: hasattr=False, in __all__=False
create_host_command_handle: hasattr=False, in __all__=False
HostCommandHandle: hasattr=False, in __all__=False
HostCommandFacet: hasattr=False, in __all__=False
HostCommandHandleOptions: hasattr=False, in __all__=False
HostLocalExecutionOptions: hasattr=False, in __all__=False
StartRunRequest: hasattr=False, in __all__=False
```

低层边界仍可导入：`from dayu.host.api import HostCommandFacet, HostCommandHandleOptions, HostLocalExecutionOptions, StartRunRequest` 均成功。

### Q2: 低层测试是否改为从 `dayu.host.api` / `dayu.host.command` 导入？

**PASS。**

`grep` 扫描 `tests/host/` 全目录，未发现任何 `from dayu.host import` 违禁符号的导入。

测试文件均使用：
- `from dayu.host.api import ...` — 导入 `HostCommandHandleOptions`、`StartRunRequest`、`HostCommandFacet` 等。
- `from dayu.host.command import ...` — 导入 `HostCommandHandle`、`create_host_command_handle`、`start_run`。

无兼容 re-export / wrapper。

### Q3: README 是否只描述当前 public contract？

**PASS。**

`dayu/host/README.md` diff 正确：
- 移除了 `HostCommandHandleOptions`、`HostCommandFacet` 从包根公共命名空间描述。
- 明确标注 `start_run`、`StartRunRequest`、command-handle construction types、`HostLocalExecutionOptions` 为低层 / 内部模块路径。
- `requests` 列表中移除 `StartRunRequest`。
- `dayu.host.api.__all__` 描述补充了低层类型归属。

`dayu/README.md` diff 正确：
- 明确低层 command handle factory、`start_run`、`StartRunRequest`、command-handle construction types、`HostLocalExecutionOptions` 不属于包根公共命名空间。
- `start_run` 术语定义标注为"低层 command / diagnostic 接口"。

### Q4: 是否引入新的 blocker？

**无新 blocker。**

- `test_package_exports.py` 白名单正确排除 AG1-AG4 符号（`ROOT_INTERNAL_API_NAMES`、`FORBIDDEN_HOST_ROOT_EXPORTS`、`REMOVED_SERVICE_FACING_ALL_EXPORTS` 均覆盖）。
- 无新增 public contract、typing、import boundary 或 README mismatch。

## 验证命令与结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_package_exports.py -q` | 8 passed |
| `pytest tests/host -q` | 695 passed, 1 failed, 1 skipped |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无 whitespace 问题 |

### 唯一失败测试分析

`test_mimo_public_real_runner_two_turn_path` 失败原因：外部 API 调用返回 `finish_reason=length`（模型输出超过 `max_tokens=2048`）。该测试未被本次修改触及（`git diff` 无变更），是环境依赖的 flaky test，与 AG1-AG4 收口无关。

## Remaining Risk

- 本次仅验证 `dayu/host` 与 `tests/host` 边界，未运行全仓测试。
- `test_mimo_public_real_runner_two_turn_path` 是 provider smoke test，依赖外部 API key 与模型行为，属已知环境 residual。
