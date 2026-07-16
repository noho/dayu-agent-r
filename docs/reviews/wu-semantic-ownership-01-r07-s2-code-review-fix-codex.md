# WU-SEMANTIC-OWNERSHIP-01 R07-S2 cumulative code-review fix（Codex）

## 结论

- Gate：`R07-S2 cumulative code-review fix`
- Finding：`R07-S2-CR-F01`
- 状态：`FIX COMPLETE / READY FOR CONTROLLER VALIDATION`
- 归属：仍属于 `WU-SEMANTIC-OWNERSHIP-01` umbrella WU 的 R07 internal sub-WU，不是新 WU。
- 修复范围只覆盖 Controller 已接受的 snapshot resource lifecycle finding；没有进入 S3 或其它 deferred scope。

## 动机与 root cause 判定

Finding 成立。原实现由三个 consumer 各自在 `finally` 中调用 `snapshot.close()`；当业务主失败与 close 失败同时发生时，Python 的异常替换语义会让资源释放失败覆盖 authoritative 业务失败。该问题不是 consumer 展示或 adapter 问题，正确 owner 是 storage snapshot resource lifecycle。

修复将双失败决策集中到 `SourceSnapshotProtocol` 及其 private filesystem implementation：consumer 只声明生命周期，不再拥有异常优先级、secondary error 投影或 close fallback 规则。

## Accepted finding closure

`R07-S2-CR-F01` 已按 Controller 裁决关闭：

1. `SourceSnapshotProtocol` 提供统一 Python context-manager contract；private implementation 持有具体临时 locator、清理与 retry 细节。
2. 无 active primary 时，`__exit__` 正常传播 close failure，不吞错。
3. 有 active primary 时，保留同一个 primary exception identity；close failure 只通过既有 `_append_secondary_error_note` 追加固定 action、error type 与可选 errno。
4. raw close exception 不作为 cause/context 进入最终异常图，其 message、traceback 与 filesystem locator 也不进入 note。
5. `__exit__` 返回 `Literal[False]`，明确不压制 lifecycle body 异常。
6. `close()` 的显式调用、幂等、失败后保留 temp root 并允许重试的既有 contract 未改变。
7. ingestion preprocess、SEC fiscal fields、SEC 6-K primary document repair 三个 S2 consumer 全部切换到同一个 owner lifecycle；未新增 consumer-local `sys.exc_info`、helper、fallback、facade 或 compatibility branch。

## 文件边界

本次 fix 修改：

- `dayu/fins/storage/repository_protocols.py`
  - 为 `SourceSnapshotProtocol` 增加严格类型的 `__enter__` / `__exit__` contract。
- `dayu/fins/storage/_fs_source_snapshot.py`
  - 在 private snapshot implementation 实现统一 lifecycle 与双失败投影规则。
- `dayu/fins/ingestion_runtime.py`
  - preprocess 改用 owner lifecycle；snapshot close 仍发生在 commit 开始前。
- `dayu/fins/pipelines/sec_fiscal_fields.py`
  - fiscal extraction 改用同一 lifecycle；原有 acquisition-only best-effort 边界和提取算法不变。
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
  - 6-K candidate assessment 改用同一 lifecycle；更新仍在 snapshot 关闭后执行。
- `tests/fins/test_fins_storage_atomicity.py`
  - 增加 owner-level active-primary/close-secondary 与 close-primary 双失败测试，并断言完整异常图 path-free 和 close retry。
- `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-codex.md`
  - 本 fix 的唯一 review artifact。

未修改 accepted plan、implementation control、Controller adjudication、reviewer artifact；未 stage、commit、push 或创建 PR。

## 行为与顺序不变量

- preprocess：snapshot lifecycle 退出后才设置 `commit_started = True` 并 commit；close failure 仍触发既有 pre-commit rollback，close-before-commit 顺序不变。
- SEC fiscal fields：snapshot acquisition 失败仍按既有 best-effort 返回空 fiscal；已成功取得 snapshot 后的 lifecycle close failure 不被 acquisition catch 吞掉，业务提取算法不变。
- SEC 6-K repair：candidate assessment 在 snapshot lifecycle 内完成，source update 仍在退出 lifecycle 后执行；selection、staging 与 caller-owned batch commit/rollback 语义不变。

## 验证

### 精确行为节点

- 新增 owner-level 双失败节点：`2 passed in 0.58s`。
- owner lifecycle 与三个 consumer 的精确累计回归节点：`9 passed, 3 warnings in 0.97s`。
- warning 均来自既有 `edgar` 依赖弃用提示。

覆盖的关键行为包括：

