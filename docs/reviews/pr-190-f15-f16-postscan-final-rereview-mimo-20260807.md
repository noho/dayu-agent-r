# PR 190 F15 / F16 Post-Scan Final Re-Review (MiMo)

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `580b1427`
- Output file: `docs/reviews/pr-190-f15-f16-postscan-final-rereview-mimo-20260807.md`
- Included scope:
  - tracked diff（`580b1427` 相对全部 tracked changes）；
  - `utils/cli_ci_run_observation.py`（untracked, 1225 行完整阅读）；
  - `tests/cli/test_cli_ci_run_observation.py`（untracked, 1069 行完整阅读）；
  - `workspace/tmp/prompt_observe_calibration.py`（ignored, 3112 行完整阅读）；
  - `workspace/tmp/f14_real_cli_observation.py`（ignored, 1368 行完整阅读）。
- Excluded scope: 无
- Parallel review coverage: 无
- Gateflow binding: `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`、`docs/gateflow/pr-190-f15-f16-implementation-20260807.md`、`docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`、`docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`
- Prior review inputs: `docs/reviews/pr-190-f15-f16-final-rereview-mimo-20260807.md`（旧 CONDITIONAL PASS，仅作 finding provenance，不作为本轮 PASS 依据）

## Findings

未发现实质性问题。

旧 001-P2 与 002-P3 已关闭，详见下方验证记录。本轮未发现新 P0-P2。

## 验证记录

### 001-P2 关闭：prompt harness final publication scan

- **旧 finding**: `workspace/tmp/prompt_observe_calibration.py` `main()` 全部 scenario 执行完毕后不调用 `scan_public_evidence_files()`，secret 明文可能进入 public evidence tree 且无 fail-closed 检测。
- **本轮验证**: `main()` line 3083-3107 现在先写 `run-completion.json`（line 3085-3101），其中 `secret_scan.record_path` 仅引用 report path、不复制尚未形成的 status/digest；随后调用 `run_observation.write_final_publication_scan_report()`（line 3103-3107）扫描含 completion 在内的整个 `evidence/` tree 并独占创建唯一 report。
- **锁定 test**: `test_final_publication_scan_covers_final_metadata_and_only_excludes_report`（line 775-826）断言 completion 和 execution-index 均进入 file descriptors，唯一自排除是尚不存在的 report。
- **结论**: ✅ 关闭。

### 002-P3 关闭：F14 harness execution-index 未被 scan 覆盖

- **旧 finding**: `workspace/tmp/f14_real_cli_observation.py` 的 `_secret_scan()` 在 index 写入前执行，index 本身不被 scan 覆盖。
- **本轮验证**: `main()` line 1332-1363 现在先写 `execution-index-f15-f16.json`（line 1332-1358），index 的 `secret_scan.record_path` 仅引用 report path（line 1353-1355），`evidence_status` 只表达 Run/context/tool collection（line 1325-1329，来自 `_top_evidence_status()`），不包含 scan verdict。随后调用 `write_final_publication_scan_report()`（line 1359-1363）扫描含 index 在内的完整 evidence tree。
- **锁定 test**: 同上 `test_final_publication_scan_covers_final_metadata_and_only_excludes_report`。
- **结论**: ✅ 关闭。

### Controller traversal / containment 补充关闭

- **旧 finding**: report path traversal、resolved root escape、symlink ancestor 未在 owner boundary 拒绝。
- **本轮验证**: `write_final_publication_scan_report()` (line 818-908) 完整防御链：
  1. `report_path.name != "secret-scan.json"` → reject (line 847-848)
  2. `".." in report_path.parts` → reject lexical traversal (line 849-850)
  3. `evidence_root.is_symlink()` → reject (line 851-852)
  4. `absolute_report.relative_to(root)` → reject outside (line 857-860)
  5. `resolved_report.relative_to(root)` → reject resolved escape (line 861-867)
  6. ancestor component `is_symlink()` → reject (line 869-873)
  7. `report_parent.is_dir()` → reject missing parent (line 874-875)
  8. `absolute_report.exists() or is_symlink()` → reject stale (line 876-879)
  9. post-enum re-check (line 886-889) → reject race
  10. `open("x")` → reject `FileExistsError` race (line 902-908)
- **锁定 tests**: `test_final_publication_scan_rejects_traversal_and_outside_report`（line 858-904）覆盖 lexical traversal、outside target、symlink ancestor；`test_final_publication_scan_rejects_existing_stale_report`（line 828-855）覆盖 stale report。
- **结论**: ✅ 关闭。

