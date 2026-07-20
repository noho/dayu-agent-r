# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Review Controller 裁决

## 1. 裁决范围与权威顺序

- 当前仍是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 overdesign remediation continuation；本裁决不创建新 WU，也不进入 R01-S2。
- accepted plan 是 commit `54e35231` 中的 `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- 实现证据为当前相对 `1b4e5d33` 的 R01-S1 workspace diff、AgentCodex implementation artifact 与 controller validation。
- review 输入为：
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-ds.md`
- reviewer verdict 不独立授权 accepted commit；controller 逐项以代码、测试与 accepted plan 的 owner contract 裁决。

## 2. 第一性原理与 owner 判断

本轮动机成立：R01-S1 删除错误的输入大小产品语义后，`SourceSnapshot` 成为完整 source 快照、共享 spool、独立 reader、物化、清理与协作取消的唯一 owner。因而并发 reader 与 `close()` 的资源生命周期、完整输入物化期间的取消响应，以及该 owner 明示的空输入/I/O 清理边界，都必须在本 owner 内闭合；不能由 Doc consumer、Host、测试 shim 或下游错误映射补偿。

旧 `BoundedSourceSnapshot.materialize()` 同样没有循环内取消检查，只能证明缺陷来自被保留的过渡实现，不能推翻 accepted plan §3.1、§4.2、§8.2、§10 已明确保留的 cooperative cancellation contract。另一方面，`SpooledTemporaryFile` 的磁盘 rollover 是标准库实现细节，accepted plan 已把真实大文件完整读取的端到端验证固定在 R01-S2 的 >33 MiB smoke；当前 slice 不重复创建第二套较小阈值测试。

## 3. 逐项裁决

| Finding | 裁决 | 直接证据与必须动作 |
|---|---|---|
| MIMO | PASS，无 finding | MiMo 完整检查了 source owner、consumer chain、删除语义、保留的目录中间态、安全/取消/output owner、测试、coverage 与 allowlist，未给出 material finding。其对测试 node 数变化的说明不作为产品语义或 gate 依据；controller 已独立以 `75 passed` 验证当前矩阵。 |
| R01-S1-DS-F01 | **接受，correctness** | `_read_at()` 在 `self._lock` 内对共享 spool 执行 `seek/read`，但 `close()` 不持同一把锁即可把 spool 关闭；因此 close 可在 reader 临界区中关闭底层对象并泄露非确定性底层 I/O 异常。修复必须由 `SourceSnapshot` 生命周期 owner 完成：同一锁必须串行化 active spool 的读取、detach 与实际 close，使已经进入临界区的读完成，close 返回后的读稳定得到 owner 级 inactive error。不得用 consumer catch/fallback 修复。新增确定性并发回归测试，禁止依赖概率竞争。 |
| R01-S1-DS-F02 | **接受，correctness** | `materialize()` 对完整大输入再次逐块复制，却不观察已有 `cancellation_check`；accepted plan 要求保留 snapshot cancellation 且取消快速收口。物化循环必须在发布路径前持续观察同一 cancellation owner，取消异常原样透出，partial materialized file 被删除，snapshot 退出后 spool 也清理。新增物化中取消测试。 |
| R01-S1-DS-F03 | **接受，owner contract test** | 空 source 是“复制到真实 EOF、active 后 exact size、reader/materialize 可用”的零长度边界，不是新产品能力。补充 owner test，验证 `snapshot_size/content_length == 0`、reader EOF、`SEEK_END` 与空物化文件生命周期。 |
| R01-S1-DS-F04 | **接受，owner contract test** | accepted plan §3.1 明确 `Source.open/read` 真实 `OSError` 原样透出，§8.4 要求 source I/O 清理；当前只覆盖 stream `read()` 失败，未覆盖 `Source.open()` 自身失败。补充直接 open failure，断言异常原样透出且已创建 spool 关闭。 |
| R01-S1-DS-F05 | **接受，owner contract test** | accepted plan 明确 I/O 异常删除 materialized path；当前仅走读证明 `output.write()` 失败的 partial file unlink。补充确定性写失败测试，断言原异常透出且 partial path 不残留；不得把 I/O 错误吞成成功。 |
| R01-S1-DS-F06 | **拒绝为当前 finding** | rollover 由标准库 `SpooledTemporaryFile` 提供，当前代码没有按内存/磁盘模式分支。accepted plan §11 已要求 R01-S2 从真实 discovery/callable 路径读取 >33 MiB 文件并验证尾部事实，必然覆盖 rollover 及完整 consumer 链。S1 再增加 >1 MiB 实现细节测试没有发现独立 failure branch，也不能替代已计划的真实 smoke。 |
| R01-S1-DS-F07 | **拒绝** | 非法 `whence` 与负位置分支来自既有 reader 接口，代码行为正确，且与本轮删除输入预算、完整 source 或 owner 迁移没有 failure 证据。为两个标准参数防御分支新增测试不是当前 remediation 必需项。 |
| R01-S1-DS-F08 | **拒绝** | LLM-facing schema 文本本身是 source-of-truth contract。accepted plan §10 明确要求 exact schema description assertions；S2 删除 directory partial 文本时实现与精确断言必须同源迁移。把断言放宽成关键词集合会允许语序、动作和禁止事项发生未审查漂移，违反 AGENTS.md 的 LLM-facing 约束。 |

## 4. Fix gate 精确边界

AgentCodex 只修复 F01-F05，允许修改：

- `dayu/documents/processors/source_snapshot.py`
- `tests/documents/test_processors.py`
- fix artifact `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-fix-codex.md`

不得修改 `doc_tools.py`、S1 其它测试、README、design truth、accepted plan、S2 目录语义或任何 deferred Issue；不得实现 F06-F08。修复后必须至少运行：

```bash
source .venv/bin/activate
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
pytest tests/documents/test_processors.py --cov=dayu/documents/processors/source_snapshot.py --cov-report=term-missing --cov-fail-under=80 -q
python -m pyright
git diff --check
```

还必须用严格类型、完整中文 docstring 和确定性同步测试证明 F01；用 source/临时文件观察证明 F02-F05 清理，而不是只断言异常类型。修复完成后回到 AgentMiMo / AgentDS 完整双路 re-review，不能直接 accepted commit。

## 5. Gate 结论

R01-S1 当前 **不接受提交**。五项 accepted finding（F01-F05）进入同一 S1 code-review fix gate；F06-F08 已按现有 owner、已接受后续 smoke 与 LLM-facing contract 关闭，不产生新 scope。R01-S2、Issue 177、统一 tool authorization framework 及其它 remediation sub-WU 均未进入。
