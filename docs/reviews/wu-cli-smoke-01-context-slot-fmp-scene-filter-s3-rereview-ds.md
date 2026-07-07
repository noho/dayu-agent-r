# Code Re-Review (S3 Naming Fix Verification)

## Metadata

- **Reviewer**: AgentDS (S3 targeted re-review)
- **Work unit**: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up, Slice S3
- **Review target**: workspace changes after S3 DS F1 naming fix (AgentCodex rework)
- **Original S3 review**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-ds.md`
- **Accepted finding**: DS F1 — `DEFAULT_BASE_USER` 常量名携带已删除 slot 的历史语义
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes（targeted re-review）
- **Base**: S3 workspace state（`f244aca2` 之后的未提交改动）
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-rereview-ds.md`
- **Included scope**: 仅验证 DS F1 命名修复的 4 个文件，以及全量 `BASE_USER`/`base_user` 源码残留扫描
- **Excluded scope**: S3 其它 36 个文件（已在初始 S3 review 中通过，本次 fix 未触及）
- **Parallel review coverage**: 无；单 reviewer 逐条验证

## Controller-Accepted Finding: Fix Verification

### DS F1: `DEFAULT_BASE_USER` 常量名携带已删除 slot 的历史语义

**Status: ✅ 已修复**

#### 子项 1: `DEFAULT_BASE_USER` → `DEFAULT_DISPLAY_USER`

三处 CLI 入口的常量均已重命名，行为不变：

| 文件 | 行号 | 旧名 | 新名 |
|---|---|---|---|
| `dayu/cli/commands/prompt.py` | 83 | `DEFAULT_BASE_USER` | `DEFAULT_DISPLAY_USER` |
| `dayu/cli/commands/prompt.py` | 231 | `display_user=DEFAULT_BASE_USER` | `display_user=DEFAULT_DISPLAY_USER` |
| `dayu/cli/commands/interactive.py` | 89 | `DEFAULT_BASE_USER` | `DEFAULT_DISPLAY_USER` |
| `dayu/cli/commands/interactive.py` | 285 | `display_user=DEFAULT_BASE_USER` | `display_user=DEFAULT_DISPLAY_USER` |
| `dayu/cli/commands/session.py` | 83 | `DEFAULT_BASE_USER` | `DEFAULT_DISPLAY_USER` |
| `dayu/cli/commands/session.py` | 175 | `display_user=DEFAULT_BASE_USER` | `display_user=DEFAULT_DISPLAY_USER` |

数据流验证：
```
DEFAULT_DISPLAY_USER ("本地 CLI 用户")
  → new_cli_invocation(display_user=...)
    → CliInvocation.display_user
      → HostCallContext.actor
        （Host 操作审计身份，不进入 LLM context slot）
```

值不变（`"本地 CLI 用户"`），调用点不变，数据流终点不变（`HostCallContext.actor`）。零泄漏进入 `context_slot_values`。

#### 子项 2: `_DEFAULT_USER` → `_DEFAULT_ACTOR`

| 文件 | 行号 | 旧名 | 新名 |
|---|---|---|---|
| `utils/smoke_host_public_multiturn.py` | 104 | `_DEFAULT_USER` | `_DEFAULT_ACTOR` |
| `utils/smoke_host_public_multiturn.py` | 677 | `actor=_DEFAULT_USER` | `actor=_DEFAULT_ACTOR` |

数据流验证：
```
_DEFAULT_ACTOR ("manual-smoke-operator")
  → _host_context()
    → HostCallContext(actor=...)
      （Host 操作审计身份，不进入 LLM context slot）
```

值不变（`"manual-smoke-operator"`），唯一调用点已同步更新。与 `context_slot_values`（仅有 `"fins_default_subject"`）完全分离。

#### 子项 3: `BASE_USER`/`base_user` 源码残留扫描

使用 `/usr/bin/grep -rn "BASE_USER\|base_user"`（绕过项目 grep wrapper）扫描全部四个目录的源码文件（排除 `.pyc`）：

| 目录 | 结果 |
|---|---|
| `dayu/config/prompts/` | 零匹配 |
| `dayu/cli/` (.py 源文件) | 零匹配 |
| `tests/` (.py 源文件) | 零匹配 |
| `utils/` (.py 源文件) | 零匹配 |

旧编译缓存 `__pycache__/*.pyc` 中仍含 `DEFAULT_BASE_USER` 字符串（S2 编译残留），不影响运行时——Python 按 `.py` 源文件时间戳决定是否重编译。

#### 子项 4: 是否引入新问题

对抗性验证：

- **`DEFAULT_DISPLAY_USER` 是否在任何地方被误用作 context slot?** 否。三处使用点均为 `display_user=DEFAULT_DISPLAY_USER`，仅流向 `new_cli_invocation` → `HostCallContext.actor`。`/usr/bin/grep -rn "DEFAULT_DISPLAY_USER" tests/` 零匹配，测试不依赖内部常量名。
- **`_DEFAULT_ACTOR` 是否在任何地方被误用作 context slot?** 否。仅用于 `HostCallContext(actor=_DEFAULT_ACTOR)`。tests 零引用。
- **重命名是否影响 `dayu/cli/host_context.py` 中的 `CliInvocation` 或 `new_cli_invocation`?** 否。这些函数接收参数名为 `display_user: str`，调用方传入什么常量名无影响。
- **重命名是否影响任何 `__all__` 导出或 public API?** 否。`DEFAULT_DISPLAY_USER` 和 `_DEFAULT_ACTOR` 均为模块级私有常量（`_DEFAULT_ACTOR` 有下划线前缀，`DEFAULT_DISPLAY_USER` 未出现在任何 `__all__` 中）。
- **是否有遗漏的旧名引用?** `/usr/bin/grep` 确认零 `BASE_USER`/`base_user` 源码残留。

**无新问题引入。**

## Validation

```
tests/cli/test_{prompt,interactive,session}_command.py:              91 passed
tests/runtime/test_smoke_host_public_multiturn_assembly.py:           7 passed
pyright:                                                              0 errors, 0 warnings
git diff --check:                                                    passed
```

## Findings

未发现实质性问题。

DS F1 命名 finding 已正确修复：`DEFAULT_BASE_USER` → `DEFAULT_DISPLAY_USER`（3 文件 6 处），`_DEFAULT_USER` → `_DEFAULT_ACTOR`（1 文件 2 处）。行为不变，数据流不变，零 `BASE_USER`/`base_user` 源码残留，无新问题引入。

## Open Questions

无。

## Residual Risk

无新增 residual risk。原有 S3 residual risks（`__pycache__` 旧编译缓存、invariant 测试反向缺口、FMP 真实 smoke）不受本次 fix 影响。

## Conclusion

**Pass** — 0 findings。DS F1 命名修复已验证通过。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-rereview-ds.md`
- **Conclusion**: Pass
- **Accepted findings fixed**: 1/1
  - DS F1: `DEFAULT_BASE_USER` → `DEFAULT_DISPLAY_USER` + `_DEFAULT_USER` → `_DEFAULT_ACTOR` ✅
- **Unresolved accepted findings**: 无
- **New blockers**: 无
- **New residual risks**: 无