### 验证清单逐项确认

| 验证项 | 结果 | 证据 |
|---|---|---|
| tracked `write_final_publication_scan_report` 是唯一 final-tree orchestration | ✅ | 两个 harness 均调用 `run_observation.write_final_publication_scan_report()`，无第二 scan 路径 |
| completion/index 先落盘且仅引用 report path，必须进入 descriptors | ✅ | prompt: line 3085→3103; F14: line 1332→1359; test line 775-826 |
| 只允许 absent secret-scan.json 自排除 | ✅ | `open("x")` + exists/is_symlink pre-check; test 819-825 |
| report stale/既有/symlink ancestor/race 独占创建 | ✅ | line 876-879 + 886-889 + 902-908; test 828-855 |
| path traversal / resolved escape fail closed | ✅ | line 849-850 + 861-867; test 858-904 |
| secret/raw DB/path/leaf+ancestor symlink/special/missing/oversize 不回退 | ✅ | `scan_public_evidence_files()` line 726-815; test 708-772 + 907-971 |
| F14 index `evidence_status` 不冒充 scan verdict | ✅ | F14 line 1325-1329: `_top_evidence_status()` 只看 Run/context/tool collection |
| prompt/F14 harness 不双扫 | ✅ | 各只调用一次 `write_final_publication_scan_report()`，无 pre-scan |

### F15 — Host canonical previous pair（复验）

1. **唯一 normalizer 真源**: `_canonical_material_text()` 唯一调用 `normalized_material_text()`；所有 previous-view 文本叶子在 `_canonical_previous_replacement_projection()` 中一次规范化。`(compact_material.py)`

2. **answer anchor 正向渲染**: canonical typed anchor → `_readable_answer_anchor_from_canonical()` → `_canonical_answer_anchor_block_text()` 调用 `previous_answer_anchor_block_text()`。无逆向解析。

3. **不再次规范化**: `_previous_block_from_canonical_text()` 直接传 `_CanonicalMaterialText.value`。

4. **accepted tool evidence 独立路径**: `_AcceptedToolEvidenceText` 校验等于 shared renderer 输出；`_CanonicalMaterialText` 不得携带 accepted evidence。

5. **validator/frontier 未修改**: `validate_previous_compacted_view_pair()` 与 `compacted_source_refs` 在 diff 中零出现。

6. **durable reopen byte-exact**: reopen 断言 readable JSON 与每个 block text/size/digest exact 相等。

7. **ordinary freeze/dispatch**: frozen candidate messages == accepted request messages 且 RunStatus.SUCCEEDED。

8. **whitespace boundary**: typed boundary 与 strict persisted parser 均拒绝 blank title。

### F14 — compacted_source_refs frontier（复验）

9. **frontier zero diff**: F14 cumulative frontier 实现未修改。

### F16 — Observation contract（复验）

10. **canonical per-Run terminal + reason 与 process exit 分离**: `observe_run_terminals()` 只读 EventLog，不读进程退出状态。`(cli_ci_run_observation.py:442-499)`

11. **reason 只取 `reason_json.reason`**: 按 terminal-specific canonical shape 严格校验 key set。`(cli_ci_run_observation.py:1125-1181)`

12. **合法失败 insufficient，未知计数 null**: `classify_required_run_evidence()` 三态精确区分。`(cli_ci_run_observation.py:598-625)`

13. **summary 与逐 Run 四类分布 exact**: `validate_terminal_class_summary()` 逐项对账。`(cli_ci_run_observation.py:628-682)`

14. **dependency safe-stop 只一次 EOT**: `classify_remaining_actions_for_safe_stop()` 仅第一个 CLEANUP_EOT 允许发送。`(cli_ci_run_observation.py:911-958)`

15. **session_id exact / lifecycle owner 复用**: terminal.session_id == accepted.session_id；`run_status_for_terminal_event()` + `is_public_outbox_terminal_item_event()` 复用。`(cli_ci_run_observation.py:1053-1078)`

### F16 — Ignored harnesses（复验）

16. **prompt_observe_calibration.py — safe-stop orchestration**: `_stop_dependency_chain()` 调用 tracked `classify_remaining_actions_for_safe_stop()`，逐项记录 remaining dependent 为 `not_run`，只发送一次 EOT，设置 10 秒 cleanup deadline。

