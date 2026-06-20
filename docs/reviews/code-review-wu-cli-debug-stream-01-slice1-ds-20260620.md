# WU-CLI-DEBUG-STREAM-01 Slice 1 Code Review

**Review date:** 2026-06-20
**Reviewer:** Claude (deepreview)
**Work unit:** WU-CLI-DEBUG-STREAM-01
**Slice:** 1 — Runtime log level + CLI `--debug-stream` plumbing
**Plan artifact:** `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
**Implementation artifact:** `docs/reviews/implementation-wu-cli-debug-stream-01-slice1-20260620.md`

## Review Scope

仅审查 Slice 1 变更（8 个文件），不审查未修改的 Host/Engine ingest、runner、SSE parser（Slice 2 范围），不审查 README（Slice 4 范围）。

## Summary

Slice 1 实现与 plan 对齐良好。核心正确性：`STREAM_DEBUG_LOG_LEVEL = 9` 低于 stdlib `DEBUG = 10`，stdlib logging 的阈值语义保证 DEBUG 抑制 STREAM_DEBUG 而 STREAM_DEBUG 同时放出二者；`_resolve_level` 中 `debug_stream` 优先于所有其他 flag；CLI `--debug-stream` parser/default/help 正确；`main()` 的初始装配和 cleanup 装配均传递 `debug_stream` 参数。

发现 1 个 Medium 级问题（类型注释遗漏），4 个 Low 级问题（测试覆盖边界），无 High/Critical 级问题。无 Host/Engine 迁移泄漏。无 README 泄漏。无 `Any`/`object`/缺失 docstring 回归。

## Findings

### Finding 1 [Medium] — `main()` 局部变量 `debug_stream_for_cleanup` 缺少类型注释

**File:** `dayu/cli/main.py:83`
**Evidence:**

```python
# line 81-83
opened_log_stream: TextIO | None = None
log_level_for_cleanup: str | None = None
debug_stream_for_cleanup = False          # ← 无类型注释
```

相邻的两个局部变量均有显式类型注释（`: TextIO | None`、`: str | None`），新增变量 `debug_stream_for_cleanup` 却省略了。虽然 pyright 能从字面量 `False` 推断出 `bool`，但违反项目中已有局部变量的显式注释惯例，且与同组变量风格不一致。

**建议:** 补为 `debug_stream_for_cleanup: bool = False`。

**Severity justification:** 不影响正确性，pyright 不报错；但属 AGENTS.md "禁止无类型参数" 精神在局部变量层面的延伸——项目在 `main()` 中所有状态变量均显式标注，新变量不应降低一致性。

---

### Finding 2 [Low] — 缺少 `set_level_from_flags(log_level=None, debug_stream=True)` 独立路径的显式测试

**File:** `tests/runtime/test_log.py`
**Evidence:**

`test_set_level_from_flags_debug_stream_beats_log_level_str` 使用 `log_level="info"` 配合 `debug_stream=True` 验证优先级；`test_set_level_from_flags_debug_stream_beats_debug_log_level_str` 使用 `log_level="debug"`。但无一测试覆盖 `log_level=None` 且仅有 `debug_stream=True`（所有其他 boolean flag 为 `False`）的路径。

`_resolve_level` 实现正确（`debug_stream` 第一条即返回），此路径不会出错，但 plan 期望的语义是 `--debug-stream` 单独使用时也解析为 `STREAM_DEBUG`，缺少显式断言使得未来重构可能意外改变此行为。

**建议:** 增加一个 case：`set_level_from_flags(log_level=None, debug=False, verbose=False, info=False, quiet=False, debug_stream=True) is LogLevel.STREAM_DEBUG`。

**Severity justification:** 实现正确，仅测试覆盖边界遗漏；不影响 Slice 1 正确性。

---

### Finding 3 [Low] — 缺少 `--debug-stream --quiet` 组合在 runtime 层的显式测试

**File:** `tests/cli/test_arg_parsing.py`, `tests/runtime/test_log.py`
**Evidence:**

`test_main_configures_runtime_log_from_parsed_cli_flags` 的 parametrize 覆盖了 `--debug-stream` 单独使用、`--debug` 单独使用等组合，但未覆盖 `--debug-stream` 与 `--quiet` 同时出现。

`_resolve_level` 中 `debug_stream` 优先于 `quiet`，因此组合结果为 `STREAM_DEBUG`。实现正确，但 plan 明确提到"Users should not combine mutually contradictory log-level flags"，建议至少有一个测试锁定此行为（即矛盾组合时 `debug_stream` 胜出），防止未来有人"修正"这个行为。

**建议:** 在 `test_main_configures_runtime_log_from_parsed_cli_flags` 的 parametrize 或单独 case 中增加 `(("prompt", "hello", "--debug-stream", "--quiet"), "error", True)` 并配合 runtime 断言验证最终 level 为 `STREAM_DEBUG`。

**Severity justification:** 实现正确，仅防御性测试缺失。

---

### Finding 4 [Low] — `_resolve_level` 错误消息列出 `STREAM_DEBUG` 但非 `--log-level` 合法选项

**File:** `dayu/runtime/log.py:247-250`
**Evidence:**

```python
raise ValueError(
    f"unknown log_level: {log_level!r}; expected one of "
    f"{[member.name for member in LogLevel]}"
) from exc
```

`LogLevel` 枚举新增 `STREAM_DEBUG` 后，此错误消息会列出 `STREAM_DEBUG` 作为合法 `log_level` 字符串。对直接调用 `set_level_from_flags` 的程序而言是正确的（`log_level="stream_debug"` 确实可解析）；但若 CLI 用户通过某种路径看到此消息，会看到 argparse `--log-level` 不接受的值。

此问题有双重缓解：(1) argparse 的 `choices=LOG_LEVEL_CHOICES` 会先拦截非法值；(2) `_resolve_level` 是私有函数。但 `LOG_LEVEL_CHOICES` 本身也有预存的 `critical` 不在列表中却在 `LogLevel` 枚举中的不一致。

**建议:** 可接受的现状。若未来需要收敛，可在 `_resolve_level` 的 `ValueError` 中区分"程序化调用合法但 CLI 不可用"的 level 名，或统一 `LOG_LEVEL_CHOICES` 与 `LogLevel` 的命名空间。不阻塞本 Slice。

**Severity justification:** 预存不一致的轻微放大，无实际用户影响。

---

### Finding 5 [Low] — `log_levels.py` 模块 docstring 未更新提及新增常量

**File:** `dayu/runtime/log_levels.py:1-7`
**Evidence:**

模块 docstring 第 2-4 行：

```python
"""Dayu 层中立日志 level 整数常量真源。

本模块只承载多层共享的 stdlib logging level 整数值与 Dayu 自定义
``VERBOSE`` 级别整数值，不注册 level name、不安装 handler、不读取配置。
```

新增 `STREAM_DEBUG_LOG_LEVEL` 后，"Dayu 自定义 ``VERBOSE`` 级别" 应更新为 "Dayu 自定义 ``VERBOSE`` 与 ``STREAM_DEBUG`` 级别"，以保持 docstring 与 `__all__` 内容一致。

**建议:** 将 "Dayu 自定义 ``VERBOSE`` 级别整数值" 改为 "Dayu 自定义 ``VERBOSE`` 与 ``STREAM_DEBUG`` 级别整数值"。

**Severity justification:** 文档滞后，不影响功能。

---

## Correctness Verification

### Property 1: `STREAM_DEBUG_LOG_LEVEL` 正确性

`STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1 = 9`（`log_levels.py:15`）。stdlib logging 的阈值为 `>=`，因此：

- Logger level = `DEBUG (10)` → 只接受 `level >= 10` 的记录 → `STREAM_DEBUG (9)` 被抑制。✅
- Logger level = `STREAM_DEBUG (9)` → 接受 `level >= 9` 的记录 → 同时通过 `STREAM_DEBUG (9)` 和 `DEBUG (10)`。✅

验证测试：`test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both`（`test_log.py:416`）。

### Property 2: `debug_stream` 优先级

`_resolve_level`（`log.py:240`）第一条即检查 `debug_stream`，早于 `log_level`、`quiet`、`debug`、`verbose`、`info`。✅

验证测试：`test_set_level_from_flags_debug_stream_beats_log_level_str`（`test_log.py:141`）、`test_set_level_from_flags_debug_stream_beats_debug_log_level_str`（`test_log.py:155`）。

### Property 3: CLI parsing

`--debug-stream` 使用 `action="store_true"`，`dest="debug_stream"`，`default=argparse.SUPPRESS`（`arg_parsing.py:349-358`）。`_new_default_namespace` 设置 `namespace.debug_stream = False`（`arg_parsing.py:250`）。因此：

- 不提供 flag → `debug_stream=False`。✅
- 提供 flag → `debug_stream=True`。✅
- 与 `--debug` 组合 → `debug_stream=True` + `log_level="debug"`。✅

验证测试：`test_parse_cli_args_accepts_debug_stream`（`test_arg_parsing.py:1015`）、`test_parse_cli_args_accepts_debug_and_debug_stream_combination`（`test_arg_parsing.py:1024`）。

### Property 4: `main()` cleanup propagation

初始化调用（`main.py:98-106`）和 cleanup 调用（`main.py:120-128`）均传入 `debug_stream=args.debug_stream` 或 `debug_stream=debug_stream_for_cleanup`。✅

验证测试：`test_main_configures_runtime_log_from_parsed_cli_flags`（`test_arg_parsing.py:414`）断言两次调用均携带正确的 `debug_stream` 值。

### Property 5: stdlib registration

`log.py:75-76` 在模块导入时注册 `STREAM_DEBUG` 和 `VERBOSE`。`test_log_level_stream_debug_registered_with_stdlib`（`test_log.py:217`）验证 `getLevelName(9) == "STREAM_DEBUG"`。`test_importing_log_levels_does_not_register_stdlib_level`（`test_log_levels.py:59`）通过子进程隔离验证只导入 `log_levels` 不注册 level name。✅

### Property 6: No Slice boundary breach

检查全部 8 个文件：

- `dayu/runtime/log_levels.py` — 仅新增常量。✅
- `dayu/runtime/log.py` — 仅新增 level name 注册 + `LogLevel` 枚举成员 + `debug_stream` 参数。✅
- `dayu/cli/arg_parsing.py` — 仅新增 `ParsedCliArgs.debug_stream` + `--debug-stream` argument。✅
- `dayu/cli/main.py` — 仅传递 `debug_stream` 参数。✅
- 测试文件 — 仅测试 Slice 1 范围。✅

未修改 Host/Engine ingest、runner、SSE parser。✅
未修改 README。✅

## AGENTS.md 合规检查

| 规则 | 状态 | 备注 |
|------|------|------|
| 完整中文 docstring | ✅ | 所有新增/修改函数均有完整中文 docstring |
| 无 `object`/`Any`/无类型参数 | ✅ 除 Finding 1 | `debug_stream_for_cleanup` 局部变量缺类型注释（Medium） |
| 无 `hasattr`/`getattr` 滥用 | ✅ | 预存的 marker handler 模式使用 `setattr`/`getattr`，有明确定义理由 |
| 无魔法数字/字符串 | ✅ | `STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1` 是计算值，非魔法数字 |
| 模块级私有辅助函数优先 | ✅ | `_resolve_level` 是私有辅助函数 |
| 禁止兼容性代码 | ✅ | 无 re-export、wrapper、兼容常量 |

## 测试覆盖评估

| Plan 要求 | 测试 | 状态 |
|-----------|------|------|
| `parse_cli_args(("prompt", "x", "--debug-stream")).debug_stream is True` | `test_parse_cli_args_accepts_debug_stream` | ✅ |
| `--debug` + `--debug-stream` 组合 | `test_parse_cli_args_accepts_debug_and_debug_stream_combination` | ✅ |
| 全局 help 含 `--debug-stream` | `test_global_help_contains_debug_stream` | ✅ |
| 命令 help 含 `--debug-stream` | `test_command_help_contains_debug_stream` | ✅ |
| `main()` 两次装配均传 `debug_stream` | `test_main_configures_runtime_log_from_parsed_cli_flags` | ✅ |
| `log_level="info" + debug_stream=True → STREAM_DEBUG` | `test_set_level_from_flags_debug_stream_beats_log_level_str` | ✅ |
| `log_level="debug" + debug_stream=True → STREAM_DEBUG` | `test_set_level_from_flags_debug_stream_beats_debug_log_level_str` | ✅ |
| DEBUG 抑制 STREAM_DEBUG 记录 | `test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both` | ✅ |
| STREAM_DEBUG 同时放出两者 | `test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both` | ✅ |
| `log_level=None + debug_stream=True` 独立路径 | 缺失 | Finding 2 |
| `--debug-stream --quiet` runtime 解析 | 缺失 | Finding 3 |

## Residual Risks

1. **Slice 2 迁移风险（已知，不在本 Slice 范围）：** Host ingest delta、OpenAI runner heartbeat、SSE done-token 仍使用 `DEBUG` level。Slice 2 迁移时需小心保持 `_engine_ingest_log_level()` 的非 delta 事件仍为 `VERBOSE`。

2. **`LOG_LEVEL_CHOICES` 与 `LogLevel` 不一致（预存）：** `critical` 和 `stream_debug` 均在 `LogLevel` 枚举中但不在 `LOG_LEVEL_CHOICES` 中。`_resolve_level` 错误消息可能误导直接调用方。本 Slice 轻微放大了此不一致。

3. **`--debug-stream` 与矛盾 flag 组合（已文档化）：** 实现始终让 `debug_stream` 胜出，符合 plan。README（Slice 4）应明确此行为。

4. **`STREAM_DEBUG_LOG_LEVEL = 9` 对 Python 版本假设：** 依赖 `logging.DEBUG == 10`。此值自 Python 2.3 起未变，风险极低。

## Validation Reproduction

实现者报告的验证命令：

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q
# Reported: 88 passed, 3 warnings

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# Reported: 0 errors, 0 warnings, 0 informations

git diff --check
# Reported: passed
```

Reviewer 未重新执行验证（遵循 Slice 1 不修改文件约束）。验证结果与代码审查结论一致。

## Adjudication

| Finding | Severity | Recommendation | Expected Adjudication |
|---------|----------|----------------|----------------------|
| 1: `debug_stream_for_cleanup` 缺类型注释 | Medium | 补为 `: bool` | Accept |
| 2: 缺少 `log_level=None + debug_stream=True` 测试 | Low | 补充 case | Accept 或 Defer（Slice 2 前补） |
| 3: 缺少 `--debug-stream --quiet` runtime 测试 | Low | 补充 case | Accept 或 Defer（Slice 2 前补） |
| 4: `_resolve_level` 错误消息列出 `STREAM_DEBUG` | Low | 可接受现状 | Accept（不阻塞） |
| 5: `log_levels.py` docstring 未更新 | Low | 更新 docstring | Accept |

## Conclusion

Slice 1 实现正确、测试覆盖良好的核心路径、无 Slice 边界泄漏、无架构回归。1 个 Medium + 4 个 Low finding 均可在后续 Slice 或本 Slice 修复轮次中低成本解决。**建议接受 Slice 1，修复 Finding 1 即可进入 Slice 2。**
