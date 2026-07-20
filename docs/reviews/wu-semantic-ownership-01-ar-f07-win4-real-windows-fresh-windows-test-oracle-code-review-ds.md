# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Implementation — AgentDS Adversarial Code Review

## Gate identity and verdict

- Timestamp：`2026-07-20T09:55:24+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate 是最后一个内部 remediation sub-WU `AR-F07 WIN4-RW-RF01` 的第二路完整 immutable code review，不是新 WU。
- Mechanical base：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- Code path：`tests/cli/test_upload_filings_from_command.py`。
- Exact function：`test_windows_generated_script_runs_real_cli_into_temp_storage`。
- Exact code diff SHA-256：`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`（已验证匹配）。
- AgentCodex implementation artifact SHA-256：`f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e`（已验证匹配）。
- Controller validation SHA-256：`382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672`（已验证匹配）。
- Test file 完整内容 SHA-256：`3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110`。
- 本 artifact 只新增，不改任何现有文件，不 stage/commit/push/dispatch，不进入 fix/re-review。

**Verdict：`PASS / MATERIAL_FINDING=0 / BLOCKER=0 / OPEN=0 / BACKFLOW=0 / READY_FOR_CONTROLLER_ADJUDICATION`。**

## Scope

- Mode：exact-function adversarial code review（不是全量 current changes review）。
- Frozen identity：mechanical base `39926eb85` = current HEAD；working tree diff 是本次 review 的唯一实现变更。
- Diff 统计：单 hunk（`@@ -1000,10 +1000,21 @@`），目标函数 `test_windows_generated_script_runs_real_cli_into_temp_storage` 内 snapshot assertion block；零 import、零 helper、零其它 test node、零 product/README/design/workflow 变更。
- 变更内容：
  1. 删除 `assert snapshot.primary_filename == source_path.name`（消除 primary/raw 语义合并）。
  2. 删除旧 `assert snapshot.primary_filename in tuple(descriptor.name for descriptor in descriptors)`（不精确的 membership）。
  3. 新增 primary exact-one membership：按 `descriptor.name == snapshot.primary_filename` 过滤 `descriptors`，断言 `len == 1`。
  4. 新增 raw-source exact-one membership：按 `descriptor.name == source_path.name` 过滤 `descriptors`，断言 `len == 1`。
  5. 新增 raw-source sha256 非空 + 精确等于 fixture bytes SHA-256。
- Excluded scope：本文件内其它所有 test node、helper、module constant、oracle JSON block、import 区均不含变更；`dayu/` product、其它 tests、全部 README/design/control、`.github/workflows/` 均零 diff。

## Review execution

AgentDS 从零 adversarial 执行七维度完整审查：

### Dimension 1 — primary exact-name 与 raw-source exact name/hash 独立性

**Primary side**（working tree lines 1001–1008）：

```python
descriptors = snapshot.files
assert descriptors
primary_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == snapshot.primary_filename
)
assert len(primary_descriptors) == 1
```

- `snapshot.primary_filename` 的类型是 `str`（Fins contract：`SourceSnapshotProtocol.primary_filename -> str`），不是 `Optional[str]`，不会出现 `descriptor.name == None` 的意外 True。
- 过滤条件使用 exact `==`，零 loose parsing、零 suffix stripping、零 normalization。
- 断言只要求恰好命中一个，不要求 primary 等于 raw source。
- 不读取 `primary_descriptor.sha256` 或其它 filed —— 按 corrected plan 设计，Fins 拥有 primary 选择的完整性保证。

**Raw-source side**（working tree lines 1009–1017）：

```python
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

- `SourceSnapshotFileDescriptor.sha256` 的类型是 `Optional[str]`（Fins contract），`is not None` guard 是必要的 fail-closed 窄化。
- 两段 tuple comprehension 是独立 comprehension，独立 `len == 1` 断言，独立变量作用域。
- 如果 primary 和 raw 命中同一个 descriptor（即 Fins 选择 raw source 为 primary），两边各自 `len == 1` 且指向同一对象，sha256 检查仍然正确生效。
- 如果 primary 和 raw 命中不同 descriptor，两边各自 `len == 1`，raw sha256 独立验证。

**Fail-closed 验证**：

