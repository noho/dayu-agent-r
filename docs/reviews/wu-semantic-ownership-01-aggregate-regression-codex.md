# WU-SEMANTIC-OWNERSHIP-01 Umbrella Aggregate Regression — AgentCodex

## 0. Gate verdict

- 状态：BLOCKED。
- umbrella：WU-SEMANTIC-OWNERSHIP-01；本轮是既有 umbrella aggregate regression gate，不是新 WU。
- 执行者边界：AgentCodex 仅执行回归命令并整理证据；未执行 aggregate deepreview / 静态 review。
- 路由保护：先前误启动的 /root/aggregate_static_review 已被立即中断；本 artifact 未读取、未采用其结论，也未采用其任何产出。后续 aggregate deepreview 只可由 AgentMiMo 与 AgentDS 并发执行。
- 结论：本机可执行项已经全部执行。build、pyright、工作树 diff-check、六组 scans、绝大多数测试及真实 smoke 通过；但 canonical aggregate pytest、真实 compactor smoke、逐变更生产文件 coverage 和真实 Windows 证据未满足，故不得进入 aggregate deepreview、push、PR 或 closeout。
- 本轮没有修改 product、test、README、workflow、plan、control 或既有 artifact；没有 stage、commit、push。

## 1. Source of truth 与范围锁

已完整读取并以当前内容裁决：

- AGENTS.md。
- docs/host/issues-implementation-control.md 当前 modified 工作区状态；其 current gate 是 umbrella aggregate regression。
- docs/phaseflow-umbrella-optimization-control.md。
- docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md。
- docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md，尤其 §22.1、§23、§25，并复核 §3、§4、§7、§20、§21、§22.2—§22.4。
- 永久设计真源：docs/host/design.md、docs/engine/design.md、docs/tool/design.md、docs/fins/design.md、docs/ui/design.md。
- 各 R01—R12 accepted plan / implementation / completion evidence 仅作为不可变历史证据；本轮命令结果优先作为当前树证据。

范围身份：

| 项 | 值 |
| --- | --- |
| branch | phaseflow/host-issues-control |
| aggregate 起点 | b1a0631f397967e7530b676a90ef7467d83a1817^ |
| 起点实际 parent | 3410d7422655c56bdf13c643f77c27f40b9d4550 |
| HEAD / R12 accepted commit | ed9bfa9fe071aba0227361c69a938010ce3abe09 |
| remediation R01 起点 | edc6ea62c7685d6d1625422df7b18ec6a22c323e |
| range commit 数 | 306 |
| range diff | 1,987 files；382,072 insertions；27,728 deletions |
| range status | 1,604 A；3 D；379 M；1 R079 |
| 现存 changed production Python | 219（另有 3 个已删除 Python path） |

本轮开始时受保护工作区：

    M docs/host/issues-implementation-control.md
    ?? docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md

两者均由 Controller 拥有；本轮未覆盖、未 stage、未编辑。唯一新增文件是本 artifact。

## 2. §22.1 canonical command ledger

### 2.1 Full aggregate pytest

无 PTY canonical 命令：

    source .venv/bin/activate && pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli

结果：exit 1；4 failed、5161 passed、10 skipped、5 deselected、3 warnings；170.38s。

失败精确归属：

| node | 直接证据 | 分类 |
| --- | --- | --- |
| tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default | 与 SEC logging node 同进程隔离为 2 passed；utils/smoke_web_ci.py:5020 的 configure(..., configure_root=True) 由 caaa559eae16beecc0c2fd07500ee91c3b714bf7（2026-06-10）引入，早于 aggregate 起点，且未恢复 root logging state | EXISTING_BASELINE / RELEASE_BLOCKER |
| tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response | 同上；隔离与原相对顺序 2 passed | EXISTING_BASELINE / RELEASE_BLOCKER |
| tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets | fixture 写出的 host_runtime profile 缺 wait_poller_policy；ConfigLoader 在 dayu/runtime/config_loader.py:1932 把它列为必填，blame 9e349ac42cf43b89bb025f66a405bdae9d9a8eaa（R04） | CURRENT_REMEDIATION_TEST_DEFECT / RELEASE_BLOCKER |
| tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers | 三个真实反向边界命中：service/fins_direct.py -> dayu.fins.direct_stream（8e0f2c558，R09）；service/fins_wait_adapter.py 与 service/host_assembly.py -> dayu.fins.tools._ingestion_tool_helpers（9e349ac42，R04） | CURRENT_REMEDIATION_ARCHITECTURE_DEFECT / RELEASE_BLOCKER |

隔离复核：

    source .venv/bin/activate && pytest tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q

结果：exit 0；2 passed in 0.10s。

    source .venv/bin/activate && pytest tests/service/test_host_admin.py tests/service/test_import_boundary.py -q

结果：exit 1；上述两个 Service node 精确失败，未出现额外 node。

一次带 PTY 的早期尝试在 CLI init prompt 处改变了真实运行环境并被人工中断，得到 4 failed、4886 passed、3 skipped、5 deselected 及 KeyboardInterrupt。该次运行标为 INVALID_NON_EVIDENCE，不用于任何 gate 结论；canonical 结论只采用上面的无 PTY 命令。

### 2.2 Full pyright

    source .venv/bin/activate && pyright

结果：exit 0；0 errors、0 warnings、0 informations。仅有 pyright 新版本提示，不是类型错误。

### 2.3 Worktree diff-check

    source .venv/bin/activate && git diff --check

结果：exit 0，无输出。

额外诊断（不是 §22.1 canonical 命令）：

    git diff --check 3410d7422655c56bdf13c643f77c27f40b9d4550..HEAD

结果：exit 2；76 条历史 committed review-artifact trailing whitespace / blank-EOF 命中。当前 worktree 命令仍为 PASS；该额外结果登记为 COMMITTED_HISTORICAL_ARTIFACT_HYGIENE_NOTE，不冒充 product/test defect，本轮也未获授权改既有 artifact。

### 2.4 Build

首次：

    source .venv/bin/activate && python -m build --outdir workspace/tmp/wu-semantic-ownership-01-aggregate-build

