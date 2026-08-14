# WU Upload Filing Ticker Alias Contract — S2 Implementation

## 1. Gate 与边界

- Gate：accepted plan 的 S2 implementation。
- 基线：`c5446b770d238aafd8c42552dadbe132cba94ad2`。
- 实施前状态：工作树 clean，HEAD 等于指定基线。
- 已完整读取并约束实施：根 `AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`、accepted plan、两轮 plan review/fix/re-review/controller adjudication、S1 implementation/fix/re-review/controller adjudication，以及根 README、`dayu/fins/README.md`、`tests/README.md` 的更新约束。
- 本次未执行：UF-PF05 真实 CLI evidence、oracle/scenario registry、冻结 evidence、其它 finding、PR、push、commit、implementation review。

## 2. 动机与 root cause 复核

直接代码与 durable data-flow 证据确认 S2 动机成立：S1 的 `UploadCompanyMetaDecision` 仍 stage prevalidation 时点的 final `CompanyMeta`；storage commit 未在 workspace identity 串行化边界重读 authoritative meta；published alias index 仍是 `dict[str, list[str]]` 并在 read 末端才发现多 owner；read runtime 仍构造候选与 fallback。该组合允许同 canonical 并发更新覆盖 aliases，也允许不同 canonical 在 durable publication 后才暴露 alias 歧义。

语义 owner 按 accepted plan 收束为：

- ticker grammar、canonicalization、market/exchange 与 stable dedupe：既有 `CompanyTickerIdentity` builder。
- CompanyMeta optimistic precondition、commit intent 与 authoritative pure merge：新增 `dayu/fins/domain/company_meta_contract.py`。
- published corpus canonical：storage identity descriptor。
- accepted aliases：strict-valid published `CompanyMeta`。
- workspace 单值唯一 projection、锁序、recovery 与 commit-before-swap validation：filesystem storage core。
- incoming conflict / durable corruption：storage typed exceptions。
- upload terminal reason：既有 `dayu/fins/upload_failure.py`。
- read-side actionable projection：既有 read error contract 与 `FinsReadRuntime`。

没有新增 durable alias registry、cache、journal/schema 字段或下游补偿。

## 3. 实现结果

### 3.1 CompanyMeta intent 与 authoritative merge

新增不可变契约：

- `CompanyMetaNonIdentitySnapshot(company_id, company_name, resolver_version, updated_at)`；
- `CompanyMetaCommitIntent(proposed_identity, merge_mode, expected_non_identity, proposed_company_id, proposed_company_name, resolver_version)`；
- `CompanyMetaConcurrentUpdateError`；
- `build_company_meta_commit_intent(...)`；
- `merge_company_meta_for_commit(...)`。

pure merge 只以 commit-time `current_published` 为 alias union 与非身份事实真源：`preserve_published` 保留 current 非身份字段；`refresh_if_stale` 仅在 exact optimistic snapshot 未变化时刷新，current 已被同 resolver version 刷新时保留较新的 authoritative facts并合并 aliases，meta 消失或仍为其它 stale version 时 typed 拒绝。`updated_at` 只在真实 mutation 时使用 storage 提供的单次 commit 时点。

upload decision、SEC download producer、CN/HK download producer均只 stage intent，不再向 storage stage final CompanyMeta。`CompanyMetaRepositoryProtocol.upsert_company_meta(...)` 已删除，替换为 `stage_company_meta_intent(...)`。

### 3.2 Producer data flow

material alias data flow 未被删除或旁路：

```text
FinsUploadMaterialRequest.ticker_aliases
  -> service_runtime.py:240 / :260
  -> sec_upload_workflow.py:494 或 cn_pipeline.py:1102
  -> stage_company_meta_for_upload(...)
  -> resolve_upload_company_meta_decision(...)
  -> CompanyMetaCommitIntent
  -> CompanyMetaRepositoryProtocol.stage_company_meta_intent(...)
  -> storage commit-time authoritative merge
```

filing 继续消费 fresh validated request 中的同一个 `company_meta_decision`，最终也 stage 相同 intent 类型。SEC/CN material create/update 均在 source document publication 前提交其 CompanyMeta batch；alias conflict 不会留下 material document publication。

### 3.3 Workspace identity lock、recovery 与原子 publication

