# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Controller Validation

## 1. Gate 与范围

- umbrella WU：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：`R01 Doc complete input`；不是新 WU。
- slice：`R01-S1`。
- accepted plan commit：`54e35231`。
- slice base：`1b4e5d33`。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s1-codex.md`。

本 artifact 是 controller 的独立验证复核，不替代 AgentMiMo / AgentDS code review，也不授权 R01-S2。

## 2. 直接代码复核

### 2.1 Owner boundary

总控完整读取新增 `source_snapshot.py`、implementation artifact，并核对 `doc_tools.py` 与三份测试 diff：

- `SourceSnapshot` 只依赖标准库与同包 `Source` 协议；没有 Tool/Host/Engine/Service/UI/Fins 反向依赖。
- snapshot 不接收 byte limit/budget/policy；单次 `Source.open()` 按固定 chunk 复制到真实 EOF。
- 独立 cursor、active exact size、single materialized path、single enter、idempotent close、异常/取消 cleanup 均在 owner 内实现。
- `doc_tools.py` 删除 `_DOC_SOURCE_MAX_BYTES`、`DocResourceBudget`、`SourceBudgetExceeded`、`resource_budget` / `max_source_bytes` 全链、source failure mapping、search oversized skip/counter/result/reason 与 LLM-facing source-cap 引导。
- S1 仅在 list/search route 直接传既有 `_DOC_DIRECTORY_MAX_ENTRIES`，没有新增 validator/wrapper/budget/config/optional/compatibility seam。
- directory cap/partial、result limit、allowed paths、search/direct-read containment、process capability、cancellation/fencing、read char output 与 ToolTruncateSpec/fetch_more 均仍存在。

### 2.2 Tests 与 allowlist

相对 `1b4e5d33` 的 tracked semantic diff 只有 accepted S1 六个 production/test 路径；另有 plan 允许的 `source_snapshot.py` 与 implementation artifact 两个 untracked 新文件。没有 control/design/README/Host/Engine/runtime/config/Fins/UI/Service diff。

测试从旧预算 shape 迁到 owner contract：完整 EOF、declared length metadata、独立 cursor、single source open、materialization/cleanup、I/O/cancellation、process target 精确字段、raw read 完整输入、search processor 完整输入与 removed-field absence。测试仍保留 S1 directory partial、result partial、path/symlink、process/direct/cancellation 和 output truncation contract。

## 3. Controller 重跑验证

在项目 Python 3.11 venv 中重跑：

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
75 passed in 2.42s

coverage run --data-file=workspace/tmp/.coverage-r01-s1-controller -m pytest \
  tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
75 passed in 2.77s

source_snapshot.py: 147 statements / 13 miss / 91%
doc_tools.py: 768 statements / 152 miss / 80%

python -m pyright
0 errors, 0 warnings, 0 informations

ruff check <S1 changed Python files>
All checks passed

git diff --check
pass
```

传播扫描结果：

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit` 在 `dayu tests README.md` 零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests` 零命中。
- `_DOC_DIRECTORY_MAX_ENTRIES|max_directory_entries` 只命中 S1 计划保留的 list/search producer/tests。
- `ToolTruncateSpec`、`result_limit`、`_project_doc_paths`、`_resolve_search_files_candidate`、cancellation 与 process capability 仍有预期 owner/test 命中。
- source-cap LLM recovery 文本在 Doc LLM-facing surface 零命中；directory partial 引导仍按 S1 contract 保留到 R01-S2。

## 4. README decision

总控重读 `tests/README.md`。该文档当前把 source 与 directory 两类旧 contract 写在同一 Documents/Tools 段落；accepted plan 把终态 README 更新放在 R01-S2。S1 不写中间态 README 符合 plan，但 R01-S2 必须更新，不能在 R01 closeout 遗留旧 source budget 描述。其它 README 的读者 contract 未被 S1 改变。

## 5. Review focus 与 gate decision

Controller validation **PASS**；未发现可直接接受的新 finding。双路 code review 仍必须重点挑战：

1. `SourceSnapshot` 的 stream/context/cleanup/concurrency 状态机是否有反例，尤其 source stream 异常、materialize 失败、reader 在 close 后使用和 declared/actual length 变化。
2. Doc process/direct route 是否仍有隐式 source cap、字段残留、参数错配或错误语义漂移。
3. search 删除 oversized catch 后，真实 I/O/cancel/error 是否仍按 owner 投影，未被宽泛 exception 错误吞没。
4. S1 是否误动 directory partial、symlink/containment、output truncation/fetch_more 或 Issue 177 边界。
5. 测试删除 8 个 node 后是否遗漏 owner-level failure path，逐文件 coverage 的 80% 边界是否由有意义断言而非偶然覆盖满足。

下一 gate：AgentMiMo / AgentDS 并发完整 R01-S1 code review。任何 accepted finding 都必须由 AgentCodex 修复并双路 re-review；无 reviewer/controller acceptance 前不得 commit 或进入 R01-S2。
