# PR Review

## Scope

- Mode: PR
- PR: 140 — "Complete conversation memory follow-up work units"
- Repository: `noho/dayu-agent-r`
- Head branch: `work/cm-05-06-08-09`
- Base branch: `main`
- Author: `noho`
- URL: https://github.com/noho/dayu-agent-r/pull/140
- Output file: `docs/reviews/pr-review-20260614-ds.md`
- Included scope: 全量 PR diff，覆盖 `dayu/host/` 下 llm_compaction.py、durable/memory.py、storage_maintenance.py、terminal_summary_payload.py、_terminal_answer.py、__init__.py、README.md；`docs/host/` 下 design.md、issues-implementation-control.md、四个 WU plan 文档；`tests/host/` 下 9 个测试文件与 tests/README.md；`docs/reviews/` 下 gate artifacts。
- Excluded scope: 无。PR diff 中所有文件均纳入审查。
- Parallel review coverage: 无。本次为主 reviewer 独立完成。

## Verification

- `pytest tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` — **212 passed, 1 skipped**
- `python -m pyright dayu/ tests/ utils/` — **0 errors, 0 warnings**
- `git diff --check` — **clean**
- CI checks: GitHub 未报告 branch 上的 status check（draft PR branch 无 CI 配置）

## Findings

### 1-未修复-低-`llm_compaction.py` 中 `_bounded_known_refs` 为未调用死代码

- **入口/函数**: `_bounded_known_refs`（`dayu/host/llm_compaction.py:1191`）
- **文件(行号)**: `dayu/host/llm_compaction.py` 行 1191–1210
- **输入场景**: 不适用——该函数在当前代码中无任何调用方。
- **实际分支**: 该函数定义存在于模块作用域，但从未被任何执行路径引用。
- **预期行为**: 如果该函数是 WU-CM-05 typed parsing 计划的一部分但未集成，应在 review 中明确说明其用途或移除。如果是有意保留供未来 slice 使用，应在注释或 control doc 中标注。
- **实际行为**: 代码中存在一个已完成实现但未接入任何调用链的校验辅助函数。
- **直接证据**: `grep -rn '_bounded_known_refs' dayu/ tests/` 仅在定义处命中，无调用方。
- **影响**: 无运行时影响。仅造成代码库中存在无法通过正常执行路径覆盖的 dead code，降低可维护性。
- **建议改法和验证点**: 两种处理方向——(a) 若该函数确实服务于未来的 ref validation 需求，在函数 docstring 中加 `.. note::` 标注预期接入点；(b) 若确定不需要，移除以保持模块清洁。无论哪种方向，均应确认 control doc 中是否有对应 residual risk 条目。
- **修复风险（低）**: 移除或标注死代码不改变运行时行为，风险极低。
- **严重程度（低）**: 非 correctness / stability 问题，仅 maintainability 微瑕。不阻塞 draft-PR-pass。

## Open Questions

- **Q1**: `_bounded_known_refs` 是否有意保留供 WU-CM-05 的后续 slice 接入？当前 control doc 中未见对应 tracking item。若有意保留，建议在 control doc residual risk 表或函数 docstring 中记录 owner/destination。
- **Q2**: WU-CM-09 S1 遗留的 "identity read failure defensive branch" uncovered branch（`_memory_snapshot_integrity_issues_for_row` 中 `except (HostDurableError, KeyError)` 路径）是否计划在后续 slice 覆盖？当前 control doc 标注为 "low-risk uncovered branch"，但未在 active residual risk 表中显式追踪。建议确认是否需要在表中新增一条 deferred-with-owner entry。

## Residual Risk

1. **WU-CM-09 identity read failure 分支未覆盖**（PR 描述与控制文档均已记录）：`dayu/host/durable/memory.py` `_memory_snapshot_integrity_issues_for_row()` 中 `except (HostDurableError, KeyError)` 路径依赖行级 identity 字段损坏才能触发，在 schema 约束下极难自然发生。不阻塞 draft-PR-pass。当前控制文档中该 risk 未以独立 tracking item 形式出现在 active residual risk 表，建议确认是否需要形式化追踪或显式关闭。

2. **`tests/host/fake_compaction.py` `cast(...)` 残留**（PR 描述与控制文档均已记录）：该 `cast` 位于测试辅助代码，不在生产路径。不阻塞本 PR。

3. **`_bounded_known_refs` 死代码**（见 Finding 1）：不阻塞本 PR。

4. **Open Questions Q1、Q2**：均为 non-blocking 确认项，不阻塞 draft-PR-pass。

## Conclusion

**PASS**

经过完整代码走读与验证，PR 140 的四个 work unit（WU-CM-05 typed parsing、WU-CM-06 terminal text policy、WU-CM-08 compaction material readability、WU-CM-09 memory snapshot integrity diagnostics）在以下维度均无 correctness / stability / maintainability blocker：

- **Scope 合规**：PR diff 只完成四个指定 WU，WU-OBS 与其它后续 work unit 在 control doc 中正确保持 pending 或 deferred 状态。
- **分层与语义**：Host/Engine 分层边界保持完整，未引入反向依赖。`_terminal_answer.py` 与 `terminal_summary_payload.py` 的 LLM-facing docstring 已收敛为自足、无歧义的语义边界说明。Conversation Memory 契约未改变。
- **Typed parsing**：`llm_compaction.py` 移除全部 7 处 `cast(...)`，替换为自解释的类型校验辅助函数（`_json_object`、`_required_string`、`_required_array`、`_required_enum`、`_optional_non_negative_int` 等），每个校验点都产生包含完整字段路径的精确错误消息。测试覆盖 malformed JSON、missing key、field type error、nested array type error、array item type error、overlimit array。
- **Terminal text policy**：`PayloadTextReadPolicy` 语义已文档化；`_terminal_answer.py` 明确 consumer 边界；`test_read_api_terminal_policy.py` 新增 policy matrix 测试验证 FAILED / CANCELLED / LOST 终态均不把 diagnostic payload 投射为 final answer。
- **Compaction material**：测试结构调整改善可维护性；material 字段命名与设计真源一致。
- **Memory snapshot integrity**：`inspect_memory_snapshot_integrity()` 纯只读、fail-safe、不修改任何 SQLite row；`MemorySnapshotIntegrityIssue` 类型定义在 `dayu.host.durable.memory` 并由 `storage_maintenance.py` 消费后通过 `dayu.host.__init__` 公开导出。测试覆盖 invalid_json、schema_mismatch、digest_mismatch、unsupported_item_kind、storage_read_failed 五大分类。
- **Docs 一致性**：`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、`docs/host/issues-implementation-control.md` 均与代码变更一致更新。

Finding 1（`_bounded_known_refs` 死代码）为低严重度 maintainability 观察，不改变 PASS 结论。Open Questions 均为 non-blocking 确认项。所有 residual risks 已有 owner/destination 或可被现有测试框架覆盖。

允许 draft-PR-pass 和 final closeout。
