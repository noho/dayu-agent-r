RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6

CANARY=gpt-6-sol-80104578

# 下载失败诊断 S1：中文函数文档 fix

- Task label：`dfdiag-doc-fix-sol-20261010-01`；work unit：`download-failure-diagnostics-20261010`。
- Gate：gateflow implementation/fix，仅本 doc fix；当前交接入口为 root 的 re-review。没有裁决 slice、review gate 或 work unit pass。
- Artifact：`docs/gateflow/download-failure-diagnostics-doc-fix-20261010.md`，本轮唯一新增正式 artifact。
- Branch：`fix/download-failure-diagnostics-20261010`；冻结及完成核验 HEAD：`a1df000835c61d1acfa383532488746e1487ed7b`。
- Runtime/provider 按任务记录；当前环境只提供 GPT-6 家族身份，未提供更细后端型号。MODEL 为 gpt-6，不把 provider 名称、canary 或自报当作 gpt-6-sol 物理型号证明；未运行型号探针。
- 工具实际读取本轮 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.1xWc7o/canary.txt`，输出原文见 CANARY；未采用旧轮次 token。
- Design document / issue / issue 关联：N/A。无子 Agent、goal 工具、联网观测、生产 query、download、overwrite 或 recovery。

## 输入、动机与 owner

已读根 AGENTS.md、已确认 goal、approved plan、本轮 code-rereview-adjudication 和 code-review-20261010-145106；使用 gateflow skill 的 implementation/fix 与风险分类。本轮用户明确将工作收窄为 doc fix 并要求交 root 后停止，不执行后续 gates。较低优先级文件中的冲突文字不覆盖系统/开发者约束。

动机成立：13 项直接文档证据存在缺失，不代表已有诊断功能出错。函数自己的 docstring 是参数、返回及异常契约的 owner；只在这些函数的首条文档表达式补全，不在生产、展示、fixture 行为或消费者增加兼容/补偿。C1 已经独立双路证明修复，本轮不更改其生产实现。

修改前用 Python hashlib 核验：manifest SHA256 `659353f68e31286995ce2b1981c3c5d6b0645d46511084e2a55af133813d4c38`；`code-rereview-01.patch` SHA256 `766f6cc8fcacf6bb373bae739f4b79323101f977697a2dd6486c2ffff1abf52b`；29/29 included_files hash 匹配；branch / HEAD 匹配。没有将后续 root owned 的 state、授权、拒绝和新 review artifacts 视为未知 dirty。

最小边界为七测试文件的 19 个中文 docstring：报告 R1 的 13 项，加同文件本次变更函数确有的六项缺口；不触碰未改历史函数。参数逐名匹配签名及实际含义。隐式 self/cls 沿项目既有文档惯例不作为调用者显式参数。helper 异常依据真实函数体及直接委托：CN/HK collector、固定 discovery 替身与取消检查、期间类型校验、runtime download 和 ValidatedFinsEventStream。未读取调用方 workflow、gate、审核包、范式或原生产数据。

## 逐函数修复

| 文件 | Qualified 函数 | 修复内容 |
| --- | --- | --- |
| `tests/cli/test_fins_commands.py:5199` | `test_cli_main_default_temporary_log_delivers_twelve_failures` | R1：逐名说明五个参数、None 返回及 AssertionError。 |
| `tests/cli/test_output.py:71` | `test_download_reference_literals_preserve_identity_and_terminal_rows` | 同类最小补全：两个无缺省 next 缺行时抛 StopIteration。 |
| `tests/cli/test_output.py:443` | `test_fins_download_failure_preserves_cli_text_bound_and_public_json` | 同类最小补全：无缺省 next 缺失败详情行时抛 StopIteration。 |
| `tests/cli/test_output.py:705` | `test_fins_cancel_without_download_keeps_original_prompt_and_channel` | R1：明确无参数、None 返回及 AssertionError。 |
| `tests/fins/test_cn_download_runtime.py:2606` | `_DiagnosticsWorkflowObserver.__call__` | R1：events/progress_sink 逐名说明；同对象返回；RuntimeError、CnDownloadIntegrityAbort、ValueError 及流/回调 BaseException 的透传范围。 |
| `tests/fins/test_cn_download_runtime.py:2625` | `_DiagnosticsPdfFailure.__init__` | 同类最小补全：failure 参数名及保存语义、None 返回、不主动抛异常。 |
| `tests/fins/test_cn_download_runtime.py:2636` | `_DiagnosticsPdfFailure.__call__` | R1：candidate 语义、不返回；Exception 保留注入实例身份，明列实际用例的 FinsDownloadProviderError/OSError/RuntimeError。 |
| `tests/fins/test_cn_download_runtime.py:2652` | `_DiagnosticsCandidateMetadata.__init__` | 同类最小补全：discovery 参数名与固定替身、None 返回、不主动抛异常。 |
| `tests/fins/test_cn_download_runtime.py:2662` | `_DiagnosticsCandidateMetadata.__call__` | R1：四参数逐名说明，年度截止日与取消检查用途；结果替换范围；CnDownloadCancelledError、回调 BaseException 和期间 TypeError/ValueError。 |
| `tests/fins/test_cn_download_runtime.py:2684` | `_DiagnosticsChangedHkCoverage.__init__` | 同类最小补全：discovery 参数名与固定替身、None 返回、不主动抛异常。 |
| `tests/fins/test_cn_download_runtime.py:2694` | `_DiagnosticsChangedHkCoverage.__call__` | R1：四参数逐名说明，年度截止日与取消检查用途；身份保持、覆盖变更；实际取消与类型校验异常。 |
| `tests/fins/test_cn_download_runtime.py:2739` | `_assert_workflow_row_diagnostics` | 同类最小补全：strict zip 三个序列长度不一致抛 ValueError；保留既有参数/返回/AssertionError。 |
| `tests/fins/test_cn_download_runtime.py:2819` | `_collect_diagnostics_runtime` | R1：runtime/request 语义、完整有序事件返回；ValueError/OSError/协议错误、上游 BaseException；StopAsyncIteration 被迭代消费。 |
| `tests/fins/test_download_failure_diagnostics.py:174` | `test_failures_after_first_ten_are_complete_and_same_source` | R1：明确无参数、None 返回及 AssertionError。 |
| `tests/fins/test_download_failure_diagnostics.py:321` | `test_cli_preserves_output_write_error` | R1：AssertionError 与 pytest.raises 失败情形；OSError 为期望被捕获写入错误，非成功测试的外抛异常。 |
| `tests/fins/test_fins_ingestion_runtime.py:10443` | `test_activation_submit_failure_terminalizes_prepared_observation` | R1：tmp_path/original_error 逐名说明；AssertionError；OSError/ValueError 是期望捕获的提交异常，不混作传播异常。 |
| `tests/fins/test_fins_ingestion_runtime.py:13107` | `test_download_cancel_preserves_downloaded_failed_prefix_and_claim` | R1：三个参数与三竞争时点；AssertionError；实际 wait_for 的 TimeoutError。 |
| `tests/service/test_fins_direct.py:1058` | `test_service_passes_same_stream_terminal_full_result` | R1：status 语义、None 返回及 AssertionError。 |
| `tests/service/test_fins_wait_adapter.py:1136` | `test_real_download_observation_wait_three_terminals_stay_bounded` | R1：tmp_path/status 逐名说明、None 返回及 AssertionError。 |

## 同一性证明及 README 决定

独立脚本对修改前快照与当前 15 个 Python 文件重新解析，按 qualified 名称识别类方法、异步函数及条件分支内嵌套函数：93 个本 unit 变更函数（23 production、70 tests）逐项去 doc AST 相同；全部函数 qualified 集合相同；整模块去 doc AST 相同。去 doc AST 保留签名、参数默认值、类型注解、装饰器、函数体、断言及嵌套逻辑。另以 AST 的 UTF-8 字节位置仅遮蔽 19 个文档表达式，七文件其它所有字节相同，证明不是只靠 AST 忽略格式。未改历史函数的完整 AST/doc 均保持原样。

29 文件中仅七测试文件的 hash 改变，剩余 22/29 全字节不变。下表为本轮前后相同的五生产文件与三个职责相关 README：

| 文件 | 前后相同 SHA256 |
| --- | --- |
| `README.md` | `72b719e57bf72c93904c3552e0f7c70e0af1ec89ce3aea16863f5344b2889c98` |
| `dayu/cli/output.py` | `9aa54696e8e67c5daaa721d5311052e5003c2c6c14c3520f5c8ff4c2bcdc97cd` |
| `dayu/fins/README.md` | `56528d24321899ec3e7cd4af6efa9ffc4f57302f4a049855bd8c9026e6eb30d8` |
| `dayu/fins/direct_events.py` | `490b45a03167facd825a6dc6cf586d0480db2119d588d998a99d82b471a4cf30` |
| `dayu/fins/download_contract.py` | `9c66c790a49095307391380c7ddd807b7655d0e3a5bf69aefd58e31185788dd3` |
| `dayu/fins/ingestion_runtime.py` | `94b19d4f1daa2e715bde2c000ff53ff49301fb7d68f6ce68b83633726f5bbad9` |
| `dayu/fins/pipelines/cn_pipeline.py` | `470f4fcaef4d264ae7a08f660e134dda4b9d7382810759b9cd36b91897124e2d` |
| `tests/README.md` | `dd4a86aa5bc5861e832e9a55928a7edb00570172fc00ce84273219a876138b94` |

已检查 tests README 开头职责：仅描述现有测试分层、运行及维护。本轮未改变这些事实、用户输出、工作流或生产接口，按用户冻结要求无需修改 README；根/Fins README 同样保持字节不变。没有跨层关系或 Host/Engine/Config 变更触发。

| 七文件 | 原测试函数定义数 | 新测试函数定义数 | 新 SHA256 |
| --- | ---: | ---: | --- |
| `tests/cli/test_fins_commands.py` | 83 | 83 | `126081e443f31d01c1dfaad28ccb8f82a48c179b95f49dbd7e36616ef15dcb08` |
| `tests/cli/test_output.py` | 11 | 11 | `d55234ecbf36bda81b9e969e4b0d8f2bd6c8a863ea77c763794953b4fe4d7941` |
| `tests/fins/test_cn_download_runtime.py` | 31 | 31 | `1a8a75f53b2fd728b0d03bf2873c8b638bf1c1283cf556e86deb028c3f02e0e6` |
| `tests/fins/test_download_failure_diagnostics.py` | 8 | 8 | `807fb2fc1e9bf3870efbeb5f63e4d02d9a88df78f7601eef8397973bffd53357` |
| `tests/fins/test_fins_ingestion_runtime.py` | 211 | 211 | `22b87456c31617154a6e8241221ee3df69e08307cc4916fe94f3acc034e2a2f1` |
| `tests/service/test_fins_direct.py` | 22 | 22 | `9208fa53f1f053f846309327461949f0b3f0cb6e23f547ce2cb8e415bc1b6421` |
| `tests/service/test_fins_wait_adapter.py` | 23 | 23 | `c83b2888bb909a23b498d6032d7244d2b6676b45a67ce54b98f2ac710f8a36c7` |

上述为 389 个函数定义，参数化后本轮实际执行 1003 个 case；未增加、删除测试或改装饰器。

## 验证：真实终态

命令直接执行并将双标准流写到本 unit 临时日志，没有管道、tee 或 `|| true` 吞掉 exit。托管 session 最后通过 write_stdin 取得真实进程终态，不以日志内容替代 exit。

```bash
source .venv/bin/activate
python -m pytest tests/cli/test_fins_commands.py tests/cli/test_output.py tests/fins/test_cn_download_runtime.py tests/fins/test_download_failure_diagnostics.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py -q > workspace/tmp/download-failure-diagnostics-20261010/doc-fix-pytest.log 2>&1
```

session 90877，真实 exit 0；1003 passed / 0 failed / 0 skipped / 3 warnings，103.93s。现有 fixture 与 fixed absolute CLI 的 fresh 根离线 rebuild 原样运行；不访问远端来源或原生产数据。三个 warning 来自 edgar 依赖弃用提示，不是业务失败。

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/ > workspace/tmp/download-failure-diagnostics-20261010/doc-fix-pyright.log 2>&1
```

