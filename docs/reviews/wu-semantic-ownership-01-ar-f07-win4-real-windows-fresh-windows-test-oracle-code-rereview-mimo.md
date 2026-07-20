# Code Review — AR-F07 WIN4-RW-RF01 最终第一路 Immutable Code Re-Review（AgentMiMo）

## Review Identity

- **Reviewer**: AgentMiMo
- **Review type**: WU-SEMANTIC-OWNERSHIP-01 最后一个内部 remediation sub-WU AR-F07 WIN4-RW-RF01 最终第一路 immutable code re-review
- **Mechanical base**: `39926eb85aa25441f5209a128a3c971f451b5b25`
- **Code path**: `tests/cli/test_upload_filings_from_command.py`
- **Exact function**: `test_windows_generated_script_runs_real_cli_into_temp_storage`
- **Frozen code diff SHA-256**: `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169` ✓ 已独立验证
- **Frozen implementation artifact SHA-256**: `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` ✓ 已独立验证
- **Frozen zero-change fix artifact SHA-256**: `edb947fdb097a21cc330d8cb3c92b0a69bd86dd4c073df6e8ebb6ba45e2fd4cf` ✓ 已独立验证
- **Frozen Controller fix validation SHA-256**: `38035a289e90a0aebd3e4dbd68774f972ae4c628ebdf5a23ce2c30b95675ac0f` ✓ 已独立验证
- **Test file complete SHA-256**: `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` ✓ 已独立验证
- **Frozen plan**: `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，`1124` lines / SHA-256 `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` ✓ 已独立验证
- **Review timestamp**: 2026-07-20T10:07:02+08:00

## Review Chain Context

本 re-review 完整消费以下链路：

1. Accepted corrected plan commit `e2c9a31b`（Controller validation 已确认 clean entry）
2. AgentCodex implementation artifact `f9b36d4b`（Controller validation `382fbf2f` 已确认 PASS）
3. AgentMiMo 初审 `0fbf17bb`（PASS / finding 0）
4. AgentDS 初审 `c60a8db6`（PASS / material finding 0）
5. Controller adjudication（`PASS / ACCEPTED_CODE_FINDING=0 / BLOCKER=0`）
6. AgentCodex zero-change fix `edb947fd`（code diff 不变 `fcecb15c`）
7. Controller fix validation `38035a28`（`PASS / ZERO_CHANGE_FIX_ACCEPTED`）

## Scope

- **Mode**: Current Changes（frozen base `39926eb85` 上的 workspace diff）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `39926eb85aa25441f5209a128a3c971f451b5b25`（frozen mechanical base）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-rereview-mimo.md`
- **Included scope**: 仅 `tests/cli/test_upload_filings_from_command.py` 中 `test_windows_generated_script_runs_real_cli_into_temp_storage` 函数的 snapshot assertion block（行 1003-1017）
- **Excluded scope**: 所有其它文件、函数、import、helper、schema、oracle、README、workflow、product 路径
- **Parallel review coverage**: 无（单一函数块变更，无需 subagent）

## Frozen Diff Identity

**文件**: `tests/cli/test_upload_filings_from_command.py`
**变更量**: 14 insertions / 3 deletions，单一 hunk `@@ -1000,10 +1000,21 @@`

**删除**（base commit 行 1003-1006）:
```python
assert snapshot.primary_filename == source_path.name
assert snapshot.primary_filename in tuple(
    descriptor.name for descriptor in descriptors
)
```

**插入**（working tree 行 1003-1017）:
```python
primary_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == snapshot.primary_filename
)
assert len(primary_descriptors) == 1
raw_source_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == source_path.name
)
assert len(raw_source_descriptors) == 1
raw_source_descriptor = raw_source_descriptors[0]
assert raw_source_descriptor.sha256 is not None
assert raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()
```

**代码 diff SHA-256（冻结命令）**: `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`

冻结命令: `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85aa25441f5209a128a3c971f451b5b25 -- tests/cli/test_upload_filings_from_command.py | shasum -a 256`

## Findings

未发现实质性问题。

## Adversarial Failure Pass（从零逐行走读）

### 1. primary exact-name 与 raw-source exact name 独立性、exact-one、optional hash fail-closed

**行 1003-1008（primary 侧）**:
- `snapshot.primary_filename` 类型为 `str`（`SourceSnapshotProtocol.primary_filename -> str`），非 `Optional[str]`，不会出现 `descriptor.name == None` 意外 True。
- 过滤条件使用 exact `==`，零 loose parsing、零 suffix stripping、零 normalization。
- `assert len(primary_descriptors) == 1`：zero hit → fail；duplicate → fail。exact-one 语义正确。
- 不读取 `primary_descriptor.sha256` 或其它 field —— 按 corrected plan 设计，Fins 拥有 primary 选择的完整性保证。