`_ActiveBatchState` 新增：

- `company_meta_intent`；
- `publishes_new_corpus`，由 `begin_batch` 在 same-ticker writer 持有期间冻结。

commit 路径固定为：

```text
identity-changing / first corpus publication:
writer -> recovery -> recovery sweep -> workspace identity -> sorted publication scans -> target publication

existing corpus document-only commit:
writer -> target publication

alias read:
workspace identity -> sorted publication scans

recovery physical mutation:
recovery -> nonblocking writer -> workspace identity -> publication
```

首次 meta-less descriptor publication 也进入 identity-changing 路径。storage 在 target backup/swap 前：

1. strict 读取 staged descriptor；
2. 在 incoming publication guard 下重读 authoritative current meta；
3. 机械调用 pure merge 并将 final meta 写入 staging；
4. 扫描全部 actual published ticker directories；
5. 从 descriptor canonicals 与 valid CompanyMeta accepted aliases 构造 `dict[str, str]`；
6. 拒绝 durable duplicate 或 incoming canonical/alias conflict；
7. 仅在全部验证通过后执行 target backup/swap/`COMMITTED`。

recovery 在 physical restore/delete/swap 前取得 workspace identity guard。读取、commit 与 recovery 的锁释放保留最早主异常；后续 release failure 仅附加 note，成功路径上的 release failure 仍作为主异常抛出。

### 3.4 Canonical/alias 唯一 route 与 corruption 分类

删除：

- `resolve_existing_ticker(...)`；
- `_resolve_existing_ticker_by_company_alias(...)`；
- `_build_company_alias_index(...)`；
- `_build_company_alias_index_from_meta(...)`；
- read runtime 的 normalize/upper fallback。

新增唯一 public route `resolve_company_ticker(ticker: str) -> str | None`。route 与 commit 共用 `_scan_actual_published_company_identities()` 和 `_build_unique_company_identity_index()`：

- descriptor canonical 无条件拥有 canonical lookup；
- `meta.json` 缺失是合法 canonical-only corpus，不贡献 alias；
- 只有 strict-valid 且与 descriptor identity 一致的 CompanyMeta 才贡献 accepted aliases；
- canonical 或任一 accepted alias 都返回 descriptor-owned canonical corpus。

`CompanyTickerIdentityCorruptionKind` 为 closed set：

- `invalid_descriptor`；
- `invalid_meta`；
- `identity_mismatch`；
- `duplicate_owner`。

authoritative scan 对 portfolio root、ticker directory、descriptor 与 meta 使用显式 `os.lstat` 分类：仅 `ENOENT` 作为缺失；symlink/non-regular/schema/namespace/locator/canonical 错误进入对应 typed corruption；permission 与普通 I/O 原样保留为 storage failure，不被 `Path.exists()` / `Path.is_file()` 抹平成 corruption。点号私有运维目录不属于 actual ticker corpus；真实 ticker directory 缺少 descriptor 仍 fail closed 为 `invalid_descriptor`。

### 3.5 Failure 与 LLM-facing projection

- incoming conflict：`CompanyTickerAliasConflictError(alias, existing_canonical_ticker, incoming_canonical_ticker)`；构造器只接受 normalized 非空 business values。
- durable corruption：`CompanyTickerIdentityCorruptionError(kind, lookup_ticker)`，不携 filesystem locator。
- upload failure owner 新增 `storage/ticker_alias_conflict`，文案固定、path-free、可行动；corruption 与 concurrent update 映射为既有 `storage/storage_io`，不归责于用户 alias。
- `upload_tools.py` 在宽泛 `except ValueError` 前显式捕获 typed corruption，避免把 workspace 损坏误报为参数错误。
- read runtime 只调用 `resolve_company_ticker(raw ticker)`；corruption 映射 `workspace_identity_corrupted`，锁/权限/I/O 映射 `storage_unavailable`，`None` 才映射 `NOT_FOUND`。
- 九个 read tools 共用的 ticker schema 说明“工作区已接收的主代码或别名会查询同一家公司归档”，不暴露 lock/index/intent/descriptor 等内部术语。

## 4. Tests

新增 owner 与 storage contract tests：

