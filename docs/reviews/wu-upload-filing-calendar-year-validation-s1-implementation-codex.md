# UF-FIX04 S1 domain calendar/year owner implementation

## Gate record

- Gate: `implementation`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S1-domain-calendar-year-owner`
- Baseline commit: `f609a4d8238c6b31456c2e1d548079b22b771a68`
- Branch: `codex/upload-filing-oracle`
- Scope: 只建立 Fins domain calendar/year owner、迁移 owner contract 测试，并锁定 read-runtime 唯一生产 direct consumer 的 fail-closed 行为。
- Completion status: `implementation complete; review pending`
- Current gate / next entry point: `dual S1 deepreview`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-s1-implementation-codex.md`

## Changed files

1. `dayu/fins/domain/filing_semantics.py`
   - 新增 `parse_calendar_year(value: int) -> int`，明确拒绝 bool、非整数以及 `1000..9999` 之外的年份。
   - 新增 `parse_iso_calendar_date(value: str) -> datetime.date`，只接受 exact ASCII `YYYY-MM-DD`，不 strip，使用 `datetime.date` 验证实际 Gregorian 日期并执行 `isoformat()` round-trip。
   - `normalize_fiscal_year` 继续拥有 optional raw `JsonValue` admission：`None` 原样返回，非空值先拒绝 bool/非 int，再委托 `parse_calendar_year`；没有保留旧“任意正整数”兼容分支。
2. `tests/fins/test_fiscal_normalization_contracts.py`
   - 增加 year owner 正负矩阵、边界和委托守护。
   - 增加 full-date 公历边界、闰年、世纪非闰年、不存在日期、whitespace、non-padded、错误分隔符和非 ASCII 数字矩阵。
   - 增加 full-date parser 不调用 year owner 的直接守护，并迁移旧 fiscal-year 正整数测试到四位年 contract。
3. `tests/fins/test_read_runtime_semantic_ownership_guards.py`
   - 增加 `_parse_source_document_meta` 对 `1000/2025/9999` 保真解析的 direct consumer 回归。
   - 增加 `999/10000/bool/数字文本` 历史非法值按 domain owner fail closed 的回归。
4. `docs/reviews/wu-upload-filing-calendar-year-validation-s1-implementation-codex.md`
   - 记录本 slice 的实现、证据、验证、docs decision、residual risks 与下一 gate 入口。

未修改任何其它文件；未 stage、未 commit、未进入 S2、未运行 UF-PF04。

## First-principles judgment and direct evidence

- 动机成立且严重性准确：基线 `filing_semantics.py::normalize_fiscal_year` 只拒绝 `<=0`、bool 和非 int，仍接受 `999` 与 `10000`，没有唯一四位 year owner。
- 正确语义 owner 是 `dayu.fins.domain.filing_semantics`：该模块已经拥有 fiscal period/form/quality 等 filing 共享业务值；把 year/date 规则放在 upload、download 或 read adapter 会形成第二真源。
- 全仓 `normalize_fiscal_year(` 调用证据表明唯一生产 direct consumer 是 `dayu/fins/tools/read_runtime.py::_parse_source_document_meta`；本 slice 没有在该下游消费者增加 fallback 或重算，只通过 owner contract 自动 fail closed。
- 全仓 literal/call-site 核对未发现生产 producer 或现有 contract 明确要求把 `<1000` 或 `>9999` 作为合法财年，因此没有触发 accepted plan 的 stop condition。
- `parse_iso_calendar_date("0999-12-31")` 的正向测试与 monkeypatch 守护共同证明 full-date 公历域没有错误委托 `parse_calendar_year`，从而保持 Gregorian `0001..9999` 与 fiscal/partial year `1000..9999` 的语义解耦。
- 实现只新增两个纯函数、三个私有常量并复用标准库 `datetime.date`；没有新增类、协议、factory、状态机、re-export、shim 或 consumer-specific 规则，符合最小 owner boundary。

## Validation

所有命令均在仓库根目录执行，并先运行 `source .venv/bin/activate`；没有使用 shell pipeline 掩盖 pytest 或 coverage 的 exit code。

1. Focused owner/direct-consumer tests
   - Command: `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`
   - Result: exit `0`; `95 passed`, `3 warnings`。
   - Baseline reference before edits: exit `0`; `47 passed`, `3 warnings`。
2. Real reachable owner coverage set
   - Command: `coverage erase && coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_sec_pipeline_download.py -q`
   - Result: exit `0`; `208 passed`, `3 warnings`。
   - Coverage command: `coverage report --include='dayu/fins/domain/filing_semantics.py' --fail-under=80`
   - Result: exit `0`; `139` statements, `19` missed, **`86%` coverage**，满足 `>=80%` gate。
3. Targeted pyright
   - Command: `python -m pyright dayu/fins/domain/filing_semantics.py tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py`
   - Result: exit `0`; `0 errors, 0 warnings, 0 informations`。
4. Diff integrity and scope
   - Command: `git diff --check`
   - Result: artifact 写入前和写入后均 exit `0`，无输出。
   - 最终 `git status --short` 精确列出三个 allowed implementation/test 文件和本 implementation artifact；没有其它 modified/untracked 文件。

三条 pytest warning 均来自 `.venv` 中 `edgar` deprecated imports，不是本 slice 新增或修改代码产生的失败。

## Docs decision

- `dayu/fins/README.md`: 本 work unit 最终需要更新稳定 owner contract，但 accepted S1 明确把 README 列为 non-goal；由后续 approved slice 按 plan 完成，不在本 slice 越界修改。
- 根 `README.md`: 同理由后续 approved slice 记录最终用户可见 upload/download contract；S1 尚未接线 consumer，不提前宣称已可见。
- `tests/README.md`: 不更新。本 slice 只在既有 Fins 测试层增加 contract cases，没有新增测试层级、运行方式或维护规则。
- `dayu/README.md`、Host/Engine README: 分层、装配和对应生产目录均未变化，不触发更新。

## Findings and residual risks

- Implementation self-check findings: 无 blocking finding；正式 finding 状态由下一 gate 的 dual S1 deepreview artifact 裁决。
- Shared owner 尚未接入 upload static admission：`covered by later approved slice`，owner=`S2-upload-strict-static-admission`。
- Shared owner 尚未接入 download wrapper，且最终 README 尚未更新：`covered by later approved slice`，owner=`S3-download-shared-owner-and-docs`。
- `UF-PF04` 真实 CLI evidence 未执行：`assigned to later work unit`，owner=`UF-PF04`；本 slice 按用户明确要求排除。
- 其它 upload findings：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`。
- `upload_filings_from` raw-date parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
- 历史非法 fiscal year 的兼容读取：`fixed in current slice`；新 owner contract 明确 fail closed，不提供 migration、fallback 或兼容 shim。

没有 `unclassified residual risk`，没有需要当前用户裁决的 open question。

## Completion and handoff

S1 objective、API/type/docstring、owner matrix、read-runtime direct consumer regression、coverage、定向 pyright 与 diff integrity 均已达到 accepted plan 的 completion signal。本 artifact 只声明 implementation complete，不声明 slice accepted，也不创建 checkpoint commit。

Next entry point: `dual S1 deepreview`。
