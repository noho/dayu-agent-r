# WU-TOOLS-01 External Blocker Reconciliation Review (AgentDS)

角色：AgentDS
日期：2026-06-06
审查对象：未提交 reconciliation 变更（3 个 test 文件）
状态：**PASS**

## 审查范围

| 文件 | 变更行 | 对应 blocker |
|---|---|---|
| `tests/host/test_effective_execution_config.py` | +18/−2 | R2 one-system-message mismatch |
| `tests/host/test_phase7_waiting_integration.py` | +5/−2 | R3 wait/resume text mismatch |
| `tests/host/test_resolve_wait_command.py` | +5/−2 | R3 wait/resume text mismatch |

未变更：dayu/ 生产代码、README、R1 compaction tests（7 项保留 must-defer）。

## 裁决

**PASS** — 3 文件变更均为测试断言对当前 accepted production semantics 的正确同步。无 production behavior 修改、无 durable schema 变更、无 prompt projection contract 修改、无 README 触发更新。pyright 0，diff --check clean。

## R2: one-system-message envelope 同步

### 变更

`test_field_level_partial_merge_uses_baseline_for_omitted_fields` (line 242-248) 与 `test_descriptor_payload_dispatch_uses_per_run_override` (line 418-432) 将旧断言从裸字符串相等替换为 one-system-message envelope 结构断言。

旧断言 (line 242):
```python
assert request.messages[0].content == "system slice3"
```

新断言:
```python
assert "## Task Instructions\nsystem slice3" in request.messages[0].content
assert "## Execution Guidance" in request.messages[0].content
assert "Use the available context and tools under the current run limits." in request.messages[0].content
assert "Tools are disabled for this runner call." in request.messages[0].content
```

### 生产语义证据

- `docs/host/design.md:2572-2573`: ordinary public RunInputBuilder 必须满足 one-system-message hard contract，system envelope 必须是第一条
- `docs/host/design.md:2576-2587`: section 顺序/标题固定真源表；`Task Instructions` = order 1, `Execution Guidance` = order 2
- `dayu/host/run_input.py:161-162`: `_SYSTEM_SECTION_TASK_INSTRUCTIONS = "Task Instructions"`, `_SYSTEM_SECTION_EXECUTION_GUIDANCE = "Execution Guidance"`
- `dayu/host/run_input.py:4447`: no-tool 路径文本 `"Tools are disabled for this runner call."`
- `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-controller-adjudication.md`: 已接受 one-system-message production assembly gate

### 断言强度判断

新断言强于旧断言：旧 `==` 只验证值不验证结构，新断言验证 one-system-message 关键 section 结构（section header、execution guidance、tool availability）同时保留原 system prompt 内容验证。使用 `in` 而非 `==` 是正确选择——system envelope 包含多个非空 section，全量精确匹配会过度约束实现内部文本细节。

### 结论: PASS

同步正确，无生产语义偏离。

## R3: wait/resume guidance text 同步

### 变更

`test_local_awaiting_tool_manual_resolve_resumes_run` (line 342-349) 与 `test_resolve_wait_completed_resumes_run_and_wakes_dispatch` (line 144-151) 将旧断言替换为当前 resume guidance 格式。

旧断言 (line 342-347, phase7):
```python
assert any(
    isinstance(message.content, str)
    and "Accepted wait result fact:" in message.content
    and wait.wait_id in message.content
    for message in resume_request.messages
)
```

新断言:
```python
assert any(
    isinstance(message.content, str)
    and "A previous interrupted step has an accepted wait result."
    in message.content
    and f"tool_name={_TOOL_NAME}" in message.content
    and "resolution_kind=completed" in message.content
    and '"answer":42' in message.content
    for message in resume_request.messages
)
```

### 生产语义证据

