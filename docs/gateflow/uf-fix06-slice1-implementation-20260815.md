# UF-FIX06 Slice 1 implementation artifact

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`implementation Slice 1`
- 日期：2026-08-15
- Accepted plan commit：`267e90b121597c1d71247273d9450b90ffbe1c26`
- Slice：`Slice 1：建立真实 converter capability owner`
- Completion status：`IMPLEMENTATION + CODE REVIEW FIX COMPLETE`
- Blocking open question：无
- Artifact path：`docs/gateflow/uf-fix06-slice1-implementation-20260815.md`
- Next entry point：`re-review`（见 code-fix artifact）

## 第一性原理与直接证据

问题成立：产品对外承诺的可转换格式必须由实际构造 `DocumentConverter` 的 Documents
运行时边界拥有；若 help/consumer 自行从 Docling 默认能力动态推导，会让第三方升级静默扩大
产品面，若 constructor 不消费同一声明，则展示能力与真实转换能力仍可能漂移。

实施前使用当前 Python 3.11 虚拟环境直接读取 Docling 安装元数据并核对
`DocumentConverter` 构造签名：

- `DocumentConverter` 明确接受 `allowed_formats`。
- `InputFormat` 可解析冻结的 `PDF/DOCX/PPTX/HTML/MD/CSV/XLSX/XML_XBRL/JSON_DOCLING`。
- `FormatToExtensions` 逐项包含冻结的 13 个产品 suffix；其中 DOCX、PPTX、MD、XLSX
  还包含产品未选择的扩展名，直接证明必须采用“产品声明是第三方映射的子集”，不能反向动态扩面。

因此 accepted plan 的动机、严重性与 owner 边界均成立；未触发“任一冻结格式无法由安装元数据证明”的停止条件。

## Scope 与 changed files

本 Slice 只修改或新增用户授权的四个文件：

- `dayu/documents/docling_runtime.py`
- `tests/documents/test_docling_runtime.py`
- `docs/gateflow/uf-fix06-slice1-implementation-20260815.md`
- `docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`

未修改其它 production、test、README、review、registry、oracle、scenario 或 evidence 文件；未 commit。

## Implementation decisions

1. 在 `dayu.documents.docling_runtime` 建立 `frozen=True, slots=True` 的
   `DoclingConverterFormat` 与 `DoclingConverterCapability`，由模块级唯一实例
   `DOCLING_CONVERTER_CAPABILITY` 冻结 9 个 format id 和 13 个有序小写 suffix。
2. capability 在构造时校验非空、规范化与去重不变量；`format_ids`、`product_suffixes`
   和 `accepts_product_suffix` 都从同一不可变声明投影。命名保持 Documents 层角色中立，
   未保留 primary 兼容 alias。
3. 模块 import 与静态 projection 只依赖标准库；仅 `_resolve_docling_allowed_formats`
   和既有 converter construction path 延迟 import Docling。
4. 构造期把稳定 format id 解析为 `InputFormat`，逐格式校验产品 suffix 是
   `FormatToExtensions` 的子集。format id、mapping 或产品 suffix 缺失均抛
   `DoclingRuntimeInitializationError`；第三方新增 suffix 不扩面，也不导致失败。
5. `build_docling_pdf_converter` 向 `DocumentConverter` 显式传入由同一 capability
   解析的 `allowed_formats`。既有 PDF `format_options`、OCR/table/device/backend
   配置、二维 fallback attempt、输入流重建与异常链均未改变；非 PDF 格式故意由
   Docling constructor 按 `allowed_formats` 生成默认 options，不复制第三方默认表。
6. 未引入 `Any`、`object`、`hasattr`、`getattr`、兼容 shim、consumer fallback
   或 Docling 默认全格式回退。

## Owner tests

`tests/documents/test_docling_runtime.py` 新增并通过以下 owner contract：

- 9 个 format tuple 与 13 个有序 suffix projection 精确相等；
- 每个产品 suffix 是当前安装 `FormatToExtensions` 的对应子集；
- 已知第三方未选择 suffix 不进入产品 projection；
- 子进程禁止 `docling` import 时，模块 import 与静态 projection 仍成功；
- 第三方新增 suffix 后 constructor 继续成功，静态 projection 不扩面；
- constructed converter 的 `allowed_formats` 与 capability format ids 精确同源；
- constructed converter 的 `format_to_options` keys 精确等于 `allowed_formats`，且 PDF
  仍使用 Dayu 自定义 OCR/table/device/backend options；
- format id、整项 extension mapping 或产品 suffix 缺失均在 constructor path typed fail；
- 空 suffix、空 formats、重复 format id、跨格式重复 suffix 由声明 owner 拒绝；
- admission predicate 对空串、空白、`.`、无 suffix 与 dotfile 等价输入均返回 `False`；
- 既有平台/device fallback、PDF options、独立输入流与首因/末因 regression 全部通过。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

### Focused tests

```text
python -m pytest tests/documents/test_docling_runtime.py -q
............................                                             [100%]
28 passed in 2.57s
```

coverage 最终复跑同一测试仍为 `28 passed in 3.73s`。

### Pyright

```text
python -m pyright dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
0 errors, 0 warnings, 0 informations
```

### 逐文件 coverage

coverage data 写入 `mktemp -d` 临时目录，没有污染 workspace：

```text
Name                                      Stmts   Miss  Cover
dayu/documents/docling_runtime.py           217     19    91%
tests/documents/test_docling_runtime.py     202      1    99%
TOTAL                                       419     20    95%
```

两个 changed code/test file 均达到 `>=80%`。

### Format 与静态审计

- `python -m ruff check ...`：`All checks passed!`
- `python -m black --check ...`：两个文件均保持不变。
- `git diff --check`：通过。
- 目标文件内 `Any/object/hasattr/getattr` 扫描：无结果。

## Docs decision

- `tests/README.md` 的更新边界只要求在测试层级、运行方式或维护规则变化时更新；本 Slice
  只扩充既有 `tests/documents/test_docling_runtime.py` 的 owner assertions，没有改变上述事实。
- 用户明确限定不得修改 README；本 Slice 也尚未迁移 help/schema/consumer，因此不修改任何 README。
- 本 implementation artifact 已同步 code review fix 后的最终契约；fix 过程与 finding 状态记录在
  `docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`。

## Residual risks 与 uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| 第三方未来删除 format id 或产品 suffix 会导致初始化失败 | fixed in current slice | constructor typed fail-fast 与 owner tests 已覆盖；依赖升级时由 Documents capability owner 裁决，不静默缩减或扩面 |
| CLI/Fins/Service 尚未消费 capability，primary/companion 语义尚未落地 | covered by later approved slice | accepted plan Slice 2–4 |
| 9 格式真实内容转换矩阵与 XBRL companion CLI evidence 未运行 | assigned to later work unit | `UF-PF06` |
| 137 条 full-real mandatory matrix 未运行 | assigned to later work unit | `UF-PF12` |
| 显式 primary、重复路径及 basename/stem collision | assigned to later work unit | `UF-FIX07` |

没有未分类 residual risk；本 Slice 未把未来 consumer 或真实 PF 工作伪装为已完成。

## Completion decision

Slice 1 的 capability owner、lazy metadata validation、同源 `allowed_formats`、owner tests、
focused regression、pyright 与逐文件 coverage 均满足 accepted plan。按用户限定不 commit、不进入
accepted slice commit；当前 code review fix 完成，下一入口精确为 `re-review`。
