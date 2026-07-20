# WU-SEMANTIC-OWNERSHIP-01 aggregate regression final validation — AgentCodex

## 1. 范围、裁决与 verdict

- Umbrella WU：WU-SEMANTIC-OWNERSHIP-01；未新建 WU。
- Gate：fresh aggregate regression validation only；不做 code review，不写产品修复。
- 唯一写入：本 artifact。
- Verdict：PASS_LOCAL_AGGREGATE_VALIDATION。
- 本地 release 结论：AR-F01—AR-F05 已用当前 tree 的 fresh 证据关闭；AR-F06 保持 RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX；AR-F07 保持 PENDING_RELEASE_BLOCKER，未触发真实 Windows。
- Provider 结论：遵循固定用户裁决，没有新增任何真实 LLM provider 请求。R03 与 real compactor 的本地 deterministic contract fresh PASS；真实 provider 部分为 NOT_RERUN_BY_FIXED_NO_NEW_PROVIDER_REQUEST_DECISION，继续按 NO_CODE / NON_BLOCKING 管理，不冒充 fresh provider success。
- 缺陷结论：未发现新的真实 product / test / README defect，不需要停交 Controller 处理产品修复。

## 2. 已完整读取的真源

以下文件均读取至 EOF：

| 文件 | 行数 | 结果 |
| --- | ---: | --- |
| AGENTS.md | 128 | PASS |
| docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md | 731 | PASS |
| docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md | 881 | PASS；重点复核 §7/§8/§9 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md | 40 | PASS |
| phaseflow SKILL.md | 完整 | PASS；仅用于遵守同一 WU 的 gate/control 约束，未派发 subagent |

固定裁决在本轮保持不变：

- Config 与 Host internal SQLite/EventLog 是 trusted local domain。
- API key/header 明文仅在 Tool Trace、audit、public、LLM-facing、logs、outputs、diff、reviews 要求为零。
- 不设计 secret infrastructure 或统一 authorization。
- Gemini quota/provider adherence 是 NO_CODE / NON_BLOCKING；未改 config/model/key/retry/quota/budget。
- AR-F06 保留原 owner/status；AR-F07 不关闭。
- Issues 142/151/175/177/178 与 Topic 8/9 均未实施。

## 3. Immutable baseline 与工作区保护

| 项目 | Fresh 结果 |
| --- | --- |
| branch | phaseflow/host-issues-control |
| HEAD | 85aa7184a694448a5b27da7cca52f753f84d6e20 |
| tree | 0db1c91f92dca594cf77c74bbde8f5b4fc42710d |
| aggregate parent | 3410d7422655c56bdf13c643f77c27f40b9d4550 |
| review range | b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20 |
| changed production Python | exact 219 |
| staged | empty |

Controller-owned entry hashes与封口前 hashes相同：

| 路径 | SHA-256 |
| --- | --- |
| docs/host/issues-implementation-control.md | a3f899dcd9f8c62927aa87e34cd4539a2e227cc8d0559dc7c95309f5f9872a61 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md | 2b1704bead5baf7e03a13be8d48655d46225df9f390704f496c72d2e58c796fc |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md | c6d368b6274605ceb86cde8393f2bab5f94a01c1f775b9cc52ed3c5b5dfb7c58 |

## 4. Fresh 命令 ledger

说明：下表记录本轮实际 validation/evidence 命令。exit 1 的 canonical zero-match rg 是预期 PASS；Ruff exit 1 是 immutable baseline findings 的工具原生结果，按 normalized delta 判定；其余非零均在“结果”列明确分类。

