# WU-SEMANTIC-OWNERSHIP-01 R06-S1 双路累计 Code Re-Review — 第二路 (DS)

## 1. 审查身份与范围

- **审查者**: AgentDS（第二路 re-reviewer）
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 cumulative code re-review（第二路）
- **这不是新 WU**；不进入 S2/S3，不修改代码
- **审查基线**: `d048adf7ec1135aaf575384432ebf1137f8a34f2` → 当前完整未暂存 working tree
- **只允许写入本 artifact**: `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-ds.md`

### 1.1 裁决优先级（已完整读取并应用）

1. `AGENTS.md`
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
3. `docs/fins/design.md`
4. `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
5. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-mimo.md`
6. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-ds.md`
7. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-controller-adjudication.md`
8. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-codex.md`
9. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-controller-validation.md`
10. `docs/host/issues-implementation-control.md` 当前 R06 rows

### 1.2 审查方法

- 完整读取 15 个 S1 production 文件与 4 个 S1 test 文件的当前 working tree 状态
- 逐项对 CR-F01..03 做直接代码证据逐行证伪/确认
- 复验原 S1 全量 owner contract（BatchToken、registry authority、lock order、read graph、journal、recovery、VF-01..04、containment、无越界）
- 独立运行 focused tests、全量 S1 tests、scoped pyright、full pyright
- 执行 ambient authority、public read self-call、fallback wording、return consumer 扫描

## 2. Verdict

**PASS**

current finding = 0，blocking question = 0。

S1 累计树的全部 owner contract（opaque BatchToken、explicit mutation authority、writer/publication lock 分离、published/private read graph、delayed opener、minimal journal、recovery fail-closed、pre/post-commit error precedence VF-01..04、containment、无 S2/S3/R07 越界）经直接代码证据验证成立。三项 Controller accepted finding（R06-S1-CR-F01..03）均在正确 owner boundary 闭合。

**READY_FOR_S1_CONTROLLER_ACCEPTANCE**

## 3. CR-F01..03 逐项闭合确认

### 3.1 R06-S1-CR-F01 — maintenance public read → private unguarded helper

**状态: CLOSED**

直接代码证据（`dayu/fins/storage/_fs_maintenance_core.py`）:

| 检查项 | 结论 | 直接证据（行号） |
| --- | --- | --- |
| public entry 只做 normalize + guard + delegate + release | PASS | line 401-411: `_normalize_ticker` → `_normalize_document_id` → `_acquire_publication_guard` → `_read_rejected_filing_file_bytes_unguarded(...)` → `finally: _release_lock_token` |
| private helper 唯一拥有 path containment | PASS | line 436: `_rejected_filing_file_path_for_read(normalized_ticker, normalized_document_id, filename)` — helper 自己调用 path resolution |
| private helper 唯一拥有 missing 分支 | PASS | line 441-442: `if not path.exists(): raise FileNotFoundError(...)` |
| private helper 唯一拥有 directory 分支 | PASS | line 443-444: `if path.is_dir(): raise IsADirectoryError(...)` |
| private helper 唯一拥有 bytes I/O | PASS | line 445: `return path.read_bytes()` |
| 无 ambient "guard held" marker | PASS | helper 签名只有三个显式 `str` 参数，无 ContextVar、task-local、默认参数表达 guard 已持有 |
| 无重入锁 | PASS | helper 不调用 `_acquire_publication_guard` 或任何 lock acquire |
| 无 public compatibility 参数 | PASS | helper 参数只有 normalized_ticker、normalized_document_id、filename，无 BatchToken、layout 推断或 optional/default |

测试证据（`tests/fins/test_fins_storage_atomicity.py`）:

| 检查项 | 结论 | 直接证据（行号） |
| --- | --- | --- |
| success 路径 | PASS | line 477-481: 通过 public entry 读取 `b"rejected payload"` |
| missing 路径 | PASS | line 482-486: `FileNotFoundError` with `match="rejected filing 文件不存在"` |
| directory 路径 | PASS | line 488-498: `IsADirectoryError` with `match="目标是目录"` |
| delegation 验证（monkeypatch） | PASS | line 530-585: public entry 将规范化后的 `AAPL`/`fil_rejected`/`rejected.htm` 精确委托给 private helper；不依赖 fixture gaming |
| 无 public read self-call | PASS | AST scan: 全部 `_fs_*_core.py` 的 `self.<public_method>(...)` 调用为 `[]` |