| 输入条件 | primary 断言 | raw-source 断言 | 结果 |
| --- | --- | --- | --- |
| `primary_filename` 不匹配任何 descriptor | `len=0` → fail | 独立 | 正确 fail |
| `source_path.name` 不匹配任何 descriptor | 独立 | `len=0` → fail | 正确 fail |
| 同一 name 出现两次 | `len=2` → fail | `len=2` → fail | 正确 fail（两边各自 fail） |
| `sha256` 为 `None` | 独立 | `is not None` → fail | 正确 fail |
| `sha256` 与 fixture 不一致 | 独立 | 等式 fail | 正确 fail |
| primary==raw（同一 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |
| primary≠raw（不同 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |

**结论：primary 与 raw-source 语义完全独立，各自 exact-one 断言 fail-closed，sha256 链式 fail-closed（None guard → exact equality）。PASS。**

### Dimension 2 — duplicate descriptor names、zero hit、primary≠raw 合法反例

- **Duplicate descriptor names**：如果 Fins storage 对同一 snapshot 发布两个 `name` 相同的 descriptor，至少一侧 `len > 1`，断言失败。两次 `len == 1` 独立提供防御纵深。
- **Zero hit**：`primary_filename` 或 `source_path.name` 不在任何 descriptor 中时，对应 tuple 为空，`len == 0`，断言失败。无默认值、无 fallback、无 `in`-only check。
- **primary≠raw 合法反例**：旧断言 `assert snapshot.primary_filename == source_path.name` 在此反例下必然失败。新断言不表达此关系 —— 当 Fins 合法选择 Docling JSON 为 primary 且 raw HTML 仍被发布时，两边各自 exact-one 通过，raw sha256 验证通过。正确的语义分离。
- **primary==raw 仍然合法**：两边各自 exact-one 通过，无冲突。

**结论：所有边界情况均正确 fail-closed 或 pass，无双向语义耦合。PASS。**

### Dimension 3 — test 越权选择 Fins primary、hardcoded Docling/private meta/rglob business oracle

逐项扫描 diff 与上下文：

| 扫描项 | diff 命中 | 上下文命中 |
| --- | --- | --- |
| test 选择 Fins primary（如 `primary_filename = source_path.name` 或 `expected_primary =`） | 0 | 0（新断言只读 `snapshot.primary_filename`，不赋值、不覆盖、不选择） |
| Docling hardcode（`docling`、`_docling.json`、`DOCLING_FILE_SUFFIX`、`.json` suffix oracle） | 0 | 0 |
| private meta（`meta.json` 读取、`_core`、`_private`、`materialize_files=True`、`get_source(`） | 0 | 0（snapshot 用 `materialize_files=False`，不物化文件） |
| rglob business oracle | 0（diff 内 `rglob` 为 context line，未被修改） | 既有的 `source_artifacts = tuple(path for path in (storage / "portfolio").rglob("*") if path.is_file())` 只做物理文件 existence check（`assert source_artifacts`），不按文件名/后缀/路径选择 primary 或推导业务事实 |
| `hasattr`/`getattr` fallback | 0 | 0 |
| loose parsing / 二次格式化 | 0 | 0 |

新断言只消费 `SourceSnapshotFileDescriptor` 的两个 public field：`name: str` 和 `sha256: Optional[str]`。两者均由 Fins storage 作为 public contract 提供，不穿透到 storage 内部实现。

**结论：test 未越权选择 Fins primary，无 Docling/private meta/rglob business oracle 硬编码。PASS。**

### Dimension 4 — exact function-block allowlist、无 import/helper/schema/oracle/README/workflow/product 扩张

diff 单 hunk 验证：

```text
@@ -1000,10 +1000,21 @@ def test_windows_generated_script_runs_real_cli_into_temp_storage(tmp_path: Path
```

- diff hunk 落在 exact function `test_windows_generated_script_runs_real_cli_into_temp_storage` 内。
- diff 不含任何 `import` / `from` 语句（`hashlib` 已在 HEAD committed 版本中存在，本次变更无需新增）。
- diff 不含任何 `def`（新 helper）、`class`、新 module-level constant。
- diff 不含 `cli-grammar-oracle.json` key 集合变更（既有 key：`test_node`、`result`、`generated_script_sha256`、`source_artifact_count`、`cmd_invocation`、`company_name_supplied`，六键不变）。
- diff 不含 `dayu/` product、其它 test 文件、README、design、workflow 任何变更。
- staged tree empty；working tree 只含本 target test file 与 control doc（后者不在本次 review scope）。