session 20398，真实 exit 0；0 errors / 0 warnings / 0 informations。另有 pyright 版本升级提示，未升级工具、降低检查或加 ignore。

`python workspace/tmp/download-failure-diagnostics-20261010/doc-fix-audit.py` 实际 exit 0：19 doc / 93 unit functions / 22 unchanged manifest files；`git diff --check` 最终源检查实际 exit 0。

非零/边界事件如实记录：初次 doc 替换给空行加缩进，diff --check exit 2；随后只修正文档空行，复核 exit 0。一次异常类型定位 rg 在已知 cn_download_models 之外猜测了两个不存在的文件路径，exit 2；后续只读真实 cn_download_models 及取消函数完成补证。首次定位 goal/plan 时误枚举历史 docs 文件名，未读取其正文；后续仅明确 unit 路径。没有必要验证遗留失败、权限提升或自动审批拒绝；未发现需要本轮修改逻辑的新实际代码缺陷。

## 继承证据，非本轮重跑

已核 `code-fix-output-hashes.json` 的 15 个 Python end_sha256 与本轮修改前 manifest 完全一致，生产本轮字节不变，测试本轮去 doc AST 与其余字节不变，允许继承原 A1497 和生产 coverage。已核旧最终测试/pyright 日志 SHA256 与其真实终态归档一致。没有重复完整 A14、broad 或 coverage，不将继承验证写成本轮执行。

