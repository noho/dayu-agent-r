# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S1 Implementation Evidence（AgentCodex）

## 1. Gate identity and status

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4-RW-S1`；不是新 WU。
- Gate：accepted amended plan 后的 `WIN4-RW-S1 implementation`。
- Accepted amended-plan commit：`cb2785d9b847e852249d05850c0550c5bcea5467`。
- Clean implementation entry / current HEAD：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Branch：`phaseflow/host-issues-control`；非 protected trunk。
- Accepted plan file：完整 `1060` 行；working-tree SHA-256 为
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`，与 Controller
  postcommit authorization 记录一致。
- Gate result：`IMPLEMENTED / LOCAL_VALIDATION_PASS / REAL_WINDOWS_PENDING / STOPPED_AT_S1_IMPLEMENTATION`。
- 本轮未 stage、commit、push、dispatch、操作 PR 或进入 S2/review gate。

## 2. First-principles and semantic-owner judgment

动机成立，严重性是 release-gate/test contract blocker，不是 production upload defect。直接证据是原测试在真实
`cmd.exe` 执行已经 `returncode == 0` 后，才因旧 `Fins result` 展示字面量失败；展示 grammar 不是上传成功事实的
owner，真实上传 smoke 不应把 CLI prefix 当业务成功真源。

业务成功事实的唯一 owner 已确认是 `dayu.fins.storage` 的 public repository contract：

- `FsCompanyMetaRepository.get_company_meta()` 负责 published company facts；
- `FsSourceDocumentRepository.list_source_document_ids()` 负责 published source inventory；
- `FsSourceDocumentRepository.read_source_snapshot()` 与 `SourceSnapshotProtocol` 负责同一 published revision 内的 exact
  identity、typed source kind、primary filename 与完整 file descriptors。

这些 public contracts 能直接表达 S1 要求的全部事实。实现不需要 raw JSON、private core、download artifact replay、
CLI output parsing、production Fins 修改或下游 fallback，因此未触发 stop condition。修复位于测试消费边界，不改变
Fins owner，也不是 compatibility/test fallback。

## 3. Changed paths and exact implementation

Product/test payload path 只有：

- `tests/cli/test_upload_filings_from_command.py`
  - 删除真实 Windows smoke 的旧 `Fins result` display assertion；没有替换为其它 stdout/stderr 文案、prefix、
    substring、regex 或 parser success 判断。
  - 保留 generation/process exit `0` 断言与 `_assert_single_windows_upload_company_name()` pre-execution oracle；
    `execution.stderr` 只继续作为 return-code 断言失败时的既有诊断值。
  - runner test 进程在 oracle artifact 写入前构造 public `FsCompanyMetaRepository(storage)` 与
    `FsSourceDocumentRepository(storage)`。
  - exact 断言 company ticker `AAPL`、company name `Apple Inc.`，以及 `SourceKind.FILING` 下唯一一个 published
    document id。
  - 使用 `with source_repository.read_source_snapshot("AAPL", document_id, SourceKind.FILING,
    materialize_files=False) as snapshot:`；仅在 `with` 内读取并断言 exact ticker、document id、typed source kind、
    primary filename 等于本次 source basename、descriptor 集合非空且包含 primary。
  - `source_artifacts = ...rglob(...)` 及非空断言只保留 physical integrity 意义；既有 oracle schema 字段
    `test_node`、`result`、`generated_script_sha256`、`source_artifact_count`、`cmd_invocation`、
    `company_name_supplied` 未增删，未新增 display 字段。
  - 增加 public enum/repository imports；受影响 test function 改为包含参数、返回值与异常说明的完整中文 docstring。

Implementation evidence path 只有：

- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-implementation-codex.md`

Payload file 最终内容 SHA-256：
`71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d`。

## 4. Fresh tests and counts

所有 Python 命令均先执行 `source .venv/bin/activate`。

| Validation | Result | Count / note |
| --- | --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | PASS | `20 passed, 2 skipped, 3 warnings`；`11.94s` |
| POSIX focused real smoke | PASS | `1 passed, 3 warnings`；`11.36s` |
| affected public repository owner nodes | PASS | `3 passed, 3 warnings`；`1.02s` |
| real Windows focused node on local macOS | PLATFORM SKIP | `1 skipped, 3 warnings`；`1.01s` |

Affected owner nodes：

- `tests/fins/test_fins_storage_atomicity.py::test_company_owner_reads_only_published_meta_inventory_and_aliases`
- `tests/fins/test_fins_storage_provider.py::test_storage_repositories_list_and_read_fixture_documents`
- `tests/fins/test_fins_storage_provider.py::test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision`

本机是 macOS / `os.name != "nt"`，真实 Windows node 按既有 marker skip。该结果只记录平台事实，不作为真实 Windows
closure，也不替代后续 fresh R11 / R12 embedded-R11 evidence。

三个 warning 都来自已安装 `edgar` package 的 deprecated import；本 slice 未新增或修改相关代码。

## 5. Coverage, type and lint

- Coverage：`N/A for WIN4-RW-S1 production target`。本 slice 零 production diff；accepted plan §13.6.3 的
  `dayu.cli.commands.init` `>=80%` production coverage target 属于未授权的 WIN4-RW-S2。本 slice 不运行旧记录、
  不以测试文件 coverage 冒充 production coverage；适用行为由 target file、POSIX real smoke 与三个 public repository
  owner nodes fresh 通过证明。
- Full pyright：`python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：`python -m ruff check dayu/cli/commands/init.py tests/cli/test_init_command.py
  tests/cli/test_upload_filings_from_command.py` -> `All checks passed!`。
- Full Ruff version：`ruff 0.15.11`。
- Entry full Ruff baseline：`142` 项；按
  `(filename, location row/column, code, message, fix-applicability)` 排序后的 canonical JSON SHA-256 为
  `bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3`。
- Final payload tree full Ruff：同为 `142` 项、同一 SHA-256；新增或扩散 `0`。既有 baseline 未被本 slice 顺手修改。

## 6. README decision

已完整读取 `tests/README.md` 全部 `338` 行，包括 `README 更新边界`：该文件只在测试层级、测试运行方式或测试维护
规则变化时同步。S1 只迁移一个既有真实 Windows node 的内部 success oracle，既未新增测试层级、命令或 workflow，
也未改变维护规则；现有 README 已说明该 node 经过 CLI→Service→Fins→temp storage 闭环。因此本 slice 对
`tests/README.md` 的职责判断是 `NO UPDATE REQUIRED`。

根 README、Fins README、分层 README 与 design/control docs 同样无触发：没有 production contract、用户可见 grammar、
工作流、分层或装配变化。README diff 为零。

## 7. Diff, allowlist and propagation scans

- `git diff --check`：PASS。
- 相对 clean entry 的 payload diff numstat：`44 insertions / 3 deletions`，只命中
  `tests/cli/test_upload_filings_from_command.py`；另新增本 implementation evidence。
- Added-line display/stream scan：`0` matches。
- Windows real smoke AST scan：`execution.stdout` references `0`；`execution.stderr` references `1`，且仅作为
  `execution.returncode == 0` 的失败诊断，不参与成功判断。另一个 generation stderr reference同样只服务 generation
  return-code 断言。
- 旧字面量 `Fins result` 在 target test file：`0` matches。
- Oracle schema：字段集合未变化；新增 display 字段 `0`。
- `.github/workflows/`、全部 `dayu/fins/` production、`dayu/cli/output.py`、
  `dayu/cli/init_environment.py`、S2 的 `dayu/cli/commands/init.py` / `tests/cli/test_init_command.py`、
  `tests/cli/test_init_smoke.py`、`README.md` 与 `tests/README.md`：相对 clean entry diff path count `0`。
- `git diff --cached --name-only`：空；staged tree empty。

本轮没有读取、派生或回显 run-specific canary；没有读取 GitHub Secrets 或 configured production values。

## 8. Open questions and residual risks

- Blocking open questions：`0`。
- Residual risk 1：本地 macOS 无法执行真实 `cmd.exe` 分支。分类：`covered by later authorized closure gate`；owner /
  destination 是两 slice accepted 后由 Controller 按 amended plan §13.8 取得 fresh R11 与 R12 embedded-R11 evidence。
- Residual risk 2：full Ruff 存在 `142` 项 entry baseline。分类：`pre-existing baseline / outside current slice`；本 slice
  精确证明集合与 digest 不变，未新增、扩散或掩盖。
- Diagnostic-first stop：未触发。若后续 fresh Windows run 的 exit/storage owner facts失败，必须回 Controller 重新取证，
  不得恢复 display parsing或把新失败归入当前 root cause。

## 9. Completion boundary

`WIN4-RW-S1` 的本地 implementation 与授权验证已完成；真实 Windows closure 仍 pending。本 artifact 明确停止在当前
implementation gate，不提交、不 dispatch、不进入 WIN4-RW-S2、aggregate、remote closure 或 PR review。
