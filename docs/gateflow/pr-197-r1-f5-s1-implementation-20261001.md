RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-d7f04474

# PR197-R1 / F5-S1 实施前范围阻塞报告

- task label：`pr197-f5-s1-implement-sol-20261001-02`。
- gate：implementation preflight **BLOCKED**；没有产品实现，没有 code gate pass。
- workspace：唯一主树；branch=`codex/upload-material-oracle`。
- HEAD=`3a836a463aab3eeffb050facd592e614801d6ca9`，local main=`fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- accepted checkpoint、binding、完整202行计划和root裁决已读取；候选header作为历史原件保留。
- plan SHA256=`e4b578807345593f0af6698189044963931b12ba5d13a76da94e553e581644d8`。
- freeze=`workspace/tmp/pr197-f5-s1-implement-sol-20261001-01/freeze.json`，SHA256=`14836630a693728d599799e703c70c16d9edd968690c950313535af1826ed600`。
- 初始工作树干净。61项current与61项originals初检、复现后终检全部同字节。未网络读取PR；PR OPEN/draft/同OID信息来自本轮root输入，不作为本轮独立远端核验声明。
- 本轮canary通过工具读取当前指定文件，并再次以Python读取原文本核对，无换行、无改写。

## F5-S1-B01：真实 rebuild caller / 结果 owner 遗漏写范围

状态：**已直接证实，未修；必须交root修正执行范围**。这不是新增业务裁决，也不是另一个行为slice。

语义owner与直接证据：

1. `dayu/fins/pipelines/cn_download_rebuild.py:41` 的 `rebuild_cn_download_artifacts` 是HK/CN本地rebuild operation结果的实际产生者。
2. 该文件83行直接调用并解包 `rebuild_hk_periods`，118–137行产生并返回完整operation字典；426行 `_build_rebuild_summary` 产生summary。现有返回通道只有 `filings, cancelled`，未知B若从filings移除，必须在这个真实caller接收并运输独立未知集合。
3. `dayu/fins/pipelines/cn_download_workflow.py:159` 调用此owner并发出其result；`cn_pipeline.py:1480` 的 `_project_cn_pipeline_summary` 消费operation结果。
4. accepted plan §5明确要求rebuild正常result必填 `uncertain_reports`，CN真实生产空数组，summary新增从tuple派生的 `uncertain_count`；§6要求未知不进入旧failed filing，§7/8要求严格schema及真实mandatory caller迁移。
5. `cn_download_rebuild.py` **不在freeze.allowed_write中**，也不在freeze.files/originals中；本轮没有修改它。当前文件SHA256=`e55c8ed4ae7035716046606241f3ff48a2e0b9984610f933826cd7b3d1683d1c`，终检确认与HEAD同字节。

离线真实Fs复现：CN和HK分别用独立空工作区执行生产 `rebuild_cn_download_artifacts`，均得到status=`ok`、filings=`[]`，result缺 `uncertain_reports`，summary缺 `uncertain_count`。复现不替换owner、不mock返回值、不访问provider、不调用网络、PDF/OCR或Docling转换，也不读用户资产；仅在专属tmp产生仓储锁文件。

只改允许文件无法完整满足合同：在adapter或workflow补空字段会把未知事实丢掉，属于下游补偿；旁路实际rebuild owner或把未知塞回filings违反N02、唯一owner与严格分层合同。不采用这些绕过。需要root将真实文件 `dayu/fins/pipelines/cn_download_rebuild.py` 纳入明确写范围并核收冻结身份后，原F5-S1才可继续。未改计划字节、未扩大API或业务语义。

本轮遵从用户明确停止条件：“若真实产品caller漏allowed……先报告具体blocked，不自行扩大语义/改裁决”。在确认这一阻塞后没有先做机械部分实现。

## 实际变更与保全

本轮产品/测试/README修改：**无**。

本轮新增交付：本报告；专属 `workspace/tmp/pr197-f5-s1-implement-sol-20261001-01/` 中：

- `reproduce_scope_blocker.py`：完整离线复现脚本，中文模块/函数说明及参数、返回、异常说明，严格typed。
- `blocker-repro.stdout`、`.stderr`、`.exitcode`。
- `identity-final.stdout`、`.stderr`、`.exitcode`。
- `blocker-repro-pyright.stdout`、`.stderr`、`.exitcode`。
- `report-final.stdout`、`.stderr`、`.exitcode`。
- `repro-empty-workspace/` 下4个真实Fs锁文件；没有源文档、PDF、processed或伪造Raw。

复现后观察到以下并发dirty文件，均不由本轮写入、没有reset或删除：

- `docs/gateflow/pr-197-review-repair-adjudication-20260930.md`
- `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`
- `docs/upload_material_repair_handoff_prompt_3.md`

交付时另观察到root新增 `docs/gateflow/pr-197-r1-f5-s1-dispatch-scope-correction-20261001.md`。已只读核对：root将相同遗漏登记为 `F5-S1-SETUP-A1`，accepted，明确“白名单更正待新派发”，旧freeze保全，等待旧作者终态后使用新unique label/freeze继续。本轮freeze SHA仍不变，故本轮按既定停止条件终止，不将root更正文档误读成旧派发可自行扩写授权。该新文件不由本轮写入。

三controller归root。本轮不写controller、旧plan、旧报告、官方冻结Raw、依赖、config、main；未派发Agent、未commit/push/PR/merge/markready或对外comment。

## 实际validation

每项独立stdout/stderr/exitcode均在上述专属tmp；shell保存原exit后以同exit退出，没有掩盖复合命令失败。

| 检查 | 真实exit | 结果与边界 |
| --- | --- | --- |
| 激活`.venv`后离线复现 | 0 | CN/HK真实空Fs均证实缺失必填未知字段；0表示阻塞复现成功，不表示F5产品测试通过 |
| 激活`.venv`后identity-final | 0 | freeze/plan/202行/HEAD/branch/local main/61current+61originals/canary/遗漏owner等于HEAD逐件核验 |
| 激活`.venv`后仅复现脚本pyright | 0 | `0 errors, 0 warnings, 0 informations`；仅诊断脚本，不代替full产品pyright |
| report-final交付自检 | 0 | 核对报告必需metadata、停止状态及无行尾空格，并保存报告SHA256 |

脚本pyright的stderr只有已有工具的新版本提示（1.1.409→1.1.414），没有类型诊断；未安装或修改依赖。

额外工具失败如实保留：一次只读 `git rev-parse main refs/remotes/origin/main` 返回128，因为当前树没有 `refs/remotes/origin/main`；随后单独 `git rev-parse main` 和终检均返回0、正确匹配base。不联网恢复远端ref，不以组合输出中的main OID掩盖128。

受影响pytest组合、full `python -m pyright dayu/ tests/ utils/`、逐修改生产py覆盖：**未执行 / N/A**，因为产品实施前已命中明确停止条件，没有修改生产py；没有以脚本pyright或复现成功冒充这些验收。

## 最短复现

在本任务唯一工作树中执行：

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f5-s1-implement-sol-20261001-01/reproduce_scope_blocker.py
```

