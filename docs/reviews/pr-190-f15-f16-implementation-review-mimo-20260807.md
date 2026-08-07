# PR190 F15/F16 Implementation Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `580b1427` (HEAD at review start)
- Output file: `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`
- Included scope: `git diff 580b1427` 全部 10 个已改文件 + `workspace/tmp/prompt_observe_calibration.py` + `workspace/tmp/f14_real_cli_observation.py` + `utils/cli_ci_run_observation.py`（新增 tracked helper）
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer 直接走读）

## Findings

### 001-未修复-P1-`_segment_terminal_facts` 在 evidence invalid 时崩溃导致整个 harness 中断

- **入口/函数**: `workspace/tmp/f14_real_cli_observation.py` → `_segment_terminal_facts()`
- **文件(行号)**: `workspace/tmp/f14_real_cli_observation.py:332-363`
- **输入场景**: 任一 scenario 的 `_run_pty()` 抛出异常（如 OSError），或 `_canonical_run_terminal_observation` 抛出 `RunObservationError`
- **实际分支**: `_execute()` 的 try/except 捕获 `_run_scenario()` 异常后，继续调用 `_segment_terminal_facts()`
- **预期行为**: evidence 文件缺失或 shape 为 `evidence_status: "invalid"` 时，`_segment_terminal_facts` 应返回 `(0, False)` 并允许 harness 继续后续 scenario
- **实际行为**: 两条崩溃路径——
  1. `_run_pty` 异常 → `run-terminals.json` 未写入 → `_segment_terminal_facts` 读取时 `FileNotFoundError` 传播到 `_execute` 外层
  2. observation 失败 → `run-terminals.json` 写入 `{"evidence_status": "invalid", ...}`（无 `summary` key）→ `payload.get("summary")` 返回 `None` → `summary.get("accepted")` 抛出 `AttributeError`
- **直接证据**: `_segment_terminal_facts:347-349`:
  ```python
  payload = cast(dict[str, JsonValue], json.loads(path.read_text(encoding="utf-8")))
  summary = cast(dict[str, JsonValue], payload.get("summary"))
  accepted = summary.get("accepted")  # AttributeError if summary is None
  ```
  `_execute:296-316` 中 `_segment_terminal_facts` 在 try/except 之外调用
- **影响**: 单个 scenario 失败会中断整个 harness，后续 scenario 全部丢失证据
- **建议改法和验证点**: 在 `_segment_terminal_facts` 开头检查 `"summary"` key 是否存在；对 `FileNotFoundError` 返回 `(0, False)`；对 shape invalid 记录诊断并返回 `(0, False)`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高（harness 单点故障导致证据丢失）

### 002-未修复-P2-execution-index-f15-f16.json 缺少 plan 要求的字段

- **入口/函数**: `workspace/tmp/f14_real_cli_observation.py` → `main()` 生成 index
- **文件(行号)**: `workspace/tmp/f14_real_cli_observation.py:628-657`
- **输入场景**: 正常 harness 完成后生成 index
- **实际分支**: index 只包含 `run_terminal_summary.accepted`、`dependency_gate.status`、`evidence_status.status`
- **预期行为**: plan Section 5.5 要求 index 包含 `process_outcomes`（逐行 kind/exit_code）、`run_terminal_summary`（succeeded/failed/cancelled/lost/missing/duplicate/invalid 计数）、`run_terminal_records`（per-run descriptor/digest）、`context_compaction_observation`、`secret_scan`
- **实际行为**: `run_terminal_summary` 只有 `{"accepted": count}`；无 `process_outcomes`、`run_terminal_records`、`context_compaction_observation`、`secret_scan`
- **直接证据**: `f14_real_cli_observation.py:631-636`:
  ```python
  "run_terminal_summary": {
      "accepted": chain.accepted_count,
  },
  ```
- **影响**: fresh evidence index 不完整，审计者无法从 index 本身判断 per-Run 成败、process outcome 分布、compaction observation 或 secret scan 状态
- **建议改法和验证点**: 从 `run-terminals.json` 的 `to_json()` output 提取完整 summary 字段；收集 per-scenario `process_outcome`；在 harness 结束前执行 secret scan。tracked helper 已提供全部结构化数据，consumers 只需透传
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中（temporary harness evidence 不完整，但 tracked helper contract 已被 deterministic tests 锁定）

### 003-未修复-P3-`RunObservationRole.INDEFINED` 枚举值已定义但从未使用

- **入口/函数**: `utils/cli_ci_run_observation.py` → `RunObservationRole` 枚举
- **文件(行号)**: `utils/cli_ci_run_observation.py:68`
- **输入场景**: N/A（dead code）
- **实际分支**: harness 的 `_run_observation_roles()` 只产出 `REQUIRED` 和 `DEPENDENT`
- **预期行为**: plan 5.1 声明三类 role（required/dependent/independent），independent 用于无依赖的 mandatory observation action
- **实际行为**: `INDEPENDENT = "independent"` 已定义但 harness 和 tests 从未赋值
- **直接证据**: `prompt_observe_calibration.py:862-874` 只映射 REQUIRED/DEPENDENT
- **影响**: 无功能影响；若未来需要标记 independent mandatory action，需修改 harness
- **建议改法和验证点**: 当前无需修改；记录为 known gap。若后续有 independent mandatory action 需求再启用
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（dead enum value）

## Open Questions

- 无。

## Residual Risk

1. **F15 格式矩阵偏窄**: 当前 deterministic test 只覆盖 answer anchor 的空行/多行/列表/表格组合。summary、fact、intent、reference 各 section 只有一个基本的空白+多行 case。若未来这些 section 出现更复杂的 Markdown 组合（如嵌套列表、代码块），当前 test 不会捕获回归。风险可控，因为 normalizer 逻辑对所有 section 统一生效，但 matrix 可扩展。
2. **F16 tracked helper session_id 未传递**: observation window 使用 `session_id=None`，读取 DB 内所有 session 的 events。当前 CLI CI 场景中每个 workspace 只有一个 session，功能无误。若未来多 session 共享 workspace，需传递 exact session_id 以避免跨 session event 混入。
3. **F16 in-flight dependency check window 非 frozen**: `_run_pty` 中的 dependency check 使用 `_db_latest_event_sequence(workspace)` 作为 window end，此时 process 仍在运行。这在 SQLite concurrent read 下是安全的，但严格意义上不符合 plan "frozen end" 语义（frozen end 适用于 post-execution observation）。in-flight check 的 "snapshot" 行为功能正确，但文档未明确区分。

## Review Conclusion

F15 核心修复正确：`_CanonicalPreviousReplacementProjection` 从单一 canonical typed projection 同步生成 packed blocks 与 readable view，每文本叶子经 `normalized_material_text()` 恰好一次，answer anchor 先形成 canonical typed anchor 再正向渲染 block text，strict pair validator 保持 exact equality，reopen/recovery 复用同一 pair，F14 frontier 零漂移。

F16 tracked helper 正确实现：filtered keyset window 读尽 frozen window、terminal-specific reason shape 严格校验（cancel 的合法 `mode`、lost 的合法 `orphan_proof`、succeeded/failed 的 exact `{reason}`）、duplicate terminal fail-closed、process outcome 与 Run terminal 分离、dependency gate 只以 `RUN_SUCCEEDED` 为 success。

主要风险是 temporary harness `_segment_terminal_facts` 的单点故障（P1）和 execution index 字段不完整（P2），tracked helper contract 本身由 15 个 deterministic tests 锁定且全部通过。
