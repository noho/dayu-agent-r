# UF-FIX06 Slice 2 implementation artifact

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`implementation Slice 2`
- 日期：2026-08-15
- 基线提交：`c1db7b495823f51b6fb01ad70c85044841cb80f0`
- Slice：`Slice 2：建立 Fins role contract 并迁移所有静态消费者`
- Completion status：`CODE REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Artifact path：`docs/gateflow/uf-fix06-slice2-implementation-20260815.md`
- Next entry point：`code re-review`

## 第一性原理与直接证据

问题成立，且 accepted plan 对严重性与 owner 边界的判断准确：

1. 实施前 `dayu.fins.ingestion_runtime` 同时读取 batch 的
   `FINS_UPLOAD_FILE_SUFFIXES` 与 Service 的 `SUPPORTED_UPLOAD_SUFFIXES`，同一个 filing
   格式事实存在两个 consumer-local 判定来源。
2. `dayu.fins.upload_batch` 自行声明包含 legacy `.xls` 与未证明 `.zip` 的 allow-list；
   material CLI 也读取同一旧常量，而 Slice 1 已经在 Documents owner 冻结了实际产品选择的
   9 个 format id 与 13 个有序 suffix。
3. filing request 只携带 raw paths，validated request 没有 primary/companion typed fact；首文件
   角色只能由后续 consumer 再次从位置反推。
4. CLI help 与 LLM-facing upload tool schema 都没有说明首文件 primary、后续 raw companion、
   companion 不转换、`.xml` 的 XBRL 限定或 suffix 不承诺内容转换成功。

因此正确修复位置是新增 Fins role owner，并让 ingestion、batch、material CLI 与两个文本 surface
消费该 owner；本 Slice 不应提前修改 Service/workflow、存储或显式 primary 协议。实施中没有发现
需要 `.xsd` 以外 companion-only 格式、batch 自动关联或内容识别的证据，未触发 stop condition。

## Scope 与 changed files

本 Slice 只修改或新增用户允许的文件：

### Production

- `dayu/fins/upload_format_contract.py`（新增）
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_batch.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/fins/tools/upload_tools.py`

### Tests

- `tests/fins/test_upload_format_contract.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_upload_batch.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`

### Artifact

- `docs/gateflow/uf-fix06-slice2-implementation-20260815.md`
- `docs/gateflow/uf-fix06-slice2-code-fix-20260815.md`

未修改 README、oracle/scenario registry、design doc、冻结 evidence 或任何 Slice 3/4 production/test
文件；未 commit。

## Implementation decisions

1. 新增唯一 Fins role owner `dayu.fins.upload_format_contract`：
   - `FinsUploadFileRole` 明确 `PRIMARY/COMPANION`；
   - `FinsUploadFormatFailureKind` 明确 primary、companion、material 三种 suffix failure；
   - `FinsUploadFormatError` 只携带 failure kind 与公共 label owner 产生的安全 basename，固定中文
     文案有界且不包含父路径；
   - `FinsUploadFormatCapability` 直接持有 Slice 1 的
     `DOCLING_CONVERTER_CAPABILITY`，primary/material suffix 始终投影其 13 个产品 suffix；
     companion 接受 primary 集合并只叠加 `.xsd`。
2. `FinsUploadFilingFiles` 使用 `frozen=True, slots=True`，以 `primary: Path | None` 和有序
   `companions` 表达角色；`from_upsert_paths` 强制非空并以首项为 primary，`for_delete` 产生唯一
   合法空状态，`ordered_files` 与 `require_primary` 提供严格 projection。
3. `FinsUploadMaterialFiles` 使用 `frozen=True, slots=True`，upsert 构造逐项执行
   converter-required admission，任一失败整体不返回 selection；`for_delete` 明确产生 typed empty。
4. ingestion 删除对两个 allow-list 的连续检查；保持逐文件
   `basename -> exists -> regular -> positional role suffix` 顺序，并在 workspace read 前构造 selection。
   `ValidatedFinsUploadFilingRequest.file_selection` 与静态 validation fact 均为必需非 Optional；
   create/update 携带 non-empty selection，delete 直接携带 `for_delete()`。
5. `FinsUploadUsageFailure.code` 接受既有 usage code 或格式 owner 的 role-specific failure kind；
   filing adapter 只把原始格式 error 包进既有 `FinsUploadUsageError`，不复制或重新解析 suffix 事实。
