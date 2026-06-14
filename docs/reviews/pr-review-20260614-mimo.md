# PR Review — PR 140 Final Gate

## Scope

- Mode: PR
- Branch: `work/cm-05-06-08-09`
- Base: `main`
- PR: 140 (draft)
- Output file: `docs/reviews/pr-review-20260614-mimo.md`
- Included scope: PR 140 全部 diff，含 WU-CM-05 / WU-CM-06 / WU-CM-08 / WU-CM-09 生产代码、测试、plan artifacts、review artifacts、design doc 更新与 control doc 更新
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

| 风险 | 状态 | Owner / Destination |
|---|---|---|
| `tests/host/fake_compaction.py` 保留了一个与 WU-CM-05 无关的已有 `cast(...)` | non-blocking，不阻塞 PR | 后续 WU 按需清理 |
| caller-side overlong truncation 不在 WU-CM-06 范围内 | 已显式排除，由各 caller budget/display tests 拥有 | caller owners |
| identity read failure defensive branch 未被覆盖 | low-risk defensive branch，不阻塞 | 后续维护时补充 |
| docs/reviews 目录下大量 review artifacts 有 trailing whitespace | 纯文档格式，不影响行为 | 后续统一清理 |

## Verification Results

### 测试

```
212 passed, 1 skipped in 1.62s
```

覆盖文件：`tests/host/test_llm_compaction.py`、`tests/host/test_compact_material.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_terminal_summary_payload.py`、`tests/host/test_read_api_terminal_policy.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_memory_projection.py`、`tests/host/test_storage_maintenance.py`、`tests/host/test_package_exports.py`

### Pyright

```
0 errors, 0 warnings, 0 informations
```

### Git whitespace

```
git diff --check main...HEAD
```

仅有 docs/reviews 下的 trailing whitespace，无生产代码 whitespace 错误。

## Review Detail

### 1. PR scope 验证：只完成四个指定 WU

**结论：通过。**

- PR diff 的生产代码变更集中在 `dayu/host/llm_compaction.py`、`dayu/host/terminal_summary_payload.py`、`dayu/host/_terminal_answer.py`、`dayu/host/durable/memory.py`、`dayu/host/storage_maintenance.py`、`dayu/host/__init__.py`、`dayu/host/README.md`。
- `docs/host/issues-implementation-control.md` 将 WU-CM-05 / WU-CM-06 / WU-CM-08 / WU-CM-09 从 `deferred` 更新为 `completed`，gate 从 `draft-PR-pass` 更新为 `ready-to-open-draft-PR`。
- WU-OBS-00 状态仍为 `pending`，WU-RET-00 状态仍为 `draft-PR-pass`，WU-CM-10 / WU-CM-11 仍为 `deferred`。未发现把后续 work unit 写成已完成的情况。

### 2. Host/Engine 分层与设计真源对齐

**结论：通过。**

- Engine 代码零变更。所有改动在 `dayu/host/` 内。
- `dayu/host/durable/memory.py`（durable 层）不 import `dayu/host/` 上层模块。新增的 `MemorySnapshotIntegrityFailureKind` 和 `MemorySnapshotIntegrityIssue` 定义在 durable 层内，`inspect_memory_snapshot_integrity` 也只操作 durable tables。
- `dayu/host/storage_maintenance.py`（Host facade 层）import durable 层类型并聚合到 `HostStorageMaintenanceResult`，符合 `UI -> Service -> Host -> Engine` 分层。
- `docs/host/design.md` 更新了 `run_storage_maintenance` 描述和 memory snapshot corruption policy，与代码行为一致。
- `dayu/host/README.md` 更新了 storage maintenance 章节，覆盖了新增的 memory snapshot integrity issues 诊断能力。

### 3. LLM-facing 语义

**结论：通过。**

- `llm_compaction.py` 的 `_parse_vnext_proposal` 不再返回宽 `Mapping[str, JsonValue]`，而是直接构造 `ConversationCompactOutputVNext`。
- 所有 JSON 字段读取通过 typed helpers（`_required_string`、`_required_array`、`_required_enum` 等），错误信息包含完整 field path（如 `evidence_backed_facts[0].evidence_kind`）。
- 不再使用 `cast(Mapping[str, JsonValue], parsed)` 进行 unchecked 类型转换。
- `from typing import cast` 已从 `llm_compaction.py` 移除（该文件不再需要 `cast`）。
- LLM-facing prompt schema 和 output shape 未变更。