### 3.2 R06-S1-CR-F02 — processed meta 唯一读取 contract

**状态: CLOSED**

直接代码证据:

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| docstring 只承诺 `tool_snapshot_meta.json` | PASS | `_fs_processed_core.py` line 184: `只读取 published ``tool_snapshot_meta.json``。` |
| docstring FileNotFoundError 只说明该唯一文件 | PASS | line 194: `published ``tool_snapshot_meta.json`` 不存在时抛出。` |
| 实现只读取一个路径 | PASS | line 227-230: `_processed_meta_path_for_read(...)` → `_read_json_object` 或 `raise FileNotFoundError`；无分支、无回退逻辑 |
| `_PROCESSED_META_FILENAME` 只有一个值 | PASS | `_fs_storage_utils.py` line 22: `_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"` |
| 无 "meta.json" 引用 | PASS | 全仓 `_fs_processed_core.py` 与 `test_fins_storage_atomicity.py` 中不包含 `meta.json` 作为业务文件名 |
| 无 fallback 描述残留 | PASS | `优先读取\|回退\|fallback\|两种元数据` scan: 0 命中 |

测试证据:

| 检查项 | 结论 | 直接证据（`test_fins_storage_atomicity.py`） |
| --- | --- | --- |
| legacy `meta.json` 存在时不被读取 | PASS | line 388-396: 在 tool snapshot 旁放置内容冲突的 `meta.json`，读取仍返回 `tool_snapshot_meta.json` 内容（`"document_id": "processed-two"` 而非 `"legacy-meta-must-not-be-read"`） |
| 仅 legacy 存在时 fail closed | PASS | line 397-399: 删除 tool snapshot 但保留 legacy → `FileNotFoundError` with `match="tool_snapshot_meta.json"` |
| 测试不误导为兼容承诺 | PASS | legacy `meta.json` fixture 的存在目的是证明它 **不** 被读取，不是隐式兼容分支 |

### 3.3 R06-S1-CR-F03 — reprocess marker 统一 `None` contract

**状态: CLOSED**

直接代码证据:

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| protocol 声明 `-> None` | PASS | `repository_protocols.py` line 720: `) -> None:` |
| wrapper 声明 `-> None` | PASS | `fs_processed_document_repository.py` line 188: `) -> None:` |
| core public 声明 `-> None` | PASS | `_fs_processed_core.py` line 241: `) -> None:` |
| core private impl 声明 `-> None` | PASS | `_fs_processed_core.py` line 268: `) -> None:` |
| `required=False` no-op | PASS | line 259-260: `if not required: return` — 早期返回，不产生 `False` |
| missing target no-op | PASS | line 288-289: `if not processed_meta_path.exists(): return` — 不产生 `False` |
| existing target 副作用正确 | PASS | line 290-293: `read_json → reprocess_required=True → updated_at → write_json` |
| 无生产返回值消费者 | PASS | 全仓 7 个 production call 全部为 statement expression（AST parent = `Expr`），`production_return_consumers=[]` |

测试证据:

| 检查项 | 结论 | 直接证据（`test_fins_storage_atomicity.py`） |
| --- | --- | --- |
| `required=False` 返回 `None` | PASS | line 321-328: `is None` 断言；commit 前后 meta 不变 |
| `required=True` 存在目标返回 `None` | PASS | line 347-354: `is None` 断言；commit 后 meta 有标记 |
| `required=True` 缺失目标返回 `None` | PASS | line 356-363: `is None` 断言；commit 后仍 `FileNotFoundError` |
| private impl 返回 `None` | PASS | line 366-371: `is None` 断言；commit 后 side effect 成立 |

## 4. 原 S1 全量 Owner Contract 复验

### 4.1 BatchToken 真 opaque

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `BatchToken` 只含 `transaction_id` + `ticker` | PASS | `document_models.py:415-424`，`frozen=True` |
| 无衍生属性/方法 | PASS | 无 property、无 `__post_init__`、无 computed field |
| 无 locator/Path/PID/hostname/时间戳 | PASS | 旧字段已全部删除 |
| 测试不断言格式 | PASS | 只断言 opaque、非空、不同 begin 不相同 |

