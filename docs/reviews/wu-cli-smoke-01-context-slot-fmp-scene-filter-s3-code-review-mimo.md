# S3 Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `f244aca2`（workspace changes after this commit, including staged, unstaged, and untracked files）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-mimo.md`
- Included scope: All S3 implementation files（manifests、scenes、CLI、tests、utils、README）
- Excluded scope: S1/S2 committed changes、Host/Engine state machines、durable schema、Fins storage protocols
- Parallel review coverage: 无

## Review Context

- Plan: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-implementation-codex.md`

## Pre-review Validation

总控已复验，本次 review 独立验证：

```
tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py:  59 passed
tests/fins/test_fmp_company_info_resolver.py:                                                                                  8 passed
tests/service/test_entrypoint_runtime*.py + test_host_assembly.py:                                                           102 passed
tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py:                     91 passed
tests/runtime/test_smoke_host_public_multiturn_assembly.py:                                                                    7 passed
rg -n base_user dayu/config/prompts dayu/cli tests utils:                                                              no matches
pyright:                                                                                                            0 errors
git diff --check:                                                                                                       passed
```

全部 267 个测试通过，pyright 零报错，base_user 零残留。

## 审查重点验证

### 1. base_user 是否从 LLM-facing context slot、manifests、CLI/tests/utils 中彻底删除，且 display_user/HostCallContext 保留不误判

**Status: ✅ Verified**

**Evidence:**

1. **Manifests 已清理**：`rg -n "base_user" dayu/config/prompts` 返回零匹配。所有 12 个 manifests 的 `context_slots` 数组不再包含 `base_user`。

2. **CLI 已清理**：
   - `dayu/cli/commands/prompt.py`: `CONTEXT_SLOT_BASE_USER` 常量已删除，`_prompt_context_slot_values()` 不再追加 `base_user`
   - `dayu/cli/commands/interactive.py`: `_interactive_context_slot_values()` 返回空字典 `{}`
   - `dayu/cli/commands/session.py`: `_session_context_slot_values()` 调用 `build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=None))`，不包含 `base_user`

3. **Tests 已清理**：`rg -n "base_user" tests/` 返回零匹配。

4. **Utils 已清理**：`utils/smoke_host_public_multiturn.py` 不再追加 `base_user` context slot。

5. **display_user/HostCallContext 保留正确**：
   - `dayu/cli/commands/prompt.py:231`: `display_user=DEFAULT_BASE_USER`
   - `dayu/cli/commands/interactive.py:285`: `display_user=DEFAULT_BASE_USER`
   - `dayu/cli/commands/session.py:175`: `display_user=DEFAULT_BASE_USER`
   - `dayu/cli/host_context.py:79`: `display_user=display_user` 进入 `CliInvocation`，最终进入 `HostCallContext`

**Conclusion:** `base_user` 已从 LLM-facing context slot 彻底删除，但 `display_user` 作为 Host call context 的身份信息正确保留。两者职责分离清晰，未误判。

### 2. fins_default_subject contract 是否闭环：所有声明该 slot 的 manifest 对应 scene md 都渲染独立行 placeholder；interactive/wechat 不声明不渲染

**Status: ✅ Verified**

**Evidence:**

1. **声明 `fins_default_subject` 的 manifests (11个)**：
   - `rg -n "fins_default_subject" dayu/config/prompts/manifests --type json` 返回 11 个匹配：audit, confirm, decision, fix, infer, overview, prompt, regenerate, repair, smoke_host_public_multiturn, write

2. **渲染 `{{fins_default_subject}}` 的 scenes (11个)**：
   - `rg -n "fins_default_subject" dayu/config/prompts/scenes --type md` 返回 11 个匹配：audit, confirm, decision, fix, infer, overview, prompt, regenerate, repair, smoke_host_public_multiturn, write

3. **一一对应验证**：声明和渲染的 scene id 完全一致。

4. **interactive/wechat 不声明不渲染**：
   - `interactive.json`: `"context_slots": []`
   - `wechat.json`: `"context_slots": []`
   - `interactive.md`: 无 `{{fins_default_subject}}`
   - `wechat.md`: 无 `{{fins_default_subject}}`

5. **Standalone line 验证**：
   - `prompt.md:3`: `{{fins_default_subject}}` 独立一行
   - 其他 scenes 也在第3行独立一行

6. **Invariant 测试覆盖**：
   - `test_scene_assets_migration.py:297`: `test_fins_default_subject_slot_is_rendered_by_declaring_scenes` 验证声明的 scene 必须渲染，`_NO_DEFAULT_SUBJECT_SCENES` 中的 scene 必须不声明不渲染

**Conclusion:** fins_default_subject contract 闭环。所有声明该 slot 的 manifest 对应 scene md 都渲染独立行 placeholder；interactive/wechat 不声明不渲染。

### 3. current_time 是否没有被机械添加，prompt/interactive/wechat 继续通过 utils tag 选择真实 get_current_time，其它 scene 不误暴露工具

**Status: ✅ Verified**

**Evidence:**

1. **current_time 未被机械添加到 scene placeholders**：
   - `rg -n "current_time" dayu/config/prompts/scenes --type md` 返回零匹配
   - Scene fragments 不包含 `{{current_time}}` placeholder

2. **prompt/interactive/wechat 通过 utils tag 选择 get_current_time**：
   - `prompt.json`: `"tool_tags_any": ["fins-read", "web", "utils"]`
   - `interactive.json`: `"tool_tags_any": ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
   - `wechat.json`: `"tool_tags_any": ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`
   - `get_current_time` 工具的 tags 包含 `"utils"`（见 `test_scene_assets_migration.py:248`: `SceneToolInfo(name="get_current_time", tags=frozenset({"utils", "time"}))`）

