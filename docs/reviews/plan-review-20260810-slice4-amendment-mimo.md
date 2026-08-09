# AgentMiMo Plan Review — WU-CLI-DOWNLOAD-01 Slice 4 Amendment

## 1. Review metadata

- Reviewer: AgentMiMo
- Review type: adversarial plan review
- Target: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`
- Base plan: `docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6 / Slice 4 / §9
- Stop-condition evidence: `docs/gateflow/wu-cli-download-01-slice4-amendment-evidence-20260810-060259.md`
- Code evidence HEAD: `399a686f8113fb39c014b98938cfaf0d0d525b3e`
- Date: 2026-08-10

## 2. Review scope

本次 review 针对 Slice 4 plan amendment 的以下核心裁决做 adversarial 审查：

1. 只新增 `sec_downloader.py` / `test_sec_downloader.py` 是否足够
2. `PrefetchedDownloaderEvent` 是否过度 god bag
3. Single transport core 能否保持现有 200/304/empty/failure/cancel 行为
4. Prepared rejected callable 是否有效 deferred-materialization owner，还是被禁止的 glue/compat seam
5. 普通/rejected 两条路径是否均无锁内 HTTP
6. Phase A/B、identity-first、overwrite/repair 矩阵
7. 测试可执行性
8. Scope / stop conditions

## 3. 直接代码证据验证

### 3.1 Root cause 确认

amendment §2 声明的 call chain 经代码验证准确：

- `sec_download_filing_workflow.py:445` — `begin_batch(ticker)` 在 `download_files_stream` 调用前。
- `sec_downloader.py:1488-1516` — `download_files_stream` 同时要求 `StoreDownloadedFile` 与 `BatchToken`。
- `sec_downloader.py:1534-1596` — 同一方法内先 HTTP (`_http_download_if_modified`) 再 `store_file(..., batch=batch)`。
- `sec_download_persistence.py:255-269` — `persist_rejected_filing_artifact` 先 `begin_batch` 再调用 `download_files_stream`。

**直接证据链完整**：普通 source 路径与 rejected artifact 路径均在 `begin_batch` 到 `commit/rollback` 区间内执行远端 HTTP。Root cause 判定正确：SEC downloader 把 transport decision 与 storage materialization 耦合在同一个 required-batch API 中。

### 3.2 Amendment 裁决正确性

amendment 正确识别了 owner 是 `sec_downloader.py`，正确拒绝了五种绕法（伪造 token、直接调用私有方法、内存 payload 复制、重复 HTTP 实现、放宽 validator），与 evidence §4 一致。

## 4. Finding F-01: PrefetchedDownloaderEvent — 接近 god bag 但可接受

**严重性**: Low

**直接证据**: amendment §4.1 定义的 `PrefetchedDownloaderEvent` 有 10 个字段，`content: bytes | None` 使同一类型在不同 event_type 下呈现不同结构：

| event_type | content | reason_code | error |
|---|---|---|---|
| `file_download_started` | None | None | None |
| `file_prefetched` | bytes | None | None |
| `file_skipped` | None | str | None |
| `file_failed` | None | str | str |

**裁决**: **接受，有保留**。

理由：
1. `__post_init__` 封闭校验强制各 event_type 字段一致性，不是无约束 god bag。
2. 该类型只存在于 downloader/pipeline 内部，amendment §4.1 明确禁止进入 tool schema、LLM-facing prompt、CLI schema、storage meta 或 audit contract。
3. 与现有 `DownloaderEvent` 对比：现有类型已有同样模式（`file_meta` 只在 `file_downloaded` 时非空）。`PrefetchedDownloaderEvent` 用 `content` 替代 `file_meta`，是同一设计模式的延续。
4. 拆成四个独立类型会增加 match/union 复杂度，对一个内部-only 类型收益不大。

**保留意见**: 如果 implementation 阶段发现 `__post_init__` 校验无法覆盖所有互斥约束，或需要扩展到 12+ 字段，应拆分。

## 5. Finding F-02: Prepared rejected callable — **可能退化为 glue/compat seam**

**严重性**: **Critical — blocking**

**直接证据**:

amendment §5.2 提出为 rejected artifact 路径新增 "prepared materialization callable"：

