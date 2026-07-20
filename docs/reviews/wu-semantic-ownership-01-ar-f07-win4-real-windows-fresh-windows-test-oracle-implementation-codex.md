# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Implementation Evidence（AgentCodex）

## 1. Gate identity and result

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4-RW-RF01`；这是 umbrella 最后一个内部 remediation sub-WU，不是新 WU。
- Gate：accepted corrected plan 后的 one-test implementation。
- Accepted corrected-plan commit：`e2c9a31b25fb6d87e6fb4d618bb4043f556a55b0`。
- Mechanical implementation base / clean entry HEAD：
  `39926eb85aa25441f5209a128a3c971f451b5b25`。
- Branch：`phaseflow/host-issues-control`；不是 protected trunk。
- Frozen plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，`1124` lines / SHA-256
  `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。
- Gate result：
  `IMPLEMENTED / LOCAL_VALIDATION_PASS / REAL_WINDOWS_PENDING / STOPPED_AT_IMPLEMENTATION_GATE`。
- 本轮没有 stage、commit、push、workflow dispatch、Agent/reviewer dispatch、PR 操作或 code review。

## 2. First-principles and semantic-owner judgment

修复动机成立，严重性准确限定为 release-gate test-oracle blocker，不是 production upload、Docling 或 Fins storage defect。
fresh Windows evidence 已直接证明真实 upload exit `0`，public snapshot 同时发布 raw HTML 与 Docling JSON，而 Fins owner 合法选择
Docling JSON 为 primary。旧断言把 `snapshot.primary_filename` 强制等于 `source_path.name`，把两个不同 owner facts 错误合并。

唯一 correction owner 是
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot
assertion block：

- Fins-owned primary 只需按 exact `name` 在 public descriptors 中恰好命中一个；
- raw source publication 需独立以 exact source basename 唯一 descriptor 和 fixture bytes SHA-256 证明；
- 两个 descriptor 允许相同，也允许不同，测试不选择 expected primary。

public `SourceSnapshotFileDescriptor.name/sha256` 已完整表达所需事实，因此无需读取 raw meta/private path、物化文件、修改 Fins
contract、增加 helper/schema/oracle字段或建立 fallback。实现没有越过 owner boundary，也没有触发 diagnostic-first stop。

## 3. Exact implementation and diff identity

唯一代码修改是
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot
assertion block：

1. 删除 `snapshot.primary_filename == source_path.name`；
2. 从既有 `descriptors` 以 exact `descriptor.name == snapshot.primary_filename` 构造 primary matches，并断言长度精确为 `1`；
3. 独立以 exact `descriptor.name == source_path.name` 构造 raw-source matches，并断言长度精确为 `1`；
4. 对唯一 raw-source descriptor 显式断言 `sha256 is not None`，再精确等于
   `hashlib.sha256(fixture).hexdigest()`；
5. 没有断言 primary/raw 相等或不同，没有硬编码 Docling filename、suffix 或 expected primary；
6. 没有修改 imports、module constants、helpers、fixtures、其它 test nodes、物理 artifact count或
   `cli-grammar-oracle.json` key set。

代码 diff 为 `14 insertions / 3 deletions`。目标文件最终内容 SHA-256：
`3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110`。

相对 mechanical base 的 exact code diff SHA-256 为：
`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。
可复核命令为：

```bash
LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames \
  39926eb85aa25441f5209a128a3c971f451b5b25 -- \
  tests/cli/test_upload_filings_from_command.py | shasum -a 256
