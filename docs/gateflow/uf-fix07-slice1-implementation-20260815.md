# UF-FIX07 Slice 1 implementation artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`implementation Slice 1`
- 日期：2026-08-15
- Accepted plan commit：`64050349756ed2f95d57b02fe6318735f8bf60f7`
- Slice：`Slice 1：Raw/validated primary contract 与 owner admission`
- Completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Artifact path：`docs/gateflow/uf-fix07-slice1-implementation-20260815.md`
- Next entry point：`re-review`

## 第一性原理与 owner 判断

问题成立。原实现的 raw `FinsUploadFilingRequest` 不携带主文件 selector，static validator
按文件 index 分配角色，`FinsUploadFilingFiles.from_upsert_paths()` 再把首项固化为 primary；
因此 primary 不是请求事实，而是顺序副作用。重复规范路径、delete 携带 files 与多文件缺少
primary 也没有在 workspace state read 前形成 closed admission contract。

本 Slice 在计划指定的唯一 owner boundary 修复：raw request 保存 selector occurrence；
`_validate_fins_upload_filing_static()` 统一拥有规范路径、raw count、duplicate、selector
cardinality/membership、delete precedence 与角色选择；`FinsUploadFilingFiles` 只保存已经确定的
authoritative primary/companions 并校验角色格式。没有在 Service、CLI、tool、storage 或 processor
增加 fallback、重算或兼容 shim。

## Scope 与 changed files

本 Slice 实际只修改或新增以下用户授权文件：

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_format_contract.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/fins/test_fins_service_runtime.py`
- `docs/gateflow/uf-fix07-slice1-implementation-20260815.md`
- `docs/gateflow/uf-fix07-slice1-review-fix-20260815.md`

未修改 CLI、tool/schema、Docling、Service 生产代码、storage、registry、oracle、scenario、
frozen evidence、README 或两份 code review artifact；未 commit、push 或创建/推进 PR。

## Implementation decisions

1. `FinsUploadFilingRequest.primary_selectors` 使用 `tuple[Path, ...] = ()` 保存 raw occurrence；
   raw `files` 与 selector 均不提前选择角色，validated request 保留原 request 实例。
2. 新增六个 `FinsUploadUsageCode`，固定文案直接进入既有 `_USAGE_MESSAGES` 唯一 mapping；
   没有增加第二套消息分发或 generic invalid-argument fallback。
3. upsert 文件与 selector 统一执行 `expanduser().resolve(strict=False)`；相等事实统一由规范
   `Path` 的 case-sensitive exact string projection 产生，不使用 `normcase`、inode、basename
   或 stem。
4. static precedence 保持 ticker → source kind → action → raw `files <= 100` → year/period/date/company，
   随后执行 delete files → delete primary；upsert 再执行 normalize → duplicate → selector
   cardinality → single/multi membership → basename/exists/regular/explicit role suffix。
5. raw files 保序且不被去重。companions 从规范 files 删除 authoritative primary 后保持原相对顺序；
   single 无 selector 自动选择唯一文件，multi 无 selector fail closed。
6. 删除 `FinsUploadFilingFiles.from_upsert_paths()`，新增 keyword-only
   `for_upsert(primary=..., companions=...)`；不保留 wrapper、alias 或 re-export。delete 继续只通过
   `for_delete()` 产生 typed empty selection。
7. validator 交付的 `file_selection` 只含规范化路径；raw request 的 `files` 与
   `primary_selectors` 保持调用方原值，避免 raw/validated 事实混淆。
8. code review fix 在同一 static admission owner 内把 `expanduser/resolve` 的
   `OSError`/`RuntimeError` 收敛为既有 `FILE_NOT_FOUND`；public message 只消费 raw
   `Path.name`，不增加 code，也不让本地父路径进入消息。

## Owner tests

本 Slice 的测试固定以下 contract：

- single 0/1 selector 与 multi primary 位于首/中/末位置；companions 保持相对顺序；
- multi 缺 primary、重复 selector、集合外 selector 的 exact closed code/message；
- delete files 优先于 delete primary，且两类错误均在 path normalization、workspace repository
  bootstrap、state read、job/observation、runner 与 workspace mutation 前失败；
- raw duplicate 先于 selector 错误，`path`/`./path`/`dir/../path`/symlink alias 规范后拒绝；
- case-sensitive string identity、case-variant selector membership 与 hardlink 不按 inode 合并；
- 不同目录同 basename、同 stem 不同 suffix 不被误判 duplicate；
- 100 个 distinct files 接受，101 个 raw entries 先于 duplicate 返回 `TOO_MANY_FILES`；
- delete 携带 101 个 raw files 时，`TOO_MANY_FILES` 先于 `FILES_NOT_ALLOWED_FOR_DELETE`；
- raw file 或 selector 为 symlink loop 时均返回 `FILE_NOT_FOUND / 上传文件不存在：loop.pdf`，
  且 workspace/state/job/observation/runner/converter/publication 全部不可达；
- `.xsd` companion 与非首位置 primary 的角色格式由 explicit selection 决定；
- selection 无顺序推断 constructor，delete empty contract 保持。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

### Affected tests

```text
python -m pytest tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py -q
319 passed, 3 warnings in 6.33s
```

三条 warning 均来自既有 `edgar` 依赖的 deprecation warning，不是本 Slice 失败。

### Targeted pyright

```text
python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py \
  tests/fins/test_upload_format_contract.py