- pure merge：preserve、无 mutation 更新时间、create/meta-less supplement、exact refresh、同 resolver 并发 refresh、meta disappearance、different stale version、非法 intent 组合；
- first meta-less publication 的 recovery/identity/publication 锁序；
- `V.BA -> V-BA`、canonical-equivalent query、US/CN/HK 语法变体与跨市场 alias；
- `DELTA` / `MSFT` canonical-alias 冲突、冲突前无 target publication；
- 两个独立 repository core barrier 并发首发同 alias，恰一成功、一 typed conflict；
- commit-time authoritative reload 保留同 resolver 较新事实与 aliases；
- meta disappearance 在 swap 前 typed 拒绝且 published tree byte-for-byte 不变；
- meta-less canonical-only route与后续补 meta；
- descriptor missing/malformed/symlink、malformed meta、identity mismatch、durable duplicate owner；
- descriptor file 与 ticker directory permission failure 保持 I/O 类别；
- upload conflict/corruption distinct mapper 与 JSON round-trip；
- `list_documents` canonical 与 accepted alias 返回 exact same result；
- read corruption actionable error；
- upload tool typed corruption 不被 `except ValueError` 吞掉。

既有 tests/fakes 已随 owner boundary 迁移到 real commit intent helper，不保留 production compatibility shim。

## 5. README decision

- 根 `README.md`：已更新。只增加直接 filing/material 与批量脚本的用户可见主代码/别名输入、同归档查询与冲突拒绝行为。
- `dayu/fins/README.md`：已更新。记录 descriptor canonical + valid CompanyMeta aliases 的 owner 分解、meta-less、唯一 route、intent merge、固定锁序、recovery 与 typed failures；同时修正 FMP result 当前接口。
- `tests/README.md`：已读取更新约束；本次只增加同层测试与 fixture helper，不改变测试入口、分层或运行方式，因此不更新。
- `dayu/README.md`：本次不改变 UI/Service/Host/Engine 分层或装配边界，因此不触发。

## 6. Validation evidence

环境均为 `source .venv/bin/activate` 后执行。

### 6.1 Focused tests

```text
pytest -q tests/fins/test_company_meta_contract.py \
  tests/fins/test_company_identity_storage_contract.py \
  tests/fins/test_fins_ingestion_tools.py::test_upload_tool_does_not_swallow_typed_corruption_as_invalid_argument \
  tests/fins/test_fins_storage_provider.py::test_list_documents_canonical_and_accepted_alias_route_same_corpus \
  tests/fins/test_fins_storage_provider.py::test_list_documents_projects_descriptor_corruption_as_actionable_business_error

27 passed
```

storage atomicity + identity contract 独立回归：`166 passed`。

### 6.2 Full relevant tests

```text
coverage run --branch -m pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py

1574 passed, 1 skipped
```

skip 为既有环境条件 skip；三条 warning 均来自 `edgar` dependency deprecation。

### 6.3 Per-production-file branch-mode coverage

`coverage report` 在 `--branch` 数据下的逐文件结果：

| Production file | Cover |
|---|---:|
| `dayu/fins/domain/company_meta_contract.py` | 91% |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 85% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 91% |
| `dayu/fins/pipelines/sec_company_meta.py` | 91% |
| `dayu/fins/pipelines/upload_company_meta.py` | 97% |
| `dayu/fins/storage/__init__.py` | 100% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 83% |
| `dayu/fins/storage/_fs_storage_infra.py` | 83% |
| `dayu/fins/storage/fs_company_meta_repository.py` | 100% |
| `dayu/fins/storage/repository_protocols.py` | 96% |
| `dayu/fins/tools/error_contract.py` | 100% |
| `dayu/fins/tools/fins_tools.py` | 83% |
| `dayu/fins/tools/read_runtime.py` | 82% |
| `dayu/fins/tools/upload_tools.py` | 91% |
| `dayu/fins/upload_failure.py` | 93% |

全部修改生产文件均不低于 80%。

### 6.4 Type、format、residue 与 diff

- `pyright`：`0 errors, 0 warnings, 0 informations`。
- 修改 Python 文件 `ruff check`：通过。
- 修改 Python 文件 `ruff format --check`：通过。
- accepted plan residue scan（`dayu tests`）：旧 alias grammar helpers、`resolve_existing_ticker`、list-index helpers、`upsert_company_meta_for_upload` 与 read `strip().upper()` 均零命中。
- `git diff --check`：通过。

