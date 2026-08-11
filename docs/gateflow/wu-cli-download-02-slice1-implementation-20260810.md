# `WU-CLI-DOWNLOAD-02` Slice 1 Implementation Gate

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Slice：Slice 1 — F12 invocation invariant 与 help
- Gate：implementation
- 日期：2026-08-10
- Accepted plan：`docs/gateflow/wu-cli-download-02-plan-20260810.md`
- Accepted-plan HEAD：`0fe85869bffe214d6d8bc18d0e69690a493928d1`
- 当前 branch：`codex/download-oracle`
- Artifact path：`docs/gateflow/wu-cli-download-02-slice1-implementation-20260810.md`
- Completion status：implementation complete；按用户要求停在 code review 前，等待总控 review。

本 gate 只实现 Slice 1。未修改 Slice 2/3、README、Service、runtime、workflow、provider 或 storage；未运行真实 post-fix CLI evidence；未 commit、push 或创建 PR。

## 2. 第一性原理判断与语义 owner

问题动机成立且严重性评估正确：`overwrite` 允许远端下载覆盖完整本地 source，`rebuild` 则要求只使用本地 source 且不访问远端，二者同时为真没有有效业务语义。冲突必须在 public typed request 成为可执行 operation 前拒绝，不能由 parser、Service、runtime 或 workflow 选择 precedence。

唯一语义 owner 为 `dayu.fins.download_contract` 中的 `_validate_download_mutation_mode(...)`：

- `FinsDownloadRequest.__post_init__` 调用该 helper，确保 CLI/Service 构造出的 public request 在 workspace resolution 前 fail closed。
- `FinsDownloadEffectiveFilters.__post_init__` 复用同一 helper，拒绝独立构造的非法公共投影。
- `build_fins_download_request(...)` 继续只做 canonicalization 和 typed request 构造，不复制冲突判断。
- CLI parser 只把同一 contract 投影到两个 flag 的 help；未注册 mutually-exclusive group 或第二个 validator。

## 3. Preflight 与直接证据

开始修改前从仓库根重新执行 branch/status、HEAD 与 Slice 1 构造/消费点 `rg`：

- branch：`codex/download-oracle`，不是 protected trunk。
- worktree：干净。
- HEAD：`0fe85869bffe214d6d8bc18d0e69690a493928d1`，与用户指定 accepted-plan HEAD 完全一致。
- `FinsDownloadRequest(...)` 的 production 构造真源仍为 `dayu/fins/download_contract.py::build_fins_download_request(...)`。
- CLI 调用顺序仍为 `_prevalidate_download_request -> _resolve_workspace_root -> FINS_DIRECT_SERVICE_FACTORY -> operation`，因此 request invariant 的异常发生在 workspace、factory 和 operation 前。
- preflight 找到的双 true 只存在于两处旧测试 fixture：Service pass-through fixture 与 CLI 参数映射测试；production 没有既存冲突判断或 precedence。

修改后重新执行精确 guard：

```text
rg "overwrite_existing and rebuild_local_artifacts|rebuild_local_artifacts and overwrite_existing" dayu
  dayu/fins/download_contract.py:79: if overwrite_existing and rebuild_local_artifacts:

rg "_validate_download_mutation_mode\(" dayu
  helper definition: 1
  FinsDownloadEffectiveFilters call: 1
  FinsDownloadRequest call: 1
```

AST owner test同时断言包含两个 mode 字段的 production `and` owner 集合精确等于 `{_validate_download_mutation_mode}`。`_register_download_command(...)` 的 post-change 源码仍只调用普通 `parser.add_argument(..., action="store_true")`。

## 4. 实现与 changed files

### Production

- `dayu/fins/download_contract.py`
  - 新增唯一 mode helper 与唯一 actionable conflict message。
  - helper 严格校验两个字段均为 `bool`，双 true 抛出 `FinsDownloadUsageError`。
  - request 与 effective filters 的 `__post_init__` 复用 helper。
  - 新增/补齐中文 docstring 的参数、返回值、`TypeError` 与 `FinsDownloadUsageError` 说明。
- `dayu/cli/arg_parsing.py`
  - `--overwrite` help 明确不可与 `--rebuild` 同时使用。
  - `--rebuild` help 明确 local-only/no-remote 语义及不可与 `--overwrite` 同时使用。
  - 未增加 parser-side 冲突判断。

