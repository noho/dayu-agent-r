# UF-FIX07 Slice 1 code review fix artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`code review fix`
- 日期：2026-08-15
- Accepted plan commit：`64050349756ed2f95d57b02fe6318735f8bf60f7`
- Slice：`Slice 1：Raw/validated primary contract 与 owner admission`
- Input review artifacts：
  - `docs/reviews/code-review-20260815-193205.md`
  - `docs/reviews/code-review-20260815-193342.md`
- Completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Artifact path：`docs/gateflow/uf-fix07-slice1-review-fix-20260815.md`
- Next entry point：`re-review`

## 主控裁决与 finding 状态

| 来源 | Finding / residual | 主控裁决 | Fix 状态 |
| --- | --- | --- | --- |
| MiMo | 无 finding | pass evidence | 无需修复 |
| DS | Finding 1：normalize 的 `OSError`/`RuntimeError` 逃出 closed usage contract | `accepted` | `已修复` |
| DS | R3：delete+101 precedence 缺少 owner test | `accepted` | `已修复` |
| DS | R1：Slice 2 前 LLM-facing 文案窗口期 | `covered by later approved slice` | Slice 2 |
| DS | R2：Slice 3 测试残留旧 constructor | `covered by later approved slice` | Slice 3 |
| DS | R4：真实 evidence 未执行 | `assigned to later work unit` | 后续 evidence work unit |
| DS | R5：private selector helper 依赖无重复 input invariant | `accepted boundary` | documented invariant；唯一 caller 先判重 |

没有 `needs-more-evidence`、unclassified residual risk 或 blocking open question。

## Root cause 与 owner 修复

DS Finding 1 成立。`_normalize_fins_upload_path()` 原先直接调用
`expanduser().resolve(strict=False)`，symlink loop 等 `RuntimeError` 或文件系统 `OSError` 会越过
`_validate_fins_upload_filing_static()` 的 closed `FinsUploadUsageError` contract。该失败发生在
canonical path 尚未产生时，正确业务 owner 是 static admission，而不是 CLI、Service 或下游 runner。

修复保持既有 contract：

1. `_normalize_fins_upload_path()` 捕获 `OSError | RuntimeError`。
2. 复用既有 `FinsUploadUsageCode.FILE_NOT_FOUND` 与 `_USAGE_MESSAGES` 文案，不新增 code、message
   mapping、CLI 分支或兼容 shim。
3. failure 只接收 raw `path.name`，因此 public message 为
   `上传文件不存在：<raw basename>`，不包含本地父路径。
4. helper 中文 docstring 明确参数、返回、`TypeError` 与 typed `FinsUploadUsageError`，不再承诺底层
   path exception 逃出 owner boundary。

DS R3 的缺口通过 owner-level test 修复：delete 同时携带 101 个 raw files 与 primary selector，
精确断言 `TOO_MANY_FILES / --files 数量不能超过 100 个`，证明 raw count gate 先于
`FILES_NOT_ALLOWED_FOR_DELETE` 与 `PRIMARY_NOT_ALLOWED_FOR_DELETE`。

## Changed files

本 fix 只修改或新增 Slice 1 白名单文件：

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/gateflow/uf-fix07-slice1-implementation-20260815.md`
- `docs/gateflow/uf-fix07-slice1-review-fix-20260815.md`

两份 `docs/reviews/` 输入 artifact 未修改。未修改 CLI/tool/schema、Docling、Service 生产代码、
storage、README、registry、oracle、scenario 或 frozen evidence。

## Owner tests

- raw file symlink loop：`FILE_NOT_FOUND / 上传文件不存在：loop.pdf`；
- raw primary selector symlink loop：同一 typed code/message；
- 两种 loop 的 message 均不含 `tmp_path`；
- guarded runtime 证明 state repository、executor/job、runner/converter、observation、workspace tree 与
  publication 路径均不可达；
- delete + 101 raw files（同时带 selector）先返回 `TOO_MANY_FILES`，不进入 delete files/primary 分支。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

### Affected tests

```text
python -m pytest tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py -q
319 passed, 3 warnings in 6.33s
```

三条 warning 均来自既有 `edgar` 依赖的 deprecation warning。

### Targeted pyright

```text
python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py \
  tests/fins/test_upload_format_contract.py
0 errors, 0 warnings, 0 informations
```

### 逐生产文件 coverage

```text
Name                                  Stmts   Miss Branch BrPart  Cover
dayu/fins/ingestion_runtime.py         2254    198    656    139    88%
dayu/fins/upload_format_contract.py     157     12     48     12    88%
```

两个 Slice 1 修改生产文件均达到 `>=80%`。

### Whitespace

`git diff --check` 无输出，exit code 0。新建 untracked artifact 另以
`git diff --no-index --check /dev/null <artifact>` 检查，无 whitespace 输出。

未执行全仓 pyright、UF-PF07、UF-PF12、真实 CLI 或其它 frozen evidence。

## Docs decision

README 属于 accepted plan Slice 4，且用户明确禁止本 fix 修改；本轮仅更新 Gateflow implementation/fix
artifact，不预写 Slice 2/3 行为。

## Residual risks

- R1：`covered by later approved slice`，Slice 2 更新 CLI/tool/schema 与 LLM-facing 文案。
- R2：`covered by later approved slice`，Slice 3 迁移旧 constructor consumer tests并完成 asset/storage contract。
- R4：`assigned to later work unit`，UF-PF07/UF-PF12 与 frozen evidence 后续获授权执行。
- R5：`fixed in current slice` 的治理记录；private helper 的无重复 input invariant 已在 docstring 明示，
  当前唯一 caller 在调用前执行 duplicate admission，主控接受该 boundary，不扩大生产实现。
- accepted plan §12 的 UF-FIX08/FIX10/FIX11、registry stale evidence、material duplicate 等分类保持不变。

没有 unclassified residual risk。

## Completion decision

DS Finding 1 与 R3 测试缺口均已修复；MiMo pass evidence、其它 residual owner/destination 已记录。
当前状态为 `REVIEW FIX COMPLETE / RE-REVIEW PENDING`。按用户要求不进入 re-review、Slice 2、commit、
PR 或真实 evidence，停止等待主控派发 re-review。