- 旧 final exact A14：session 2359，exit 0，1497 passed / 0 failed / 0 skipped / 3 warnings；日志 SHA256 `36dec5a0b4d99a3ade0051ce8a18242dcaf6a9871624eb4e014a6a33c0918adf`。
- 原生产覆盖率：output 85.58%、direct_events 90.23%、download_contract 88.42%、ingestion_runtime 91.23%、cn_pipeline 82.53%；逐文件均 ≥80%，原 excluded lines 沿用，未更改计算。逐文件 JSON SHA256 `fac8059a1eff484947f318563a3a1993ffbdd1c0bedad1d750555fab9f565fee`，完整 JSON `40b8ffe21ee8fd4530b222c7ed586792f7668daf166f4eed52c612e5ede98ebc`。
- 原验证档 `code-fix-validation.json` SHA256 `d0d39f761660f8c208ea7db3b0a3c552260bbeb6f66fdc2e16408f35d45b4d83`；源码映射 `code-fix-output-hashes.json` SHA256 `a5fd13efc1c97f84588f1dcb19f43a7bbbdc2ab8bfa73de1322a7139ea92bf16`。
- 67 baseline 失败 / 14 resource skip 沿 implementation-adjudication 与 baseline-validation 既有裁决，不宣称 broad 通过；未本轮复现或推断各项根因。
- C1 双路修复证明及旧 8 原因/日期未知只继承 root 已裁决证据；没有重新生产 query 或来源观测。