> - 输入是不可变的 `tuple[PrefetchedDownloaderEvent, ...]` 与 exact prefetch request facts；创建过程不接受 batch，不执行 storage I/O。
> - callable 的公开调用签名结构化满足现有 `DownloadFilesStream`，但调用时必须校验 `remote_files`、`overwrite`、`existing_files`、`primary_document` 与预取 request exact equality。
> - callable 只重放 started/skipped/failed facts，并对 `file_prefetched` 使用 persistence owner 传入的真实 `StoreDownloadedFile` 与真实 batch materialize。

amendment §5.2 自身承认：
> 若双路 plan review 认定 prepared callable 仍属于不允许的 glue/compat seam，必须 fail 本 amendment 并重新扩充 `sec_download_persistence.py` allowlist。

**问题分析**:

1. **该 callable 本质上是一个 captured-data replay wrapper**：它捕获 prefetch 结果，在被调用时重放。这不是 storage owner 自己的 materialization 逻辑，而是一个外部构造的 replay adapter。

2. **与 AGENTS.md 禁止项的冲突**：
   - "禁止兼容性 wrapper / facade：方法体仅透传到真源模块，不增加有效语义" — prepared callable 不是简单透传，但它增加了 "deferred replay" 语义，这个语义是否 "有效" 取决于是否有更优路径。
   - "禁止胶水 seam" — prepared callable 把 prefetch 层的输出胶合到 persistence 层的输入接口。

3. **更优路径存在**：直接修改 `sec_download_persistence.py` 的 `persist_rejected_filing_artifact` 函数，在 `begin_batch` 前消费 `prefetch_files_stream`，在 batch 内只做 materialization。这是在 storage owner 边界内的自然修改，不需要外部 replay wrapper。

4. **Amendment 的 allowlist 约束自我矛盾**：amendment §3 声明不修改 `sec_download_persistence.py`，但 §5.2 的 prepared callable 实质上要求 `sec_download_persistence.py` 的调用者（`sec_pipeline.py`）改变其调用方式。如果 `sec_pipeline.py` 不在 allowlist 内，这个改变如何实现？

**裁决**: **FAIL — prepared callable 作为 glue seam 不可接受**。

**最优修订**:
- 将 `dayu/fins/pipelines/sec_download_persistence.py` 加入 Slice 4 production allowlist。
- `persist_rejected_filing_artifact` 改为：先消费 `prefetch_files_stream`（无 batch），再 `begin_batch`，在 batch 内逐文件 materialize 已预取 content。
- 删除 prepared callable 设计。
- 保留 `download_files_stream` 的 shared transport core 重构（§5.1）不变。
- 如果需要保持 `sec_download_persistence.py` 不变，则 rejected artifact 路径暂时保留锁内 HTTP，但必须在 amendment 中明确标记为 residual 并设置后续 gate。

## 6. Finding F-03: Single transport core 设计 — 接受

**严重性**: None

**直接证据**:

amendment §5.1 要求 `download_files_stream` 改为组合 `prefetch_files_stream` + `StoreDownloadedFile`：

```text
prefetch_files_stream (唯一 HTTP/transport core)
  -> started/skipped/failed: 无损投影为现有 DownloaderEvent
  -> file_prefetched:
       StoreDownloadedFile(content, batch=真实 caller token)
       cancellation checkpoint
       成功后才投影 DownloaderEvent(event_type="file_downloaded", file_meta=...)
```

代码验证：现有 `download_files_stream`（`sec_downloader.py:1488-1652`）的两个分支（`overwrite=False` 的 conditional download 和 `overwrite=True` 的 unconditional download）确实各自独立调用 `_http_download_if_modified` 和 `_http_download`，然后各自调用 `store_file`。提取为 `prefetch_files_stream` 后，transport decision 逻辑只需存在一处。

**裁决**: **接受**。该设计正确实现了 transport/materialization 分界，保持现有 observable behavior（200/304/empty/failure/cancel/primary 0-byte abort），`download_files` 聚合 facade 也继续委托 `download_files_stream`。

## 7. Finding F-04: AST gate 缺少工具规格

**严重性**: Medium

**直接证据**:

amendment §8 要求 6 项 AST/static gate 证明：

> 1. `prefetch_files_stream` 签名与 body 不可达 `BatchToken`、`StoreDownloadedFile`...
> 2. `_http_download`、`_http_download_if_modified` 及 provider client 调用只可从唯一 prefetch transport core 到达
> 3. 普通 source 与 rejected artifact 两条 call graph 中，`begin_batch` 至 commit/rollback 区间不可达 provider/PDF/Docling I/O
> 4. SEC Phase B 首个 target side effect 之前必经 staged identity comparison
> 5. production 无 `BatchToken(...)` prefetch 构造、fake capability...
> 6. `download_files_stream` 与 prepared replay 只消费 typed prefetch facts