### 4.2 Registry/Core/Ticker/Open Lifecycle — 唯一 Mutation Authority

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `_active_batches` + `_active_transaction_by_ticker` 唯一 registry | PASS | `_fs_storage_infra.py` |
| `_resolve_active_batch` 是唯一 mutation resolve 入口 | PASS | line 531-571: 检查 registry membership、canonical token match、ticker match、open lifecycle |
| 不检查 `ContextVar`/task/thread identity | PASS | `_resolve_active_batch` 体不含任何 ambient identity 检查 |
| 无 `_execute_with_auto_batch` | PASS | 已删除；ambient authority scan: 0 命中 |
| 无 `_BATCH_OWNER_CONTEXT` | PASS | 已删除 |

### 4.3 Writer Mutex 与独立 Publication Guard

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| writer lock: `batch_locks/<ticker>.lock` | PASS | `_acquire_ticker_lock`，non-blocking |
| publication lock: `batch_locks/<ticker>.publication.lock` | PASS | `_acquire_publication_guard`，`blocking=True` |
| 两个不同锁文件 | PASS | 不同 path derivation |
| 锁序始终 writer → publication | PASS | begin 获取 writer；commit 在 swap 短窗获取 publication |
| publication → writer 反向路径不存在 | PASS | 审计全部 acquire 路径 |
| commit 短窗: publication guard 只覆盖 physical swap | PASS | `commit_batch` line 318-337: guard 内只有 `target→backup`、`staging→target`、journal write、pre-commit restore |
| post-commit release failure 不回滚 COMMITTED | PASS | line 344-351: `post_commit_error` 保留，不调 `_rollback_precommit_batch` |

### 4.4 Public Outer Guard / Private Unguarded Read Graph

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 全部 public read 获取 guard → unguarded helper | PASS | 5 个 core 文件全部 public read 符合 outer guarded + private unguarded 模式 |
| public-to-public read 嵌套: 0 | PASS | AST scan: `self.get_*` / `self.load_*` / `self.list_*` / `self.read_rejected*` 调用在 `_fs_*_core.py` 中为 `[]` |
| `_ticker_dir_for_read` 只路由到 published tree | PASS | 不通过 state 参数路由到 staging |
| `list_rejected_filing_artifacts` 内部调用 `_get_rejected_filing_artifact_unguarded` | PASS | line 358-362: 在 guard 内调用 private unguarded helper，不调用 public entry |

### 4.5 LocalFileSource Delayed Opener

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| opener 绑定 path/ticker，不绑定 batch | PASS | `_PublicationGuardedBinaryOpener.__init__` 只接收 `lock_path` |
| `__call__`: acquire → `open("rb")` → finally release | PASS | `_fs_storage_infra.py` line 111-115 |
| fd 成功/失败均释放 guard | PASS | `finally` 块保证 |
| 后续流读取不持 guard | PASS | 返回的 `BinaryIO` 不持有 guard token |

### 4.6 Minimal Journal

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| journal 字段: `transaction_id`、`ticker`、`phase` | PASS | `_JOURNAL_FIELDS = frozenset({"transaction_id", "ticker", "phase"})` |
| 无 PID/hostname/绝对路径/owner token | PASS | 已删除 |

### 4.7 Malformed Evidence Fail-Closed (VF-01)

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| invalid journal ticker → skip + continue | PASS | `_recover_single_batch_dir` 中 `ValueError` 单独捕获 |
| invalid backup ticker → preserve + continue | PASS | `_recover_orphan_backup_dirs` 中 `ValueError` 单独捕获 |
| 不吞无关 I/O error | PASS | 只捕获 `ValueError` |

### 4.8 Pre/Post-Commit Error Precedence (VF-03, VF-04)

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| VF-03: primary preserved, writer release 附着 `.add_note()` | PASS | `_close_active_batch` line 600-611 |
| VF-04: COMMITTED 后 publication release failure 成为 post-commit primary | PASS | `commit_batch` line 344-351 |
| COMMITTED durable truth 不回滚 | PASS | post-commit 路径不调 `_rollback_precommit_batch` |

### 4.9 Containment/Symlink

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| ticker/document/entry normalize + root containment | PASS | `_normalize_ticker`、`_normalize_document_id`、`_is_contained_recovery_path` |
| symlink 拒绝 | PASS | `_is_contained_recovery_path` 逐级检查 symlink |

### 4.10 无 S2/S3/R07/Issue 175/177/Authorization 越界

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 无 S2 complete-source validator | PASS | 未实现 |
| 无 S2 ack 删除 | PASS | `stage_source_document` 保留为 S1 intentional residual |
| 无 S3 producer propagation | PASS | full pyright 110 项属于 S3 scope |
| 无 R07 snapshot/revision | PASS | 未实现 |
| 无 Issue 175/177 | PASS | 未触及 |
| 无统一 authorization framework | PASS | 未实现，符合 plan §1.3 非目标 |

