RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-f9861bfd

# G5：O33 同 identity 并发权威裁决准备计划

任务：`pr197-g4g5-plan-preparation-sol-20261001-01`。状态：**conditional preparation proposal；implementation blocked on final owner rebind；非 accepted plan / gate pass**。
第三列精确模型无可读取遥测，不从路由/canary 推断。用户原 goal 已批准，本轮不重问裁决、不实施；所有最终成果仍在 PR197，用户手动 merge。
唯一主树 `dayu-agent-r`、指定 branch `codex/upload-material-oracle`；F5 Sol97574 是唯一产品 writer，本轮只写两 proposal 与独占证据，不接触其它 runner 报告。

## 1. binding goal、版本与第一性原理

- 只读 OID=`3a836a463aab3eeffb050facd592e614801d6ca9`；40 件 pinned 校验一致，freeze `absent=[]`。
- `workspace/tmp/pr197-g4g5-plan-preparation-sol-20261001-01/freeze.json` SHA-256=`9ae2c95cdd86b6ba7402b5547d063a6df7e98523d5ef77d2e4a578cf16b25838`；首末核验/补源 hash 见同根证据索引。
- 正式 goal：`docs/gateflow/upload-material-o33-concurrency-goal-20260929.md`；oracle：`docs/reviews/upload-material-um-o33-oracle-adjudication.md`；同源补证：`upload-material-o33-e01-evidence-20260929.md`。
- 旧候选 `upload-material-o33-concurrency-plan-20260929.md`、必要旧裁决 `upload-material-o33-plan-review-adjudication-20260929.md` 只作合同/反例来源，不继承旧隔离树安排或 gate 票。
- **唯一 S1：同一 auto 请求竞争后的权威相同性裁决到完整终态**。恰一 success、一 skip；只有完整 published target、same exact identity/最终 G2 role fingerprint、same amended、无公司/alias 漂移才可 skip；skip 零业务 diff，时间/版本不改。
- 动机成立：顺序相同输入已有 skip，竞争败者应收到同源幂等结果；旧证据只证明最终一份完整材料，不证明半发布或统计成功率。
- E01 第二组真实异常链为 stale `auto→create` → `commit_prepared_upload_batch` → source create → `FileExistsError`。这是旧精确基线的同源根因证据，不凭 CLI `storage_io` 文案定位，也不反推冻结 L06 的具体异常。
- 不新增公开分类/schema、不造重试框架、不加无限 retry/长时全局锁/第二 snapshot fallback；健康 tombstone 恢复与重复删按 G3 保持，download indeterminate residual 不自动前置。

## 2. pinned 实际源码与 owner 缺口

| owner / 真实函数 | pinned 事实 | 对 S1 的意义 |
| --- | --- | --- |
| 身份 / `build_material_ids`、`validate_material_upload_ids` | SEC `sec_upload_workflow.py:461–482` 在准备前读 previous_meta 并解析动作；CN/HK 同构 | G1 最终 exact identity 真源必须带入 admission，不能从 CLI/路径反推 |
| 字节/角色指纹 / `_build_upload_source_fingerprint` | `docling_upload_service.py:1595–1686` material 当前按 original name/hash/size/source 排序，不含 material primary；filing 角色另有既有合同 | **G2 material primary/fingerprint 尚不能按已存在接口引用**；最终重绑，不复制 filing 算法 |
| 准备 / `DoclingUploadService.prepare_upload` | `:468–488` material 旧 meta 同指纹直接早退；`:530` candidate 未暴露 material publication identity/skip-safe typed public accessor | 竞争 skip 必须延后到 G3 权威裁决，不用早退结果当完整 target 证明 |
| 独立公司 / `stage_company_meta_for_upload` | SEC `:505–518` 先 company batch；CN 同构 | O34 独立合法事实保持；G3 最终 decision/post-company guard 替代旧重判接缝 |
| source create / `_upsert_source_document` | `_fs_source_document_core.py:1797–1798` staged meta 已存在即 FileExistsError | 与 E01 stale create 同源；存在本身不证明相同/完整，不 catch FileExistsError 猜 skip |
| writer / `_FsStorageInfra.begin_batch` | `:454,476–486` 取得 ticker writer 后复制 published tree；持锁到 commit/rollback | 竞争 winner 必须在 loser begin_batch **之前**提交；不能在 loser 持锁时等 winner commit |
| publication / `_commit_batch_with_publication_guard` | `:692–706` guard 内 backup/swap/COMMITTED；`:728–735` COMMITTED 后 release 可抛 | 不得“异常 ⇒ 未发布”；取消与能力转交沿当前 owner |
| API / `BatchingRepositoryProtocol.commit_batch` | `repository_protocols.py:702–721` 正常返回以 COMMITTED 为真源，异常没有 typed material certainty outcome | 内部 phase 有真源，material 调用方异常通道缺发布确定性证明；明确 fail closed，不新造成功承诺 |
| 完整性 / `classify_source_integrity` | 当前 source classifier 可检查 material；`FilingUploadPublishedState/read_filing_upload_state_in_batch` 仅 filing | 分别读完整性/meta 不是 material 同版合同；G3 必须给唯一同版 owner，不拼第二快照 |

