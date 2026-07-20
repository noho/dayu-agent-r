# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S1 Code Review（AgentMiMo 第一路）

## Result

`PASS / NO_MATERIAL_FINDINGS / REAL_WINDOWS_PENDING`

## Scope

- Mode: current changes（AR-F07 WIN4-RW-S1 payload review）
- Branch: `phaseflow/host-issues-control`
- Base: clean implementation entry `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-mimo.md`
- Payload: `tests/cli/test_upload_filings_from_command.py`（content SHA-256 `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d`）
- Payload diff（entry vs prior remediation）: 44 insertions / 3 deletions
- Parallel review coverage: 无

## 审查依据

- AGENTS.md（129 行，完整读取）
- Accepted amended-plan commit `cb2785d9b847e852249d05850c0550c5bcea5467`
- Accepted plan file 1060 行，SHA-256 `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`
- S1 postcommit authorization `8fafe9ba`
- AgentCodex implementation artifact SHA-256 `b12e3489819482b3815bfd6056ce2bbaba66827774405440c42a221b77ca6180`
- Controller validation SHA-256 `2c326a9b4fb1fab49fe5acb96c197f68caa10731ceef9ec67676224703d0bc9e`
- Direct Fins public repository/snapshot contracts:
  - `dayu/fins/storage/repository_protocols.py`（`SourceSnapshotProtocol`、`SourceSnapshotFileDescriptor`、`CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol`）
  - `dayu/fins/storage/__init__.py`（public exports）
  - `dayu/fins/domain/enums.py`（`SourceKind`）
  - `dayu/fins/domain/document_models.py`（`CompanyMeta` 等）

## Findings

未发现实质性问题。

以下逐项说明审查结论：

### 1. Display success dependency 彻底删除

**直接证据**：S1 diff 删除 `assert "Fins result" in execution.stdout`（line 879 旧版本）。

**当前代码验证**：
- `execution.stdout` 在 `test_windows_generated_script_runs_real_cli_into_temp_storage` 中零引用。
- `execution.stderr` 仅在 line 981 `assert execution.returncode == 0, execution.stderr` 中使用，作为 return-code 断言失败时的既有诊断值，不参与成功判断。
- 没有 stderr/stdout display 文案、prefix、substring、regex 或 parser 替代判断。
- 成功断言完全依赖 exit code + public repository facts。

**结论**：display dependency 已彻底清除，无替代泄漏。

### 2. Public repository 构造与断言正确性

**直接证据**：lines 982-1006。

- `FsCompanyMetaRepository(storage)` 与 `FsSourceDocumentRepository(storage)` 是 `dayu.fins.storage` 公开导出的具体实现，构造参数为 `Path`。
- Company facts：`get_company_meta("AAPL")` 返回 `CompanyMeta`，断言 exact ticker `"AAPL"` 与 company name `_WINDOWS_REAL_SMOKE_COMPANY_NAME`（`"Apple Inc."`）。
- Source inventory：`list_source_document_ids("AAPL", SourceKind.FILING)` 返回 list，`len == 1` 断言唯一性。
- Snapshot：`read_source_snapshot("AAPL", document_id, SourceKind.FILING, materialize_files=False)` 作为 context manager 进入，`with` 块内断言 `snapshot.ticker`、`snapshot.document_id`、`snapshot.source_kind is SourceKind.FILING`、`snapshot.files` 非空、`snapshot.primary_filename == source_path.name`、primary filename 在 descriptor names 中。
- 所有断言在 `with` 块内执行，snapshot 资源生命周期正确。
- `rglob("*")` 仅在 repository facts 之后计算 physical artifact count（line 1007-1010），不含业务语义。
- Oracle schema 字段集合未变化（`test_node`、`result`、`generated_script_sha256`、`source_artifact_count`、`cmd_invocation`、`company_name_supplied`），未新增 display 字段。

**结论**：public repository 构造正确，断言覆盖 identity/ticker/company/唯一 id/SourceKind/primary filename/descriptors，不读 raw/private/downloaded artifact。

