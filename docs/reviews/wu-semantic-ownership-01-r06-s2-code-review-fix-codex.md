# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 code-review fix（Codex）

## 1. Gate 身份与结论

- work unit：继续同一 `WU-SEMANTIC-OWNERSHIP-01 / R06-S2`，不是新 WU。
- gate：code-review fix，只处理 Controller accepted `R06-S2-CR-F01`。
- 状态：`READY_FOR_CONTROLLER_VALIDATION`。
- 下一步仅为 Controller validation；本 gate 未进入 S3，未 stage、commit、push 或创建 PR。
- artifact：`docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-codex.md`。

## 2. 第一性原理动机与直接证据

动机成立，Low 严重性评估准确，不需要扩大为 schema、validator 或 caller 改造。

直接证据是 `dayu/fins/storage/_fs_storage_utils.py::_resolve_primary_uri` 的公开函数契约写明“未找到返回 `None`”，但修复前的控制流在以下两种输入下都执行 `return str(file_payloads[0].get("uri"))`：

1. caller 提供非空显式 `primary_name`，但没有任何 file entry 的规范名称精确匹配；
2. `primary_name` 缺失。

这不是 durable publication qualification 的错误：commit validator 已独立要求 `primary_document` 精确命中完整 files manifest。但 validator 的 fail-closed 不能证明此前返回给 caller 的 `DocumentHandle.primary_file_uri` 正确，也不能为错误派生值提供下游补偿。第一文件的偶然顺序不是显式 primary identity 的业务真源。

## 3. 唯一 semantic owner 与修复边界

- 显式 primary name 到 URI 的派生 owner：`_resolve_primary_uri`。
- durable complete-source publication qualification owner：`FsStorageCore.commit_batch` 调用的 complete-source validator，保持不变。
- 两个 production caller：`_fs_source_document_core.py` 的 source upsert 与 logical delete/restore 投影路径，保持不变。

因此修复只在唯一派生 helper 删除 first-file 猜测：

```text
primary_name 缺失 -> None
primary_name 非空且精确命中 entry name -> 该 entry URI
primary_name 非空但未精确命中 -> None
```

没有在 caller 增加条件，没有放宽 commit validator，没有引入 fallback、loose parsing、兼容 wrapper/shim 或默认 primary。

## 4. 精确 authored diff

### 4.1 Production

`dayu/fins/storage/_fs_storage_utils.py`

- 将入口条件从“files 为空返回 `None`”改为“显式 primary 缺失返回 `None`”；空 files 仍由空迭代自然返回 `None`。
- 保留既有 entry name 解析与精确相等比较。
- 删除末尾 `file_payloads[0].uri` fallback，未命中时明确返回 `None`。

本 gate 没有修改 `_fs_source_document_core.py` 两个 caller，也没有修改 `_fs_storage_infra.py` commit validator。

### 4.2 Tests

`tests/fins/test_fins_storage_atomicity.py`

- 在既有 material create/delete/restore/replace/reset public lifecycle test 中，增加 create 精确 primary 命中后 `DocumentHandle.primary_file_uri == file_meta.uri` 的断言；原有 logical delete/restore 调用与最终 published contract 断言原样保留。
- 新增 owner helper test，分别断言精确命中成功、错误 primary 返回 `None`、primary 缺失返回 `None`。

`tests/fins/test_fins_storage_provider.py`

- 新增 `has_published_old=False/True` 两格 public repository test：同一 transaction 写入两个文件并声明不存在的显式 primary，断言返回的 `DocumentHandle.primary_file_uri is None`。
- 同一测试继续调用真实 `commit_batch`，断言 validator 以 `primary_document 未精确命中 files` fail closed，token 已消费、二次 rollback 被拒绝。
- old-absent 格断言 published source IDs 仍为空且 meta/blob 均不可见；old-present 格断言旧 source ID/bytes 不变且非法新 source 的 meta/blob 均不可见。

没有修改另两个 S2 allowlist tests。没有修改任何其它 production/test、README、control、reviewer/controller artifact。

## 5. 测试与 coverage

所有命令均在 `source .venv/bin/activate` 后运行。

### 5.1 定点行为测试

最终定点结果：

```text
5 passed, 3 warnings in 0.93s
```

覆盖 owner helper、material logical delete/restore、错误 primary 的 old/absent 两格 public contract、既有 blob-first complete commit。

第一次定点迭代曾出现 1 个 test-only failure：新增断言错误假设 `delete_source_document` / `restore_source_document` 返回 `DocumentHandle`，实际 public contract 返回 `None`。未修改 production contract；删除该错误返回值断言后重跑为上述全绿结果，原 logical delete/restore 行为测试保留。

### 5.2 Accepted R06-S2 focused command

```text
91 passed, 144 deselected, 3 warnings in 2.67s
```

三条 warning 均来自 `edgar` 依赖的既有 deprecation warning。

### 5.3 四个累计 S1/S2 allowlist tests 与逐文件 coverage

独立 `coverage run --branch --source=dayu.fins` session：

```text
235 passed, 3 warnings in 10.41s
```

按 `covered_lines / num_statements` 计算 line coverage：