### Tests

- `tests/service/test_fins_direct.py`
  - 原双 true Service pass-through fixture 改为合法 overwrite-only request。
  - 新增 request/effective filters 的 `00/10/01` 合法矩阵、`11` 精确同诊断、非 bool TypeError 与唯一 conjunction owner guard。
- `tests/cli/test_arg_parsing.py`
  - download help inventory 新增 `--rebuild`，并断言两个 option 的互斥说明。
- `tests/cli/test_fins_commands.py`
  - 原非法双 true 映射测试改为 overwrite-only/rebuild-only 两个合法 sentinel。
  - 新增两个冲突 argv 顺序，精确断言 exit 2、actionable stderr、Service factory 0、operation 0、workspace 不存在。

`ruff format` 对上述 allowed changed files 做了机械格式化；未触碰 plan 外 production/test 文件。

## 5. Tests 与 validation

所有命令均在仓库根执行并先 `source .venv/bin/activate`。

### Slice 1 affected tests

```text
pytest tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py
550 passed, 3 warnings in 5.04s
```

3 个 warning 均来自 `edgar` 依赖的既有 deprecation warning，不是本 slice 新增失败或 warning。

### Focused owner union 与 coverage

首次只用 Slice 1 三文件采集整文件 coverage 时，`arg_parsing.py=99%`，但 `download_contract.py=67%`，未达到 accepted plan 的逐 production 文件 80% 门槛。未使用 omit、pragma、降阈值或 aggregate 掩盖；随后按 accepted plan §7.1 的完整 focused owner union 重跑：

```text
coverage erase
coverage run -m pytest \
  tests/service/test_fins_direct.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_output.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_report_selection.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_fins_ingestion_runtime.py

1021 passed, 3 warnings in 13.26s
```

最终逐文件 line coverage：

| Changed production file | Statements | Miss | Line coverage | Gate |
|---|---:|---:|---:|---|
| `dayu/cli/arg_parsing.py` | 342 | 2 | 99% | PASS |
| `dayu/fins/download_contract.py` | 325 | 39 | 88% | PASS |

### Static / type validation

```text
ruff check <5 changed Python files>             PASS
ruff format --check <5 changed Python files>    PASS
python -m compileall -q <2 production modules>  PASS
pyright                                          PASS（0 errors）
git diff --check                                 PASS
```

Post-change `git diff --name-only` 在创建本 artifact 前精确为 plan 允许的 5 个 production/test 文件；创建 artifact 后只额外包含用户明确要求的本文件。

## 6. Docs decision

- README：按用户明确要求，本 slice 不修改。accepted plan §8 的最终用户/开发者文档更新留到后续获批 slice 行为稳定后处理。
- 本 implementation artifact：已创建，用于记录 gate、直接证据、changed files、validation、coverage 与 residual risk。

## 7. Residual risks 与 uncovered areas

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| 当前证据是 in-process CLI owner tests，尚未以 detached clean worktree/installed CLI 验证两个真实 argv 顺序和 help。 | covered by later approved slice | accepted plan §9.2；仅在所有 slice/review 稳定后由 CLI evidence gate 执行。用户明确禁止本轮运行。 |
| README 尚未投影 F12 用户可见互斥语义。 | covered by later approved slice | accepted plan Slice 3 稳定后的 README decision；用户明确禁止本轮修改。 |
| F13/F14 的 provider/material period policy 与 data flow 未实现。 | covered by later approved slice | Slice 2 / Slice 3；本 gate 不提前修改。 |

没有 unclassified residual risk；没有 deferred finding 需要在本 implementation gate 内裁决。

## 8. Completion signal 与 next entry point

Slice 1 completion signal 已满足：唯一 typed invariant 存在；request/filter 复用；两种冲突 argv 顺序均在所有副作用前 exit 2；help 自解释；三个合法 typed 组合及两个合法 CLI single-mode sentinel 保持可用；affected tests、focused owner union、changed-files Ruff/format、compileall、pyright、diff guard 与逐文件 coverage 全部通过。

按用户明确 stop condition，本轮停在 implementation complete。Next entry point：总控发起 Slice 1 code review；不得自行进入 fix、re-review、accepted slice commit、Slice 2 或 production CLI evidence。