## 临时证据路径与 hash

全部临时脚本、快照、审计、delta 与日志位于 `workspace/tmp/download-failure-diagnostics-20261010/`，没有常驻 docs 校验框架：

| 文件 | SHA256 |
| --- | --- |
| `doc-fix-before.json` | `66cfa095a3fa6b726705a451b15749be7696f3ed101b713d3ad862c08b1b0aa3` |
| `doc-fix-functions-before.json` | `aa167a78ee182f4f71eef47fe62700fc2f2c06e580f03a26d7165e95eed8cd4a` |
| `doc-fix-edit.py` | `3190edaa1558f639cd535a0cbdf069d2680aadc6775dec39aacd553c06fa9ff6` |
| `doc-fix-edited-functions.json` | `f3aabc22a67bead09d0b927797aa65a80659dced3e534cc8074447b9cf422b0c` |
| `doc-fix-audit.py` | `7ecf290c7d47ea4d8a339f1888d088ee1d19d3421eefda04dabf6ac13905b788` |
| `doc-fix-audit.json` | `59d1883af5d938fa6676e248d04928c80d8a5f5227d48edb3b07e9f8c136dceb` |
| `doc-fix-delta.patch` | `c6b24a9267899c94a832f87899ae2732681c31e1ff5223183b705cc811b6d12e` |
| `doc-fix-pytest.log` | `a58f7dbea4c95e94c590b0d2828eb5b497104955a6eef0f775afb6cea2964c38` |
| `doc-fix-pyright.log` | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` |
| `doc-fix-validation.json` | `f0596e4e1b4c75c8791d0cb3630a395683b791f77cbdefb5eeb63dd86672ec4a` |

## 全部 93 个变更函数：逐项全文文档检查

先与冻结 base 作完整 qualified AST 对比得出 93 项，实际逐个读取完整签名及全文 doc，再按参数含义、返回语义、明确异常审核；不是仅关键词命中或 13 项抽样。下表保存逐函数检查结果；完整 doc、签名参数和返回注解在临时 `doc-fix-audit.json`。异常栏沿用当前 doc 全文语义；测试中 `pytest.raises` 期望的业务异常是被捕获的被测行为，不能据此当作成功测试的传播异常。所有测试均声明 AssertionError；失败检查可由 pytest 报告，不伪称期望异常必然外抛。无需触碰名单外文件或历史函数。


### `dayu/cli/output.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_print_terminal_business_summary` | result, stream：逐项含义已核 | ``None`` | OSError: 输出流写入失败时由底层 ``print`` 透传。 | 同一 |
| `_print_download_summary` | summary, stream：逐项含义已核 | ``None`` | OSError: 输出流写入失败时由底层 ``print`` 透传。 | 同一 |

### `dayu/fins/direct_events.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `FinsDownloadPublicSummary.from_result_summary` | summary：逐项含义已核 | 原序前十行及同源计数、筛选条件和未知报告预算投影 | ValueError: 公共摘要不符合计数或安全字段契约时抛出。 | 同一 |
| `_download_public_document` | row：逐项含义已核 | 保留全部业务字段、将相对定位符转换成文本的公共行 | ValueError: 公共字段违反安全文本契约时抛出。 | 同一 |
| `FinsResultSummary.__post_init__` | 无显式参数：逐项含义已核 | 无 | TypeError: download_result 或 warning 元素不符合 typed contract 时抛出。 ValueError: 摘要组合、有界摘要或任一完整失败行违反公共契约时抛出。 | 同一 |
| `FinsResultSummary.download` | 无显式参数：逐项含义已核 | 下载结果的有界公共投影；非下载结果为 None | 无。 | 同一 |
| `FinsResultSummary.to_download_diagnostics_json_value` | 无显式参数：逐项含义已核 | 同源有界摘要、无截断失败行和整体失败说明的 JSON 对象 | ValueError: 当前终态没有下载结果时抛出。 | 同一 |
| `FinsEvent.__post_init__` | 无显式参数：逐项含义已核 | 无 | ValueError: 事件字段组合非法或包含禁止投影内容时抛出。 | 同一 |

