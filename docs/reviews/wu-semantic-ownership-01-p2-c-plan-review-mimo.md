# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: plan review
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-controller-validation.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`

## Review Focus

按任务要求逐项审查。

### 1. Plan 是否正确解决 MiMo 05：runtime config 与 Engine AgentPolicy prompt default 双真源

**结论：是。**

直接证据确认双真源存在：

- `dayu/engine/contracts/agent_policy.py:29-35` 定义 `_DEFAULT_FALLBACK_PROMPT = "请基于目前已经获得的上下文直接给出最终回答，不要再调用工具。"` 和 `_DEFAULT_CONTINUATION_PROMPT`，作为 `AgentPolicy` dataclass 字段默认值（`:61-64`）。
- `dayu/config/execution_profiles.json` 四个默认 profile 均显式提供 `fallback_prompt = "请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"`，与 Engine 默认文案不同。
- `dayu/service/host_assembly.py:628-633` 的 `merge_agent_policy_config(...)` 以 `_agent_policy_defaults_from_config(execution_profile.agent_policy)` 作为 `code_default` 输入，该函数（`:1622-1641`）直接从 execution profile config 投影所有字段包括 prompt。
- `dayu/service/host_assembly.py:1699-1707` 的 `_agent_policy_from_merged(...)` 显式传入 `fallback_prompt=config.fallback_prompt` 和 `continuation_prompt=config.continuation_prompt`。

问题语义：`AgentPolicy` 同时承担 typed policy validation 与 LLM-facing prompt 文本默认生产职责。直接 Engine 调用方或测试可以省略 prompt 字段并获得 Engine 持有的文本，绕过 execution profile config 真源。这不是展示差异，而是同一 LLM-facing policy 事实的双真源。

### 2. Plan 是否应该移除 Engine LLM-facing prompt text defaults，而不是把 Engine 默认改成 config 文本

**结论：是，plan 选择了正确路径。**

`docs/engine/design.md:3-7` 明确 Engine 不读取配置文件，调用方负责构造完整 `AgentRunRequest`，Engine 只消费请求事实。若 Engine contract 仍有 prompt 默认，就仍违反 finding —— 即使默认文案与 config 一致，Engine 仍然"拥有"了 prompt 文本生产职责。

物理移除 Engine prompt default 是唯一彻底解法。把 Engine 默认改成 config 文案只是让两个真源碰巧一致，没有消除双真源结构。

### 3. Owner boundary 是否正确

**结论：正确。**

Plan 的 owner boundary 判定与设计真源一致：

- **产生 prompt 默认**：ordinary Run 由 `execution_profiles.json` 的 `agent_policy` 产生；compactor 由 `conversation_compaction` scene manifest required `agent_policy` 产生。`docs/host/design.md:86` 明确 execution profile 内嵌 `agent_policy`，`fallback_prompt` 默认为"请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"。
- **校验 prompt 默认**：ConfigLoader 校验 execution profile 字段存在和类型（`dayu/runtime/config_loader.py`）；Engine `AgentPolicy.__post_init__` 只校验已传入 typed policy 的 prompt 非空（`dayu/engine/contracts/agent_policy.py:89-92`）。
- **持久 / 冻结**：`agent_policy_from_json(...)` 已显式读取 prompt 字段（`dayu/host/_execution_config_projection.py:420-423`），不从 Engine 默认补。
- **投影给 Engine**：RunInputBuilder / dispatch path 把已冻结的 `AgentPolicy` 投影到 `AgentRunRequest.agent_policy`；Engine fallback / continuation 状态机把已传入的 prompt 追加为 user message。

Propagation audit 覆盖了 ordinary path、per-run override path、compactor path 和 durable restore path，每一处语义一致。

### 4. Plan 是否 code-generation-ready

**结论：基本 code-generation-ready，有两点可改进。**

生产构造点：
- Plan 正确识别了 4 个 production `AgentPolicy(...)` 构造点：`_execution_config_projection.py:408`、`host_assembly.py:1018`、`host_assembly.py:1663`、`host_assembly.py:1699`。这 4 个构造点均已显式传入 prompt，不需要修改。

测试构造点：
- Plan 识别了 51 个 test `AgentPolicy(...)` 构造点，分布于 `tests/engine/`、`tests/host/`、`tests/service/`、`tests/runtime/`。
- 直接证据确认部分测试省略 prompt 字段依赖 Engine 默认，例如：
  - `tests/engine/contracts/test_agent_run.py:149` 省略 `fallback_prompt` 和 `continuation_prompt`。
  - `tests/engine/test_agent_phase3_tool_call.py:799` 省略 prompt 并断言默认存在（`:803-805`）。
  - `tests/engine/test_agent_phase3_tool_call.py:817-859` 多个 negative test 省略 prompt。

Negative tests：
- Plan 正确要求缺少 prompt 触发 `TypeError`，空白 prompt 仍触发 `ValueError`。现有 `test_agent_phase3_tool_call.py` 的 contract test 需要从断言默认存在改为断言 `TypeError`。

README 触发：
- Plan 正确识别需检查 `dayu/engine/README.md`（Engine contract 行为改变）、`dayu/config/README.md`（已说明 execution profile agent_policy）和 `tests/README.md`。

Validation 命令：
- Plan 提供了完整验证命令集，包括 focused tests、pyright、`git diff --check` 和 `rg` 后验扫描。

**改进点 1**：Plan 的 post-scan acceptance 要求 `rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests` 不应在 Engine contract 中命中 prompt 默认。但 `dayu/runtime` 下的 `_agent_policy_constants.py` 或 `config_loader.py` 可能仍有相关常量用于 config documentation / test helper。Plan 应明确：runtime config loader 的 ordinary fallback prompt 常量可以保留为 config 真源文档，但 Engine contract 中的 `_DEFAULT_*` 必须物理删除。

**改进点 2**：Plan 提到 `AgentPolicyDefaults` 命名可能造成误读（`_SOURCE_CODE_DEFAULT`），建议 implementation 优先消除命名歧义。但 plan 没有明确具体改名方案。建议 plan 补充：若实现发现 `code_default` 已被 execution profile 同值填充且语义混乱，应将 `AgentPolicyDefaults` 改名为 `AgentPolicyBaseline` 或类似名称，并将 `_SOURCE_CODE_DEFAULT` 改为 `_SOURCE_BASELINE_DEFAULT`。这不影响功能正确性，但影响代码可读性。

### 5. Plan 不切 slice 是否合理

**结论：合理。**

Plan 选择不切 implementation slices，理由：

- 这是一个单一语义闭环：`AgentPolicy` prompt 必填化后，生产构造点、测试夹具、README 必须同一次完成，否则中间状态会 pyright / pytest 大面积失败。
- 不涉及 durable schema、Host public API、provider 行为或跨 owner 状态机，回滚风险低。
- 55 个构造点数量多但迁移方式一致，按模块拆 slice 只会增加 gate 成本。

`docs/host/issues-implementation-control.md:140-148` 的 slice 切分原则支持该判断：小型同一语义 cleanup 默认 1-3 slices；本 WU 的语义闭环确实不需要拆分。

### 6. 是否存在过度设计、兼容 wrapper、测试 fixture 隐藏默认真源、或遗漏 durable restore / Service override / compactor path 的风险

**结论：无过度设计风险，有一处需注意。**

过度设计：Plan 明确不新增 compatibility alias、default wrapper、test-only default helper 或 re-export（non-goals）。符合 AGENTS.md 编码硬约束。

兼容 wrapper：Plan 不引入兼容性代码。`AgentPolicyDefaults` 仍可作为 runtime-neutral merge helper 输入，但 plan 要求它只来自 config loader / explicit assembly input，不代表 Engine 默认。

测试 fixture 隐藏默认真源：Plan 允许测试局部 helper 提供显式 fixture policy，但必须是测试局部，不得被 production 复用或伪装为 Engine 默认。这是正确约束。

Durable restore path：`agent_policy_from_json(...)` 已显式读取 prompt（`:420-423`），不从 Engine 默认补。Plan 正确覆盖。

Service override path：`_agent_policy_with_run_overrides(...)` 已显式传入 prompt。Plan 正确覆盖。

Compactor path：`_compactor_agent_policy_from_scene_inputs(...)` 已要求 scene `agent_policy` 完整声明所有字段（`:999-1027`）。Plan 正确覆盖。

**需注意**：`_agent_policy_defaults_from_config(execution_profile.agent_policy)` 函数（`host_assembly.py:1622-1641`）把 execution profile config 投影为 `AgentPolicyDefaults`，然后作为 `merge_agent_policy_config` 的 `code_default` 参数。当前 `AgentPolicyDefaults` 的 docstring 写的是"Agent policy 代码默认值"，但实际值来自 config。Plan 提到应消除命名歧义，但没有明确这个函数是否需要改名。建议 implementation 将该函数和 `AgentPolicyDefaults` 的 docstring 更新为"Agent policy baseline 配置投影"，避免暗示 Engine 代码默认。

### 7. 是否遗漏 AGENTS.md 约束

**结论：无遗漏。**

- 语义所有权：Plan 的 owner boundary 判定完整覆盖产生、校验、持久、投影全链路。
- LLM-facing 文本：Plan 确保 prompt 文本从 config / scene 真源一路派生，不由 Engine contract 自行补写。
- 类型：Plan 要求 `AgentPolicy(...)` 构造触发 `TypeError`（缺少 prompt）或 `ValueError`（空白 prompt），符合严格类型检查。
- README 更新：Plan 按 AGENTS.md 触发规则检查 `dayu/engine/README.md`、`dayu/config/README.md` 和 `tests/README.md`。
- pyright：Plan 要求 pyright 通过，禁止新增或扩散报错。

## Findings

### F01: `AgentPolicyDefaults` 命名与 docstring 语义不一致（LOW）

**直接证据**：`dayu/runtime/assembly.py:160-181` 定义 `AgentPolicyDefaults`，docstring 为"Agent policy 代码默认值"。`dayu/service/host_assembly.py:1622-1641` 的 `_agent_policy_defaults_from_config(...)` 把 execution profile config 投影为该类型。`_SOURCE_CODE_DEFAULT` 常量（`assembly.py:38`）用于标记来源。

**失败场景**：开发者阅读 `merge_agent_policy_config(...)` 调用时，`code_default` 参数名和 `AgentPolicyDefaults` 类型名暗示这是 Engine 代码默认值，但实际上它来自 execution profile config。这可能导致开发者误以为 Engine 仍拥有 prompt 默认。

**影响**：代码可读性，不影响功能正确性。

**建议修复**：Implementation 阶段将 `AgentPolicyDefaults` 改名为 `AgentPolicyBaseline`（或保留原名但更新 docstring），将 `_SOURCE_CODE_DEFAULT` 改为 `_SOURCE_BASELINE`，更新 `_agent_policy_defaults_from_config` 函数名和 docstring。

**严重性**：LOW。不阻塞 plan gate，可在 implementation 阶段处理。

### F02: Plan 未明确 `test_contract_fields_are_explicit` 的具体迁移语义（LOW）

**直接证据**：Plan 提到"更新 `test_contract_fields_are_explicit`：不再断言默认 prompt 存在，改为断言缺少 prompt 触发 `TypeError`，显式 prompt 构造后字段保留且空白 prompt 仍 `ValueError`"。但未给出该测试的当前文件路径。

**失败场景**：Implementation agent 可能找不到该测试或遗漏迁移。

**影响**：测试覆盖完整性。

**建议修复**：Plan 应补充该测试的文件路径（当前在 `tests/engine/test_agent_phase3_tool_call.py:799-805`，名为 `test_contract_fields_are_explicit` 的断言块）。

**严重性**：LOW。Implementation agent 可通过 `rg` 找到，不阻塞 plan gate。

## Conclusion

**pass**

Plan 正确解决了 MiMo 05 的 root cause：runtime config 与 Engine `AgentPolicy` prompt default 双真源。Plan 选择了正确的修复路径（移除 Engine prompt text defaults），owner boundary 判定准确，code-generation-ready 程度足够，不切 slice 合理，无过度设计或遗漏风险。

两个 LOW findings 不阻塞 plan gate，可在 implementation 阶段处理。

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-mimo.md`