17. **prompt_observe_calibration.py — terminal 三态**: `_run_scenario()` 写 `run-terminals.json` 后由 `_execute()` 内 `_segment_terminal_facts()` 读取。`RunObservationError` → invalid（保留 diagnostics）；`evidence_status == "invalid"` → invalid；valid non-succeeded → `classify_required_run_evidence()` 返回 INSUFFICIENT。

18. **f14_real_cli_observation.py — terminal 三态与 dependency gate**: `_segment_terminal_facts()` 对文件缺失/malformed JSON/invalid shape 返回 `_invalid_segment_terminal_facts()`（保留 diagnostics + record path/digest）；valid 时调用 `validate_terminal_class_summary()` + `classify_required_run_evidence()`。dependency gate 由 `SegmentTerminalFacts.dependency_status` property 投射。

19. **f14_real_cli_observation.py — safe-stop**: 依赖链通过 `_run_segment()` 的 `chain.dependency_status` 传播；非 PROCEEDED 时直接写 `not_run` row，不执行 scenario。

20. **f14_real_cli_observation.py — final-tree scan**: 先写 execution-index（line 1332-1358），再调用 `write_final_publication_scan_report()`（line 1359-1363），无 pre-scan。

21. **f14_real_cli_observation.py — oracle_status**: `execution-index-f15-f16.json` 固定 `"oracle_status": "unadjudicated"`（line 1356）。

### Adversarial A-D（复验）

22. **A — 普通路径不当 secret**: tracked scanner 的 exact probes 只接受实际 secret 环境值和 canary；repo/run/corpus 路径不进入 probes。`(test line 631-666)`

23. **A — exact secret 必命中**: 注入 secret fixture 必命中且 invalid。`(test line 669-705)`

24. **D — raw sqlite/db 文件、文本 raw DB path、symlink fail closed**: 三类 typed reason 由真实文件/路径/symlink 证明。`(test line 708-772)`

25. **D — final-tree 枚举 secret/raw DB/symlink 候选**: `write_final_publication_scan_report()` 复用唯一 scanner，不遗漏。`(test line 907-971)`

### Schema / public contract（复验）

26. **run_transition.py zero diff**: product lifecycle/audit contract 未修改。

27. **CompactAcceptedReplacementV4 未修改**: schema 5、compactor LLM schema、Engine contract 与 CLI public surface 无变化。

### Tests / validation

28. **focused suite**: 31 passed in 0.46s（`tests/cli/test_cli_ci_run_observation.py`）。

29. **ignored harness pyright**: 0 errors, 0 warnings。

30. **full pyright** (`dayu/ tests/ utils/`): 0 errors, 0 warnings。

31. **diff --check**: 通过。

32. **py_compile ignored harnesses + tracked helper + tests**: 四文件编译通过。

33. **SHA-256 一致性**:
    - `utils/cli_ci_run_observation.py`: `239bfd1f762fa44fd4e0e2131fe577f64cc2c7f240bcd2d00f2b46da2cc06872` ✓
    - `workspace/tmp/prompt_observe_calibration.py`: `15c6e2dbcc081b20c63197aba03544d00042ecf1718ab0e44214b09a5dea5e60` ✓
    - `workspace/tmp/f14_real_cli_observation.py`: `dfc3d61853e0c2bf5b7b6421ae57bd1440ad09d33446c72e5c1e28941bb1535e` ✓

34. **禁改面审计**: `run_transition.py`、oracle/scenario files、prompt、Engine、F14 `compacted_source_refs` 实现均 zero diff。

## Open Questions

无。

## Residual Risk

- `assigned to post-commit validation gate / Controller`：accepted plan 要求 fresh production real rerun 只针对 clean committed target；当前用户明确限制 implementation gate 且禁止 commit/push，因此本 gate 未启动真实 provider/AAPL rerun。不得把 deterministic pass 表述成 real-evidence completion。
- Formal financial/business Oracle 保持 `unadjudicated`，owner 不在本 review gate。
- 没有 unclassified residual risk。

## Conclusion

**PASS**。旧 001-P2 与 002-P3 已通过 review-fix 后的独立复验关闭；Controller traversal/symlink/stale 补充全部关闭。本轮未发现新 P0-P2。F15 canonical pair、F14 frontier、F16 tracked helper 全部通过，A-D adversarial 审查在 tracked helper 与 tests 层面通过。两个 ignored harness 的 final-tree scan 时序、completion/index descriptor coverage、terminal 三态、safe-stop orchestration、dependency gate 与 lifecycle owner 复用经完整阅读确认正确。所有 owner contract 闭环，zero drift。
