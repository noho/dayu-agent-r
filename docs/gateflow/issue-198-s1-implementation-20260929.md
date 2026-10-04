RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-551d1adc

# Issue #198 S1 实施记录（2026-09-29）

## 基线、边界与结论

- 工作区：`/Users/leo/workspace/dayu-agent-r`。HEAD 及 accepted plan commit 均为 `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`；未提交、暂存、push、创建 PR 或进入评审 gate。
- 已先读 `AGENTS.md`、`docs/gateflow/issue-198-download-failure-projection-plan-20260928.md` 全文、`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`，并核对工作树候选和语义 owner。S1 的动机成立：typed 来源完整性错误在下载链路中会被文档级宽泛异常吞掉或投影成普通执行失败，且已确认文档与请求级失败的摘要所有权不同。
- owner 边界：存储层仍产生 typed 完整性事实；CN/HK 下载 workflow 负责已处理文档的事实快照；pipeline adapter 将原 typed cause 与同源快照送到 ingestion runtime；runtime 负责操作状态、持久摘要与 public failure；wait adapter 与 CLI 仅消费公共投影。首候选前没有已处理文档时，使用请求级 `FAILED` 零摘要。post-repair 中止保留此前已确认 filing 的快照，即使其文档终态为 `SUCCEEDED`，操作仍是 `FAILURE`。O34 文档成功与公司状态是独立事实；未从文档结果推断 company 成功。
- S1 代码、owner 测试和相关 README 已完成；计划指定窄日期 CLI baseline 的“发现至少一篇 filing”前提未满足，故该项仍有明确 validation gap。补充宽日期的真实 CLI 双流验证已完成，不将它冒充窄日期验收。

## S1 改动与最终 diff

| 边界 | 文件 | 改动 |
| --- | --- | --- |
| 公共失败契约 | `dayu/fins/direct_events.py` | 结构化 `reason_code`；允许整体失败与已确认文档 `SUCCEEDED` / `PARTIAL_FAILURE` / `FAILED` 快照共存，拒绝矛盾的取消状态。 |
| ingestion owner | `dayu/fins/ingestion_runtime.py` | typed cause 与已验证摘要随 adapter 传递；首候选前零摘要；direct/job 同源投影与安全持久化；次生写失败仅固定诊断，不泄露原始异常。 |
| 下载 owner | `dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py` | 真实预检及 post-repair typed 中止；已确认 filing 快照严格投影；保留原始 typed cause；首候选前 whole-kind/company 原错传递。 |
| 消费者 | `dayu/service/fins_wait_adapter.py`、`dayu/cli/output.py` | wait 同帧说明整体失败与文档快照范围；CLI 将公共码标为 `reason_code=`，文档行 `reason=` 维持其既有含义。 |
| owner 测试 | `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、`tests/cli/test_output.py`、`tests/service/test_fins_wait_adapter.py` | 覆盖真实存储注入、CN/HK direct/job、首候选前与 post-repair、契约拒绝、持久化和消费者双流。 |
| README | `README.md`、`dayu/fins/README.md`、`tests/README.md` | 按各 README 的更新约束补 S1 可见语义与测试范围。`dayu/README.md` 已检查，本次未改分层/装配关系。 |

上述 14 个有改动的 tracked 文件均在计划 S1 白名单内；白名单中的 `tests/service/test_fins_direct.py` 用作验证，未改动。新建的本记录是任务明确要求的交付文件。`git diff --stat -- <S1 白名单>` 为 **14 files changed, 1904 insertions(+), 65 deletions(-)**；`git diff --binary -- <S1 白名单> | shasum -a 256` 为 `f2766de5d4deb8ebfd922854892e575829d578bbd4faa2e03f38e0351239d448`（不含本新文件）。`git diff --check` 退出码 0。工作树原有其它 WU 的 tracked/untracked 修改及 `docs/gateflow/issue-198-s1-implementation-20260928.md` 均未触碰；未实施 S2 helper、泛异常发布不确定性或其它 WU。

## K-F1 与 owner 证据

- `tests/fins/test_cn_download_runtime.py::test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary` 的 direct/job 两个参数情形使用 fresh ticker。注入前在真实 batch state 上断言 `company_meta_intent is not None`，再把非点文件写入 staged filings root。
- wrapper 调用真实 `FsBatchingRepository.commit_batch`，并由包装的真实 `_validate_complete_source_tree` 计数，两个调用均为 1；typed `SourceIntegrityPreflightError` 从该真实路径抛出。断言目标公司目录尚不存在，因此是物理 swap 前的 durable 边界，而非 spy 伪造 typed。注入仅用于制造受控损坏，不替代生产校验。
- direct 与 job 都得到整体 `FAILED`、请求级零摘要、没有虚构 filing 行和安全的 public failure；job 的持久摘要与该零摘要完全相同。该测试也确认 discovery/download 尚未启动。
- Phase B、post-repair 分类器/公司提交、另一 selected source 的 revision conflict 均有独立 owner 测试；首候选前 whole-kind 另有 direct/job 真实存储测试。Phase A revision conflict 的继续处理仅有受控注入测试，不将其说成真实并发重现。

## 验证命令与结果

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `source .venv/bin/activate && python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | 844 passed，3 条第三方 edgartools 弃用警告。 |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | 0 | 0 errors、0 warnings、0 informations；仅版本升级提示。 |
| `source .venv/bin/activate && COVERAGE_FILE=/private/tmp/issue198-s1-coverage-final4 python -m coverage run --branch --source=dayu.cli.output,dayu.fins.direct_events,dayu.fins.ingestion_runtime,dayu.fins.pipelines.cn_download_workflow,dayu.fins.pipelines.cn_pipeline,dayu.service.fins_wait_adapter -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -k 'not test_direct_consumer_task_cancel_waits_for_producer_cleanup_and_thread_join and not test_task_cancellation_closes_runtime_stream' -q && COVERAGE_FILE=/private/tmp/issue198-s1-coverage-final4 python -m coverage report --skip-covered` | 0 | 611 passed、2 deselected；按 statement+branch 统计见下表。两项取消时序测试在上方普通完整 suite 中通过；覆盖插桩下发生时序失败，未将其计入覆盖通过。 |
| `git diff --check` | 0 | 无空白错误。 |

