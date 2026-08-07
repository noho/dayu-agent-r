# PR 190 F15 / F16 Final Re-Review (MiMo)

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `580b1427`
- Output file: `docs/reviews/pr-190-f15-f16-final-rereview-mimo-20260807.md`
- Included scope: `580b1427` 相对全部 tracked diff（11 文件）、`utils/cli_ci_run_observation.py`（untracked）、`tests/cli/test_cli_ci_run_observation.py`（untracked）、`workspace/tmp/prompt_observe_calibration.py`（ignored, 3077 行完整阅读）、`workspace/tmp/f14_real_cli_observation.py`（ignored, 1447 行完整阅读）
- Excluded scope: 无
- Parallel review coverage: 无
- Gateflow binding: `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`、`docs/gateflow/pr-190-f15-f16-implementation-20260807.md`、`docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`、`docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`

## Findings

### 001-P2-prompt_harness_缺失_final_secret_scan

- **入口/函数**: `workspace/tmp/prompt_observe_calibration.py` `main()` (line 2954-3072)
- **文件(行号)**: `workspace/tmp/prompt_observe_calibration.py:2954-3072`
- **输入场景**: 47 个 scenario 全部执行完毕后
- **实际分支**: `main()` 在 scenario loop 结束后只写 `run-completion.json` (line 3057-3071)，不调用 `scan_public_evidence_files()`
- **预期行为**: accepted plan 要求 "独立 path hygiene 必须扫描整个 public evidence tree"；calibration harness 作为 F16 挂载的 47-scenario 矩阵执行器，应在全部 evidence 写入后执行 final secret scan 与 path hygiene
- **实际行为**: 完全缺失 secret scan。evidence tree 中的 `stdout.txt`、`command.json`、`tool-trace.json`、`run-terminals.json` 等文件中的 redaction 失败不会被检测。`_redaction_pairs()` 虽用精确值替换，但 PTY transcript 可能包含未预期的 secret 暴露路径（如 CLI 错误信息、provider 响应中回显的 key）
- **直接证据**: `main()` line 2968-3072 无任何 `scan_public_evidence_files` 调用；`_run_scenario()` line 2664-2939 写入 12+ evidence 文件但无 scan
- **影响**: 如果 redaction 有遗漏，secret 明文进入 public evidence tree 且无 fail-closed 检测
- **建议改法和验证点**: 在 `main()` 的 scenario loop 结束后、写 `run-completion.json` 前，调用 `run_observation.scan_public_evidence_files()` 扫描整个 `run_root/evidence/` tree，使用 `SECRET_ENV_NAMES` 对应的实际环境值 + canary 作为 exact probes；结果写入 `evidence/public/secret-scan.json` 并在 `run-completion.json` 中引用
- **修复风险（低/中/高）**: 低 — 复用 tracked helper，不改产品代码
- **严重程度（低/中/高/严重）**: 中 — real rerun 前的 harness 证据完整性 gap；redaction 已有但无独立验证

### 002-P3-f14_harness_execution_index_未被_secret_scan_覆盖

- **入口/函数**: `workspace/tmp/f14_real_cli_observation.py` `main()` (line 1216-1442)
- **文件(行号)**: `workspace/tmp/f14_real_cli_observation.py:1387-1441`
- **输入场景**: 所有 segment 执行完毕、public evidence 采集后
- **实际分支**: `_secret_scan()` 在 line 1387-1391 执行，此时 evidence tree 包含 7 个 segment 的 per-scenario evidence。但 `execution-index-f15-f16.json` 在 line 1403-1441 才写入，`context-compaction-observation.json` 在 line 1385-1386 写入（scan 之前但文件内容在 scan 之后才完整）
- **预期行为**: final secret scan 应覆盖全部拟公开 evidence 文件，包括 execution-index 本身
- **实际行为**: `_public_evidence_files()` (line 963-978) 在 scan 调用时枚举 `evidence_root.rglob("*")`，此时 index 和 context-compaction 文件尚未写入或刚写入。execution-index 中的 `source_digests`、`rows` 等字段可能包含敏感路径或 token 摘要；若 index 被注入 secret，不会被检测
- **直接证据**: `_secret_scan()` 调用在 line 1387；`_write_json(run_root / "evidence" / "execution-index-f15-f16.json", ...)` 在 line 1403；`_public_evidence_files()` 在 scan 内部同步枚举
- **影响**: execution-index 和 context-compaction-observation 文件未被 secret scan 覆盖；index 中引用的 `secret_scan.record_path` 和 `record_digest` 反映的是不含 index 自身的 scan 结果
- **建议改法和验证点**: 将 `_secret_scan()` 调用移到所有 evidence 文件写入之后（包括 index 和 context-compaction），或在 index 写入后执行第二轮 scan 并更新 index 中的 secret_scan 引用
- **修复风险（低/中/高）**: 低 — 调整执行顺序即可
- **严重程度（低/中/高/严重）**: 低 — index 是 metadata 汇总，实际 secret 暴露风险低于 per-scenario evidence 文件；且已有 redaction 保护