6. 删除 `FINS_UPLOAD_FILE_SUFFIXES` 及导出；batch scanner 直接调用
   `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary`。因此 13 个冻结 suffix 进入 standalone candidate，
   legacy、ZIP、`.xsd` 与第三方未选择扩展稳定 skip，且没有自动 companion association。
7. material CLI 的路径 helper 现在构造 `FinsUploadMaterialFiles`，再把其 authoritative files 传给
   既有 Service UI contract；非法 material suffix 由同一 role owner 在 Service factory 后、direct
   stream 前投影为 usage exit 2。本 Slice 未改变 Service/workflow 参数，避免提前扩入 Slice 3。
8. `FINS_UPLOAD_FORMAT_TEXT` 是 CLI `upload_filing --files` help 与 upload tool `files` schema 的共同
   immutable projection。文案自足说明首文件必须实际转换、后续文件仅原样保存且不转换、`.xsd`
   只能作为 companion、material 每项都转换、`.xml` 仅是 XBRL XML candidate，以及 suffix 不保证
   内容转换成功。
9. 文本 projection 只 import Slice 1 的静态 capability；子进程 import guard 证明 contract、CLI
   parser 与 upload tool schema 导入阶段均不加载第三方 Docling。
10. 未新增 `Any/object` 签名、`hasattr/getattr`、兼容 wrapper、consumer fallback、文件内容检查、
    存储语义、显式 primary selector 或 batch companion association。
11. code review accepted A1-A5 后，统一 projection 补齐 filing/material 的 create/update 至少一文件与
    delete 禁止文件规则，并把 `.json` 限定为 Docling JSON candidate，不承诺任意 JSON 内容可转换。
12. format owner 保留完整 canonical `file_label`，仅在错误文本超过 240 字符时使用 role-specific
    有界文案；`FinsUploadUsageFailure` 自身 fail-fast 校验 closed code union、非空文本与 240 字符上界，
    合法长 basename 不会退化为 runtime/unexpected failure。
13. `_upload_material_stream` 的异常契约已补记 `FinsUploadFormatError`；恢复了不承载语义的既有 Black
    formatting churn，并在源码 owner audit 测试处写明 governance 意图。delete+files 历史行为按裁决
    明确 deferred，本 Slice 未修改。

## Owner tests 与矩阵

新增或更新的断言覆盖：

- 13 个有序 primary suffix 精确等于
  `.pdf, .docx, .pptx, .htm, .html, .xhtml, .md, .txt, .csv, .xlsx, .xbrl, .xml, .json`；
- `.xsd` 是唯一 companion-only suffix，首文件 `.xsd` 失败，HTML primary + XSD companion 成功；
- filing 单 primary、多 companion 保序，empty upsert 失败，delete typed empty，empty selection
  `require_primary` 失败；
- material 多文件保序且逐项 converter-required；非法项产生
  `MATERIAL_SUFFIX_UNSUPPORTED`，不返回部分 selection；
- `.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx` 全部不能作为 standalone primary；
- primary、companion、material 三种错误 kind 均固定、中文、有界、只携带安全 basename；
- 长 basename 的 primary/material/usage 路径保留 canonical label、文本不超过 240 字符，且仍投影为
  typed usage failure；raw `FinsUploadUsageFailure` 对 open code、空文本和超长文本立即拒绝；
- batch 对 13 个 suffix 逐个产生 standalone filing plan 与 CLI script command；上述 10 个拒绝
  suffix 均为 `unsupported_suffix`，`.xsd` 不自动关联；
- validated filing create/update 直接携带 non-empty selection，delete 直接携带 typed empty；
- material CLI 对 `.xsd` 在 Service 调用前返回 usage exit 2；
- CLI help 与 LLM schema 都精确消费 `FINS_UPLOAD_FORMAT_TEXT`，并包含全部冻结业务语义、各 action 的
  files requirement，以及 `.json` 仅为 Docling JSON candidate 的内容限定；
- ticker/date/action/state 与既有 direct/runtime regression 全部继续通过。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行；未运行 UF-PF06 或 UF-PF12。

### Focused tests

```text
python -m pytest \
  tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_upload_batch.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py -q

1030 passed, 3 warnings in 19.43s
```

3 个 warning 均来自既有 `edgar` 依赖的 deprecated import，不是本 Slice 新增失败或 warning。
coverage 复跑同一矩阵仍为 `1030 passed, 3 warnings in 22.28s`。

