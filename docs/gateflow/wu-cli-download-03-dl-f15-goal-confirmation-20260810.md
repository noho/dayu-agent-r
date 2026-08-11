# WU-CLI-DOWNLOAD-03-DL-F15 Goal Confirmation

## Gate

- Gate：goal confirmation
- Work unit：`WU-CLI-DOWNLOAD-03-DL-F15`
- Branch：`codex/download-oracle`
- Baseline HEAD：`54dd750a2e300e943eb25d9e49c09d31145ef1fb`
- Decision：confirmed；无 blocking open question，下一 gate 为 `plan`

## 第一性原理判断

DL-F15 成立且严重性判断准确。Docling runtime 对外声明 backend × device 的有序 fallback；只要第一次 converter 能关闭输入流，后续 attempt 复用同一流就必然不再处理原始 PDF，因此当前 fallback 不是偶发不稳定，而是输入生命周期违反 attempt 隔离契约。

真实 0700 观察与代码处于同一条数据路径：首次 `docling-parse/auto` 因外部 SSL/model resolution 失败，第二次 `pypdfium2/auto` 随即得到 `ValueError: I/O operation on closed file`。代码中 `convert_pdf_bytes_with_docling` 在调用 `run_docling_pdf_conversion` 前只构造一次 `DocumentStream`，其 callback 对每个 converter 都执行 `converter.convert(stream)`；而 `run_docling_pdf_conversion` 会为 attempt chain 多次调用该 callback。

## 目标与 semantic owner

唯一目标是让一次 `convert_pdf_bytes_with_docling` 调用中的每个 Docling attempt 都从同一份 immutable `raw_bytes` 新建独立、仍可读的 `DocumentStream`。

语义 owner 是 `dayu/documents/docling_runtime.py::convert_pdf_bytes_with_docling` 的“immutable PDF bytes -> attempt-local DocumentStream”装配边界：

- `raw_bytes` 是转换输入真源；
- `run_docling_pdf_conversion` 继续唯一拥有 attempt 顺序、converter 构造、日志和首次/末次异常语义；
- `ProcessCnDoclingConversionRunner` 继续拥有子进程、取消、临时目录、输出 size/digest 校验与 cleanup；
- Fins workflow、storage publication、CLI summary 不拥有 stream 生命周期，不能在下游补偿。

## 最小修复路径

只在 `convert_pdf_bytes_with_docling` 的 attempt callback 内从闭包中的 immutable `raw_bytes` 和 `stream_name` 新建 `DocumentStream`，再交给当次 converter。保留 `run_docling_pdf_conversion` 的公开签名和 callback 形态；不新增 factory/profile/schema、兼容 shim、测试后门或通用重试框架。

## 成功信号

1. owner deterministic test：第一次 converter 关闭自己的 stream 后失败；第二次 attempt 收到不同 identity、仍可读且 bytes 与原始 PDF 完全一致的 stream并成功。
2. 覆盖 `auto` 三档链，证明每个 attempt stream identity 独立；全链失败仍抛最后异常，并以首次失败为 `__cause__`。
3. production `ProcessCnDoclingConversionRunner`、取消、临时目录、digest/size、publication 语义不变。
4. 受影响测试、完整 pyright、changed-files Ruff/format、compileall、`git diff --check` 通过；修改生产文件单文件 coverage 不低于 80%。
5. 在修复 commit 的独立真实环境中，以此前失败的 0700 Q3 或 0066 文档运行 production `dayu-cli download` 与真实 Docling，核对 PDF、Docling JSON、meta、manifest 和后续 process 消费。
6. 若真实首 attempt 自然失败，记录后续 attempt 成功且不再出现 closed-file；若首 attempt 直接成功，只证明目标文档成功链，并把“real fallback 未观察”保留为待用户裁决 gap，不制造失败条件。

## 非目标与冻结边界

- 不修改 DL-F12、DL-F13、DL-F14，也不修改 HK Q2/Q4 分类或 CN/HK form policy。
- 不修改其它 CLI 命令、SEC throttle、process/upload、Host/Engine、下载缓存、性能或 observation 基础设施。
- 不改变 `run_docling_pdf_conversion` 的 attempt 策略、公开签名、日志含义或异常聚合规则。
- 不吞异常、不重开已关闭对象、不加入 loose fallback、mock hook 或生产测试开关。
- 不修改正式 Oracle/scenario registry 的 accepted/readiness 状态。
- 运行中发现的其它问题只登记直接证据，不在本 work unit 修复。

## 文件边界与文档决策

预期产品修改仅为：

- `dayu/documents/docling_runtime.py`
- 对应 owner test（优先新增 `tests/documents/test_docling_runtime.py`）

测试目录变化触发检查 `tests/README.md`；只有现有测试分层描述需要表达新增 owner coverage 时才更新。该修复不改变用户可见 CLI、Fins、Host/Engine 或架构契约，因此不触发其它 README/design 更新。

两份用户裁决输入 `docs/cli_ci.md` 与 `docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md` 必须保持当前字节不变，并在本 work unit 的 protected commit 中纳入。

## 风险与 open questions

- 真实网络/model cache 状态可能让第一 attempt 直接成功，导致真实 fallback 未自然触发；这是 evidence gap，不改变 deterministic owner test 的有效性。
- Docling 第三方 converter 是否关闭 stream 是外部实现细节，但 owner contract 不应依赖其保持打开；attempt-local stream 消除该耦合。
- Open questions：无。