### 验证记录（其余全部通过）

#### F15 — Host canonical previous pair

1. **唯一 normalizer 真源**：`_canonical_material_text()` 唯一调用 `normalized_material_text()`；所有 previous-view 文本叶子在 `_canonical_previous_replacement_projection()` 中一次规范化。`(compact_material.py:881-890, 2696-2744)`

2. **answer anchor 正向渲染**：canonical typed anchor → `_readable_answer_anchor_from_canonical()` → `_canonical_answer_anchor_block_text()` 调用 `previous_answer_anchor_block_text()`。无逆向解析。`(compact_material.py:2747-2790)`

3. **不再次规范化**：`_previous_block_from_canonical_text()` 直接传 `_CanonicalMaterialText.value`。`(compact_material.py:2793-2836)`

4. **accepted tool evidence 独立路径**：`_AcceptedToolEvidenceText` 校验等于 shared renderer 输出；`_CanonicalMaterialText` 不得携带 accepted evidence。`(compact_material.py:893-914, 963-969)`

5. **validator/frontier 未修改**：`validate_previous_compacted_view_pair()` 与 `compacted_source_refs` 在 diff 中零出现。

6. **durable reopen byte-exact**：reopen 断言 readable JSON 与每个 block text/size/digest exact 相等。`(test_compact_material.py:2183-2207)`

7. **ordinary freeze/dispatch**：frozen candidate messages == accepted request messages 且 RunStatus.SUCCEEDED。`(test_dispatch_scheduler.py:9030-9103)`

8. **whitespace boundary**：typed boundary 与 strict persisted parser 均拒绝 blank title。`(test_context_compact_events.py:352-382)`

#### F14 — compacted_source_refs frontier

9. **frontier zero diff**：F14 cumulative frontier 实现未修改。

#### F16 — Observation contract（tracked helper）

10. **canonical per-Run terminal + reason 与 process exit 分离**：`observe_run_terminals()` 只读 EventLog，不读进程退出状态。`(cli_ci_run_observation.py:441-555)`

11. **reason 只取 `reason_json.reason`**：按 terminal-specific canonical shape 严格校验 key set。`(cli_ci_run_observation.py:1031-1087)`

12. **合法失败 insufficient，未知计数 null**：`classify_required_run_evidence()` 三态精确区分。`(cli_ci_run_observation.py:597-624)`

13. **summary 与逐 Run 四类分布 exact**：`validate_terminal_class_summary()` 逐项对账。`(cli_ci_run_observation.py:627-681)`

14. **dependency safe-stop 只一次 EOT**：`classify_remaining_actions_for_safe_stop()` 仅第一个 CLEANUP_EOT 允许发送。`(cli_ci_run_observation.py:817-864)`

15. **session_id exact / lifecycle owner 复用**：terminal.session_id == accepted.session_id；`run_status_for_terminal_event()` + `is_public_outbox_terminal_item_event()` 复用。`(cli_ci_run_observation.py:959-962, 1017-1028)`

#### F16 — Ignored harnesses（完整阅读后确认）

16. **prompt_observe_calibration.py — safe-stop orchestration**：`_stop_dependency_chain()` (line 918-996) 调用 tracked `classify_remaining_actions_for_safe_stop()`，逐项记录 remaining dependent 为 `not_run`，只发送一次 EOT，设置 10 秒 cleanup deadline。`(line 955-957, 1352, 1373)`

17. **prompt_observe_calibration.py — terminal 三态**：`_run_scenario()` 写 `run-terminals.json` 后由 `_execute()` 内 `_segment_terminal_facts()` 读取。`RunObservationError` → invalid（保留 diagnostics）；`evidence_status == "invalid"` → invalid；valid non-succeeded → `classify_required_run_evidence()` 返回 INSUFFICIENT。`(line 429-466)`

