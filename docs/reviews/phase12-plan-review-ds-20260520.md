# Phase 12 Plan Review — AgentDS

**Review artifact:** `docs/reviews/phase12-plan-review-ds-20260520.md`
**Plan under review:** `docs/host/phase12-runtime-assembly-plan.md`
**Design truth:** `docs/host/design.md`
**Control doc:** `docs/host/implementation-control.md`
**Date:** 2026-05-20

## Verdict: PASS

Blocking findings count: **0**

---

## 1. Blocking Findings

无。

---

## 2. Non-Blocking Findings / Risks

### N1. `ToolBundleSourceKind` / `ToolBundleSourceRef` 重定位路径未指定默认方案

**Severity:** Medium
**Owner:** 实施前由 controller / user 指定

当前 `ToolBundleSourceKind`、`ToolBundleSourceRef` 位于 `dayu/host/tooling.py`，通过 `dayu/host/__init__.py` 公共导出。计划 §2 声明它们应"进入 `dayu.contracts`"，Slice 1 说"必要时新增 `dayu/contracts/runtime_assembly.py`"，但没有明确选择：

- 方案 A：移动到 `dayu/contracts/tool_declaration.py`（与 `ToolBundle` 同模块）
- 方案 B：新增 `dayu/contracts/runtime_assembly.py`
- 方案 C：保留在 `dayu.host.tooling`，在 `dayu.contracts` 定义独立类型

计划已有的 stop condition 能防止沉默突破，但实施 agent 在 Slice 1 第一步就需要这个决策。**建议在进入 implementation 前由 controller 指定默认方案。**

### N2. Digest 算法未指定

**Severity:** Low
**Owner:** Slice 2 implementation agent（可自行选择并记录）

计划 §5 说 digest 覆盖 "tool name、LLM-facing schema、truncate spec、tags、display metadata"，§6 说 ScenePrepare digest "基于 manifest、直接 fragment 内容与 assembly 输入计算"。两处都声明"不得 hash callable"，但未指定：hash 函数（SHA-256？）、序列化格式（canonical JSON？）、字段排序规则。实施 agent 会自行选择；只要测试断言稳定即可。**不属于阻塞项。**

### N3. ConfigLoader 输出类型的模块归属未明确

**Severity:** Low
**Owner:** Slice 3 implementation agent

计划说 ConfigLoader 输出"层中立 typed config view"，供 Service 映射为 `RunnerSpec`、`AgentPolicy` 等。但未说明这些 typed config view 类型定义在 `dayu.runtime.config_loader` 自身，还是在 `dayu/contracts/`。当前 `dayu/contracts/` 无相关类型。实施 agent 需要判断：新建 `dayu/contracts/runtime_assembly.py` 统一承载，还是各组件自管类型。**若选前者，应与 N1 一起决策。**

### N4. `PreparedSceneInputs` 类型结构未定义

**Severity:** Low
**Owner:** Slice 4 implementation agent

计划 §6 列出 `PreparedSceneInputs` 包含的字段（`system_messages`、tool selection result、model hints、runtime hints、conversation hint、fragment refs、source refs、content digest、capability tags），但未给出 dataclass 定义。实施 agent 可从设计文档 §3 的描述推导出具体字段名和类型。

### N5. 配置 schema 字段级细节待实施 agent 从设计文档推导

**Severity:** Low
**Owner:** Slice 3 implementation agent

计划 §4 以 prose 描述四类配置 schema 的字段（如 `models.json` 的 "tool calling / streaming / stream usage capability"），但未给出 exact field names、types、required vs optional。设计文档 §3 有更精确的描述，实施 agent 应以设计文档为准，遇到歧义时回到设计文档确认。

### N6. 迁移源路径硬编码为绝对路径

**Severity:** Low
**Owner:** Slice 5 implementation agent

计划 §7 指定迁移源为 `/Users/leo/workspace/dayu-agent/dayu/config/prompts/manifests/*.json`，这是单机绝对路径。实施 agent 应在本地验证该路径可访问；若不可访问，需从用户获取实际路径。不影响本机 implementation。

### N7. 迁移源 fragment 引用的可达性未预先验证

**Severity:** Low
**Owner:** Slice 5 implementation agent（实施时验证）

计划声明只迁移 manifest 直接引用的 fragments，但未预先检查那 15 个源 manifest（audit、confirm、conversation_compaction、decision、fix、infer、interactive、overview、prompt、prompt_mt、regenerate、repair、wechat、write）的 `fragments[].path` 是否都指向存在的文件。这属于实施期验证，不阻塞 plan gate。**建议在 Slice 5 第一步先做可达性检查。**

### N8. 验证命令引用的测试文件待确认存在

**Severity:** Low
**Owner:** Implementation agent（运行时验证）