全仓 `ruff check dayu tests utils` 仍报告 88 个与本 work unit 无关的既有 lint findings；未按 scope 扩展处理。修改文件集合自身 lint 为 0，pyright 全仓为 0。

## 7. Residual risk / 未覆盖项

- 未执行用户明确禁止的 UF-PF05 真实 CLI evidence；CLI 真实 evidence 仍由后续既定 gate/work unit 承担。
- 未运行仓库所有非 Fins 测试；本次运行了完整 `tests/fins` 与受影响 combined tools acceptance，Host/Engine 未修改。
- filesystem permission tests 使用 exact `os.lstat` failure injection，避免 root-like CI 环境忽略 mode bits；真实平台 ACL/NFS 行为未做跨平台外部环境验证。
- workspace identity index 每次 route/identity-changing commit 扫描全部 corpus；accepted plan 明确不预建 durable cache/index，当前无真实性能证据支持扩展。

## 8. Stop condition

S2 implementation、tests、README、coverage、pyright、residue 与 diff validation 已完成。工作树未提交；本 artifact 写入后停止，不开始 implementation review。

## 9. S2 review FAIL 后的 fix addendum

S2 implementation review controller 判定 FAIL 后，已在同一 S2 fix gate 只处理 accepted F1/F2/F3；完整证据见 `docs/reviews/wu-upload-filing-ticker-alias-contract-s2-fix-codex.md`。

- F1：`begin_batch` 的 `publishes_new_corpus` 改由显式 `os.lstat` owner 派生；仅 `ENOENT` 为 missing，`EACCES/EIO`、symlink/non-directory fail closed，published tree byte-for-byte regression 已补。
- F2：accepted plan §11.3/§11.4 的 11 组强制矩阵全部补齐；测试涵盖 spawn same-canonical、锁获取/释放、orphan interleaving/recovery barrier/evidence、meta-less e2e 与 SEC/CN filing/material/direct/durable/observation exact failure projection。测试暴露的唯一生产缺口是 SEC/CN material terminal 仍使用 `str(exc)`；现已复用既有 `fins_upload_failure_from_exception(...)` owner。
- F3：download/preprocess/upload awaiting tests 各恰有一条 snapshot id 不包含 `finsjob_` 的断言；upload 断言归位，download 重复删除。
- 最终 relevant branch run 更新为 `1599 passed, 1 skipped`；修改生产文件最低 branch coverage `83%`，`_fs_storage_infra.py=84%`、SEC/CN material workflow files 均 `92%`；全量 pyright 仍为 `0 errors`。

本 addendum 覆盖第 6 节的旧测试计数，但不改变第 1 节 scope：未提交、未触碰 UF-PF05/oracle/scenario/frozen evidence/其它 finding，也未开始 re-review。

## 10. S2 re-review controller follow-up addendum

S2 re-review controller 对两项 low finding 要求同一 fix gate 的窄 follow-up，现已完成：

- `_commit_batch_with_publication_guard(...)` 的 target backup 判定不再使用 `Path.exists()`，而是在 target publication guard 内复用 `_lstat_optional_storage_path(...)`；仅 `ENOENT` 是 missing，operational I/O 与 symlink/non-directory 均在第一次 replace 前 fail closed。
- 新增 commit-time EACCES/EIO 与 regular-file owner tests，断言 replace 零调用、published locator/tree 与 backup evidence 不变、rollback/active state 按既有 contract 收口。
- 新增 begin-time symlink/regular-file 参数化 owner test，断言 locator exact 不变、无 reservation/active/batch evidence 泄漏，并通过同 ticker retry begin/rollback 证明 writer 可恢复。
- material company-name open question 按 controller 明确裁决不处理；README、锁图、merge/recovery owner 均未修改。
- 最终 relevant branch run：`1604 passed, 1 skipped`；identity + storage atomicity：`190 passed`；修改生产文件 branch coverage 全部 `>=80%`，`_fs_storage_infra.py=84%`；全量 pyright `0 errors`；ruff、residue 与 `git diff --check` 通过。

完整调用点、断言与 residual risk 见 S2 fix artifact 第 8 节。工作树仍未提交，未开始 re-review。