18. **f14_real_cli_observation.py — terminal 三态与 dependency gate**：`_segment_terminal_facts()` (line 535-713) 对文件缺失/malformed JSON/invalid shape 返回 `_invalid_segment_terminal_facts()`（保留 diagnostics + record path/digest）；valid 时调用 `validate_terminal_class_summary()` + `classify_required_run_evidence()`。dependency gate 由 `SegmentTerminalFacts.dependency_status` property 投射：COMPLETE→PROCEEDED, INSUFFICIENT→STOPPED, INVALID→INVALID。`(line 122-134, 667-713)`

19. **f14_real_cli_observation.py — safe-stop**：依赖链通过 `_run_segment()` (line 745-803) 的 `chain.dependency_status` 传播；非 PROCEEDED 时直接写 `not_run` row，不执行 scenario。`(line 772-787)`

20. **f14_real_cli_observation.py — secret scan 与 path hygiene**：`_secret_scan()` (line 981-1013) 使用 `SECRET_ENV_NAMES` 实际环境值 + canary 作为 exact probes；`_public_evidence_files()` 枚举整个 evidence tree（含 symlink）。`(line 996-1010)`

21. **f14_real_cli_observation.py — oracle_status**：`execution-index-f15-f16.json` 固定 `"oracle_status": "unadjudicated"`。`(line 1439)`

#### Adversarial A-D

22. **A — 普通路径不当 secret**：tracked scanner 的 exact probes 只接受实际 secret 环境值和 canary；repo/run/corpus 路径不进入 probes。`(test_cli_ci_run_observation.py:629-664)`

23. **A — exact secret 必命中**：注入 secret fixture 必命中且 invalid。`(test_cli_ci_run_observation.py:667-703)`

24. **D — raw sqlite/db 文件、文本 raw DB path、symlink fail closed**：三类 typed reason 由真实文件/路径/symlink 证明。`(test_cli_ci_run_observation.py:706-748)`

25. **D — 无硬编码假事实**：`scan_public_evidence_files()` 按实际后缀、symlink 组件遍历和文本正则匹配，不使用硬编码布尔。`(cli_ci_run_observation.py:741-806)`

26. **scanner 不 loose parse/heuristic**：`_terminal_reason()` 使用 `json.loads()` + exact key set 校验；`_RAW_DATABASE_PATH_PATTERN` 是显式正则。`(cli_ci_run_observation.py:1046-1087, 45-48)`

#### Schema / public contract

27. **run_transition.py zero diff**：product lifecycle/audit contract 未修改。

28. **CompactAcceptedReplacementV4 未修改**：schema 5、compactor LLM schema、Engine contract 与 CLI public surface 无变化。

#### Tests / validation

29. **focused suite**：474 passed in 4.65s。

30. **pyright**：0 errors, 0 warnings。

31. **diff --check**：通过。

32. **py_compile ignored harnesses**：两文件编译通过。

33. **SHA-256 一致性**：三个文件 SHA-256 与 review-fixes artifact 记录一致 ✓

34. **禁改面审计**：`run_transition.py`、oracle/scenario files、prompt、Engine、F14 `compacted_source_refs` 实现均 zero diff。

## Open Questions

无。

## Residual Risk

- **001-P2 残留**：prompt_observe_calibration.py 缺失 final secret scan。real rerun 前必须修复或由 post-commit validation gate 补充独立 scan。
- **002-P3 残留**：f14_real_cli_observation.py 的 execution-index 未被 secret scan 覆盖。风险较低（index 是 metadata），但应在 clean committed target rerun 前调整时序。
- `assigned to post-commit validation gate / Controller`：accepted plan 要求 fresh production real rerun 只针对 clean committed target；当前用户明确限制 implementation gate 且禁止 commit/push，因此本 gate 未启动真实 provider/AAPL rerun。
- Formal financial/business Oracle 保持 `unadjudicated`，owner 不在本 review gate。

## Conclusion

**CONDITIONAL PASS**。F15 canonical pair、F14 frontier、F16 tracked helper 全部通过，A-D adversarial 审查在 tracked helper 与 tests 层面通过。两个 ignored harness 的 terminal 三态、safe-stop orchestration、dependency gate 与 lifecycle owner 复用经完整阅读确认正确。发现两个 harness-level secret scan gap：prompt_observe_calibration.py 完全缺失 final secret scan（P2），f14_real_cli_observation.py 的 execution-index 未被已执行的 scan 覆盖（P3）。无 P0-P1；P2/P3 均为 harness 证据完整性问题，不影响产品代码或 tracked helper contract。所有 owner contract 闭环。
