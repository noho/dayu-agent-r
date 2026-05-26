# PR 68 Post-Draft Re-Review: Compactor AgentPolicy / User Prompt Template Ownership

**Reviewer:** AgentMiMo
**Date:** 2026-05-23
**Gate:** P12.5 compactor AgentPolicy / user prompt template ownership fix
**Scope:** 工作区未提交 diff（19 files, +382/-64）
**Controller-side:** affected pytest 364 passed; pyright dayu tests 0; git diff --check clean

---

## Verdict: PASS

No blocking findings. 所有 5 项审查标准均通过。

---

## Findings

无 blocking findings。以下为低严重度观察项，不阻塞合并。

### OBS-1: `docs/host/runtime-defaults-audit.md` 残留旧常量引用（不在 diff 内）

- **Severity:** observation（不在本次 diff 范围内，不计入 blocking）
- **Location:** `docs/host/runtime-defaults-audit.md:18`
- **Evidence:** audit 表仍列出 `_COMPACTOR_MAX_ITERATIONS = 1`、`_COMPACTOR_TOOL_TIMEOUT_SECONDS = 1.0`，但这两个常量已从 `dayu/host/llm_compaction.py` 移除。
- **Impact:** 文档与代码不一致，不影响运行时行为。
- **建议:** 后续清理时同步更新 audit 表，将该行标注为 "已迁移至 scene manifest agent_policy"。

---

## 逐项审查

### Criterion 1: Compactor AgentPolicy 由 scene 定义，Service 装配为 typed AgentPolicy 传入 Host

**PASS**

| 检查点 | 文件:行号 | 证据 |
|--------|-----------|------|
| scene manifest 声明完整 agent_policy | `dayu/config/prompts/manifests/conversation_compaction.json:14-23` | 8 字段全覆盖：max_iterations=1, continuation_max_attempts=0, allow_tool_calls=false, tool_execution_timeout_seconds=1.0, fallback_mode=raise_error, fallback_prompt, continuation_prompt, max_consecutive_failed_tool_batches=1 |
| 旧 scene fragment（conversation_compaction_user）已移除 | `conversation_compaction.json:33-40` | fragments 只剩 1 个 system prompt fragment |
| Service 提取 AgentPolicy | `dayu/service/host_assembly.py:640-689` (`_compactor_agent_policy_from_scene_inputs`) | 从 `scene_inputs.agent_policy_override` 构造完整 `AgentPolicy`，逐字段校验非 None |
| Service 传入 CompactorRunnerBaseline | `dayu/service/host_assembly.py:500` | `compactor_agent_policy=compactor_prompts.agent_policy` |
| Host 接收 typed AgentPolicy | `dayu/host/api.py:928-934` | `CompactorRunnerBaseline.compactor_agent_policy: AgentPolicy`，有 isinstance 校验 |
| Host 构造 LLMContextCompactor | `dayu/host/open_host.py:651` | `agent_policy=compactor_runner_baseline.compactor_agent_policy` |
| LLMContextCompactor 不再硬编码 policy | `dayu/host/llm_compaction.py:65-66` | `_COMPACTOR_MAX_ITERATIONS` 和 `_COMPACTOR_TOOL_TIMEOUT_SECONDS` 已删除 |
| `_agent_request` 使用传入 policy | `dayu/host/llm_compaction.py:250` | `agent_policy=agent_policy`（参数透传） |

### Criterion 2: conversation_compaction_user 不再在 scene fragments 中，由 execution_profiles.json 指向

**PASS**

| 检查点 | 文件:行号 | 证据 |
|--------|-----------|------|
| execution_profiles.json 新增 user_prompt_template_path | `dayu/config/execution_profiles.json:15,83,151,219` | 4 个 profile 均有 `"user_prompt_template_path": "scenes/conversation_compaction_user.md"` |
| CompactorBaselineConfig 新增字段 | `dayu/runtime/config_loader.py:196-204` | `user_prompt_template_path: str`，有 docstring 说明 |
| _parse_compactor_baseline 校验新字段 | `dayu/runtime/config_loader.py:1387-1410` | `_require_exact_fields` 包含 `user_prompt_template_path`，`_require_str_field` 校验 |
| Service 读取 template | `dayu/service/host_assembly.py:570-585` (`_read_compactor_user_prompt_template`) | 从 `execution_profile.compactor_baseline.user_prompt_template_path` 读取 |
| 路径安全校验 | `dayu/service/host_assembly.py:588-623` (`_resolve_prompt_asset_path`) | 拒绝绝对路径、空路径、逃逸 prompt asset root |

