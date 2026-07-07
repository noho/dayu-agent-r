# Code Review

## Metadata

- **Reviewer**: AgentDS (S3 independent code review)
- **Work unit**: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up, Slice S3
- **Review target**: workspace changes since commit `f244aca2` (uncommitted S3 changes)
- **Plan**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Implementation artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-implementation-codex.md`
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes
- **Base**: `f244aca2`（S2 终点 commit，S3 为未提交改动）
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-ds.md`
- **Included scope**: 40 个文件，涵盖 12 个 manifest、11 个 scene `.md`、3 个 CLI command、1 个 smoke utility、7 个测试文件、3 个 README
- **Excluded scope**: S1/S2 已提交文件、Host/Engine 内部状态机、Durable schema、Fins storage protocols、`soul.md`（经核实无需修改）
- **Parallel review coverage**: 4 个 Explore subagent 并行覆盖：
  - base_user 残留扫描（CLI / manifests / tests / utils）
  - fins_default_subject contract 闭环（manifest ↔ scene `.md`）
  - current_time 工具暴露正确性（manifest tool_tags_any / context_slots）
  - smoke utility 边界与 fins_awaiting_runtime 保留
  - 测试覆盖 invariant（1 个主 agent 覆盖）
  - 未覆盖区域：无；所有 6 个重点审查领域均已覆盖

## Pre-review Validation

```
tests/runtime/test_scene_prepare.py + test_scene_tool_selection.py + test_scene_assets_migration.py:  59 passed
tests/fins/test_fmp_company_info_resolver.py:                                                          8 passed
tests/service/test_entrypoint_runtime*.py + test_host_assembly.py:                                    102 passed
tests/cli/test_{prompt,interactive,session}_command.py:                                                91 passed
tests/runtime/test_smoke_host_public_multiturn_assembly.py:                                             7 passed
tests/service/test_import_boundary.py + test_weak_typing_guard.py:                                      2 passed
---------------------------------------------------------------------------------------------------------------
Total:                                                                                               269 passed
pyright:                                                                                               0 errors, 0 warnings
git diff --check:                                                                                     passed
```

Warnings 均为已有 `edgar` deprecation warning，与本次变更无关。

## Findings

### F1-Nonblocking-Low: `DEFAULT_BASE_USER` 常量名携带已删除 slot 的历史语义

- **入口/函数**: `dayu/cli/commands/prompt.py` / `interactive.py` / `session.py` 模块级常量
- **文件(行号)**: `prompt.py:83`, `interactive.py:89`, `session.py:83`
- **输入场景**: 无运行时触发；纯命名问题
- **实际分支**: `DEFAULT_BASE_USER` 常量仅用于 `new_cli_invocation(display_user=DEFAULT_BASE_USER, ...)` — 即 Host 层 `HostCallContext.actor` 的默认值，不是 LLM context slot
- **预期行为**: 常量名应反映其唯一用途（Host display_user 默认值），不携带已删除 slot 名称 `BASE_USER`
- **实际行为**: 常量名 `DEFAULT_BASE_USER` 包含 `BASE_USER` 子串，该名称是已删除的 `"base_user"` context slot 的大写形式。虽然 `display_user` 语义正确（plan 明确允许保留），但常量名会让未来维护者误以为该值仍与某个 `base_user` slot 有关
- **直接证据**:
  - `prompt.py:83`: `DEFAULT_BASE_USER: Final[str] = "本地 CLI 用户"`
  - `prompt.py:231`: `display_user=DEFAULT_BASE_USER,` — 唯一使用点
  - `CONTEXT_SLOT_BASE_USER` 已在 S3 中删除（`prompt.py` diff 确认），但 `DEFAULT_BASE_USER` 未同步改名
  - plan 原文："`display_user="本地 CLI 用户"` 可保留用于 Host call context，但不得进入 LLM slot" — 允许保留值，未强制改名
- **影响**: 维护者可能误将 `DEFAULT_BASE_USER` 重新引入 context slot。当前无运行时影响
- **建议改法和验证点**: 重命名为 `DEFAULT_DISPLAY_USER` 或直接在三处调用点内联字符串 `"本地 CLI 用户"`；`/usr/bin/grep -rn "BASE_USER" dayu/cli/` 确认零残留
- **修复风险（低）**: 纯重命名，不改变运行时行为
- **严重程度（低）**: 命名问题，不影响正确性；plan 未强制改名

## Review Area 1: base_user 从 LLM-facing 层彻底删除

### 1.1 Context slot 名 `"base_user"` 残留扫描

使用 `/usr/bin/grep -rn "base_user"`（注意：项目配置的 `grep` wrapper 存在漏报，见 Open Questions）扫描全部 S3 范围：