| ID | 命令 | exit / 结果 |
| --- | --- | --- |
| C001 | wc -l 与 sed 分段完整读取四份授权真源及 phaseflow SKILL.md | 0；读至 EOF |
| C002 | git branch --show-current；git rev-parse HEAD；git rev-parse HEAD^{tree}；git status --short；git diff --cached --name-status | 0；baseline 精确匹配，staged empty |
| C003 | git diff --name-only --diff-filter=ACMR 3410d742... HEAD -- dayu/**/*.py；sort -u；wc -l | 0；219 |
| C004 | pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli | 0；5260 passed, 10 skipped, 5 deselected, 3 warnings, 170.88s |
| C005 | pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task | 0；唯一完整 node，1 test collected |
| C006 | pytest -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task | 0；1 passed, 0.31s |
| C007 | COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage python -m coverage erase | 0 |
| C008 | COVERAGE_FILE=... python -m coverage run --branch -m pytest canonical dirs --deselect=exact AR-F06 node | 0；5259 passed, 10 skipped, 6 deselected, 3 warnings, 185.20s |
| C009 | COVERAGE_FILE=... python -m coverage json -o workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json | 0；coverage.py 7.13.5，676 measured files |
| C010 | jq 按 covered_lines / num_statements 连接 exact 219 changed paths | 0；219/219 >=80.00%，最低 80.00% |
| C011 | pyright | 0；0 errors, 0 warnings, 0 informations |
| C012 | ruff check dayu tests utils --output-format json | 1；142 immutable findings：E402 65、F401 64、F541 3、F821 1、F841 9 |
| C013 | Ruff JSON normalize为 filename,row,column,code,message 集合并与 accepted final baseline比对 | 0；raw SHA-256 46a4a54cf302d9a83047fef257799575ba2ec774326b5c55f0fec465841981ad；normalized SHA-256 6d2597c1040a062b8597904ffae2335b363eff9217b228cba12e2829874b180d；ADDED=0 |
| C014 | ruff check 对 aggregate fix 最终八个 mutable Python paths | 0；All checks passed |
| C015 | git diff --check；git diff --cached --name-status | 0；无 whitespace error；staged empty |
| C016 | python -m build --outdir workspace/tmp/wu-semantic-ownership-01-ar-fix-final-aggregate-build | 0；wheel 与 sdist 均生成 |
| C017 | shasum -a 256 与 stat 对 build artifacts | 0；见 §7 |
| C018 | S1 rg DocResourceBudget/SourceBudgetExceeded/source_budget_exceeded/directory_entry_limit/source_limit/skipped_oversized_files | 1；0 match，PASS |
| C019 | S2 rg llm_safe_replay_arguments/arguments_summary_unsafe/_INTERNAL_SOURCE_REF_KINDS | 1；0 match，PASS |
| C020 | S3 rg stage_source_document/ingest_complete false/owner_scope_id/owner_token/_BATCH_OWNER_CONTEXT/_execute_with_auto_batch | 1；0 match，PASS |
| C021 | S4 rg statement_locator/statement_method_missing/raw_total/deduped_count | 1；0 match，PASS |
| C022 | S5 rg total/raw_total 指定 owner roots | 0；48 matches / 10 paths；raw_total=0；均为 accepted fixture/财务/summary 语义 |
| C023 | S6 rg schema_version commands/JSON argv/dayu-web/dayu-wechat/dayu-render | 0；3 matches / 3 paths；均为 diagnostic filename、temp state dir、cleanup label，无 removed entrypoint/JSON argv contract |
| C024 | rg dayu.fins.direct_stream dayu tests utils | 1；旧 public owner import 0 |
| C025 | rg direct event consumers 与 awaiting owner definitions/imports dayu tests utils | 0；direct consumers exact 6；awaiting definitions exact 3 且都在新 owner；imports只在授权 consumers |
| C026 | rg 旧 awaiting private definitions/imports | 1；0 match |
| C027 | rg _filter_table_refs_by_availability/_assign_unmapped_tables_by_position/fallback_ref/last_known_ref sec_form_section_common.py | 1；0 match |
| C028 | git diff --exit-code 48c6cc5e... -- base.py SecProcessor 10-K/10-Q BS subclasses | 0；protected producer/subclasses无漂移 |
| C029 | git diff -U0 对 sec_form_section_common.py 新增 hunk作 fallback/guessing/hasattr/getattr/except/warning scan | 0；仅命中 raw marker range 的 position docstring/边界判断，无被禁猜测或补偿 owner |
| C030 | pytest Documents containment/output truncation + Web DNS/private/proxy/redirect/diagnostic matrix | 0；346 passed, 1 skipped, 3 warnings, 18.21s |
| C031 | pytest Host digest/EventLog/opaque ref/wait late-publication/config projection matrix | 0；514 passed, 4.37s |
| C032 | pytest tests/fins | 0；998 passed, 1 skipped, 3 warnings, 40.64s |
| C033 | pytest CLI POSIX upload/init exact nodes | 0；8 passed, 5 skipped, 3 warnings；5项均为 Darwin 上 Windows-only skip |
| C034 | pytest full deterministic HKEX test file | 0；77 passed |
| C035 | DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants -q -rs | 4；计划历史路径当前不存在，VALIDATION_COMMAND_DRIFT |
| C036 | DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort -q -rs | 0；1 passed, 2.73s，current owner fresh PASS |
| C037 | pytest 五个 configured-secret synthetic sentinel owner nodes | 0；5 passed, 0.33s |
| C038 | python workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-configured-value-scan.py | 0；trusted/zero-required 分类见 §8 |
| C039 | python utils/smoke_web_ci.py --output-dir ...final-aggregate-web --include-playwright --external-limit 0 --run-label ... | 0；status passed，local 11，external 0，failures 0，skips 0 |
| C040 | python utils/smoke_host_public_awaiting_entrypoint.py | 0；首个 timeout 保持 WAITING，最终 SUCCEEDED，worker accept + poll 2 |
| C041 | pytest R03 semantic-ownership deterministic assembly tests | 0；18 passed, 3 warnings |
| C042 | pytest tests/host/test_public_compact_smoke.py | 0；23 passed, 1 skipped；skip 是未设置真实 provider env 的显式 real-provider node |
| C043 | dayu-cli fins upload 使用 fresh storage 与 repository fixture | 0；unique upload success；生成态 document id未写入本 artifact |
| C044 | dayu-cli fins download SEC 使用 fresh storage 与本地 accepted fixture | 0；discovered 1 / downloaded 1 / failed 0 / written 1 |
| C045 | dayu-cli fins process 同一 fresh storage | 0；selected 1 / processed 1 / failed 0 / not_supported 0 |
| C046 | shasum/stat + jq 只读复核 R10 HKEX manifest/round-001/round-002 | 0；三份 immutable evidence hashes/结构精确匹配，见 §10；未新增 HKEX GET |
| C047 | 阅读根/dayu/fins/tests README 更新约束；git diff -- README targets | 0；validation-only，全部 NO_UPDATE |
| C048 | git diff --exit-code ffbf48c2...HEAD -- dayu/engine/agent.py dayu/engine/contracts/error_codes.py | 0；Topic 8/Codex F-13 no-code paths零 diff |
| C049 | fix-range deferred/Topic 9 semantic added-hunk scans与 workflow path scan | 0；0 match / 0 path |
| C050 | git show/git diff-tree/merge-base 对 ba44bf87、9e7a4e9d、85aa7184 | 0；三 accepted commits均为 ancestors；精确路径未引入 deferred/Topic8/Topic9 |
| C051 | shasum Controller-owned 三路径，entry/final-preartifact 对比 | 0；三个 hash不变 |
| C052 | git diff --check；git status --short；git diff --cached --name-status | 0；封口前 allowlist精确，staged empty |