**问题**:
- Python 没有内置 AST reachability analysis。`rg` 可以证明直接调用存在，但不能证明 "不可达"（需要完整的 call graph resolution）。
- amendment 没有指定使用什么工具或脚本来执行这些证明。
- 对于 `download_files_stream` 改为调用 `prefetch_files_stream` 后，如何证明 `_http_download` 不再被 `download_files_stream` 直接调用？简单的 `rg` 搜索可以证明 `_http_download` 在 `download_files_stream` 方法体内不出现，但不能证明通过间接调用链不可达。

**裁决**: **不 blocking，但需要 implementation 阶段补充工具规格**。

**建议**:
- 对于 "body 不可达" 类证明，使用 `rg` 搜索方法体内直接调用 + pyright 确认类型。
- 对于 "call graph 只可从 X 到达" 类证明，使用 `rg` 搜索所有调用点并人工验证。
- §8 应明确：这些证明是 best-effort static analysis + 人工审查，不是形式化验证。

## 8. Finding F-05: Phase A/B 状态机与 identity-first — 接受

**严重性**: None

**直接证据**:

amendment §6 的 SEC Phase A/B 状态机与 base plan §5.6 完全一致：

1. Phase A classify/policy — 短 publication guard 内返回 typed integrity classification
2. Phase A prefetch — 消费 `prefetch_files_stream`，无 batch/lock/callback
3. Phase B begin/latest-copy — 全部 transport 完成后才 `begin_batch`
4. Phase B identity-first — 第一条 target operation 必须是 `classify_staged_source_integrity`
5. Phase B policy — identity 相同时按 latest integrity + overwrite policy
6. Phase B materialization — 逐个 `file_prefetched` 用真实 token 调用
7. Publication — materialization/upsert/validator/atomic commit
8. Revision churn — 最多 3 轮

代码验证：`sec_download_filing_workflow.py:445` 当前在 `download_files_stream` 前 `begin_batch`，amendment 要求改为先 prefetch 再 batch，与 Phase A/B 设计一致。

**裁决**: **接受**。状态机设计正确，与 base plan 不变量兼容。

## 9. Finding F-06: Overwrite/repair 矩阵 — 接受

**严重性**: None

**直接证据**:

amendment §6 第 5 步定义的决策矩阵：

| Phase A status | overwrite | Phase A 行为 | Phase B 行为 |
|---|---|---|---|
| COMPLETE | False | skip，不做 HTTP | — |
| COMPLETE | True | prefetch | identity-first → apply |
| REPAIR_REQUIRED | any | prefetch | identity-first → apply |
| MISSING | any | prefetch | identity-first → create |

Phase B identity-first 后的决策：

| Latest identity 变化 | Latest status | 行为 |
|---|---|---|
| 变化 | any | rollback → 回 Phase A（消耗 1 轮） |
| 不变 | REPAIR_REQUIRED | apply |
| 不变 | MISSING | create apply |
| 不变 | COMPLETE + False | skip |
| 不变 | COMPLETE + True | overwrite apply |

代码验证：`sec_download_filing_workflow.py:529-536` 的 skip 条件检查 `overwrite`、`download_version`、`downloaded_files == 0`、`skipped_files == len(file_results)`。amendment 要求 identity-first 先于这些检查，与 base plan §5.6 一致。

**裁决**: **接受**。矩阵覆盖所有 status/overwrite 组合，identity-first 保证不发布陈旧 payload。

## 10. Finding F-07: 测试可执行性 — 接受但有改进空间

**严重性**: Low

**直接证据**:

amendment §7 的测试矩阵覆盖 10 个 case，每个都有明确的 prefetch contract assertion 和 materialization assertion。

**改进空间**:
- 测试矩阵缺少 "prepared rejected replay" 的 request mismatch case（amendment 提到 "request mismatch fail closed" 但没有具体断言内容）。如果 F-02 导致删除 prepared callable，此 case 自然消失。
- 测试矩阵缺少 `download_files_stream` → `prefetch_files_stream` 集成测试的明确描述。§7 最后一段提到 "保留并更新现有 `download_files_stream`、`download_files` tests，证明它们共享 prefetch core"，但没有具体断言。
- 建议增加一个 case：`download_files_stream` 调用后，验证 HTTP helper 调用次数为 0（证明 transport 只来自 prefetch core）。

