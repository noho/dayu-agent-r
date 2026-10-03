RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-1f75a5cf

# UM-O18-F01 PR3 plan fix 记录

- 工作区：`/private/tmp/dayu-upload-o18`；只修改 `docs/gateflow/upload-material-o18-amended-plan-20260929.md` 并新增本记录；未改产品代码、测试、README、goal、adjudication、queue 或旧 review，未实施、commit、push、PR、merge、派发子 Agent。
- 旧计划 SHA-256：`61a6cb02eacaed4e3e48e63d9bacb6b22cf1c46cd635530338a0f4250e27b62d`；**新计划 SHA-256：`0d3f109b2f538d26cddd8ca6b4dd89da03e3ac27cd7e57915aefaa4b055892ce`**。
- Gate：PR3-F2～F9 已按总控裁决修订候选计划；仍须同版 Kimi/MiMo 双路 plan re-review，通过前不实施。ds-flash PR3-F1 关于「没有 state plan / tombstone create 无合同」的推断已由总控撤回，未据此发明行为。

## 裁决到计划的差异

| 裁决 | 修订 | 直接证据 |
| --- | --- | --- |
| PR3-F2 | metadata-only、delete、常规/overwrite 内容发布的**每个 material mutation batch**均注册 O12 `expected_source_state` 与 post-company `expected_company_meta`；拟 skip 只用同一 guard 的只读比较。验收加真实仓储 A prepare→B commit→A commit 的 delete/content 交错和公司状态漂移，不把 skip 当 mutation batch。 | O12 accepted plan「storage 同版状态与分阶段 guard」第 43～47 行明定两类材料 precondition 与 skip 只读 guard；原 O18 计划仅细写 metadata-only/skip。 |
| PR3-F3/F4 | 将 read tool 说明真 owner `dayu/fins/tools/fins_tools.py` 与 `tests/tools/test_combined_tools_acceptance.py` 加入条件白名单；read 范围精确为 `list_documents.documents[]` 与 `recommended_documents`，后者维持 ID/null 推荐槽位，不虚构详情。 | `fins_tools.py:387-419` 定义 `list_documents` 描述；`read_runtime.py:887-945` 组装两个结果表面，`:910` 的 documents 项含 amended，`:725-773` 的推荐仅给 ID；`:2546-2575` 的 `_SourceDocumentMeta` 是内部读取，不是 LLM-facing 详情。 |
| PR3-F5 | 逐表面记载 processed meta/manifest 的 `amended` 为 preprocess 时点快照；独立风险 `fins-material-processed-amended-projection` 审时间语义、失效/重处理和消费者契约；O18 不改 processed writer。若发现它被消费为当前发布值，停下相关实施并给 writer→consumer 直接调用链。 | `ingestion_runtime.py:5786-5817` processed 已有时可 skip，新处理时 `_build_processed_meta`；`:8491-8514` 复制 source meta；`_fs_processed_core.py:565-588` 写 processed meta/manifest amended；`read_runtime.py:2546-2575` 当前发布标记取 source meta，`:2750-2776` 只从 processed meta 取财务能力标志。 |
| PR3-F6 | 删除现行不可达的「不安全 material 指纹」例外，仅在未来 fingerprint owner 改变 `identical_skip_safe` 时重审八格。 | `docling_upload_service.py` material 路径现行 `identical_skip_safe=true`；两份旧 review 均核过 `_can_skip_upload` 与版本 owner。 |
| PR3-F7 | 健康首次/重复 delete 终态均 `deleted`、requested=stored=0，保留最后发布 amended；O13 仅拥有重删时间幂等。 | O13 accepted 裁决与 O18 总控 PR3-F7；原计划 §8 的「重删 `skipped`」与终态表矛盾。 |
| PR3-F8/F9 | 补 O16/O05→O12 传递依赖；逐格注明 O12 plan gate pass 但产品未实施，O14/O15 共用 state plan 已存在但本版 gate 未双路闭合、产品未实施。 | O12 plan SHA `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，其 adjudication 末节判 plan gate pass 且待 O16/O05 accepted+integrated；state plan SHA `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` 实测一致，文件第 3 行标 plan fix、非实施通过。 |
| 已撤回 PR3-F1 推断 | 保留用户八格与 `--overwrite` 强制转换/发布、同指纹保版；state plan 第 103 行的 material tombstone + create 无 overwrite 保持现有 source upsert/storage 拒绝，**不作新 typed O14 接受标准**。 | `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md:91-103` 明列 active create、missing update/delete、tombstone auto/重复 delete 与 tombstone create；O18 adjudication 末节撤回旧推断。 |

## 核验与剩余风险

- 实读本工作区 `AGENTS.md`、binding goal、总控 adjudication 末节、ds-flash review、MiMo review；实测 O12/state 两份计划 SHA 与引用一致，O12 gate 状态以 adjudication 末节为准，不将其计划页首旧状态冒充最新裁决。
- 静态核对新计划仍有八格；`metadata_updated`、`--overwrite` 同指纹重转发布且保版、`requested_amended`/`published_amended` 三域、O12/O14/O15 实施硬停均保留。新计划的 source/post-company 双 guard、read 说明 owner、processed 停止条件和 O16/O05 依赖均在文；两份未跟踪文档的尾随空白/末尾换行与计划 SHA 回填断言通过。`git diff --check` 也 exit0，但不覆盖未跟踪文件。此次仅改 Markdown，未运行 pytest、pyright 或真实 CLI canary；计划中的 CLI canary 是未来实施验收配方，**不是本轮运行结果**。
- 当前未见 `list_documents` 把 processed 快照用作发布标记，但 processed manifest 和 `DocumentSummary.amended` 仍可能被其它消费者误读；实施前须逐调用链复核。若发现实际消费者作为当前发布事实、O12/state 合同与计划事实不符，或 read 描述需要白名单外 owner，则停止相应修订/实施并提交直接调用链，不加下游补偿。
- O12 产品未实施；O14/O15 计划 gate 未双路闭合且产品未实施；O16/O05 传递依赖也须就绪。此计划不是 implementation handoff。下一 gate 仅为总控安排的同 SHA 双路 plan re-review。
