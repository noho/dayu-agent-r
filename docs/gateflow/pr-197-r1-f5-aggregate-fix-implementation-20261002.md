RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-c341826a

# PR197 F5-AG01 aggregate fix 作者实施交付

任务 label：`pr197-f5-aggregate-fix-sol-20261002-01`。本轮实际进程链为 codex-agent-run `--provider gpt-6-sol` → codex exec `-p gpt-6-sol --ephemeral --json`，线程事件 `thread.started` 的 ID 为 `01a0fae2-c612-72f2-be52-5fc403b40b8b`。当前运行事件没有实际 model 字段，故明确写 unknown，不从 profile/canary 推造模型名。canary 来自本轮指定文件实际读取，SHA256 `de1ea1755dd75cbc3deed09bcbd0c450940bae014f4f565fd82ce344ca1345f9`。

## 目标、版本与授权边界

- 当前同一 F5-S1 完整行为 WU 的必要修复 AG01；已完成作者实现、owner regressions、README 决策及本轮最终版本验证。当前仅 author delivery，root 独立核收及双路 aggregate re-review 尚未执行，不宣称 aggregate/gate/PR/final closeout pass。
- 唯一 workspace `/Users/leo/workspace/dayu-agent-r`，唯一 branch `codex/upload-material-oracle`；HEAD 始终 `0d8de8cb6bfdf490b6d790611e9547bb48d44560`，base `3a836a463aab3eeffb050facd592e614801d6ca9`，main 始终 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。未 commit/push/PR/merge，未新 branch/worktree/clone/detached，未派发子 Agent。
- 已先读 AGENTS、指定 accepted plan/checkpoint、user-decision、S1 final adjudication、AG01 finding、MiMo report 与 root 三件独立取证。accepted plan 的 candidate header 保持历史；不修改既有裁决/报告/controller/handoff/preparation，不重开用户财期裁决或 IV01–05。
- 已知 A 正常处理、B 未知单列不猜、query_window ∩ union(period_windows)、remote 同窗/local 不误滤及 F6/F7 词表不变；全部既有 A/B 业务断言原样保留。

## 根因、唯一 owner 与最小修改

动机成立，严重度沿用 root 已接受的中等级别。原 published get 通过 persisted meta → source root → `_ticker_dir_for_read` 严格解析公司身份；原 list 同样经严格根。F5 抽取稳定根 helper 后，两个 published wrapper 改为仅计算路径的 `_target_ticker_dir`，真实 ticker descriptor 损坏因此被三读入口及 CN rebuild 空结果掩盖。根因与直接异常/成功返回证据同源，不是财期逻辑问题。

唯一修复 owner 为 `dayu.fins.storage` 的 published-read 根解析/共享 core 委托边界。本次仅：

1. `_get_source_meta_unguarded` 先用 `_ticker_dir_for_read(external_ticker)`，仍委托原 `_get_source_meta_at_root`。
2. `_list_document_ids_unguarded` 先用 `_ticker_dir_for_read(normalized_ticker)`，仍委托原 `_list_source_ids_at_root`，含显式 kind 和无 kind 两支。
3. 相关 core 异常 docstring 标明 company typed 原样传播；纠正旧 private getter 的“逻辑删除即 FileNotFound”文档误述，实际逻辑删除仍可 raw 读取。

