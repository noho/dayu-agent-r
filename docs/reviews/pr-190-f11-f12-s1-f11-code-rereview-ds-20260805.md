# Code Re-Review — AgentDS S1/F11 独立复核

## Identity

- **Reviewer**: AgentDS（独立 re-review，第二路复核）
- **Target**: PR 190 F11/F12 work unit，S1 — F11 Host Tool Trace typed resolver 与 analysis projection，fix 后复核
- **Original DS review**: `docs/reviews/pr-190-f11-f12-s1-f11-code-review-ds-20260805.md`
- **Controller adjudication**: `docs/gateflow/pr-190-f11-f12-s1-f11-code-review-adjudication-20260805.md`
- **Implementation artifact**: `docs/gateflow/pr-190-f11-f12-s1-f11-implementation-20260805.md`
- **Base**: `19a6d6257504876e01da3067bbc4cf33ae99525d`（S1 implementation base）
- **Branch**: `codex/interactive-oracle`
- **Re-review date**: 2026-08-05
- **Artifact path**: `docs/reviews/pr-190-f11-f12-s1-f11-code-rereview-ds-20260805.md`

## Scope

- **Mode**: current changes（relative to S1 implementation base `19a6d625`）
- **Re-review scope**（与 controller adjudication 要求一致）:
  - 唯一 accepted finding DS-03 是否已闭合且未把 128 暴露为 config
  - DS-01、DS-02、MiMo M-001/002/003 与 open questions 是否保持 adjudicated no-change
  - 数值、resolver 行为、cursor/validator contract/public schema 是否未漂移
  - tests/pyright/Ruff/diff-check 证据是否一致性可复现
  - 是否有新 finding
- **Excluded**: 不修改 target、不 stage/commit/push

## Verification Results

### 1. DS-03（page-size 选择说明）— 已闭合

**PASS。** 直接证据：

```python
# dayu/host/durable/tool_trace.py:60-62
_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE = 128
"""仅界定单次 SQLite keyset read I/O；correctness 由完整 exhaustion 与 cursor
不变量拥有，不得开放为 public config。"""
```

逐项验证：

| 检查项 | 结果 | 证据 |
|---|---|---|
| 常量 owner 处有中文说明 | PASS | `tool_trace.py:60-62` |
| 说明 correctness 与该值无关 | PASS | "correctness 由完整 exhaustion 与 cursor 不变量拥有" |
| 说明只界定单次 I/O | PASS | "仅界定单次 SQLite keyset read I/O" |
| 128 未暴露为 config | PASS | 全局搜索 `__all__`、函数签名、参数均不含 `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE` 或 128 |
| 128 仍是模块私有常量 | PASS | 前缀 `_`，未出现在 `__all__`（`tool_trace.py:1723-1752`） |
| 数值未变 | PASS | 仍为 `128` |

### 2. DS-01（validator/parser 双重调用 parse_successful_runner_response_identity）— 保持 no-change

**PASS。** 直接证据：

- `context_events.py:1625`：validator 分支 `parse_successful_runner_response_identity(successful_response_identity)` 未变
- `context_events.py:1654`：parser 分支 `parse_successful_runner_response_identity(_required_mapping(...))` 未变
- 两处之间无 mutation、无缓存、无新增中间状态

原始 adjudication："rejected-as-non-finding"——两处都调用同一公开 owner，validator 负责校验，parser 负责构造 typed value。当前代码与原始 review 时的代码完全一致，未增加任何合并、缓存或接口变更。

### 3. DS-02（cursor 逐行检查）— 保持 no-change

**PASS。** 直接证据：

```python
# tool_trace.py:610-616（未变）
previous_sequence = cursor
for row in page:
    if row.event_sequence <= previous_sequence:
        raise CompactorResponseResolutionError(...)
    previous_sequence = row.event_sequence
```

