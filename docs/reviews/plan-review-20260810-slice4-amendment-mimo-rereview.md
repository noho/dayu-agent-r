# AgentMiMo Plan Re-Review — WU-CLI-DOWNLOAD-01 Slice 4 Amendment (revised)

## 1. Review metadata

- Reviewer: AgentMiMo
- Review type: adversarial re-review
- Target: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`（修订版）
- Base plan: `docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6 / Slice 4 / §9
- Stop-condition evidence: `docs/gateflow/wu-cli-download-01-slice4-amendment-evidence-20260810-060259.md`
- 第一轮 review: `docs/reviews/plan-review-20260810-slice4-amendment-mimo.md`
- Code evidence HEAD: `399a686f8113fb39c014b98938cfaf0d0d525b3e`
- Date: 2026-08-10

## 2. Re-review scope

验证修订后 amendment 是否逐项关闭第一轮全部 finding，并审查以下新增关注点：

1. persistence owner 语义是否无新 seam/owner drift
2. private discriminated prefetch contract 是否封闭
3. repair unconditional 语义是否正确
4. deterministic barriers 是否可执行
5. static gate 可执行性
6. malformed sha256 strict error 边界

## 3. 第一轮 finding 逐项关闭验证

### F-01 (PrefetchedDownloaderEvent god bag) → **已关闭**

**修订前**: 单一 `PrefetchedDownloaderEvent` dataclass 有 10 个字段，`content: bytes | None` 在不同 event_type 下呈现不同结构。

**修订后**: §4.1 改为四个 frozen/slots 模块私有 discriminated variants：

```python
_PrefetchStarted(kind="started", descriptor)
_PrefetchedFile(kind="prefetched", descriptor, http_status, http_etag, http_last_modified, content: bytes)
_PrefetchSkipped(kind="skipped", descriptor, http_status, reason_code, reason_message)
_PrefetchFailed(kind="failed", descriptor, http_status, reason_code, reason_message, error)
_PrefetchEvent = _PrefetchStarted | _PrefetchedFile | _PrefetchSkipped | _PrefetchFailed
```

**验证**:
- 每个 variant 的字段集合互斥，不存在 `content=None` 模拟另一 variant 的问题。✓
- `_PrefetchedFile.content` 是非空 `bytes`，不携带 `FileObjectMeta`/batch/URI/path/reason/error。✓
- `_PrefetchSkipped` 没有 content/file_meta/error。✓
- `_PrefetchFailed` 没有 content/file_meta。✓
- 所有 variant 模块私有，不从 `dayu.fins.downloaders` re-export。✓
- §4.1 末尾保留防御性约束：若单个 variant 仍无法封闭互斥约束，必须继续拆分。✓

**裁决**: **关闭**。Discriminated variants 比原单一 dataclass 更安全，互斥语义由类型系统强制。

### F-02 (Prepared callable glue seam) → **已关闭**

**修订前**: Prepared rejected callable 是 captured-data replay wrapper，捕获 prefetch 结果后伪装为 `DownloadFilesStream` 签名重放。

**修订后**:
- §3.1 将 `dayu/fins/pipelines/sec_download_persistence.py` 加入 production allowlist。✓
- §5.2 完全删除 prepared callable 设计。✓
- §5.2 改为 `persist_rejected_filing_artifact` 直接接收并调用 `SecDownloader.prefetch_files_stream`。✓
- §5.2 流程：prefetch 完整消费（无 batch）→ cancellation checkpoint → begin_batch → 逐文件 materialize → 保持既有 rejected semantics → commit/rollback。✓
- §3.4 明确禁止 "prepared callable、replay wrapper、request-identity replay 校验、legacy path、默认参数"。✓
- §11 review finding adjudication 表确认 "allowlist 增加 `sec_download_persistence.py`；由 `persist_rejected_filing_artifact` 直接 preload 再用真实 batch materialize；删除 prepared/replay 设计"。✓

**验证代码证据**:
- `sec_download_persistence.py:255` 当前 `begin_batch` 在 `download_files_stream` 调用前。
- `sec_download_persistence.py:265` 当前 `async for event in download_files_stream(...)` 在 batch 内。
- 修订后要求：prefetch 在 `begin_batch` 前完成，batch 内只做 materialization。
- 这是在 persistence owner 边界内的自然修改，不引入外部 replay wrapper。

**裁决**: **关闭**。Prepared callable 设计已完全删除；persistence owner 直接消费 typed stream，不构成 glue seam。

### F-04 (AST gate 缺少工具规格) → **已关闭**

**修订前**: §8 要求 6 项 AST/static gate 证明，但没有指定工具。

**修订后**: §8 明确四类证据：