Validation harness 的非产品异常也保留：

| ID | 命令/现象 | 分类与纠正 |
| --- | --- | --- |
| H001 | 首次 zsh coverage ledger loop 使用保留变量名 path，导致后续 jq command not found，exit 127 | HARNESS_ONLY；未改变 coverage data；改用 jq 单次 join fresh 生成完整 ledger |
| H002 | 首次并行 full Fins wrapper detached，未可靠回收 exit | HARNESS_ONLY；随后串行 fresh 重跑 tests/fins，998 passed |
| H003 | 以错误短 hash ba44bf877327... / 9e7a4e9d6102... 查询 accepted commits，git 报 bad object | EVIDENCE_LOOKUP_ONLY；从 Controller accepted-commit artifacts读取完整正确 hash后重跑 C050 |
| H004 | 计划旧 live-browser node exit 4 | COMMAND_DRIFT；C036 current owner真实运行通过；不构成产品缺陷 |
| H005 | 试用 aggregate parent 做整 umbrella broad no-code file diff，输出包含无关历史改动 | QUERY_SCOPE_TOO_BROAD；未据此作裁决；最终只用 accepted fix base ffbf48c2 与精确 semantic paths/scans |

没有通过删除、缩小测试根、增加 skip/retry/deselect 或修改配置来修饰结果。

## 5. Canonical、coverage 与 AR-F06

Canonical suite fresh PASS：5260 passed / 10 skipped / 5 deselected / 0 failed。AR-F06 exact node在 canonical 中真实 collect/执行，且另行单节点 fresh PASS；其 coverage exclusion只用于可测量 ledger，不改变 finding 状态。

Coverage fresh run只额外 deselect以下唯一 node：

    tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task

结果：

| 指标 | 结果 |
| --- | ---: |
| exact changed production Python | 219 |
| JSON 中完成 owner join | 219 |
| >=80.00% | 219 |
| <80.00% | 0 |
| statements | 61039 |
| covered lines | 54510 |
| 最低路径 | dayu/fins/storage/_fs_identity.py |
| 最低 line coverage | 80.00% |

Coverage evidence：

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage | 12042240 | ab9caca3ffbd76f33b8718b95e3c76b01efe05e5a93d1ac42bd9c5dca5231b77 |
| workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json | 16121952 | 3abca2b175d5f05019358003d34b255d907b291d493addcbc91fb3d07a410c7b |
| workspace/tmp/wu-semantic-ownership-01-ar-fix-final-changed-python.txt | 7713 | bc034be78dccf1289ffb0b217c27eac0392dace03c5190e31187ea490c086238 |

九个原 AR-F05 paths及关键新增 owner：

| 路径 | statements | covered | missing | line % |
| --- | ---: | ---: | ---: | ---: |
| dayu/documents/processors/docling_processor.py | 649 | 534 | 115 | 82.28 |
| dayu/fins/pipelines/sec_6k_rules.py | 447 | 385 | 62 | 86.13 |
| dayu/fins/processors/sec_form_section_common.py | 1125 | 901 | 224 | 80.09 |
| dayu/fins/processors/sec_report_form_common.py | 416 | 343 | 73 | 82.45 |
| dayu/fins/processors/sec_section_build.py | 303 | 256 | 47 | 84.49 |
| dayu/fins/processors/sec_table_extraction.py | 863 | 691 | 172 | 80.07 |
| dayu/fins/tools/preprocess_tools.py | 62 | 57 | 5 | 91.94 |
| dayu/host/_execution_config_projection.py | 157 | 146 | 11 | 92.99 |
| dayu/runtime/argparse_exit.py | 7 | 7 | 0 | 100.00 |
| dayu/fins/direct_events.py | 239 | 225 | 14 | 94.14 |
| dayu/fins/ingestion/awaiting_resolution.py | 22 | 22 | 0 | 100.00 |