结果：exit 1；.venv 未安装 PyPA build。pip show build 也确认 absent；这是本机验证依赖缺失，不是 project build failure。

只修改本地 .venv 的依赖补齐：

    source .venv/bin/activate && python -m pip install 'build>=1.2,<2.0'

结果：exit 0；安装 build 1.5.0 与 pyproject_hooks。

重新执行同一 build 命令：exit 0；sdist 与 wheel 均成功。setuptools license classifier 警告为上游 deprecation warning。

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| workspace/tmp/wu-semantic-ownership-01-aggregate-build/dayu_agent-0.1.4-py3-none-any.whl | 2,101,532 | 1762649867e5bf20ca715dd2303d54d1249cf97dfc6019f073e1bba0601f2fb2 |
| workspace/tmp/wu-semantic-ownership-01-aggregate-build/dayu_agent-0.1.4.tar.gz | 1,836,332 | 7d3d9c0ec47aef0943aaadd8abff973fd8f06dd543db3e88d0a41993bf24d82f |

build 写入的 root build/ 中间内容已用 find build -mindepth 1 -delete 安全清空，保留原有空目录；生成物只留在 gitignored workspace/tmp，不污染可见工作树。

## 3. 六组 aggregate scans

所有命令均在当前 HEAD 执行；rg 的 exit 1 且无输出表示零命中。

### S1 — Doc legacy budgets

    rg -n 'DocResourceBudget|SourceBudgetExceeded|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md

exit 1，零命中：PASS。

### S2 — accepted-call repair / internal ref legacy

    rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|_INTERNAL_SOURCE_REF_KINDS' dayu tests

exit 1，零命中：PASS。

### S3 — Fins staging / implicit batch authority

    rg -n 'stage_source_document|ingest_complete.*false|owner_scope_id|owner_token|_BATCH_OWNER_CONTEXT|_execute_with_auto_batch' dayu/fins tests/fins

exit 1，零命中：PASS。

### S4 — stale financial public semantics

    rg -n 'statement_locator|statement_method_missing|raw_total|deduped_count' dayu/fins/tools dayu/fins/domain tests/fins

exit 1，零命中：PASS。

### S5 — total/raw_total classification

    rg -n '\btotal\b|raw_total' dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors tests/fins

exit 0；48 个 occurrence，逐项分类：

- raw_total：0。
- dayu/fins/domain/xbrl_result_contract.py：0。
- 34 个是不可变 SEC/XBRL fixture 原文：HTM 20、HTM XML 12、label XML 2。
- 14 个非 fixture occurrence：financial_enhancer.py 的 total assets / total liabilities；six_k_form_common.py 的局部数值 total 与财务术语；测试中的 download/read/storage summary 字段。
- 无命中把 provider/internal raw total 投影成 public/LLM fact_count；均为 EXPECTED_NON_STALE_HIT。S5：PASS。

### S6 — removed public entrypoint / JSON argv classification

    rg -n 'schema_version.*commands|JSON argv|dayu-web|dayu-wechat|dayu-render' pyproject.toml dayu tests README.md

exit 0；仅 3 个命中：

- tests/tools/web/test_diagnose_web_access.py:237：diagnostic filename。
- tests/tools/web/test_web_tools_provider.py:4335：临时状态目录名。
- dayu/tools/web/web_playwright_backend.py:704：cleanup thread/process label。

均不是 console script、package entrypoint、public JSON argv/schema 或 README 承诺，分类 EXPECTED_OPERATIONAL_LABEL。S6：PASS。

## 4. Current rerun test / smoke ledger

### 4.1 Deterministic local matrices

| 命令 | exit / result | 用途 |
| --- | --- | --- |
| pytest tests/tools/test_doc_tools_provider.py tests/tools/web -q | 0；344 passed、1 skipped、3 warnings；17.82s | Doc >32 MiB、10,001 entries、tail hit、symlink escape；Web owner tests |
| pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_context_compact_events.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_awaiting_accept.py tests/host/test_phase7_waiting_integration.py tests/engine/test_agent_phase3_tool_call.py -q | 0；493 passed；3.02s | accepted result / run input / memory / compact / trace / wait / Engine suspension |
| pytest tests/fins -q | 0；950 passed、1 skipped、3 warnings；38.84s | full Fins storage/read/direct/HKEX/processor |
| pytest tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_default_output_generates_posix_script_and_summary tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage tests/cli/test_init_smoke.py -q | 0；8 passed、5 skipped、3 warnings；26.40s | POSIX real shell/CLI/storage + init |
| DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants -q -rs | 0；1 passed；3.84s | 真实 Chromium descendant cleanup |

CLI 的 5 个 skip 全部是 Darwin 上不可执行的真实 Windows nodes：Windows init 四态、junction、symlink、root identity、setx；它们未计为成功。POSIX 证据包含真实 /bin/sh 对抗 argv recorder、生成脚本真实 python -m dayu.cli -> Service/Fins -> temp storage，以及 init current-schema / preserve / overwrite / reset No/Yes / prewarm / profile marker / 双 publisher lock。

### 4.2 Real Web smoke — 本轮重跑

    source .venv/bin/activate && python utils/smoke_web_ci.py --output-dir workspace/tmp/wu-semantic-ownership-01-aggregate-web-smoke --include-playwright --external-limit 0 --run-label wu-semantic-ownership-01-aggregate

结果：exit 0；status passed；11 local required cases、4 diagnostic-only search cases、0 failure、0 skip。local HTML/PDF requests/tool、真实 Playwright、challenge control、versioned filing HTTP/Playwright、配置装配均通过。external URL limit 0；search provider 的保留地址解析/key-missing 只按脚本 contract 记 diagnostic-only，不签署业务 success。

| 文件 | lines / bytes | SHA-256 |
| --- | --- | --- |
| summary.json | 208 / 9,342 | dd567e59c067d9b6875570d7970c2de802f2aa2c34506334b2773425413cc247 |
| summary.md | 23 / 1,416 | f4da6f1e3cca3a14375892d8ae4d68244b66c4d89fee62b441a5637bc0fc149e |

