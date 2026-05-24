# PR 68 P12.6 Draft Review

## Scope

- Mode: PR Review
- PR: [#68](https://github.com/noho/dayu-agent-r/pull/68)
- Title: P12.5 conversation memory evidence-backed facts
- Author: noho
- Head: `feat/phase-12-5-conversation-memory-optimize` @ `466a639`
- Base: `main` @ `09481cfe`
- Output file: `docs/reviews/pr-68-p12-6-draft-review-mimo-20260524.md`
- Included scope: PR 68 全量 Python diff + 配置 + README 变更
- Excluded scope: `docs/reviews/` 下的 review artifacts（非生产代码）
- Parallel review coverage: 5 个 subagent 分别覆盖 compaction contract、memory projection、LLM compaction operation、dispatch/governance/assembly、test adequacy；主 reviewer 覆盖 engine layer（agent.py, sse_parser.py, tool_call_aggregator.py）、runtime config_loader、durable storage、tool_runtime、README sync、pyright 验证

## Validation Commands

```bash
# pyright
source .venv/bin/activate && pyright --stats
# 结果: 零错误

# 测试
source .venv/bin/activate && python -m pytest tests/host/test_compaction_operation.py tests/host/test_memory_projection.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compact_material.py tests/service/test_host_assembly.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/runtime/test_config_loader.py --tb=short -q
# 结果: 307 passed in 5.22s

# 空白字符检查（Python 文件）
git diff main...HEAD --check -- '*.py'
# 结果: 无问题

# 旧 schema key 残留检查
grep -rn 'verified.fact' dayu/ --include='*.py'
# 结果: 全部为 fail-closed 拒绝守卫，非残留
```

## Findings

### 1-未修复-中-compact() 超时未包装为 LLMCompactionProposalError

- **入口/函数**: `dayu/host/llm_compaction.py` `compact()` 方法
- **文件(行号)**: `dayu/host/llm_compaction.py:276`
- **输入场景**: compactor LLM 调用超时
- **实际分支**: `asyncio.wait_for(...)` 抛出 `TimeoutError`
- **预期行为**: 超时应被 `compact()` 捕获并包装为 `LLMCompactionProposalError("compactor proposal timed out")`，与 proposal 解析失败保持一致的错误类型
- **实际行为**: `TimeoutError` 透传到 `compaction_operation.py:161` 的 `except Exception`，虽被兜底捕获但错误类型为 `TimeoutError` 而非 `LLMCompactionProposalError`，导致日志中错误分类不一致
- **直接证据**: 第 276 行 `return await asyncio.wait_for(run_agent_and_wait(request), timeout=timeout_seconds)`；`compact()` 方法的 `except` 块只捕获 `LLMCompactionProposalError`，不捕获 `TimeoutError`
- **影响**: 运行时功能正确（operation 层兜底捕获），但诊断日志中 timeout 与 proposal failure 不可区分，影响生产问题定位
- **建议改法和验证点**: 在 `compact()` 中增加 `except asyncio.TimeoutError` 分支，包装为 `LLMCompactionProposalError("compactor proposal timed out")`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-range endpoint label 映射静默截断多 ref

- **入口/函数**: `dayu/host/llm_compaction.py` `_range_tuple()` / `_optional_input_range()`
- **文件(行号)**: `dayu/host/llm_compaction.py:749-763`
- **输入场景**: LLM 输出的 range endpoint label 对应的 provenance entry 含多个 `canonical_source_refs`
- **实际分支**: `start_refs = _canonical_refs_for_labels(...)` 后取 `start_refs[0]`
- **预期行为**: range endpoint 应精确映射到单个 canonical ref；若 label 映射到多个 refs，应报错而非静默截断
- **实际行为**: `_canonical_refs_for_labels` 的 `refs.extend(entry.canonical_source_refs)` 可能产出多元素列表，`[0]` 只取第一个，静默丢弃其余
- **直接证据**: 第 749 行 `start_refs = _canonical_refs_for_labels(request, (...), ...)`；第 763 行 `start_input_ref=start_refs[0]`；第 784-795 行 `refs.extend(entry.canonical_source_refs)` 不保证单元素
- **影响**: 若 LLM 引用的 label 对应多个 canonical source，range 边界语义不精确，可能导致 compact 范围错误
- **建议改法和验证点**: 在 `_range_tuple` 和 `_optional_input_range` 中添加 `if len(start_refs) != 1: raise ValueError(...)` 断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-中-dispatch lag skip 无上限保护

- **入口/函数**: `dayu/host/dispatch.py` `_build_run_input_with_lag_repair()`
- **文件(行号)**: `dayu/host/dispatch.py:2241-2256`
- **输入场景**: memory projection 持续 lag（如 rebuild 本身有 bug 或 projection 持续落后）
- **实际分支**: `SNAPSHOT_LAG_OVER_THRESHOLD` 捕获后 rebuild 再重试，重试仍失败时 `return "skipped"`
- **预期行为**: skip 应有上限保护，超过后 fail closed 或写入 diagnostic event
- **实际行为**: Run 被 skip 后回到 queued 状态，下一轮 dispatch 再次尝试，无 skip 计数器或上限
- **直接证据**: dispatch.py:2241-2256 的 `return "skipped"` 无 escalation 机制
- **影响**: 若 lag 持续存在，Run 会无限 skip 循环，既不执行也不终止
- **建议改法和验证点**: 为 skip 计数加上限（如 `max_consecutive_skips`），超过后 fallback 到 terminal closeout
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-中-evidence_labels 空集时 guard rail 失效

- **入口/函数**: `dayu/host/context_governance.py` `_summary_pretends_evidence_backed_fact()`
- **文件(行号)**: `dayu/host/context_governance.py:160-177`
- **输入场景**: compaction request 构造时 `material_pack.evidence_labels` 为空集
- **实际分支**: `evidence_labels = set(request.material_pack.evidence_labels)` 为空，交集检查被跳过
- **预期行为**: 若有 `evidence_backed_fact_refs` 非空但 labels 为空的场景，应触发 diagnostic
- **实际行为**: guard rail 静默失效，LLM 可能在 summary 中越权引用 evidence ref 作为 fact
- **直接证据**: context_governance.py:167 `evidence_labels = set(request.material_pack.evidence_labels)`
- **影响**: 若 material_pack 构造遗漏 evidence labels，quality checker 的越权引用检查失效
- **建议改法和验证点**: 确认 `material_pack.evidence_labels` 在所有路径上正确填充；若有 evidence_backed_fact_refs 非空但 labels 为空的场景，触发 diagnostic issue
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 5-未修复-低-memory fact dedup tiebreaker 使用 item_id 字典序

- **入口/函数**: `dayu/host/memory.py` `_is_newer_or_equal_extraction()`
- **文件(行号)**: `dayu/host/memory.py`（`_is_newer_or_equal_extraction` 函数）
- **输入场景**: 同一 compact event 产出多个 fact candidate，event_sequence 相同
- **实际分支**: `candidate.item_id >= current.item_id` 字典序比较
- **预期行为**: 同 sequence 内应有确定性 tiebreaker（如 candidate index）
- **实际行为**: item_id 字典序不保证等价于时间序或 LLM 输出顺序
- **直接证据**: `return candidate.item_id >= current.item_id`
- **影响**: dedup 结果在极端 case 下可能不稳定，但实际触发概率低
- **建议改法和验证点**: 增加 intra-event tiebreaker（如 candidate 在 payload 数组中的 index）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 6-未修复-低-episode summary 上限与 recent_raw_turns_floor 耦合

- **入口/函数**: `dayu/host/memory.py` `_policy_bounded_recent_episode_summaries()`
- **文件(行号)**: `dayu/host/memory.py`（该函数内部）
- **输入场景**: policy 调整 `recent_raw_turns_floor`
- **实际分支**: `max_items = max(DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR, policy.recent_raw_turns_floor)`
- **预期行为**: episode summary 上限应由独立 policy 字段控制
- **实际行为**: 与 raw turn 保底条数耦合，调整一个会影响另一个
- **直接证据**: `policy.recent_raw_turns_floor` 语义是 "raw turn 保底条数"，不是 "episode summary 上限"
- **影响**: 当前默认值下无实际影响，但未来 policy 调整时可能意外膨胀
- **建议改法和验证点**: 在 `MemoryProjectionPolicy` 中增加独立的 `max_episode_summaries` 字段
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 7-未修复-低-脱敏逻辑重复实现

- **入口/函数**: `dayu/host/llm_compaction.py` 与 `dayu/host/compaction_operation.py`
- **文件(行号)**: `llm_compaction.py:71-75` 与 `compaction_operation.py:47-50`
- **输入场景**: N/A（代码重复）
- **实际分支**: N/A
- **预期行为**: 重复逻辑必须抽取到公共模块
- **实际行为**: 两个模块各自实现了几乎相同的 secret redaction regex 和 `_safe_*_message` 函数
- **直接证据**: `llm_compaction.py:73-75` 与 `compaction_operation.py:48-50` 的 `_ASSIGNMENT_SECRET_PATTERN` 和 `_safe_outcome_text` 逻辑几乎一致
- **影响**: 维护成本增加，修改一处可能遗漏另一处
- **建议改法和验证点**: 抽取到 `dayu/host/_compact_redaction.py` 公共模块
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 8-未修复-低-compact_material.py dead code

- **入口/函数**: `dayu/host/compact_material.py` `_required_text()`
- **文件(行号)**: `dayu/host/compact_material.py:1838-1841`
- **输入场景**: N/A
- **实际分支**: `_require_non_empty_text(value, ...)` 在 `value is None` 时已抛 `TypeError`
- **预期行为**: 无 dead code
- **实际行为**: 后续 `if value is None` 分支不可达
- **直接证据**: `_require_non_empty_text` 在 None 时抛异常，后续 None 检查永远不执行
- **影响**: 无运行时影响，降低代码可读性
- **建议改法和验证点**: 删除 `if value is None` 分支
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **`_estimate_preserved_share_from_budget` 的 ref 命名空间一致性**: `preserved_refs`（含 `recent_raw_turn_refs`）与 `source_refs`（含 `material_source_refs`）的命名空间是否完全重叠？若不重叠，交集为空会导致返回 0。

2. **LLM proposal 的 `dropped_ranges` 和 `summarized_ranges` 语义重叠**: LLM 可同时输出两者，当前不校验重叠，是否有互斥约束？

3. **rebuild 并发安全**: `_build_run_input_with_lag_repair` 和 `_catch_up_memory_projection_before_worker` 都可触发 rebuild，两个 dispatch 并发执行时是否有 rebuild 竞态？

## Residual Risk

1. **LLM 输出不可控**: strict JSON proposal 依赖 LLM 遵循 schema，quality checker 是唯一防线。极端情况下 LLM 可能输出合法 JSON 但语义错误的 evidence-backed fact。
2. **budget_after_compact 估算精度**: 基于字符/token 比率的估算在中日文混合内容中可能偏差较大。
3. **旧 schema 数据迁移**: 旧 compacted event（含 `tool_fact_refs`/`verified_fact_refs`）被新 validation 拒绝。需确认 durable store 已迁移或不存在旧数据。
4. **test_compact_material.py 边界条件不足**: 缺少空 material blocks、单 block 全保护、inline delta threshold 精确等于 lag 的测试。
5. **多 pass 合并边界**: 缺少 `max_attempts=0` 的 ValueError 测试和单 pass 退化行为测试。

## Parallel Review Coverage

| Subagent | 覆盖范围 | 关键发现 |
|----------|---------|---------|
| compaction contract | compaction.py, evidence.py, compaction_evidence.py, compact_material.py, compact_payload.py | 枚举名/值不一致、dead code、重命名完整性确认通过 |
| memory projection | memory.py, run_input.py | tiebreaker 字典序、episode summary 上限耦合、dedupe key 碰撞风险 |
| LLM compaction | llm_compaction.py, compact_artifact.py | TimeoutError 未包装、range endpoint 截断、脱敏重复 |
| dispatch/governance | dispatch.py, engine_ingest.py, context_governance.py, host_assembly.py | lag skip 无上限、evidence_labels 空集 bypass、分层干净 |
| test adequacy | 全部测试文件 | compact_material 边界不足、多 pass 合并边界缺失 |

主 reviewer 独立覆盖: agent.py（regex 敏感信息检测改进）、sse_parser.py（空 choices 防御）、tool_call_aggregator.py（负数合成 index）、runtime/config_loader.py（schema 变更）、durable/memory.py（fail-closed item kind 校验）、durable/schema.py（CHECK 约束更新）、tool_runtime.py（accepted evidence envelope）、README sync、pyright 验证。

## Verdict

**PASS_WITH_FINDINGS**

4 个中等 severity findings（TimeoutError 未包装、range endpoint 截断、lag skip 无上限、evidence_labels 空集 bypass），均为边界 case，不影响核心功能正确性。pyright 零错误，307 测试全通过，旧 schema key 拒绝守卫完整，README 同步到位，Host/Engine 分层无违规。

建议在 merge 前修复 Finding 1（TimeoutError 包装）和 Finding 2（range endpoint 断言），其余可作为 follow-up。Finding 3（lag skip 上限）和 Finding 4（evidence_labels 空集）建议在下一个 slice 中处理。