### 5.1 Fresh 219 文件逐文件 ledger

列顺序：path、statements、covered、missing、line_percent。

dayu/cli/agent_entrypoint.py	88	80	8	90.91
dayu/cli/arg_parsing.py	294	294	0	100
dayu/cli/commands/fins.py	449	408	41	90.87
dayu/cli/commands/init.py	295	268	27	90.85
dayu/cli/commands/interactive.py	68	59	9	86.76
dayu/cli/commands/prompt.py	64	58	6	90.63
dayu/cli/commands/session.py	209	176	33	84.21
dayu/cli/errors.py	3	3	0	100
dayu/cli/host_api_errors.py	31	26	5	83.87
dayu/cli/init_catalog.py	276	249	27	90.22
dayu/cli/init_environment.py	304	288	16	94.74
dayu/cli/init_workspace.py	547	477	70	87.2
dayu/cli/main.py	88	82	6	93.18
dayu/cli/session_execution.py	296	276	20	93.24
dayu/cli/upload_script.py	139	127	12	91.37
dayu/contracts/__init__.py	14	14	0	100
dayu/contracts/agent_policy.py	8	8	0	100
dayu/contracts/tool_result.py	46	38	8	82.61
dayu/contracts/tool_schema.py	115	94	21	81.74
dayu/documents/processors/_doc_processor_factory.py	27	27	0	100
dayu/documents/processors/docling_processor.py	649	534	115	82.28
dayu/documents/processors/source_snapshot.py	154	144	10	93.51
dayu/engine/__init__.py	6	6	0	100
dayu/engine/agent.py	742	663	79	89.35
dayu/engine/contracts/__init__.py	14	14	0	100
dayu/engine/contracts/agent_policy.py	31	31	0	100
dayu/engine/contracts/agent_run.py	84	83	1	98.81
dayu/engine/contracts/engine_events.py	222	219	3	98.65
dayu/engine/contracts/error_codes.py	64	62	2	96.88
dayu/engine/contracts/messages.py	53	53	0	100
dayu/engine/contracts/runner_events.py	132	130	2	98.48
dayu/engine/runners/openai/_choice_policy.py	171	163	8	95.32
dayu/engine/runners/openai/error_classifier.py	72	67	5	93.06
dayu/engine/runners/openai/non_stream_parser.py	196	183	13	93.37
dayu/engine/runners/openai/retry_policy.py	53	52	1	98.11
dayu/engine/runners/openai/runner.py	338	282	56	83.43
dayu/engine/runners/openai/sse_parser.py	311	291	20	93.57
dayu/engine/runners/openai/tool_call_aggregator.py	199	186	13	93.47
dayu/fins/direct_event_text.py	83	71	12	85.54
dayu/fins/direct_events.py	239	225	14	94.14
dayu/fins/domain/document_models.py	432	416	16	96.3
dayu/fins/domain/filing_semantics.py	105	97	8	92.38
dayu/fins/domain/financial_result_contract.py	201	178	23	88.56
dayu/fins/domain/tool_models.py	87	84	3	96.55
dayu/fins/domain/xbrl_result_contract.py	187	167	20	89.3
dayu/fins/downloaders/cninfo_downloader.py	289	265	24	91.7
dayu/fins/downloaders/hkexnews_downloader.py	428	367	61	85.75
dayu/fins/downloaders/sec_downloader.py	864	789	75	91.32
dayu/fins/ingestion/awaiting_resolution.py	22	22	0	100
dayu/fins/ingestion_runtime.py	1684	1529	155	90.8
dayu/fins/pipelines/cn_download_company_meta.py	28	26	2	92.86
dayu/fins/pipelines/cn_download_filing_workflow.py	218	191	27	87.61
dayu/fins/pipelines/cn_download_models.py	74	74	0	100
dayu/fins/pipelines/cn_download_protocols.py	40	40	0	100
dayu/fins/pipelines/cn_download_rebuild.py	164	132	32	80.49
dayu/fins/pipelines/cn_download_source_upsert.py	78	73	5	93.59
dayu/fins/pipelines/cn_download_workflow.py	242	204	38	84.3
dayu/fins/pipelines/cn_pipeline.py	326	274	52	84.05
dayu/fins/pipelines/cn_report_selection.py	150	130	20	86.67
dayu/fins/pipelines/docling_upload_service.py	372	313	59	84.14
dayu/fins/pipelines/sec_6k_primary_document_repair.py	181	149	32	82.32
dayu/fins/pipelines/sec_6k_rules.py	447	385	62	86.13
dayu/fins/pipelines/sec_company_meta.py	45	42	3	93.33
dayu/fins/pipelines/sec_download_diagnostics.py	57	55	2	96.49
dayu/fins/pipelines/sec_download_filing_workflow.py	147	127	20	86.39
dayu/fins/pipelines/sec_download_persistence.py	122	100	22	81.97
dayu/fins/pipelines/sec_download_source_upsert.py	39	39	0	100
dayu/fins/pipelines/sec_download_state.py	148	119	29	80.41
dayu/fins/pipelines/sec_download_workflow.py	169	150	19	88.76
dayu/fins/pipelines/sec_filing_collection.py	71	68	3	95.77
dayu/fins/pipelines/sec_fiscal_fields.py	278	254	24	91.37
dayu/fins/pipelines/sec_form_utils.py	67	59	8	88.06
dayu/fins/pipelines/sec_pipeline.py	379	332	47	87.6
dayu/fins/pipelines/sec_rebuild_workflow.py	138	125	13	90.58
dayu/fins/pipelines/sec_sc13_filtering.py	214	176	38	82.24
dayu/fins/pipelines/sec_upload_workflow.py	129	109	20	84.5
dayu/fins/pipelines/upload_company_meta.py	61	57	4	93.44
dayu/fins/processors/bs_report_form_common.py	166	139	27	83.73
dayu/fins/processors/bs_six_k_processor.py	348	279	69	80.17
dayu/fins/processors/bs_ten_k_processor.py	17	17	0	100
dayu/fins/processors/bs_ten_q_processor.py	18	15	3	83.33
dayu/fins/processors/financial_base.py	14	14	0	100
dayu/fins/processors/html_financial_statement_common.py	712	572	140	80.34
dayu/fins/processors/report_form_financial_statement_common.py	91	81	10	89.01
dayu/fins/processors/sec_form_section_common.py	1125	901	224	80.09
dayu/fins/processors/sec_processor.py	290	260	30	89.66
dayu/fins/processors/sec_report_form_common.py	416	343	73	82.45
dayu/fins/processors/sec_section_build.py	303	256	47	84.49
dayu/fins/processors/sec_table_extraction.py	863	691	172	80.07
dayu/fins/processors/sec_xbrl_query.py	283	234	49	82.69
dayu/fins/processors/six_k_form_common.py	514	421	93	81.91
dayu/fins/processors/source_text.py	36	34	2	94.44
dayu/fins/processors/ten_k_processor.py	17	17	0	100
dayu/fins/processors/ten_q_processor.py	18	18	0	100
dayu/fins/processors/value_normalization.py	13	13	0	100
dayu/fins/resolver/fmp_company_info.py	124	118	6	95.16
dayu/fins/service_runtime.py	113	99	14	87.61
dayu/fins/storage/_fs_blob_core.py	67	60	7	89.55
dayu/fins/storage/_fs_company_meta_core.py	135	123	12	91.11
dayu/fins/storage/_fs_identity.py	115	92	23	80
dayu/fins/storage/_fs_maintenance_core.py	197	182	15	92.39
dayu/fins/storage/_fs_processed_core.py	179	159	20	88.83
dayu/fins/storage/_fs_source_document_core.py	360	299	61	83.06
dayu/fins/storage/_fs_source_snapshot.py	449	406	43	90.42
dayu/fins/storage/_fs_storage_infra.py	1010	870	140	86.14
dayu/fins/storage/_fs_storage_utils.py	241	202	39	83.82
dayu/fins/storage/fs_batching_repository.py	18	17	1	94.44
dayu/fins/storage/fs_company_meta_repository.py	18	18	0	100
dayu/fins/storage/fs_document_blob_repository.py	20	20	0	100
dayu/fins/storage/fs_filing_maintenance_repository.py	29	29	0	100
dayu/fins/storage/fs_processed_document_repository.py	26	26	0	100
dayu/fins/storage/fs_source_document_repository.py	77	74	3	96.1
dayu/fins/storage/local_file_source.py	20	20	0	100
dayu/fins/storage/local_file_store.py	93	92	1	98.92
dayu/fins/storage/repository_protocols.py	96	96	0	100
dayu/fins/tools/_ingestion_tool_helpers.py	65	55	10	84.62
dayu/fins/tools/cache.py	63	61	2	96.83
dayu/fins/tools/download_provider.py	19	19	0	100
dayu/fins/tools/download_tools.py	50	45	5	90
dayu/fins/tools/error_contract.py	10	10	0	100
dayu/fins/tools/fins_tools.py	348	301	47	86.49
dayu/fins/tools/preprocess_provider.py	19	19	0	100
dayu/fins/tools/preprocess_tools.py	62	57	5	91.94
dayu/fins/tools/read_runtime.py	975	841	134	86.26
dayu/fins/tools/read_runtime_helpers.py	485	391	94	80.62
dayu/fins/tools/result_types.py	138	138	0	100
dayu/fins/tools/upload_provider.py	21	21	0	100
dayu/fins/tools/upload_tools.py	95	86	9	90.53
dayu/fins/upload_batch.py	316	302	14	95.57
dayu/host/__init__.py	10	10	0	100
dayu/host/_durable_actor.py	78	66	12	84.62
dayu/host/_event_payload.py	60	59	1	98.33
dayu/host/_execution_config_projection.py	157	146	11	92.99
dayu/host/_execution_health.py	96	88	8	91.67
dayu/host/_runner_call_manifest.py	453	410	43	90.51
dayu/host/_terminal_answer.py	47	45	2	95.74
dayu/host/_wait_observation.py	167	151	16	90.42
dayu/host/accepted_result_projection.py	271	259	12	95.57
dayu/host/accepted_tool_outcome.py	24	23	1	95.83
dayu/host/admission.py	1051	955	96	90.87
dayu/host/api.py	1213	1131	82	93.24
dayu/host/command.py	410	361	49	88.05
dayu/host/compact_material.py	916	789	127	86.14
dayu/host/compact_payload.py	226	204	22	90.27
dayu/host/compact_pipeline.py	251	235	16	93.63
dayu/host/compaction.py	1015	897	118	88.37
dayu/host/compaction_operation.py	483	457	26	94.62
dayu/host/context_budget.py	218	202	16	92.66
dayu/host/context_events.py	323	300	23	92.88
dayu/host/dispatch.py	1246	1136	110	91.17
dayu/host/durable/event_log.py	369	337	32	91.33
dayu/host/durable/idempotency.py	135	133	2	98.52
dayu/host/durable/memory.py	351	309	42	88.03
dayu/host/durable/options.py	73	73	0	100
dayu/host/durable/outbox.py	273	245	28	89.74
dayu/host/durable/payload.py	168	149	19	88.69
dayu/host/durable/payload_resolution.py	128	108	20	84.38
dayu/host/durable/purge.py	560	536	24	95.71
dayu/host/durable/read_model.py	127	120	7	94.49
dayu/host/durable/run_transition.py	1375	1281	94	93.16
dayu/host/durable/schema.py	352	342	10	97.16
dayu/host/durable/session_lifecycle.py	175	165	10	94.29
dayu/host/durable/state.py	1353	1191	162	88.03
dayu/host/durable/tool_trace.py	383	332	51	86.68
dayu/host/durable/wait_resolution_digest.py	32	29	3	90.63
dayu/host/engine_ingest.py	1394	1265	129	90.75
dayu/host/evidence.py	200	190	10	95
dayu/host/lifecycle_events.py	147	142	5	96.6
dayu/host/llm_compaction.py	323	296	27	91.64
dayu/host/memory.py	925	851	74	92
dayu/host/open_host.py	525	460	65	87.62
dayu/host/outbox.py	164	158	6	96.34
dayu/host/payload_resolution.py	140	134	6	95.71
dayu/host/queue_policy.py	19	17	2	89.47
dayu/host/read_api.py	528	479	49	90.72
dayu/host/read_model.py	119	113	6	94.96
dayu/host/recovery.py	256	234	22	91.41
dayu/host/run_input.py	1252	1132	120	90.42
dayu/host/tool_call_request.py	105	100	5	95.24
dayu/host/tool_duplicate_governance.py	239	224	15	93.72
dayu/host/tool_runtime.py	1988	1764	224	88.73
dayu/host/tool_trace.py	756	676	80	89.42
dayu/host/tooling.py	77	77	0	100
dayu/host/wait_adapter.py	722	658	64	91.14
dayu/host/wait_boundary.py	49	40	9	81.63
dayu/host/wait_callback.py	207	180	27	86.96
dayu/host/waiting.py	604	536	68	88.74
dayu/runtime/__init__.py	2	2	0	100
dayu/runtime/argparse_exit.py	7	7	0	100
dayu/runtime/assembly.py	220	202	18	91.82
dayu/runtime/cancellation.py	126	116	10	92.06
dayu/runtime/config_loader.py	678	654	24	96.46
dayu/runtime/filelock.py	109	101	8	92.66
dayu/runtime/interruptible_process.py	339	299	40	88.2
dayu/runtime/lane.py	577	509	68	88.21
dayu/runtime/numeric.py	14	14	0	100
dayu/runtime/scene_prepare.py	644	596	48	92.55
dayu/runtime/tool_call_projection.py	279	254	25	91.04
dayu/service/__init__.py	3	3	0	100
dayu/service/entrypoint_runtime.py	571	504	67	88.27
dayu/service/fins_direct.py	61	55	6	90.16
dayu/service/fins_wait_adapter.py	184	174	10	94.57
dayu/service/host_admin.py	36	30	6	83.33
dayu/service/host_assembly.py	570	543	27	95.26
dayu/service/scene_context.py	73	71	2	97.26
dayu/service/wait_callback_endpoint.py	271	238	33	87.82
dayu/tools/doc_tools.py	770	620	150	80.52
dayu/tools/web/provider.py	114	106	8	92.98
dayu/tools/web/web_challenge_detection.py	110	102	8	92.73
dayu/tools/web/web_diagnostics.py	182	168	14	92.31
dayu/tools/web/web_egress_policy.py	139	119	20	85.61
dayu/tools/web/web_fetch_orchestrator.py	517	422	95	81.62
dayu/tools/web/web_http_session.py	285	254	31	89.12
dayu/tools/web/web_playwright_backend.py	540	486	54	90
dayu/tools/web/web_resource_budget.py	72	72	0	100
dayu/tools/web/web_search_projection.py	55	53	2	96.36
dayu/tools/web/web_search_providers.py	295	258	37	87.46
dayu/tools/web/web_tool_projection_text.py	22	22	0	100
dayu/tools/web/web_tools.py	712	575	137	80.76


