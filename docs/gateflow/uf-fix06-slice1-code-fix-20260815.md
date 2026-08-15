# UF-FIX06 Slice 1 code review fix artifact

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`code review -> fix`
- Slice：`Slice 1：建立真实 converter capability owner`
- 日期：2026-08-15
- Controller 裁决：`docs/reviews/uf-fix06-slice1-code-review-adjudication-20260815.md`
- Reviewed inputs：
  - `docs/reviews/code-review-slice1-mimo-20260815.md`
  - `docs/reviews/code-review-slice1-ds-20260815.md`
- Completion status：`CODE FIX COMPLETE`
- Blocking open question：无
- Artifact path：`docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`
- Next entry point：`re-review`

## Scope 与 owner 决策

本 fix 只修改 Controller 授权的 Slice 1 owner 边界与 durable artifacts：

- `dayu/documents/docling_runtime.py`
- `tests/documents/test_docling_runtime.py`
- `docs/gateflow/uf-fix06-slice1-implementation-20260815.md`
- `docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`

Documents capability 拥有产品允许格式、产品 suffix 投影与 admission predicate；Fins 才拥有
primary/companion 角色。Dayu 拥有 PDF 自定义 pipeline/backend 配置，非 PDF 默认 format option
由 Docling constructor 拥有。本 fix 未在 consumer、adapter 或测试 fixture 增加 fallback，也未复制
第三方默认 option 表。

## Finding 状态

| ID | 最终状态 | 修复与直接证据 |
| --- | --- | --- |
| F1 | 已修复 | 唯一公开投影改为 `product_suffixes` / `accepts_product_suffix`；production/test/artifact 的旧 primary 名扫描为空，未保留 alias、re-export 或 wrapper。 |
| F2 | 已修复 | 新增 `FormatToExtensions[InputFormat.PDF]` 整项删除的 constructor typed-fail owner test；新增空 suffix、空 formats、重复 format id、跨格式重复 suffix 四项最小声明不变量断言。 |
| O1 | 已修复 | `accepts_product_suffix` 在 capability owner 内先识别无有效 suffix；空串、空白、`.`、带空白的点、无 suffix 路径和 dotfile 的 `Path.suffix` 均断言返回 `False`，严格声明 normalizer 仍对非法声明抛 `ValueError`。 |
| O2 | 已修复 | production docstring/注释明确非 PDF 故意交给 Docling constructor 默认 options；真实 converter 测试断言 `format_to_options` keys 按顺序精确等于 `allowed_formats`，并断言 PDF 仍是 `PdfFormatOption`、使用 Dayu backend 与 OCR/table/device 配置。未复制第三方默认表。 |

没有 `未修复`、`部分修复` 或 `证据失效` finding。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

### Focused tests

```text
python -m pytest tests/documents/test_docling_runtime.py -q
............................                                             [100%]
28 passed in 2.57s
```

coverage 复跑同一测试：`28 passed in 3.73s`。

### 两文件 pyright

```text
python -m pyright dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
0 errors, 0 warnings, 0 informations
```

### 逐文件 coverage

coverage data 写入 `mktemp -d` 工作区外临时目录：

```text
Name                                      Stmts   Miss  Cover
dayu/documents/docling_runtime.py           217     19    91%
tests/documents/test_docling_runtime.py     202      1    99%
TOTAL                                       419     20    95%
```

两文件均达到 `>=80%`。

### Format、diff 与 scope

- `python -m ruff check dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py`：`All checks passed!`
- `python -m black --check dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py`：两个文件保持不变。
- `git diff --check`：通过。
- production/test/implementation artifact 内旧 `primary_suffixes` / `accepts_primary_suffix` 扫描：无结果。
- preflight 已存在的三份 untracked review/裁决输入保持未修改；本 fix 未修改其它文件，未 commit。

## Docs decision

本 fix 不改变测试层级、运行方式、用户入口、分层关系或最终用户工作流。按 Controller 与用户明确
范围不修改 README、plan、registry、oracle/scenario 或冻结 evidence；只同步原 implementation
artifact 并新增本 code-fix artifact。

## Residual risks 与 uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| private helper test coupling 与已知第三方未选择 suffix 列表可能过期 | tracked by existing review | Controller 明确保留为低 residual；aggregate review 可再次检查，不改为动态反向枚举 |
| 第三方畸形 mapping 值可能先产生裸 `ValueError` | tracked by existing review | Controller 当前不接受为产品 finding；aggregate review 可再次检查 |
| later slices 尚未删除旧 allow-list | covered by later approved slice | accepted plan Slice 2–4 |
| 9 格式真实内容转换矩阵与 137 条 full-real mandatory matrix 未运行 | assigned to later work unit | `UF-PF06` / `UF-PF12` |

没有未分类 residual risk；本 fix 未运行 Controller 明确排除的 UF-PF06/UF-PF12。

## Completion decision

F1/F2/O1/O2 均为 `已修复`，focused tests、两文件 pyright、ruff/black、逐文件 coverage
与 diff check 全部通过。按用户要求不 commit；当前 gate 完成，下一入口精确为 `re-review`。
