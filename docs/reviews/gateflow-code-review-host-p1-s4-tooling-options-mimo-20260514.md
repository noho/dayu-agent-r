# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-1
- Base: HEAD (1f70719)
- Output file: docs/reviews/gateflow-code-review-host-p1-s4-tooling-options-mimo-20260514.md
- Included scope: 当前未提交 workspace changes，相对 HEAD 的 diff；重点检查 Slice 4 实现是否符合 approved plan 与 design.md §10.1 / §18.1。
- Excluded scope: Slice 1–3 已提交代码、Engine / Fins / Service / UI / runtime 模块。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

以下为逐项审查结论：

### 1. 允许范围检查

diff 涉及文件：`dayu/host/tooling.py`（新建）、`dayu/host/__init__.py`、`tests/host/test_tooling_options.py`（新建）、`tests/host/test_package_exports.py`、`tests/host/test_import_boundary.py`、`dayu/host/README.md`、`dayu/README.md`、`tests/README.md`。全部在 approved plan Slice 4 允许修改范围内。`docs/reviews/gateflow-implementation-host-p1-s4-tooling-options-20260514.md` 是 implementation artifact，不在 diff 中但作为参考。

### 2. 模块职责边界

`dayu/host/tooling.py` 只定义 construction typed input，不实现：
- ToolRuntime factory — 未出现。
- framework tool injection — 未出现。
- ToolsDiscovery / ScenePrepare — 未出现。
- 业务工具扫描 — 未出现。
- durable snapshot / digest — 未出现。

符合 Slice 4 non-goals。

### 3. API shape 完整性

plan 要求的 6 个公共符号全部实现：
- `ToolBundleSourceKind(StrEnum)` — `tooling.py:45-55`。
- `FrameworkToolName(StrEnum)` — `tooling.py:58-61`。
- `ToolBundleSourceRef` — `tooling.py:64-95`，frozen dataclass，`__post_init__` 校验。
- `FrameworkToolPolicyView` — `tooling.py:98-123`，frozen dataclass，`__post_init__` 校验。
- `HostToolingOptions` — `tooling.py:142-176`，frozen dataclass，`__post_init__` 校验。
- `default_framework_tool_policy_view()` — `tooling.py:126-139`，返回新实例，无共享可变状态。

与 approved plan Contract / API Decisions 一致。

### 4. 校验语义

| 要求 | 位置 | 结果 |
|------|------|------|
| `source_refs` 非空 | `tooling.py:165-166` | 正确抛 `ValueError` |
| `source_id` 非空 | `tooling.py:86-88` | 正确抛 `ValueError` |
| `version_ref` / `content_digest` optional 非空 | `tooling.py:89-95` | 存在时正确抛 `ValueError` |
| `enabled` 是 `reserved` 子集 | `tooling.py:117-123` | 正确抛 `ValueError` |
| 业务 ToolBundle 不得占用 `fetch_more` | `tooling.py:167-176` | 正确抛 `ValueError` |
| 默认 reserved 包含 FETCH_MORE，enabled 为空 | `tooling.py:136-139` | 正确 |

### 5. 导出边界

- `dayu.host.__init__` 导出 6 个 tooling 符号到 `__all__` — 确认。
- `dayu.host.api.__all__` 不包含 tooling 符号 — 确认（测试验证）。
- `dayu.host` 不 import Engine / Fins / Service / UI — 确认（import boundary 测试覆盖）。

### 6. request 边界

`test_import_boundary.py` 新增 `test_host_request_dataclasses_do_not_carry_tool_bundle`，遍历全部 11 个 request dataclass 的 fields，确认无 `business_tool_bundle` 字段。符合 plan 要求。

### 7. 类型与 docstring

- 所有 dataclass 使用 `frozen=True, slots=True`。
- 所有枚举使用 `StrEnum`。
- 所有模块、类、函数提供中文 docstring。
- 未使用 `Any`、`object`、无类型参数或无类型返回值。
- pyright 通过（仅预存的 pytest import 解析问题，非本 slice 引入）。

### 8. 测试覆盖

14 tests 全部通过。覆盖：
- `StrEnum` 类型与枚举值稳定性。
- 默认 policy view 预留 FETCH_MORE、enabled 为空。
- frozen dataclass + frozenset + 不共享可变状态。
- enabled 必须是 reserved 子集。
- `ToolBundleSourceRef` 空字符串 / 纯空白拒绝。
- `source_refs` 非空。
- 业务 ToolBundle 占用 reserved name 拒绝。
- 正常业务 bundle 可接受。
- 包根导出白名单。
- tooling 符号从包根导出但不进入 `dayu.host.api`。
- Host request dataclass 不携带 `business_tool_bundle`。

符合 Slice 4 Expected assertions。

### 9. README 同步

- `dayu/host/README.md`：新增 Host Tooling Options 段落、校验边界新增 4 条、架构边界新增 tooling 描述、non-goals 更新、测试说明更新。与当前代码一致。
- `dayu/README.md`：术语表新增 `HostToolingOptions`、更新 `ToolBundle` 描述、更新 `dayu.host` 公共命名空间说明。与当前代码一致。
- `tests/README.md`：更新 `tests/host/` 说明、新增 tooling options 测试命令、更新维护约定。与当前测试一致。

## Open Questions

无。

## Residual Risk

- `HostToolingOptions` 当前只做 construction-time typed boundary 与 reserved name 防御性校验；durable tool snapshot refs、bundle / schema digest 与 policy binding refs 仍需后续 ToolRuntime / command path phase 落地。这是已知 deferred scope，不是本 slice 遗漏。
- 当前只支持单个 construction-time business `ToolBundle`；多 scene tool profile 需后续 phase。同上。
