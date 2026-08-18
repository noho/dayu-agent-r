# UF-FIX11 S3 implementation

## Gate metadata

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：`S3 implementation`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- accepted prerequisites：`5bb122d3`、`f6893c29`
- completion status：`COMPLETE / READY FOR IMPLEMENTATION REVIEW`
- artifact path：`docs/gateflow/uf-fix11-s3-implementation-20260817.md`
- stage / commit / push / PR：均未执行

## Scope 与 owner 判断

S1+S2 已由 company-meta commit owner 基于 publication-lock final truth 产生 typed warning；S3 的真实缺口是该值尚未进入 runtime summary、durable JSON、direct public result、CLI 与 completed wait projection。实现只修改 accepted S3 allowed files 和 amendment 新增的三个 direct symbols，不重新解析 warning、不比较公司名称、不读取 storage，也不修改 S1+S2 parser/codec 或四个 `SourceKind` callsite。

语义 owner 保持不变：

- `CompanyMetadataWarning` 及 JSON codec 继续属于 `dayu.fins.company_metadata_warning`，本 slice 零 diff。
- `FinsUploadResultSummary` 拥有 runtime/durable upload summary invariant 与 JSON 投影。
- `FinsResultSummary` 拥有 direct public result 的 warning invariant。
- Service、direct builder、CLI 与 wait adapter 只机械复制或序列化同一 typed tuple。

## Changed files 与 decisions

### Production

- `dayu/fins/ingestion_runtime.py`
  - `FinsUploadResultSummary.warnings` 固定为 `tuple[CompanyMetadataWarning, ...] = ()`。
  - constructor exact 校验元素类型、最多一个，并只允许 exact `ok` / `skipped` 携带非空 warning；`failed` / `cancelled` / `deleted` 非空时 fail closed。
  - `to_json_summary()` 始终输出 `warnings` 数组，空值为 `[]`。
  - `_direct_result_event` 新增无默认值的必填 `warnings` 参数；upload callsite 传 `summary.warnings`，唯一 generic/non-upload callsite 传 `()`。
  - CANCELLED 分支不重写 warnings，非法非空组合由 `FinsResultSummary` constructor 拒绝。
- `dayu/fins/service_runtime.py`
  - `_upload_summary_from_result` 显式复制 `result.warnings`，不依赖 summary 默认值。
- `dayu/fins/direct_events.py`
  - `FinsResultSummary.warnings` 固定为自然空默认 `()`，exact 校验元素、最多一个，且仅 `SUCCESS` 可非空。
- `dayu/cli/output.py`
  - success stdout 标题和摘要保持既有输出；随后把每个 typed `warning.message` 写入 stderr，exit code 不变。
- `dayu/service/fins_wait_adapter.py`
  - completed value 增加 canonical `warnings` JSON 数组；failed/cancelled outcome 不增加该字段，也不从错误文本推断。

### Tests

- `tests/fins/test_fins_ingestion_runtime.py`
  - 覆盖 upload summary exact-element、at-most-one、`ok|skipped`-only、空数组与 durable save/re-read。
  - 复用现有 runtime/request/runner fixtures 和真实 direct stream 覆盖 uploaded、skipped、empty、deleted copy；既有真实 download、failure、cancelled 路径断言空 warning。
  - AST 穷举 `_direct_result_event` exact 两个 callsites，实参集合 exact 为 `summary.warnings` 与 `()`，并断言 warnings keyword-only 参数没有默认值、helper 内没有写回该参数。
- `tests/fins/test_fins_service_runtime.py`
  - 断言 service 汇合点保留同一 typed tuple。
- `tests/fins/test_fins_direct_stream.py`
  - 只覆盖 `FinsResultSummary` public exact/at-most-one/SUCCESS-only invariant 与既有 stream contract；未导入 ingestion private helper。
- `tests/cli/test_output.py`
  - 断言 warning 不改变 stdout、无 warning 不增加 stderr、规范 message 逐条进入 stderr；补齐相关 typed download failure renderer 分支以满足逐文件 coverage gate。
- `tests/cli/test_fins_commands.py`
  - mocked uploaded/skipped terminal summary 均覆盖 warning、stdout 摘要、stderr 文案和 exit `0`。
- `tests/service/test_fins_wait_adapter.py`
  - completed warning exact JSON，completed empty 为 `[]`；failed/cancelled 不增加或推断 warning。

### README

