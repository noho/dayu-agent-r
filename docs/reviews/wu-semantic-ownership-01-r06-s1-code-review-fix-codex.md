# WU-SEMANTIC-OWNERSHIP-01 R06-S1 Code Review Fix — AgentCodex

## 1. Gate 身份与结论

- Work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 cumulative code-review fix。
- Controller 输入：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-controller-adjudication.md`。
- 本 gate 只闭合 Controller accepted `R06-S1-CR-F01..03`；不是新 WU，不进入 S2/S3，不创建中间 accepted commit。
- 本 gate authored scope：两个允许 production owner、一个既有 S1 owner test 文件与本 artifact；没有修改 protocol/wrapper、control/controller/reviewer/design/README 或其它产品文件。
- 最终状态：`R06-S1-CR-F01..03` 全部已修复；blocking question 为 0。

**READY_FOR_CONTROLLER_VALIDATION**

## 2. 第一性原理与 semantic owner

三项 finding 的动机均成立，严重性与 Controller 的 LOW 裁决相符：它们不会改变 S1 已成立的 transaction correctness，但会让同一 owner contract 出现结构或返回语义分叉。

1. Published read guard 的最小可审计不变量是 outer public entry 只获取一次 guard，并把路径/I/O 交给 private unguarded helper。`read_rejected_filing_file_bytes` 原先在 public guard 内直接做路径解析与 I/O，违反 accepted plan §4.2 的全称 read-graph 约束。owner 是 `_FsMaintenanceMixin`。
2. Processed meta 的唯一 durable 文件名由 storage path/read owner 承诺。实现只读 `tool_snapshot_meta.json`，原 docstring 却虚构 `meta.json` fallback。正确动作是修文档真源，不是实现兼容读取。owner 是 `_FsProcessedMixin.get_processed_meta` 与其 path/read graph。
3. `ProcessedDocumentRepositoryProtocol.mark_processed_reprocess_required(...) -> None` 是公开 mutation 返回 contract 真源。shared core/private impl 的 `bool` 无生产消费者，属于死的第二套 success 语义。owner 是公开 protocol，shared core 是直接实现边界。

修复不需要 ambient marker、重入锁、public 参数、optional/default batch、兼容分支、fallback、统一 authorization 或新 framework。

## 3. Finding closure 与直接 diff 证据

### 3.1 R06-S1-CR-F01 — maintenance private unguarded read graph

状态：**已修复**。

直接代码证据：

- `dayu/fins/storage/_fs_maintenance_core.py:401-411`：public entry 只规范化 ticker/document ID、获取 publication guard、委托 `_read_rejected_filing_file_bytes_unguarded(...)`，并在 `finally` 释放 guard。
- `dayu/fins/storage/_fs_maintenance_core.py:413-445`：新增 typed private helper；参数为三个显式 `str`，完整中文 docstring 含 `Args/Returns/Raises`。
- helper 自己调用 `_rejected_filing_file_path_for_read(...)` 完成 filename/path containment 校验，自己拥有 missing、directory 与 `read_bytes()` 分支；public entry 不保留第二套路径/I/O 语义。
- 没有 ambient “guard held” marker、重入获取、public compatibility 参数或 BatchToken/layout 推断。

Owner tests：

- `tests/fins/test_fins_storage_atomicity.py:470-500`：通过 public entry 覆盖 success、missing 与 directory 行为。
- `tests/fins/test_fins_storage_atomicity.py:530-584`：窄 monkeypatch 证明 public entry 将规范化后的 `AAPL` / `fil_rejected` 和原 filename 精确委托给 private helper。
- AST read-graph scan：全部 `_fs_*_core.py` 的 `self.<public method>(...)` 调用为 `[]`；maintenance public entry 的调用闭集精确为 `_normalize_ticker`、`_normalize_document_id`、`_acquire_publication_guard`、`_read_rejected_filing_file_bytes_unguarded`、`_release_lock_token`。

### 3.2 R06-S1-CR-F02 — processed meta 唯一读取 contract

状态：**已修复**。

直接代码证据：

- `dayu/fins/storage/_fs_processed_core.py:181-198`：docstring 只承诺 published `tool_snapshot_meta.json`，`FileNotFoundError` 也只说明该唯一文件不存在。
- `dayu/fins/storage/_fs_processed_core.py:208-230`：既有 private read graph 仍只从 `_processed_meta_path_for_read(...)` 取得唯一 path；没有新增 fallback 或旧布局兼容。
- `tests/fins/test_fins_storage_atomicity.py:388-399`：在 owner path 旁放置内容冲突的 legacy `meta.json` 时，读取仍返回 `tool_snapshot_meta.json` 内容；删除 tool snapshot 文件且保留 legacy 文件后，精确抛出包含 `tool_snapshot_meta.json` 的 `FileNotFoundError`。
- owner/test 范围 `优先读取|回退|fallback|两种元数据` scan 为 0。

### 3.3 R06-S1-CR-F03 — reprocess marker 统一 `None` contract

状态：**已修复**。

直接代码证据：

- `dayu/fins/storage/_fs_processed_core.py:234-261`：shared-core public method 返回类型改为 `None`；`required=False` 在 capability resolve 后直接 no-op，不再产生 `False`。
- `dayu/fins/storage/_fs_processed_core.py:263-293`：private impl 返回类型改为 `None`；目标缺失直接 no-op，目标存在时仍写入 `reprocess_required=True` 与新的 `updated_at`，副作用不变。
- protocol 与 repository wrapper 原本已经准确声明 `-> None`，本 gate 未做机械改动。
- `tests/fins/test_fins_storage_atomicity.py:319-377`：明确断言 required=False、存在目标、缺失目标的 core public 返回均为 `None`；false 分支 commit 前后完整 meta 相等，存在目标写入标记，缺失目标不创建 meta；同时直接断言 private impl 返回 `None` 且存在目标副作用成立。

返回值消费扫描：

- `dayu/fins` 中共有 7 个真实 `mark_processed_reprocess_required` call expression。
- 7 个调用的 AST parent 全部为独立 `Expr`；`production_return_consumers=[]`。
- tests 中对返回值的 `is None` 只用于本次 owner contract 验证，不是业务消费者。

## 4. 精确 authored scope

本 gate 实际 authored paths：

- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/_fs_processed_core.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-codex.md`

