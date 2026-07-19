# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S1 Re-Review（AgentMiMo 第一路）

## Result

`PASS / NO_NEW_FINDINGS / NO_BACKFLOW_FINDINGS / REAL_WINDOWS_PENDING`

## Scope

- Mode: current changes（AR-F07 WIN4-RW-S1 unchanged target re-review）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1
- Branch: `phaseflow/host-issues-control`
- Base: S1 authorization entry `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-mimo.md`
- Payload: `tests/cli/test_upload_filings_from_command.py`
  - Content SHA-256: `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` ✓（本机 `shasum -a 256` 已核验）
  - Git tree entry: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Diff stat（entry vs working tree）: 44 insertions / 3 deletions
- Staged tree: empty（`git diff --cached` 无输出）
- `git diff --check`: PASS（无 whitespace error）
- Parallel review coverage: 无

## 审查依据（完整读取清单）

| Artifact | 读取状态 |
|---|---|
| `AGENTS.md`（128 行） | ✓ 完整读取 |
| `CLAUDE.md`（项目约束） | ✓ 完整读取 |
| Accepted amended plan（commit `cb2785d9`，1060 行） | ✓ 完整读取 |
| S1 postcommit authorization（commit `8fafe9ba`） | ✓ 已核验 |
| S1 implementation artifact（SHA-256 `b12e3489...`） | ✓ 完整读取 |
| S1 Controller validation（SHA-256 `2c326a9b...`） | ✓ 完整读取 |
| AgentMiMo initial code review（SHA-256 `62b49d40...`） | ✓ 完整读取 |
| AgentDS initial code review（SHA-256 `332947a0...`） | ✓ 完整读取 |
| Controller adjudication（SHA-256 `365f2196...`） | ✓ 完整读取 |
| AgentCodex zero-change artifact（SHA-256 `09de7075...`） | ✓ 完整读取 |
| Controller zero-change validation（SHA-256 `4d56682b...`） | ✓ 完整读取 |
| Payload `tests/cli/test_upload_filings_from_command.py`（1226 行） | ✓ 完整逐行走读 |
| `dayu/fins/storage/repository_protocols.py`（`SourceSnapshotProtocol`、`SourceSnapshotFileDescriptor`、`CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol`） | ✓ 完整读取相关协议 |
| `dayu/fins/storage/__init__.py`（public exports） | ✓ 完整读取 |
| `dayu/fins/domain/enums.py`（`SourceKind`） | ✓ 完整读取 |
| `dayu/fins/storage/fs_company_meta_repository.py`（构造签名） | ✓ 完整读取 |
| `dayu/fins/domain/document_models.py`（`CompanyMeta`） | ✓ 引用确认 |

## 重新验证维度

### 维度 1: Display 依赖零回流

**验证目标**：`"Fins result" in execution.stdout` 已彻底删除，未用任何 stdout/stderr/word/parser/regex/count 替代。

**直接证据**：

| 检查项 | 旧代码（已删除） | 当前代码 | 判断 |
|---|---|---|---|
| stdout 内容断言 | `assert "Fins result" in execution.stdout`（旧 line 879） | 已删除（diff `-` 行） | ✓ 彻底删除 |
| stdout 引用 | — | `execution.stdout` 在 `test_windows_generated_script_runs_real_cli_into_temp_storage` 中零引用 | ✓ 无替代 |
| stderr 替代 | — | `assert execution.returncode == 0, execution.stderr`（line 981）— stderr 仅作断言失败诊断，不作成功判断 | ✓ 非替代 |
| `str.find` / `in` / `.count()` 替代 | — | S1 unstaged 新增行零此类操作 | ✓ 无替代 |
| `shlex` / `json.loads(stdout)` / regex 解析输出 | — | 零引用 | ✓ 无替代 |
| parser 替代 | — | 零任何 stdout 解析逻辑 | ✓ 无替代 |

**逐行走读确认**：完整走读 `test_windows_generated_script_runs_real_cli_into_temp_storage`（lines 912–1030），确认成功判断完全依赖 `execution.returncode == 0`（line 981）→ public repository typed contracts（lines 982–1006）。stdout/stderr 不参与业务判断。

**结论**：display dependency 已彻底清除，零回流。**PASS**。

### 维度 2: Exit → public storage facts → physical integrity → oracle 顺序

**验证目标**：确认断言执行顺序为 process exit → storage facts → physical integrity → oracle artifact 写入。

**直接证据**（line-by-line sequence）：