### `dayu/fins/ingestion_runtime.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `FinsIngestionRuntime.activate_observation` | handle：逐项含义已核 | 无 | Exception: executor submit 或 activation 内部异常会在 observation 被收口为 failed 后按原异常抛出。 | 同一 |
| `FinsIngestionRuntime._run_direct_stream_producer` | context, producer：逐项含义已核 | 无 | 无。异常会转成失败 RESULT。 | 同一 |
| `FinsIngestionRuntime._produce_direct_download` | context, normalized, request：逐项含义已核 | 无 | _UnsupportedDownloadSourceError: 没有匹配下载 adapter 时抛出。 ValueError: adapter 返回字段非法时抛出。 OSError: 仓储读写失败时抛出。 | 同一 |
| `FinsIngestionRuntime._run_download_job` | job_id, normalized, request：逐项含义已核 | 无 | 无。所有业务与运行时异常都会转换为 terminal job record。 | 同一 |
| `FinsIngestionRuntime._save_typed_download_failure` | job_id, request, exc：逐项含义已核 | 无 | 无。二次读写失败只记录固定安全事件。 | 同一 |
| `FinsIngestionRuntime._save_download_unsupported` | job_id, request, message：逐项含义已核 | 无 | 无。二次落盘失败只记录诊断。 | 同一 |
| `FinsIngestionRuntime._emit_direct_result` | context, status, details, error_kind, error_message, download_result, failure：逐项含义已核 | 无 | TypeError: 非下载事件字段类型违反公共契约时抛出。 ValueError: 非下载事件字段违反公共契约时抛出。 | 同一 |
| `FinsIngestionRuntime._emit_direct_cancelled_result` | context, download_summary：逐项含义已核 | 无 | 无。 | 同一 |
| `_direct_result_event` | context, status, details, error_kind, error_message, download_result, failure, warnings, emitted_at：逐项含义已核 | 已完成全部 typed contract 校验、尚未入队的 RESULT 事件 | TypeError: public event 字段类型不符合 contract 时抛出。 ValueError: public event 字段组合、长度或安全文本不符合 contract 时抛出。 | 同一 |
| `_direct_upload_terminal_events` | context, request, summary, disposition, emitted_at：逐项含义已核 | ``(progress, result)``；cancelled 的 progress 为 ``None``，其余终态 返回同一 disposition 派生且尚未入队的完整事件组 | TypeError: public event 字段类型不符合 contract 时抛出。 ValueError: 请求、摘要或 public event 投影不符合有界 contract 时抛出。 | 同一 |
| `_observation_failure_result` | operation_kind, download_request：逐项含义已核 | Fins result summary | ValueError: result 字段非法时由契约构造抛出。 | 同一 |
| `_observation_cancelled_result` | operation_kind, download_request：逐项含义已核 | Fins result summary | ValueError: result 字段非法时由契约构造抛出。 | 同一 |
| `_mark_observation_failed` | record, message：逐项含义已核 | 无 | ValueError: result 字段非法时由契约构造抛出。 | 同一 |
| `_cancelled_download_json_summary` | summary：逐项含义已核 | 只覆盖终态的有界新 schema JSON | typed 不变量或预算不足抛 ValueError。 | 同一 |

### `dayu/fins/pipelines/cn_pipeline.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_project_cn_document_row` | item, ticker, source_repository：逐项含义已核 | typed 单文档结果 | ValueError: 必填字段缺失、类型非法或 status 未封闭时抛出。 OSError: downloaded locator 查询失败时抛出。 | 同一 |