## 6. Type / Ruff / diff / owner 与 stale scans

- pyright：0/0/0，PASS。
- Full Ruff：工具原生 exit 1，当前 exact immutable set 142；相对 accepted final baseline ADDED=0，最终八 mutable Python paths均0 finding。旧基线变化为已接受删除的一条 SecProcessor F401，不是本轮增量。
- git diff --check：PASS；staged：empty。
- direct-stream旧 owner import：0；direct consumers exact 6。
- awaiting 新 owner三项定义各唯一；旧 private definitions/imports：0。
- virtual section silent raw-ref filter / positional assignment / fallback_ref / last_known_ref：0。
- marker producer、SecProcessor、10-K/10-Q与BS subclasses相对 protected ref无漂移。
- sec_form_section_common.py新增语义没有标题相似度、顺序 fallback、hasattr/getattr、except Exception或新 warning/log补偿。

## 7. Build

Build exit 0；只有既有 setuptools license deprecation warning。

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| dayu_agent-0.1.4-py3-none-any.whl | 2101692 | 7f6ac6fb630a0887a85555c7ed51eb7dcb3b4bb52a6936ef3cc0d02aed826ce2 |
| dayu_agent-0.1.4.tar.gz | 1836905 | 0eb78f02fdbcaa822355e03105a59484f839072358dd4855c5e4d700910d09ce |