- `README.md`：按最终用户手册边界记录 fresh canonical name 不被单次 filing 改写、成功 warning 的 stdout/stderr/exit 语义，以及 skipped filing 的合法 alias 原子保存。
- `dayu/fins/README.md`：按开发手册边界修正 skip 状态机稳定事实，记录 commit outcome/publication-final warning owner 与各投影层机械传播。
- `tests/README.md`：扩充现有 Fins direct focused 矩阵与 warning owner/projection 覆盖说明。

## Validation

所有命令均在仓库根目录、`source .venv/bin/activate` 后执行。

### S3 focused

```text
pytest -q \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

结果：`543 passed, 3 warnings`。warnings 均为已安装 edgar 包的 deprecation warning。

### Combined regression

```text
pytest -q \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

最终结果：`2152 passed, 1 skipped, 3 warnings`。唯一 skip 为既有 Docling integration 环境条件；没有失败。

### Branch coverage

```text
coverage erase
coverage run --branch -m pytest \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
coverage report -m --include='dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py,dayu/fins/direct_events.py,dayu/cli/output.py,dayu/service/fins_wait_adapter.py'
```

结果：`2152 passed, 1 skipped, 3 warnings`；逐文件 coverage：

- `dayu/fins/ingestion_runtime.py`：89%
- `dayu/fins/service_runtime.py`：88%
- `dayu/fins/direct_events.py`：83%
- `dayu/cli/output.py`：82%
- `dayu/service/fins_wait_adapter.py`：91%

第一次 coverage 运行中 `dayu/cli/output.py` 为 78%，未伪造通过；随后只补相关 typed Fins failure renderer 测试，完整重跑后达到 82%。

### Type check

```text
python -m pyright dayu tests utils
```

结果：`0 errors, 0 warnings, 0 informations`。

### Static boundary

- `git diff --check`：通过。
- `git status --short` / `git diff --name-only`：除本 artifact 外只包含 S3 production、test 与三个 README allowed files。
- `rg -n "def commit_batch" dayu tests`：仍为 production 3 个定义、tests 7 个文件 / 9 个定义，全部 exact `CompanyMetaCommitOutcome | None`。
- SEC/CN failure producer 仍显式 `warnings=[]`；SKIP metadata commit 的 capability transfer 与 rollback 代码零 diff。
- `_direct_result_event` AST test 证明 exact 两个 callsites、必填无默认 warnings 参数与无 helper 内静默归零。
- `_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 函数体零 diff。
- S1+S2 `FinsUploadPipelineResult` parser、warning codec、四个 Service `SourceKind` callsites零 diff。
- Host、Engine、material、oracle、scenario、registry、frozen evidence 均无 diff。

## Validation corrections

首次 focused 运行为 `541 passed, 1 failed`，失败来自新增 wait 负例把 generic failed message 错当 JSON；直接代码证明该分支的 owner contract 是纯业务文本，修正测试为“不含 warnings 文本”后最终 focused 全绿。该失败没有触发 production fallback 或 contract 变更。

## Residual risks 与 uncovered areas

### Fixed in current slice

- runtime/durable/direct/service/CLI/wait 丢失或重算 typed warning。
- failed/cancelled/deleted 非法携带 warning。
- `_direct_result_event` 默认参数掩盖漏传、第三个 callsite 漂移或 CANCELLED 静默归零。
- CLI warning 改写 stdout/exit code，或 no-warning 成功新增 stderr。
- completed wait 缺少 warning JSON，或 failed/cancelled 从错误文本推断 warning。

### Accepted tradeoffs

- warning collection 当前最多一个；这是 frozen company-name ignored 业务闭集，不扩张为通用 warning framework。
- 所有 completed wait result 都显式包含 `warnings` 数组；非 upload completed 使用自然空数组。
- branch coverage 中保留的 misses 属于既有非 S3 分支；五个修改生产文件均达到逐文件 80% 门槛。

### Assigned to later work unit

- name-only metadata batch 的 writer lock / physical swap 成本。
- material upload 的类似 company-name 行为。
- 真实 CLI/network/scenario/oracle/frozen evidence；本 work unit 明确未运行、未修改。
- commit 已 durable 但 post-commit guard-release/cleanup 报错的运维可见性。

未分类 residual risk：无。

## Boundary confirmation 与 next entry point

- 未 stage、commit、push 或创建 PR。
- 未运行真实 CLI、网络或 evidence。
- 未修改 Host、Engine、material、oracle、scenario、registry 或 frozen evidence。
- 下一 gate：`S3 implementation review`；本 artifact 不预判 review、fix、acceptance 或 accepted slice commit。