已有 `filing_upload_publication.py` 的 arbiter/execute、prepared filing 描述器及 storage filing state 是边界参照，**不是可直接套用的 material API**；不得兼容 wrapper/re-export 或将 filing 文案下游改成 material。
真实 callers：SEC `run_upload_material_stream`、CN/HK `CnPipeline.upload_material_stream` → `prepare_upload` → `commit_prepared_upload_batch` → `publish_prepared_upload/_store_upload_assets` → source 仓储 CRUD → `commit_batch`；direct/CLI/tool/job 只接收统一 pipeline outcome。

## 3. 最小 proposed API（全部 proposal，最终名称/类型须重绑）

优先在 G3 最终 material publication arbiter 增加窄规则；以下是合同草案，不宣称这些类型、方法已存在，也不要求另建协调器。

```python
# proposed：归准备 owner，candidate 只接受已完成的 material mutation。
def describe_prepared_material_publication(
    prepared: PreparedDoclingUpload,
) -> MaterialUploadPublicationIdentity: ...

# proposed：若 G3 已有同职责 arbiter，只扩其规则，不另建透传 helper。
def arbitrate_material_auto_publication(
    *,
    initial: MaterialUploadAdmission,
    fresh: MaterialUploadAdmission,
    candidate: MaterialUploadPublicationIdentity,
) -> MaterialAutoPublicationDisposition: ...
```

`PreparedDoclingUpload` 是 pinned 现存类型；其它名称均本 proposal 对最终 G1/G2/G3 合同的待重绑称谓。
candidate 是窄 publication identity：exact ticker/document/internal identity、owner 已产生的 original descriptor 与 G2 primary 角色/fingerprint、amended；skip 资格必须消费最终 preparation/fingerprint owner 同源产生的 closed 事实，不能见 digest 相等自行宣称 safe。不放取消/日志/UI/公司写意图等 god bag。不得另算 hash/资产名，若 G2 已暴露同源描述器则复用它。
initial/fresh 复用 G3 admission 的同版 published state 与封闭公司 decision；state 必须含完整性、可信 active/tombstone meta、opaque revision、权威 publication identity，以及 G3 阶段性公司/alias guard 真源。revision 是并发引用标签，不是业务事实或成功依据。
proposed disposition 只供内部 `PUBLISH / IDENTICAL_SKIP / CONFLICT` 裁决；conflict/failure 复用 G3 既有 typed owner 投影，不新增公开 status/reason enum。不把 proposed 内部标签投影成财报结论。
默认 mutation/初始顺序 skip/metadata-only/delete 都沿 G3；只对 requested auto、非 overwrite、非 repair 的竞争窗口增加同一性例外，不改显式 create/update/delete。
若最终 G3 admission/API 无法表达上述事实，阻塞交 root 回 owner，不能按本草案直接发明 storage schema。