## 8. Security 与 configured-secret 分类

Synthetic sentinel owner tests fresh 5/5 PASS；real configured-value scan在 current typed config上 fresh PASS，仅输出计数：

| 分类 | match / paths 或 rows |
| --- | --- |
| configured value count | 5 |
| ACCEPTED_TRUSTED_INTERNAL Config source | 5 / 0 paths（source owner计数，不投影正文） |
| ACCEPTED_TRUSTED_INTERNAL Host physical SQLite | 27 / 4 files |
| Host exact logical effective-execution canonical fact | 23 matches / 23 rows |
| Host logical other | 0 |
| ZERO_REQUIRED Tool Trace hot/cold/query | 0 / 0 |
| ZERO_REQUIRED audit JSONL/query | 0 / 0 |
| ZERO_REQUIRED public/read-model/outbox | 0 / 0 |
| ZERO_REQUIRED LLM-facing material | 0 / 0 |
| ZERO_REQUIRED operator logs | 0 / 0 |
| ZERO_REQUIRED other smoke outputs | 0 / 0 |
| ZERO_REQUIRED review/diff | 0 / 0 |

扫描没有输出 value、ref、header name或match正文。Host trusted internal逻辑命中全部属于 USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers exact canonical fact；其它logical path为0。无需 secret infra/redaction redesign。