- `dayu/host/run_input.py:3478-3490`: 当前 resume guidance 格式为 `Resume guidance:\nA previous interrupted step has an accepted wait result.\ntool_name=...\nresolution_kind=...\ntool_fact_kind=...\nresult=...`
- `Accepted wait result fact:` 在生产代码中已不存在（dayu/ 全包 grep 零命中）
- `wait_id` 在 `dayu/host/run_input.py` 中完全不存在（零命中），符合设计约束
- `docs/host/design.md:2585-2586`: "Recent Evidence" section — "不得暴露 fallback diagnostic、wait record id 或内部恢复状态"
- `docs/host/design.md:2586`: "Resume Guidance" section — "只写当前继续目标和用户可理解的恢复说明；不得写 tool_call_id、Attempt id、execution id、runner iteration id 或内部账本字段"
- `docs/host/design.md:2592-2605`: 内部标识禁止表明确 event id、attempt id、execution id、iteration id、cursor 等字段不得进入 LLM-facing envelope

### 旧断言问题

旧断言 `wait.wait_id in message.content` 是对设计违规行为的断言——将内部 wait record id 暴露到 LLM-facing text 直接违反 design.md §23 internal-id ban 硬约束。本轮变更是将从错误断言修正为当前正确业务语义断言，不是放松。

### 结论: PASS

同步正确。旧断言验证的是已不再存在的文本 (`Accepted wait result fact:`) 和设计禁止的行为 (`wait_id` in LLM-facing text)。新断言验证的是当前 production 格式和业务可读字段 (`tool_name`、`resolution_kind`、`result`)。

## R1: proactive compaction manifest ref

### 未变更

7 项 R1 test 保留失败，无 production code 修改。Codex 裁决 must-defer-with-owner 经本 review 确认成立。

### 直接证据

- `dayu/host/dispatch.py:3734-3758`: `_required_compactor_manifest_ref` / `_required_compactor_manifest_digest` fail-closed guard，accepted result 缺少 manifest ref/digest 时抛 RuntimeError
- `docs/host/design.md:3141-3153`: Host-owned compactor proposal call 必须写入 runner-call manifest；accepted compact event 必须通过 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 反向引用
- `tests/host/fake_compaction.py:39-66`: `FakeContextCompactor` 只实现 `compact(...)`，不实现 prepared proposal input capability，generic fallback 必然返回 `proposal_manifest_reference=None`
- 7 项 tests 均注入 generic `FakeContextCompactor`，在 accepted closeout 处触发 fail-closed

### Deferral 正确性

本 review 确认 Codex 裁决成立：
1. R1 非 WU-TOOLS provider 迁移引入
2. fail-closed guard 是 accepted production behavior
3. 需要 Host compactor seam owner 裁决：opener/scheduler construction 是否应 reject unprepared compactor、`ContextCompactor` public seam 是否应升级为 prepared-only、或 generic compactor fallback 仍合法时如何生成 durable manifest
4. 本轮未以测试替身绕过 Host compactor manifest ref 生产语义

### 结论: DEFERRED-CORRECTLY

## Production Code / README 影响确认

- `git diff HEAD --name-only -- 'dayu/**' '**/README.md'`: 零输出，确认未修改生产代码或 README
- `git diff --check`: clean
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings, 0 informations

## 综合裁决

| 维度 | 结论 |
|---|---|
| R2 one-system-message 同步 | PASS — 测试断言同步到当前 accepted production semantics，断言强度提升 |
| R3 wait/resume 同步 | PASS — 测试断言修正为业务正确语义，消除对设计违规行为（暴露 wait_id）的旧断言 |
| R1 compaction deferral | PASS — defer 正确，无生产代码修改，无测试替身绕过 |
| Production code 误改 | PASS — 零变更 |
| README 触发更新 | PASS — 未触发 |
| pyright / diff --check | PASS — 0 errors, clean |
| AGENTS typing/docstring/LLM-facing 约束 | PASS — 测试代码不产生 LLM-facing content，docstring/typing 符合 AGENTS.md 约束 |

**最终裁决: PASS. No blocking findings.**
