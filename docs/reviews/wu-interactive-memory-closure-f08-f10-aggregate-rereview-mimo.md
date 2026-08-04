# Interactive Conversation Memory Closure F08–F10 Aggregate Re-Review

## Scope

- **Mode**: aggregate re-review（对 Codex fix/audit 的独立复核）
- **Branch**: `codex/interactive-oracle`
- **Base**: `68ba4038` (accepted plan checkpoint)
- **Review range**: `68ba4038..fd15b660` + `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-fix-codex.md`
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-rereview-mimo.md`
- **Included scope**: 6 production files（`compact_material.py`、`compact_pipeline.py`、`compaction.py`、`compaction_operation.py`、`context_governance.py`、`dispatch.py`）、1 prompt file、10 test files、4 review artifacts（MiMo aggregate、DS aggregate、Codex fix、本 artifact）
- **Excluded scope**: generated/vendor/build/cache
- **Review date**: 2026-08-04

## 方法

本 re-review 的任务是独立复核 Codex 对 DS 三项 finding 的 `rejected-with-reason` 裁决，确认两路 aggregate PASS 项目，并验证完整 pytest/flake/coverage/static/digests 证据链。复核方法为：沿正式 producer/pack/source_boundary/operation/provider 路径追踪直接证据，审 git history/owner 模式，寻找能改变 semantic set、identity 或 terminal 且通过 barrier 的反例。

---

## Codex 裁决独立复核

### DS-A：`_validate_operation_selected_pack` 不包含 `previous_compacted_view` blocks

**独立裁决：`rejected-with-reason` 成立。**

**追踪路径**：`select_compact_segment` / `initial_segment_selection` → `CompactSegmentSelection.selected_block_provenance` → `_validate_operation_selected_pack`

**直接证据**：

1. **`previous_compacted_view` 从未进入 `selected_block_provenance`**：
   - `select_compact_segment`（`compact_material.py:836`）的 selection 逻辑通过 `_collective_exclusion_reason` 对所有 previous_compacted_view blocks 标记 `_REASON_PREVIOUS_COMPACTED_VIEW`（`compact_material.py:96`），它们被排除在 `selected` 列表之外。
   - `initial_segment_selection`（`compact_material.py:1384`）显式将所有 previous label 写入 `excluded_reason_codes`，reason 为 `_REASON_PREVIOUS_COMPACTED_VIEW`。
   - `selected_block_provenance_for_material_blocks`（`compact_material.py:1910`）只从 `selected_block_ids` 构造 provenance，而 `selected_block_ids` 不包含 previous。

2. **previous 的独立验证链**：
   - `_previous_compacted_view_pair_from_candidate`（`compact_material.py:2255`）从 accepted `CONTEXT_COMPACTED` candidate 机械映射 previous blocks，block_id 使用 `"previous:{event_id}:..."` 固定前缀。
   - `validate_previous_compacted_view_pair`（`compaction.py`）在 pack 构造时校验 presence、kind、label、数量与文本 exact pairing。
   - `_validate_operation_root_request`（`compaction_operation.py:1584-1593`）验证全部 pack labels（含 previous）与 `CompactInputV2.source_boundary` 精确一致。

3. **proof domain 刻意只覆盖 raw selected delta**：
   - `_validate_operation_selected_pack` 的 `packed_blocks` 只包含 trace/evidence/answer（`compaction_operation.py:1605-1609`），与 `selected_block_provenance` 的 domain 完全对应。
   - 若将 previous 加入 proof domain，每个合法带 previous 的请求会出现 `len(proof) > len(pack)` 假阳性（因为 previous blocks 不在 selected provenance 中），或需要把 previous 也加入 provenance（扩大 contract）。

**反例审计**：

- 交换/篡改 raw selected block 的 refs 或 digest：pipeline snapshot exact proof 或 operation selected-pack multiset 在 provider 前失败。
- 伪造 previous pack 内容：需要绕过 private `_previous_compacted_view_pair_from_candidate`，该函数从 trusted accepted event 机械映射。operation 不持有 raw snapshot，无法区分"合法 request"与"整体伪造的合法 request"——这不是 provider 前漏掉的内部 mismatch，而是把未授权 caller 当成 source owner。
- 若让 operation 重新读取 accepted EventLog 或接收完整 snapshot，会复制 pipeline/material owner 并扩大 request contract。

**结论**：没有找到"由当前正式 producer 产生、改变 durable semantic set、同时通过 provider 前校验"的反例。Codex 裁决正确。

---

### DS-B：`_requires_budget_acceptance` 硬编码为 `True`

**独立裁决：`rejected-with-reason` 成立。**

**追踪路径**：`_requires_budget_acceptance` → `_run_compaction_operation:1150` 的 `hard_threshold_tokens` 闸门

**直接证据**：

1. **Git history 确认这是既有 Host policy**：
   - `git blame` 确认该函数早于 F08–F10 存在。
   - commit `bd1d3e94`（2026-07-20，`WU-SEMANTIC-OWNERSHIP-01`）把旧的 `return request.trigger_source is PROACTIVE` 明确改为 `del request; return True`。
   - 同一变更的 docstring 明确：compaction owner 必须在接受 candidate 前统一执行 hard threshold 验收，proactive 与 reactive 都不能把仍明显越界的输出交给 dispatch/Engine loop。

2. **当前行为正确**：
   - `_run_compaction_operation:1150` 的 `if _requires_budget_acceptance(request) and (last_budget >= request.budget_before_compact.hard_threshold_tokens)` 分支始终执行 hard threshold 检查。
   - 已有 owner tests 覆盖 hard-threshold rejection/repair 路径。

3. **删除或条件化会暗示存在绕过硬闸门的合法路径**：
   - 函数名表达的是 Host policy requirement，参数保留 request-level policy seam。
   - 无 correctness 或维护性收益足以支持本 slice 改动。

**结论**：这是既有 accepted Host hard-threshold contract，不是 F08–F10 引入的死分支或待实现 conditional。Codex 裁决正确。

---

### DS-C：`DurableCompactorProposalManifestRecorder` 内建 `PayloadStore()`

**独立裁决：`rejected-with-reason` 成立。**

**追踪路径**：`DurableCompactorProposalManifestRecorder.__init__` → `PayloadStore` → `write_sqlite_payload` / `write_payload_descriptor_for_artifact` / `read_payload_descriptor`

**直接证据**：

1. **`PayloadStore` 是无状态方法集合**：
   - 类文档（`durable/payload.py:155-160`）明确："该类不持有连接、不创建 transaction；所有 mutation 都必须发生在调用方传入的 HostTransaction 中。"
   - 所有方法只将调用方传入的 `HostTransaction` 与 typed request 委托给 durable payload primitive。
   - 无 constructor state、无缓存、无 identity counter。

2. **同类模式一致**：
   - `DurableRunnerCallManifestRecorder` 同样在 recorder 内创建 `EventLogStore()` 与 `PayloadStore()`。
   - 需要共享外部 state 的 Host providers 才使用注入。

3. **F09 diff 没有引入该内建实例**：
   - F09 diff（`47b6a2af..d04f7531`）只把同一 `manifest_descriptor.payload_ref` 与同一 `manifest_digest` 填入 canonical EventLog row，并从同一 projection descriptor 填充 manifest/hot projection triple。
   - recorder 在一个 `run_write` transaction 内先写 projection descriptor、再写 manifest descriptor、再 append EventLog；hot payload、row descriptor 与返回的 `CompactorProposalManifestReference` 全部复用这两个 descriptor 的同源值。

**结论**：增加 optional `payload_store` 参数会扩大 constructor/public seam、产生默认/注入双装配路径，却不能修复任何当前 identity 问题。Codex 裁决正确。

---

## 两路 Aggregate PASS 项目复核

### MiMo Aggregate PASS 项目

| PASS 项 | 独立验证 | 直接证据 |
|---------|---------|---------|
| F08 summary null/meaningful | ✅ | prompt 三子弹点自足定义；governance 接受合法 null；memory projector 通过完整生产链验证 |
| F09 manifest identity | ✅ | projection/manifest descriptor、hot atoms、EventLog row 与 formal resolver 使用同源 ref/digest/size；mismatch fail closed |
| F10 atomic selection/budget | ✅ | collective exclusion 后按 turn-group atomic unit strict prefix；首个 oversized 不越 cap、不拆组、不跳过 |
| root/transient proof | ✅ | pipeline snapshot exact proof；root raw partition；operation pass per-id exact subset、无重叠遗漏 |
| repair binding | ✅ | request digest + source-boundary digest 双绑定；root→root 保留，root/tier/boundary 变化清空 |
| durable terminal/race | ✅ | operation 仅 aggregate root 产出 accepted truth；dispatch terminal CAS 拒绝 multiple；stale/late 结果 fail closed |
| Memory/RunInput/artifact fork | ✅ | accepted compact EventLog 是 memory 单向真源；post-compact re-freeze 使用最新 snapshot |
| compat/schema/public drift | ✅ | 无 alias、optional shim、旧 digest fallback 或下游补偿 |
| LLM governance leakage | ✅ | material/repair projection 剥离 canonical refs、digest、cursor 与 provenance map |
| ownership/maintainability | ✅ | 单一 `_packed_content_digest`；无新增 God helper、反向依赖或重复 semantic owner |

### DS Cross-Slice PASS 项目

| PASS 项 | 独立验证 | 直接证据 |
|---------|---------|---------|
| F08 prompt → F10 material → memory semantic null flow | ✅ | prompt 定义 meaningful/null；accept barrier 不对 null 做 LOW_INFORMATION；memory projector 清空旧 summary |
| F09 manifest → F10 operation 六条退出路径 | ✅ | 成功/QUALITY_CHECK_REJECTED/PROPOSAL_FAILED/CANCELLATION/non-repairable contract failure/exhaustion 均有 manifest 记录或正确不记录 |
| stale/late/double terminal | ✅ | compaction CAS、dispatch terminal CAS、post-compact Run status re-read 三层保护 |
| identity mismatch | ✅ | CompactAcceptedTruthV2.validate_input_binding、repair feedback 三层检查、pass identity 验证、manifest identity 验证、worker accept CAS |
| LLM governance field leaks | ✅ | llm_json() 剥离 provenance_map；to_json() 只暴露 readable_text/source_kind；repair feedback 不含 request_digest/source_boundary_digest |
| Memory/RunInput/artifact fork | ✅ | post-compact re-freeze 使用最新 memory projection；compact artifact → memory 单向投影；candidate sizing fork protection |

---

## 证据链验证

### pytest

| 检查项 | 结果 |
|-------|------|
| Focused owner suite（10 test files） | 418 passed, 1 skipped |
| Skip 原因 | opt-in real provider smoke（`test_public_compact_smoke.py`） |

### Pyright

| 检查项 | 结果 |
|-------|------|
| 6 production files | 0 errors, 0 warnings, 0 informations |

### Frozen Baseline Digests

| 文件 | Expected SHA-256 | Current SHA-256 | Status |
|------|------------------|-----------------|--------|
| `docs/cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` | ✓ Match |
| `docs/cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` | ✓ Match |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` | ✓ Match |

