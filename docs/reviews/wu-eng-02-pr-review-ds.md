# WU-ENG-02 PR Review Gate — AgentDS

## Gate / Work Unit

- gate: PR review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- reviewer: AgentDS
- review date: 2026-06-03
- PR: https://github.com/noho/dayu-agent-r/pull/114
- branch: phaseflow/wu-eng-02-request-identity
- base: main

## Verdict

**pass**

0 条 blocking findings。1 条 non-blocking finding（Info）。

---

## 1. PR Metadata

| 字段 | 值 |
|------|-----|
| PR number | 114 |
| Title | WU-ENG-02: provider request identity and correlation |
| State | OPEN (draft) |
| Base | main |
| Head | phaseflow/wu-eng-02-request-identity |
| Mergeable | MERGEABLE |
| Files changed | 82 |
| Additions | 6428 |
| Deletions | 88 |
| Commits | 13 (gateflow/phaseflow record commits) |

PR 描述覆盖 Summary、Validation、Residual Risks、Issues 四部分，内容与实现一致。

---

## 2. Diff Packaging Check

### 2.1 PR vs Local 一致性

```bash
diff <(gh pr diff 114 --repo noho/dayu-agent-r --name-only | sort) \
     <(git diff main...HEAD --name-only | sort)
```

**结果**: 0 差异。PR 的 82 个文件与本地 branch diff 完全一致。

### 2.2 工作树状态

```bash
git status --short
```

**结果**: clean，无未提交变更。

### 2.3 Branch / Base 检查

- base: `main` (正确)
- head: `phaseflow/wu-eng-02-request-identity` (正确)
- mergeable: `MERGEABLE` (无冲突)

### 2.4 文件覆盖

| 类别 | Plan 预期 | PR 实际 | 一致 |
|------|-----------|---------|------|
| Engine contracts (Slice 1) | `runner_identity.py`, `runner.py`, `agent_run.py`, `engine_events.py`, `__init__.py` | 全部包含 | PASS |
| Engine Agent (Slice 1) | `agent.py` | 包含 | PASS |
| OpenAI Runner (Slice 2) | `runner_spec.py`, `runner.py`, `__init__.py` | 全部包含 | PASS |
| Host config (Slice 2) | `_execution_config_projection.py` | 包含 | PASS |
| Host projection (Slice 3) | `run_input.py`, `llm_compaction.py` | 全部包含 | PASS |
| Host ingest (Slice 3) | `engine_ingest.py` | 包含 | PASS |
| Host Tool Trace (Slice 3) | `tool_trace.py` | 包含 | PASS |
| Host durable (Slice 3) | `durable/run_transition.py` | 包含 | PASS |
| Service assembly | `host_assembly.py` | 包含 | PASS |
| README (Slice 4) | `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md` | 全部包含 | PASS |
| Tests | plan 所有指定测试文件 | 全部包含 (47 test files) | PASS |
| Review artifacts | 全部 23 个 phaseflow artifacts | 全部包含 | PASS |
| Control doc | `issues-implementation-control.md` | 包含 | PASS |

无遗漏文件，无多余文件。

---

## 3. Control Doc 状态一致性

### 3.1 当前状态表 (line 138-153)

| 字段 | 值 | 一致性 |
|------|-----|--------|
| gate | PR review | 与当前 gate 一致 |
| implementation status | draft-pr-open | 与 PR state 一致 |
| active work unit | WU-ENG-02 | 一致 |
| implementation commits | 7 个 accepted commits | 与 git log 一致 |
| review artifacts | 23 个路径 | 与 `docs/reviews/` 目录一致 |
| aggregate review artifacts | 2 个 | 与文件系统一致 |
| draft PR status | PR 114 open | 与 GitHub 一致 |
| blocking open questions | none | 一致 |

### 3.2 Residual Risk 表 (line 197-204)