1. `rg` 枚举全部定义与调用点。✓
2. Python AST 脚本（`workspace/tmp/wu_cli_download_01_slice4_static_gate.py`）。✓
3. Full pyright 验证。✓
4. 人工 call-graph review，记录 `file:line` 证据。✓

§8 明确声明："任何单项都不能单独声称形式化证明 Python 动态调用图不可达"。✓

§8 提供了可执行的 rg 命令集：
```bash
rg -n "def (download_files_stream|prefetch_files_stream|persist_rejected_filing_artifact)|..." dayu tests
rg -n "_http_download(_if_modified)?\(|_execute_sec_request\(|begin_batch\(|..." dayu/fins/downloaders dayu/fins/pipelines dayu/fins/storage tests/fins
```

**裁决**: **关闭**。Static gate 现在有可执行工具规格，且明确不是形式化 reachability 证明。

### F-07 (测试矩阵缺 shared-core 断言) → **已关闭**

**修订前**: 测试矩阵缺少 `download_files_stream` → `prefetch_files_stream` 集成断言。

**修订后**: §7.1 增加 "shared-core integration" case：

> spy prefetch core 返回 started/prefetched/skipped/failed variants → 真实 `download_files_stream` 逐个调用唯一 materializer；不存在旧直接 transport 分支

§5.1 也明确要求：
> `tests/fins/test_sec_downloader.py` 必须增加 shared-core 集成断言：替换/spy `prefetch_files_stream` 返回预设 typed variants，调用真实 `download_files_stream`，证明输出及 callback/token 行为完全来自该 core 且旧直接 transport branch 不再执行。

**裁决**: **关闭**。Shared-core 集成断言已明确纳入测试矩阵。

## 4. 新增关注点验证

### 4.1 Persistence owner 语义 — 无新 seam/owner drift

**验证**:

修订后 §5.2 的 `persist_rejected_filing_artifact` 流程：

```text
prefetch_files_stream（无 batch、无 storage callback）
  → cancellation checkpoint
  → begin_batch(ticker)
  → 逐文件 materialize_prefetched_event（使用真实 batch）
  → 保持既有 rejected semantics
  → commit/rollback
```

当前 `sec_download_persistence.py` 的 callback 构造（`build_rejected_store_file`）不改变，只改变调用时序。✓

§4.3 定义唯一 materializer：`sec_downloader.py` 拥有 `prefetch variant → callback invocation → DownloaderEvent` 的映射。persistence 只把 typed intermediate 逐个交给 materializer，不 inspect raw fields 或重算 transport reason。✓

§5.2 硬约束："删除 `DownloadFilesStream` 仅为该路径服务的 dependency/Protocol 形态时，应改为直接、typed、具体参数；不得新增替代 capability Protocol、factory、replay adapter 或兼容 facade。" ✓

`sec_download_persistence.py` 已 import `sec_downloader`（`RemoteFileDescriptor`、`StoreDownloadedFile`），新增对 `_PrefetchEvent` types 和 materializer 的依赖不改变依赖方向。✓

**裁决**: **无新 seam**。Persistence owner 继续拥有 callback 构造、transaction 和 rejected semantics；downloader owner 继续拥有 transport 和 event projection。唯一变化是调用时序从"batch 内 HTTP"改为"prefetch → batch materialize"。

### 4.2 Private discriminated prefetch contract — 封闭

**验证**:

§4.1 四个 variant 均为 `@dataclass(frozen=True, slots=True)`。✓

类型别名 `_PrefetchEvent` 是 union，模块私有。✓

§4.1 禁止项：
- "不从 `dayu.fins.downloaders` re-export" ✓
- "不进入公共 schema、storage meta、durable audit、LLM-facing 文本或 compatibility contract" ✓

§3.4 禁止项：
- "不把 batch、callback、repository、storage path 或 durable identity 塞入 extra payload" ✓

§4.1 防御性约束："若 implementation 发现单个 variant 或共享字段仍无法在类型构造时封闭互斥约束，必须继续拆成更窄的 typed variants；禁止退回一个包含多个 optional state 字段的大 dataclass。" ✓

**裁决**: **封闭**。Discriminated variants 互斥语义由类型系统强制；模块私有；防御性约束防止回退。

### 4.3 Repair unconditional 语义 — 正确

**验证**:

§4.2 定义 `allow_not_modified: bool` 为 required transport 参数：

> - `True` 才允许使用 existing ETag/Last-Modified 发 conditional request 并产生 304 skip。
> - `False` 必须走现有 unconditional transport helper，不发送 conditional reuse decision。
> - repair target 无论原请求 `overwrite_existing` 为何都必须传 `False`，取得完整 replacement。

§6 Phase A prefetch：
> SEC repair 强制 `allow_not_modified=False`；普通 overwrite 同样 unconditional。✓

