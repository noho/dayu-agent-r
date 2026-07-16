# WU-SEMANTIC-OWNERSHIP-01 R06-S1 Code Review Fix Controller 验证

## 1. 结论

Controller 对 `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-codex.md` 与当前累计 working tree 做了独立代码、测试、coverage、typing、lint、source scan、AST 与范围复核。

结论：**PASS / READY_FOR_DUAL_COMPLETE_REREVIEW**。

- `R06-S1-CR-F01..03` 均在正确 owner boundary 闭合。
- 本 fix gate authored scope 为两个 production owner、一个既有 S1 owner test 与一个 fix artifact。
- 没有 S2/S3、R07、Issue 175/177、README、统一 authorization framework、stage/commit/push/PR 越界。
- blocking question：0。

## 2. Owner-level 直接复核

### R06-S1-CR-F01

`_FsFilingMaintenanceMixin.read_rejected_filing_file_bytes` 现在只执行 ticker/document identity normalize、publication guard acquire、private helper delegate 与 `finally` release。新增 `_read_rejected_filing_file_bytes_unguarded` 唯一拥有 filename/path containment、missing、directory 与 bytes I/O 分支，具有严格类型和完整中文 `Args/Returns/Raises`。

Controller AST 复核全部 `_fs_*_core.py`：`public_self_calls=[]`。新增 owner test 同时覆盖实际 success/missing/directory 行为，并用窄 monkeypatch 证明 public entry 向 private helper 传递规范化后的 identity；没有 ambient held marker 或重入锁。

### R06-S1-CR-F02

`_FsProcessedMixin.get_processed_meta` 现在只承诺读取 published `tool_snapshot_meta.json`；`FileNotFoundError` 描述与唯一 path owner 一致。实现没有增加 `meta.json` fallback。owner test 在同目录放入冲突 legacy `meta.json`，证明实际读取仍来自 tool snapshot；删除 tool snapshot 后即使 legacy 文件保留也精确 fail closed。

`优先读取|回退|fallback|两种元数据` 在本 owner/test 范围零命中。

### R06-S1-CR-F03

shared core 与 private impl 返回类型均收敛为 `None`；`required=False` 与 missing target 保持 no-op，existing target 的 `reprocess_required=True`/`updated_at` 副作用不变。protocol/wrapper 原已准确声明 public `None` contract，没有机械改动。

Controller 调用扫描确认生产调用均作为 statement expression 使用，没有返回值消费者。owner test 明确覆盖 false/existing/missing 三条 public core path 为 `None`，以及 private impl 的 `None` 与副作用。

## 3. 独立测试与 coverage

均按 `source .venv/bin/activate` 的 Python 3.11 环境运行。

- 四个 S1 tests 完整 coverage run：`207 passed, 3 warnings in 10.93s`。
- warning 均来自第三方 `edgar` deprecated imports，不是本 gate 新增 failure。
- 15 个累计 changed production 文件逐文件 line coverage：
  - `document_models.py 96%`
  - `_fs_blob_core.py 93%`
  - `_fs_company_meta_core.py 97%`
  - `_fs_maintenance_core.py 93%`
  - `_fs_processed_core.py 94%`
  - `_fs_source_document_core.py 82%`
  - `_fs_storage_infra.py 89%`
  - `fs_batching_repository.py 94%`
  - `fs_company_meta_repository.py 100%`
  - `fs_document_blob_repository.py 100%`
  - `fs_filing_maintenance_repository.py 100%`
  - `fs_processed_document_repository.py 96%`
  - `fs_source_document_repository.py 90%`
  - `local_file_source.py 100%`
  - `repository_protocols.py 100%`
- 全部逐文件 `>=80%`；总计 `2220 statements / 206 miss / 91%`。

## 4. Typing、Ruff 与环境纠正

- scoped pyright（15 production + 4 tests）：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff：`All checks passed!`。
- full pyright：精确 `110 errors, 0 warnings, 0 informations`，与 fix 前累计 checkpoint 相同；全部仍位于 R06-S2/S3 尚未迁移的 producer/callback/composition/test-double，两个本 gate owner与四个 S1 tests零命中。
- full Ruff：`Found 160 errors`，与 fix 前累计 checkpoint 相同；scoped owner/tests零命中。

Controller 首次直接调用 `.venv/bin/pyright` 时没有设置 `VIRTUAL_ENV`，产生 pytest/docling 等 installed dependency unresolved 的无效环境噪音。该命令不能作为代码证据。按 AGENTS.md 使用 `source .venv/bin/activate && pyright` 重跑后得到上述真实 `0/110` 结果；没有因此修改代码或豁免类型错误。

## 5. Source、AST、范围与 README

按 accepted plan §8.3 的精确 closed scope 复跑：

| Scan | 结果 | 裁决 |
|---|---:|---|
| ambient authority | `0` | 无第二 mutation authority |
| S2 acknowledgement | `59` | accepted deferred；本 gate 未删除或增加业务 ack |
| lifecycle | `170` | 相比 fix 前 `168` 的两条增量是 owner test 的一次 begin/commit |
| mutation propagation | `165` | 与 fix 前一致 |
| locator | `118` | 与 fix 前一致；public token/journal 不含 locator |

- 15 个 production 文件所有 function/method 的中文 `Args/Returns/Raises` AST 缺口：`[]`。
- 全部 `_fs_*_core.py` public-to-public self-call：`[]`。
- production reprocess return consumer：0。
- `git diff --check`：pass；staged diff：空。
- cumulative allowlist 保持 15 production + 4 tests + Controller/control/review artifacts；fix authored scope未越界。
- 已按 `dayu/fins/README.md` 与 `tests/README.md` 更新约束复核：本 gate 只收敛既有 private read graph、纠正文档事实、使 shared core 回到既有 public `None` contract，没有新增稳定 public capability、测试层级或用户工作流，不触发 README 更新。

## 6. Residual 与下一 gate

- R06-S2：complete-source validator、blob-first 与 acknowledgement 删除仍由 accepted S2 承接。
- R06-S3：producer/callback/composition propagation 与 full pyright 清零仍由 accepted S3 承接。
- R07：跨调用 snapshot/revision/opaque identity mapping 继续不在本 gate 实施。
- Issue 175/177 与统一 tool authorization framework 保持未实施。

下一 gate 是 AgentMiMo / AgentDS 对 base `d048adf7ec1135aaf575384432ebf1137f8a34f2` 到当前完整累计 S1 tree 的并发 complete re-review。必须逐项确认 `R06-S1-CR-F01..03` 关闭并检查 fix 是否引入新 finding；两路通过前不得进入 S2或创建中间 accepted commit。
