# Code Re-Review — Interactive Memory Closure F09

## Scope

- Mode: re-review（controller 裁决前独立复核）
- Branch: `codex/interactive-oracle`
- Base: `47b6a2af`（F08 accepted checkpoint）
- Output file: `docs/reviews/wu-interactive-memory-closure-f09-code-rereview-mimo.md`
- Re-review date: 2026-08-04
- Included scope:
  - `dayu/host/compaction_operation.py`（production diff vs F08 checkpoint）
  - `tests/host/test_dispatch_scheduler.py`（test diff vs F08 checkpoint）
  - `tests/host/test_tool_trace_queries.py`（test diff vs F08 checkpoint）
  - `docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md`（implementation artifact）
  - `docs/reviews/wu-interactive-memory-closure-f09-code-review-mimo.md`（MiMo review artifact）
  - `docs/reviews/wu-interactive-memory-closure-f09-code-review-ds.md`（DS adversarial review artifact）
  - `docs/reviews/wu-interactive-memory-closure-f09-code-review-fix-codex.md`（no-op fix artifact）
- Excluded scope: frozen CLI material、resolver/projector/private SQLite owner（只读验证）、其它未修改文件

## Re-review 验证清单

### 1. No-op fix 合理性

**结论：合理。**

两路 review（MiMo PASS、DS PASS）均未发现 blocking finding。DS 的两个 low/informational findings 被 fix artifact 以充分理由拒绝：

- DS finding 9（low）：`_required_json_int` 不校验正值。拒绝理由成立——该 helper 是类型解析器，不拥有值域语义；所有调用点已通过 `== attempt_number`（`enumerate(start=1)` 产生）间接断言正值，不存在"helper 静默通过后测试仍通过"的反例。
- DS finding 10（informational）：diagnostic code 非 enum。拒绝理由成立——`CompactCandidateDiagnosticV2.code` 与 `CompactValidationIssueCodeV2` 是不同语义层级，强行统一会造成 contract 扩张。

为制造 fix diff 而修改 production/tests，反而会越过 owner boundary 或扩大 accepted F09 scope。no-op decision 正确。

### 2. DS low 拒绝理由成立

**结论：成立。**

逐一复核：

| DS finding | 拒绝理由 | 复核判定 |
|---|---|---|
| 9（low）`_required_json_int` 不校验正值 | helper 职责是类型收窄；调用点已断言 `== attempt_number`（`enumerate(start=1)`） | 成立。正值语义由调用点 contract owner 断言，不属通用 JSON helper |
| 10（informational）diagnostic code 非 enum | `CompactCandidateDiagnosticV2.code` 与 `CompactValidationIssueCodeV2` 是不同层级 | 成立。强行统一会造成 contract/schema 扩张 |
| 11（verified）catch-up 幂等 | positive confirmation，无修复 | 成立。无争议 |

### 3. Production/tests 无 review 后改动

**结论：无 review 后改动。**

- 三文件 diff fingerprint（`47b6a2af` → 当前 workspace）：`cc49580c26c8fea3b8fb64532727056d435e0123c3e72a7e13ed05d4d9f926cd`
- fix artifact 声明的 fingerprint：`cc49580c26c8fea3b8fb64532727056d435e0123c3e72a7e13ed05d4d9f926cd`
- **两者一致。** fix gate 只新增了 durable artifact 文件，未修改 production/test 代码。

`git status` 确认：
- staged changes：无
- unstaged changes：3 个 production/test 文件（与 F08 checkpoint 的 diff）
- untracked：4 个 review artifacts（implementation、mimo、ds、fix-codex）

### 4. Formal resolver 链验证

**结论：未修改、未放松。**

直接证据：