**结论：exact function-block allowlist 严格遵守，零 scope creep。PASS。**

### Dimension 5 — 测试/pyright/Ruff evidence 是否足够且真实 Windows 仍 pending

AgentDS 独立 fresh 验证：

| Validation | AgentDS fresh result |
| --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | `20 passed, 2 skipped, 3 warnings in 11.98s` |
| Windows exact node | `1 skipped`（`requires real cmd.exe`；macOS 平台） |
| `python -m pyright tests/cli/test_upload_filings_from_command.py` | `0 errors, 0 warnings, 0 informations` |
| Code diff SHA-256 | `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`（exact match） |
| AgentCodex artifact SHA-256 | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e`（exact match） |
| Controller validation SHA-256 | `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672`（exact match） |

- 三个 warning 均来自已安装 `edgar` package 的 deprecated imports（`edgar.files.htmltools`），不在本次变更范围内。
- macOS 不能执行真实 `cmd.exe`，Windows exact node 的 `skip` 是正确平台行为，不是 test failure。
- 真实 Windows evidence（fresh R11/R12 runs）仍为 `PENDING`——这是 corrected plan §13.8 的明确释放条件，不是本次 code review 的 finding 或 waiver。

**结论：本地 evidence 一致且足够；真实 Windows 仍 pending，分类正确，不作为 code review finding。PASS。**

### Dimension 6 — 安全边界、trusted-local secret 裁决、Tool Trace/audit 明文禁止、deferred Issue 范围不漂移

- 新断言不含任何 API key / secret / token 字面量或环境变量读取。
- `cli-grammar-oracle.json` 六键字段（`test_node`、`result`、`generated_script_sha256`、`source_artifact_count`、`cmd_invocation`、`company_name_supplied`）均不包含 secrets、credentials 或 Tool Trace 内容。
- `_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."` 是公开公司名测试常量，不是 secret。
- 不读取、派生或扫描 GitHub Secrets / configured production secrets / run-specific canary。
- Tool Trace / audit 明文不进入断言或 oracle artifact。
- deferred Issues（142/151/175/177/178）、Web/WeChat/render、setx redesign、统一 authorization/secret management、Fins generic diagnostic schema 全部保持 deferred/forbidden，零实现、零预埋。

**结论：安全边界完整；trusted-local secret 裁决不变；deferred Issue 范围零漂移。PASS。**

### Dimension 7 — correctness/stability/maintainability、semantic ownership drift、adversarial failure pass

#### 7a. Semantic ownership 判定

| 事实 | Owner | Test 行为 | 是否越权 |
| --- | --- | --- | --- |
| primary_filename 的选择 | Fins storage（`_parse_snapshot_files` 内的 Docling JSON 优先逻辑） | 只验证 `primary_filename` 在 public `descriptors` 中恰好命中一个 | 否 — test 不选择、不覆盖、不重定义 primary |
| primary file 完整性 | Fins storage（元数据和内容一致性） | 只验证 exact-one membership | 否 — 不重复验证 primary sha256（Fins contract 内部保证） |
| raw source 的存储 name | Fins storage（上传时保留原始 basename） | 验证 `source_path.name` 在 descriptors 中恰好命中一个 | 否 — 验证 public contract 履行 |
| raw source 的字节完整性 | Fins storage + test oracle | `is not None` guard + `hashlib.sha256(fixture).hexdigest()` exact match | 否 — test 作为 consumer 验证存储结果 |
| company name | Fins storage（`FsCompanyMetaRepository`） | 只读取 `company_meta.company_name` 并比较 | 否 — 不写入、不派生 |
| 脚本 company-name oracle | Test oracle（`_assert_single_windows_upload_company_name`） | 独立验证生成脚本中业务命令的 `--company-name` | 否 — 不依赖 Fins 存储 |

每个事实有唯一 owner；test 不越权产生、解释或持久化任何业务语义。

#### 7b. Adversarial failure pass

AgentDS 逐项验证以下 adversarial 场景：