### 3. rglob/oracle schema 与 company-name oracle

**直接证据**：lines 1007-1010, 1086-1125。

- `rglob` 仅断言非空，验证 physical artifact 存在性，不解析内容或派生业务语义。
- Oracle schema 6 个字段未增删，未新增 display 字段。
- `_assert_single_windows_upload_company_name` 独立解析 batch 脚本 CRLF 结构、header oracle、唯一业务命令、`--company-name` token 值，不依赖 renderer 内部 helper。
- `_WINDOWS_REAL_SMOKE_COMPANY_NAME = "Apple Inc."` 常量未改变。

**结论**：rglob 仅做 physical integrity，company-name oracle 未漂移。

### 4. Windows/POSIX 路径与 repository lifecycle

**直接证据**：lines 929-970, 992-1006。

- `source_path = source_dir / "2024FY_AAPL_Annual_Report.htm"` 使用 `pathlib.Path`。
- `snapshot.primary_filename == source_path.name`：`Path.name` 返回纯 basename，Windows/POSIX 均正确。
- `read_source_snapshot` 的 `ticker`、`document_id`、`source_kind` 参数均为 Python 字符串/枚举，不涉及路径分隔符。
- `materialize_files=False` 避免不必要的临时文件物化，snapshot context manager 在 `with` 块结束时清理。
- `_windows_test_artifact_directory` 在配置了 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 时使用确定性目录，否则回退 `tmp_path`；`shutil.rmtree` + `mkdir` 确保干净状态。
- 真实 `cmd.exe` 执行通过 `subprocess.run` 调用，失败时 `returncode != 0` 触发 assert，fail closed。

**结论**：路径处理正确，repository lifecycle 在 `with` 块内闭合，失败 fail closed。

### 5. Imports/docstring/typing/pyright/README/security

**直接证据**：lines 1-36, 912-927。

- 新增 imports：`SourceKind`（`dayu.fins.domain.enums`）、`FsCompanyMetaRepository`、`FsSourceDocumentRepository`（`dayu.fins.storage`），均为 public contract。
- `test_windows_generated_script_runs_real_cli_into_temp_storage` docstring 包含完整 Args/Returns/Raises。
- `_assert_single_windows_upload_company_name` 和 `_parse_windows_batch_fixed_argv` 均有完整中文 docstring。
- Controller validation 确认 full pyright `0 errors, 0 warnings, 0 informations`。
- Controller validation 确认 scoped Ruff `All checks passed!`。
- `tests/README.md` 只覆盖测试层级/运行方式/维护规则，S1 未改变这些读者契约，`NO UPDATE REQUIRED` 正确。
- 不读取/派生/回显 run-specific canary，不读取 GitHub Secrets，不新增统一 authorization/secret infrastructure。
- 无过度设计/耦合/fallback。

**结论**：全部通过。

### 6. Windows pending 与 Issue 约束

**直接证据**：lines 911, 929-931。

- `@pytest.mark.skipif(os.name != "nt", reason="requires real cmd.exe")` 正确标记平台依赖。
- 本机 macOS 按 marker skip，不误报 closure。
- 未引入统一 authorization/secret infra。
- 未实施 Issue 142/151/175/177/178。

**结论**：Windows pending 由平台 marker 正确表达，不误报。

## Open Questions

无。

## Residual Risk

1. **真实 Windows closure 仍 pending**：本机 macOS 无法执行 `cmd.exe` 分支。分类：`covered by later authorized closure gate`；owner/destination 是双路 code review accepted 后由 Controller 按 amended plan §13.8 取得 fresh R11 与 R12 embedded-R11 evidence。

2. **Full Ruff baseline 142 项**：pre-existing baseline，本 slice 精确证明集合与 digest 不变，未新增/扩散/掩盖。

## Verdict

`PASS`。未发现 material findings。WIN4-RW-S1 payload 实现正确删除了 display success dependency，改用 public repository contracts 验证上传成功事实，符合语义所有权原则。真实 Windows closure 仍 pending，等待 remote evidence。
