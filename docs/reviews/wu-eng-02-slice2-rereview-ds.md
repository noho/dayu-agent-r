# WU-ENG-02 Slice 2 Re-Review — AgentDS

## Gate / Work Unit / Slice

- gate: re-review (deepreview)
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 2 — RunnerSpec Policy And OpenAI-Compatible Header Mapping
- reviewer: AgentDS
- review target: AgentCodex fix for accepted code review finding F2 (AgentMiMo)

## 输入

- design_doc: `docs/host/design.md`
- control_doc: `docs/host/issues-implementation-control.md`
- plan: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- implementation artifact: `docs/reviews/wu-eng-02-slice2-implementation-codex.md`
- prior review artifacts: `docs/reviews/wu-eng-02-slice2-code-review-mimo.md`, `docs/reviews/wu-eng-02-slice2-code-review-ds.md`
- fix artifact: `docs/reviews/wu-eng-02-slice2-fix-codex.md`

## Accepted Finding 审查

### Finding: F2 (AgentMiMo) — `DISABLED` policy + `request_identity=None` 组合路径缺少直接测试

**原始 finding**: `tests/engine/runners/openai/test_request_identity.py` 缺少 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时，OpenAI-compatible runner 不应发送 `X-Client-Request-Id` header 的直接测试。

**Controller 裁决**: accepted（Low，不阻塞）。

**AgentCodex fix**: 在 `tests/engine/runners/openai/test_request_identity.py` 新增 `test_policy_disabled_without_identity_does_not_send_header`（line 160-175）。

**Fix 逐项检验**:

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 测试构造 DISABLED policy runner | PASS | line 168: `_runner(policy=ClientCorrelationPolicy.DISABLED)` |
| 测试传入 `request_identity=None` | PASS | line 173: `await _collect(runner, request_identity=None)` |
| 测试断言不发送 header | PASS | line 175: `assert "X-Client-Request-Id" not in session.calls[0][2]` |
| 测试通过 | PASS | `pytest ...::test_policy_disabled_without_identity_does_not_send_header` → 1 passed |
| docstring 声明意图 | PASS | line 161-162: "policy disabled 且 request identity 缺失时不发送客户端关联 header" |
| 未修改生产代码 | PASS | git diff 确认仅 `test_request_identity.py` 包含本次 fix 新增 |
| 未修改 control doc / README | PASS | 无相关 diff |
| 未 commit / push / PR | PASS | `git log` 无新 commit |

**Finding closure 状态**: **已关闭**。新增测试真实覆盖了 accepted finding 要求的 `DISABLED + request_identity=None` 组合，断言明确（header 不在 outbound headers 中），测试通过。

---

## Slice 2 生产代码 Plan 合规复查

对 Slice 2 已有生产代码逐项复查，确认 fix 未引入回归：

### ClientCorrelationPolicy enum

| 检查项 | 结果 | 证据 |
|--------|------|------|
| enum 定义完整 | PASS | `runner_spec.py:72-89`，`DISABLED` + `OPENAI_X_CLIENT_REQUEST_ID` |
| docstring 声明 provider-protocol-specific | PASS | `runner_spec.py:73-78` |
| 无 provider 字符串分支 | PASS | `runner.py:150-194` 仅用 `is` 比较 enum member |

### RunnerSpec required field

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `client_correlation_policy` 无默认值 | PASS | `runner_spec.py:281` |
| 生产装配显式补齐 | PASS | `host_assembly.py:870` |
| Host freeze/restore 正确 | PASS | `_execution_config_projection.py:154-156, 183-185` |

### OpenAI runner header helper

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Content-Type 默认 + static headers 合并 | PASS | `runner.py:170-172` |
| DISABLED → 不发送 header | PASS | `runner.py:174-175` |
| OPENAI + identity 非 None → 发送 | PASS | `runner.py:186-189` |
| OPENAI + identity None → 不发送 | PASS | `runner.py:186` 条件 `if request_identity is not None` |
| 静态 header 冲突 case-insensitive → ValueError | PASS | `runner.py:180-185, 197-209` |
| 冲突在 HTTP post 前 fail-fast | PASS | `_build_request_headers` 在 `_do_attempt` 前调用 |
| Transport retry 复用同一 header | PASS | `runner.py:378-381` headers 在 retry loop 外构建一次 |

### Response x-request-id 采集

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `_extract_provider_request_id` 未修改 | PASS | diff 中无变更 |
| 所有采集路径完整 | PASS | `_do_attempt` 各分支 `provider_request_id` 赋值不变 |

---

## New Findings

**None.**

本次 fix 仅新增一个测试函数，未修改生产代码、control doc、README。fix 范围严格限制在 accepted finding 要求的窄测试补充，无越界行为。

---

## Validation Commands / Results

### 测试执行

```
source .venv/bin/activate && pytest \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py \
  tests/host/test_effective_execution_config.py -q

62 passed in 0.40s
```

（原 Slice 2 实现 61 passed + 新增 1 test = 62 passed）

### 新增测试单独验证

```
pytest tests/engine/runners/openai/test_request_identity.py::test_policy_disabled_without_identity_does_not_send_header -v
1 passed in 0.12s
```

### pyright

```
pyright
0 errors, 0 warnings, 0 informations
```

### git 状态确认

- `git log --oneline -5`：最新 commit 为 `b246b1f phaseflow: record WU-ENG-02 slice 1 commit`，无新 commit。
- `git diff --stat`：37 files changed，与 Slice 2 implementation + fix 一致，无越界文件。

---

## Residual Risk

| 风险 | 等级 | Owner | 说明 |
|------|------|-------|------|
| `_build_request_headers` ValueError 传播到 Agent 层 | Low | Slice 3 / 后续 | 与 DS review 原始 residual risk 一致，fail-fast 语义正确 |
| 生产装配默认 DISABLED | Info | 产品/配置决策 | 启用需显式配置，plan 已明确此设计 |
| 全部直接构造点使用 DISABLED，未在生产路径测试 ENABLED | Low | Slice 3 / future | 与 DS review 原始 residual risk 一致 |
| Native Anthropic / Claude Code gateway 未实现 | Info | future adapter | plan 明确标注为 future work unit |
| production assembly 默认 DISABLED 与 static header conflict 上层结构化收口 | Info | Slice 3 / aggregate review | 按 re-review 指令 deferred，不阻塞 Slice 2 |

---

## Final Recommendation

**Proceed.**

Accepted finding F2 已正确修复，新增测试真实覆盖目标场景。生产代码无回归，plan 合规性保持完整。无 new blocking findings。Slice 2 可继续推进。

---

## Verdict

**pass**

- accepted finding closure: F2 (AgentMiMo) 已关闭
- new findings: none
- blocking findings: 0
- tests: 62 passed, 0 failed
- pyright: 0 errors, 0 warnings, 0 informations
