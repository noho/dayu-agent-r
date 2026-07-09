# S3 Targeted Re-Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: S3 code review 通过后的 workspace changes（DS F1 命名 finding 返工）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-rereview-mimo.md`
- Included scope: DS F1 命名 finding 相关的重命名改动
- Excluded scope: 其他 S3 改动（已在 S3 code review 中验证）
- Parallel review coverage: 无

## Review Context

- DS S3 review artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-ds.md`
- MiMo S3 review artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-mimo.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-implementation-codex.md`

## Pre-review Validation

总控窄复验已通过，本次 review 独立验证：

```
tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py:  91 passed
tests/runtime/test_smoke_host_public_multiturn_assembly.py:                                                  7 passed
pyright:                                                                                              0 errors
git diff --check:                                                                                         passed
```

## 审查重点验证

### 1. DEFAULT_BASE_USER 是否已重命名为 DEFAULT_DISPLAY_USER，行为不变，只用于 display_user/HostCallContext

**Status: ✅ Verified**

**Evidence:**

1. **重命名完成**：
   - `dayu/cli/commands/prompt.py:83`: `DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"`
   - `dayu/cli/commands/interactive.py:89`: `DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"`
   - `dayu/cli/commands/session.py:83`: `DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"`

2. **行为不变**：
   - 值仍为 `"本地 CLI 用户"`
   - 只用于 `display_user=DEFAULT_DISPLAY_USER`（prompt.py:231, interactive.py:285, session.py:175）
   - `display_user` 进入 `CliInvocation`，最终进入 `HostCallContext`，不进入 LLM context slots

3. **旧常量名零残留**：
   - `rg -n "DEFAULT_BASE_USER" dayu/ tests/ utils/ --type py` 返回零匹配

**Conclusion:** `DEFAULT_BASE_USER` 已正确重命名为 `DEFAULT_DISPLAY_USER`，行为不变，只用于 `display_user`/`HostCallContext`。

### 2. utils/smoke_host_public_multiturn.py 的 _DEFAULT_USER 是否已重命名为 _DEFAULT_ACTOR 或等价非 slot 语义，行为不变

**Status: ✅ Verified**

**Evidence:**

1. **重命名完成**：
   - `utils/smoke_host_public_multiturn.py:104`: `_DEFAULT_ACTOR: Final[str] = "manual-smoke-operator"`

2. **行为不变**：
   - 值仍为 `"manual-smoke-operator"`
   - 只用于 `actor=_DEFAULT_ACTOR`（line 677）
   - `actor` 是 `HostCallContext` 的字段，不进入 LLM context slots

3. **旧常量名零残留**：
   - `rg -n "_DEFAULT_USER" utils/smoke_host_public_multiturn.py` 返回零匹配

4. **其他文件的类似常量不在范围内**：
   - `utils/smoke_host_public_conversation_memory.py:113`: `_DEFAULT_USER_ID: Final[str] = "manual-smoke-user"`（不同常量，不在 DS F1 范围）
   - `utils/diagnose_web_access.py:70`: `_DEFAULT_USER_AGENT`（不同语义，不在 DS F1 范围）

**Conclusion:** `_DEFAULT_USER` 已正确重命名为 `_DEFAULT_ACTOR`，行为不变，只用于 `HostCallContext.actor`。

### 3. 源码范围 dayu/config/prompts dayu/cli tests utils 是否无 BASE_USER/base_user 源码残留

**Status: ✅ Verified**

**Evidence:**

1. **全面扫描**：
   - `rg -n "BASE_USER|base_user" dayu/config/prompts dayu/cli tests utils --type py --type json --type md` 返回零匹配

2. **分类验证**：
   - `dayu/config/prompts/`: manifests 和 scenes 无残留
   - `dayu/cli/`: 三个 CLI command 无残留
   - `tests/`: 所有测试文件无残留
   - `utils/`: smoke utilities 无残留

3. **pyc 缓存不作为代码问题**：
   - pyc 缓存是 Python 运行时产物，不影响源码正确性
   - 源码已正确清理，pyc 缓存会在下次运行时自动更新

**Conclusion:** 源码范围 `dayu/config/prompts dayu/cli tests utils` 无 `BASE_USER`/`base_user` 残留。

### 4. 是否引入任何新问题

**Status: ✅ Verified**

**Evidence:**

1. **测试全部通过**：
   - CLI tests: 91 passed
   - Smoke assembly tests: 7 passed
   - pyright: 0 errors
   - git diff --check: passed

2. **重命名是纯符号重命名**：
   - 常量值不变
   - 使用位置不变
   - 语义不变（从 `base_user` 改为 `display_user` 更准确地描述了其用途）

3. **无新增 import 或依赖**：
   - 重命名不引入新的模块依赖
   - 不改变模块边界

4. **无新增测试需求**：
   - 重命名是内部实现细节
   - 现有测试已覆盖相关行为
   - 不需要新增测试用例

**Conclusion:** 未引入任何新问题。

## New Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。DS F1 命名 finding 的返工是纯符号重命名，不改变行为，不引入新风险。

## Conclusion

**Pass**

所有审查重点均通过验证：

1. ✅ `DEFAULT_BASE_USER` 已重命名为 `DEFAULT_DISPLAY_USER`，行为不变，只用于 `display_user`/`HostCallContext`
2. ✅ `_DEFAULT_USER` 已重命名为 `_DEFAULT_ACTOR`，行为不变，只用于 `HostCallContext.actor`
3. ✅ 源码范围 `dayu/config/prompts dayu/cli tests utils` 无 `BASE_USER`/`base_user` 残留
4. ✅ 未引入任何新问题

DS F1 命名 finding 的返工完成，可以进入下一步。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-rereview-mimo.md`
- **Conclusion**: Pass
- **New blockers**: 0
- **Residual risks**: 无
