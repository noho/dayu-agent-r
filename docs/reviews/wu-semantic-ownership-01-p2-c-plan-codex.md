# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan - AgentCodex

## Goal / Motivation / Success Signal

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: plan
- Accepted finding: MiMo 05, runtime config and Engine `AgentPolicy` define different default fallback prompts.
- Plan decision: `ready`

动机成立。`fallback_prompt` / `continuation_prompt` 是直接进入 LLM 上下文的文本，不能由 Engine contract 和 execution profile 同时提供默认值。当前 Engine `AgentPolicy` 在字段默认值上持有 prompt 文案，而 `execution_profiles.json` 也持有 ordinary Run 默认文案，且 fallback prompt 内容不同。这不是展示差异，而是同一 LLM-facing policy 事实的双真源。

成功信号：

- Engine `AgentPolicy` 不再定义 LLM-facing prompt 文本默认值；`fallback_prompt` 与 `continuation_prompt` 必须由调用方显式传入。
- Ordinary Run 的 prompt 默认来自 execution profile，经 ConfigLoader / runtime assembly / Service assembly 变成完整 typed `AgentPolicy` 后传给 Host / Engine。
- Compactor policy 来自 `conversation_compaction` scene 的 required `agent_policy`，缺字段继续 fail fast，不从 Engine 默认补文本。
- 所有 production 和 test `AgentPolicy(...)` 构造点都显式传入 prompt；测试不通过省略 prompt 依赖 Engine 默认。
- 缺少 `fallback_prompt` 或 `continuation_prompt` 时，`AgentPolicy(...)` 构造触发 Python `TypeError`；空白 prompt 仍触发 `ValueError`。

## Non-goals / Scope Boundary

- 不改变默认 ordinary fallback / continuation prompt 的实际文本，除非 implementation 发现配置真源已不一致并需要只同步文档。
- 不改变 compactor prompt 文本或 compactor scene 行为。
- 不改变 Host public API、durable schema、EventLog、memory、tool runtime、Runner protocol 或 provider payload。
- 不让 Engine import `dayu.runtime`、ConfigLoader、execution profile 或 Service helper。
- 不新增 compatibility alias、default wrapper、test-only default helper 或 re-export。
- 不把 explicit prompt 参数塞进 extra payload。

## Design Alignment

- `docs/engine/design.md:3-7` 说明 Engine 不读取配置文件，调用方负责构造完整 `AgentRunRequest`，Engine 只消费请求事实。
- `docs/engine/design.md:135-145` 说明 continuation / fallback 路径消费 `AgentPolicy.continuation_prompt` 和 `AgentPolicy.fallback_prompt`，但没有要求 Engine 拥有这些文本。
- `docs/host/design.md:31-36` 固定 `UI -> Service -> Host -> Engine`，Service 负责业务入口和场景装配，Engine 负责单次模型交互。
- `docs/host/design.md:111-119` 明确 Service / composition root 把 ConfigLoader、ScenePrepare、ToolsDiscovery 输出映射为完整 typed inputs，Host / Engine 不接收 raw config fragment。
- `dayu/config/README.md:88-97` 说明 execution profile 内嵌普通 `agent_policy`；`dayu/config/README.md:127` 记录默认 fallback prompt 文本。
- `dayu/config/README.md:220-224` 说明 `conversation_compaction` scene 在自身 `agent_policy` block 中声明 compactor AgentPolicy，Service 从 scene 装配 compactor AgentPolicy。

结论：最佳实践不是把 Engine 默认文案改成 config 文案，而是移除 Engine 文本默认，让所有入口在 owner boundary 处显式提供完整 policy。

## Root-cause Direct Evidence

直接证据：

- `dayu/engine/contracts/agent_policy.py:29-35` 定义 `_DEFAULT_FALLBACK_PROMPT` 和 `_DEFAULT_CONTINUATION_PROMPT`，其中 fallback prompt 是“请基于目前已经获得的上下文直接给出最终回答，不要再调用工具。”。
- `dayu/engine/contracts/agent_policy.py:61-64` 把 `fallback_prompt` 和 `continuation_prompt` 设为 dataclass 默认字段。
- `dayu/config/execution_profiles.json:80-88`、`:167-175`、`:254-262`、`:341-349` 为四个默认 execution profile 显式提供 ordinary `fallback_prompt` 和 `continuation_prompt`，其中 fallback prompt 是“请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。”。
- `dayu/runtime/config_loader.py:421-440` 的 `AgentPolicyConfig` 把 `fallback_prompt` / `continuation_prompt` 建模为 execution profile 内嵌字段；`dayu/runtime/config_loader.py:1808-1847` 解析时要求字段存在。
- `dayu/service/host_assembly.py:628-633` 用 execution profile 的 agent policy 与 scene override 合并 ordinary policy；`:1699-1707` 再把 merged config 映射为 Engine `AgentPolicy`，并已显式传入 prompt。
- `dayu/service/host_assembly.py:1000-1027` compactor path 要求 scene `agent_policy` 完整声明所有字段，并显式传入 prompt。
- `rg -n "AgentPolicy\\(" dayu/ tests/ --glob '*.py'` 共发现 55 个构造点：production 4 个，tests 51 个。Engine tests 中存在省略 prompt 的构造，例如 `tests/engine/test_agent_phase3_tool_call.py` 的 contract test 当前断言默认 prompt 存在，这正是需要迁移的测试语义。
- Implementation acceptance 必须把 `utils/` 一并纳入 AgentPolicy 构造点扫描：`rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'`。`utils/` 是开发 / smoke 辅助入口，不属于 production owner，但省略 prompt 会在 Engine contract 收紧后变成运行时失败。

