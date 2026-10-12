# 601225-annual-fulltext：S1 code review 总控裁决

- Gate：code review → fix r1；当前未通过，无accepted slice commit。
- 两runner实际退出0/completed；MiMo184158有高/中两finding，DS Flash184159未发现实质问题。两份完整artifact已读，按同源证据裁决，不多数表决。
- Target：accepted-plan HEAD7709c015的S1工作树，freeze50文件SHA f8e126a979ae024fac607197001b3f1aaafa4d2106a417b692e5ccf19bef21f6，tracked diff SHA f48c3cb9501b91d833d17583e63e04b7eee1908d28ee1dc0e501872d7eef0e82。审查期间50文件无变化。

## 必须修复

| Finding | 裁决/状态 | 同源原因与限定修法 |
| --- | --- | --- |
| MiMo-01 selected repair身份漂移绕过gate | accepted / 未修复 / 高 | 初始index+finalpreflight固化D_old，循环重新resolve得D_new，当前if document_id==repair_document_id使失败break、fresh inventory及company publish全跳过。CN年度新增来源绑定让该分支可达；必须保存明确selected source key与expected document ID的repair intent，从初始同一identity投影建立，不从偶然排序/日志猜。首次处理该source前fresh解析ID不同就typed RevisionConflict abort，零该candidate与tail/company写；gate按source intent收束，合法单filing失败仍关闸。成功仅fresh inventory clean+company publish后开tail。正常终态不得带未收口repair intent；不能借终态检查掩盖合法cancel或provider/conversion原失败原因。 |
| MiMo-02 fallback只查external未查internal | accepted / 未修复 / 中 | 独立pure-owner反例允许合法external不同、internal已占用，返回重复internal。身份owner必须显式收集在场可信internal IDs（frozenset[str]等严格不可变投影），CN FY新分配同时检查外部/内部占用；原seed任一已占用则用source hash fallback，fallback任一已占用拒绝，不覆写/随机后缀。同key旧pair先复用；missing_internal/duplicate/read_error原优先序保持。HK/H1/Q分配业务不变，新字段所有调用显式迁移，无默认shim/schema改动。 |

测试须证明初preflight后fresh identity重绑定（新target原本可成功/可失败两类）都在应用前typed失败，无tail/company写，旧源/并发写入者已发布态保留；稳定repair成功、失败、取消、普通clean和已确认prefix保持。ID测试含internal-only seed/fallback碰撞、external碰撞、metadata未知source key但可信internal占用、同key复用和原错误优先序，owner级零写入，不靠fake放宽生产。

## DS非阻塞注记与待定问题裁决

- N1：deferred-with-owner；取消回调两种填充均满足当前Noop与显式checkpoint控制，真实外部gate未装配，暂无同源失败。用户非目标包括Host/Engine/一般调度，本plan明确不增gate限流；非阻塞。owner Fins gate协议维护者，destination未来真实gate装配时的回调语义契约任务；assigned to later work unit。
- N2/N3：rejected-with-reason / 证据失效（非finding风格注记）；同形私有checkpoint与utils排版未证明行为/所有权错误，不为风格统一增加公共层或重开slice，不生成必须的后续任务。
- OQ1：deferred-with-owner；background job与direct公共失败投影差异是既有行为，当前普通CLI实际诊断完整，未修改runtime，非阻塞。授权依据goal排除调用方/财务处理与普通入口边界；owner Fins runtime失败投影维护者，destination按需独立统一失败投影任务；assigned to later work unit。
- OQ2：不是已证defect；唯一source绑定为已接受handoff contract，跨类别重合安全拒绝比猜财期有效。本次35候选唯一已实核，其它公司反例缺证；不扩H1/Q或加loose兼容。潜在跨分类输入风险assigned to later work unit，owner Fins discovery/selection，destination有真实输入后独立取证任务；当前非阻塞且不要求用户决策。

## 风险、验证与下一入口

- 两accepted finding：fixed in current slice，owner Sol及总控，destination code-fix-r1 + 双路re-review；未修复不能放行。
- MiMo列open/read/close注入覆盖与seeded-first no-extra校验缺口：assigned to later work unit，owners Fins source/验收维护者，destination按需资源失败回归/辅助验收任务；当前context manager路径静态正确，root与两reviewer独立核2→37及全部source records，无当前证据缺口。不能冒充覆盖全部故障。
- 历史启动树/raw、未知布局/其它公告/日期、历史坏身份自动恢复、落选GET成本、SDK历史因果限制沿已接受风险表owner/destination，assigned to later work unit。不造issue、不扩scope。
- 当前四真实CLI/三compare/SDK/hash/摘要保留/零完整源GET、731测试/类型/coverage已通过，fix不得覆盖原证据。两修法仅repair漂移与identity占用guard，不改变正常facts/selection/conversion路径；修后全受影响tests+pyright+逐文件coverage，并用真实P6已记录first顺序/元数据在pure identity owner重放allocation确认35 pair保持，另用当前代码在独立既有验证base各跑新bare repeat（新run-dir/log/verify/compare）验证合法缓存不变。不重复两次完整Docling转换；若实现改变正常取得/转换路径，需明确新影响再扩验证，不能把旧结果当新版覆盖。
- 无scope/owner/schema阻断，不需新goal confirmation。未merge/PR，next entry point fix r1。

## 最终状态回写（总控，r1双路复审后）

MiMo-01、MiMo-02均accepted / **已修复**；同源证据由DS194843与mimo-flash210515正式re-review验证，无未修复项。最终裁决、风险分类、真实验证与下一入口见[code-rereview-final-adjudication](../gateflow/601225-annual-fulltext-code-rereview-final-adjudication.md)。本节更新不覆盖原review历史。
