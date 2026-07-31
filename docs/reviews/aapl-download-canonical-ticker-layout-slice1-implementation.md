# AAPL 下载与 canonical ticker 目录 Slice 1 实施记录

## Gate

- gate：implementation
- slice：1 / SEC transformed primary document
- work unit：AAPL SEC 下载与 canonical ticker 目录
- completion status：implemented，待 code review

## Scope

- `dayu/fins/pipelines/sec_filing_collection.py`
- `tests/fins/test_sec_pipeline_download.py`

## Changes

- 在 SEC submissions 到 `FilingRecord` 的 owner 边界新增严格
  `primaryDocument` 投影。
- 合法 XSL relative transform path 只产生最后一个已验证 archive filename。
- 非字符串、空值、absolute、backslash、dot/dotdot segment、double separator、
  trailing separator 与 Windows drive-like filename 全部 fail closed。
- `FilingRecord.primary_document` 成为 downloader descriptor、store callback、主文件判断
  与 source upsert 共享的单一文件名真源。

## Validation

- `pytest -q tests/fins/test_sec_pipeline_download.py -k 'primary_document'`
  - 12 passed
- `pytest -q tests/fins/test_sec_pipeline_download.py`
  - 99 passed
- `pyright dayu/fins/pipelines/sec_filing_collection.py tests/fins/test_sec_pipeline_download.py`
  - 0 errors

## Docs decision

- 本 slice 不独立更新 README；累计 work unit 在 ticker storage contract 落地后更新
  `dayu/fins/README.md`。

## Residual risks

- 未来真实嵌套 SEC archive 文件：assigned to later work unit when direct evidence exists。
- 旧 ticker layout：covered by later approved Slice 2。

## Completion signal

目标 accession 的 primary document 已由
`xslSCHEDULE_13G_X02/primary_doc.xml` 投影为 `primary_doc.xml`，非法路径不进入
downloader/storage。