3. **其它 scene 不误暴露 get_current_time**：
   - `infer.json`: `"tool_tags_any": ["fins-read", "web"]`（无 `utils`）
   - 测试验证：`test_scene_assets_migration.py:373`: `assert "get_current_time" not in selected`

4. **tools.md 条件块保护**：
   - `base/tools.md:90`: `<when_tool get_current_time>` 条件块包裹 `get_current_time` 工具说明
   - ScenePrepare 过滤后，未选中该工具的 scene 不会暴露其说明

**Conclusion:** current_time 没有被机械添加。prompt/interactive/wechat 通过 utils tag 选择真实 get_current_time，其它 scene 不误暴露工具。

### 4. README 更新是否符合各 README Agent 更新约束，不写未来态

**Status: ✅ Verified**

**Evidence:**

1. **`dayu/config/README.md`**：
   - 添加了 `<when_tag>` / `<when_tool>` 条件块 marker 的说明（当前代码已实现的 prompt asset 控制语法）
   - 添加了 `utils` tag 选择 `get_current_time` 工具的说明（当前代码已实现的事实）
   - 不写未来态，只记录当前配置行为

2. **`dayu/fins/README.md`**：
   - 更新了 `resolve_company_info` 的说明，包括第二跳失败包装（当前代码已实现的错误处理边界）
   - 符合 "Agent更新约束"：只写当前代码已实现的对外接口、公共契约

3. **`tests/README.md`**：
   - 更新了测试覆盖的说明，包括 scene condition filtering、FMP resolver coverage、slot builder coverage、aggregate old identity slot residue scan
   - 符合开头约束："本文件只记录当前 `tests/` 下已经存在的测试分层、运行方式与维护约定"

**Conclusion:** 所有 README updates 只记录当前代码已实现的事实，符合各 README 的约束，不写未来态。

### 5. utils/smoke_host_public_multiturn.py 中 preservation of fins_awaiting_runtime 是否正确、是否引入边界风险

**Status: ✅ Verified**

**Evidence:**

1. **Preservation 实现**：
   - `utils/smoke_host_public_multiturn.py:556`: `fins_awaiting_runtime=discovered.fins_awaiting_runtime`
   - 当追加内置 smoke tool 时，保留原始的 `discovered.fins_awaiting_runtime`

