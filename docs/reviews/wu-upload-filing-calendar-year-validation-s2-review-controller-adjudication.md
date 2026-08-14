# UF-FIX04 S2 双路审查控制侧裁决

## Gate record

- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S2-upload-strict-static-admission`
- Base: `e5d4394a`
- Reviewers: AgentMiMo、AgentDS
- Decision: `fix required`
- Next entry point: `AgentCodex S2 review fix`

## 审查结论

- AgentMiMo：Pass；未发现实质性问题。
- AgentDS：1 个低严重度 finding。生产实现已经把 filing/report date admission 放在文件存在性探测之前，但新增测试没有用“非法日期 + 缺失文件”的同一请求锁定该优先级。

## 裁决

接受 AgentDS F1。依据不是风格偏好，而是 accepted plan 在 S2 invariant 中明确要求 date/year checks 位于 file existence probes 之前，并用测试锁定。当前生产顺序正确，但若未来被移动到 file probes 之后，现有全部新增矩阵仍可能通过，因此 contract guard 不完整。

最小修复边界：

1. 只修改 `tests/fins/test_fins_ingestion_runtime.py`，在既有 validation-priority contract test 中加入 filing date 与 report date 对称 case。
2. 每个 case 同时提供合法 year/period、缺失文件路径和非法日期，断言返回字段对应的 `INVALID_FILING_DATE` / `INVALID_REPORT_DATE`，从而证明日期错误优先于 `FILE_NOT_FOUND`。
3. 不修改生产代码、CLI/tool tests、README、冻结 registry/evidence，不运行 UF-PF04。
4. 运行新增优先级测试、S2 focused/runtime 完整测试、定向 pyright 与 `git diff --check`；若完整 tool 测试被复跑，其 failure set 必须仍精确等于 UF-FIX01 baseline。

## 其它审查项

两路均确认以下事实，无需修复：

- upload runtime 直接委托 S1 calendar/year owner，没有复制 Gregorian/year 规则；
- CLI/tool filing 日期保留 raw input，material 与 `upload_filings_from` 非目标路径未改；
- 非法 year/date 在 workspace state read、operation、runner/converter、observation/job 和 durable mutation 前拒绝；
- typed usage mapping、LLM-facing schema、严格类型与中文 docstring 满足约束；
- frozen registry/evidence 未改，UF-PF04 未执行；
- runtime、CLI、tool 测试/覆盖率与 pyright 复核结果和 implementation artifact 一致。

S2 在修复完成并经 AgentMiMo / AgentDS 双路 re-review Pass 前不得 accepted 或 commit。