## 4. S1 白名单、完整时序与 fail/cancel/commit guard

候选产品白名单：`dayu/fins/pipelines/docling_upload_service.py`（描述已产生候选事实/统一 skip result）、`sec_upload_workflow.py`、`cn_pipeline.py`（机械接同一个 owner）；G3 最终 material publication 模块（路径待 root 绑定，不在 prep 新建）。
storage 合同必要时只限 `repository_protocols.py`、`_fs_source_document_core.py`、`_fs_storage_infra.py`、`fs_source_document_repository.py` 和 G3 最终同版 material state 实现；不是整 storage 开放重构。
`upload_failure.py` 仅消费最终已批准 typed failure；runtime/CLI/Service/tool 产品默认不改，无新推断逻辑；最终白名单未绑定前不得开工。
测试白名单：`test_docling_upload_service.py`、`test_fins_storage_atomicity.py`、`test_filing_upload_publication.py`、`test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py`、`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`，以及 G3 最终 material publication owner 测试（路径待绑定）。

1. G1 接受稳定 exact 请求，G2 单次资产计划携角色；G3 得到 initial 同版 state/decision。fresh 缺名/动作/alias 规则先由各 owner 执行，不在 G5 改优先级。
2. 合法公司事实由独立公司阶段 commit；保留 O34 语义。相同并发输入的 loser 不得重复刷新公司时间/版本；这项 no-op 必须由 G3 公司 decision/commit owner 保证，不靠 G5 回滚。
3. 读取原件并产生最终同源 fingerprint/amended/candidate；material 全原件 Docling。失败/取消只保留已合法独立公司事实，不发布本材料。
4. winner 完整提交后，loser 才取得自身 writer capability。storage 用 G3 唯一 writer-owned view/guard 合同读取 fresh 同版事实；证明其来源为 acquisition 时 published tree，不能读本请求 staged mutation 冒充 winner。
5. alias/公司优先冲突先判，只有另一方完成导致目标出现且可证明完整 active、exact identity/角色指纹/amended 均同一、无其它公司/alias 漂移才 IDENTICAL_SKIP。不能简单要求“revision 必须旧值”，也不能忽略 revision 所表示的其它状态变动。
6. 同一性判定与后续 no-op 受 G3 相同锁序/guard 保护；释放锁后的旧结论不可再使用。选定同一次 fresh read，不能从普通冲突 catch 再读第二 snapshot/retry。
7. skip 不 stage 材料/公司 mutation、不 physical swap，沿唯一生命周期 owner rollback/关闭未提交 capability；stored=0，canonical file-skipped/result/最终 published amended 从 owner 同源投影。rollback/release 失败是 operational failure，不能仍报 skip。
8. 非同指纹、异 primary、异 amended、alias/公司漂移、corruption、missing/tombstone 都不能套竞争 skip；G3 动作/完整性规则给 typed conflict 或合法状态处理，异 amended 保留 G3 metadata-only 合同而不伪装 skip。
9. 真正 I/O、锁故障、commit 异常原样走 storage owner；一旦进入 commit，capability 已交 storage，caller 不再 rollback、不再观察取消、不再做相同性重判。COMMITTED 后 release/cleanup 异常绝不猜 skip，也不据异常说未发布。
10. F6 两取消 checkpoint/active-only 终态与 G3 完全一致；取消已赢则 cancelled，commit 已赢按实际 outcome；cancel 不是冲突后重试许可。各市场、direct/job/observation/CLI 只投影一个结果。

## 5. 旧 accepted findings 与精确 blocked 项