**行 1009-1017（raw-source 侧）**:
- `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`（Fins contract），`is not None` guard 是必要的 fail-closed 窄化。
- 两段 tuple comprehension 是独立 comprehension，独立 `len == 1` 断言，独立变量作用域。
- 如果 primary 和 raw 命中同一 descriptor（Fins 选择 raw source 为 primary），两边各自 `len == 1` 且指向同一对象，sha256 检查仍正确生效。
- 如果 primary 和 raw 命中不同 descriptor，两边各自 `len == 1`，raw sha256 独立验证。

**Fail-closed 验证表**:

| 输入条件 | primary 断言 | raw-source 断言 | 结果 |
| --- | --- | --- | --- |
| `primary_filename` 不匹配任何 descriptor | `len=0` → fail | 独立 | 正确 fail |
| `source_path.name` 不匹配任何 descriptor | 独立 | `len=0` → fail | 正确 fail |
| 同一 name 出现两次 | `len=2` → fail | `len=2` → fail | 正确 fail |
| `sha256` 为 `None` | 独立 | `is not None` → fail | 正确 fail |
| `sha256` 与 fixture 不一致 | 独立 | 等式 fail | 正确 fail |
| primary==raw（同一 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |
| primary≠raw（不同 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |

**结论: 通过。**

### 2. duplicate descriptor names、zero hit、primary!=raw 合法反例

- **Duplicate descriptor names**: 若 `descriptors` 中有两个同名文件，至少一侧 `len > 1`，断言失败。测试正确拒绝重复描述符。
- **Zero hit**: 若 primary 或 raw-source 不在 descriptors 中，`len == 0` 断言失败。测试正确拒绝缺失描述符。
- **primary != raw 合法反例**: 旧断言 `snapshot.primary_filename == source_path.name` 在此反例下必然失败。新断言不表达此关系 —— Fins 合法选择 Docling JSON 为 primary 且 raw HTML 仍被发布时，两边各自 exact-one 通过，raw sha256 验证通过。
- **primary==raw 仍然合法**: 两边各自 exact-one 通过，无冲突。

**结论: 通过。**

### 3. test 越权选择 Fins primary、hardcoded Docling/private meta/rglob business oracle

| 扫描项 | diff 命中 | 上下文命中 |
| --- | --- | --- |
| test 选择 Fins primary（如 `primary_filename = source_path.name`） | 0 | 0（新断言只读 `snapshot.primary_filename`，不赋值、不覆盖、不选择） |
| Docling hardcode（`docling`、`_docling.json`、`.json` suffix oracle） | 0 | 0 |
| private meta（`meta.json`、`_core`、`materialize_files=True`、`get_source(`） | 0 | 0（snapshot 用 `materialize_files=False`） |
| rglob business oracle | 0（diff 内 `rglob` 为 context line，未修改） | 既有 `rglob` 只做物理文件 existence check |
| `hasattr`/`getattr` fallback | 0 | 0 |
| loose parsing / 二次格式化 | 0 | 0 |

**结论: 通过。**

### 4. exact function-block allowlist、无 import/helper/schema/oracle/README/workflow/product 扩张

- diff 单 hunk 落在 exact function `test_windows_generated_script_runs_real_cli_into_temp_storage` 内。
- `hashlib` 已在文件头部导入（行 6），无新增 import。
- 无新增 `def`（helper）、`class`、module-level constant。
- `cli-grammar-oracle.json` 六键字段集合不变。
- `dayu/` product、其它 tests、README、design、workflow 零 delta。
- staged tree empty；working tree 只含本 target test 文件与 control doc。

**结论: 通过。**

### 5. 测试/pyright/Ruff fresh verification

| Validation | Fresh result |
| --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | `20 passed, 2 skipped, 3 warnings`；`12.32s` |
| `python -m pyright tests/cli/test_upload_filings_from_command.py` | `0 errors, 0 warnings, 0 informations` |
| `python -m ruff check tests/cli/test_upload_filings_from_command.py` | `All checks passed!` |
| `git diff --check` | PASS |

三个 warning 均来自已安装 `edgar` package 的 deprecated imports，不在本次变更范围内。
Windows exact node 在 macOS 上因 `os.name != "nt"` 被正确跳过。

**结论: 通过（真实 Windows 仍 pending，见 Residual Risk）。**

### 6. 安全边界、trusted-local secret 裁决、Tool Trace/audit 明文禁止、deferred Issue 范围不漂移