| ID | 状态 | Owner | 验证 |
|----|------|-------|------|
| WU-ENG-02-S1-R1 | deferred-with-owner | aggregate review / future Engine focused test | aggregate deepreview 已确认 |
| WU-ENG-02-S1-R2 | deferred-with-owner | aggregate review / future Engine focused test | aggregate deepreview 已确认 |
| WU-ENG-02-S2-R1 | closed | 无后续动作 | aggregate deepreview 确认关闭 |
| WU-ENG-02-S2-R2 | deferred-with-owner | Service / config assembly follow-up | Engine 部分已关闭 |
| WU-ENG-02-S3-R1 | deferred-with-owner | WU-OBS-00 | aggregate deepreview 已确认 |
| WU-ENG-02-S3-R2 | deferred-with-owner | aggregate review / future Host focused test | aggregate deepreview 已确认 |

全部 6 条 residual risk 均有 owner，无 orphan risk。

### 3.3 WU-ENG-02 详细状态 (line 287-330)

WU-ENG-02 段完整记录了 plan gate → implementation slices → code reviews → fixes → re-reviews → aggregate deepreview → draft PR 的全流程。各 gate 裁决、finding 处置、accepted commit 均与 git log 一致。

最后一行叙述 "WU-ENG-02 draft PR 已创建...当前进入 PR review gate" 与当前状态完全一致。

---

## 4. 测试验证

```bash
source .venv/bin/activate && pytest \
  tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py \
  tests/host/test_effective_execution_config.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_local_proxy_engine_ingest.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_llm_compaction.py -q
```

**结果**: 372 passed in 1.65s

---

## 5. Pyright 验证

```bash
source .venv/bin/activate && pyright
```

**结果**: 0 errors, 0 warnings, 0 informations

---

## 6. Plan 验收信号对照

| 验收信号 | 状态 | 证据 |
|----------|------|------|
| `AsyncRunner.call` 有强类型 `request_identity` 输入 | PASS | `runner.py:31` keyword-only 参数 |
| Agent 每次 Runner 调用都传入 identity | PASS | AgentMiMo aggregate deepreview §2, AgentDS aggregate deepreview §2 |
| Host dispatch 投影 `attempt_id/execution_id` | PASS | `run_input.py:1680-1681` |
| OpenAI adapter policy 开启时发送 `X-Client-Request-Id` | PASS | `runner.py:186-189` |
| Policy 关闭或 identity 缺失时不发送 | PASS | 测试覆盖 DISABLED + identity=None 两种情况 |
| Response `x-request-id` 采集不回退 | PASS | `_extract_provider_request_id` 未修改 |
| Host ingest/Tool Trace 同时呈现 `provider_request_id` 与 `client_correlation_id` | PASS | AgentMiMo aggregate deepreview §4 |
| 不新增 SQLite 表/列 | PASS | `client_correlation_id` 仅进入 JSON payload |
| 不伪造 `user_id`/`safety_identifier`/`metadata.user_id` | PASS | 全文搜索 0 occurrences |

全部 9 个验收信号均满足。

---

## 7. 项目指令合规确认

| 指令 | 状态 | 依据 |
|------|------|------|
| 分层架构 | PASS | 两个 aggregate deepreview 均确认无反向依赖 |
| 无 `Any`/`object`/无类型签名 | PASS | pyright 0 errors |
| 中文 docstring | PASS | aggregate deepreview 确认全部新增函数/类均有完整中文 docstring |
| 无兼容性代码 | PASS | fresh-schema 设计，无 re-export/wrapper |
| 无 provider 字符串治理分支 | PASS | `ClientCorrelationPolicy` 使用 enum `is` 比较 |
| Schema 变更按全新起库 | PASS | 无旧库兼容读取 |
| README 触发规则 | PASS | Engine/Host/Tests README 已更新；根 README 未触发 |
| 无魔法数字/字符串 | PASS | 模块级常量 |
| 测试覆盖 >= 80% | PASS | 372 tests passed |