## 5. Controller Pyright 噪音裁决验证

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| scoped pyright (15 production + 4 tests) = 0 | PASS | `0 errors, 0 warnings, 0 informations` |
| full pyright = 110 | PASS | 全部 110 项在 S2/S3 producer/callback/test-double；changed owner 零命中 |
| 无新增或扩散 | PASS | 110 与 Controller validation / fix codex 记录精确一致 |
| 不使用无 VIRTUAL_ENV 的无效环境噪音 | PASS | 所有命令均在 `source .venv/bin/activate` 后运行 |

## 6. 测试访问 Private Helper/Core 检查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 测试访问 `_mark_processed_reprocess_required_impl` | ACCEPTABLE | line 366-371: 仅用于验证 private contract 行为，不固化 public token layout |
| 测试使用 `_only_active_batch_state` | ACCEPTABLE | failure-injection 测试需要；路径从 `_ActiveBatchState`（storage owner）取得，不从 `BatchToken` 反推 |
| legacy `meta.json` fixture 不误导成兼容承诺 | PASS | fixture 存在目的是证明不被读取（§3.2 测试证据），不是隐式兼容分支 |

## 7. 全量测试、Typing 与 Lint 证据

| 证据类型 | 结果 |
| --- | --- |
| 四个 S1 test 文件完整运行 | `207 passed, 3 warnings in 9.18s` |
| 3 条 warning 来源 | 第三方 `edgar` deprecated imports，非本 gate 新增 |
| Scoped pyright (15 prod + 4 test) | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `110 errors` (全部 S2/S3, changed owner 0) |
| Ambient authority scan | `0` 命中 |
| Public core read self-call | `0` 命中 |
| Processed fallback wording scan | `0` 命中 |
| Production reprocess return consumer | `0` |
| CR-F01 public read delegation (monkeypatch) | 精确委托规范化 identity |

## 8. 与第一路 Re-Review (MiMo) 的交叉验证

本轮独立审查确认 MiMo re-review 的 PASS 结论成立。两路在以下关键点上一致：

- CR-F01..03 均在正确 owner boundary 闭合
- BatchToken opaque、registry-only authority、无 ambient 残留
- Writer/publication lock 分离、锁序正确
- Published/private read graph 覆盖全部 public reads
- Recovery fail-closed、journal minimal
- Pre/post-commit error precedence VF-01..04 closed
- 无 S2/S3/R07 越界
- Scoped pyright 0、full pyright 110（不变）
- 207 tests passed

## 9. Open Questions

无。

## 10. Residual Risk

1. **S2 blob-first migration 依赖**: `store_file` 仍要求 pre-existing source meta。这是 accepted plan 的 S2 deferred 行为；S1 当前 behavior 是安全的（fail closed），S2 必须正确移除该前置依赖。

2. **S3 full pyright 110 errors**: 全部 110 项是 S2/S3 producer/callback/composition propagation 的类型可见残留。S3 cumulative tree 必须清零。

3. **R07 snapshot/revision**: `LocalFileSource` 只做了 delayed opener guard；跨多次 read 的同版本 snapshot 仍由 R07 独占。

4. **测试对 `_ActiveBatchState` 私有字段的依赖**: crash-injection 测试需要内部物理 layout。这是 intentional design（implementation codex §3.1 确认），但若字段变更，测试需同步更新。

## 11. 最终 Ledger

| 类别 | 状态 |
| --- | --- |
| R06-S1-CR-F01 (maintenance unguarded read graph) | **CLOSED** |
| R06-S1-CR-F02 (processed meta 唯一读取 contract) | **CLOSED** |
| R06-S1-CR-F03 (reprocess marker 统一 None contract) | **CLOSED** |
| 原 S1 全量 owner contract (opaque token, registry authority, lock order, read graph, journal, recovery, VF-01..04, containment, 无越界) | **VERIFIED** |
| Controller pyright 噪音裁决 | **VERIFIED** (scoped=0, full=110, 未新增/扩散) |
| 测试对 private helper/core 访问 | **ACCEPTABLE** (failure injection 需要，不固化 public token layout) |
| Legacy meta fixture 兼容误导 | **无** (fixture 目的为证明不被读取) |
| current material finding | **0** |
| blocking question | **0** |

**READY_FOR_S1_CONTROLLER_ACCEPTANCE**