§6 Phase B policy：
> identity 相同才使用 latest integrity 与原始 request-level `overwrite_existing`。transport 的 `allow_not_modified` 绝不覆盖或替代该 policy 值。✓

§7.1 测试矩阵 "repair transport" case：
> `allow_not_modified=False` 时强制 unconditional，不产生 304。Phase B 仍保留原请求 overwrite policy。✓

§12 stop condition：
> repair prefetch 允许 conditional/304，request-level overwrite 被 transport 参数覆写，或 `overwrite_existing=True` 袔 latest COMPLETE 转成 skip。✓

**裁决**: **正确**。`allow_not_modified` 是 transport-level 参数，与 request-level `overwrite_existing` 正交。Repair 强制 unconditional；Phase B policy 使用原 request 值。两者不混淆。

### 4.4 Deterministic barriers — 可执行

**验证**:

§7 声明："所有新增 thread/process/race tests 只使用 `threading.Event`、`multiprocessing.Event`、`Barrier` 与 bounded test deadline 协调；禁止 `sleep`、概率循环或 production timing hook。" ✓

§7.2 rejected persistence cancel 测试：
> fake prefetch 在返回最后一个 typed event 后设置 `prefetch_returned` 并等待 test-owned `release_prefetch_return` Event；测试线程观察该 Event 后主动设置 canonical cancel flag，再释放 generator 返回。

这是精确的 Event-based 协调，不是 sleep 猜时序。✓

§7.3 Phase A/B race 矩阵：

1. **同 target 双 overwrite**: `phase_a_classified` Barrier → `prefetch_complete` Barrier → `a_committed` Event → `b_retry_started` Event。✓
2. **三轮 revision churn**: `round_n_prefetched` Event → `round_n_published` Event。✓
3. **不同 target union**: `prefetch_complete` Barrier → `a_committed` Event。✓
4. **ordering spies**: `SpyBatchRepository` 记录 `begin/staged_classify/commit/rollback/release`，`SpyStoreFile` 记录首次 callback 与 payload digest；断言 `prefetch_complete < begin < staged_classify < first_store < commit`。✓

§7.3 第 6 条明确断言每轮 ordering，identity 变化轮不存在 `first_store`。✓

§12 stop condition："deterministic race/cancel 测试需要 sleep、概率时序或 production timing hook" 触发停止。✓

**裁决**: **可执行**。所有 barrier/Event 序列精确指定，不依赖 sleep 或概率时序。

### 4.5 Static gate 可执行性 — 已指定

**验证**:

§8 提供了 5 条 rg 命令和 1 条 AST 脚本命令：

```bash
rg -n "def (download_files_stream|prefetch_files_stream|persist_rejected_filing_artifact)|..." dayu tests
rg -n "_http_download(_if_modified)?\(|_execute_sec_request\(|begin_batch\(|..." dayu/fins/... tests/fins
rg -n "SourceDocumentRepositoryProtocol|class .*SourceDocumentRepository|..." dayu tests
rg -n "BatchToken\(|getattr\(|hasattr\(|prepared|replay|compat" dayu/fins/...
python workspace/tmp/wu_cli_download_01_slice4_static_gate.py
python -m pyright dayu/ tests/ utils/
```

AST 脚本至少检查：
- `prefetch_files_stream` required 参数、annotation 与直接 body 不包含 batch/callback/repository/`FileObjectMeta`/begin/commit/rollback。✓
- `download_files_stream` 直接调用 `prefetch_files_stream`，且不直接调用 HTTP/provider helpers。✓
- 所有 `_http_download`、`_http_download_if_modified`、`_execute_sec_request` 调用点被完整列出并输出供人工复核。✓
- production 不存在 prefetch `BatchToken(...)` 构造、prepared/replay adapter、fake capability、compat alias/wrapper、`getattr/hasattr` fallback 或新增 timeout。✓

§8 明确："人工 call-graph review 必须明确记录：普通 SEC 路径、rejected 路径、CN 路径。若因动态 dispatch 或独立 Protocol implementer 而无法建立可信调用链，触发 stop condition。" ✓

**裁决**: **可执行**。四类证据各有具体工具/命令/脚本；AST 脚本检查项明确；人工 review 有明确输出要求和 stop condition。

### 4.6 Malformed sha256 strict error — 正确，无新 seam

**验证**:

§6.1 定义：

> - `sha256` 非字符串、空串或不满足 canonical 64 位十六进制摘要结构属于 meta 结构错误，沿用 strict storage error 立即失败；不得把 malformed sha256 降级为 `DIGEST_MISMATCH`、`REPAIR_REQUIRED`、`UNKNOWN` 或 repair fallback。
> - 只有结构合法的 expected sha256 与实际 physical bytes 摘要不同，才分类为 `DIGEST_MISMATCH`。