```
Line 981:  assert execution.returncode == 0, execution.stderr     ← process exit 先验
Line 982:  company_meta = FsCompanyMetaRepository(storage).get_company_meta("AAPL")
Line 983:  assert company_meta.ticker == "AAPL"
Line 984:  assert company_meta.company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME
Line 985:  source_repository = FsSourceDocumentRepository(storage)
Line 986-990: list_source_document_ids → len == 1 → document_id
Line 992-1006: read_source_snapshot → with block → identity/descriptor assertions
Line 1007-1010: rglob("*") → assert source_artifacts                  ← physical integrity
Line 1011-1030: (artifact_directory / "cli-grammar-oracle.json").write_text(...)  ← oracle 最后
```

**逐行走读确认**：
- `execution.returncode == 0`（line 981）先于所有 storage 读取。
- Storage facts（lines 982–1006）先于 physical integrity（lines 1007–1010）。
- Physical integrity 先于 oracle artifact 写入（lines 1011–1030）。
- Oracle artifact 写入是最后一个操作，且在所有断言通过后才执行。

**结论**：exit → storage facts → physical integrity → oracle 顺序严格正确。**PASS**。

### 维度 3: Snapshot with lifecycle / Windows 路径 / fail closed

**验证目标**：snapshot context manager lifecycle 正确、`source_path.name` 跨平台稳定、所有失败路径 fail closed。

#### 3.1 Snapshot lifecycle

**直接证据**：

```python
# lines 992-1006
with source_repository.read_source_snapshot(
    "AAPL", document_id, SourceKind.FILING, materialize_files=False,
) as snapshot:
    assert snapshot.ticker == "AAPL"
    assert snapshot.document_id == document_id
    assert snapshot.source_kind is SourceKind.FILING
    descriptors = snapshot.files
    assert descriptors
    assert snapshot.primary_filename == source_path.name
    assert snapshot.primary_filename in tuple(
        descriptor.name for descriptor in descriptors
    )
```

- `SourceSnapshotProtocol.__enter__`（`repository_protocols.py:90-103`）：进入资源生命周期。
- `SourceSnapshotProtocol.__exit__`（`repository_protocols.py:105-125`）：返回 `Literal[False]`，不压制活动异常；正常退出时释放临时资源。
- `materialize_files=False`：light snapshot，不复制文件内容到临时树。
- 所有断言在 `with` 块内执行，`__exit__` 在块结束时自动调用，即使断言失败也执行。

**结论**：lifecycle 正确。✓

#### 3.2 Windows 路径

**直接证据**：

- `source_path = source_dir / "2024FY_AAPL_Annual_Report.htm"`（line 937）：`pathlib.Path / str` 运算符在 Windows 与 POSIX 均产生正确平台路径。
- `source_path.name`（line 1003）：`Path.name` 返回纯 basename（不含驱动器号或路径分隔符），Windows 上为 `"2024FY_AAPL_Annual_Report.htm"`，POSIX 同。
- `snapshot.primary_filename`（`repository_protocols.py:170-173`）：返回 `str`，来自 persisted meta `primary_document` 字段，不含路径分隔符。

**结论**：跨平台路径稳定。✓

#### 3.3 Fail closed

| 失败场景 | 触发条件 | 测试行为 | 行号 |
|---|---|---|---|
| `DAYU_R11_WINDOWS_ARTIFACT_DIR` 不存在 | `not artifact_root.is_dir()` | `raise AssertionError` | 101-104 |
| CLI generation 非零退出 | `generation.returncode != 0` | `AssertionError` | 966 |
| Oracle 检测到非唯一业务命令 | `len(body_lines) != 1 + 1 + len(...)` | `AssertionError` | 1109 |
| Oracle 检测到非 upload_filing 命令 | `business_argv[:4] != (...)` | `AssertionError` | 1115 |
| Oracle 检测到零/多条 --company-name | `len(company_name_indexes) != 1` | `AssertionError` | 1121 |
| Oracle 检测到错误 company-name 值 | `business_argv[...] != expected` | `AssertionError` | 1124 |
| cmd.exe 执行失败 | `execution.returncode != 0` | `AssertionError` | 981 |
| Company meta 未持久化 | `get_company_meta` → `FileNotFoundError` | 未捕获异常 → test error | 982 |
| Filing 未创建 | `list_source_document_ids` 返回 `[]` → `len == 1` | `AssertionError` | 990 |
| Filing 重复创建 | 返回 2+ → `len == 1` | `AssertionError` | 990 |
| Snapshot 不存在 | `read_source_snapshot` → `FileNotFoundError` | 未捕获异常 → test error | 992 |
| primary_filename 与 source 不匹配 | `snapshot.primary_filename != source_path.name` | `AssertionError` | 1003 |
| primary_filename 不在 descriptors 中 | `primary_filename not in descriptor_names` | `AssertionError` | 1004-1006 |
| Portfolio 无文件 | `rglob` 空 → `assert source_artifacts` | `AssertionError` | 1010 |

