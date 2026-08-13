# UF-FIX01 validation-atomic-boundary — Implementation Artifact

## 1. Gate context

- accepted plan commit：`5031ec6b7b7d53a41fe9fb1fc41b5b393260dfbd`
- factual correction checkpoint：`69bc9d2af91788303c839d01ad937cf9b802eb1d`
- implementation date：`2026-08-13`
- scope：S1–S5；保留既有 goal/non-goals、owner boundary、local-only 约束与 UF-FIX09 shared interruptible Docling converter
- branch policy：未创建 PR、未 push、未切分支、未更新 main

## 2. Implemented changes

### S1 — pure read 与 lazy bootstrap

- 新增 `FilingUploadPublishedState`、`FilingUploadStateRepositoryProtocol` 与文件系统实现，在同一 publication guard 下读取 company/source 同版轻量状态。
- fresh canonical root absent 时在 guard、lock 与目录创建前返回 absent；corrupt identity 继续 fail closed。
- repository fallback 使用 `create_directories=False`；legacy job store 只在真实 create mutation 前建立 root，missing read/save 保持零目录副作用。

### S2 — unified validation boundary

- 新增 closed `FinsUploadUsageCode`、typed usage failure/error 与 `ValidatedFinsUploadFilingRequest`。
- 唯一 validator 固定字段、文件、suffix、overwrite、company freshness 与 validation priority；文件文案只消费 basename，不从字符串反推 code。
- CLI 在 Service factory 前读取 pure published state 并校验；usage failure 精确映射 exit `2`。Service、runtime 与 runner 原样传递 validated request；所有 raw non-CLI filing 入口在 producer、observation、job 与 runner 前复用同一 validator。

### S3 — authoritative recheck 与单 batch publication

- production runner 在提交前 fresh 读取 published state，并用同一 validator 丢弃旧 action/company 派生值。
- `DefaultFinsRuntime` 向 SEC/CN facade 与 runner 注入同一个 `FilingUploadStateRepositoryProtocol` instance。
- SEC/CN/HK filing 先完成转换；terminal skip/cancel 不开启 batch。非 terminal 路径以同一 `BatchToken` stage company 与 source/blob，成功一次 commit；stage 或 precommit failure 只 rollback 一次，无补偿 delete、第二 batch 或 late rollback。
- composition owner test 固定 ingestion runtime 缓存、state repository identity，以及 SEC upload、CN upload、CN download、HK download 共用同一 `ProcessDoclingConverter`。

### S4 — typed bounded failure

- 新增层内唯一 owner `dayu.fins.upload_failure`；pipeline 与 orchestration runtime 直接依赖该模块，不存在 pipeline → ingestion runtime 反向依赖、lazy import 或 compatibility re-export。
- exhaustive 映射全部 `DoclingConversionFailureKind`，并为 storage/runtime 提供各自 closed code 与固定安全文案。
- failed pipeline JSON 缺 failure、未知 key/kind/code、kind/code 不一致、pathful/control/过长文本均 fail closed；非 failed 带 failure 同样拒绝。
- pipeline result、runtime summary、direct RESULT details/error message 与 durable failure summary 从同一 typed reason 投影；public 内容不使用 `str(exc)`，operator cause 不进入 public event 或 durable summary。

### S5 — documentation

- 更新根 `README.md`：用户可见 usage exit `2`、content/storage/runtime exit `1` 与失败不发布 filing。
- 更新 `dayu/fins/README.md`：validation owner、pure state read、lazy bootstrap、fresh recheck、single-batch publication、typed failure，以及 validation snapshot 与完整 source snapshot 的职责区别。
- 更新 `dayu/service/README.md`：validated filing request identity handoff；Service 不读取 storage、不重建 request、不按字符串分类。
- 更新 `tests/README.md`：pre-factory zero-mutation、fresh recheck、single-batch atomicity、shared converter 与 typed failure owner coverage。
- 不更新 `dayu/README.md`、Host/Engine/config README 与设计文档：分层关系、Host/Engine contract、config/schema/prompt 均未变化。

## 3. Verification

### Tests

- S4 owner 回归：`273 passed`、`0 failed`；3 条第三方 `edgar` deprecation warning。
- 计划指定最终受影响测试集：`545 passed`、`0 failed`；3 条第三方 `edgar` deprecation warning。
- coverage 主测试运行：`544 passed`；coverage supplement（SEC material/download、CN/HK download owner suites）：`228 passed`。
- import boundary：`2 passed`；确认 closed failure owner 拆分后无反向 import。
- 按 Controller 指示未运行 UF-PF01 focused-real bundle。

### Per-production-file coverage

以下为 `coverage report --include=<all modified production files>` 的逐文件 statement coverage；所有文件均达到 `>=80%`：

| Production file | Coverage |
| --- | ---: |
| `dayu/cli/commands/fins.py` | 85% |
| `dayu/fins/ingestion_runtime.py` | 90% |
| `dayu/fins/pipelines/cn_pipeline.py` | 91% |
| `dayu/fins/pipelines/docling_upload_service.py` | 86% |
| `dayu/fins/pipelines/sec_pipeline.py` | 86% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 89% |
| `dayu/fins/pipelines/upload_company_meta.py` | 89% |
| `dayu/fins/service_runtime.py` | 90% |
| `dayu/fins/storage/__init__.py` | 100% |
| `dayu/fins/storage/_fs_filing_upload_state_core.py` | 94% |
| `dayu/fins/storage/_fs_identity.py` | 81% |
| `dayu/fins/storage/_fs_storage_core.py` | 100% |
| `dayu/fins/storage/_fs_storage_infra.py` | 87% |
| `dayu/fins/storage/fs_filing_upload_state_repository.py` | 100% |
| `dayu/fins/storage/repository_protocols.py` | 100% |
| `dayu/fins/upload_failure.py` | 94% |
| `dayu/service/fins_direct.py` | 90% |
| **TOTAL** | **89%** |

### Type and static checks

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- changed production additions 扫描：无 `hasattr/getattr`、无 `str(exc)` public classification、无补偿删除、无 compatibility shim。

## 4. README decision

README trigger audit 与 accepted plan 一致：root、Fins、Service、tests 更新；`dayu/README.md`、Host、Engine、config 与 design docs 不更新。所有新增文本只描述当前已实现行为，不记录未来态或 gate 流程。

## 5. Residual risks

- UF-PF01 focused-real bundle 按 Controller 明确要求保留到双路 implementation deepreview 通过后，本 implementation gate 未提供该真实 CLI/tree/durable/SHA-256 证据。
- 未执行仓库全量 pytest；执行了 accepted plan 指定的完整受影响测试集与为逐文件覆盖率补充的 SEC/CN/HK owner suites。
- 测试仅出现第三方 `edgar` deprecation warning；无本次实现 warning、测试失败或 pyright error。