| Production file | Covered / statements | Line coverage |
| --- | ---: | ---: |
| `dayu/fins/storage/_fs_storage_utils.py` | 161 / 184 | 87.50% |
| `dayu/fins/domain/document_models.py` | 417 / 434 | 96.08% |
| `dayu/fins/storage/repository_protocols.py` | 59 / 59 | 100.00% |
| `dayu/fins/storage/_fs_storage_infra.py` | 728 / 813 | 89.54% |
| `dayu/fins/storage/_fs_blob_core.py` | 58 / 64 | 90.62% |
| `dayu/fins/storage/_fs_source_document_core.py` | 328 / 397 | 82.62% |
| `dayu/fins/storage/fs_document_blob_repository.py` | 20 / 20 | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 72 / 77 | 93.51% |

本次新增 owner 文件与累计 S2 production owner 文件全部达到单文件 80% 目标。

## 6. Pyright 与 Ruff

### 6.1 Scoped

scope 为累计 S2 七个 production 文件、本次 `_fs_storage_utils.py` refinement 与四个 allowlist tests：

- pyright：`0 errors, 0 warnings, 0 informations`；
- Ruff：`All checks passed!`。

### 6.2 Full baseline

- full pyright：`108 errors, 0 warnings, 0 informations`，与 accepted S2 baseline 完全一致；错误仍全部属于 accepted R06-S3 producer/callback/test propagation，本次 production/test scope 经 scoped pyright 证明为 0。
- full Ruff：`160`，与 accepted S2 baseline 完全一致；规则分布仍为 `E402=66`、`F401=79`、`F541=3`、`F821=1`、`F841=11`；本次三个 authored Python path 命中 0。

没有新增、扩散、掩盖或 ignore 类型/风格错误。

## 7. Exact scans

| Scan | Result | Attribution |
| --- | ---: | --- |
| ambient authority exact scan | 0 | storage/tests 无 ContextVar、task/thread identity 或 auto-batch 第二 authority。 |
| storage acknowledgement/false exact scan | 0 | `dayu/fins/storage` owner 无旧 acknowledgement contract。 |
| aggregate acknowledgement/false exact scan | 35 | 与 accepted S2 baseline 一致：S3 producer/tests、S3/final README 和两条 fail-closed owner tests；本 fix 未新增命中。 |
| lifecycle exact scan | 188 | baseline 183 加本 public-contract test 的 5 条合法 begin/commit/rollback；均属于 top-level test owner。 |
| mutation exact scan | 173 | baseline 170 加本 public-contract test 的 2 次 `store_file` 与 1 次 `create_source_document`；全部显式 `batch=`。 |
| locator exact scan | 128 | internal active/recovery state 与 owner tests；本 fix 未修改 locator/journal。 |
| `owner_pid|hostname` | 0 | journal/public token 未引入 process owner fact。 |
| `_fs_storage_utils.py` 的 `file_payloads[0]` | 0 | first-file URI 猜测已从唯一 owner 删除。 |
| source owner 的 primary/completion `setdefault` | 0 | 未增加默认 primary 或 completion 补偿。 |

`_resolve_primary_uri` 调用图仍只有 `_fs_source_document_core.py` 的两个既有 production caller；新增三条 test assertion 覆盖 exact/mismatch/missing。caller 未新增条件或重复派生。

## 8. Diff、allowlist 与 docs 决策

- `git diff --check`：通过。
- staged diff：空。
- Controller transition base `d048adf7ec1135aaf575384432ebf1137f8a34f2` 的累计 diff 只比进入本 gate 前增加 `_fs_storage_utils.py`；其余 cumulative S1/S2/control paths 原样保留。
- 本 gate 精确 authored paths：`_fs_storage_utils.py`、两个既有 S2 allowlist tests、本 artifact。
- 未修改另两个 allowlist tests、其它 production/test、control、accepted plan、reviewer/controller artifacts、design 或 README。
- README 决策：用户与 Controller 明确禁止在本 code-review fix gate 更新 README；S2 仍是 breaking cutover 中间 checkpoint，final contract README 继续由 accepted S3/final gate owner 处理。
- 无 stage、commit、push；未进入 S3。

## 9. Finding 状态与 residual risk

### R06-S2-CR-F01

状态：`已修复，等待 Controller validation / dual re-review`。

关闭证据：唯一 owner 不再读取第一文件作为 fallback；missing/mismatch 返回 `None`，exact match 保留；public projection、validator fail-closed、token consumption、published old/absent、logical delete/restore 均有通过的 owner/public-contract tests。

### Residual risks / uncovered areas

1. R06-S3 producer propagation 的 full pyright 108 与 acknowledgement residual 仍由 accepted S3 owner 处理；本 gate 不进入 S3。
2. R07 的跨多个 repository call / 长生命周期 processor snapshot-revision residual 未改变；本 fix 只修单一 `DocumentHandle.primary_file_uri` 派生。
3. README 旧 contract 仍按 accepted plan 留到 S3/final cumulative tree；本 gate 明确不修改。
4. 未发现新的 unclassified residual risk 或 blocking open question。

## 10. Handoff

`READY_FOR_CONTROLLER_VALIDATION`
