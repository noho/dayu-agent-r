# WU-TOOLS-01 External Blocker Reconciliation Review

Gate: code-review
Reviewer: AgentMiMo
Date: 2026-06-06
Status: **PASS**

## 审查对象

未提交 reconciliation 变更（3 个测试文件 + 1 个 review artifact）：

- `tests/host/test_effective_execution_config.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_resolve_wait_command.py`
- `docs/reviews/wu-tools-01-external-blocker-reconciliation-codex.md`

## 审查结论

| 维度 | 结论 |
|---|---|
| R2/R3 断言同步 | PASS — 基于 accepted production semantics，非放松断言 |
| R1 proactive compaction defer | PASS — root-cause 证据链完整，defer 裁决正确 |
| 生产代码 / README 误改 | PASS — 仅改 3 个 test 文件，无生产代码或 README 变更 |
| 验证可信度 | PASS — 4 targeted passed，pyright 0，diff --check clean |
| 整体 | **PASS** |

## Finding 详情

### F1: R2 断言同步 — 无 blocking finding

**旧断言**：`request.messages[0].content == "system slice3"` / `"descriptor system prompt"`

**新断言**：检查 one-system-message envelope 包含 `## Task Instructions\nsystem slice3`、`## Execution Guidance`、execution guidance 文本和 no-tool guidance。

**证据链**：

1. `design.md:2572-2574` 定义 one-system-message hard contract，system envelope 必须是第一条且唯一一条 system message。
2. `design.md:2576-2579` 定义 section title 和顺序：`Task Instructions` → `Execution Guidance` → ...
3. `run_input.py:2648-2652` 的 `_render_system_envelope` 使用 `## ` 前缀 + section title + `\n\n` 分隔符渲染。
4. `run_input.py:1742-1751` 的 `DefaultSceneParameterProvider.build_scene_messages` 生成 `Execution Guidance` section，内容包含 `"Use the available context and tools under the current run limits."` 和 `_tools_scene_line` 输出。
5. `run_input.py:4438-4447` 的 `_tools_scene_line` 在 no-tool 路径返回 `"Tools are disabled for this runner call."`。
6. `test_run_input_builder.py:3741-3753` 的 `_expected_system_content()` 已使用相同 section title，说明这是 established test pattern。

**结论**：新断言精确校验 one-system-message envelope 的结构与内容，比旧的裸字符串等值匹配更强。旧断言只匹配原始 system prompt 文本，完全未覆盖 envelope 结构，属于测试债务。同步方向正确，不是放松。

### F2: R3 断言同步 — 无 blocking finding

**旧断言**：查找 `"Accepted wait result fact:"` 且要求 `wait.wait_id` 出现在 LLM-facing resume messages。

**新断言**：查找 `"A previous interrupted step has an accepted wait result."`、`tool_name=...`、`resolution_kind=completed` 和 result 内容；不再要求 `wait_id`。

**证据链**：

1. `run_input.py:3478-3490` 的 `_resume_wait_message_from_current_start` 生成内容：`_RESUME_GUIDANCE_PREFIX`（`"Resume guidance:"`）+ `"A previous interrupted step has an accepted wait result."` + `tool_name=...` + `resolution_kind=...` + `tool_fact_kind=...` + `result=...`。
2. `design.md:2585-2586` 明确规定："Resume Guidance section 不暴露 wait record id 或内部恢复状态，只写当前继续目标和用户可理解恢复说明"。
3. `design.md:2592-2605` 的 LLM-facing internal-id ban 表格将 `wait_id` 类内部标识列为禁止暴露。
4. 新断言的 `"A previous interrupted step has an accepted wait result."` 是生产代码 `run_input.py:3481` 的精确文本。
5. `tool_name=...`、`resolution_kind=...` 和 result 内容均来自 `run_input.py:3482-3487` 的实际投影。

**结论**：旧断言要求 LLM-facing 消息包含 `wait_id`，违反 `design.md:2585-2586` 的 internal-id ban。新断言移除 `wait_id` 要求并改为校验业务可读字段，与 accepted production semantics 一致。这是修正测试债务，不是放松断言。

### F3: R1 proactive compaction defer — 无 blocking finding

**Codex 裁决**：must-defer-with-owner。

**root-cause 证据链**：

1. `dispatch.py:3734-3745` 的 `_required_compactor_manifest_ref` 在 `accepted_proposal_manifest_ref is None` 时 fail closed。
2. `fake_compaction.py:39-66` 的 `FakeContextCompactor` 只实现 `compact()` 接口，不实现 `CompactorProposalPreparedCompactor` prepared capability。
3. `compaction_operation.py:777-784` 的 generic `ContextCompactor.compact(...)` fallback 返回 `proposal_manifest_reference=None`。
4. `compaction_operation.py:749-776` 只有 compactor 满足 prepared capability 时才 prepare、record manifest、再 run proposal。
5. `design.md:3141-3153` 要求 accepted compact event 必须通过 `accepted_proposal_manifest_ref` / digest 反向引用 accepted proposal manifest。

**结论**：R1 不是 WU-TOOLS provider 迁移引入的回归。直接根因是 Host scheduler tests 使用 generic `FakeContextCompactor`，而 production accepted closeout 要求 manifest ref。这不是测试断言过时的问题，而是 Host compactor seam 的生产语义问题——需要 owner 裁决 generic compactor path 是否仍合法。Codex 的 defer-with-owner 裁决正确，本轮不应绕过。

### F4: 生产代码 / README 误改检查 — 无 finding

`git diff --name-only` 仅列出 3 个 `tests/host/*.py` 文件。`git diff -- dayu/ docs/host/ README.md dayu/README.md tests/README.md` 无输出。未触及生产代码、设计文档或 README。

### F5: 验证可信度 — 无 finding

| 验证项 | 期望 | 实际 |
|---|---|---|
| 4 targeted R2/R3 tests | 4 passed | 4 passed |
| pyright（3 个修改文件） | 0 errors | 0 errors, 0 warnings, 0 informations |
| git diff --check | clean | clean |

## LLM-facing 约束合规检查

R2 新断言校验 one-system-message envelope 的 section title（`## Task Instructions`、`## Execution Guidance`）和业务可读 guidance 文本，符合 `design.md:2574-2587` 的 section title 与 LLM-facing 文本契约。

R3 新断言校验 resume guidance 中的业务可读字段（tool name、resolution kind、result），不校验任何内部标识（wait_id、event_id、digest），符合 `design.md:2585-2605` 的 internal-id ban。

## Typing / Docstring 检查

3 个修改的 test 文件均为纯断言变更，未新增函数、类或签名变更，不触发 docstring / typing 新增要求。pyright 0 errors 确认类型安全。

## 总结

本轮 reconciliation 变更范围正确、证据充分：
- R2/R3 是测试债务同步，基于 accepted production one-system-message / internal-id ban 设计，非放松断言。
- R1 defer 裁决正确，root-cause 是 Host compactor seam 生产语义问题，非本轮范围。
- 无生产代码、设计文档或 README 误改。
- 验证可信：4 passed、pyright 0、diff --check clean。

**结论：PASS。无 blocking finding。**
