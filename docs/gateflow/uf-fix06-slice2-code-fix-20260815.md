# UF-FIX06 Slice 2 code review fix artifact

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`code review fix Slice 2`
- 日期：2026-08-15
- 基线提交：`c1db7b495823f51b6fb01ad70c85044841cb80f0`
- Completion status：`CODE REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Next entry point：`code re-review`

## Review 输入与裁决

本轮完整读取并以 Controller 裁决为唯一执行边界：

- `docs/reviews/code-review-slice2-mimo-20260815.md`
- `docs/reviews/code-review-slice2-ds-20260815.md`
- `docs/reviews/uf-fix06-slice2-code-review-adjudication-20260815.md`

Controller 结论为 `FIX REQUIRED`，接受 A1-A5。delete+files 历史行为明确 deferred；Slice 3、README、
UF-FIX07、registry、design doc 与冻结 evidence 均不属于本轮修复范围。

## Accepted findings 状态

| Finding | 状态 | 修复证据 |
| --- | --- | --- |
| A1：CLI help / LLM schema 缺少 action-level files requirement | 已修复 | 唯一 `FINS_UPLOAD_FORMAT_TEXT` projection 同时说明 filing/material 的 auto/create/update 至少一文件、delete 禁止文件；CLI 与 LLM schema 均消费该 projection |
| A2：长 basename 可能使合法格式失败退化为 runtime/unexpected，usage failure 未自校验 | 已修复 | format owner 保留完整 canonical `file_label`，仅对投影 message 使用 role-specific bounded fallback；`FinsUploadUsageFailure` fail-fast 校验 closed code union、非空 message 与 240 字符上界 |
| A3：material stream docstring 未声明 owner 格式异常 | 已修复 | `_upload_material_stream` 的异常段补齐 `FinsUploadFormatError` |
| A4：`.json` 文案可能承诺任意 JSON 内容可转换 | 已修复 | 同源 projection 明确 `.json` 仅为 Docling JSON candidate，suffix 不保证任意 JSON 内容可转换 |
| A5：无语义 Black churn 与源码 audit 治理说明 | 已修复 | 安全恢复 3 个文件的基线格式，仅保留语义 diff；源码 owner audit 前增加 governance 注释 |

delete action 同时携带 files 的历史行为没有修改，也没有用 CLI adapter 或 schema 特例提前收紧；该项按
Controller 裁决分配给后续独立 work unit。

## Owner 与实现边界

1. `dayu.fins.upload_format_contract` 继续是 suffix、role、format failure 与 LLM-facing 格式文本的唯一
   owner。长文件名不会被截断或改写：exception 中的 `file_label` 始终是公共 label owner 产生的完整
   canonical basename；只有人类可读 message 在无法同时容纳完整 label 与 240 字符上界时退回固定的
   role-specific 文案。
2. `FinsUploadUsageFailure` 是 usage projection 的直接 contract owner，因此由 dataclass 自身拒绝 open
   code、空文本和超过 240 字符的文本，而不是依赖某个 caller 碰巧校验。
3. CLI help 与 LLM tool schema 不各自复制 action/files 或 JSON 语义，而是继续引用同一个 immutable
   projection；projection 只依赖静态 converter capability，import path 不 eager import Docling。
4. batch 与 material CLI 的既有 owner 消费方式未回退；`FINS_UPLOAD_FILE_SUFFIXES` 仍不存在。

## 新增与更新测试

- format owner：primary/material 的超长合法 basename 保留完整 label、message 有界且无父路径；projection
  同时断言 filing/material files requirement 与 JSON candidate 限定。
- ingestion runtime：raw `FinsUploadUsageFailure` 对 open code、空 message、241 字符 message fail-fast；
  长合法 filename 仍是 `FinsUploadUsageError`，cause 保留 canonical label，不会变成 unexpected failure。
- material CLI：`.xsd` 与超长 `.doc` 均在 Service 调用前产生 typed usage exit；超长文件名不泄漏到有界
  message。
- CLI parser 与 upload tool schema：两侧分别断言同源 files requirement、delete prohibition 与
  `.json` 内容限定。
- batch source audit：保留唯一 owner 边界检查，并注明它是防止重复 allow-list 回流的 governance audit。

## Validation

全部命令均在 `source .venv/bin/activate` 后运行；没有运行 UF-PF06 或 UF-PF12。

### 六个 focused test files

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

3 个 warning 均来自既有 `edgar` 依赖的 deprecated import。

### Changed-file pyright

```text
python -m pyright <6 个 changed production files> <6 个 changed test files>
0 errors, 0 warnings, 0 informations
```

### Coverage

同一六文件矩阵复跑为 `1030 passed, 3 warnings in 22.28s`：

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

全部 changed production files 均达到单文件 `>=80%`。

### Format、owner 与 scope audit

- Ruff 检查全部 12 个 changed production/test files：`All checks passed!`。
- Black 全文件检查 9 个本身符合当前 Black 的 changed files：全部 unchanged。
- `dayu/fins/upload_batch.py`、`tests/fins/test_upload_batch.py`、
  `tests/cli/test_arg_parsing.py` 存在本 Slice 之前的基线 Black 差异；仅对本 Slice changed ranges 执行
  Black check，全部 unchanged，避免重新加入与语义无关的整文件 churn。
- `git diff --check`：通过。
- `rg -n 'FINS_UPLOAD_FILE_SUFFIXES' dayu tests -g '*.py'`：无结果。
- README、registry、oracle/scenario、design doc、冻结 evidence 与 Slice 3 production/test diff：为空。
- review artifacts 只读，未修改；没有 commit。

## Docs decision

用户明确禁止本 Slice 修改 README；accepted plan 将 README 同步冻结到 Slice 4。本轮只更新 Slice 2
implementation artifact 并新增本 code-fix artifact。

## Residual risks

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| Service 仍保留 `SUPPORTED_UPLOAD_SUFFIXES`，validated selection 尚未被 workflow 消费 | covered by later approved slice | accepted plan Slice 3 |
| README 尚未同步最终用户与开发者 owner/data flow | covered by later approved slice | accepted plan Slice 4 |
| delete action 同时携带 files 的历史行为未收紧 | assigned to later independent work unit | Controller 明确 deferred |
| batch `.xsd` association、显式 primary、重复输入及 basename/derived-name collision | assigned to later work unit | UF-FIX07 / 后续 batch association work unit |
| 9 格式真实内容转换矩阵与 XBRL companion CLI evidence | assigned to later work unit | UF-PF06 |
| 137 条 full-real mandatory matrix | assigned to later work unit | UF-PF12 |

没有未分类 residual risk。本轮没有把 deferred 行为、Slice 3、UF-FIX07 或真实 PF 验证伪装为已完成。

## Completion decision

accepted A1-A5 均已在正确 owner boundary 修复并由 focused tests 覆盖；类型、覆盖率、格式、静态 owner
与 scope audit 均通过。当前 gate 状态为 `CODE REVIEW FIX COMPLETE / RE-REVIEW PENDING`，下一入口严格为
`code re-review`。
