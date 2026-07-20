# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Review Fix 与 Controller Validation Follow-up — AgentCodex

## 1. Gate 身份、输入与结论

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **internal remediation sub-WU / slice**：`R01 Doc complete input / R01-S1`；不是新 WU，未进入 R01-S2。
- **accepted plan**：`docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`，accepted commit `54e35231`。
- **slice base**：`1b4e5d33`。
- **review 输入**：完整读取 MiMo / DS 两路 S1 code review、`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-controller-adjudication.md`、当前 tracked diff、新增 `source_snapshot.py`、S1 implementation artifact、controller validation，以及同一 fix gate 的 controller validation follow-up。
- **gate**：S1 code-review fix；只处理 controller 接受的 `DS-F01` 至 `DS-F05`。
- **结论**：五项 accepted finding 均已在 `SourceSnapshot` owner 或其 owner-level tests 内闭合；controller follow-up 指出的测试过渡设计也已收敛；`DS-F06` 至 `DS-F08` 未实现。状态为 `controller-follow-up-fix-pass / awaiting-controller-validation`，不授权 re-review、accepted commit 或 R01-S2。
- **artifact path**：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-fix-codex.md`。

## 2. 第一性原理与 owner 判断

修复动机成立。完整快照建立后，active spool 的读、detach、底层关闭、物化复制、取消观察与临时资源清理都由 `dayu.documents.processors.source_snapshot.SourceSnapshot` 唯一拥有；consumer 捕获底层异常、Host 补取消或测试 shim 都不能修复 owner 状态机。

F01 的直接根因是 `_read_at()` 已用 `self._lock` 覆盖 `seek/read`，而 `close()` 可绕过同一锁 detach 并关闭 spool。F02 的直接根因是 `materialize()` 再次完整复制时没有复用现有 `cancellation_check`。F03-F05 是 accepted owner contract 的确定性边界验证缺口。无需修改 `doc_tools.py`、schema、README、S2 目录语义或 Issue 177；扩大边界反而会产生第二语义 owner。

## 3. Exact fix diff

以进入最初 fix gate 时的 workspace 为基线，当前累计精确文件增量为：`source_snapshot.py` 净增 10 行；`test_processors.py` 增加 379 行、删除 20 行，净增 359 行；本 artifact 在原路径更新。相较 controller follow-up 前 `test_processors.py` 的净增 577 行，已删除 218 行净增（约 37.8%），文件从 1148 行降至 930 行。累计 fix 仍只有这两份 Python 文件与本 artifact，没有第四个文件被写入；本次 follow-up 没有修改 production。

### 3.1 `dayu/documents/processors/source_snapshot.py`

- `SourceSnapshot.close()` 继续使用现有 `self._lock`，并把 active spool 的读取、`_spool/_snapshot_size` detach 与 `spool.close()` 实际调用全部放进同一临界区。已进入 `_read_at()` 临界区的读先完成；`close()` 返回后的新读取只观察到 `ValueError("source snapshot is not active")`。
- `SourceSnapshot.materialize()` 在创建输出前、每个复制迭代前及发布 `_materialized_path` 前调用同一个 `_check_cancellation()`。取消或任意写入异常继续原样抛出，已创建的 partial path 在异常分支删除。
- partial path 的删除失败被抑制，避免覆盖原始 cancellation / output `OSError`；正常可删除路径仍由测试证明无残留。
- materialize docstring 增加 cancellation 原样透出说明；未增加公开参数、状态、异常类型、fallback 或兼容分支。

### 3.2 `tests/documents/test_processors.py`

- `test_source_snapshot_close_serializes_inflight_read_and_actual_close`：只保留单个 `_ConcurrentSpoolProbe`。它同时提供该测试所需的 owner lock / spool 观察点，确定性证明第二次 lock acquire 已开始但 close 尚未完成、inflight read 先完整返回、actual close 发生在 owner lock 内、close 后 reader 稳定得到 inactive `ValueError`；不使用 sleep、概率循环或通用并发测试框架。
- `test_source_snapshot_materialize_observes_cancellation_and_cleans_resources`：使用测试内单用途 cancellation callback，进入快照后才启用；把标准库 `tempfile.tempdir` 定向到 `tmp_path`，由真实 `NamedTemporaryFile` 创建 partial path，并在取消当场观察路径存在、异常后观察路径删除及 context 退出后 spool 关闭。它不再复用或经过 output.write 失败 double。
- `test_source_snapshot_empty_source_has_exact_eof_and_materialization`：断言 `snapshot_size/content_length == 0`、EOF、`SEEK_END == 0`、空物化文件和 context 退出清理。
- `test_source_snapshot_open_oserror_is_preserved_and_closes_spool`：断言 `Source.open()` 自身抛出的同一 `OSError` 实例原样透出，已创建 spool 关闭。
- `test_source_snapshot_materialize_write_oserror_removes_partial_path`：只使用单一用途 `_FailingMaterializedOutput` callable/context-manager；它没有成功模式、策略字段或通用 factory 层，只执行“打开固定路径、写入部分字节、flush、原样抛错”，并断言异常实例身份和 partial path 删除。
- `_SpoolRecorder` 只保留测试实际消费的单一 `spool` 字段与 factory 调用；旧 `_ObservedLock`、`_BlockingReadSpool`、`_MaterializedOutput`、`_MaterializedOutputFactory`、`_ArmableCancellationCheck` 已全部删除。所有保留函数/方法仍有严格类型和包含参数、返回值、异常的中文 docstring。

### 3.3 最小设计理由

- F01 必须观察锁获取开始、临界区读取和实际 close 的相对顺序，因此保留一个同步 probe 是确定性测试的最小必要 seam；去掉该 seam 只能退回 sleep/概率 race。
- F02 不需要替换输出：真实 NamedTemporaryFile 与临时目录本身就是 partial lifecycle 的真源，测试只在 cancellation callback 捕获该路径。
- F05 必须使 `output.write` 抛出指定实例，因而保留一个没有成功分支的最小 context-manager；不再为 F02/F05 建立共享输出抽象。
- F03/F04 只使用现有内存 Source/spool recorder。没有为五个 finding 建立配置、通用协议、builder、继承层或可扩展测试框架。

### 3.4 未修改边界

- 未修改 `dayu/tools/doc_tools.py`、其它 production/test、README、design、control、accepted plan、两路 review、controller adjudication 或 deferred Issue。
- 未新增 F06 disk-spill 实现细节测试、F07 seek 防御测试，也未放宽 F08 LLM-facing exact assertion。
- 当前工作区中上述其它文件的既有 S1 diff 保持原样；本 fix gate 新增/修改只有本节列出的两份 Python 文件与本 artifact。

## 4. 验证

### 4.1 Focused tests

```text
pytest tests/documents/test_processors.py -q
15 passed

pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
80 passed
```

### 4.2 单文件 coverage

controller adjudication 给出的 `pytest --cov=dayu/documents/processors/source_snapshot.py` 在当前 pytest-cov 中把文件路径当作模块名，报告 `module-not-imported / no-data-collected`，因此该次命令无有效 coverage 证据。按 accepted plan 的文件级采样方式纠正为：

```text
coverage run --data-file=workspace/tmp/.coverage-r01-s1-fix-followup \
  -m pytest tests/documents/test_processors.py -q
15 passed

coverage report --data-file=workspace/tmp/.coverage-r01-s1-fix-followup \
  --include='dayu/documents/processors/source_snapshot.py' \
  --show-missing --fail-under=80
source_snapshot.py: 154 statements / 10 miss / 94%
```

单文件 `94% >= 80%`，gate 通过。

### 4.3 Type / lint / diff hygiene

```text
python -m pyright
0 errors, 0 warnings, 0 informations

ruff check \
  dayu/documents/processors/source_snapshot.py \
  dayu/tools/doc_tools.py \
  tests/documents/test_import_boundary.py \
  tests/documents/test_processors.py \
  tests/tools/test_doc_tools_provider.py
All checks passed

git diff --check
pass

git diff --no-index --check /dev/null dayu/documents/processors/source_snapshot.py
无 whitespace error；exit 1 只表示新增文件与 `/dev/null` 内容不同
```

### 4.4 Source / boundary scans

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit` 在 `dayu tests README.md`：零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests`：零命中。
- `_ObservedLock|_BlockingReadSpool|_MaterializedOutputFactory|_MaterializedOutput|_ArmableCancellationCheck` 在 `test_processors.py`：零命中，证明 follow-up 指出的通用/分层 doubles 已删除。
- `disk_spill|invalid_whence|negative_seek|negative_position` 在 `tests/documents/test_processors.py`：零命中，证明未实现 F06/F07。
- `_DOC_DIRECTORY_MAX_ENTRIES|max_directory_entries` 只命中既有 S1 list/search producer 和对应 provider tests；S2 中间态未改。
- `ToolTruncateSpec`、`result_limit`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled` 与 `ProcessBackedToolExecutionCapability` 均仍在既有 owner/test 位置命中。

## 5. README / docs decision

本 fix 不改变用户入口、配置、分层、工具 schema、测试总 contract 或 R01-S2 终态，且用户明确禁止修改 README、design、control 与 accepted plan。因此 README 无 diff；只新增本 gate 必需 fix artifact。

## 6. Finding status 与 residual risks

| Finding | 状态 | 证据 |
|---|---|---|
| DS-F01 | 已修复 | 同一锁覆盖 read/detach/actual close；确定性线程握手测试通过 |
| DS-F02 | 已修复 | materialize 全复制阶段复用 cancellation check；异常身份、partial、spool cleanup 测试通过 |
| DS-F03 | 已修复 | 空 source exact size/EOF/SEEK_END/空物化/清理测试通过 |
| DS-F04 | 已修复 | `Source.open()` 原始 `OSError` 身份与 spool close 测试通过 |
| DS-F05 | 已修复 | output partial write、原始 `OSError` 身份与路径删除测试通过 |
| DS-F06 | controller 拒绝；未实现 | R01-S2 真实 >33 MiB smoke 的既有 owner/destination 不变 |
| DS-F07 | controller 拒绝；未实现 | 与本 remediation 无直接 failure evidence |
| DS-F08 | controller 拒绝；未实现 | LLM-facing exact assertion 保持原样 |

Residual risk 均已分类：S1 保留的 10,000 directory entry cap 与 README 终态迁移属于 later approved R01-S2；真实 >33 MiB rollover smoke 属于 R01-S2 / completion；完整 `TruncationManager` / `fetch_more` 接入仍由 Issue 177 拥有。没有未分类 residual risk、blocking open question 或 allowlist 扩张。

## 7. Stop / next entry

本 fix gate 在 `controller-follow-up-fix-pass` 停止。下一入口只能是 controller validation；只有 controller 接受收敛结果后才能进入 AgentMiMo / AgentDS 双路 re-review。本 artifact 不触发 re-review、不 commit、不进入 R01-S2、不创建 PR，也不修改 controller 状态。