### Changed-file pyright

```text
python -m pyright <6 个 changed production files> <6 个 changed test files>
0 errors, 0 warnings, 0 informations
```

### 逐文件 coverage

coverage data 写入 `mktemp -d` 临时目录，没有污染 workspace：

```text
Name                                  Stmts   Miss  Cover
dayu/cli/arg_parsing.py                 345      2    99%
dayu/cli/commands/fins.py               450     64    86%
dayu/fins/ingestion_runtime.py         2207    187    92%
dayu/fins/tools/upload_tools.py         106      8    92%
dayu/fins/upload_batch.py               316     14    96%
dayu/fins/upload_format_contract.py     152     10    93%
TOTAL                                  3576    285    92%
```

全部 changed production file 均达到 `>=80%`。

### Format、静态 owner 与 scope 审计

- Black 全文件检查覆盖 9 个本身符合当前 Black 的 changed files，均 unchanged；对 3 个存在基线格式
  差异的文件仅检查本 Slice changed ranges，均 unchanged，从而不重新引入已安全恢复的无语义 churn。
- `python -m ruff check <12 个 changed code/test files>`：`All checks passed!`
- `git diff --check`：通过。
- `rg -n 'FINS_UPLOAD_FILE_SUFFIXES' dayu tests -g '*.py'`：无结果。
- Slice 2 production/test 范围内 `SUPPORTED_UPLOAD_SUFFIXES`：无结果；该旧 Service-local 常量仍仅在
  approved Slice 3 文件中存在，按计划留给下一 slice 删除。
- 新增 diff 中 `Any/object/hasattr/getattr`、旧 allow-list 或 consumer fallback：无结果。
- registry、oracle/scenario、Host/Engine design 与全部 README diff：为空。
- import guard：`dayu.fins.upload_format_contract`、`dayu.cli.arg_parsing`、
  `dayu.fins.tools.upload_tools` 均可在禁止第三方 `docling` import 的子进程中成功导入。

## Docs decision

- 用户明确要求本 Slice 不修改 README；accepted plan 也把 README 同步冻结到 Slice 4。
- 本 Slice 虽触及 `dayu/fins`、CLI 与 tests，但不机械更新任何 README；最终用户/开发者文档由
  approved Slice 4 在 Service 行为落地并完成全局审计后统一更新。
- 唯一新增文档是用户允许的 implementation artifact 与 code-fix artifact。

## Residual risks 与 uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| Service 尚保留 `SUPPORTED_UPLOAD_SUFFIXES`，filing 仍按旧路径逐文件转换，validated selection 尚未被 workflow 消费 | covered by later approved slice | accepted plan Slice 3；本 Slice 不允许修改这些文件 |
| Slice 2 已投影最终角色文案，但完整 runtime 行为要到 Service/workflow 迁移后才闭环 | covered by later approved slice | accepted plan Slice 3；当前分支不应在 Slice 3 前发布 |
| README 尚未同步最终用户与开发者 owner/data flow | covered by later approved slice | accepted plan Slice 4；用户明确禁止本 Slice 修改 README |
| delete action 同时携带 files 的历史行为未在本 Slice 收紧 | assigned to later independent work unit | Controller 明确 deferred；本 Slice保持行为不变 |
| batch 不会把同目录 `.xsd` 自动关联到 HTML/XBRL primary | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| 显式 primary、重复输入及 basename/derived-name collision 未解决 | assigned to later work unit | `UF-FIX07` |
| 9 格式真实内容转换矩阵与 XBRL companion CLI evidence 未运行 | assigned to later work unit | `UF-PF06` |
| 137 条 full-real mandatory matrix 未运行 | assigned to later work unit | `UF-PF12` |

没有未分类 residual risk；本 Slice 未把 Service runtime、真实 PF 或 UF-FIX07 工作伪装为已完成。

## Completion decision

Slice 2 的 Fins role owner、role-specific typed failures、filing/material selections、non-Optional
validated selection、batch/material CLI owner migration、统一 help/schema projection，以及 code review
accepted A1-A5 的修复、owner tests、focused regression、changed-file pyright、逐文件 coverage 与静态审计
均已完成。按用户限定不 commit，也不进入 Slice 3；当前 code review fix 完成，下一入口精确为
`code re-review`。