全部 14 个独立失败场景均为 fail closed（未捕获异常或 `AssertionError`）。无 `try/except` 吞错误、无 `pytest.skip` 降级、无 `warning` 替代。

**结论**：lifecycle 正确、路径跨平台稳定、失败 fail closed。**PASS**。

### 维度 4: Company-name oracle / schema

**验证目标**：company-name oracle 未从 storage/stdout/fallback 反推公司名，oracle schema 字段未增删。

#### 4.1 Company-name oracle

**直接证据**：

- `_assert_single_windows_upload_company_name`（lines 1086-1125）：
  - 输入：`script_path.read_bytes().decode("utf-8", errors="strict")`（line 1101）— 只读生成脚本 bytes。
  - 零 `execution.stdout` / `capsys` / `captured` 引用。
  - 零 storage / `FsCompanyMetaRepository` / `FmpCompanyInfoResolver` 引用。
  - 预期值来源：`_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."`（line 59）— 同一常量用于 generation argv（line 954）、pre-execution oracle（line 970）与 storage 断言（line 984）。
- Oracle 正/负测试覆盖（lines 499-562）：`test_windows_upload_company_oracle_fails_closed_on_non_business_evidence` 覆盖 4 正例 + 4 负例。

**结论**：company-name oracle 未漂移。✓

#### 4.2 Oracle schema

**直接证据**（lines 1011-1030）：

```python
{
    "test_node": "test_windows_generated_script_runs_real_cli_into_temp_storage",
    "result": "passed",
    "generated_script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
    "source_artifact_count": len(source_artifacts),
    "cmd_invocation": "cmd.exe /d /c",
    "company_name_supplied": company_name_supplied,
}
```

6 个字段未增删，未新增 display 字段。`company_name_supplied` 来自 oracle 函数返回值（line 967-970），不来自 storage 或 stdout。

**结论**：oracle schema 未漂移。**PASS**。

### 维度 5: Typing / tests / README / security / deferred

**验证目标**：类型正确、测试覆盖、README 触发、安全边界、deferred Issues。

#### 5.1 Imports

- `SourceKind`（`dayu.fins.domain.enums`，line 27）：`str, Enum`，public domain 类型。
- `FsCompanyMetaRepository`、`FsSourceDocumentRepository`（`dayu.fins.storage`，line 29）：public repository 实现类。
- 无 `hasattr` / `getattr` / `Any` / `object` 新增。
- 无 `dayu.engine` / `dayu.host` 导入。

#### 5.2 Docstring

- `test_windows_generated_script_runs_real_cli_into_temp_storage`（lines 913-927）：完整中文 docstring，覆盖 Args/Returns/Raises。
- `_assert_single_windows_upload_company_name`（lines 1086-1099）：完整中文 docstring。
- `_parse_windows_batch_fixed_argv`（lines 1128-1134）：完整中文 docstring。

#### 5.3 Typing

- `source_path: Path` — 由 `Path / str` 推断。
- `company_meta` — 由 `FsCompanyMetaRepository.get_company_meta() -> CompanyMeta` 推断。
- `source_repository` — 由 `FsSourceDocumentRepository(...)` 推断。
- `document_ids: list[str]` — 由 `list_source_document_ids() -> list[str]` 推断。
- `snapshot` — 由 `read_source_snapshot() -> SourceSnapshotProtocol` 推断。
- 无显式 `Any`、无 `# type: ignore`、无 `cast` 绕过。

#### 5.4 pyright / Ruff

- AgentCodex zero-change artifact 确认：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- AgentCodex zero-change artifact 确认：scoped Ruff → `All checks passed!`。
- Full Ruff baseline 142 项，canonical tuple JSON SHA-256 `bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3` 不变。

#### 5.5 README 触发

- `tests/` 修改触发 `tests/README.md` 检查。accepted plan §7 明确 `tests/README.md` 只属于 WIN4-S3 统一更新。WIN4-S1 不更新 README。✓ 符合 plan。
- 非 `dayu/engine/` / `dayu/host/` / `dayu/fins/` / `dayu/config/` 修改，不触发对应 README。✓

