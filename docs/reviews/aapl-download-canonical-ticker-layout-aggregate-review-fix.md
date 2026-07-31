# AAPL 下载与 canonical ticker 布局：Aggregate Review Fix

## Finding

Aggregate deep review 指出 SEC `primaryDocument` 的 Windows drive 校验只检查最后
一个 segment，`C:/primary_doc.xml` 或 `xsl/C:/primary_doc.xml` 会被错误投影成
`primary_doc.xml`。

## 修复

- 对严格 POSIX 相对路径切分后的每个 segment 执行
  `PureWindowsPath(segment).drive` 校验。
- 保留最后一个 segment 作为合法 SEC XSL 展示路径的归档文件名。
- 新增 drive 位于首段和中间段的两个反例。

## 验证

- `pytest -q tests/fins/test_sec_pipeline_download.py`：101 passed。
- focused pyright：0 errors。
- `git diff --check`：通过。