| 必要裁决 | 本 S1 的闭合映射（待实施，not-run） |
| --- | --- |
| O33-F01 / E01 | 权威 window 再裁决 stale auto-create，success+skip；禁止 FileExistsError/storage_io 文本判定 |
| O33 C1（O34） | 公司与材料独立 commit；材料失败保留合法公司，不制造全命令事务；同请求 skip 仍零业务 mutation |
| O33 C2 | 本轮正式 oracle 已在 freeze 实读；state/O12 最新正式 adju 由精确 OID 补源；不再访问废止隔离路径 |
| O33 C3 | 明确异常不能证明未发布；publication certainty 不足回 material storage owner；download residual 非自动依赖 |
| O12-PR5-F1/F2/F3 | G3 active-only job 双摘要、无 runner、selection/O16 边界由 G3闭合；G5 只验证终态消费，无 upload/download 共用路径重写 |
| state PR-C5-F1–F3 | 唯一 usage producer source-kind 文案、hint 边界/raw CLI format 由 G3/G1闭合；G5 不造第二表 |
| O18 PR4-F1/F3/F4/F5/F6 | barrier 在 begin_batch 前；amended 从实际发布 outcome、同字节同标记才 skip；沿 G3 guard，metadata-only 不改日期等其它事实 |

**B1：material 同版完整 publication identity / guard 未集成于 pinned**。现存 material 自由 meta read 与早退不能证明完整相同；G1/G2/G3 最终接口实施前必须正式绑定。owner：G3 storage/material publication；交 root，不让用户重述 goal。
**B2：异常通道 publication certainty 缺口**。storage `_ActiveBatchState.phase`/journal 知 COMMITTED，但普通 RuntimeFileLockError/OSError 不携 typed material outcome；两条分别“尚未 swap 的锁失败”和“COMMITTED 后释放失败”可投影同类 operational failure，caller 不能判未发布。
B2 不阻碍本次条件 proposal；S1 必须把相同性裁决放在本请求 commit 尚未开始的 guard 窗口，并排除所有 commit 异常。若实现需要对这些异常声明发布/未发布或成功承诺，先回现有 storage owner 合同裁决；不创公开分类或顺手实施 download WU。

## 6. owner / 真实 FS / barrier / 最终 CLI 测试

| 样本 | owner 级必要断言 |
| --- | --- |
| fresh 同 exact auto/bytes/primary/amended | 两请求 old admission 完成，B 先 commit，A 后 begin_batch：一 uploaded、一 skipped，单完整 active target/manifest 条目 |
| 顺序同输入、并发 skip 再重复 | 材料/公司 identity/meta/manifest/资产字节、业务时间、revision、版本零 diff；无 converter/republication 重试 |
| 换 bytes、仅换 primary、仅换 amended | 不误 skip；真实竞争变更沿 typed conflict，非竞争异 amended 按 G3 metadata-only；不另升版规则 |
| 缺 original/Docling/manifest、同长度 digest 损坏 | 完整性 owner fail closed，即使 meta fingerprint 相同也不得 skip；不返回成功承诺 |
| 公司字段/时间漂移、第三方 alias占用、alias+target同时变 | G3 guard/alias优先级；相同请求必要合法公司阶段无-op 与额外漂移区分，后者不准 skip |
| 真实 read/write I/O、锁获取/rollback释放故障 | 保留 operational failure，无无条件 retry/CLI fallback；业务 publication 与失败来源分开核 |
| COMMITTED后 publication释放、cleanup/writer释放故障 | durable完整目标可能已发布；异常不触发 skip/二次提交/caller rollback，保留最早主因与次因 |
| 取消前/准备中/最终checkpoint/commit后 | F6取消优先级、零材料发布或已提交事实保持；active-only job终态不覆写 |
| G3 tombstone首删/重删/恢复/再删、explicit create/missing update/delete | 重删仍 deleted；恢复保持旧首次时间，同指纹不增版；不把 tombstone当active竞争winner |
| O32不同identity/ticker、filing SEC/CN/HK | 共存、既有publication合同不漂移，各入口结果同源 |