| 场景 | 分析 | 结论 |
| --- | --- | --- |
| `snapshot.files` 返回空 tuple | `assert descriptors` 对空 tuple 为 False → fail | fail-closed |
| `snapshot.primary_filename` 为 `""` 且恰好有一个 descriptor 名为 `""` | `descriptor.name == ""` 匹配 → `len=1` → pass。但 Fins contract (`_parse_snapshot_files` line 987-988) 通过 `_normalize_filename` 拒绝空名 → 此场景不可达 | 不可达 |
| `source_path.name` 被 Fins 规范化后与原始不同 | `raw_source_descriptors` 的 `len=0` → fail。这是对 Fins 公共 contract（保留原始 basename）的正确验证 | fail-closed |
| `hashlib.sha256(fixture).hexdigest()` 与 Fins 存储的 sha256 因上传时字节转换而不匹配 | 等式 fail → fail。Fins 应 byte-for-byte 保留上传内容 | fail-closed（contract enforcement） |
| 脚本生成成功但执行失败（exit ≠ 0） | `assert execution.returncode == 0, execution.stderr` → fail | fail-closed |
| Company meta 不存在或字段为空 | `FsCompanyMetaRepository` 抛出或 `assert company_meta.ticker == "AAPL"` → fail | fail-closed |
| `_assert_single_windows_upload_company_name` oracle 本身有 bug | Oracle 由独立 test `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence` 和 `test_windows_renderer_round_trips_fixed_argument_oracles` 验证 | defense-in-depth |
| 并发写入 portfolio（多进程） | 本 test 为单进程 subprocess，无并发 | 不适用 |

所有 adversarial 场景均 fail-closed 或不可达。

#### 7c. Stability 与 maintainability

- 新断言只用 tuple comprehension + `len == 1`，无复杂控制流、无嵌套异常处理、无外部依赖引入。
- 如果 Fins 未来改变 primary 选择策略（比如不再选 Docling JSON），test 仍然 pass（只要 primary_filename 命中一个 descriptor）。
- 如果 Fins 未来改变 raw source 命名规则，test 正确 fail（contract regression detection）。
- 无 observable 副作用：不修改 `descriptors`、不调用 mutating API、不在 `with` block 外持有 snapshot 引用（snapshot 在 `with` 退出后正确释放）。
- `cli-grammar-oracle.json` 在断言全部通过后才写入（断言失败 → 提前退出 → 不写入 `"result": "passed"` → 无假阳性 artifact）。

**结论：correctness 无 defect；stability 充分；maintainability 无退化；semantic ownership 零漂移；adversarial failure pass 全覆盖。PASS。**

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **真实 Windows evidence 仍 pending**：本 test node 在 macOS 上因 `os.name != "nt"` 被 `pytest.mark.skipif` 正确跳过。fresh R11/R12 `windows-latest` runs 是 corrected plan §13.8 的唯一 release closure gate。此 residual 已由 Controller 正确分类为 `COVERED_BY_LATER_APPROVED_REMOTE_VALIDATION`，不是本次 code review 的 finding 或 waiver。
- **Full Ruff baseline 142 项**：pre-existing immutable baseline，不在本次 diff 范围内；AgentCodex/Controller 已独立证明五元组集合与 digest 不变。

## Verification ledger

| 项目 | 值 | 验证方式 |
| --- | --- | --- |
| Mechanical base | `39926eb85aa25441f5209a128a3c971f451b5b25` | `git rev-parse HEAD` |
| Code diff SHA-256 | `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169` | `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85 -- tests/cli/test_upload_filings_from_command.py \| shasum -a 256` |
| AgentCodex artifact SHA-256 | `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` | `shasum -a 256 docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-codex.md` |
| Controller validation SHA-256 | `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672` | `shasum -a 256 docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-controller-validation.md` |
| Test file 完整 SHA-256 | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('tests/cli/test_upload_filings_from_command.py').read_bytes()).hexdigest())"` |
| Target test file fresh | `20 passed, 2 skipped, 3 warnings in 11.98s` | `pytest tests/cli/test_upload_filings_from_command.py -q` |
| Target file pyright | `0 errors, 0 warnings, 0 informations` | `pyright tests/cli/test_upload_filings_from_command.py` |
| `_FIXTURE_SOURCE` 存在 | `True`，`1503780` bytes | `pathlib.Path.exists()` |

## Next gate

```
Controller adjudication → AgentCodex 修复所有 accepted findings（即使 0 也要 zero-change fix record）→ AgentMiMo + AgentDS 双路完整 re-review
```

本 review 返回 `PASS / MATERIAL_FINDING=0`，authorized next gate 为 Controller adjudication。

---

AgentDS 停止。不改任何现有文件，不 stage/commit/push/dispatch，不进入 fix/re-review。