**裁决**: **接受**。测试矩阵总体可执行，改进空间不 blocking。

## 11. Finding F-08: Scope / stop conditions — 接受

**严重性**: None

**直接证据**:

amendment §3 定义的 scope 不变量：
- 唯一新增 production allowlist：`sec_downloader.py`
- 唯一新增 test allowlist：`test_sec_downloader.py`
- 不增加或修改其它 production/test allowlist

amendment §11 定义的 11 个 stop conditions，每个都有明确的触发条件和后果。

**问题**：如果 F-02 导致需要扩充 `sec_download_persistence.py` allowlist，这直接触发 §11 的第一个 stop condition："需要增加本 amendment §3 以外的新 production/test allowlist"。这证明 stop conditions 设计正确。

**裁决**: **接受**。Stop conditions 完整且自洽。

## 12. Finding F-09: `download_files_stream` 不是 compatibility wrapper — 接受

**严重性**: None

**直接证据**:

amendment §5.1 明确声明：
> 这不是 compatibility wrapper：`download_files_stream` 继续拥有真实 materialization 语义，并新增明确的 transport/materialization 分界；不新增旧名转发、双实现或 feature flag。

代码验证：`download_files_stream` 当前被以下消费者使用：
- `sec_download_filing_workflow.py:455` — 普通 source download
- `sec_download_persistence.py:265` — rejected artifact download
- `sec_pipeline.py:1661` — 通过 `self._downloader.download_files_stream` 传递

重构后 `download_files_stream` 继续保持相同签名和语义（下载 + materialize），只是内部实现改为 compose prefetch + store。这是真实的语义保持，不是 wrapper。

**裁决**: **接受**。

## 13. 综合裁决

### 结论: **FAIL**

amendment 的 root cause 分析正确，transport/materialization 分界设计合理，Phase A/B 状态机与 base plan 一致，测试矩阵可执行，stop conditions 自洽。但 **prepared rejected callable (F-02) 构成 blocking finding**。

### Blocking findings

| ID | Severity | Finding | 最优修订 |
|---|---|---|---|
| F-02 | **Critical** | Prepared rejected callable 是 captured-data replay wrapper，实质上把 prefetch 层输出胶合到 persistence 层输入接口，构成 glue seam；更优路径是直接修改 `sec_download_persistence.py` 的 `persist_rejected_filing_artifact`，在 `begin_batch` 前消费 prefetch | 将 `sec_download_persistence.py` 加入 Slice 4 production allowlist；`persist_rejected_filing_artifact` 改为先 prefetch 再 batch materialize；删除 prepared callable 设计 |

### Non-blocking findings

| ID | Severity | Finding | 建议 |
|---|---|---|---|
| F-01 | Low | `PrefetchedDownloaderEvent` 接近 god bag 但有封闭校验且内部-only | implementation 阶段监控字段数；若超 12 或校验无法覆盖则拆分 |
| F-04 | Medium | AST gate 缺少工具规格，"不可达" 证明在 Python 中无内置工具 | §8 补充：使用 rg 搜索 + pyright 类型检查 + 人工审查，不声称形式化验证 |
| F-07 | Low | 测试矩阵缺少 `download_files_stream` → `prefetch_files_stream` 集成断言 | §7 补充一个 case：验证 download_files_stream 调用后 HTTP helper 调用数为 0 |

### 最优修订路径

1. **接受** amendment 的 root cause 分析、transport core 设计、Phase A/B 状态机、测试矩阵和 stop conditions。
2. **修订** §3 allowlist：增加 `dayu/fins/pipelines/sec_download_persistence.py` 和 `tests/fins/test_sec_download_persistence.py`（或在现有 test file 中增加 rejected artifact prefetch case）。
3. **修订** §5.2：删除 prepared callable 设计，改为 `persist_rejected_filing_artifact` 自身在 `begin_batch` 前消费 `prefetch_files_stream`。
4. **修订** §7 测试矩阵：增加 `download_files_stream` → `prefetch_files_stream` 集成 case；删除 prepared replay case。
5. **修订** §8：明确 AST/static gate 为 best-effort rg + pyright + 人工审查。
6. 修订后进入双路 re-review。

### 下一动作

amendment 持有者（AgentCodex）按上述修订更新 amendment，两位原 reviewer 分别 re-review。两路均 accepted 前不得恢复 Slice 4 implementation。