| 生产文件 | 覆盖率 |
| --- | ---: |
| `dayu/cli/output.py` | 81% |
| `dayu/fins/direct_events.py` | 84% |
| `dayu/fins/ingestion_runtime.py` | 87% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 92% |
| `dayu/fins/pipelines/cn_pipeline.py` | 92% |
| `dayu/service/fins_wait_adapter.py` | 92% |

## 真实 CLI：baseline-first 与双流

隔离 base 为 `/private/tmp/issue198-cli.X853oX`，运行前为全新目录，未初始化工作区。计划窄日期命令：

```sh
.venv/bin/dayu-cli --base /private/tmp/issue198-cli.X853oX download --ticker 000333 --forms FY --start 2025-03-28 --end 2025-03-28 --log-file /private/tmp/issue198-cli.X853oX/baseline.log > /private/tmp/issue198-cli.X853oX/baseline.stdout 2> /private/tmp/issue198-cli.X853oX/baseline.stderr
```

退出码 0，但 `discovered=0`，没有 `portfolio/000333/filings/`；因此计划要求的窄窗口 baseline 前提未成立，不能声称该项验收通过。为检查真实路径，改用同一隔离 base 的宽窗口：

```sh
.venv/bin/dayu-cli --base /private/tmp/issue198-cli.X853oX download --ticker 000333 --forms FY --start 2024-01-01 --end 2026-12-31 --log-file /private/tmp/issue198-cli.X853oX/diagnostic-wide.log > /private/tmp/issue198-cli.X853oX/diagnostic-wide.stdout 2> /private/tmp/issue198-cli.X853oX/diagnostic-wide.stderr
```

退出码 0，`discovered=3`、`downloaded=3`，真实目录具有 `.identity.json`、`meta.json` 与 PDF/Docling 产物。随后在实际 filings root 创建 `issue198-foreign-root.bin`，以相同宽窗口运行：

```sh
.venv/bin/dayu-cli --base /private/tmp/issue198-cli.X853oX download --ticker 000333 --forms FY --start 2024-01-01 --end 2026-12-31 --log-file /private/tmp/issue198-cli.X853oX/typed-failure.log > /private/tmp/issue198-cli.X853oX/typed-failure.stdout 2> /private/tmp/issue198-cli.X853oX/typed-failure.stderr
```