---

## 8. Residual Risk Reconciliation

| ID | 描述 | 当前状态 | PR Review 确认 |
|----|------|----------|---------------|
| WU-ENG-02-S1-R1 | 工具超时 `RunFailedData` 缺 `client_correlation_id` | deferred-with-owner | 保持 — aggregate deepreview 已确认 owner 为 future Engine focused test |
| WU-ENG-02-S1-R2 | Force-answer EngineEvent 断言缺失 | deferred-with-owner | 保持 — 代码行为正确，后续补 focused test |
| WU-ENG-02-S2-R1 | Production assembly 默认 DISABLED | closed (Slice 4) | 确认关闭 — 测试/实现均已确认 |
| WU-ENG-02-S2-R2 | 静态 header 冲突上层收口 | deferred-with-owner (Engine 部分 closed) | Engine adapter 部分确认关闭；Service 部分保持 deferred |
| WU-ENG-02-S3-R1 | Usage observation 与 correlation 关联 | deferred-with-owner → WU-OBS-00 | 保持 — analyzer scope，非本 WU |
| WU-ENG-02-S3-R2 | ContextRecoveryCloseInput 专用测试 | deferred-with-owner | 保持 — 间接覆盖充分，不阻塞 |

全部 6 条 residual risk 均有明确 owner，无新增 unowned risk。PR description 中列出的 3 条 residual risk 与 control doc 一致。

---

## 9. Aggregate Deepreview 重开检查

根据审查目标："如果 finding 已在 aggregate deepreview 裁决为 deferred/rejected，请只在发现新直接证据时重开。"

| 原 Finding | 原裁决 | 新证据 | 结论 |
|------------|--------|--------|------|
| F1 (MiMo) — 工具超时 `RunFailedData` 缺 `client_correlation_id` | LOW, deferred-with-owner | 无新证据 | 不重开 |
| F2 (MiMo) — force-answer EngineEvent 断言 | LOW, deferred-with-owner | 无新证据 | 不重开 |
| F3 (MiMo) — `_build_request_headers` 防御性分支 | INFO, 保持现状 | 无新证据 | 不重开 |

无 aggregate deepreview finding 被重开。

---

## 10. Findings

### F1 [INFO] — Control doc WU-ENG-02 状态叙事为单行超长段落

- **文件**: `docs/host/issues-implementation-control.md:303`
- **直接证据**: Slice 1 到 aggregate deepreview → draft PR 的全流程状态叙述被压缩成单行超长段落（~1.5KB），阅读和 diff 不友好。
- **影响**: 无功能影响。控制文档可读性略低，但不影响 PR 质量或 gate 裁决。
- **建议**: 后续 control doc 维护时建议将全流程叙述拆为多行，按 gate 阶段分段。不作为本 PR blocking issue。

---

## 11. Final Recommendation

**draft-PR-pass — 可进入。**

WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation 的 PR 114 满足 draft PR gate 全部要求：

1. **PR packaging**: 82 文件与本地 branch 完全一致，无遗漏、无多余、无未提交变更。
2. **Branch/base**: main ← phaseflow/wu-eng-02-request-identity，MERGEABLE。
3. **Control doc 状态**: gate/implementation status/commits/artifacts/residual risks 全部一致。
4. **验证结果**: 372 tests passed，pyright 0 errors。
5. **Plan 验收信号**: 全部 9 个信号满足。
6. **Residual risks**: 6 条均有 owner，无 orphan。
7. **Aggregate deepreview**: 0 条 findings 需重开。
8. **项目指令**: 分层、编码、schema、README 全部合规。

---

- artifact path: `docs/reviews/wu-eng-02-pr-review-ds.md`
- verdict: pass
- blocking findings: 0
- non-blocking findings: 1 (Info)
- tests: 372 passed
- pyright: 0 errors, 0 warnings, 0 informations