**代码证据验证**: base plan §5.6 定义 `SourceIntegrityReason` 为 `PHYSICAL_FILE_MISSING | SIZE_MISMATCH | DIGEST_MISMATCH`。`DIGEST_MISMATCH` 隐含前提是 expected digest 结构合法。amendment §6.1 只是显式声明了这个前提，不改变 owner 或新增类型。✓

§7.3 corruption 测试矩阵：
> malformed sha256 单独断言 strict 结构错误且 provider/prefetch/batch 均未调用。✓

§12 stop condition：
> malformed sha256 被归类为 repair/UNKNOWN 而非 strict 结构错误，或为通过测试放宽 snapshot/read/complete validator。✓

**裁决**: **正确，无新 seam**。Malformed sha256 是 strict storage error 的自然边界；§6.1 只是显式声明了 base plan 隐含的前提，不引入新类型、新 owner 或新 fallback。

## 5. 与 base plan 一致性验证

### 5.1 §5.6 Storage concurrency 与 typed integrity

- Amendment §6 的 Phase A/B 状态机与 base plan §5.6 完全一致。✓
- Base plan §5.6 的 identity-first 决策：identity/revision 变化 → rollback → 回 Phase A。Amendment §6 第 4 步一致。✓
- Base plan §5.6 的 overwrite 矩阵：`COMPLETE + False` skip、`COMPLETE + True` overwrite、`REPAIR_REQUIRED` apply、`MISSING` create。Amendment §6 第 5 步一致。✓
- Base plan §5.6 的 3 轮 revision churn。Amendment §6 第 8 步一致。✓
- Base plan §5.6 "HTTP/PDF/Docling 不得出现在 writer/publication lock 区间"。Amendment §5.2 要求 prefetch 在 `begin_batch` 前完成。✓

### 5.2 Slice 4 allowed production files

- Base plan Slice 4 production allowlist 包含 `sec_download_filing_workflow.py`、`sec_pipeline.py` 等。✓
- Amendment §3.1 新增 `sec_downloader.py` 和 `sec_download_persistence.py`。✓
- 不修改 base plan 已列出的文件。✓

### 5.3 Slice 4 allowed test files

- Base plan Slice 4 test allowlist 包含 `test_sec_pipeline_download.py`。✓
- Amendment §3.3 确认 rejected persistence 测试落在该文件。✓
- Amendment §3.2 新增 `test_sec_downloader.py`。✓

### 5.4 Slice 4 stop condition

- Base plan Slice 4 stop condition 要求 "AST/call-graph 与 barrier 双证据证明所有外部 I/O 在 writer/publication lock 外"。✓
- Amendment §8 提供了四类证据规格。✓
- Base plan stop condition 要求 "identity 变化后仍发布旧 prefetch、overwrite=True 被转成 skip" 触发停止。Amendment §12 一致。✓

## 6. 综合裁决

### 结论: **PASS**

修订后 amendment 逐项关闭了第一轮全部 finding：

| 原 Finding | 状态 | 验证 |
|---|---|---|
| F-01 god bag | **关闭** | 改为 discriminated variants，互斥由类型系统强制 |
| F-02 glue seam | **关闭** | Prepared callable 完全删除；persistence owner 直接消费 typed stream |
| F-04 AST gate | **关闭** | 指定 rg + AST 脚本 + pyright + 人工 review，明确非形式化证明 |
| F-07 缺集成断言 | **关闭** | Shared-core integration case 纳入测试矩阵 |

新增关注点均无问题：

| 关注点 | 状态 |
|---|---|
| Persistence owner 语义 | 无新 seam/owner drift |
| Private discriminated contract | 封闭，模块私有，防御性约束 |
| Repair unconditional | 正确，transport/policy 正交 |
| Deterministic barriers | 可执行，Event-based 协调 |
| Static gate 可执行性 | 已指定工具/命令/脚本 |
| Malformed sha256 strict error | 正确，无新 seam |

### Non-blocking observations

| ID | Severity | Observation | 建议 |
|---|---|---|---|
| O-1 | Low | §5.2 未指定 `persist_rejected_filing_artifact` 新签名的精确参数类型（prefetch stream callable 和 materializer callable 的具体类型） | implementation 阶段按 §4.3 "直接、typed、具体参数" 原则定义；plan 层面不 blocking |
| O-2 | Low | §7.2 rejected persistence cancel 测试依赖 fake prefetch generator 的 Event 协调，implementation 时需确保 generator cleanup 正确 | implementation 阶段验证 generator finalization；plan 层面不 blocking |

### 下一动作

本 re-review 结论为 PASS。等待 AgentDS 独立 re-review 结论。两路均 PASS 且总控裁决后，可恢复 Slice 4 implementation。