### 4.3 Real Host / Wait — 本轮重跑

    source .venv/bin/activate && python utils/smoke_host_public_awaiting_entrypoint.py --workspace-root workspace/tmp/wu-semantic-ownership-01-aggregate-awaiting --keep-workspace

结果：exit 0。第一次 observation timeout 后 run/wait 保持 WAITING、claim 释放、terminal_outbox=0；长事务 0.300238s 大于 0.05s handshake；late ready 被拒绝；第二 claim 生效；最终 SUCCEEDED，outbox identity 一致，worker accept/poll 均为 2；PASS。

真实普通 + awaiting + resume + Doc/Web/Fins LLM closure：

    source .venv/bin/activate && python utils/smoke_host_public_r03_semantic_ownership.py --workspace-root workspace/tmp/wu-semantic-ownership-01-aggregate-r03 --doc-file tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json --web-query 'Apple annual report 2024 revenue' --fins-ticker AAPL --fins-document-id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283 --keep-workspace

结果：exit 0；providers=7、selected_tools=14、wait_poller=true；Doc、Web、Fins awaiting/list/read、observation 全部 ROUND_PASS；projection requests=5、accepted_results=5、explicit_citations=1；opaque ref 无 LLM 泄漏；总耗时约 84s。

### 4.4 Real compactor — 本轮重跑，失败

    source .venv/bin/activate && DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity --basetemp=workspace/tmp/wu-semantic-ownership-01-aggregate-real-compactor-pytest -q -rs

结果：exit 1；1 failed in 6.41s。不是 provider/network failure：

- first_terminal 与 second_terminal 都是 SUCCEEDED；
- compact artifacts 新增 3 个；
- context_compaction artifact schema_version=3，SHA-256 4e87bf80af775d9fb3e62f8d8b497d8c7be82dbf5ede3c14193e4dae3ccb23f4；
- accepted_candidate keys 精确为 answer_anchors、diagnostics、evidence_backed_facts、forward_intents、reference_continuity_items、schema_version、session_summary；
- tests/host/test_public_compact_smoke.py:1785—1794 的旧 helper 仍要求 candidate_id == llm-compact:{run_id}。这些 helper 行 blame 914a698d735ff104e03a286f46f848864eb1a752（2026-05-19）；R03 又修改了同一 test file 却未迁移该 optional real-smoke oracle。

分类：STALE_TOUCHED_TEST_OWNER_CONTRACT / RELEASE_BLOCKER。真实 product run 成功不等于 smoke gate 成功；不得用 skip 代替。

### 4.5 Real Fins direct — 本轮重跑

真实 upload（先为 R03 smoke 创建 temp storage）：

    source .venv/bin/activate && python -m dayu.cli --base workspace/tmp/wu-semantic-ownership-01-aggregate-r03 upload_filing --ticker AAPL --action create --files tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm --fiscal-year 2024 --fiscal-period FY --filing-date 2024-11-01 --report-date 2024-09-28 --company-name 'Apple Inc.'

结果：exit 0；uploaded_files=1；document id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283。

真实 SEC download：

    source .venv/bin/activate && python -m dayu.cli --base workspace/tmp/wu-semantic-ownership-01-aggregate-r09-download-20260718 download --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31

结果：exit 0；discovered=1、downloaded=1、failed=0、written_documents=1；document fil_0000320193-25-000079；progress 后唯一 success terminal。

真实 Docling process：

    source .venv/bin/activate && python -m dayu.cli --base workspace/tmp/wu-semantic-ownership-01-aggregate-r09-download-20260718 process --ticker AAPL

结果：exit 0；selected=1、processed=1、failed=0、not_supported=0；progress 后唯一 success terminal。

### 4.6 HKEX official — accepted immutable evidence，未在本轮重发外部 GET

R10 accepted gitignored raw evidence仍存在且哈希匹配：

| evidence | lines / bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 107 / 3,046 | db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe |
| round-001-body.json | 0 / 56,514 | cfec10de8f3d20d8a6b7eefc73937cf00a71c61124061f49ec16704222d1ed18 |
| round-002-body.json | 0 / 864,825 | 548254d47e805d841a39b60fb51af879d453b36c9bb5c9987156f251969e8fdd |

该 immutable accepted evidence 记录 2026-07-17 public read-only GET：100 -> recordCnt 1669 -> request 1669 -> final 1669，non-range params exact equal、无重复、无 mutation/cookie/auth/proxy credential。当前本轮重跑了 full Fins HKEX deterministic owner tests；没有把历史外部 GET 冒充为本轮重跑。

### 4.7 Windows workflow/run/artifact oracle

本地 workflow 真源：

- .github/workflows/r11-upload-script-windows.yml，commit de4cf116c20c687f38cd3474b53949b0aedee5ab。
- .github/workflows/r12-init-windows.yml，commit ed9bfa9fe071aba0227361c69a938010ce3abe09。

真实查询：

    gh run list --workflow r12-init-windows.yml --limit 20 --json ...

结果：exit 1；GitHub API 404，workflow 不在 default branch。

    gh api repos/noho/dayu-agent-r/actions/workflows --jq ...

结果：exit 0；total_count=0。

    gh api 'repos/noho/dayu-agent-r/actions/runs?per_page=100' --jq ...

结果：exit 0；total_count=0、runs=[]。

当前本地仓库也没有 origin remote；没有可触发或读取的远端 branch workflow。故：

