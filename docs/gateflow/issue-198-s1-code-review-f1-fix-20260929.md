RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-e1838ce7

# Issue #198 S1 code review → fix：MiMo F1

## 基线、判断与边界

- 工作区：`/Users/leo/workspace/dayu-agent-r`。起始 `git diff --binary -- <S1 14 文件> | shasum -a 256` 为 `f2766de5d4deb8ebfd922854892e575829d578bbd4faa2e03f38e0351239d448`，与派发基线一致；未覆盖其它 WU 的 dirty hunk。结束时同一 14 文件 diff 的 SHA-256 为 `86aa9a2bdecdd4f9f817c555cf2eb94da668f9329a264428e192bf91f07b8cb5`。
- 已读 `AGENTS.md`、accepted plan、MiMo S1 review、总控裁决、两份实施记录，以及 CN 仓储、workflow、adapter、runtime 和既有 owner 测试调用链。MiMo F1 的动机成立，但范围是缺少回归锁定，当前生产投影代码本身没有被证据证明错误。仓储拥有 source 状态，workflow 拥有已处理 filing 快照，adapter 严格投影该快照，runtime 独占公共失败分类和 direct/job 投影；只在其真实路径上补测。
- 唯一修改的既有文件是 `tests/fins/test_cn_download_runtime.py`；新增本记录。未改生产代码、其它测试、README、accepted plan、旧实施记录、review、裁决或队列；未进入复审、commit、push、PR 或 S2。`tests/README.md` 已检查：现有下载终态测试说明涵盖 post-repair 已处理快照和 direct/job；本次仅补该行为的回归，无新的用户可见测试类别，且派发明确禁止修改该文件。

## F1 修复与 owner 证据

`test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary` 对 `direct`/`job` 参数化。先用真实文件系统仓储和 `CnDownloadAdapter` 发布两个不同身份财期的 selected filing；通过仓储 locator 定位两个实际 PDF，只将第一份改为待 repair。在真实 `list_source_integrity` 第二次调用，即第一份 repair 已确认、post-repair 分类之前，才改变第二份 PDF 字节；wrapper 始终委托真实仓储枚举，没有构造 classification、异常、adapter failure 或 public result。测试实测第二份状态为 `REPAIR_REQUIRED`、调用恰两次、第一份 PDF 已修复，第二份保持新字节、company meta 保持旧值。

真实 workflow 因另一 selected source 变坏触发 `SourceIntegrityRevisionConflictError`，真实 adapter 包装已验证的单 filing 摘要，真实 runtime 的 direct 唯一 RESULT / job failed record 均保留 repair filing ID、`terminal_disposition=succeeded` 与 `discovered=downloaded=1`、其它 disposition 计数为零。direct 的 `error_kind` 和 `failure.kind` 均为既有 `EXECUTION`，`failure.reason_code is None`，错误与公共安全消息均为“下载执行失败”；job 的 `failure_summary` 恰为 `{"message": "下载执行失败"}`，没有原异常文本、路径或臆造公开 reason。已发布两份 source meta 仍可由仓储读取。该测试不把 workflow cause-only 断言或手工公共失败对象当成端到端证据。

## 本次实际验证

所有命令均在 `/Users/leo/workspace/dayu-agent-r` 执行。`exec_command` 返回合并的命令输出，未另行重定向 stdout/stderr，所以下列摘要不伪称可区分两个流；没有测试失败 traceback。非零命令：无。

| 命令 | exit | 实际合并输出摘要 |
| --- | ---: | --- |
| `source .venv/bin/activate && python -m pytest tests/fins/test_cn_download_runtime.py -k second_source_revision_conflict -q` | 0 | `2 passed, 38 deselected, 3 warnings in 1.43s`。三条警告为 edgar 第三方 deprecated import。 |
| `source .venv/bin/activate && python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | `846 passed, 3 warnings in 18.38s`；同三条 edgar 弃用警告。 |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | 0 | `0 errors, 0 warnings, 0 informations`；另有 pyright `v1.1.409 -> v1.1.414` 更新提示。 |
| `source .venv/bin/activate && COVERAGE_FILE=/private/tmp/issue198-s1-f1-coverage-20260929 python -m coverage run --branch --source=dayu.cli.output,dayu.fins.direct_events,dayu.fins.ingestion_runtime,dayu.fins.pipelines.cn_download_workflow,dayu.fins.pipelines.cn_pipeline,dayu.service.fins_wait_adapter -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -k 'not test_direct_consumer_task_cancel_waits_for_producer_cleanup_and_thread_join and not test_task_cancellation_closes_runtime_stream' -q` | 0 | `613 passed, 2 deselected, 3 warnings in 12.71s`；同三条 edgar 弃用警告。 |
| `source .venv/bin/activate && COVERAGE_FILE=/private/tmp/issue198-s1-f1-coverage-20260929 python -m coverage report -m` | 0 | 六个生产文件的 statement+branch 覆盖率如下，总计 88%。 |
| `git diff --check -- tests/fins/test_cn_download_runtime.py` | 0 | 无输出，无空白错误。 |

| 生产文件 | 测试新增后重跑覆盖率 |
| --- | ---: |
| `dayu/cli/output.py` | 81% |
| `dayu/fins/direct_events.py` | 84% |
| `dayu/fins/ingestion_runtime.py` | 87% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 92% |
| `dayu/fins/pipelines/cn_pipeline.py` | 92% |
| `dayu/service/fins_wait_adapter.py` | 92% |

覆盖采集沿既有实施记录排除两项插桩下时序敏感的取消用例；它们在本次未插桩的八文件 suite 中通过。这是覆盖运行的限制，不把覆盖运行称为完整八文件 suite。新增回归只锁定 post-repair 第二 selected source 的此条 revision conflict 路径；mid-filing revision conflict 和其它已登记残余仍按 accepted plan 的边界处理。F1 已补测，S1 gate 是否通过留待总控后续复审裁决。

## 总控结构化执行核对

上述「非零命令：无」是实施者对验证命令的描述，**不是整段子 Agent 执行日志事实**。总控检查 JSONL，进程 exit0、`turn.completed`、canary `gpt-6-sol-e1838ce7` 匹配，stderr 空，最终测试/pyright/coverage 均通过；但第 60 条 command execution `rg -n -A 22 -B 2 'Agent更新约束' tests/README.md` 因无匹配 exit1。严格按 sub-agents 协议，本派发 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, retry_class=none`，只能将测试 diff 与本记录作为待独立复审候选。该查询失败不证明 README 规则缺失或产品失败；总控另按 AGENTS.md 触发规则判断本次仅补既有测试种类、不需 README 正文改动。S1 code gate 仍待双路有效 re-review。
