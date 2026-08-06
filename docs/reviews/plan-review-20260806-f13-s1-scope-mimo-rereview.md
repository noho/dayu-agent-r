# Re-Review: PR 190 F13 S1 Scope Amendment — MiMo

- Reviewer: MiMo (adversarial re-review)
- Date: 2026-08-06
- Base: 7bfe36f928b9e00d8f72a3d1b7a6dc08f6b751d6
- Controller adjudication: `docs/gateflow/pr-190-f13-s1-scope-review-adjudication-20260806.md`
- Updated amendment: `docs/gateflow/pr-190-f13-s1-scope-amendment-20260806.md`

## Methodology

逐原 finding（F1–F7）对照 Controller 裁决与 amendment 更新，确认 FIXED / PASS / STILL OPEN。

---

## Finding-by-Finding Re-Review

### F1. test_tool_trace_queries.py 直接证据描述精度

**Original severity**: Low
**Controller adjudication**: ACCEPT / FIXED — amendment 列出 3 个具体 v3 symbols
**Amendment update**: Line 16 现为 "`COMPACT_OUTPUT_SCHEMA_V3`、`CompactCandidateV3`、`CompactSessionSummaryV3`及其fixture构造"

**Verification**:
- 原 amendment 只写 "v3 candidate/schema fixture"，现列出 3 个具体 symbol 名。
- 与 base 文件实际引用一致（`test_tool_trace_queries.py:85-87` 导入这 3 个 symbol，`951-953` 构造 fixture）。
- 与其它 5 个文件的描述粒度一致。

**Status**: **FIXED** ✓

---

### F2. test_tool_trace_queries.py S1/S2 所有权分割

**Original severity**: Pass
**Controller adjudication**: PASS — concern 边界明确，不构成双 owner

**Verification**: 无需变更。Controller 裁决与原 review 结论一致。S1 机械存活（删除 symbol 替换）/ S2 新语义（public projection），无重叠。

**Status**: **PASS** ✓

---

### F3. Residue scan 范围收窄至 Python

**Original severity**: Low
**Controller adjudication**: ACCEPT / FIXED — 两个 utils/ smoke 加入 S1 helper scope，residue scan 扩到 `utils/**/*.py`

**Amendment update**:
- Direct evidence 新增两条（line 17-18）：`utils/smoke_host_public_conversation_memory_scenarios.py`（14 处）和 `utils/smoke_host_public_r03_semantic_ownership.py`（4 处）
- Residue scan scope 从 `dayu/**/*.py` + `tests/**/*.py` 扩展为包含 `utils/**/*.py`

**Verification**:
- 原 review 指出非 Python 文件零 v3 引用（收窄安全），但未发现 `utils/` 下的 Python 脚本也有 v3 引用——这是原 review 的盲区。
- Controller 发现 DS review 的 medium finding 后正确处理：不是仅记录 residual risk，而是直接加入 scope。
- **计数更正**：DS 原 review 统计 utils/ 为 11+4=15 处，实测为 **14+4=18 处**（conversation_memory_scenarios 漏计 3 个 `COMPACT_OUTPUT_SCHEMA_V3` / `CompactForwardIntentStatusV3` schema/candidate hit：line 2257、2286、2325）。Controller 已在 amendment/adjudication 更正。
- 更新后 residue scan 覆盖 `dayu/**/*.py` + `tests/**/*.py` + `utils/**/*.py`，无遗漏。

**Status**: **FIXED** ✓（原 review 的 Low severity 未覆盖 utils/ 盲区，Controller 通过采纳 DS finding 补上）

---

### F4. "生产allowed scope未发现新的遗漏" 声明准确性

**Original severity**: Pass
**Controller adjudication**: PASS — 非 Host 生产与非 Host tests 无会被删除的 v3 contract 引用

**Verification**: 原 review 结论不变。6 个新增文件全是 test/helper，生产 scope 无新增。

**Status**: **PASS** ✓

---

### F5. 原 allowed list 已覆盖文件同样重度使用 v3

**Original severity**: Informational
**Controller adjudication**: 未单独裁决（属于 F4/7 的背景信息）

**Verification**: 原 review 为观察性 finding，不构成 issue。Controller 裁决中 "6个Host test/helper遗漏 → 全部加入" 已隐含确认原 list 覆盖正确。

**Status**: **PASS** ✓（informational，无 action needed）

---

### F6. PromptLocalProvenanceEntry.accepted_evidence_id singular/plural 区分

**Original severity**: Pass
**Controller adjudication**: PASS — 合法上游 `derive_accepted_evidence_id` 不属于 material-pack 字段

**Verification**: 原 review 结论不变。Controller 裁决确认 `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` 引用的 `derive_accepted_evidence_id` 是上游 atom，不是被删除的 `PromptLocalProvenanceEntry.accepted_evidence_id`。

**Status**: **PASS** ✓

---

### F7. 未发现遗漏文件

**Original severity**: Pass
**Controller adjudication**: PASS — dayu/ 与 tests/ 无遗漏；utils/ 已通过 F3 修复加入

**Verification**: 原 review 的 19 文件全仓扫描结论不变。Controller 额外发现 utils/ 的 2 个文件（18 处 v3 引用），已加入 scope。合并后完整清单：
- 原 allowed list: 13 test files
- Amendment 新增: 6 host test files
- Controller 追加: 2 utils/ smoke files
- 总计: 21 files，覆盖全仓所有 v3 引用者

**Status**: **FIXED** ✓（原 review 未覆盖 utils/ 盲区，已由 Controller 修复）

---

## Controller 裁决中 MiMo 原 review 未覆盖的 findings

### C1 import-breakage 证据链

**Controller adjudication**: ACCEPT / FIXED — C1-C3 改为完整 worktree 审查 cluster

**MiMo assessment**: 原 review 未单独审查 C1 import-breakage 问题（因为 review scope 聚焦于 allowed list 和 residue scan，不涉及 C1-C3 执行时序）。Controller 裁决的 cluster 方案最小正确——在完整 worktree 上运行 focused tests 比在不可导入中间态运行更强。

**Status**: 未在原 review 范围内；Controller 裁决已正确处理。

### Cluster 会削弱 checkpoint

**Controller adjudication**: REJECT WITH EVIDENCE — 两路 review 确认 cluster 增强验证可执行性

**MiMo assessment**: 同意 Controller 裁决。完整 worktree 上的 focused test 能真正执行，比不可导入中间态的想象验证更强。

---

## Overall Conclusion

**7/7 原 findings: 2 FIXED + 5 PASS + 0 STILL OPEN**

Amendment 更新后的完整 scope（21 files + `utils/**/*.py` residue scan）覆盖全仓所有 v3 引用者。Controller 裁决正确处理了所有 accepted findings，特别是 utils/ 盲区（原 MiMo review 未覆盖，由 DS review 发现并由 Controller 修复）。

**Gate verdict: PASS — amendment 可接受。**