### 4. Terminal summary text policy

**结论：通过。**

- `_terminal_answer.py` 的 `assistant_final_answer_continuity_text` 固定读取顺序：inline `final_answer` -> digest-checked terminal summary artifact `content`。裸 `content`、`summary_text`、nested `summary` 不在读取范围。
- `terminal_summary_payload.py` 的 `assistant_final_answer_text_from_run_payload` 只读 `final_answer`，`terminal_summary_content_text_from_payload` 只读 `content`。
- `durable/memory.py` 的 `_payload_with_assistant_final_answer` 在 `RUN_SUCCEEDED` 路径中先尝试 inline，再通过 strict resolver 读取 artifact fallback。
- 测试覆盖 success / failure / cancel / lost / empty-final-answer 的 policy 矩阵。

### 5. Compaction material readability

**结论：通过。**

- `compact_material.py` 无生产代码变更。
- 测试增加了 `_MaterialPackShape` / `_VNextInputShape` assertion helpers 和 boundary-specific failure messages。
- public compact smoke 增加了 focused assertion helpers 用于 material section shape、stale legacy section exclusion、forbidden internal terms、evidence marker retention 和 fake compactor label-only proposal。

### 6. Durable memory snapshot corruption diagnostics

**结论：通过。**

- `MemorySnapshotIntegrityFailureKind` 枚举覆盖五类：`INVALID_JSON`、`SCHEMA_MISMATCH`、`DIGEST_MISMATCH`、`UNSUPPORTED_ITEM_KIND`、`STORAGE_READ_FAILED`。
- `inspect_memory_snapshot_integrity` 全 DB scan，逐 row 分类，不修改 SQLite row，不触发 rebuild / overwrite。
- `storage_maintenance.py` 在同一 read state 中读取 integrity issues 并传递到 `HostStorageMaintenanceResult`。
- `HostStorageMaintenanceResult.__post_init__` 校验 `memory_snapshot_integrity_issues` tuple。
- `json_value()` 输出自解释 JSON objects，不泄漏 snapshot JSON、prompt 或大 payload。
- 测试覆盖 empty DB、valid snapshot、invalid JSON、schema mismatch、digest mismatch、unsupported item kind、storage read failure。

### 7. Package exports

**结论：通过。**

- `dayu/host/__init__.py` 导出 `MemorySnapshotIntegrityIssue`。
- `storage_maintenance.py` 的 `__all__` 包含 `MemorySnapshotIntegrityIssue`。
- `test_package_exports.py` 验证通过。

### 8. README / docs 一致性

**结论：通过。**

- `docs/host/design.md` 更新了 `run_storage_maintenance` 描述（新增 memory snapshot integrity issues 和 no-quarantine/rebuild/overwrite 声明）和 memory snapshot corruption policy。
- `dayu/host/README.md` 更新了 Storage Maintenance 章节，覆盖 memory snapshot integrity issues 和五类 failure kind。
- `tests/README.md` 更新了 Host 测试覆盖说明。
- `docs/host/issues-implementation-control.md` 准确反映四个 WU 的 completed 状态和 gate artifacts。

### 9. Residual risks owner / destination

**结论：通过。**

- `tests/host/fake_compaction.py` 的 `cast(...)` residual：non-blocking，已记录为 WU-CM-05 scope 外的已有代码。
- caller-side overlong truncation：已显式排除出 WU-CM-06 scope，由各 caller 拥有。
- identity read failure defensive branch：low-risk uncovered branch，不阻塞。
- 所有 residual risks 都有 owner 或 destination。

## Conclusion

**PASS**

PR 140 的 diff 只完成 WU-CM-05、WU-CM-06、WU-CM-08、WU-CM-09 四个指定 work unit。Host/Engine 分层、LLM-facing 语义、Conversation Memory、terminal summary、storage maintenance 行为均符合设计真源。typed parsing 消除了 unchecked cast 并提供 field-level diagnostics。terminal text policy 覆盖完整 policy 矩阵。compaction material readability 改善了测试可维护性。durable memory snapshot corruption diagnostics 提供了 operator-facing 五类 failure classification。README/docs 与代码一致。residual risks 均有 owner/destination。允许 draft-PR-pass 和 final closeout。