0 errors, 0 warnings, 0 informations
```

本 Slice 按 accepted plan 运行 targeted pyright。尚未修改的 Slice 3 测试仍引用已删除构造器，
其迁移属于后续 approved slice；本 Slice 没有越界修改，也没有为全仓临时通过保留兼容 shim。

### 逐生产文件 coverage

```text
Name                                  Stmts   Miss Branch BrPart  Cover
dayu/fins/ingestion_runtime.py         2254    198    656    139    88%
dayu/fins/upload_format_contract.py     157     12     48     12    88%
```

两个修改生产文件均达到 accepted plan 的 `>=80%` gate。

### Whitespace

```text
git diff --check
```

无输出，exit code 0。

未执行 UF-PF07、UF-PF12 或任何真实 CLI evidence。

## Docs decision

用户明确禁止本 Slice 修改 README；accepted plan 也把 README 同步放在 Slice 4。当前只完成
contract/admission，CLI/tool/schema 与 asset publication 尚未实现，因此不预写未来行为。

## Findings 与 residual risks

- MiMo review `docs/reviews/code-review-20260815-193205.md` 无 finding。
- DS Finding 1：`accepted`，`已修复`。normalize 的 `OSError`/`RuntimeError` 现在由 static
  admission owner 映射为既有 path-safe `FILE_NOT_FOUND`，files/selector symlink-loop owner test
  证明 typed code/message 与零副作用边界。
- DS R3：`accepted`，`已修复`。新增 delete+101 owner test，冻结 `TOO_MANY_FILES` 优先于
  `FILES_NOT_ALLOWED_FOR_DELETE`。
- DS R1/R2：`covered by later approved slice`，分别由 Slice 2 与 Slice 3 处理。
- DS R4：`assigned to later work unit`，仍禁止执行 UF-PF07/UF-PF12 与真实 evidence。
- DS R5：`accepted boundary`；private helper 已记录无重复 input invariant，唯一 caller 先执行
  duplicate admission，不修改生产代码。
- CLI/LLM tool 尚未构造 `primary_selectors`：`covered by later approved slice`，owner/destination 为 Slice 2。
- Docling upload、storage identity/primary 与 processor consumption 测试尚未迁移；这些测试中残留的
  `from_upsert_paths()` 调用同属 `covered by later approved slice`，owner/destination 为 Slice 3。
- README 与 full affected validation：`covered by later approved slice`，owner/destination 为 Slice 4。
- UF-PF07/UF-PF12 真实 evidence：`assigned to later work unit`，本 Slice 明确禁止执行。
- UF-FIX08/FIX10/FIX11、registry/oracle stale evidence 与 material duplicate 行为保持计划 §12 的既有分类，
  未发生 owner 或风险分类变化。

没有 unclassified residual risk，也没有 blocking open question。

## Completion decision

Slice 1 的 raw selector、static validation precedence、inclusive 100 上限、exact normalized-path
duplicate、single/multi primary contract、delete closed rejection 与 typed authoritative selection 已按
accepted plan 完成并通过 focused tests、targeted pyright、逐文件 coverage 与 whitespace 检查。
两路 code review 的 accepted finding 与测试缺口均已修复；按用户要求不进入 re-review、commit 或
后续 Slice，下一入口为主控派发 `re-review`。