计划 §8 引用了 `tests/host/test_tooling_options.py`、`tests/host/test_submit_followup_public_contract.py`、`tests/host/test_per_run_tool_selection.py`、`tests/contracts/test_import_boundary.py` 等文件。若其中某些不存在，实施 agent 应在对应 slice 中创建。

---

## 3. Explicit Confirmation of What Was Checked

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| ToolsDiscovery 位于 `dayu.runtime`，只用显式 provider callable / entry point，不扫描包 | PASS | 计划 §5；设计 §3 (line 73) |
| ToolsDiscovery 不 import Host/Engine/Service/UI/Fins | PASS | 计划 §1 非目标、Slice 1 停止条件；设计 §3 (line 73) |
| source refs / digest 语义可实现 | PASS | 计划 §5 digest 覆盖字段明确、不 hash callable |
| ConfigLoader 四类 schema 覆盖 models / execution_profiles / host_runtime / tool_discovery | PASS | 计划 §4；设计 §3 (lines 85-86) |
| overlay 整条替换 + 单 extends 规则清晰 | PASS | 计划 §4 overlay 规则；设计 §3 (line 87) |
| 旧 `llm_models.json` / `run.json` 删除无兼容路径 | PASS | 计划 §4；设计 §3 (line 83) |
| ScenePrepare manifest schema 字段充分 | PASS | 计划 §6 列出所有必填字段；设计 §3 (line 91) |
| 单 extends、fragment 加载、context slots 语义正确 | PASS | 计划 §6；设计 §3 (lines 95-96) |
| tool_selection all/none/select names+tags 充分且非 workflow | PASS | 计划 §6；设计 §3 (lines 93-94) |
| 不修改 Host public API | PASS | 计划 §1 非目标、§9 停止条件；设计 §3 (line 105) |
| 不修改 Engine 执行路径 | PASS | 计划 §9 停止条件 |
| 不修改 Fins storage | PASS | 计划 §9 停止条件 |
| 不修改 ToolRuntime accept barrier | PASS | 计划 §9 停止条件、Slice 2 停止条件 |
| 不修改 Service / Skill workflow | PASS | 计划 §1 非目标 |
| per-run override 不超出 `SubmitFollowupRequest` 现有字段 | PASS | 计划 §2 契约清单确认字段；当前 `api.py:1826-1858` 验证字段匹配 |
| Slice 写范围、测试、README 触发、验收标准、停止条件具体 | PASS | 计划 §3 六个 slice 均有明确写范围、测试用例、验收标准和停止条件 |
| `dayu.runtime` 包根 `__init__.py` 当前干净，不导出业务符号 | PASS | `dayu/runtime/__init__.py` `__all__ = []`，无业务 import |
| `ToolDefinition` / `ToolBundle` / `@tool` 已在 `dayu.contracts.tool_declaration` | PASS | `tool_declaration.py` 完整实现 |
| `SubmitFollowupRequest` 字段与计划描述一致 | PASS | `api.py:1848-1858`：system_prompt, user_prompt, tool_names, runner_spec, runner_options, agent_policy, behavior, target_run_id |
| 既有 `tests/runtime/test_import_boundary.py` 存在且可扩展 | PASS | 已有 AST-scan 边界测试模式，新增模块会被自动扫描 |

---

## 4. Residual Risks (Non-Blocking)

- **Digest 稳定性跨 Python 版本**：如果实施 agent 选择 `hashlib.sha256(repr(...))` 或 `json.dumps(sort_keys=True)`，跨 Python 3.11 小版本的稳定性大概率可保证，但未在设计文档中承诺。当前 digest 只用于诊断/trace，不属于 Host truth，风险可接受。
- **ConfigLoader 不解析环境变量导致 Service 映射复杂度集中**：旧 `llm_models.json` 的 `{{DEEPSEEK_API_KEY}}` 占位符在新 `models.json` 中如何表达，取决于实施 agent 的 schema 设计。ConfigLoader 不解析 env var 是正确的架构选择，Service 侧需要自行替换，但 Service 尚未实现——这是 Phase 13+ 的 concern，不阻塞 Phase 12。
- **ScenePrepare `conversation_compaction` scene 的迁移语义**：计划 §7 说 `conversation_compaction` 可迁移为 no-tool scene，但 "不得变成 Skill workflow 或 Host compactor public contract"。实施 agent 需要理解这个边界——迁移的是 scene manifest 资产，不是把 compaction policy 写入 runtime assembly。停止条件已覆盖。

---

## 5. Summary

计划对架构边界、slice 顺序、非目标、停止条件的定义是充分的。所有"必须检查"项均 PASS。七个 non-blocking findings 中 N1 建议在进入 implementation 前由 controller 指定 `ToolBundleSourceKind`/`ToolBundleSourceRef` 的重定位默认方案，其余可在各 slice 实施时自然解决。