真实 Fs/storage 仓储与 bounded barrier：A/B 在 admission/prepare 后均无 writer batch，B 完成 commit再放 A begin_batch；guard内 compare至close/swap间尝试第三 writer，应阻塞至A终态。不得让A持ticker writer等待B commit；finally释放并收集进程。
skip 检查做 **winner commit后→loser终态后** 的业务 hash/diff，另保存 pair before/after；共享最终 diff不归因单进程。缺件/坏hash用真实FS字节注入；I/O仅在实际owner操作注入OSError，不用只抛FileExistsError的fake证明同一性。
最终 aggregate campaign才跑真实双进程CLI：每轮fresh临时base、同一离线公开合成输入/hash、同exact最终G1/G2/G3 argv，stdin DEVNULL，同步启动；普通/debug分别保存每进程stdout/stderr/log/summary、PID、纳秒/单调启动结束、启动时差、exit/timeout和完整进程树。
按最终接口绑定 `upload_material --base <fresh-base> --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Concurrent Same' --company-name 'Apple Inc.' --files <probe.txt>`；多文件primary/amended按最终批准CLI补参数，不从当前pin猜未来参数。
真实多轮每轮应一success、一skipped、单完整文档，无残留进程；未越过共同old admission的轮次仅证明顺序幂等，保留原样不算竞争证明。确定性owner barrier测试承担竞态闭合，启动时差本身不证明业务重叠或成功率。
保存公司/source/meta/manifest/原件/派生 hash、两终态/事件/summary/durable查询；CLI direct无job记录须queried-but-absent，另真job/observation测试分开。原L06/E01证据不覆盖，本prep全部not-run。

## 7. 实施后代码/文档门槛（本轮 not-run）

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_filing_upload_publication.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

上述命令还必须加最终G3 material owner测试；绑定路径后才能作为完整执行清单。先确认主树 `.venv` Python3.11、dayu.__file__/CLI入口；不得新隔离树或借其它checkout结果。
pytest-cov生成JSON，逐一实际修改生产 `.py` ≥80%，类型检查覆盖完整dayu/tests/utils，无新增/扩散错误；若触及旧type错误须在允许owner边界一起解决，否则报root范围阻塞，不绕过检查。
已读pinned README职责：Fins README只写已实现稳定publication/状态契约；根README只写用户并发skip/冲突/排障事实；tests README只写当前测试层级/运行约定。实施后按真实diff触发并按职责更新，不机械同步，不在README放proposal。无分层/装配改变则不触发dayu总README。

## 8. classified residual、最终 source rebind 与停止

| 分类 / owner / destination | 处置 |
| --- | --- |
| fixed in current slice（拟，未修）/ G5 | 窄auto竞争相同性裁决、零业务skip及统一投影；真实验证后才能记已修 |
| covered by later approved slice / G1/G2/G3 | B1、稳定身份/primary指纹、合法公司无-op、完整target/双guard、amended/tombstone/active-only终态；正式final实施接口重绑后进入G5 |
| requiring explicit owner decision / storage，root | B2当前异常certainty合同缺口；若G5需要据异常断言发布状态即blocked，不能改成功承诺 |
| assigned to later work unit / download storage | `fins-download-indeterminate-publication-state`独立residual，既不自动前置也不顺带实施 |
| assigned to later work unit / Docling runtime | 转换质量、部署、OCR、XBRL，G5只消费outcome |

root实施前须在最终明确OID逐项绑定：①G1 request/admission、auto原始意图与identity；②G2 material primary/资产描述器/角色指纹/skip-safe真源及version；③G3同版state、完整性/可信meta/tombstone、公司独立decision/无-op与post-company/alias锁序；④material arbiter/execute实际路径、初始skip也经过同一完整性guard；⑤全部mutation与只读skip的capability终态；⑥amended持久/manifest/result唯一publishedoutcome；⑦F6取消/checkpoint和active-onlyjob；⑧storageCOMMITTED/journal/release/rollback真实异常合同；⑨最终精确白名单、测试路径/README职责、真实CLI参数与campaign采集点。
任一source rebind缺关键证据，把精确函数/数据反例和owner交root，保留conditional；不读其它在途报告补票，不按候选API编码。
本轮交付两准备报告、冻结证据和补源/依赖索引即停止；pytest/pyright/cov/真实CLI/转换/OCR/安装/review/commit/push/PR/merge均 **not-run**，无acceptedplan/实施/gatepass。
