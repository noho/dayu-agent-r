# Host Phase 4 Slice P4-S1 Code Review

- **reviewer**: AgentMiMo
- **review target**: 当前未提交 diff
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`，Slice P4-S1
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`
- **date**: 2026-05-14

## Review 范围

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `dayu/host/README.md`

## 验证结果

- `pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q`：30 passed in 0.08s
- `pyright dayu/host tests/host`：0 errors, 0 warnings, 0 informations

## Finding 列表

无 blocking finding。

## Plan 完整性逐项检查

| Plan Item | 状态 | 位置 |
|---|---|---|
| `HostApiErrorCode.UNSUPPORTED_OPERATION` | ✅ | `api.py:266` |
| `SteerConflictDetail` frozen/slots | ✅ | `api.py:270-300` |
| `HostApiErrorDetail` typed alias | ✅ | `api.py:303` |
| `HostApiError.detail` | ✅ | `api.py:1383-1408` |
| `FollowupSnapshot` accepted-run shape | ✅ | `api.py:1199-1264` |
| `FollowupSnapshot` queue + QUEUED 校验 | ✅ | `api.py:1248-1253` |
| `FollowupSnapshot` queue + RUNNING 校验 | ✅ | `api.py:1254-1259` |
| `FollowupSnapshot` queue 拒绝其它状态 | ✅ | `api.py:1260-1264` |
| `FollowupSnapshot` queue 不允许 target_run_id | ✅ | `api.py:1244-1247` |
| `FollowupSnapshot` steer 不要求 queued_run_id | ✅ | 无 steer 分支校验，符合 plan |
| `HOST_EVENT_STREAM_DEFAULT_LIMIT = 100` | ✅ | `api.py:18` |
| `HOST_EVENT_STREAM_MAX_LIMIT = 1000` | ✅ | `api.py:19` |
| `HostCommandHandleOptions` frozen/slots + 全字段 | ✅ | `api.py:529-619` |
| `HostCommandHandleOptions` 校验 optional handle id | ✅ | `api.py:566-569` |
| `HostCommandHandleOptions` 校验 Path 类型 | ✅ | `api.py:570-576` |
| `HostCommandHandleOptions` 校验 bool 类型 | ✅ | `api.py:577-580` |
| `HostCommandHandleOptions` 校验正数 float | ✅ | `api.py:581-610` |
| `HostCommandHandleOptions` 校验非负 int | ✅ | `api.py:587-592` |
| `HostCommandHandleOptions` 校验正数 int | ✅ | `api.py:614-619` |
| `api.py` `__all__` 更新 | ✅ | `api.py:1411-1453` |
| `__init__.py` 导出更新 | ✅ | `__init__.py:11-111` |
| 测试覆盖 enum + error detail | ✅ | `test_public_contracts.py:246-280` |
| 测试覆盖 stream constants | ✅ | `test_public_contracts.py:283-288` |
| 测试覆盖 `HostCommandHandleOptions` 校验 | ✅ | `test_public_contracts.py:291-376` |
| 测试覆盖 `FollowupSnapshot` accepted-run 校验 | ✅ | `test_public_contracts.py:434-544` |
| 测试覆盖 package exports | ✅ | `test_package_exports.py:9-53` |
| README 更新 | ✅ | `dayu/host/README.md` |

## 项目硬约束检查

| 约束 | 状态 | 说明 |
|---|---|---|
| 中文 docstring 完整 | ✅ | 所有新增类与函数均有完整中文 docstring，含参数/返回值/异常 |
| 无 Any/object/无类型签名 | ✅ | `TypeAlias` 显式声明；所有签名完全 typed |
| 无 getattr/hasattr 逃避类型 | ✅ | 未使用 |
| 无无结构 payload/god bag | ✅ | `HostApiErrorDetail` 为 typed union，非 dict/Any |
| 无兼容 wrapper/re-export | ✅ | 无 |
| 无反向依赖 | ✅ | 未 import engine/fins/service/ui |
| 无魔法数字散落 | ✅ | 校验通过命名 helper 函数；常量在模块级声明 |

## FollowupSnapshot 校验逻辑走查

`api.py:1243-1264` 校验逻辑：

1. `behavior=QUEUE` + `target_run_id is not None` → reject ✅
2. `behavior=QUEUE` + `accepted_run_status=QUEUED` + `queued_run_id != accepted_run_id` → reject ✅
3. `behavior=QUEUE` + `accepted_run_status=RUNNING` + `queued_run_id is not None` → reject ✅
4. `behavior=QUEUE` + `accepted_run_status` 不在 `{QUEUED, RUNNING}` → reject ✅
5. `behavior=STEER` → 无额外校验，符合 plan "steer 不要求 queued_run_id" ✅

running run id 无法被塞入 `queued_run_id`：case 3 明确拒绝。

## HostCommandHandleOptions 校验逻辑走查

`api.py:558-619` 校验覆盖：

- `_require_optional_non_empty`：可选 handle id 存在时非空
- `_require_path`：`pathlib.Path` 类型守卫
- `_require_bool`：`bool` 类型守卫（拒绝 int 混入）
- `_require_positive_float`：`bool` 守卫 + `> 0` 校验
- `_require_non_negative_int`：`bool` 守卫 + `>= 0` 校验
- `_require_positive_int`：`bool` 守卫 + `> 0` 校验

无魔法数字：所有阈值语义通过字段名表达，helper 函数复用已有 `_require_non_empty` / `_require_optional_non_empty` 模式。

## 非阻塞观察（不构成 finding）

1. `_require_positive_float` 接受 `int` 参数（Python numeric tower 行为），运行时正确，类型注解 `float` 仅作 hint。
2. `_require_non_negative`（旧 helper，用于 cursor/sequence）不含 `bool` 守卫；`_require_non_negative_int`（新 helper，用于配置值）含 `bool` 守卫。分离合理，旧 helper 不在本 slice 修改范围内。
3. `HostApiErrorDetail` 当前只有 `SteerConflictDetail` 一个成员，符合 plan "First version" 声明，后续 phase 扩展 union。
4. `HostCommandHandleOptions` 无默认值，所有字段必填。符合 P4-S1 "只冻结类型" 定位；factory 默认值映射属于 P4-S2。

## 结论

**accepted**

P4-S1 实现完整覆盖 approved plan 所有 slice 项目，符合项目全部硬约束。校验逻辑正确，测试覆盖 public contract，README 只写当前事实。无 blocking finding。