其余累计 S1 dirty files、Controller control/validation 与两路 reviewer artifacts 均为本 gate 进入前的既有工作区状态，本 gate 未修改。没有 stage、commit、push 或 PR 动作。

## 5. 测试与 coverage

所有命令均在 `source .venv/bin/activate` 后运行。

### 5.1 Focused tests

- 三项直接 owner tests：`3 passed in 0.40s`。
- accepted plan §7.1 focused matrix：`109 passed, 61 deselected, 3 warnings in 3.05s`。
- 相比既有 108，新增的 1 个 pass 是 maintenance public-to-private delegation owner test。

### 5.2 四个 S1 tests 完整矩阵

同一 coverage session 完整运行：

- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`

结果：`207 passed, 3 warnings in 9.92s`。三条 warning 均来自第三方 `edgar` deprecated imports，不是本 gate 新增失败。

### 5.3 Changed production line coverage

coverage data：`/tmp/dayu-r06-s1-cr-fix.coverage`；JSON：`/tmp/dayu-r06-s1-cr-fix-coverage.json`。branch coverage 未启用。

| 文件 | covered/statements | line coverage |
| --- | ---: | ---: |
| `document_models.py` | `384/399` | `96%` |
| `_fs_blob_core.py` | `54/58` | `93%` |
| `_fs_company_meta_core.py` | `115/119` | `97%` |
| `_fs_maintenance_core.py` | `138/148` | `93%` |
| `_fs_processed_core.py` | `109/116` | `94%` |
| `_fs_source_document_core.py` | `378/460` | `82%` |
| `_fs_storage_infra.py` | `576/650` | `89%` |
| `fs_batching_repository.py` | `17/18` | `94%` |
| `fs_company_meta_repository.py` | `18/18` | `100%` |
| `fs_document_blob_repository.py` | `20/20` | `100%` |
| `fs_filing_maintenance_repository.py` | `29/29` | `100%` |
| `fs_processed_document_repository.py` | `25/26` | `96%` |
| `fs_source_document_repository.py` | `71/79` | `90%` |
| `local_file_source.py` | `20/20` | `100%` |
| `repository_protocols.py` | `60/60` | `100%` |

全部累计 S1 changed production files 均 `>=80%`；本 gate 两个 production owner 分别为 `93%` 与 `94%`。

## 6. Typing、Ruff 与全仓基线

### 6.1 Scoped

- 15 个累计 S1 production files + 4 个 S1 tests 的 Ruff：`All checks passed!`。
- 同一 scoped pyright：`0 errors, 0 warnings, 0 informations`。
- 更窄的本 gate 两个 production owner + changed test 也为 Ruff pass、pyright 0。

### 6.2 Full read-only comparison

- Full pyright：仍为精确 `110 errors, 0 warnings, 0 informations`，与 Controller validation / 双路 review entry 相同。
- 110 项仍全部位于 S1 禁止迁移的 S2/S3 producer、callback、composition 与 test-double：缺 required batch、旧 Source lifecycle、尚未迁移 override/callback 或旧 token shape；两个本 gate owner与四个 S1 tests 无命中，未新增或扩散。
- Full Ruff：`Found 160 errors`，与当前累计基线 160 相同；scoped changed owner/tests 无命中，未新增。

## 7. Source scans、AST 与 scope checks

### 7.1 Accepted plan scans

| Scan | 结果 | 归因 |
| --- | ---: | --- |
| ambient authority | `0` | 无 ContextVar/task/thread/auto-batch 第二 authority |
| S2 ack | `59` | 全部是 accepted S2 deferred staging acknowledgement；本 gate 未改 |
| lifecycle | `170` | 相比既有 168 的两条增量只来自 required=False no-op owner test 的一次 begin/commit |
| mutation propagation | `165` | 与既有值相同；changed owner/tests 均显式 batch 或 resolved state |
| locator | `118` | 与既有值相同；public token/journal 不含 locator，tests 不从 BatchToken 反推布局 |

### 7.2 Fix-specific scans

- Production reprocess return consumption：7 个 call 全为 statement expression；consumer 0。
- Public core read self-call：0。
- Maintenance public call graph：只含 normalize/acquire/private-delegate/release 五类调用。
- Processed fallback wording scan：0；行为测试同时证明 legacy `meta.json` 不被读取。
- 中文 docstring AST：本 gate 新增/修改 production/test 函数的中文概览、`Args`、`Returns`、`Raises` 缺口均为 `[]`。
- 没有 `hasattr/getattr`、optional/default batch、compatibility shim、ambient held marker、public read 参数扩展或 R07 snapshot/revision。

### 7.3 Diff / allowlist

- tracked `git diff --check`：pass。
- staged diff：空。
- cumulative working tree 仍是 accepted S1 的 15 production + 4 tests，以及既有 Controller/reviewer/implementation artifacts；本 gate authored scope 精确为 §4 四个 path。
- 本 artifact 另以 no-index whitespace check 复核；无越界 product/test/docs 修改。

## 8. README 决定

不修改 README。

- 已读取 `dayu/fins/README.md` 的 `Agent更新约束`。本 gate 不改变 public protocol：F03 只是让 shared core 回到既有 protocol-owned `None` contract；F01 是 private read graph 收敛；F02 是 owner docstring 纠错。没有新的稳定 Fins capability、用户工作流或架构事实需要写入 README。
- 当前 R06 仍停在 S1 cumulative checkpoint，S2 acknowledgement cutover 与 S3 producer/composition 尚未完成；不能把未来完整 transaction truth提前写成 current package contract。
- `tests/README.md` 只需在新增测试层级/运行方式时同步；本 gate 只在既有 Fins storage owner suite 中补分支，不触发更新。
- 根 README 与 `dayu/README.md` 的用户入口、安装、CLI、分层/装配触发条件均未命中。
- 用户也明确禁止本 gate 修改任何 README。

## 9. Residual risk 与未覆盖项

没有本 gate 新增的未分类 residual。

| Residual | 分类 / owner | 当前处理 |
| --- | --- | --- |
| S2 complete-source validator、blob-first 与 ack 删除 | covered by later approved slice R06-S2 | 本 gate 保留 59 个 ack scan 命中，不实现 fallback |
| S3 producer/callback/composition propagation | covered by later approved slice R06-S3 | full pyright 110 精确保留，不在 S1 越界修复 |
| 多次 repository call / 长生命周期 processor 的 snapshot/revision | assigned to later work unit R07 | 本 gate 只维护一次 published read/open 边界 |

Owner tests 对 storage private helper/state 的窄访问只用于验证 private owner contract与 failure/delegation graph，不从 BatchToken 推导物理布局；这是既有 S1 测试策略的维护成本，不是新增产品正确性 residual。

未实施：S2 ack/complete validator、S3 producer propagation、R07 snapshot、Issue 175/177、统一 authorization framework、schema migration、commit/push/PR。

## 10. Handoff

- `R06-S1-CR-F01`：已修复。
- `R06-S1-CR-F02`：已修复。
- `R06-S1-CR-F03`：已修复。
- Blocking question：0。
- 当前下一 gate：Controller 独立 validation；之后才可由 AgentMiMo / AgentDS 对完整累计 S1 tree 做并发 re-review。

**READY_FOR_CONTROLLER_VALIDATION**