| 范围 | 结果 | 证据 |
|---|---|---|
| `dayu/config/prompts/` | 零匹配 | 16 个 manifest 的 `context_slots` 均不含 `base_user` |
| `dayu/cli/` (源文件) | 零匹配 | `CONTEXT_SLOT_BASE_USER` 已删除，`DEFAULT_BASE_USER` 是大写 Python 标识符不是字面量 `base_user` |
| `tests/` (源文件) | 零匹配 | 所有测试 fixture 不再引用 `base_user` slot |
| `utils/` | 零匹配 | `smoke_host_public_multiturn.py` 已删除 `--base-user` 参数和 `context_slot_values["base_user"]` |
| `__pycache__/*.pyc` | 仅旧编译缓存匹配 | 不影响运行时行为；`.pyc` 是 S2 编译残留 |

### 1.2 CLI context_slot_values 构造验证

| CLI 入口 | context_slot_values 内容 | base_user 残留 |
|---|---|---|
| `prompt.py:_prompt_context_slot_values` | `build_entrypoint_context_slot_values(...)` → `{fins_default_subject, current_time}` | 无 |
| `interactive.py:_interactive_context_slot_values` | `{}` | 无 |
| `session.py:_session_context_slot_values` | `build_entrypoint_context_slot_values(ticker=None)` → `{fins_default_subject, current_time}` | 无 |

三者均不再向 LLM context slot 注入任何用户身份标识。

### 1.3 display_user / HostCallContext 保留

`display_user` 在 `dayu/cli/host_context.py` 中作为 `CliInvocation` 字段保留，由 `new_cli_invocation(display_user=DEFAULT_BASE_USER, ...)` 在三处 CLI 入口传入。该值进入 `HostCallContext.actor`（Host 操作审计身份），不进入 `context_slot_values`。与 plan 一致。

**结论：通过。** `base_user` 字面量从 LLM-facing context slot、manifests、CLI context_slot_values 构造、测试 fixture 中彻底删除。`display_user` 正确保留在 Host 层。

## Review Area 2: fins_default_subject contract 闭环

### 2.1 Manifest 声明 → Scene `.md` 渲染映射

| Manifest | Scene `.md` | 渲染 `{{fins_default_subject}}`? | 格式 |
|---|---|---|---|
| audit.json | audit.md | ✅ (line 3, 独立行) | 正确 |
| confirm.json | confirm.md | ✅ (line 3, 独立行) | 正确 |
| decision.json | decision.md | ✅ (line 3, 独立行) | 正确 |
| fix.json | fix.md | ✅ (line 3, 独立行) | 正确 |
| infer.json | infer.md | ✅ (line 3, 独立行) | 正确 |
| overview.json | overview.md | ✅ (line 3, 独立行) | 正确 |
| prompt.json | prompt.md | ✅ (line 3, 独立行, 无前导空格) | 正确 |
| regenerate.json | regenerate.md | ✅ (line 3, 独立行) | 正确 |
| repair.json | repair.md | ✅ (line 3, 独立行) | 正确 |
| smoke_host_public_multiturn.json | smoke_host_public_multiturn.md | ✅ (line 3, 独立行) | 正确 |
| write.json | write.md | ✅ (line 3, 独立行) | 正确 |

11 个声明该 slot 的 manifest 均有对应 scene `.md` 渲染独立行 placeholder。`prompt.md` 前导空格已修复。

### 2.2 interactive / wechat 排除

- `interactive.json`: `context_slots: []`，`interactive.md`: 不含 `fins_default_subject` ✅
- `wechat.json`: `context_slots: []`，`wechat.md`: 不含 `fins_default_subject` ✅

### 2.3 测试保护

`tests/runtime/test_scene_assets_migration.py:297-315` — `test_fins_default_subject_slot_is_rendered_by_declaring_scenes`：
- 遍历所有 packaged manifest/scene 对
- 声明 slot → 必须渲染独立行 placeholder ✅
- interactive/wechat → 不声明且不渲染 ✅

minor gap：未检查反向（渲染 placeholder 但未声明 slot），但该场景会导致 ScenePrepare 模板替换失败（未知 placeholder），属于 fail-closed，非静默失效。

**结论：通过。** Contract 闭环，无 gap。

## Review Area 3: current_time 工具暴露正确性

### 3.1 Manifest context_slots

零个 manifest 声明 `current_time` context slot。未机械添加。

### 3.2 Scene `.md` placeholder

零个 scene `.md` 文件渲染 `{{current_time}}`。未机械添加。

### 3.3 真实 `get_current_time` 工具