```

本 implementation 另只新增本文：
`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-codex.md`。

## 4. Fresh tests and platform result

所有 Python 命令均先执行 `source .venv/bin/activate`。

| Validation | Result | Count / note |
| --- | --- | --- |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | PASS | `20 passed, 2 skipped, 3 warnings`；`12.35s` |
| POSIX real smoke exact node | PASS | `1 passed, 3 warnings`；`11.95s` |
| 三个 public repository owner nodes | PASS | `3 passed, 3 warnings`；`1.06s` |
| target Windows exact node（本地 macOS） | PLATFORM SKIP | `1 skipped, 3 warnings`；`1.05s`；`requires real cmd.exe` |
| plan aggregate test set | PASS | `262 passed, 2 skipped, 3 warnings`；`36.59s` |
| `pytest tests/cli -q` | PASS | `552 passed, 7 skipped, 3 warnings`；`39.00s` |

三个 public repository owner nodes精确为：

- `tests/fins/test_fins_storage_atomicity.py::test_company_owner_reads_only_published_meta_inventory_and_aliases`；
- `tests/fins/test_fins_storage_provider.py::test_storage_repositories_list_and_read_fixture_documents`；
- `tests/fins/test_fins_storage_provider.py::test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision`。

aggregate 首次运行的工具输出流没有保留 pytest 最终 summary，因此未把该次运行计为验收证据；fresh 串行重跑取得上表
`262 passed, 2 skipped` 与 exit `0`。三个 warning 均来自已安装 `edgar` package 的 deprecated imports，本轮未修改相关代码。

本机是 macOS / `os.name != "nt"`。Windows exact node 的 skip 只记录平台事实，不作为真实 Windows closure，也不替代后续 fresh
R11 与 R12 embedded-R11。

## 5. Type, lint and coverage decision

- Full pyright：`python -m pyright dayu/ tests/ utils/` ->
  `0 errors, 0 warnings, 0 informations`。
- Ruff version：entry 与 final 均为 `ruff 0.15.11`。
- Scoped Ruff：`python -m ruff check tests/cli/test_upload_filings_from_command.py` -> `All checks passed!`。
- Entry full Ruff：`142` 项；按
  `(filename, location row/column, code, message, fix-applicability)` 排序后的 canonical JSON SHA-256 为
  `a11d2c84c95ddb84e8313316afb98ed81124bf18cf98a2beecb17d3d2a8ac0c9`。
- Final full Ruff：同为 `142` 项、同一 canonical SHA-256；新增、扩散、移动或顺手清理为 `0`。
- Coverage：N/A。本 correction 没有 production Python diff，不产生 production line/branch coverage分母，也没有增加 coverage
  helper；行为由 target file、POSIX smoke、public repository owner nodes与 aggregate regression fresh 验证。

## 6. Diff, allowlist and forbidden scans

- `git diff --check`：PASS。
- 相对 mechanical base 的 tracked changed paths只有 target test；新增本文后 worktree exact path allowlist为 target test与本文。
- `git diff --cached --name-only`：空；staged tree empty。
- function-level diff只有 target function内 `snapshot.files` 取得后的现有 assertion block；imports、helper区、其它 test函数和 oracle
  JSON block均零 diff。
- `dayu/` product、其它 tests、全部 README/design/control、`.github/workflows/` 相对 mechanical base零 diff。
- 新增 `rglob` scan：`0` matches；既有 snapshot block之后的 physical `rglob` 没有被修改，仍只承担 artifact integrity。
- raw/private scan：`source_meta`、`meta.json`、`private`、`_core`、`materialize_files=True`、`get_source(` 新增均为
  `0` matches。
- Docling hardcode scan：`docling`、`_docling.json`、`DOCLING_FILE_SUFFIX` 新增均为 `0` matches。
- primary==raw scan：新增 primary/source-path 等式为 `0` matches。
- import/helper/class/oracle-field scan：新增 import、`def`、`class`、string-key字段均为 `0` matches。
- display/stream oracle scan：新增 `Fins result/summary/progress/...` 与 `execution.stdout/stderr` 为 `0` matches。
- fallback/弱类型补偿 scan：新增 `fallback`、`hasattr(`、`getattr(` 为 `0` matches。
- corrected plan旧错误措辞 scan：`0` matches。

新增断言只消费 public descriptor `name/sha256`；primary exact membership与 raw-source exact name/hash在源码中是两个独立 tuple、
两个独立 exact-one断言。现有 oracle JSON字段集合没有 diff。

## 7. README, security and deferred boundary

已核对 `tests/README.md` 的 `README 更新边界`：只在新增测试层级、测试运行方式或测试维护规则变化时更新。本 correction只修改
既有真实 Windows node 的内部 public-contract assertion，不改变这些职责，因此 `tests/README.md` 为
`NO UPDATE REQUIRED`。根 README、Fins README、分层 README与 design同样无用户工作流、public contract、分层或装配触发项；
全部保持零 diff。

本轮不读取、迁移、重写或扩大 trusted-local secret范围，不读取 GitHub Secrets/configured production values，也不派生或扫描
run-specific canary。Issue 142/151/175/177/178、Web/WeChat/render、console/PTY/process isolation、setx redesign、统一
authorization/secret management与 Fins generic diagnostic schema全部保持 deferred/forbidden，没有实现或预埋。

## 8. Residual risks and completion boundary

- Blocking open questions：`0`。
- Residual risk 1：macOS不能执行真实 `cmd.exe`。分类：`covered by later approved remote validation`；唯一 destination是本 exact
  implementation完成 Controller validation、code review/re-review、accepted implementation与 aggregate gates后，由 Controller
  按 plan §13.8取得 fresh R11 与 R12 embedded-R11 evidence。
- Residual risk 2：若 fresh R11/R12 的 primary membership或 raw-source exact name/hash失败。分类：
  `covered by diagnostic-first stop gate`；必须回 Controller取证，不得恢复 primary==raw、硬编码 Docling expected primary、读取
  private meta/path或修改 Fins contract迁就测试。
- Residual risk 3：full Ruff `142` 项。分类：`pre-existing immutable baseline / outside current slice`；本轮精确证明五元组集合与
  digest不变。

当前没有 accepted implementation commit、fresh dispatch-returned run id、same-run canary证据或 remote closure；remote状态仍为
`PENDING`，不能在本 implementation gate误报关闭。本地 one-test implementation与授权验证已完成，本文停止在 implementation
gate；下一 entry point是 Controller validation后进入独立 code review，本轮不自行进入。
