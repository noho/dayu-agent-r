# WU-ENGINE-01 Slice 3 Validation Artifact Review

## Scope

- Mode: current changes — validation artifact review (not a diff review)
- Review target: `docs/reviews/wu-engine-01-slice3-validation-codex-20260602.md`
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Output file: `docs/reviews/wu-engine-01-slice3-code-review-ds-20260602.md`
- Included scope: validation artifact claims verification, full target validation re-run, boundary re-audit, README decision re-check, raw_payload residual re-check
- Parallel review coverage: 无

## Review Method

本 review 是独立验证，不是实现 review。验证逻辑：

1. 重跑 approved plan Slice 3 的 full target validation 命令，检查结果是否与 artifact 声称一致。
2. 独立搜索 `raw_payload=dict(parsed)` 残留，检查所有 `原始载荷` / `provider 原始` 命中是否在 `不承诺保留` 上下文内。
3. 检查所有 call site 是否使用 diagnostic_payload helper。
4. 按 CLAUDE.md README 触发更新规则，逐条验证 artifact 的 README 决策是否有直接证据支撑。
5. 检查 validation artifact 是否覆盖 approved Slice 3 的全部 objective。

## Findings

未发现实质性问题。

## Evidence Log

### 1. Full Target Validation 重跑结果

```text
95 passed in 0.54s
```

```text
0 errors, 0 warnings, 0 informations
```

与 artifact 第 58-79 行声称一致（95 passed, 0 errors）。pyright 仅输出版本提示 `v1.1.409 -> v1.1.410`，不是类型错误。

### 2. raw_payload=dict(parsed) 残留检查

```bash
rg -n "raw_payload\s*=\s*dict\(parsed\)|raw_payload=dict\(" dayu/engine
```

结果：无匹配。所有 `raw_payload` 写入点均使用 helper 函数。

Call site 确认：
- `non_stream_parser.py:238-241` → `provider_error_diagnostic_payload(parsed, source=_PROVIDER_ERROR_CODE)`
- `sse_parser.py:250` → `invalid_utf8_diagnostic_payload(chunk, final_decode=final_decode)`
- `sse_parser.py:352-354` → `provider_error_diagnostic_payload(parsed, source=_PROVIDER_ERROR_CODE)`
- `sse_parser.py:384-387` → `protocol_object_diagnostic_payload(parsed, source=_MISSING_CHOICES_CODE, reason=_MISSING_CHOICES_AND_USAGE_REASON)`
- `sse_parser.py:423-426` → `protocol_object_diagnostic_payload(parsed, source=_MISSING_CHOICES_CODE, reason=_NO_VALID_CHOICE_OBJECT_REASON)`
- `runner.py:900` → `http_error_diagnostic_payload(decoded)`

### 3. "原始载荷" / "provider 原始" 上下文检查

全部 6 处命中及上下文：

| 文件(行号) | 上下文 |
|---|---|
| `diagnostic_payload.py:6` | 模块 docstring："不保存完整 provider 原始载荷" |
| `engine/README.md:190` | "不保证保留 provider 原始 payload" |
| `runner_events.py:156` | "不承诺保留 provider 原始报错载荷" |
| `runner_events.py:178` | "不承诺保留 provider 原始报错载荷" |
| `engine_events.py:299` | "不承诺保留 provider 原始报错载荷" |

全部命中均处于"不承诺保留"语义中，非旧承诺残留。artifact 第 51-53 行声称准确。

### 4. README 决策验证

**dayu/engine/README.md**（第 190 行）：
```
- `raw_payload`：Runner / Provider 诊断事件上的可选诊断 JSON。该字段是有界、脱敏、摘要化的诊断载荷，不保证保留 provider 原始 payload；核心错误事实仍通过 `message`、`error_code`、`provider_request_id` 等强类型字段表达。
```
已同步 ✓。符合 `dayu/engine/README.md` 作为 Engine 开发手册的职责。

**根目录 README.md**：未命中 `raw_payload` / `diagnostic` / `provider error` / `协议错误` 相关内容（仅命中 `output/` 下诊断辅助文件目录说明，与 runner diagnostic 无关）。CLAUE.md 触发条件是项目级使用方式、CLI、trace/render 入口变化 → 未触发。不更新正确。

**dayu/host/README.md**：命中 `diagnostic` 广泛存在于 Host 内部低层 diagnostic 路径说明中，但均为 Host 层面的 EventLog / Context Governance 概念，与 OpenAI runner `raw_payload` 语义无关。CLAUE.md 触发条件是 Host production 行为、状态机、EventLog schema 变化 → 未触发。不更新正确。

**tests/README.md**：未命中 `raw_payload`。OpenAI runner 测试目录说明（line 170）已覆盖"协议错误、HTTP error 分类"、"非法 UTF-8"、"SSE 与 non-stream"边界，与本次变更的测试覆盖范围一致。CLAUE.md 触发条件"`tests/` 修改"满足，但按约束"先检查变更是否属于该 README 的职责范围与目标读者；只有属于时才实际修改"。本次未新增测试分层、未改变测试运行方式、未改变维护约定。不更新正确。

artifact 第 23-38 行 README 决策声称准确。

### 5. Boundary Audit 重确认

```text
git status --short
 M docs/host/host-core-followup-implementation-control.md
?? docs/reviews/wu-engine-01-slice3-validation-codex-20260602.md
```

工作区干净。未修改 Host production、未修改 schema、未修改 provider state sealed union。

### 6. 已承诺 Slice 3 变更覆盖

Approved plan Slice 3 的 exact changes：
- "只在 Slice 1 / Slice 2 尚未完成 README 同步时补齐 `dayu/engine/README.md`" → 已在 Slice 2 完成（`08fd353`），Slice 3 确认无需再补齐。
- "不更新 `docs/host/design.md`" → 未修改。
- "不更新根目录 README、`dayu/host/README.md`、`tests/README.md`，除非 implementation 实际改变了对应文档职责内的稳定说明" → 已逐条验证，均不需更新。

### 7. Git History 一致性

本地历史包含所有 accepted commits：
```
08fd353 gateflow: record WU-ENGINE-01 slice 2
3857e23 gateflow: accept WU-ENGINE-01 slice 2
748b743 gateflow: record WU-ENGINE-01 slice 1
dba6513 gateflow: accept WU-ENGINE-01 slice 1
e55f05e gateflow: record accepted plan for WU-ENGINE-01
```

与 artifact 第 11 行声称一致。

## Open Questions

无。

## Residual Risk

- 未执行真实 provider 网络 smoke。这是 approved plan 明确排除的范围（本 work unit 是 diagnostic payload 语义与边界验证），不属于本 slice 缺失。
- 未运行全仓 pytest。approved plan 的 Slice 3 要求 full target validation（5 个文件），不是全仓。当前全仓范围超出本 work unit scope。
- 未执行 aggregate deepreview。该动作属于 controller 后续 gate。

## Conclusion

**PASS**。无 blocking / high / medium finding。

验证结论：
- Approved Slice 3 的 full target validation 重跑通过：95 passed, pyright 0 errors。
- `raw_payload=dict(parsed)` 残留：无。
- 所有 call site 均使用 diagnostic_payload helper。
- README 决策符合 CLAUDE.md 职责约束，逐条有直接证据。
- 不存在需要 design_doc / public contract 重新裁决的问题。

建议 controller 接受本 review，推进到 WU-ENGINE-01 accepted Slice 3 checkpoint。