- 新断言只比较 hash 值（单向摘要），不暴露文件内容。无 secret 泄露风险。
- 测试使用本地 fixture 文件，不涉及 secret。
- 断言不写入任何 trace 或 audit 内容。
- deferred Issues（142/151/175/177/178）、Web/WeChat/render、setx redesign、统一 authorization/secret management、Fins generic diagnostic schema 全部保持 deferred/forbidden，零实现、零预埋。

**结论: 通过。**

### 7. semantic ownership drift 检查

| 事实 | Owner | Test 行为 | 是否越权 |
| --- | --- | --- | --- |
| primary_filename 的选择 | Fins storage | 只验证在 public descriptors 中恰好命中一个 | 否 |
| primary file 完整性 | Fins storage | 只验证 exact-one membership | 否 |
| raw source 的存储 name | Fins storage | 验证 `source_path.name` 在 descriptors 中恰好命中一个 | 否 |
| raw source 的字节完整性 | Fins storage + test oracle | `is not None` guard + exact hash match | 否 |

旧断言是典型 semantic ownership drift —— 测试层越权强制 Fins 层的 primary == raw-source。新断言正确收敛回 Fins contract。无 fallback、特例、`hasattr`/`getattr`、loose parsing 或兼容 shim。

**结论: 通过。**

### 8. plain diff hash 误区

Controller adjudication 已明确：plain `git diff | sha256` 输出 `f4dd51eb...` 是不同序列化格式（无 `--binary --full-index`），不是 identity mismatch。该误区已在 same-task follow-up 中关闭，不可回流。

**结论: 已关闭，无回流风险。**

### 9. POSIX asymmetry

兄弟测试 `test_posix_generated_script_runs_real_cli_into_temp_storage`（行 792）不包含 snapshot/descriptor 断言。这是 pre-existing 且 out-of-scope，非本次变更引入，不构成 finding 或 residual risk。

**结论: non-finding / no-action。**

## Open Questions

无。

## Finding / Backflow / Blocker / Open Ledger

| Category | Count | Status |
| --- | ---: | --- |
| Accepted finding | `0` | CLOSED |
| New finding | `0` | CLOSED |
| Backflow finding | `0` | CLOSED |
| Blocker | `0` | CLOSED |
| Open | `0` | CLOSED |

## Residual Risk

1. **真实 Windows 验证 pending**: macOS 无法执行 `cmd.exe`，Windows exact node 显示 `PLATFORM SKIP`。真实 Windows 验证需在 accepted implementation commit 后通过 fresh R11/R12 workflow 执行。唯一 destination 是 Controller。若 R11/R12 在 primary membership 或 raw-source name/hash 上失败，diagnostic-first stop gate 要求返回 Controller 而非回退到旧断言。

## Non-Finding / No-Action

- **POSIX assertion asymmetry**: 兄弟测试 `test_posix_generated_script_runs_real_cli_into_temp_storage` 不包含 snapshot/descriptor 断言。Pre-existing / out-of-scope / non-finding / no-action。

## Verification Ledger

| 项目 | 值 | 验证方式 |
| --- | --- | --- |
| Mechanical base | `39926eb85aa25441f5209a128a3c971f451b5b25` | `git rev-parse HEAD` |
| Code diff SHA-256 | `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169` | `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85 -- tests/cli/test_upload_filings_from_command.py \| shasum -a 256` |
| Implementation artifact SHA-256 | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` | `shasum -a 256` |
| Zero-change fix artifact SHA-256 | `edb947fdb097a21cc330d8cb3c92b0a69bd86dd4c073df6e8ebb6ba45e2fd4cf` | `shasum -a 256` |
| Controller fix validation SHA-256 | `38035a289e90a0aebd3e4dbd68774f972ae4c628ebdf5a23ce2c30b95675ac0f` | `shasum -a 256` |
| Test file SHA-256 | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('tests/cli/test_upload_filings_from_command.py').read_bytes()).hexdigest())"` |
| Plan file | `1124` lines / SHA-256 `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `python3 -c "..."` |
| Fresh target test | `20 passed, 2 skipped, 3 warnings in 12.32s` | `pytest tests/cli/test_upload_filings_from_command.py -q` |
| Fresh pyright | `0 errors, 0 warnings, 0 informations` | `pyright tests/cli/test_upload_filings_from_command.py` |
| Fresh Ruff | `All checks passed!` | `ruff check tests/cli/test_upload_filings_from_command.py` |
| `git diff --check` | PASS | `git diff --check` |

## Verdict

**PASS**

- **Finding**: 0
- **Backflow**: 0
- **Blocker**: 0
- **Open**: 0

## Correct Next Gate

Controller adjudication → accepted implementation commit（exact code diff `fcecb15c` 上的 commit）→ aggregate gate → fresh R11/R12 workflow 执行真实 Windows 验证。不得直接 remote/PR/closeout。