仅三个 manifest 通过 `utils` tag 获得真实 `get_current_time` 工具：

| Manifest | tool_tags_any | 获得 `get_current_time`? |
|---|---|---|
| prompt.json | `["fins-read", "web", "utils"]` | ✅ |
| interactive.json | `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]` | ✅ |
| wechat.json | `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]` | ✅ |
| 其余 13 个 manifest | 不含 `utils` tag | ❌（正确） |

### 3.4 设计一致性

plan 提出"其它 scene 若需要当前时间，只通过 LLM-facing context slot 注入文本"。当前无其它 scene 声明 `current_time` slot，这意味着目前没有 scene 同时需要"非交互式当前时间文本"又不使用真实工具。这是一个中性状态：未过度暴露，未来按需添加。

**结论：通过。** `current_time` 未机械添加，真实工具仅 prompt/interactive/wechat 可用。

## Review Area 4: README 更新合规

### 4.1 `dayu/config/README.md`

新增内容：
- 条件块 marker `<when_tag>` / `<when_tool>` 说明（ScenePrepare 控制语法，不进入 LLM 输出）
- `utils` tag 用于选择 `get_current_time` 的说明

符合该 README 的 Agent 更新约束（文档化 prompt asset 控制语法和 manifest tag 语义）。未写未来态。

### 4.2 `dayu/fins/README.md`

更新 FMP resolver 边界说明：补充第二跳失败收口为 `FmpCompanyInfoResolutionError`。

符合该 README 的 Agent 更新约束（记录 public contract 边界）。未写未来态。

### 4.3 `tests/README.md`

更新内容：
- prompt 测试：新增"入口身份不进入 LLM context slots"
- interactive 测试：改为"不要求入口 context slots"
- scene prepare：新增 `<when_tag>` / `<when_tool>` 条件块过滤语义
- entrypoint runtime：改为"scene context slot builder"覆盖描述，interactive path 改为"空 context slot 装配"
- FMP resolver：新增 S3 aggregate 验证旧入口身份 slot 字面残留扫描
- 删除 `base_user` 参数引用

符合该 README 的 Agent 更新约束（记录测试覆盖事实变化）。未写未来态。

**结论：通过。** 三个 README 更新均在其 Agent 更新约束范围内，记录当前态事实。

## Review Area 5: utils/smoke_host_public_multiturn.py 边界

### 5.1 base_user 删除

逐点验证：
- `SmokeArgs.base_user: str` 字段 → 已删除 ✅
- `SmokeArgs` docstring `:param base_user:` → 已删除 ✅
- `--base-user` argparse 参数 → 已删除 ✅
- `base_user: str = namespace.base_user` 变量提取 → 已删除 ✅
- `base_user=base_user` 构造函数参数 → 已删除 ✅
- `context_slot_values["base_user"]` → 已删除 ✅

### 5.2 Host 身份保留

`_host_context()` 中 `actor=_DEFAULT_USER`（值 `"manual-smoke-operator"`）正确保留为 `HostCallContext.actor`，不入 LLM slot。与 `context_slot_values` 完全分离。

### 5.3 fins_awaiting_runtime 保留

`_discover_smoke_service_tools` 在构造 `ServiceDiscoveredTools` 时新增 `fins_awaiting_runtime=discovered.fins_awaiting_runtime`（line 556）。路径分析：

- **正常路径**：`discover_service_tools()` → `_shared_fins_awaiting_runtime_from_provider_configs()` → `FinsIngestionRuntime | None` → passthrough
- **None 路径**：无配置时返回 `None`，passthrough 保留 `None`，下游 `host_assembly.py:1825,1861` 均有 `if fins_awaiting_runtime is None: return` 守卫
- **early-return 路径**（line 523-524）：smoke tool 已存在时直接返回 `discovered`，`fins_awaiting_runtime` 已由原始 `discover_service_tools()` 设置
- **ValueError 路径**（line 525-529）：smoke tool 未找到时抛异常，不构造 `ServiceDiscoveredTools`

逻辑正确，无边界风险。

**结论：通过。** base_user 彻底删除，Host 身份分离正确，fins_awaiting_runtime 保留正确。

## Review Area 6: 测试覆盖 invariant

### 6.1 已覆盖 invariant