### `tests/cli/test_fins_commands.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_FakeFinsDirectService.__init__` | events, stream_error, close_error, pause_after_first_event：逐项含义已核 | ``None`` | Exception: 不主动抛出异常。 | 同一 |
| `_FakeFinsDirectService._stream` | command_operation_kind, cancellation_token, validator_operation_kind：逐项含义已核 | production validator stream | Exception: 不主动抛出异常。 | 同一 |
| `_FakeFinsDirectService._raw_stream` | operation_kind：逐项含义已核 | 未校验的 Fins raw event async generator | BaseException: stream_error 原样抛出；关闭失败保留为取消 cause 或原样抛出。 | 同一 |
| `test_live_fins_commands_render_progress_and_terminal_summary` | command_name, tmp_path, fake_service, capsys：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_fins_direct_debug_diagnostic_details_are_bounded` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `_result_event` | status, operation_kind：逐项含义已核 | fake result event | ValueError: 事件违反 direct contract 时抛出。 | 同一 |
| `test_fixed_cli_download_diagnostics_on_empty_rebuild` | tmp_path：逐项含义已核 | 无 | AssertionError: 实际退出码、唯一诊断行或新协议字段不满足预期时抛出。 subprocess.TimeoutExpired: 固定入口未在六十秒内退出时抛出。 | 同一 |
| `test_cli_main_default_temporary_log_delivers_twelve_failures` | tmp_path, monkeypatch, capsys, quiet, status：逐项含义已核 | 无（None） | AssertionError，完整性、原通道、退出码或流生命周期不满足断言时抛出。 | 同一 |
| `test_real_runtime_public_rejection_delivers_unique_safe_cli_diagnostic` | tmp_path, monkeypatch, capsys, index, typed_abort, race：逐项含义已核 | 无 | 终态丢失、错误通道、泄漏、非法事实或 claim 后投影时抛出 AssertionError。 | 同一 |
| `test_real_runtime_public_rejection_delivers_unique_safe_cli_diagnostic.controlled_claim` | state, status：逐项含义已核 | 原 owner 的终态或 None | 取消时点或请求终态错误时抛出 AssertionError。 | 同一 |

### `tests/cli/test_output.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_download_reference_literals_preserve_identity_and_terminal_rows` | cancelled, reference, has_existing_document：逐项含义已核 | 无 | AssertionError: 原引用、计数、通道、退出码或行结构发生改变时抛出。 :raises StopIteration: 缺少文档行或未知报告行、next 无匹配项时抛出。 | 同一 |
| `test_fins_download_cli_mechanically_projects_typed_public_summary` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_fins_download_failure_projects_typed_rows_missing_periods_and_recovery` | 无显式参数：逐项含义已核 | 无 | AssertionError: failure public object 被省略或进入错误输出通道时抛出。 | 同一 |
| `test_fins_download_failure_preserves_cli_text_bound_and_public_json` | hint, expected_hint：逐项含义已核 | ``None`` | AssertionError: 有界显示、空单元格、渠道或公共 JSON 发生漂移时抛出。 :raises StopIteration: 缺少失败详情行、next 无匹配项时抛出。 | 同一 |
| `test_fins_renderer_covers_progress_failure_cancel_and_error_helpers` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_fins_cancel_without_download_keeps_original_prompt_and_channel` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，取消提示、stderr 通道或空下载展示不满足断言时抛出。 | 同一 |

### `tests/fins/test_cn_download_runtime.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_cn_integrity_snapshot_has_separate_strict_projection_entry` | tmp_path：逐项含义已核 | 无 | AssertionError: status 或 row 校验被绕过时抛出。 | 同一 |
| `test_cn_legal_terminal_does_not_bypass_summary_validation` | tmp_path, entry, field_name, invalid_value：逐项含义已核 | 无 | AssertionError: 合法终态放宽其它契约时抛出。 | 同一 |
| `test_cn_adapter_summary_counts_are_derived_from_typed_rows` | tmp_path：逐项含义已核 | 无 | AssertionError: adapter projection 发生语义漂移时抛出。 | 同一 |
| `test_cn_adapter_rejects_invalid_required_coverage` | tmp_path, coverage_value：逐项含义已核 | 无 | AssertionError: 非法 workflow coverage 被接纳时抛出。 | 同一 |
| `test_cn_hk_adapter_local_rebuild_does_not_mutate_processed_documents` | tmp_path, source, market, ticker, exchange：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_cn_real_churn_preserves_success_prefix_and_stops_tail` | tmp_path, monkeypatch, entry：逐项含义已核 | 无 | 断言失败抛出 AssertionError。 | 同一 |
| `_DiagnosticsWorkflowObserver.__init__` | 无显式参数：逐项含义已核 | 无 | 无。 | 同一 |
| `_DiagnosticsWorkflowObserver.__call__` | events, progress_sink：逐项含义已核 | 委托收集函数返回的完整 workflow 结果对象 | RuntimeError，缺少完成事件或完成事件没有结果时由收集函数抛出； CnDownloadIntegrityAbort，工作流完整性中止时透传同一对象； ValueError，进度字段或回调拒绝投影时透传； BaseException，事件流或 progress_sink 的其它异常及取消保持原类型和对象透传。 | 同一 |
| `_DiagnosticsPdfFailure.__init__` | failure：逐项含义已核 | 无（None） | 无；只保存异常并初始化候选记录。 | 同一 |
| `_DiagnosticsPdfFailure.__call__` | candidate：逐项含义已核 | 不返回，始终抛出构造时传入的 failure | Exception，原样抛出保存的 failure，保留其实际类型和对象； 本组用例分别传入 FinsDownloadProviderError、OSError 或 RuntimeError。 | 同一 |
| `_DiagnosticsCandidateMetadata.__init__` | discovery：逐项含义已核 | 无（None） | 无；只保存该实例的候选查询方法。 | 同一 |
| `_DiagnosticsCandidateMetadata.__call__` | query, profile, local_annual_ends, cancellation_checkpoint：逐项含义已核 | 保留原 discovery 其它字段、替换候选报告日和期间投影的结果 | CnDownloadCancelledError，取消检查命中时保持同一对象透传； BaseException，cancellation_checkpoint 的其它异常保持实际类型和对象透传； TypeError / ValueError，期间投影构造违反类型或覆盖期间契约时抛出。 | 同一 |
| `_DiagnosticsChangedHkCoverage.__init__` | discovery：逐项含义已核 | 无（None） | 无；只保存该实例的候选查询方法。 | 同一 |
| `_DiagnosticsChangedHkCoverage.__call__` | query, profile, local_annual_ends, cancellation_checkpoint：逐项含义已核 | 候选身份不变、覆盖期间改为 FY 和 Q4 的 discovery 结果 | CnDownloadCancelledError，取消检查命中时保持同一对象透传； BaseException，cancellation_checkpoint 的其它异常保持实际类型和对象透传； TypeError / ValueError，期间投影构造违反类型或覆盖期间契约时抛出。 | 同一 |
| `test_hk_period_metadata_mismatch_is_real_failed_diagnostic` | tmp_path, monkeypatch：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `_assert_workflow_row_diagnostics` | result, workflow：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 ValueError，strict zip 的三个序列长度不一致时抛出。 | 同一 |
| `test_cn_hk_real_workflow_failure_reasons_reach_complete_diagnostics` | tmp_path, monkeypatch, source, category, expected_reason, message：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `_collect_diagnostics_runtime` | runtime, request：逐项含义已核 | 按流顺序收集的全部 FinsEvent，包括已验证的唯一终态 | ValueError，请求或公共字段非法时由 runtime 透传； OSError，仓储读写失败时由 runtime 透传； FinsDirectStreamProtocolError，缺少、重复终态或终态之后还有事件时抛出； BaseException，原始流的其它异常或取消保持实际类型和对象透传。 正常流耗尽的 StopAsyncIteration 由异步迭代消费，不向外传播。 | 同一 |
| `test_cn_hk_real_skip_and_hk_rebuild_keep_workflow_reason` | tmp_path, monkeypatch, source：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_cn_reason_owner_strictly_rejects_missing_empty_unsafe` | tmp_path, entry, status, field, value：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |

### `tests/fins/test_download_failure_diagnostics.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_document` | index, disposition, unknown：逐项含义已核 | 来源级文档结果 | ValueError: 固定事实违反下载契约时抛出。 | 同一 |
| `_download_summary` | failed, skipped, downloaded, source, unknown：逐项含义已核 | 下载 owner 派生计数的完整结果 | ValueError: 候选不满足下载契约时抛出。 | 同一 |
| `_terminal` | summary, status：逐项含义已核 | 唯一完整下载结果的 direct 终态 | ValueError: 终态组合不符合 owner 契约时抛出。 | 同一 |
| `_event` | result, operation：逐项含义已核 | 校验后的事件 | ValueError: 操作与结果违反 owner 约束时抛出。 | 同一 |
| `test_result_owner_rejects_unsafe_complete_failed_projection` | index, field：逐项含义已核 | 无 | 拒绝边界迟于构造或只检查前十行时抛出 AssertionError。 | 同一 |
| `test_accepted_result_consumers_reuse_validated_projection` | monkeypatch, status：逐项含义已核 | 无 | 投影重建、原事实改变或完整失败行丢失时抛出 AssertionError。 | 同一 |
| `test_failures_after_first_ten_are_complete_and_same_source` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，完整失败数量、顺序、同源字段或摘要预算不满足断言时抛出。 | 同一 |
| `_expected_row` | row：逐项含义已核 | 预期字段和值 | 无。 | 同一 |
| `test_complete_diagnostics_across_sources_counts_and_unknowns` | failed, source, unknown：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_event_owner_rejects_download_result_missing_and_wrong_typed_value` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_event_owner_rejects_download_result_for_other_operations` | operation：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_cli_delivers_one_complete_reversible_line_on_original_channel` | status, failed, downloaded：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `_BrokenOutput.write` | text：逐项含义已核 | 不返回 | OSError，始终模拟写入失败。 | 同一 |
| `test_cli_preserves_output_write_error` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，捕获到的 OSError 文本不符合匹配预期时抛出； 未抛出期望异常时 pytest.raises 使测试失败。 OSError 是本测试期望并捕获的写入异常，不是成功测试向外传播的异常。 | 同一 |