### 工作树状态

| 检查项 | 结果 |
|-------|------|
| `git status --short -- ':(exclude)docs/'` | 无输出（无生产改动） |

---

## Findings

### 未发现实质性问题

经过对 Codex fix/audit 的独立逐项复核、两路 aggregate PASS 项目的交叉验证、完整证据链确认，未发现实质性问题。

---

## Open Questions

- 无。

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**：按 gate 约束未运行。F08（summary null）、F09（formal Tool Trace）、F10（turn-group atomicity）的真实 provider 端到端行为留待后续 Oracle evidence/readiness gate。

2. **Previous view provenance gap**（DS Finding 1）：Codex 已裁决为 `rejected-with-reason`，非 deferred correctness risk。当前调用路径安全，previous_compacted_view 从未进入 selected_block_provenance。

3. **Legacy compactor path 无 manifest recording**：F09 design 中已接受的限制；只有 `CompactorProposalPreparedCompactor` protocol 实现才能享有正式 Tool Trace identity。

---

## Final Conclusion

**PASS**

本 aggregate re-review 独立复核了 Codex 对 DS 三项 finding 的 `rejected-with-reason` 裁决：

1. **DS-A**（`_validate_operation_selected_pack` 不包含 previous_compacted_view）：裁决成立。`previous_compacted_view` 从未进入 `selected_block_provenance`，proof domain 刻意只覆盖 raw selected delta。没有找到能改变 durable semantic set 且通过 provider 前校验的反例。

2. **DS-B**（`_requires_budget_acceptance` 恒真）：裁决成立。这是既有 accepted Host hard-threshold contract（`bd1d3e94`，2026-07-20），不是 F08–F10 引入的死分支。

3. **DS-C**（`PayloadStore` 内建）：裁决成立。`PayloadStore` 是无状态方法集合，同类模式一致，增加 DI seam 无 correctness 收益。

两路 aggregate PASS 项目全部通过独立验证。完整证据链确认：418 passed / 1 skipped、pyright 0 errors、frozen baseline digests 全部匹配、工作树无生产改动。

无实质性问题，无 blocking open questions，无 unclassified residual risk。