| Invariant | 测试 | 位置 |
|---|---|---|
| 声明 `fins_default_subject` → 必须渲染 placeholder | `test_fins_default_subject_slot_is_rendered_by_declaring_scenes` | `test_scene_assets_migration.py:297` |
| interactive/wechat 不声明不渲染 | 同上（line 313-315） | 同上 |
| interactive 接受空 context slots | `test_interactive_runtime_accepts_empty_context_slots` | `test_entrypoint_runtime_interactive_path.py:252` |
| prompt 仍 fail-closed on missing `fins_default_subject` | `test_prompt_runtime_rejects_missing_required_context_slot` | `test_entrypoint_runtime_prompt_path.py:255` |
| CLI interactive context_slot_values 为空 | `test_interactive_command` 断言 | `test_interactive_command.py` |
| `base_user` 字面量零残留 | 本文 Review Area 1.1 验证 | N/A（deploy-time 验证） |

### 6.2 测试弱化检查

逐项审核所有断言删除：

| 变更 | 是否弱化 | 理由 |
|---|---|---|
| interactive content_digest 比较删除 | 否 | 无 variant slot，digest 比较无意义 |
| `test_interactive_runtime_rejects_missing_required_context_slot` 替换为 `test_interactive_runtime_accepts_empty_context_slots` | 否 | 语义翻转：interactive manifest 不再要求 context slots |
| `ScenePrepareError` import 删除 | 否 | 文件中无测试再用 |
| `assert "base_user" not in fact_rules_content` 删除 | 否 | 该断言针对不存在的行为，始终 trivial true |
| host_assembly 测试中 8 处 `"base_user"` 删除 | 否 | 对应已删除 slot，非断言弱化 |

**无测试弱化。无兼容 shim。**

**结论：通过。** 关键 invariant 均有测试覆盖，无测试为适配实现而弱化。

## Architecture Boundary Verification

S3 变更不改变架构边界。所有变更限于：
- Config 层（manifests + scene fragments）
- CLI adapter 层（移除 context slot 注入）
- Smoke utility（移除 CLI 参数 + context slot）
- 测试（更新期望）

未穿透 Service / Host / Engine 边界。未引入新跨层依赖。

## Open Questions

1. **grep wrapper 漏报**：项目配置的 `grep` 函数（`claude -G --ignore-files --hidden -I`，ARGV0=ugrep）对 `rg -n "base_user" dayu/cli/` 返回零匹配，但 `/usr/bin/grep -rn "BASE_USER"` 能正确匹配 `DEFAULT_BASE_USER`。控制器复验使用的 `rg` 命令可能受同一 wrapper 影响，导致"rg base_user 无匹配"的结论在字面量 `base_user`（小写）上成立但未暴露 `DEFAULT_BASE_USER`（大写）的命名残留。建议 S3 closeout 时用 `/usr/bin/grep` 或 `command grep` 独立复验。

## Residual Risk

1. **`DEFAULT_BASE_USER` 命名残留**：3 个 CLI 文件中常量名仍含 `BASE_USER` 子串，不阻塞 ship 但有误导风险。见 F1。
2. **`_DEFAULT_USER` 命名**（smoke utility）：常量名暗示用户身份 slot，实际仅为 `HostCallContext.actor`。与 F1 同类，严重程度更低。
3. **`__pycache__/*.pyc` 旧编译缓存**：4 个 `.pyc` 文件含 S2 的 `base_user` 字面量残留，不影响运行时（Python 会按源码 `.py` 的时间戳决定是否重编译），但 `grep` 扫描时会产生噪音。
4. **invariant 测试未检查反向**：scene `.md` 渲染 `{{fins_default_subject}}` 但 manifest 未声明 → ScenePrepare 模板替换失败（fail-closed），非静默失效。当前无此场景，不构成实际风险。
5. **真实 FMP 网络 smoke 仍未执行**：与 S1/S2 一致，推迟到后续验证。

## Conclusion

**Pass** — 0 blocking findings, 1 nonblocking finding (Low), 5 documented residual risks (all non-blocking).

S3 实现严格遵循 accepted plan。`base_user` 从 LLM-facing context slot、12 个 manifests、3 个 CLI 入口、smoke utility 和全部测试中彻底删除；`fins_default_subject` contract 在 11 个 manifest/scene 对中闭环且由 deploy-time 测试保护；`current_time` 未机械添加，真实 `get_current_time` 工具仅 prompt/interactive/wechat 可用；README 更新合规；smoke utility 的 `fins_awaiting_runtime` 保留正确；测试覆盖全部关键 invariant 且无弱化。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-code-review-ds.md`
- **Conclusion**: Pass
- **Blocking findings**: 0
- **Nonblocking findings**: 1 (Low)
  - F1: `DEFAULT_BASE_USER` 常量名携带已删除 slot 的历史语义（`prompt.py:83`, `interactive.py:89`, `session.py:83`）
- **Residual risks**: 5（常量命名残留 ×2、pyc 缓存残留、invariant 测试反向缺口、FMP 真实 smoke）