#### 5.6 Security / deferred

- 零新增 `os.environ` 读取（除既有 `_WINDOWS_ARTIFACT_DIR_ENV`）。
- 零新增 API key / secret / token 处理。
- 零新增 `FMP_API_KEY` 引用（只在既有 POSIX infer tests 中使用，非 S1 变更）。
- 零新增 `GITHUB_ACTIONS` / `GITHUB_RUN_ID` 引用。
- 零引用 Issue 142/151/175/177/178。
- 零引用 `web_tools_storage_states`。
- 零引入统一 authorization/secret infra。
- 无 `shell=True`、`errors=replace`、`capture_output=True`（production）新增。

**结论**：全部通过。**PASS**。

### 维度 6: 真实 Windows pending

**验证目标**：不把本地 skip 误报为 closure。

**直接证据**：

- `@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")`（line 911）— 非 Windows 平台干净跳过。
- 本机 macOS 按 marker skip，不计入 passed。
- Accepted plan §8 closure matrix 要求真实 Windows R11 4/4 + R12 9/9 + canary scan 全部通过才能关闭 WIN4-F01/F02/F03 和 AR-F07。
- Oracle artifact `result: "passed"`（line 1017）仅表示本地断言通过，不表示远程 Windows closure。

**结论**：不误报 closure。**PASS**。

## Controller 五项 no-action 裁决核对

本轮 re-review 必须明确核对 Controller 对 DS 五项 `NOT_A_CURRENT_CODE_FINDING / NO_ACTION` 观察的最终处置。

### 1. DS scope 表 artifact 路径引用错误

**Controller 裁决**：DS scope 表引用了先前 `win4-s1` implementation/controller artifacts，而本轮权威 evidence 是带 `real-windows-s1` 路径的 AgentCodex artifact 和 Controller validation。该引用错误不改变其已锁定 payload SHA、direct code 走读和 PASS 结论，但不得用于后续 evidence lineage。

**本轮核对**：DS review 文件名 `wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-ds.md` 内部 scope 行引用了 `wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md` 和 `wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`（缺少 `real-windows` 段），而本轮实际 evidence 文件路径包含 `real-windows-s1`。这是一个 artifact 引用路径错误，不影响 DS 已完成的 payload SHA 核验、逐行代码走读和 PASS 结论。Controller 裁决 `NO_ACTION` 正确。✓

### 2. Repository assertions 时序描述错误

**Controller 裁决**：DS Decision 中"repository 断言在 artifact upload 后执行"是文字错误。实际顺序是 `cmd.exe` exit → runner test 内 public repository/snapshot assertions → oracle 写入 → pytest 结束 → workflow 后续 artifact upload；本轮 plan 要求的"upload 前"成立。

**本轮核对**：按本 re-review 维度 2 逐行走读确认的实际顺序：

```
execution.returncode == 0 (line 981)
  → FsCompanyMetaRepository assertions (lines 982-984)
  → FsSourceDocumentRepository assertions (lines 985-1006)
  → rglob physical integrity (lines 1007-1010)
  → oracle artifact 写入 (lines 1011-1030)
```

所有 repository/snapshot 断言在 oracle artifact 写入之前执行。oracle artifact 写入在 pytest 结束之前执行。workflow artifact upload 在 pytest 结束之后执行。因此"upload 前"成立，DS 的"upload 后"描述确实是文字错误。Controller 裁决 `NO_ACTION` 正确。✓

### 3. 16-row 表计数不构成代码 finding

**Controller 裁决**：DS 称"15 个失败场景"，其表格实际列出 16 行。该计数错误不影响逐行 fail-closed 证据，不形成代码 fix。

**本轮核对**：DS review failure scenario 表（lines 456-473）逐行计数：

1. `DAYU_R11_WINDOWS_ARTIFACT_DIR` 指向不存在的目录
2. CLI generation 非零退出
3. Oracle 检测到零 business command
4. Oracle 检测到多条 business command
5. Oracle 检测到非 upload_filing 命令
6. Oracle 检测到零 --company-name
7. Oracle 检测到重复 --company-name
8. Oracle 检测到错误 company-name 值
9. cmd.exe 执行失败
10. Company meta 未持久化
11. Filing 未创建
12. Filing 重复创建
13. Snapshot 不存在
14. primary_filename 与 source 不匹配
15. primary_filename 不在 descriptors 中
16. Portfolio 无文件