### Criterion 3: Host 不读取 config / prompt asset

**PASS**

| 检查点 | 文件:行号 | 证据 |
|--------|-----------|------|
| Host 层无 config_loader import | grep `dayu/host/` | 无 `import.*config_loader` 或 `import.*execution_profile` |
| Host 层 runtime import 仅限层中立能力 | grep `dayu/host/` | 仅 import `dayu.runtime.log_levels`、`dayu.runtime.cancellation`、`dayu.runtime.tool_truncation`、`dayu.runtime.lane`（全部允许） |
| Host 只接收 typed CompactorRunnerBaseline | `dayu/host/api.py:920-970` | frozen dataclass，所有字段 typed，有 __post_init__ 校验 |
| open_host 构造 compactor 仅用 baseline 字段 | `dayu/host/open_host.py:646-659` | 无 config 读取，纯 typed 字段映射 |

### Criterion 4: 测试与文档一致性

**PASS**

| 检查点 | 文件:行号 | 证据 |
|--------|-----------|------|
| test_llm_compaction 传入 agent_policy | `tests/host/test_llm_compaction.py:47-52,79-80,133` | `_TEST_AGENT_POLICY` 常量 + assert `seen[0].agent_policy is _TEST_AGENT_POLICY` |
| test_open_host_runtime 补齐 agent_policy | `tests/host/test_open_host_runtime.py:492-497` | `CompactorRunnerBaseline` 构造传入 `compactor_agent_policy` |
| test_public_compact_smoke 全链路 | `tests/host/test_public_compact_smoke.py:97-121,187-248` | `_compactor_baseline_inputs()` 返回 3-tuple，scene assembly + file read + policy extraction |
| test_public_open_host_options 校验类型 | `tests/host/test_public_open_host_options.py:274,286-287` | `compactor_agent_policy` 类型校验测试 |
| test_config_loader 校验必填字段 | `tests/runtime/test_config_loader.py:768-801` | `test_compactor_baseline_requires_user_prompt_template_path` 测试缺失字段失败 |
| test_scene_assets_migration | `tests/runtime/test_scene_assets_migration.py:56-60,262-268` | `_COMPACTOR_POLICY_SCENES` 白名单 + 校验 compactor scene 的完整 policy |
| test_host_assembly | `tests/service/test_host_assembly.py:118-129,195-231,283-337,640-643,726-754` | 全面覆盖：policy 校验、scene fragment count、agent_policy required、自定义 scene 路径 |
| README 同步 | `dayu/README.md`, `dayu/host/README.md`, `dayu/config/README.md`, `tests/README.md` | 全部更新，术语一致（AgentPolicy、user_prompt_template_path） |
| design.md 同步 | `docs/host/design.md:86-91,907-915,2689-2695` | 架构描述更新，与新契约一致 |

### Criterion 5: 架构边界

**PASS**

| 检查点 | 文件:行号 | 证据 |
|--------|-----------|------|
| runtime 不反向依赖 | grep `dayu/runtime/` | 无 `import.*from dayu.(host|service|engine|fins|ui)` |
| Service 是唯一 config→Host 映射方 | `dayu/service/host_assembly.py:270-510` | `compose_open_host_options` 是唯一入口，读 config + scene → 构造 `CompactorRunnerBaseline` |
| Host 不感知 config 结构 | `dayu/host/open_host.py:646-659` | 仅从 typed baseline 取值 |

---

## 验证的关键文件

1. `dayu/config/prompts/manifests/conversation_compaction.json` — scene manifest agent_policy 声明
2. `dayu/config/execution_profiles.json` — user_prompt_template_path 新字段
3. `dayu/runtime/config_loader.py` — CompactorBaselineConfig 与解析
4. `dayu/service/host_assembly.py` — Service 装装配逻辑核心
5. `dayu/host/api.py` — CompactorRunnerBaseline typed shape
6. `dayu/host/llm_compaction.py` — LLMContextCompactor 移除硬编码 policy
7. `dayu/host/open_host.py` — Host 构造 compactor
8. `tests/service/test_host_assembly.py` — 装配测试
9. `tests/host/test_llm_compaction.py` — compactor 单元测试
10. `tests/host/test_public_compact_smoke.py` — public smoke 全链路
11. `tests/runtime/test_config_loader.py` — config 解析测试
12. `tests/runtime/test_scene_assets_migration.py` — scene migration 测试