- `previous_sequence` 初始化为 `cursor`——首行必然 `> cursor` 否则命中 `<=` 检查
- 逐行严格单调递增检查
- 跨页检查（line 632）：`previous_sequence <= cursor` 确保 full page 后 cursor 已推进

原始 adjudication："rejected-as-false-positive"——再增加显式 `> cursor` 只会重复同一不变量。当前代码与原始 review 时一致。

### 4. MiMo M-001/002/003 — 保持 no-change

**M-001**（matching operation/attempt 无 manifest binding 时抛错）：

- `tool_trace.py:678-691`：`operation_matches != manifest_matches` → error。代码与原始 review 一致。
- Adjudication："rejected-as-non-finding"——fail-closed 是设计真源要求。

**M-002**（analysis summary 缺少 parent Host Run id 时抛错）：

- `tool_trace_analysis_rules.py:306-307`：`parent_host_run_id is None → ValueError`。代码与原始 review 一致。
- Adjudication："rejected-as-non-finding"——跳过会把 identity corruption 伪装成没有 response。

**M-003**（page size 不可配置）：

- `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE` 仍是模块私有常量，仅 DS-03 注释增加。与原始 review 一致。
- Adjudication："rejected-as-non-finding"——扩大 public surface 无此需求。

### 5. Open Questions — 保持 no-change

**OQ-01**（failure category identity constraint closed set）：

- `_POST_SUCCESS_REJECTION_CATEGORIES`（`context_events.py:995-999`）未变：`{"quality_check_rejected", "hard_threshold_after_compact"}`
- `_NO_SUCCESS_REJECTION_CATEGORIES`（`context_events.py:1001`）未变：`{"cancellation_requested"}`
- `git diff 19a6d625 -- context_events.py` 中这两组 frozenset 无任何 diff 行

**OQ-02**（resolver corruption 向 Service/CLI 的呈现）：

- `CompactorResponseResolutionError` 仍继承 `HostDurableError`，mismatch fail closed
- 无新增 error suppression、downgrade 或 fallback
- Adjudication："covered-by-later-integration-observation"——S4 拥有

### 6. 数值/行为/contract 漂移检查

| 检查项 | 结果 | 证据 |
|---|---|---|
| page size 数值 128 | 未漂移 | `tool_trace.py:60` |
| resolver keyset exhaustion 逻辑 | 未漂移 | `tool_trace.py:588-636`，完整 while True + short page exit |
| cursor 初始化 `cursor = 0` | 未漂移 | `tool_trace.py:591` |
| `previous_sequence = cursor` 初始化 | 未漂移 | `tool_trace.py:610` |
| 页内递增检查 `<= previous_sequence` | 未漂移 | `tool_trace.py:612` |
| 跨页检测 `<= cursor` | 未漂移 | `tool_trace.py:632` |
| manifest/operation/attempt mismatch fail closed | 未漂移 | `tool_trace.py:687-690` |
| Engine run identity mismatch fail closed | 未漂移 | `tool_trace.py:694-701` |
| duplicate terminal detection | 未漂移 | `tool_trace.py:625-628` |
| schema_version = 2（非 1） | 未漂移 | `tool_trace_analysis_contracts.py` `__post_init__` |
| compactor_responses 字段 | 未漂移 | JSON report 含 `compactor_responses` |
| JSON/Markdown 同源白名单 | 未漂移 | `_compactor_response_json()` 字段集未变 |
| missing limitation reason 字符串 | 未漂移 | `"compactor-response-terminal-not-observed"` |
| `RunnerCallResolvedProjection.compactor_response_identity` 字段签名 | 未漂移 | `ResolvedCompactorResponseIdentity \| None` |
| `__all__` 导出列表 | 未漂移 | `tool_trace.py:1723-1752` 与原始 review 一致，仅新增已在 plan 中的公开类型 |
| `dayu/host/__init__.py` | 未修改 | `git diff 19a6d625 -- dayu/host/__init__.py` 无输出 |
| `_POST_SUCCESS_REJECTION_CATEGORIES` / `_NO_SUCCESS_REJECTION_CATEGORIES` | 未修改 | `git diff` 无相关行 |
| `CompactorResponseDisposition` 枚举值 | 未漂移 | `ACCEPTED`, `ATTEMPT_REJECTED` |