- 状态：PENDING_RELEASE_BLOCKER。
- 必需 workflow：Windows runner checkout 含 ed9bfa9 HEAD 的分支；优先运行 r12-init-windows.yml（其 always step同时运行 R11 两个真实 cmd nodes），并可独立运行 r11-upload-script-windows.yml。
- 必需 run oracle：runs-on windows-latest；Python 3.11；locked constraints 安装成功；job 非 skipped/cancelled；所有 pytest node exit 0。
- 必需 R11 artifact oracle：r11-windows-upload-script-{run_id}；包含 environment/cmd help、pytest stdout/stderr/junit、cmd-recorder/generated-upload.cmd、recorder-oracle.jsonl 恰一行、cli-storage/cli-generated-upload.cmd、cli-grammar-oracle.json；cmd_invocation 精确 cmd.exe /d /c；script hash一致；temp portfolio artifact count一致。
- 必需 R12 artifact oracle：r12-init-windows-{run_id}；包含 versions.txt、environment-names.txt、source-hashes.json、init-pytest-junit.xml、r11-pytest-junit.xml；五个 Windows init nodes、platform capability、rollback/race nodes及两个 R11 cmd nodes全绿。
- Darwin 的 5 skip 不得计为成功；当前没有真实 cmd.exe/init workflow pass。

## 5. Coverage gate

命令：

    source .venv/bin/activate
    COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-aggregate.coverage python -m coverage erase
    COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-aggregate.coverage python -m coverage run --branch -m pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli
    COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-aggregate.coverage python -m coverage json -o workspace/tmp/wu-semantic-ownership-01-aggregate-coverage.json

coverage pytest：exit 1；5 failed、5160 passed、10 skipped、5 deselected、3 warnings；187.08s。除 canonical 4 failures 外，多出：

- tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task；
- coverage instrumentation 下 scheduler.close 的 clean-EOF terminal promotion 在 close gate 后 wake，得到 HostApiError: Host execution is unavailable；
- 无 coverage 隔离重跑：1 passed in 0.32s；
- R05 accepted validation 早已记录相同 node / error / coverage-only timing，且与 R05 owner paths零交集。

分类：EXISTING_COVERAGE_TIMING_BASELINE / RELEASE_BLOCKER。隔离通过只证明非确定性，不能把 aggregate coverage session签为 green。

coverage JSON：0 lines（单行）/ 16,043,408 bytes；SHA-256 623bad4d401a6b6053e26b9d5ca7b197a289c5c26c6c712e3ee72d974162ecfe。

逐文件 line coverage 结果：

- 219 个现存 changed production Python files。
- 210 个 >=80%。
- 8 个 <80%。
- 1 个未命中。
- 下列 9 个文件在 remediation 起点 edc6ea62..HEAD 均无 diff，属于既有 umbrella pre-remediation integrated baseline；但 §22.3 明确要求总 changed production files各自 >=80%，所以仍是 release blocker。
- accepted sub-WU evidence只精确证明当时的 changed owners（例如 source_text.py 94%、value_normalization.py 100%、R09 5 files 88.56%—97.78%、R10 4 files >=80%）；不能为下列未达标文件补签。特别是 argparse_exit.py 当前仓库无任何 test 引用。

| file | fresh line coverage | disposition |
| --- | ---: | --- |
| dayu/documents/processors/docling_processor.py | 63.46% | BLOCK |
| dayu/fins/pipelines/sec_6k_rules.py | 67.56% | BLOCK |
| dayu/fins/processors/sec_form_section_common.py | 78.23% | BLOCK |
| dayu/fins/processors/sec_report_form_common.py | 65.14% | BLOCK |
| dayu/fins/processors/sec_section_build.py | 77.56% | BLOCK |
| dayu/fins/processors/sec_table_extraction.py | 66.16% | BLOCK |
| dayu/fins/tools/preprocess_tools.py | 75.81% | BLOCK |
| dayu/host/_execution_config_projection.py | 76.43% | BLOCK |
| dayu/runtime/argparse_exit.py | 未命中 | BLOCK |

## 6. README decision ledger

总范围内 README changed paths共 8 个：README.md、dayu/README.md、dayu/config/README.md、dayu/engine/README.md、dayu/fins/README.md、dayu/host/README.md、dayu/service/README.md、tests/README.md。

- root/dayu/engine/fins/host README 的 Agent更新约束已读取；config/service/tests 当前没有同名专节，按仓库总规则与各自职责核对。
- 最新 owner commit：root/config/service/tests 为 R12 ed9bfa9；dayu/fins 为 R11 de4cf116；engine 为 1a70fd2；host 为 ff7b0b1。
- range README-only git diff --check：exit 0，无输出。
- 当前 gate 不修改 product/test/public contract，只新增 review artifact；因此本轮 README decision 为 NO_UPDATE。
- 当前 README 文本与 current local POSIX workflow、R01—R12 owner contract一致；Windows 成功状态没有被 README 或本 artifact伪造。Windows仍由 release-blocker ledger约束。

## 7. Security retained / modified ledger

| §21 behavior | 本轮证据 | 状态 |
| --- | --- | --- |
| Doc allowed_paths / resolve containment / symlink拒绝 | test_doc_complete_input_real_smoke_above_legacy_thresholds；10,001 entries、>32MiB、tail、outside symlink permission_denied | PASS |
| Doc output truncation / cancellation | 同一 real node断言 complete input 与 2,000-char output truncation分离；full Doc tests | PASS |
| Web private/custom-port / DNS redirect / proxy / peer proof | tests/tools/web全量；real Web local matrix；explicit deny与proof/proxy fail-closed tests | PASS |
| Web resource budgets / browser capability / challenge / diagnostics v2 | 344-node group、real Playwright、11-case Web smoke、4 diagnostic-only provider cases | PASS |
| browser storage-state lifecycle deleted/deferred | source scan无 storage-state-out/ttl、credential retention/refresh；只保留 explicit input | PASS |
| Host canonical digest / EventLog / opaque provenance | 493 owner tests + R03 real LLM smoke；5 accepted results、citation、opaque ref零泄漏 | PASS |
| wait late-publication fence / claim | public awaiting real smoke；WAITING -> retry -> SUCCEEDED，never LOST | PASS |
| Fins transaction / atomic swap / path containment / opaque IDs | full Fins 950 passed + current focused earlier 574 passed；storage crash/concurrency/Unicode/symlink nodes均在集合 | PASS |
| Fins direct safe text / validator identity | full Fins + real SEC/download/process/upload；唯一 success terminal | PASS |
| CLI POSIX atomic write / quoting | real /bin/sh adversarial recorder与真实 CLI temp storage | PASS |
| CLI Windows quoting | 只有 Darwin skip；无 GitHub run/artifact | PENDING_RELEASE_BLOCKER |
| init containment / symlink / atomic swap / managed roots | POSIX real four-state/profile/lock nodes通过 | PASS_LOCAL_POSIX |
| init Windows filesystem/env | 无真实 runner/artifact | PENDING_RELEASE_BLOCKER |
| process fencing | wait real smoke、Host/Engine tests、real Playwright descendant cleanup | PASS |