- active primary + close secondary 保留原 primary identity，只附加 path-free action/type/errno note；
- 无 active primary + close failure 传播 path-free close primary；
- 两种失败路径的完整 exception graph 均不含 workspace path、temp locator 或 raw close message；
- cleanup failure 后 temp root 保留，恢复清理能力后显式 `close()` 可重试成功；
- 三个 consumer 已消费统一 lifecycle，preprocess close-before-commit 与 rollback/commit 顺序保持不变。

### 五文件累计测试

命令范围：

- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_processor_read_consistency.py`

结果：`401 passed, 3 warnings in 24.02s`。

### Changed production line coverage

覆盖率数据：`workspace/tmp/r07-s2-fix-coverage.json`。15 个累计 changed production 文件均不低于 80%，最低 `80.00%`，最高 `100.00%`。

| 文件 | covered/statements | line coverage |
| --- | ---: | ---: |
| `dayu/fins/domain/document_models.py` | 416/432 | 96.30% |
| `dayu/fins/storage/_fs_identity.py` | 92/115 | 80.00% |
| `dayu/fins/storage/_fs_storage_utils.py` | 202/241 | 83.82% |
| `dayu/fins/storage/_fs_storage_infra.py` | 870/1010 | 86.14% |
| `dayu/fins/storage/_fs_blob_core.py` | 59/67 | 88.06% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 123/135 | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 182/197 | 92.39% |
| `dayu/fins/storage/_fs_processed_core.py` | 159/179 | 88.83% |
| `dayu/fins/storage/_fs_source_document_core.py` | 313/375 | 83.47% |
| `dayu/fins/storage/repository_protocols.py` | 97/97 | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 76/79 | 96.20% |
| `dayu/fins/storage/_fs_source_snapshot.py` | 405/449 | 90.20% |
| `dayu/fins/ingestion_runtime.py` | 1536/1694 | 90.67% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 280/304 | 92.11% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 149/181 | 82.32% |

### 静态与 hygiene 验证

- full pyright：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff（15 个 production 文件 + 5 个累计 test 文件）：`All checks passed!`。
- full Ruff baseline fingerprint：共 `152` 条，保持既有分布：`F401=72`、`E402=66`、`F841=10`、`F541=3`、`F821=1`；本次 scoped 变更没有新增或扩散。
- `git diff --check`：通过。
- accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`，未变化。

### Source / exception graph / temp-root / boundary scans

- 三个 consumer 的目标调用路径均已使用 context-manager lifecycle；未发现 consumer-local `snapshot.close()`、`sys.exc_info` 或 `_append_secondary_error_note`。
- owner scan 只在 protocol/private snapshot implementation 暴露 lifecycle contract 与 secondary note rule；具体 locator/retry 仍为 private implementation 细节。
- owner-level 测试断言 active-primary 异常图只有原 primary 节点；无-primary close failure 的 context/cause 图不携 raw close error，两个图均 path-free。
- `tempfile.gettempdir()` 下 `dayu-source-snapshot-*` 扫描结果：`0`。
- source revision scan 未发现新的 hash builder 或 revision grammar；`dayu/fins/tools/read_runtime.py` 中既有 before/after revision 与 cache 使用仍属于明确 deferred S3，未在本 fix 改动。
- `tests/README.md` 中既有 `sha256:<hex>` 是层中立文本 digest 测试说明，不是 source revision grammar。

## README trigger 判定

本 fix 没有改变稳定用户 contract、安装/CLI/工作流、分层关系或既有 S2 storage snapshot 对外事实；只是把已接受的资源释放与异常优先级语义归位到 owner lifecycle。现有 `dayu/fins/README.md` 和 `tests/README.md` 已覆盖 R07-S2 的稳定 contract 与测试边界，因此本 fix 不新增 README 修改。

## S3 / deferred / security non-change

- 未进入 S3 processor cache、borrow/read-runtime lifecycle、citation provenance 或 file-kind 删除。
- 未进入 R08+，未扩大 Issues 142/151/175/177/178 或 unified authorization 范围。
- 未改变 opaque revision identity、batch publication、rollback/recovery、symlink/containment、atomic write、typed error 或 storage locator 保密边界。
- 未新增 LLM-facing prompt、tool schema、memory、trace 或 evidence 文本变化。
- 未新增 public glue、facade、compatibility shim 或跨层反向依赖。

## Residual risk 与交接

当前 accepted finding `R07-S2-CR-F01` 没有遗留未关闭项。仓库仍保留既有 full Ruff 152 条 baseline 和 3 个第三方依赖弃用 warning；它们不在本 fix 授权范围内。S3 read/cache/borrow 迁移仍按 accepted plan 留待后续 slice。

本次工作停在 `READY FOR CONTROLLER VALIDATION`，等待 Controller 执行 validation；不继续 cumulative re-review、commit 或 PR gate。