其它安全矩阵：

- Documents containment/output truncation与Web egress/private/proxy/redirect/diagnostic：346 passed / 1 accepted skip。
- Host digest/EventLog/opaque ref、wait fence、public/config projection：514 passed。
- Fins transaction/atomic swap/path/opaque id/direct validator：full Fins 998 passed / 1 accepted skip。
- CLI POSIX quoting/init containment/process fencing：8 passed；5个 Windows-only nodes在 Darwin真实 skip，未计作成功。

## 9. Real/local smokes

| Smoke | Fresh 结果 |
| --- | --- |
| Real Web local + Playwright，external-limit=0 | PASS；local 11，external 0，failures 0，skips 0 |
| Web summary JSON | 9495 bytes；SHA-256 485f17a113194050d598b24ecd9c6cec6e34f36ea1eec143c3432d237060e693 |
| Web summary Markdown | 1464 bytes；SHA-256 dd7eee2cfa643122e94f341b5300df86efb0b57c57e99b40495a4c4131d69c01 |
| Public awaiting | PASS；WAITING timeout语义、最终SUCCEEDED、worker accept/poll 2 |
| R03 deterministic semantic ownership | 18 passed |
| Public compactor deterministic | 23 passed；real-provider node 1 skipped |
| Live browser current owner | 1 passed |
| Fins upload | PASS，fresh storage，unique success |
| Fins SEC download | PASS；1/1/0/1 |
| Fins process | PASS；1/1/0/0 |
| POSIX generated script / real sh / real CLI / init | 8 passed；Windows-only 5 skipped |