- `dayu/host/durable/tool_trace.py`：未出现在 `git diff 47b6a2af --name-only` 中，未被 F09 修改。
- `_validated_runner_call_contract`（`durable/tool_trace.py:1036-1059`）：row/hot identity check 仍为严格相等（`row.payload_ref != hot_payload.manifest_payload_ref`、`row.payload_digest != hot_payload.manifest_digest` → `HostDurableError`）。
- `resolve_runner_call_projection_from_signal`（`durable/tool_trace.py:362-410`）：仍从 manifest raw JSON 读取 `runner_call_projection_artifact_ref`/`_digest`，缺失时仍报 `HostDurableError("runner-call manifest has no projection artifact ref")`。
- `_validate_manifest_hot_identity`（`durable/tool_trace.py:1612-1685`）：projection triple 仍在 hot/manifest identity tuple 中，未修改。

F09 production diff 只修改了 `compaction_operation.py`（producer boundary），将 `None` 值替换为同源 descriptor 值。resolver、projector、identity check 代码均未变动。

### 5. Baseline 仍 PASS

**结论：全部 PASS。**

| 文件 | Accepted SHA-256 | 重算 SHA-256 | 结果 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da04923193a04c0e...` | `da04923193a04c0e...` | ✓ 未改变 |
| `docs/cli_ci_scenarios.json` | `7c991d14ebc79f9f...` | `7c991d14ebc79f9f...` | ✓ 未改变 |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a...` | `95a09543fc7f1a2a...` | ✓ 未改变 |
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad64315116c3940d...` | `ad64315116c3940d...` | ✓ 未改变 |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926a22406f0...` | `7ba64926a22406f0...` | ✓ 未改变 |

### 6. F09 focused tests 仍 PASS

**结论：4 passed in 0.46s。**

```
tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input
tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept
tests/host/test_dispatch_scheduler.py::test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback
tests/host/test_tool_trace_queries.py::test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch
```

### 7. Pyright 仍 PASS

**结论：0 errors, 0 warnings, 0 informations。**

三个修改文件均通过 pyright 检查。

### 8. Allowed files 精确性

**结论：精确等于四个 approved paths。**

`git diff 47b6a2af --name-only` 输出：
1. `dayu/host/compaction_operation.py`
2. `tests/host/test_dispatch_scheduler.py`
3. `tests/host/test_tool_trace_queries.py`

加上 implementation artifact（untracked），共四个 approved paths。其余三个 review artifacts（mimo、ds、fix-codex）是 gate 产物，不在 approved path 约束内。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 真实 provider/model/response identity 的跨进程 CLI evidence 仍由后续 `interactive.g06.tool-trace-formal` readiness stage 覆盖，与 implementation artifact 分类一致。
- 历史已写入 null row descriptor 的 EventLog 不做兼容读取或 migration，accepted non-goal。
- 五条正式 CLI scenarios 全部未覆盖，covered by later approved evidence stage。
- no-op fix gate 未重复 full pytest/coverage，已由 implementation 与两路 review 覆盖；当前 re-review 确认 diff fingerprint 未变、focused tests 仍 PASS。

## Conclusion

**PASS**

Re-review 验证全部通过：

1. **No-op fix 合理**：两路 review 均 PASS，DS low/informational findings 拒绝理由充分，无需修改 production/tests。
2. **DS low 拒绝理由成立**：finding 9（类型 helper 不拥有值域语义）和 finding 10（不同语义层级不强制统一）均经独立复核确认。
3. **Production/tests 无 review 后改动**：diff fingerprint `cc49580c...` 与 fix artifact 声明完全一致。
4. **Formal resolver 链未修改、未放松**：`durable/tool_trace.py` 不在 F09 diff 中，identity check、projection resolver、manifest/hot validator 均保持原状。
5. **Baseline 仍 PASS**：5 个 frozen baseline/evidence 文件 SHA-256 全部匹配。
6. **Focused tests 仍 PASS**：4 passed in 0.46s。
7. **Pyright 仍 PASS**：0 errors, 0 warnings, 0 informations。
8. **Allowed files 精确**：四个 approved paths，无越界修改。

F09 slice 在正确的 owner boundary 修复了 EventLog row descriptor null 导致 formal resolver fail-closed 的根因。所有 identity 链从同一 transaction 已写出的 descriptor 派生，无重复计算、无分裂来源、无 fallback 或兼容 shim。两路 review 结论一致，no-op fix gate 未引入额外改动。可进入 controller 裁决。
