# WU-CLI-DOWNLOAD-03-DL-F15 Aggregate Deepreview 裁决

## 裁决范围

- Work unit：`WU-CLI-DOWNLOAD-03-DL-F15`
- Review base：`715b25a6105651fe21ddb454b1c378459cea1d9a`
- Accepted slice commit：`8e7f9a10f31e167bdcc66e474f0ea102434baaf5`
- MiMo review：`docs/reviews/code-review-20260810-221142.md`
- DS review：`docs/reviews/code-review-20260810-221157.md`

## 双路结论

MiMo 与 DS 均独立给出 `PASS`，没有 material finding，也没有 blocking open question。两路审查均完整走读了：

`convert_pdf_bytes_with_docling → run_docling_pdf_conversion → _build_docling_document_stream`

并确认：

1. immutable raw PDF bytes 是唯一输入真源；`DocumentStream` 与底层 `BytesIO` 现在在每个 attempt 内重新构造。
2. `run_docling_pdf_conversion` 的公开签名、attempt 顺序、成功短路、日志与首次 cause/末次异常聚合相对 base 零改动。
3. owner tests 直接证明首档关闭自己的输入并失败后，第二档获得 identity 不同、仍可读、内容相同的新输入；auto 三档全失败时每档输入独立且异常链不回归。
4. `ProcessCnDoclingConversionRunner`、upload service 与 web caller 相对 base 零改动；不存在下游补偿、兼容 shim、测试后门或 semantic ownership drift。
5. 修改文件 coverage 为 81%，owner tests、runner regression、pyright、Ruff、format、compileall 与 diff-check 均已通过。

## 总控裁决

### Findings

无 accepted finding。Slice S1 通过 aggregate deepreview gate，不需要 fix / re-review。

### Residual risks 裁决

- 真实补跑若首 attempt 直接成功，则无法自然观察真实 fallback。这是明确的 post-fix evidence gap，不是代码缺陷；不得为制造失败增加生产 hook、mock、断网副作用或观察基础设施。deterministic owner test 负责锁定 fallback contract，真实 CLI 只陈述实际发生的 attempt 顺序。
- 单 attempt 全失败分支和若干非目标 Docling 装配分支未直接覆盖。它们不属于 DL-F15 的 attempt-local stream 生命周期语义，且修改文件分支覆盖率已达到冻结计划的 80% 门槛，不扩大测试范围。
- 极端的 Docling 部分安装状态可能使 stream import 错误进入既有 attempt 聚合并增加日志。完整缺失依赖仍在 converter 构造阶段直接失败；该非标准安装边缘不改变本 work unit 目标，不作为新 finding 扩修。

## Scope guard

- 未修改 DL-F12～F14、HK Q2/Q4 分类、CN/HK form policy、overwrite/rebuild、SEC throttle、process/upload、Host/Engine 或正式 Oracle/scenario registry。
- 未引入通用 observation harness、runner framework、schema、兼容层、下载缓存或性能工程。
- 真实 CLI 补跑必须以本裁决后的不可变产品 HEAD 执行；观察结果只形成 `observed-behavior.md` 与待用户裁决建议，不得由 Agent 标记 Oracle/scenario/readiness 为 accepted/ready。

## Gate 结论

`PASS`。允许提交 aggregate deepreview artifacts，并进入最终产品 HEAD 上的最小真实 post-fix observation。