Secret scan：

    python -c '<读取已配置 secret values，仅输出匹配计数，在 aggregate workspace/tmp outputs中搜索>'

结果：exit 0；configured secret value count=6；aggregate output secret value match count=0；matched path count=0。命令没有打印 secret value。

## 8. Deferred / no-code ledger

| 项 | 直接 diff/source evidence | 状态 |
| --- | --- | --- |
| Issue 177 | remediation diff未引入新 TruncationManager wiring；S1 legacy budget扫描零命中；Doc完整输入 smoke通过 | DEFERRED / owner Issue 177 |
| Issue 178 | storage-state lifecycle output/TTL/retention/refresh source scan零命中；显式 input保留 | DEFERRED / owner Issue 178 |
| Issue 175 | R01—R12 remediation diff未加入 Fins process isolation/thread hard-kill；当前 cooperative fence保留 | DEFERRED / owner Issue 175 |
| Issue 142 / 151 | find dayu -type d -name assets 零结果；remediation diff无 product assets/migration path；当前 managed roots仍仅 .dayu/config | DEFERRED / respective issue owners |
| Topic 8 | git diff edc6ea62..HEAD 对 dayu/engine/agent.py 与 engine/contracts/error_codes.py为空；未改 240-char redaction/truncation策略，未加 durable full-detail ref | NO_CODE / PASS |
| Codex F-13 128-char runner code | 同一 engine error_codes remediation diff为空 | NO_CODE / PASS |
| Topic 9 | remediation diff path/source scan无 unified authorization、capability token、policy DSL、role model框架；局部 permission/I/O defenses仍由 security matrix验证 | NO_CODE / PASS |

现有 tests/host/test_toolruntime_truncation_fetch_more.py 只是既有 test path，不是本 remediation 新建 Issue 177 wiring；没有把路径名命中误判为实现。

## 9. Failure / finding adjudication ledger

| ID | finding | root-cause class | status / owner |
| --- | --- | --- | --- |
| AR-F01 | host_admin test fixture未提供 R04 必填 wait_poller_policy | CURRENT_REMEDIATION_TEST_DEFECT | OPEN RELEASE BLOCKER；R04 config/test owner |
| AR-F02 | Service 三处直接 import Fins，违反 UI -> Service -> Host -> Engine 与 Service boundary test | CURRENT_REMEDIATION_ARCHITECTURE_DEFECT | OPEN RELEASE BLOCKER；R04/R09 owner |
| AR-F03 | Web smoke configure_root=True 污染全局 logging，导致两个 order-dependent full-suite failure | EXISTING_BASELINE（早于 aggregate range） | OPEN RELEASE BLOCKER；Web smoke/test harness owner；Controller R03 证据明确要求 umbrella final ledger处理 |
| AR-F04 | real compactor test helper仍按已删除 candidate_id检索 current vNext artifact；真实两次 run本身成功 | STALE_TOUCHED_TEST_OWNER_CONTRACT | OPEN RELEASE BLOCKER；R03 compact smoke/test owner |
| AR-F05 | 219 changed production files中 8 低于80%、1未命中 | PRE_REMEDIATION_UMBRELLA_BASELINE | OPEN RELEASE BLOCKER；原 changed-file test owners |
| AR-F06 | coverage instrumentation下 scheduler promotion/close timing node复现既有 failure | EXISTING_COVERAGE_TIMING_BASELINE | OPEN RELEASE BLOCKER；scheduler/test owner |
| AR-F07 | GitHub workflow/run/artifact均不存在，无法证明真实 cmd.exe 与 Windows init | EXTERNAL_RELEASE_EVIDENCE_BLOCKER | PENDING_RELEASE_BLOCKER；workflow/remote runner owner |
| AR-N01 | PyPA build最初未安装 | ENVIRONMENT_LIMITATION | RESOLVED：安装到本地 .venv 后 build exit 0 |
| AR-N02 | range-level历史 review artifact whitespace | COMMITTED_HISTORICAL_ARTIFACT_HYGIENE | NOTE；不影响当前 git diff --check，不在本轮授权范围 |

没有把任何失败改写成产品成功；没有自行修代码。

## 10. Residual risks 与 closeout status

§23 residual owner/destination保持不变：

- Doc极大输入资源耗尽 -> Issue 177。
- browser credential lifecycle -> Issue 178。
- Fins thread-backed长事务不可物理取消 -> Issue 175。
- future product assets/migration -> Issue 142/151。
- Windows env与config不能形成跨资源全局原子事务 -> R12 CLI owner；只报告 env names，不泄值。
- HKEX未来 rowRange hard cap -> evidence-driven HKEX provider后续 issue；accepted live evidence当前未观察到。
- Web peer proof + enterprise proxy不可同时证明最终 peer -> Web config owner，typed fail closed。
- unified tool authorization -> Topic 9 future design WU。

这些是已接受 residual，不用于豁免 AR-F01—AR-F07。当前 closeout矩阵：

| gate | status |
| --- | --- |
| §22.1 tests | BLOCKED |
| pyright | PASS |
| worktree git diff --check | PASS |
| build | PASS after local environment prerequisite |
| six scans | PASS after hit classification |
| local deterministic smoke | PASS except real compactor |
| real POSIX CLI/init | PASS |
| per-file coverage | BLOCKED |
| Windows real workflow | PENDING_RELEASE_BLOCKER |
| README decision | PASS / NO_UPDATE |
| security | PASS_LOCAL except Windows |
| deferred/no-code | PASS |
| aggregate deepreview | NOT_STARTED；路由保留给 AgentMiMo + AgentDS |
| PR / push / final closeout | NOT_AUTHORIZED / BLOCKED |