### `tests/fins/test_f5_result_contract.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_public_and_durable_share_unknown_budget_and_conserve_counts` | known, unknown, id_chars：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |

### `tests/fins/test_f5_workflow_rebuild.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_actual_adapter_observation_wait_and_cli_keep_a_and_unknown` | tmp_path, monkeypatch, cancel_after_a, unknown_source_id：逐项含义已核 | 无 | AssertionError: 原引用、A/B 计数、终态或行结构漂移、wait 读 job 时抛出。 | 同一 |

### `tests/fins/test_fins_direct_stream.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_result_summary` | 无显式参数：逐项含义已核 | success 终态摘要 | ValueError: 固定测试数据违反结果契约时抛出。 | 同一 |

### `tests/fins/test_fins_ingestion_runtime.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_public_download_json_preserves_cn_coverage_and_sec_empty_array` | 无显式参数：逐项含义已核 | 无 | AssertionError: CN coverage 被重算或 SEC 空数组缺失时抛出。 | 同一 |
| `test_direct_download_projects_typed_provider_failure_without_raw_cause` | tmp_path：逐项含义已核 | 无 | AssertionError: failure 分类、空摘要或脱敏边界漂移时抛出。 | 同一 |
| `test_failed_operation_accepts_only_valid_processed_document_dispositions` | 无显式参数：逐项含义已核 | 无 | AssertionError: 组合校验越过文档或整体状态所有权时抛出。 | 同一 |
| `test_direct_result_builder_callsites_are_exact_and_never_rewrite_warnings` | 无显式参数：逐项含义已核 | 无 | AssertionError: callsite 数量、实参或 helper 内 warning 重写发生漂移时抛出。 OSError: production 源码读取失败时抛出。 SyntaxError: production 源码无法解析时抛出。 | 同一 |
| `test_activation_submit_failure_terminalizes_prepared_observation` | tmp_path, original_error：逐项含义已核 | 无（None） | AssertionError，异常对象身份、空下载事实或安全终态不满足断言时抛出； 未抛出 original_error 对应类型时 pytest.raises 使测试失败。 注入的 OSError 或 ValueError 由 pytest.raises 捕获，不是成功测试向外传播的异常。 | 同一 |
| `_assert_empty_request_download` | summary, request：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_cancel_prepared_download_preserves_request_and_never_submits` | tmp_path：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_unexpected_activation_exception_terminalizes_prepared_observation` | tmp_path：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_sec_integrity_failure_public_and_job_conservation` | tmp_path, scenario, mode, caplog：逐项含义已核 | 无 | 断言失败抛出 AssertionError。 | 同一 |
| `test_download_cancel_preserves_downloaded_failed_prefix_and_claim` | tmp_path, monkeypatch, mode：逐项含义已核 | 无（None） | AssertionError，守恒、唯一终态或竞争 barrier 不满足断言时抛出； TimeoutError，asyncio.wait_for 等待事件收集超过三秒时抛出。 | 同一 |
| `test_download_cancel_preserves_downloaded_failed_prefix_and_claim.controlled_claim` | state, status：逐项含义已核 | 原 owner 裁决的终态或 None | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_download_runtime_full_result_and_durable_budget_same_source` | tmp_path, case：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |

### `tests/service/test_fins_direct.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `_result_event` | status, operation_kind：逐项含义已核 | Fins direct result 事件 | ValueError: 事件违反 direct contract 时抛出。 | 同一 |
| `test_service_passes_same_stream_terminal_full_result` | status：逐项含义已核 | 无（None） | AssertionError，Service 重建、截断或替换下载事实，或流身份不满足断言时抛出。 | 同一 |

### `tests/service/test_fins_wait_adapter.py`

| Qualified 函数 | 参数检查 | 返回检查 | 明确异常检查 | 去 doc AST |
| --- | --- | --- | --- | --- |
| `test_fins_wait_adapter_projects_same_typed_download_object` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_fins_wait_adapter_failure_contains_same_typed_download_and_failure` | 无显式参数：逐项含义已核 | 无（None） | AssertionError，既定断言或测试前提不满足时抛出。 | 同一 |
| `test_real_download_observation_wait_three_terminals_stay_bounded` | tmp_path, status：逐项含义已核 | 无（None） | AssertionError，wait 扩容、终态改变、结果身份或同源 omission 不满足断言时抛出。 | 同一 |

## Finding 状态、五类风险及交接

C2/R1 的 13 项及同边界六项已完成 doc 修复候选，13/13 目标覆盖；本 fix 自核无剩余同类文档缺项。**仍须 root 授权的 gpt-6-astra / 另一 ds-flash 独立 re-review 验证，根控制状态及最终 finding 裁决归 root。**本报告不宣称 slice/work unit pass。C1 沿既有双路已修结论，生产未改。

| 风险 | Gateflow 五类规范分类 | Owner / destination 与限制 |
| --- | --- | --- |
| C2/R1 文档缺项及本轮六项同类补全 | fixed in current slice | S1 doc fix，当前修复候选，必须由 root 双路 re-review；分类不是 gate 放行。 |
| C1 公共受理/claim | fixed in current slice | S1 public contract/runtime owner；沿既有两路与 root 证明，生产字节不变。 |
| 后续批准 slice | covered by later approved slice | N/A；没有后续 approved slice 代替本 C2 收口。 |
| 67 baseline 失败 | assigned to later work unit | Dayu CLI/Service 维护；destination 沿 baseline-validation 所列六文件及真实装配/grammar/init/import 约束 owner。 |
| 14 外部资源/平台 skip | assigned to later work unit | Dayu 集成验证 owner；后续真实资源验收 work unit，未计本轮通过。 |
| SEC 原因治理 | assigned to later work unit | Dayu 来源/公共契约维护侧；后续 SEC 原因 owner work unit，未扩大当前原因保真承诺。 |
| 极端规模内存、输出和 repr | assigned to later work unit | Dayu 性能维护侧；沿 implementation-adjudication 的后续性能 work unit，未作压力验证。 |
| 既有 issue | tracked by existing issue | N/A；没有 issue 或 design doc，不自行建 issue。 |
| 旧 8 原因/日期未知；新观测/生产下载/recovery；未捕获/崩溃历史追溯 | requiring new issue or explicit user decision | 巡检线/用户另定范围；既有如实未知授权沿用，不推导新观察授权。 |
| 双原因治理扩范围及 merge/部署等外部动作 | requiring new issue or explicit user decision | 巡检线及 Dayu 相应公共契约维护侧/用户；沿既有 owner，不顺手改业务。 |

没有未分类风险。当前未覆盖：真实远端、原生产数据、原 8 原因恢复、资源平台实证、极端规模、历史 durable 诊断与部署/合并。本轮没有 commit/stage/push/PR/merge/approve/ready/comment，没有修改 goal/plan、旧报告/证据或 root 控制 artifacts，没有派发 re-review。

本 doc fix 完成并停止。下一未完成入口：root 组织授权的双路 re-review，检查本 19 文档、全 93 文档及去 doc/字节同一性、真实测试/type 日志和继承边界；最终是否关闭 C2/R1 与当前 slice 由 root 裁决。