未改 acquisition/finally/异常投影；meta view 仍先完整枚举再读成功前缀，ticker 身份失败在枚举阶段原样抛出，文档 raw 读取仍保留原 read_error 对象与完整 meta/文档 descriptor 校验。published integrity view 仍将显式根交给 whole-kind inspector；ticker 根损坏仍为 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`，没有统一成 company typed。真实 open staging capability 仍只消费 staging 根，closed capability 仍拒绝。workflow/runtime/CLI/helper/schema 未增加 fallback、硬化或兼容分支。

## 必要 owner 回归

仅新增于两件既有测试文件，均用真实 Fs 仓储、真实 batch 和正式 commit；来源文档 descriptor 与 ticker descriptor 严格区分。

| 回归 | 新增参数用例 | 真实断言 |
| --- | ---: | --- |
| published 三读入口及 core 无 kind 枚举 | 32 | filing/material × ticker descriptor 缺失/畸形/symlink/错 canonical × get/meta view/list/list-all，全部原 typed `invalid_descriptor`；恢复原 descriptor 后独立 core 写者可开启/回滚，原 meta 不变 |
| locator/whole-kind/staging 边界 | 8 | locator 仍 company typed；published integrity view 仍 unsafe_publication；已开放真实 staging 即使 published 后被损坏也能读 A/B COMPLETE；rollback 后旧 capability 拒绝 |
| 正常控制 | 2 | ticker 真缺席 list[]/empty view、文档真缺席 FileNotFound/MISSING、完整元数据同源、逻辑删除字段为 True 且物理分类仍 COMPLETE |
| CN rebuild 空命中 | 2 | 正式发布 material（filing 空枚举）或 upload filing（非 download，空匹配）；正常对照 ok/filings[]，仅损 ticker descriptor 后原 typed 失败；全部来源原字节不变，provider/转换调用为零 |

CN 测试只有未使用的 provider/converter 为既有隔离替身；source/blob/batching 均真实，未通过 mock/Fake 绕过仓储 owner。完整回归继续覆盖文档级 descriptor、raw 错误对象与 finally、F4 两 rename guard 窗口、完整性/删除/取消及 F5 A/B 业务断言。

## 验证与失败记录

全部验证先 `source .venv/bin/activate`。实际 cwd、argv、Python 版本、VIRTUAL_ENV/PATH/PYTHONPATH/COVERAGE_FILE/PYTHONDONTWRITEBYTECODE、真实 exit/stdout/stderr、duration 与输出 SHA 均在本轮 `validation/*.command.json` / `*.receipt.json`。入口仅为 `workspace/tmp/pr197-f5-aggregate-fix-sol-20261002-01/run_validation.py`。

- 实修前先保存明确红测：首轮 36 failed/8 passed，其中 34 个 AG01 真实失败，另 2 个是作者把逻辑删除误写为物理 MISSING 的控制测试误断。读取 inspector 并据实修正测试；产品删除语义不变。保留首轮原 stdout/stderr/exit，不冒充全部都是 AG01。
- 修正控制测试后的实修前红测：34 failed/10 passed，全部 AG01 反例都为 DID NOT RAISE。实修后 focused 44 passed；最终版本 focused 也为 44 passed（126 deselected 为显式 focused 选择，完整回归无该筛选）。
- 首轮完整回归 1747 passed/3 warnings。首轮 full pyright 因新增 CN 测试把 protocol-typed pipeline 仓储传给具体 Fs 测试 helper 而出现 2 errors；通过显式创建并注入共享 core 的真实 Fs 仓储修正测试类型，不改生产或加 cast/shim。失败原件完整保留。
- 测试字节变化后必要重验：最终完整 **1747 passed，3 warnings，exit 0**；最终 `python -m pyright dayu/ tests/ utils/` **0 errors/0 warnings/0 informations，exit 0**。不以首轮产品验证充当最终测试版本通过，也不复用旧 1703 结果。
- 完整命令严格来自 `docs/gateflow/evidence/pr197-f5-final-20261002/complete.command.json`，保留全部 22 测试文件、pytest/coverage 参数和 warning；仅替换本轮 JSON 输出与 cache 路径，COVERAGE_FILE 换本轮独立路径。未修改 companyidentity 测试，故无需追加该文件。无新增生产文件。
- 3 条 pytest warning 为 edgartools 的 `html_documents`、`files.html`、`htmltools` 弃用提示；pyright 输出还保留版本更新通知（v1.1.409 → v1.1.414），不是类型 warning 或验证失败。未隐藏输出、未升级依赖。
- 普通 `git diff --check` exit 0；不重写 raw 历史证据。

| 运行 | 真实 exit | wall 秒 | stdout SHA256 |
| --- | ---: | ---: | --- |
| `focused-red` | 1 | 2.132 | `f17ebdc81eaa16b2cb1bcf352c20b57bfaab75e743770026ed1ef07933872edf` |
| `focused-red-owner` | 1 | 2.941 | `d259523fedb19ae60ab28f2e879c4530c34a6dcdd348a8ca66f6233ea7be1042` |
| `focused-green` | 0 | 2.003 | `55e93ba3823e4b63f6e618d35b4bd28d18b49c2c5993c66130fb02ac20be22ec` |
| `complete` | 0 | 70.557 | `aed5491f03f5535d45e6d881d1446a3969a41796a6d76c5269821648a7214bbe` |
| `pyright` | 1 | 34.800 | `36a75e1407864521de16cf73ae80e998b96e85d84d7f8698fad4f9b1ceaf198f` |
| `focused-green-final` | 0 | 1.973 | `ec1f59d8773ac2e649756d8371ad304d089d3b690083c825614be390c6c399d1` |
| `complete-final` | 0 | 71.372 | `7493df7c4807bdceb8134494b89ad558179e5a5a236435b29ec4171920cf3fc8` |
| `pyright-final` | 0 | 35.991 | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` |

最终 focused、完整 pytest、全量 pyright 的 before/after manifest 全部逐字相同，覆盖 **46 产品 + 相关代码依赖，共 77 件输入**。23 个生产文件均 ≥80%；coverage raw JSON 为 `validation/complete-final.coverage.json`，原 coverage data 为 `validation/complete-final.coverage-data`，同源逐件汇总为 `validation/product-coverage-final.json`，不以全仓总率替代单文件目标。

| 生产文件 | covered/statements | 当前实际覆盖率 |
| --- | ---: | ---: |
| `dayu/cli/output.py` | 176/206 | 85.44% |
| `dayu/fins/direct_event_text.py` | 74/85 | 87.06% |
| `dayu/fins/direct_events.py` | 407/455 | 89.45% |
| `dayu/fins/download_contract.py` | 415/473 | 87.74% |
| `dayu/fins/downloaders/cninfo_downloader.py` | 301/334 | 90.12% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 390/458 | 85.15% |
| `dayu/fins/ingestion_runtime.py` | 2221/2434 | 91.25% |
| `dayu/fins/pipelines/cn_download_models.py` | 110/113 | 97.35% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40/40 | 100.00% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 161/186 | 86.56% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 68/79 | 86.08% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 277/291 | 95.19% |
| `dayu/fins/pipelines/cn_pipeline.py` | 441/466 | 94.64% |
| `dayu/fins/pipelines/cn_report_selection.py` | 268/291 | 92.10% |
| `dayu/fins/pipelines/hk_download_rebuild.py` | 90/98 | 91.84% |
| `dayu/fins/pipelines/hk_fiscal_calendar.py` | 56/58 | 96.55% |
| `dayu/fins/pipelines/sec_pipeline.py` | 406/470 | 86.38% |
| `dayu/fins/storage/__init__.py` | 15/15 | 100.00% |
| `dayu/fins/storage/_fs_source_document_core.py` | 448/518 | 86.49% |
| `dayu/fins/storage/fs_source_document_repository.py` | 90/93 | 96.77% |
| `dayu/fins/storage/repository_protocols.py` | 250/293 | 85.32% |
| `dayu/fins/storage/source_meta_read.py` | 20/20 | 100.00% |
| `dayu/service/fins_wait_adapter.py` | 188/201 | 93.53% |

## Changed paths 与 README 决策

| 本轮路径 | 输入 SHA256 | 最终 SHA256 |
| --- | --- | --- |
| `dayu/fins/README.md` | `87064d15a37634a596d710f50875d338acda10bd09c339cd635a4acf005b31bd` | `524d56d6e2e105aa24c9191f4273d110d065e6bd431b5f58a199f05a1607278f` |
| `dayu/fins/storage/_fs_source_document_core.py` | `639992696357a91c33285ef41890e2e68fe0043fa646aa89e1d92d0ec467ffbd` | `d3903c194ed84e03a4bc353a75c00c1de1d1673d098f8a39244443b60639776c` |
| `tests/README.md` | `ac9e6330da882dc9210dac4d945cbdd51a3efbb8a8cbbfba6148de6e7640ea4b` | `2c75613c2280c6bd5204e5f31f97eb34104b88299c989cca42f0495744e0d7f9` |
| `tests/fins/test_cn_download_workflow.py` | `13ab63293142f323c7d23ff8dc4bd46776f3c4c49d02d15ae599e25c49a62be5` | `590a4b694bd56868b6ddd17dd4dd3db4ca1834b956f713e6e57269423accbdef` |
| `tests/fins/test_f5_storage_calendar.py` | `2ab1e0f5a6ff42637c5f0f37bf559182bdc5453e3b49e7cdba769ec4a45497d0` | `08e7f21c1e3fea88c025d42c6b9b5cedf4b2fb228bf70741a75ecd724fd4a0c0` |

以上仅五件产品/测试/README 路径；另新增本正式 implementation artifact，及自身 `workspace/tmp/pr197-f5-aggregate-fix-sol-20261002-01/` 的验证/临时脚本。作者规范 delta 为 `author-fix.diff`，SHA256 `b748d0ab6bd1f92e41d4f9beb91cb3df470d72f2bbf10f259f0e8e945d434f29`。

已读三个 README 职责约束：Fins 只补 published strict root 与 staging/whole-kind 稳定边界，tests 只补当前真实 owner 回归。根 README 不改：没有新入口、参数、通道、退出语义或用户工作流；本次恢复既有 storage 读契约。层关系未变，不触发 dayu README。README 不写 gate 过程/未来能力。

## 输入、输出 SHA 与只读保全

开始时完整冻结文件 SHA 与 77/11 件逐件 SHA 已核收，记录 `inputs.json`；本轮额外只读证据记录 `readonly-evidence.json`。原 11 件 validation、6 官方 Raw、accepted plan/checkpoint、旧报告和相关只读证据全部未改。原 77 文件只有上述五件授权路径发生变化；输入/最终逐路径字节均有记录。

| 指定只读证据 | SHA256 |
| --- | --- |
| `docs/gateflow/pr-197-r1-f5-aggregate-identity-read-finding-20261002.md` | `868eadda6feb4a96eacadde9fe525057492953fa3102b72456232633ac7288bd` |
| `docs/reviews/code-review-20261002-113431.md` | `bd0e4b038c47fa0ac0dcfbbce2f2808d0b134eef1a352ba103075cf133d575b0` |
| `workspace/tmp/pr197-f5-aggregate-20261002/freeze.json` | `fa2fdee9ada161836da20e92ac2559a890afc1a91a2e3189b6f6b890d4c0333b` |
| `workspace/tmp/pr197-f5-aggregate-20261002/root-validation/identity_read_probe_02.stdout` | `079c558062173b539fbc6667924b07b8c3337f24a6a29d67a4befc7ffdfade35` |
| `workspace/tmp/pr197-f5-aggregate-20261002/root-validation/identity_read_probe.receipt.json` | `c995eff4c5d0b19834be58debf744881aa126aafb2e157a1127c554b75de937d` |
| `workspace/tmp/pr197-f5-aggregate-20261002/root-validation/identity_base_contract.json` | `de7946a235bcf958c6817bde3f189214cf0b69d3840a6bf681b413cc40016ee5` |
| `docs/gateflow/evidence/pr197-f5-final-20261002/complete.command.json` | `9708499d74f9144eb23cba14c872b5b589b265e11064ccff72a44eed8cef4789` |

最终 46 产品及 77 依赖 SHA 在 `validation/complete-final.manifest-before.json` / `complete-final.manifest-after.json`；全量类型检查同源 manifest 在 `validation/pyright-final.manifest-{before,after}.json`。所有本轮证据与本 artifact 的实际输出 SHA 在外部 `outputs.json`，避免自引用 SHA。工作区原有 controller/handoff/preparation 改动保留，不覆盖、stage 或 reset；另有 root 并发生成的 aggregate-initial adjudication 仍只读，不归为作者 changed path。

## Residual 分类、未覆盖与停止点

- 新增成立 scope 外问题/owner 不清/必需扩大范围：无；没有顺带实现或登记后偷做。AG01 author 修复及必要验证已交付，是否核收由 root 独立证据裁决。
- 既有信息边界：calendar/selection owner 的窗口外未取得年度冲突、52/53 周、transition year、未支持标题仍未知，destination 为后续明确授权 WU；当前不扩大网络/解析承诺。
- 既有非目标：runtime/storage 的 late ordinary 全局快照与通用大结果重构仍沿 accepted plan §10；没有新 finding 证据，不做假设硬化。
- 本轮未覆盖：upload17、XBRL、最终真实 CLI CI/oracle/scenarios/readiness、生产网络/Docling 与服务现场；destination 为原后续队列。当前仅指定完整离线 owner 回归，不宣称全仓所有行为覆盖；整仓 pyright 已真实通过。
- `unknown` 实际模型字段是运行事件未暴露的身份取证限制，不以 provider profile 替代。不影响本轮产品验证的实际命令、字节与退出证据。
- 本次结束后停止；下一动作为 root 独立核收和双路 aggregate re-review。本作者不 commit/push/PR/merge，不推进其它 gate，不再为 nit/文案派发任务。