R03 real provider 与 real compactor provider 请求没有运行，原因不是测试缺陷或环境伪成功，而是本 gate 的固定最高用户裁决“不要发任何新增真实 provider 请求”。没有改 provider、model、key、retry、quota或budget。Gemini quota/provider adherence继续是 NO_CODE / NON_BLOCKING residual。

## 10. Immutable HKEX evidence

未发新 external official GET。Fresh只读复核 accepted R10 raw evidence：

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| manifest.json | 3046 | db1f428e9d0ab6ec135e66f0d72ea064e0c0025a41090162eb8d327356742bbe |
| round-001-body.json | 56514 | cfecf9078ebc6f0cfc0c451d0e50be0048307090e8d312f4d079d88f6aa6c3f6 |
| round-002-body.json | 864825 | 548acaf4f4d501bec60feaf79e1f10c25d853ab1d6c9cc8bd0af7f709d1aab3f |

Manifest/body contract：

- GET；round 1 request 100、loaded/result 100、recordCnt 1669、hasNext=true。
- round 2 request 1669、loaded/result/recordCnt 1669、hasNext=false。
- non-range identical与final-only proof均为true。
- public read-only；无PDF/mutation/cookie/auth/header/proxy credential。
- deterministic HKEX tests fresh 77 passed。

## 11. README、deferred/no-code与安全保留项

README ledger：

| README | 结论 | 直接理由 |
| --- | --- | --- |
| README.md | NO_UPDATE | validation-only，无安装/CLI/用户工作流变化 |
| dayu/README.md | NO_UPDATE | 无分层/装配边界变化 |
| dayu/fins/README.md | NO_UPDATE | HEAD 已准确记录 atomic virtual publication、whole-base fallback、contradiction fail-closed、no position guessing |
| tests/README.md | NO_UPDATE | 无新增/迁移测试 owner |
| dayu/service/README.md | NO_UPDATE | 无 Service contract变化 |

安全保留/未实现项：

- Issue 177：TruncationManager wiring未实现；residual owner保持原 issue。
- Issue 178：storage-state lifecycle/TTL/retention/refresh未实现；residual owner保持原 issue。
- Issue 175：Fins hard-kill/process isolation未实现；residual owner保持原 issue。
- Issues 142/151：assets migration等既有 owner不变；未实施。
- Topic 8 / Codex F-13：accepted fix range内 dayu/engine/agent.py 与 error_codes.py零 diff。
- Topic 9：未引入统一 authorization framework、capability token、policy DSL或role model。
- Config/Host internal trusted domain保持原设计；未引入 secret infra。
- AR-F06：没有生产代码修复、waiver或状态漂移。
- AR-F07：未触发 Windows；仍是 release blocker。

## 12. AR-F01—AR-F07 最终状态与 residual owner

| Finding | 最终状态 | Fresh 直接证据 | Residual owner |
| --- | --- | --- | --- |
| AR-F01 | CLOSED | canonical/current-schema owner tests PASS | 无 |
| AR-F02 | CLOSED | import boundary、direct-stream/awaiting owner与stale scans PASS | 无 |
| AR-F03 | CLOSED | canonical + Host logging/projection matrix PASS | 无 |
| AR-F04 | CLOSED | public compactor deterministic current-owner tests PASS；真实 provider未按固定禁令重发 | provider adherence仅为NO_CODE/NON_BLOCKING环境项 |
| AR-F05 | CLOSED | fresh exact 219/219 line coverage >=80%；九路径与owner matrix PASS | 无 |
| AR-F06 | RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX | canonical真实运行node PASS；coverage仅exact exclusion | Host scheduler/lifecycle未来独立 owner |
| AR-F07 | PENDING_RELEASE_BLOCKER | Darwin Windows-only nodes真实skip；未伪造Windows evidence | Controller授权后的真实remote Windows gate |

## 13. 最终交接

- Local aggregate verdict：PASS_LOCAL_AGGREGATE_VALIDATION。
- 不授权也未执行：产品修复、code review、subagent、stage、commit、push、PR、真实 Windows。
- Provider请求型smokes：按固定用户裁决未重发；NO_CODE / NON_BLOCKING，不影响本地 aggregate verdict，也不关闭 AR-F07。
- 下一 owner：Controller。Controller可据此进入后续授权 gate；AR-F07必须保留到真实 Windows evidence完成。
- 本 artifact SHA-256在写入后由封口命令外部计算；artifact不自嵌 hash，避免自引用。