stdout逐市场打印真实result与summary字段，以及freeze SHA、caller行号、owner SHA和allowed membership；脚本断言所有关键证据，任何不符原样非零退出。实际执行的独立日志和exit文件可复核。

## README decision与未完成回归

已读根README和Fins README各自更新约束及tests README当前运行/维护边界。未实施用户行为、契约或新增测试层，故三者本轮均不改；不存在层关系变化，dayu README不机械更新。范围解除后的完整实现仍必须按职责更新根用户未知列表/退出/重试、Fins同窗与公共契约、tests真实回归/运行方式。

全部accepted §3–9仍待实施。完整可验证回归继续以冻结计划§9为验收真源：同源366日历/可信英文/远年N01/同ID原ValueError；真实Fs同窗/rename barrier/staging-published/异常原对象及锁释放；A+B与纯未知/真空/未知零下载和身份；N02逐字保全与A提交、写失败和取消；旧processed日期rebuild清None及normal→rebuild→overwrite两writer；public/durable双10上限、4096与独立omission、direct/job/CLI/wait；fresh空与typed取消/失败投影；F6/F7/CN/SEC；冻结官方Raw正例及明确合成未知。受影响pytest一次组合、fullpyright与逐改生产py≥80%均不能由本轮阻塞复现替代。

## classified residual / completion

- 阻断范围项：F5-S1-B01；destination=root核收遗漏产品owner写范围，随后继续同一个完整F5-S1，不重裁业务。
- 产品F5/N01/N02：未实施、未验证、未闭环；A4与取消/durable义务全部保留。
- 已裁信息边界：52/53周、过渡财年、窗口外未取得来源继续按原计划，不扩解析或历史爬窗。
- 其他upload WU与#198：保全；没有顺带处理。
- completion：本轮完成阻塞取证与交付后停止；**F5-S1未完成，不宣称代码gatepass，不提交同版代码双审**。本报告交root用于恢复正确范围；后续仍进入既有draft PR197，由用户merge。