Root cause：

- `AgentPolicy` 同时承担 typed policy validation 与 LLM-facing prompt 文本默认生产职责，违反 Engine “只消费完整请求事实”的边界。
- Service assembly 主路径已经能从 config / scene 产生完整 policy；缺陷主要在 Engine contract 允许省略 prompt，从而使 direct Engine usage 和大量测试夹具绕过 config 真源。

## Owner Boundary

语义：Agent fallback / continuation prompt 文本。

- 产生 prompt 默认：ordinary Run 由 `execution_profiles.json` 的 execution profile `agent_policy` 产生；compactor 由 `conversation_compaction` scene manifest required `agent_policy` 产生。
- 校验 prompt 默认：ConfigLoader 校验 execution profile 字段存在和类型；ScenePrepare 校验 scene override 字段类型；Service compactor helper 校验 compactor scene policy 必填完整；Engine `AgentPolicy.__post_init__` 只校验已传入 typed policy 的数值和 prompt 非空。
- 持久 / 冻结：Host opener ordinary baseline 和 compactor baseline 接收 Service 传入的完整 typed `AgentPolicy`；Host effective execution config projection 序列化 / 反序列化完整 policy JSON，不补默认。
- 投影给 Engine：RunInputBuilder / dispatch path 把 Host baseline 或 per-run override 中已冻结的 `AgentPolicy` 投影到 `AgentRunRequest.agent_policy`；Engine 只读取字段执行 fallback / continuation，不生成文本。
- 投影给 LLM：Engine fallback / continuation 状态机把已传入的 prompt 追加为 user message。LLM-facing 文本从 config / scene 真源一路派生，不由 Engine contract 自行补写。

Propagation audit：

- Ordinary path：`execution_profiles.json` -> `ConfigLoader.AgentPolicyConfig` -> `merge_agent_policy_config(...)` -> `ServiceOpenHostAssemblyResult.agent_policy_config` -> `OrdinaryRunExecutionBaseline.agent_policy` -> Host effective policy snapshot -> `AgentRunRequest.agent_policy` -> Engine fallback / continuation user message。
- Per-run override path：ordinary baseline -> `ServiceRunOverrides` 只覆盖允许字段；未覆盖的 prompt 继续来自 ordinary baseline，覆盖 fallback prompt 时必须显式非空。
- Compactor path：`execution_profile.compactor_baseline.scene_id` -> `ScenePrepare` 读取 `conversation_compaction` manifest -> `_compactor_agent_policy_from_scene_inputs(...)` required policy -> `CompactorRunnerBaseline.compactor_agent_policy` -> Host compaction run -> Engine。
- Durable restore path：`agent_policy_to_json(...)` / `agent_policy_from_json(...)` 要求 JSON 中已有 prompt 字段；不从 Engine 默认补。

## Affected Files / Modules

Production:

- `dayu/engine/contracts/agent_policy.py`
- `dayu/engine/README.md`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `dayu/host/_execution_config_projection.py`
- 只在必要时检查 `dayu/config/README.md`；预计不需要改默认 config JSON。

Tests:

- Engine direct fixtures: `tests/engine/contracts/test_agent_run.py`, `tests/engine/test_agent_phase2.py`, `tests/engine/test_agent_phase3_tool_call.py`, `tests/engine/test_metadata_boundary.py`, `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- Host direct fixtures: `tests/host/**` 中 `AgentPolicy(...)` 构造点，包含 `tests/host/public_smoke_support.py`、dispatch、compaction、effective execution config、open host runtime、run input builder 等。
- Service / runtime: `tests/service/test_host_assembly.py`, `tests/runtime/test_assembly_helpers.py`, `tests/runtime/test_config_loader.py`
- README trigger check: `tests/README.md`

Utils / smoke scripts:

- `utils/**` 中 `AgentPolicy(...)` 构造点必须纳入扫描；若存在省略 prompt 的脚本，应在该脚本内显式传入 fixture prompt，不新增跨脚本默认真源。

## Exact Implementation Decisions

1. 修改 `AgentPolicy` 字段定义：
   - 删除 `_DEFAULT_FALLBACK_PROMPT` 与 `_DEFAULT_CONTINUATION_PROMPT`。
   - `fallback_prompt: str` 与 `continuation_prompt: str` 改为无默认必填字段。
   - 保留 `fallback_mode=AgentFallbackMode.FORCE_ANSWER` 与 `max_consecutive_failed_tool_batches=2`，因为它们不是 LLM-facing 文本；本 WU 不处理这些非文本默认。
   - 保留 `__post_init__` 非空校验和错误语义。

2. 不把 Engine 默认替换为 config 文本：
   - 若 Engine contract 仍有 prompt 默认，就仍违反 finding；因此 plan 要求物理移除 Engine prompt default。

3. Runtime assembly：
   - 命名和 docstring cleanup 是硬性要求，不留给 implementation 自行判断。Runtime assembly 的 merge baseline 可以继续存在，但它不得在名称、source tag 或 docstring 中暗示 Engine / code 拥有 prompt 默认。
   - 必须执行以下 before / after 改名，不做旧名兼容 wrapper、alias 或 re-export：
     - `AgentPolicyDefaults` -> `AgentPolicyBaseline`。
     - `code_default` 参数名 -> `base_policy`。
     - `_SOURCE_CODE_DEFAULT` -> `_SOURCE_RUNTIME_BASE`，source 字符串从 `"code_default"` 改为 `"runtime_base"`。
     - `_agent_policy_defaults_from_config(...)` -> `_agent_policy_baseline_from_config(...)`。
   - `AgentPolicyBaseline` 的 docstring 必须说明它是 runtime assembly merge fallback / baseline values，来源于 config loader 或显式 assembly input，不是 Engine contract defaults，也不是 LLM-facing prompt 文本真源。
   - `merge_agent_policy_config(...)` 测试必须证明 `continuation_prompt` / `fallback_prompt` 来源是 execution profile 或 explicit override，不是 Engine default。

4. Service ordinary path：
   - `_agent_policy_from_merged(...)` 和 `_agent_policy_with_run_overrides(...)` 继续显式传入 prompt。
   - `ServiceRunOverrides` 当前只支持 `fallback_prompt` override，不支持 `continuation_prompt` per-run override；本 WU 不新增 public override 字段。未覆盖 continuation prompt 继续来自 ordinary baseline。

5. Compactor path：
   - `_compactor_agent_policy_from_scene_inputs(...)` 保持 required policy 校验，不允许省略 prompt 后由 Engine 补默认。
   - 增加或保留测试覆盖：compactor scene 缺 `fallback_prompt` / `continuation_prompt` 时 Service assembly fail fast。

6. Host durable projection：
   - `agent_policy_from_json(...)` 已显式读取 prompt；实现只需在 AgentPolicy 必填化后确认无构造点省略 prompt。
   - 不加旧 JSON 兼容读取；本项目 schema 变更按全新 schema 起库处理，且当前 durable frozen policy 已包含 prompt 字段。

7. Test migration:
   - Engine tests 建 fixture helper 时，helper 必须属于测试语义 owner，例如 `_agent_policy(...)` 返回完整 explicit policy。helper 必须 file-local 或 function-local，不得放到 `conftest.py`，不得被其它测试模块 import 为共享默认真源，不得放到生产代码或作为 compatibility default。
   - 所有直接 `AgentPolicy(...)` 构造点按所在测试的语义显式传入 prompt：fallback 行为测试传可断言文本；非 fallback 关注点测试传稳定 fixture 文本。
   - `tests/host/public_smoke_support.py` 是显式迁移目标：其 ordinary run baseline 的 `AgentPolicy(...)` 必须传入显式 `fallback_prompt=` 和 `continuation_prompt=`。这些 prompt 只能作为该 fixture 构造点的显式测试输入，不能抽成可跨测试导入的默认真源。
   - 具体迁移 `tests/engine/test_agent_phase3_tool_call.py::test_contract_fields_are_explicit`：
     - 不再断言默认 prompt 存在。
     - 将缺少 prompt 的行为改成 `TypeError` 测试，例如拆出或重命名为 `test_agent_policy_prompt_fields_are_required`：分别覆盖缺 `fallback_prompt` 和缺 `continuation_prompt`。
     - 增加或保留显式 prompt 构造 / 保留测试，例如 `test_agent_policy_accepts_explicit_prompt_fields`：断言传入的 `fallback_prompt`、`continuation_prompt` 原样保留。
     - `fallback_mode=AgentFallbackMode.FORCE_ANSWER` 与 `max_consecutive_failed_tool_batches=2` 是非文本默认；这些断言可独立保留，或放入显式 prompt acceptance test，但不得再借省略 prompt 来验证。
     - 空白 prompt 的 `ValueError` 仍由 invalid values 测试覆盖；迁移这些 negative test 的其它字段时必须显式传入非空 prompt，避免缺字段 `TypeError` 掩盖空白值校验。
   - 运行后再次 `rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'`，抽查每个构造点都有 `fallback_prompt=` 和 `continuation_prompt=`，除了 deliberate `TypeError` negative test。

8. README / docs:
   - 修改 `dayu/engine/README.md`，说明 Engine `AgentPolicy` 接收 resolved prompt values，不拥有文本默认。
   - 检查 `dayu/config/README.md`：它已说明 execution profile `agent_policy` 和默认 fallback prompt；仅当实现改名或发现 continuation prompt 文档缺口影响读者时才改。
   - 检查 `tests/README.md`：如果新增/迁移共享测试 fixture 规则，按其职责更新；否则不机械修改。
   - 不修改 `docs/engine/design.md` / `docs/host/design.md`，因为设计真源已支持该边界；除非 implementation 发现现文档仍宣称 Engine 拥有 prompt 默认。

## Tests / Validation Commands

Implementation 后必须执行：

```bash
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host
source .venv/bin/activate && pyright
git diff --check
```

Focused checks:

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/contracts/test_agent_run.py
source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py
source .venv/bin/activate && rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'
```

Post-scan acceptance:

- Production `AgentPolicy(...)` 构造点必须都显式传入 prompt。
- Test 和 `utils/` `AgentPolicy(...)` 构造点必须都显式传入 prompt，除了 deliberate `TypeError` negative test；negative test 应用 `pytest.raises(TypeError)` 包裹并说明原因。
- `rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests` 不应在 Engine contract 中命中 prompt 默认；runtime config loader 的 ordinary fallback prompt 常量可以保留为 config documentation/test helper 真源。

## README / Docs Decision

- 需要检查并预计更新 `dayu/engine/README.md`，因为 `dayu/engine/` contract 行为改变：prompt 字段从 Engine default 变为 caller-resolved required input。
- 需要检查 `dayu/config/README.md`，预计无需改；它已经把 execution profile `agent_policy` 和默认 fallback prompt 写成配置职责。
- 需要检查 `tests/README.md`，只有在新增共享测试 fixture 或改变测试目录职责时更新。
- 不更新根 README、`dayu/README.md`、Host design 或 Engine design，除非 implementation 实际改变用户可见 workflow、分层关系或设计真源。

## Residual Risks

- 构造点多，机械迁移容易漏传 `continuation_prompt`。用 pyright、pytest 和 `rg` 后验扫描兜底。
- `AgentPolicy` 是 public dataclass；外部调用方若直接省略 prompt 会从运行时默认变成 `TypeError`。这是本 WU 期望 contract 收紧，不做兼容。
- 如果 tests 为了减少重复而新增过宽 fixture helper，可能把默认真源再次藏入测试层。只允许 file-local 或 function-local helper，必须是显式 fixture policy，不得放入 `conftest.py`，不得被其它测试模块 import，不得被 production 复用或伪装为 Engine 默认。
- Runtime assembly 的旧 `code_default` 命名若保留会继续造成 owner 误读；本 plan 已将 `AgentPolicyDefaults` / `code_default` / `_SOURCE_CODE_DEFAULT` cleanup 设为 implementation 必做项。

## Slice Decision

不切 implementation slices，一次实现。

理由：

- 这是一个单一语义闭环：`AgentPolicy` prompt 必填化后，生产构造点、测试夹具、README 必须同一次完成，否则中间状态会 pyright / pytest 大面积失败。
- 不涉及 durable schema、Host public API、provider 行为或跨 owner 状态机，回滚风险低。
- 55 个构造点数量多但迁移方式一致，按模块拆 slice 只会增加 gate 成本，并留下某些测试继续依赖 Engine 默认的半成品窗口。

## Open Questions

无阻塞问题。

Implementation 前只需确认当前分支没有并发修改同一批 AgentPolicy tests；若有，按 dirty worktree 规则读取并顺着现有变更迁移。

## Proposed Files

- `dayu/engine/contracts/agent_policy.py`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `dayu/host/_execution_config_projection.py`
- `dayu/engine/README.md`
- `dayu/config/README.md`（按检查结果决定）
- `tests/README.md`（按检查结果决定）
- `tests/engine/**`
- `tests/runtime/test_assembly_helpers.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- `tests/host/**`
- `utils/**`（按扫描结果决定）

## Completion Report

- plan decision: `ready`
- artifact path: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- proposed files: listed above
- validation commands: listed above
- open questions: none