实际 16 行，DS 文字称"15 个"。本 re-review 独立确认 16 行均为正确 fail-closed 场景，计数差异不影响任何代码判断。Controller 裁决 `NO_ACTION` 正确。✓

### 4. POSIX display 观察 out of scope

**Controller 裁决**：同文件 POSIX smoke 既有 `Fins succeeded` 展示断言与 `meta.json` 读取不在本次真实 Windows finding、accepted amendment 或 S1 allowlist 内；没有 current failure/Controller 裁决支持扩域。拒绝在本 slice 修改或创建新 WU/Issue。

**本轮核对**：POSIX real workflow test `test_posix_generated_script_runs_real_cli_into_temp_storage`（lines 792-848）仍使用 `assert execution.stdout.count("Fins succeeded") == 2`（line 842）和 `rglob("meta.json")` + `json.loads`（lines 843-848）。这不属于 S1 scope（plan §3.1 allowlist 未含 POSIX 测试修改），且 POSIX 测试无 current failure。Controller 裁决 `NO_ACTION` 正确。✓

### 5. Filelock 具体实现推测不作为 durable fact

**Controller 裁决**：Reviewer 关于 Windows filelock 底层实现的具体推测不成为 durable 产品事实；accepted contract 仅是 public repository 在支持平台的既有行为与 fresh R11/R12 最终 evidence。

**本轮核对**：DS review 提及 `filelock` 通过 `msvcrt` 或 `pywin32` 工作（DS review line 259）。这是对底层实现的推测，不是基于代码路径的直接证据。accepted contract 是 `SourceSnapshotProtocol` 的 public behavior（context manager lifecycle、typed properties），不依赖具体 filelock 实现。Controller 裁决 `NO_ACTION` 正确。✓

## Semantic ownership 审查

| 事实 | Owner | S1 变更 |
|---|---|---|
| "upload 是否成功" | Fins storage published state（`FsCompanyMetaRepository` + `FsSourceDocumentRepository`） | 从 stdout display grammar 迁移到 typed repository contract ✓ |
| "company name 是否传入" | Test-local oracle（`_assert_single_windows_upload_company_name`） | 不变 ✓ |
| "上传产生了哪些文件" | Fins storage published portfolio（`rglob` physical check） | 新增，仅 physical integrity ✓ |
| "filing 的 primary document 是什么" | `SourceSnapshotProtocol.primary_filename`（storage owner 从 persisted meta 投影） | 新增断言 ✓ |
| CLI renderer | `dayu/cli/upload_script.py`（未修改） | 不变 ✓ |
| Fins batch plan | `dayu/fins/upload_batch.py`（未修改） | 不变 ✓ |
| 缺 company-name fail closed | `dayu/fins/pipelines/upload_company_meta.py`（未修改） | 不变 ✓ |

无跨层 fallback、`hasattr`/`getattr`、loose parsing、兼容 shim 或测试固化。所有事实均从唯一 owner 读取。

## Findings

未发现实质性问题。

本轮 re-review 从零完整走读 payload 全部 1226 行、direct public Fins contracts、完整 initial review/adjudication/zero-change 链，逐行验证六个维度和 Controller 五项 no-action 裁决。未发现新的 correctness、semantic ownership、overdesign、security 或 contract 层面的 material finding，也未发现 initial review 结论需要回溯修正的 backflow finding。

## Open Questions

无。

## Residual Risk

1. **真实 Windows closure 仍 pending**：本机 macOS 无法执行 `cmd.exe` 分支。分类：`covered by later authorized closure gate`；owner/destination 是双路 re-review PASS 后由 Controller 按 amended plan §13.8 取得 fresh R11 与 R12 embedded-R11 evidence。本地 skip 与 review PASS 不能替代。

2. **Full Ruff baseline 142 项**：pre-existing baseline，本 slice 精确证明集合与 digest 不变，未新增/扩散/掩盖。

3. **POSIX real workflow test 仍有 display dependency**：`test_posix_generated_script_runs_real_cli_into_temp_storage`（line 842）仍使用 `assert execution.stdout.count("Fins succeeded") == 2`。不属于 S1 scope，但它是同一文件中剩余的唯一 display success dependency。后续若有直接 accepted finding，必须由其原 owner/范围单独裁决。

## Verdict

`PASS`。未发现新 findings，未发现 backflow findings。S1 immutable payload 实现正确删除了 display success dependency，改用 public repository contracts 验证上传成功事实，符合语义所有权原则。Controller 对 DS 五项 no-action 观察的裁决全部正确，无回流为代码修改。真实 Windows closure 仍 pending，等待 remote evidence。