### 7. 验证证据一致性

| 检查项 | 结果 | 实际输出 |
|---|---|---|
| focused owner tests | PASS | `172 passed in 0.97s` |
| test_package_exports regression | PASS | `15 passed in 0.35s` |
| affected pyright | PASS | `0 errors, 0 warnings, 0 informations` |
| affected Ruff | PASS | `All checks passed!` |
| git diff --check | PASS | 无输出（无 whitespace error） |

上述结果与 implementation artifact 声明的 fix 后验证完全一致。

### 8. 新 finding 检查

对全部 production diff（6 个文件）完成 adversarial pass：

- **无新 config/compatibility 路径**：未新增参数、环境变量、配置文件读取、fallback 逻辑
- **无新 public surface 过扩**：`__all__` 仅含 accepted plan 声明的公开类型；未 leak 内部常量或 error 类型
- **无 semantic ownership drift**：identity 仍由 `context_events.py` canonical parser 唯一拥有；Tool Trace resolver 只读解析不产生语义
- **无 schema 意外变更**：`schema_version=2` 为 accepted plan 要求的 fresh breaking contract
- **无 secret/raw payload 泄漏**：`_compactor_response_json()` 字段白名单未扩展
- **无下游补偿**：Service/CLI/renderer 层无 fallback、loose parsing、默认 identity 或兼容分支
- **无 magic number 扩散**：128 仅存在于已知私有常量并已文档化
- **无测试夹具退化**：测试断言基于 owner contract，未固化偶然行为
- **无类型/边界问题**：pyright clean，所有公开 typed dataclass 有 `__post_init__` 校验

## Findings

未发现实质性问题。本次 re-review 验证的唯一 accepted finding DS-03 已正确闭合，所有 rejected findings 与 open questions 保持 adjudicated 状态，数值/行为/contract 无漂移，验证证据可复现一致。

## Open Questions

无。

## Residual Risk

1. **仍由 S4 拥有**：真实 provider 的 successful/rejected Tool Trace evidence、operator-facing error presentation、最大 observed terminal scan page count 仍由 accepted plan S4 拥有。S1 re-review 确认未提前实现或模拟这些语义。

2. **仍由 external consumer owner 拥有**：schema v2 fresh breaking contract 的仓外 consumer 升级需求保持不变。S1 不提供 v1 reader/adapter。

3. **controller 裁决的 residual risk 分类仍成立**：`not-a-risk`（DS-01/02、M-001/002/003）和 `covered-by-later-approved-slice`（S4 evidence）分类在 fix 后不变。

## PASS/FAIL 判定

**PASS。**

- 唯一 accepted finding DS-03 已闭合：page-size owner 处有正确说明，128 未暴露为 config
- DS-01、DS-02、MiMo M-001/002/003 均保持 adjudicated no-change
- DS open questions（OQ-01/02）保持 adjudicated no-change
- 数值、resolver 行为、cursor/validator contract/public schema 未漂移
- tests（172 passed）、pyright（clean）、Ruff（clean）、git diff --check（clean）、test_package_exports（15 passed）证据一致性可复现
- adversarial pass 未发现新 finding

## Still-open findings

无。控制器裁决的所有 finding 状态均为 closed（DS-03 fixed）或 rejected（其余），无 deferred 或 needs-more-evidence 遗留。

## Residual risks

同上 Residual Risk 节三项：S4 evidence coverage、external v2 consumer migration、controller residual risk classification 在 fix 后不变。

## Review gate status

**PASS** — AgentDS 独立 re-review 完成。DS-03 修复验证通过，无漂移、无新 finding。可进入下一 gate。