## 11. Final workspace scope

写入本 artifact 前，tracked/staged状态仍与开始一致；build/cache/coverage/smoke只写 gitignored workspace/tmp 或本地 .venv。写入后预期且只允许：

    M docs/host/issues-implementation-control.md
    ?? docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md
    ?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md

staged tree必须为空；HEAD必须仍为 ed9bfa9fe071aba0227361c69a938010ce3abe09。

## Appendix A — 219 changed production Python files fresh line coverage

数据源：workspace/tmp/wu-semantic-ownership-01-aggregate-coverage.json，SHA-256 623bad4d401a6b6053e26b9d5ca7b197a289c5c26c6c712e3ee72d974162ecfe。

| file | line coverage | status |
| --- | ---: | --- |
| `dayu/cli/agent_entrypoint.py` | 90.91% | PASS |
| `dayu/cli/arg_parsing.py` | 100.00% | PASS |
| `dayu/cli/commands/fins.py` | 90.87% | PASS |
| `dayu/cli/commands/init.py` | 90.85% | PASS |
| `dayu/cli/commands/interactive.py` | 86.76% | PASS |
| `dayu/cli/commands/prompt.py` | 90.62% | PASS |
| `dayu/cli/commands/session.py` | 84.21% | PASS |
| `dayu/cli/errors.py` | 100.00% | PASS |
| `dayu/cli/host_api_errors.py` | 83.87% | PASS |
| `dayu/cli/init_catalog.py` | 90.22% | PASS |
| `dayu/cli/init_environment.py` | 94.74% | PASS |
| `dayu/cli/init_workspace.py` | 87.20% | PASS |
| `dayu/cli/main.py` | 93.18% | PASS |
| `dayu/cli/session_execution.py` | 93.24% | PASS |
| `dayu/cli/upload_script.py` | 91.37% | PASS |
| `dayu/contracts/__init__.py` | 100.00% | PASS |
| `dayu/contracts/agent_policy.py` | 100.00% | PASS |
| `dayu/contracts/tool_result.py` | 82.61% | PASS |
| `dayu/contracts/tool_schema.py` | 81.74% | PASS |
| `dayu/documents/processors/_doc_processor_factory.py` | 100.00% | PASS |
| `dayu/documents/processors/docling_processor.py` | 63.46% | BLOCK |
| `dayu/documents/processors/source_snapshot.py` | 93.51% | PASS |
| `dayu/engine/__init__.py` | 100.00% | PASS |
| `dayu/engine/agent.py` | 89.35% | PASS |
| `dayu/engine/contracts/__init__.py` | 100.00% | PASS |
| `dayu/engine/contracts/agent_policy.py` | 100.00% | PASS |
| `dayu/engine/contracts/agent_run.py` | 98.81% | PASS |
| `dayu/engine/contracts/engine_events.py` | 98.65% | PASS |
| `dayu/engine/contracts/error_codes.py` | 96.88% | PASS |
| `dayu/engine/contracts/messages.py` | 100.00% | PASS |
| `dayu/engine/contracts/runner_events.py` | 98.48% | PASS |
| `dayu/engine/runners/openai/_choice_policy.py` | 95.32% | PASS |
| `dayu/engine/runners/openai/error_classifier.py` | 93.06% | PASS |
| `dayu/engine/runners/openai/non_stream_parser.py` | 93.37% | PASS |
| `dayu/engine/runners/openai/retry_policy.py` | 98.11% | PASS |
| `dayu/engine/runners/openai/runner.py` | 83.43% | PASS |
| `dayu/engine/runners/openai/sse_parser.py` | 93.57% | PASS |
| `dayu/engine/runners/openai/tool_call_aggregator.py` | 93.47% | PASS |
| `dayu/fins/direct_event_text.py` | 85.54% | PASS |
| `dayu/fins/direct_events.py` | 92.21% | PASS |
| `dayu/fins/direct_stream.py` | 97.78% | PASS |
| `dayu/fins/domain/document_models.py` | 96.30% | PASS |
| `dayu/fins/domain/filing_semantics.py` | 92.38% | PASS |
| `dayu/fins/domain/financial_result_contract.py` | 88.56% | PASS |
| `dayu/fins/domain/tool_models.py` | 96.55% | PASS |
| `dayu/fins/domain/xbrl_result_contract.py` | 89.30% | PASS |
| `dayu/fins/downloaders/cninfo_downloader.py` | 91.70% | PASS |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 85.75% | PASS |
| `dayu/fins/downloaders/sec_downloader.py` | 91.32% | PASS |
| `dayu/fins/ingestion_runtime.py` | 90.80% | PASS |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 92.86% | PASS |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 87.61% | PASS |
| `dayu/fins/pipelines/cn_download_models.py` | 100.00% | PASS |
| `dayu/fins/pipelines/cn_download_protocols.py` | 100.00% | PASS |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 80.49% | PASS |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 93.59% | PASS |
| `dayu/fins/pipelines/cn_download_workflow.py` | 84.30% | PASS |
| `dayu/fins/pipelines/cn_pipeline.py` | 84.05% | PASS |
| `dayu/fins/pipelines/cn_report_selection.py` | 86.67% | PASS |
| `dayu/fins/pipelines/docling_upload_service.py` | 84.14% | PASS |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 82.32% | PASS |
| `dayu/fins/pipelines/sec_6k_rules.py` | 67.56% | BLOCK |
| `dayu/fins/pipelines/sec_company_meta.py` | 93.33% | PASS |
| `dayu/fins/pipelines/sec_download_diagnostics.py` | 96.49% | PASS |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 86.39% | PASS |
| `dayu/fins/pipelines/sec_download_persistence.py` | 81.97% | PASS |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 100.00% | PASS |
| `dayu/fins/pipelines/sec_download_state.py` | 80.41% | PASS |
| `dayu/fins/pipelines/sec_download_workflow.py` | 88.76% | PASS |
| `dayu/fins/pipelines/sec_filing_collection.py` | 95.77% | PASS |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 91.37% | PASS |
| `dayu/fins/pipelines/sec_form_utils.py` | 88.06% | PASS |
| `dayu/fins/pipelines/sec_pipeline.py` | 87.60% | PASS |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 90.58% | PASS |
| `dayu/fins/pipelines/sec_sc13_filtering.py` | 82.24% | PASS |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 84.50% | PASS |
| `dayu/fins/pipelines/upload_company_meta.py` | 93.44% | PASS |
| `dayu/fins/processors/bs_report_form_common.py` | 83.73% | PASS |
| `dayu/fins/processors/bs_six_k_processor.py` | 80.17% | PASS |
| `dayu/fins/processors/bs_ten_k_processor.py` | 100.00% | PASS |
| `dayu/fins/processors/bs_ten_q_processor.py` | 83.33% | PASS |
| `dayu/fins/processors/financial_base.py` | 100.00% | PASS |
| `dayu/fins/processors/html_financial_statement_common.py` | 80.34% | PASS |
| `dayu/fins/processors/report_form_financial_statement_common.py` | 89.01% | PASS |
| `dayu/fins/processors/sec_form_section_common.py` | 78.23% | BLOCK |
| `dayu/fins/processors/sec_processor.py` | 85.17% | PASS |
| `dayu/fins/processors/sec_report_form_common.py` | 65.14% | BLOCK |
| `dayu/fins/processors/sec_section_build.py` | 77.56% | BLOCK |
| `dayu/fins/processors/sec_table_extraction.py` | 66.16% | BLOCK |
| `dayu/fins/processors/sec_xbrl_query.py` | 82.69% | PASS |
| `dayu/fins/processors/six_k_form_common.py` | 81.91% | PASS |
| `dayu/fins/processors/source_text.py` | 94.44% | PASS |
| `dayu/fins/processors/ten_k_processor.py` | 82.35% | PASS |
| `dayu/fins/processors/ten_q_processor.py` | 83.33% | PASS |
| `dayu/fins/processors/value_normalization.py` | 100.00% | PASS |
| `dayu/fins/resolver/fmp_company_info.py` | 95.16% | PASS |
| `dayu/fins/service_runtime.py` | 87.61% | PASS |
| `dayu/fins/storage/_fs_blob_core.py` | 89.55% | PASS |
| `dayu/fins/storage/_fs_company_meta_core.py` | 91.11% | PASS |
| `dayu/fins/storage/_fs_identity.py` | 80.00% | PASS |
| `dayu/fins/storage/_fs_maintenance_core.py` | 92.39% | PASS |
| `dayu/fins/storage/_fs_processed_core.py` | 88.83% | PASS |
| `dayu/fins/storage/_fs_source_document_core.py` | 83.06% | PASS |
| `dayu/fins/storage/_fs_source_snapshot.py` | 90.42% | PASS |
| `dayu/fins/storage/_fs_storage_infra.py` | 86.14% | PASS |
| `dayu/fins/storage/_fs_storage_utils.py` | 83.82% | PASS |
| `dayu/fins/storage/fs_batching_repository.py` | 94.44% | PASS |
| `dayu/fins/storage/fs_company_meta_repository.py` | 100.00% | PASS |
| `dayu/fins/storage/fs_document_blob_repository.py` | 100.00% | PASS |
| `dayu/fins/storage/fs_filing_maintenance_repository.py` | 100.00% | PASS |
| `dayu/fins/storage/fs_processed_document_repository.py` | 100.00% | PASS |
| `dayu/fins/storage/fs_source_document_repository.py` | 96.10% | PASS |
| `dayu/fins/storage/local_file_source.py` | 100.00% | PASS |
| `dayu/fins/storage/local_file_store.py` | 98.92% | PASS |
| `dayu/fins/storage/repository_protocols.py` | 100.00% | PASS |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.54% | PASS |
| `dayu/fins/tools/cache.py` | 96.83% | PASS |
| `dayu/fins/tools/download_provider.py` | 100.00% | PASS |
| `dayu/fins/tools/download_tools.py` | 90.00% | PASS |
| `dayu/fins/tools/error_contract.py` | 100.00% | PASS |
| `dayu/fins/tools/fins_tools.py` | 86.49% | PASS |
| `dayu/fins/tools/preprocess_provider.py` | 100.00% | PASS |
| `dayu/fins/tools/preprocess_tools.py` | 75.81% | BLOCK |
| `dayu/fins/tools/read_runtime.py` | 86.26% | PASS |
| `dayu/fins/tools/read_runtime_helpers.py` | 80.62% | PASS |
| `dayu/fins/tools/result_types.py` | 100.00% | PASS |
| `dayu/fins/tools/upload_provider.py` | 100.00% | PASS |
| `dayu/fins/tools/upload_tools.py` | 90.53% | PASS |
| `dayu/fins/upload_batch.py` | 95.57% | PASS |
| `dayu/host/__init__.py` | 100.00% | PASS |
| `dayu/host/_durable_actor.py` | 84.62% | PASS |
| `dayu/host/_event_payload.py` | 98.33% | PASS |
| `dayu/host/_execution_config_projection.py` | 76.43% | BLOCK |
| `dayu/host/_execution_health.py` | 91.67% | PASS |
| `dayu/host/_runner_call_manifest.py` | 90.51% | PASS |
| `dayu/host/_terminal_answer.py` | 95.74% | PASS |
| `dayu/host/_wait_observation.py` | 90.42% | PASS |
| `dayu/host/accepted_result_projection.py` | 95.57% | PASS |
| `dayu/host/accepted_tool_outcome.py` | 95.83% | PASS |
| `dayu/host/admission.py` | 90.87% | PASS |
| `dayu/host/api.py` | 93.24% | PASS |
| `dayu/host/command.py` | 88.05% | PASS |
| `dayu/host/compact_material.py` | 86.14% | PASS |
| `dayu/host/compact_payload.py` | 90.27% | PASS |
| `dayu/host/compact_pipeline.py` | 93.63% | PASS |
| `dayu/host/compaction.py` | 88.37% | PASS |
| `dayu/host/compaction_operation.py` | 94.62% | PASS |
| `dayu/host/context_budget.py` | 92.66% | PASS |
| `dayu/host/context_events.py` | 92.88% | PASS |
| `dayu/host/dispatch.py` | 91.33% | PASS |
| `dayu/host/durable/event_log.py` | 91.33% | PASS |
| `dayu/host/durable/idempotency.py` | 98.52% | PASS |
| `dayu/host/durable/memory.py` | 88.03% | PASS |
| `dayu/host/durable/options.py` | 100.00% | PASS |
| `dayu/host/durable/outbox.py` | 89.74% | PASS |
| `dayu/host/durable/payload.py` | 88.69% | PASS |
| `dayu/host/durable/payload_resolution.py` | 84.38% | PASS |
| `dayu/host/durable/purge.py` | 95.71% | PASS |
| `dayu/host/durable/read_model.py` | 94.49% | PASS |
| `dayu/host/durable/run_transition.py` | 93.16% | PASS |
| `dayu/host/durable/schema.py` | 97.16% | PASS |
| `dayu/host/durable/session_lifecycle.py` | 94.29% | PASS |
| `dayu/host/durable/state.py` | 88.03% | PASS |
| `dayu/host/durable/tool_trace.py` | 86.68% | PASS |
| `dayu/host/durable/wait_resolution_digest.py` | 90.62% | PASS |
| `dayu/host/engine_ingest.py` | 90.75% | PASS |
| `dayu/host/evidence.py` | 95.00% | PASS |
| `dayu/host/lifecycle_events.py` | 96.60% | PASS |
| `dayu/host/llm_compaction.py` | 91.64% | PASS |
| `dayu/host/memory.py` | 92.00% | PASS |
| `dayu/host/open_host.py` | 87.62% | PASS |
| `dayu/host/outbox.py` | 96.34% | PASS |
| `dayu/host/payload_resolution.py` | 95.71% | PASS |
| `dayu/host/queue_policy.py` | 89.47% | PASS |
| `dayu/host/read_api.py` | 90.72% | PASS |
| `dayu/host/read_model.py` | 94.96% | PASS |
| `dayu/host/recovery.py` | 91.41% | PASS |
| `dayu/host/run_input.py` | 90.10% | PASS |
| `dayu/host/tool_call_request.py` | 95.24% | PASS |
| `dayu/host/tool_duplicate_governance.py` | 93.72% | PASS |
| `dayu/host/tool_runtime.py` | 88.73% | PASS |
| `dayu/host/tool_trace.py` | 89.42% | PASS |
| `dayu/host/tooling.py` | 100.00% | PASS |
| `dayu/host/wait_adapter.py` | 91.55% | PASS |
| `dayu/host/wait_boundary.py` | 81.63% | PASS |
| `dayu/host/wait_callback.py` | 86.96% | PASS |
| `dayu/host/waiting.py` | 88.74% | PASS |
| `dayu/runtime/__init__.py` | 100.00% | PASS |
| `dayu/runtime/argparse_exit.py` | 未命中 | BLOCK |
| `dayu/runtime/assembly.py` | 91.82% | PASS |
| `dayu/runtime/cancellation.py` | 92.06% | PASS |
| `dayu/runtime/config_loader.py` | 96.46% | PASS |
| `dayu/runtime/filelock.py` | 92.66% | PASS |
| `dayu/runtime/interruptible_process.py` | 88.20% | PASS |
| `dayu/runtime/lane.py` | 88.21% | PASS |
| `dayu/runtime/numeric.py` | 100.00% | PASS |
| `dayu/runtime/scene_prepare.py` | 92.55% | PASS |
| `dayu/runtime/tool_call_projection.py` | 91.04% | PASS |
| `dayu/service/__init__.py` | 100.00% | PASS |
| `dayu/service/entrypoint_runtime.py` | 88.27% | PASS |
| `dayu/service/fins_direct.py` | 90.16% | PASS |
| `dayu/service/fins_wait_adapter.py` | 94.57% | PASS |
| `dayu/service/host_admin.py` | 83.33% | PASS |
| `dayu/service/host_assembly.py` | 95.26% | PASS |
| `dayu/service/scene_context.py` | 97.26% | PASS |
| `dayu/service/wait_callback_endpoint.py` | 87.82% | PASS |
| `dayu/tools/doc_tools.py` | 80.52% | PASS |
| `dayu/tools/web/provider.py` | 92.98% | PASS |
| `dayu/tools/web/web_challenge_detection.py` | 92.73% | PASS |
| `dayu/tools/web/web_diagnostics.py` | 92.31% | PASS |
| `dayu/tools/web/web_egress_policy.py` | 85.61% | PASS |
| `dayu/tools/web/web_fetch_orchestrator.py` | 81.62% | PASS |
| `dayu/tools/web/web_http_session.py` | 89.12% | PASS |
| `dayu/tools/web/web_playwright_backend.py` | 90.00% | PASS |
| `dayu/tools/web/web_resource_budget.py` | 100.00% | PASS |
| `dayu/tools/web/web_search_projection.py` | 96.36% | PASS |
| `dayu/tools/web/web_search_providers.py` | 87.46% | PASS |
| `dayu/tools/web/web_tool_projection_text.py` | 100.00% | PASS |
| `dayu/tools/web/web_tools.py` | 80.76% | PASS |

## Appendix B — artifact measurement

以下 fixed-width wc 值在最终文件写入后复核。canonical SHA 的定义刻意排除其自身这一行，避免不可能的 cryptographic self-reference；最终完整文件 SHA-256由 handoff响应外部报告。

artifact_final_wc_lines: 0000000668
artifact_final_wc_bytes: 0000043672
artifact_canonical_sha256_excluding_self_hash_line: fa6fd6f604f006655696505ada19e9d370772b7ef57333bf631a8fb691bd26fd

复核命令：

    wc -l -c docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md
    grep -v '^artifact_canonical_sha256_excluding_self_hash_line:' docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md | shasum -a 256
    shasum -a 256 docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md