2. **正确性分析**：
   - Smoke tool 不是 Fins tool，不需要 Fins awaiting runtime
   - 原始的 `discovered.fins_awaiting_runtime` 可能包含真实的 Fins awaiting runtime（如果配置了 Fins providers）
   - 保留它可以确保 smoke 测试能够验证 Fins wait adapter registry 的正确注册

3. **边界风险分析**：
   - Smoke utility 只追加 tool definitions、source_refs 和 provider_reports
   - 不修改 `effective_provider_configs`（line 555）
   - 不修改 `fins_awaiting_runtime`（line 556）
   - 这确保了 Fins wait adapter registry 的完整性

4. **测试覆盖**：
   - `test_smoke_host_public_multiturn_assembly.py`: 7 个测试通过，验证了 Service assembly 路径的正确性

**Conclusion:** `fins_awaiting_runtime` 的 preservation 正确，未引入边界风险。Smoke utility 在追加内置 tool 时保留了原始的 Fins awaiting runtime，确保了 Fins wait adapter registry 的完整性。

### 6. 测试是否覆盖上述 invariant，是否存在为了旧测试堆兼容逻辑

**Status: ✅ Verified**

**Evidence:**

1. **Subject-slot invariant 测试**：
   - `test_scene_assets_migration.py:297`: `test_fins_default_subject_slot_is_rendered_by_declaring_scenes`
   - 验证声明 `fins_default_subject` 的 scene 必须渲染独立行 placeholder
   - 验证 `_NO_DEFAULT_SUBJECT_SCENES` 中的 scene 必须不声明不渲染

2. **Interactive context slot 测试**：
   - `test_entrypoint_runtime_interactive_path.py:225`: `test_interactive_runtime_uses_real_manifest_required_slots`
   - 验证 interactive scene 只要求并消费当前 manifest 所需 slots
   - 不再期望 `base_user` slot

3. **CLI context slot 生成测试**：
   - `test_prompt_command.py:990`: `assert "未指定具体公司" not in str(captured_requests[0].context_slot_values)`
   - 验证旧 placeholder text 不存在

4. **Negative assertions 正确**：
   - `test_entrypoint_runtime.py:204`: `assert "未指定具体公司" not in str(no_key_values[FINS_DEFAULT_SUBJECT_SLOT])`
   - 只验证旧文本不存在，不要求旧文本存在

5. **无兼容逻辑**：
   - `rg -n "base_user" tests/` 返回零匹配
   - 测试不再引用旧的 `base_user` context slot
   - 测试 expectations 已更新为新 boundary

**Conclusion:** 测试覆盖了所有关键 invariant，不存在为了旧测试堆兼容逻辑的情况。测试 expectations 已正确更新为新 boundary。

## New Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

1. **Real provider smoke 未执行**：所有 FMP HTTP 调用均通过 fake HTTP client 模拟，未验证真实 FMP API 的响应格式兼容性。分类为 optional later validation。

2. **Prompt assets 不消费 `current_time` placeholder**：`build_entrypoint_context_slot_values` 仍然生成 `current_time` slot，但 prompt assets 不消费该 placeholder（因为 prompt/interactive/wechat 使用真实 `get_current_time` 工具）。这是 S3 设计选择，通过 manifest tool selection tests 覆盖。

## Conclusion

**Pass**

所有审查重点均通过验证：

1. ✅ `base_user` 已从 LLM-facing context slot 彻底删除，`display_user`/HostCallContext 正确保留
2. ✅ `fins_default_subject` contract 闭环，manifest 和 scene 一一对应，interactive/wechat 不声明不渲染
3. ✅ `current_time` 没有被机械添加，prompt/interactive/wechat 通过 utils tag 选择真实 `get_current_time`
4. ✅ README updates 符合各 README Agent 更新约束，不写未来态
5. ✅ `fins_awaiting_runtime` preservation 正确，未引入边界风险
6. ✅ 测试覆盖所有 invariant，无兼容逻辑

未发现新 blockers。S3 implementation 完整且正确。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-mimo.md`
- **Conclusion**: Pass
- **New blockers**: 0
- **Residual risks**: 2（real provider smoke 未执行、`current_time` placeholder 未消费）
