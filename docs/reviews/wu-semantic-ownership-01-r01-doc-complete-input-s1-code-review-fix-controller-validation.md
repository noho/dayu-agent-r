# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Review Fix Controller Validation

## 1. Gate 与结论

- 当前仍是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R01-S1 code-review fix，不是新 WU，也未进入 R01-S2。
- 输入为 accepted plan commit `54e35231`、两路初始 code review、controller adjudication、AgentCodex fix artifact 与当前完整 S1 diff。
- Controller 对五项 accepted finding、fix allowlist、测试设计、coverage、类型、lint、删除语义与保留 owner 独立复核。
- 结论：`DS-F01` 至 `DS-F05` 均已在 `SourceSnapshot` owner 或其 owner tests 内闭合；controller 首次验证发现的测试过渡设计已在同一 fix gate 收敛。状态为 **fix validation pass / ready for complete dual re-review**，不授权 accepted commit 或 R01-S2。

## 2. Source owner 复核

### 2.1 F01 reader/close 生命周期

`SourceSnapshot._read_at()` 与 `close()` 现在使用同一把 `self._lock`。锁覆盖：

1. reader 对 active spool 的检查、`seek` 与 `read`；
2. close 对 `_spool/_snapshot_size` 的 detach；
3. 同一 active spool 的实际 `close()`。

所以已进入 reader 临界区的读取先完成；close 不会在其间关闭底层对象；close 返回后的 reader 只会观察到 `ValueError("source snapshot is not active")`。修复位于资源生命周期 owner，不存在 consumer catch、下游 normalization 或 fallback。

`_ConcurrentSpoolProbe` 通过事件和第二次 lock acquire 观察点确定性证明上述顺序，不使用 sleep、概率循环或偶发 race：close 的第二次 lock acquire 已开始但仍未完成，放行后 inflight read 返回完整 payload，实际 close 发生在 owner lock 内，随后 reader 得到 inactive error。

### 2.2 F02 materialize 取消

`materialize()` 在输出创建前、每轮复制前和 materialized path 发布前调用既有 `_check_cancellation()`；它没有新增参数、策略、异常或第二取消 owner。取消异常原样透出，异常路径删除已创建的 partial path，context 退出继续关闭 spool。

测试使用真实 `NamedTemporaryFile` 和 pytest `tmp_path`，在第三次物化检查时确认真实 partial path 已存在，取消后确认路径删除与 spool 关闭。局部 cancellation callback 只捕获该单一 test 的路径和计数状态；把它抽成可配置 class/factory 会重新引入 controller 已拒绝的通用测试框架，因此当前局部 seam 有直接必要性。

### 2.3 F03-F05 owner 边界

- 空 source：active 后 exact size 为零，reader EOF / `SEEK_END` 正确，空物化文件由 snapshot 生命周期清理。
- `Source.open()` 自身失败：同一 `OSError` 实例原样透出，已创建 spool 关闭。
- materialized output 写失败：单用途 double 先写 partial 再抛同一 `OSError`，异常不被清理覆盖，partial path 删除。

## 3. 测试过渡设计 follow-up

首次 fix 虽然行为正确，但为五个测试净增 577 行，并建立通用 lock/spool、armable cancellation 和成功/失败 output factory 层，与本 umbrella 的过渡设计 remediation 动机冲突；controller 因此未放行 re-review。

同一 fix gate 已删除 `_ObservedLock`、`_BlockingReadSpool`、`_ArmableCancellationCheck`、`_MaterializedOutput` 与 `_MaterializedOutputFactory`。当前只保留：

- F01 单用途 `_ConcurrentSpoolProbe`；
- F05 无成功模式、无策略字段的 `_FailingMaterializedOutput`；
- 复用已有失败/内存 source 与收窄到单一字段的 `_SpoolRecorder`；
- F02 真实临时文件路径。

`test_processors.py` 相对 fix-entry workspace 当前净增 359 行，比首次 fix 减少 218 行（37.8%）。剩余辅助逻辑分别对应不可由真实 I/O 构造的并发顺序与写入失败注入，且没有 builder、协议、配置、可扩展策略或多层复用框架。Controller 接受该最小 seam；不要求用 sleep、loose mock、`Any/object` 或下游断言换取更少行数。

## 4. Controller 独立验证

```text
pytest tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
80 passed in 2.58s

COVERAGE_FILE=workspace/tmp/.coverage-r01-s1-fix-controller \
  coverage run -m pytest tests/documents/test_processors.py -q
15 passed in 0.74s

COVERAGE_FILE=workspace/tmp/.coverage-r01-s1-fix-controller \
  coverage report --include='dayu/documents/processors/source_snapshot.py' \
  --show-missing --fail-under=80
source_snapshot.py: 154 statements, 10 missed, 94%

python -m pyright
0 errors, 0 warnings, 0 informations

ruff check dayu/documents/processors/source_snapshot.py \
  dayu/tools/doc_tools.py \
  tests/documents/test_import_boundary.py \
  tests/documents/test_processors.py \
  tests/tools/test_doc_tools_provider.py
All checks passed

git diff --check
pass
```

Source / propagation scans：

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit`：`dayu tests README.md` 零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded`：`dayu tests` 零命中。
- 被拒绝的通用 test doubles 与 F06/F07 identifiers：零命中。
- `_DOC_DIRECTORY_MAX_ENTRIES|max_directory_entries` 仍只存在于 accepted S1 的 list/search 中间态及其 tests。
- `ToolTruncateSpec`、`result_limit`、path projection、search containment、cooperative cancellation 与 process-backed execution owner 均仍有预期命中。

## 5. Boundary / README / residual risk

- Fix 累计只修改 `source_snapshot.py`、`test_processors.py` 与 fix artifact；没有触碰 `doc_tools.py`、README、design、control、accepted plan、S2 或 deferred Issue 的产品语义。
- 当前完整 S1 product/test diff 仍在 accepted plan §8.3 allowlist；review/controller artifacts 按 gate 命名另行允许。
- README 终态由 accepted R01-S2 统一迁移；当前 fix 不改变 README 职责内的终态 contract。
- F06 的真实 rollover/consumer 验证仍由 accepted R01-S2 >33 MiB smoke 完成；F07 不属于本 remediation；F08 的 exact LLM-facing assertion 保留。
- Issue 177、统一 tool authorization framework 与其它 remediation sub-WU 均未实施。

## 6. 下一入口

AgentMiMo 与 AgentDS 必须从 accepted plan、初始 review/adjudication、fix artifact、本 controller validation 和当前完整 S1 diff出发，分别做一次完整 re-review；不能只检查五个局部 patch。两路 re-review 都必须复核 accepted findings closure、测试 seam 最小性、S1/S2 边界、安全/取消/output owner、coverage/pyright/scans，并停在 controller 裁决前。
