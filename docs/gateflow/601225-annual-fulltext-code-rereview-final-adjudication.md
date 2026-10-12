# 601225-annual-fulltext：S1 r1复审最终总控裁决

- Gate：code review / fix r1 / re-review **pass**；next entry point：accepted slice commit → aggregate deepreview。work unit未完成、未PR/merge。
- 同版review artifacts：DS Flash [194843](../reviews/code-review-20261012-194843.md)，mimo-flash [210515](../reviews/code-review-20261012-210515.md)；两路完整正文已读，runner各实际exit0/completed。DS在原并行r1复审完成，原MiMo退出0无artifact/终态裁决而拒收；用户后续明确改mimo-flash，后者独立补齐本路，未读DS结果。原失败日志不删、不把旧机械passed冒充gatepass。
- 冻结：54文件manifest SHA814ce7ce3a1ffc0a4d9cae39b72c625f594760fbc4deedd2e26a73b6e4a439cf；原双路启动前54/54一致，补审前后53实现/证据文件一致，唯一state由总控追加真实进展。当前总控独立重算53/53一致。
- mimo-flash needs_review的2异常是误以manifest.files为list的探索失败；已更正dict.items后完整前后hash并交付artifact，非缺失验证；不作为pass依据。

## Finding最终状态

| Finding | 裁决 / 修复状态 | 同源证据 |
| --- | --- | --- |
| MiMo-01 selected repair身份漂移绕过gate | accepted / 已修复 | 请求owner唯一_SelectedRepairIntent从initial同一projection建立；fresh来源重绑定typed RevisionConflict在FILING_STARTED/batch/GET前abort；gate按source intent，失败关tail保reason，取消优先，成功fresh inventory→company→clear。两真实Fs重绑定反例与provider/conversion/cancel回归由DS、mimo-flash独立重跑。 |
| MiMo-02 fallback只查external | accepted / 已修复 | 身份owner必填allocated_internal_ids，source key过滤前显式投影非空str；CN FY seed/fallback双命名空间占用检查；原同key/缺身份/read_error/duplicate优先序与HK/H1/Q不变。12矩阵/类型/优先序双方通过，DS独立old/new13场景差分验证。 |

两路无新实质finding、无blocking open question；不多数表决，root已走读identity与workflow实际分支和修复反例。DS N1/OQ1继续deferred-with-owner，N2/N3 rejected-with-reason，OQ2未证defect；原裁决授权/非阻塞/owner/destination不变。DS与mimo-flash把部分risk写accepted/deferred-with-owner，这仅为finding语义，不能当Gateflow风险分类；总控以下统一为assigned to later work unit，不增加验收或新issue授权。

## 验证与文档

- Sol final受影响13文件集758 passed；pyright0 errors/0 warnings、pipcheck0。root独立核checks原退出、cov24文件全>=80(最低85.03%)；DS另完整758/pyright/cov验证；mimo-flash35聚焦反例实际exit0。
- 四原真实bare CLI与修后两真实repeat均exit0；clean35源、seeded37含旧2摘要；三全文官方原件SHA与FY2021/2023/2024、真实Docling正文一致。四repeat35 skipped/0conversion/完整源0PDF GET，全source metadata/revision/资产SHA及摘要原样保持。root已独立全记录比较、SDK读回、原证据hash核验；证据见s1-controller-validation与code-fix-r1。
- r1仅两guard不改正常facts/selection/acquisition/conversion路径；两真实顺序pure owner replay35pair相等，当前两repeat同版，不能称新版完整首次下载；历史启动树/raw及未保存FILING_STARTED不补造。
- docs：root/Fins/testsREADME按职责已更新，无其它层触发。53冻结文件无变化，代码/测试/原始证据无人覆盖；调用方目录/原日志未写。

## 风险归属

| 风险/未覆盖 | Gateflow分类 | owner / destination与非阻塞依据 |
| --- | --- | --- |
| 历史启动树/raw与FILING_STARTED本体未保存 | assigned to later work unit | 总控/取证维护者；按需独立历史追溯。用户明确不造历史raw，本次当前直接链路与官方原文已证。 |
| OCR/未知首页布局、其它公司公告、一般日期/财务处理、旧坏身份错年自动恢复 | assigned to later work unit | Fins discovery/facts/date/integrity维护者；有真实输入后另立任务。goal明确非目标，当前未知闭合拒绝，三目标已实际取得。 |
| 落选来源repeat GET成本(clean4/seeded2，各一次) | assigned to later work unit | Fins维护者；按需性能任务。无已持完整源GET、无转换/摘要覆盖，不新增缓存目标。 |
| SDK origin有损hash/未持久derived_from历史因果 | assigned to later work unit | Fins审计维护者；按需独立来源审计。当前完整PDF/JSON SHA、fingerprint、实际SDK转换/正文均已核验，不新增schema。 |
| open/read/close全故障注入；seeded-first辅助no-extra断言 | assigned to later work unit | Fins source/验收维护者；按需资源失败回归。context manager已走读，真实2→37全部source一致，当前无缺失验收。 |
| 外部PdfGate回调装配与后台/direct失败投影(DS N1/OQ1) | assigned to later work unit | Fins gate/runtime维护者；真实gate装配/独立投影统一。原裁决deferred-with-owner，goal排除调度/一般runtime；当前Noop与普通CLI真实诊断正确。 |
| 其它公司跨类别重复source输入(OQ2) | assigned to later work unit | Fins discovery/selection；真实反例后独立取证。当前35候选唯一且安全拒绝，不增加loose猜测。 |
| 不可达防御repair分支覆盖/docstring异常列举小项 | assigned to later work unit | CN workflow owner；状态机演化时按可达反例维护。len!=1/tripwire当前正常结构不能触发，修复可达failure/cancel/success全通过；无实质finding。 |
| fresh identity错误族与workflow→single-filing观察微窗口 | assigned to later work unit | identity/filing owner；后续并发契约任务。原行为未变，single filing自身fresh proof/仓储guard保持安全，本次source intent修复已完成。 |
| 未复跑r1新的完整首下载/首下载未冻结最终commit | assigned to later work unit | 总控/验证维护者；未来变更正常facts/selection/conversion路径再做新首下载。r1两guard在真实顺序pure owner35pair replay相等，两真repeat全记录不变，旧首下载与修改成功路径等价边界已明示。 |

两accepted修复：fixed in current slice，owner CN workflow/identity，destination code-fix-r1和两re-review。外部来源/真实转换本次已验证：fixed in current slice，owner实施/验收；未分类风险为0，未修复accepted为0，非阻塞问题不扩goal。

## 下一入口

自动accepted slice commit后以base7637bb0至S1 head完整branch执行mimo-flash/DS Flash并行aggregate deepreview；此artifact不替代下一gate、PRreview或final closeout。