预期退出码 1。stdout 仅有 `preparing`、`started` 进度行；stderr 为安全的 `Fins failure`、零摘要及 `Fins failure detail`，其中 `classification="storage" source="cninfo" transport="-" reason_code="unsafe_publication"`，并给出修复工作区来源状态的建议。普通日志仅有进入下载流程的 INFO，不含 typed 内部路径、URL、token 或原始异常细节。CLI 实测确认 `reason_code=` 双流落点；测试另断言文档行仍使用 `reason=`。隔离目录在记录结果后删除。

## 失败命令原样记录

以下非零命令均保留原样及原因；其中测试/类型检查的早期失败已修复，真实 CLI 的非零为预期业务失败或窄窗口验收缺口。

| 原命令 | 退出码与处理 |
| --- | --- |
| `source .venv/bin/activate && python -m pytest tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py -q` | 1；旧 CLI `reason=` 断言与新公共 `reason_code=` 冲突，已更新测试。 |
| `source .venv/bin/activate && python -m pytest tests/fins/test_cn_download_runtime.py -k initial_company_commit_real_preswap -q` | 1；首次包装的方法归属于 shared core 而非 repository，已改为真实 core 校验路径。 |
| `source .venv/bin/activate && python -m pytest tests/fins/test_cn_download_workflow.py -k phase_b_real_preflight tests/fins/test_cn_download_runtime.py -k 'phase_b_real_preflight or real_phase_b_abort' -q` | 1；目标目录缺 descriptor 的实际异常为 `ValueError`，已纠正断言。 |
| `source .venv/bin/activate && python -m pyright tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py` | 1；测试对 `JsonValue` 的索引类型错误，已修复；最终完整 pyright 为 0。 |
| `rg --files --hidden /private/tmp/issue198-cli.X853oX/portfolio/000333/filings` | 1；窄窗口 baseline 无 filing 目录，形成上述 validation gap。 |
| `source .venv/bin/activate && COVERAGE_FILE=/private/tmp/issue198-s1-coverage python -m coverage run --branch --source=dayu.cli.output,dayu.fins.direct_events,dayu.fins.ingestion_runtime,dayu.fins.pipelines.cn_download_workflow,dayu.fins.pipelines.cn_pipeline,dayu.service.fins_wait_adapter -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q && COVERAGE_FILE=/private/tmp/issue198-s1-coverage python -m coverage report -m` | 1；568 passed、2 个取消时序测试仅在 coverage 插桩下失败；最终普通 suite 通过，最终覆盖命令明确排除并记录。 |
| `rg -n 'fins\.download\.|unsafe_publication|secret|token|/private/tmp/issue198-cli|https?://' /private/tmp/issue198-cli.X853oX/typed-failure.log` | 1；无匹配，符合普通日志不泄露的预期。 |
| `.venv/bin/dayu-cli --base /private/tmp/issue198-cli.X853oX download --ticker 000333 --forms FY --start 2024-01-01 --end 2026-12-31 --log-file /private/tmp/issue198-cli.X853oX/typed-failure.log > /private/tmp/issue198-cli.X853oX/typed-failure.stdout 2> /private/tmp/issue198-cli.X853oX/typed-failure.stderr` | 1；人工制造 typed source preflight 失败的预期退出码。 |

另有一次 `ps -ww -o pid,ppid,etime,stat,comm -ax | rg 'dayu-cli|docling|python' | tail -n 15` 在受限环境输出 `zsh:1: operation not permitted: ps`（管道最终退出码 0）；不影响已完成 CLI 进程结果。一次 `apply_patch` 因上下文不匹配被拒，随后按真实上下文应用；未改变工作树其它 hunk。

## 残余与交接

- 精确窄窗口的真实 baseline 未发现候选，故未满足该条完整 CLI 验收；宽窗口结果仅是补充证据。若总控需要该日期上的正式验收，须先确认可用 filing 来源/日期，不得把零发现写成成功。
- coverage 插桩改变两个取消时序测试结果，普通测试已通过；这两个用例的插桩敏感性可另行调查，不属于 S1 语义修复。
- 泛异常发布不确定性、物理 swap 后 typed durable 边界、S2 调用栈 helper 仍在计划边界外；本次没有为它们添加 fallback 或声称覆盖。
