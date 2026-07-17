# WU-SEMANTIC-OWNERSHIP-01 / R10 HKEX cumulative discovery plan — adversarial plan review

## 1. Reviewed target and scope

- **Target**: `docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
- **Lock**: 605 lines；SHA-256 `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699`
- **Baseline HEAD**: `1c2585275f4134d8456a3fda2d84464e4e52c9d7`；staged tree empty
- **Scope**: R10 内部 remediation sub-WU 独立实施计划；不是新 WU、issue 或 feature
- **Reviewer**: AgentMiMo

## 2. Assumptions tested

| # | Assumption | Evidence source | Verdict |
|---|---|---|---|
| A1 | HKEX title search 使用官方 cumulative `rowRange` continuation | Controller discussion Topic 6.6 官方验证证据；`docs/fins/design.md` §8 | confirmed |
| A2 | 官方 `hasNextRow` 为 JSON bool，三个 count/range 字段为 JSON int，`result` 为字符串化 JSON array | Controller discussion Topic 6.6 live 验证；plan §5.2 | confirmed |
| A3 | 官方响应 `rowRange` 回显请求值 | Controller discussion live check with `rowRange=5/10/20/1200` | confirmed |
| A4 | 当前代码只发一次固定 `rowRange=100` 请求，用八个 generic total aliases 猜完整性 | `hkexnews_downloader.py:392-419, 634-663, 692-728` | confirmed |
| A5 | `CnReportDiscoveryClientProtocol.list_report_candidates` 当前无 `cancel_checker` 参数 | `cn_download_protocols.py:83-106` | confirmed |
| A6 | Workflow 当前在 `list_report_candidates` 调用前后检查取消，但不在 downloader 内部每轮检查 | `cn_download_workflow.py:227-234` | confirmed |
| A7 | Test doubles 在 `test_cn_pipeline.py:58,144` 和 `test_cn_download_runtime.py:109` 实现 protocol 但无 `cancel_checker` 参数 | 直接代码检查 | confirmed |
| A8 | Umbrella plan §17 将 R10 归为单 slice、HKEX cumulative discovery、依赖 R06→R07→R08→R09 | `wu-semantic-ownership-01-overdesign-remediation-plan.md` §5-6 | confirmed |
| A9 | Controller validation PASS，明确标出六个双路 review 必须重点挑战的高风险点 | `wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-controller-validation.md` §6 | confirmed |

## 3. Findings

**零 finding。** 以下是对 Controller validation §6 六个重点挑战点的逐项 adversarial 验证，每个都基于直接代码/设计真源证据证明 plan 设计自洽。

### 3.1 cancel_checker seam 验证（重点挑战 #1）

**攻击路径**: 尝试证明 seam 不 production-reachable、不最小、或无意改变 CNInfo。

**证据与结论**:

1. **Production reachability**: 当前 `cn_download_workflow.py:233` 已将 `cancel_checker` 作为 workflow 级参数持有。Plan 要求 workflow 把同一 checker 原样传入 `discovery.list_report_candidates(query, profile, cancel_checker=cancel_checker)`。调用链完整：`run_cn_download_stream_impl` → `discovery.list_report_candidates` → HKEX downloader 每轮消费。不需要 `ContextVar`、mutable setter、factory 或 market-specific branch。

2. **最小性**: 共享 protocol 只增加一个 `keyword-only` 参数 `cancel_checker: Callable[[], bool] | None = None`。CNInfo downloader 为满足同一 structural contract 在其既有单轮 discovery I/O 前后消费信号。CNInfo 不获得 HKEX cumulative 状态机，不改变 query/pagination/selection/error 语义。Plan §4.1、§4.2、§6.3 已明确约束。

3. **CNInfo 无意外漂移**: `cninfo_downloader.py:229-233` 当前 `list_report_candidates` 只做单次 POST。添加 `cancel_checker` 后，CNInfo 实现在 POST 前后各调一次 checker。这不改变 CNInfo query 参数、分页、筛选或错误语义（plan §4.2 明确禁止）。Workflow 当前的 `_raise_if_cancelled` 调用（line 227, 234）保持不变，与 downloader 内部检查构成双层安全网，是冗余而非冲突。

4. **Test double 迁移**: `test_cn_pipeline.py:58,144` 和 `test_cn_download_runtime.py:109` 的三个 discovery test double 需要添加 `cancel_checker: Callable[[], bool] | None = None` 参数以满足 structural typing。Plan §4.2 和 §8 已将这些文件列入 test allowlist，plan §8 最后一段明确要求"migrated explicit cancel parameter and assert propagation"。

**结论**: seam production-reachable、最小、不改变 CNInfo。无 finding。

### 3.2 requested range 增长与 strict loaded/rows 进展验证（重点挑战 #2）

**攻击路径**: 尝试证明 no-progress 检测会拒绝合法 terminal snapshot，或允许无限 doubling。

**证据与结论**:

1. **No-progress 检测位置**: Plan §6.2 伪代码在 `hasNextRow=true` 分支内检查 `loadedRecord > previous_continuation_loaded`。当 `hasNextRow=false` 时，先检查 `loadedRecord == recordCnt == len(rows)` 然后直接返回，不检查跨轮 progress。

2. **合法 terminal 不被拒绝**: 场景：round 1 `loadedRecord=100, recordCnt=150, hasNextRow=true`；round 2 `loadedRecord=100, recordCnt=100, hasNextRow=false`。Provider 数据变化导致 recordCnt 缩小，但最新 snapshot 内部一致。Plan §6.2 正确接受此场景——"terminal complete 优先于跨轮 progress 比较"、"不要求历史 rows/count 单调"。

3. **无限 doubling 被阻止**: 场景：round 1 `loadedRecord=100, hasNextRow=true`；round 2 扩大 range 后仍 `loadedRecord=100, hasNextRow=true`。此时 `previous_continuation_loaded=100`，`loadedRecord=100`，`100 > 100` 为 false → typed fail。Plan §8 "no progress" 测试用例明确覆盖此场景。

4. **Requested range 增长不算 progress**: Plan §4 裁决"requested range 增长不得单独算 provider progress"。§6.2 伪代码只检查 `loadedRecord > previous_continuation_loaded`，不检查 `current_range > previous_range`。正确。

**结论**: no-progress 检测正确、有限失败、不拒绝合法 terminal。无 finding。

### 3.3 exact bool/int/stringified-list 与 response range equality 验证（重点挑战 #3）

**攻击路径**: 尝试证明 parser 类型检查与官方证据不一致、存在 alias/coercion、或引入第二 completeness owner。

**证据与结论**:

1. **Bool 严格性**: Plan §5.2 item 2 要求 `hasNextRow` 只接受 JSON bool；`"true"`、`0/1`、null 全拒绝。Controller discussion Topic 6.6 live 验证确认 `hasNextRow` 为 JSON bool。Python `bool` 是 `int` 子类，plan 要求先显式拒绝 bool 再检查 int。正确。

2. **Int 严格性**: Plan §5.2 item 3 要求三个 count/range 字段只接受 JSON int 且非负，先拒绝 bool。Live 验证确认为 JSON int。字符串数字、integral float、non-integral float 全拒绝。无 coercion。

3. **Stringified-list**: Plan §5.2 item 4 要求 `result` 只接受字符串化 JSON array。`_extract_json_rows` 的通用 fallback 被显式禁止。新 strict parser 只走 `json.loads(result_string)` 路径。

4. **Response range equality**: Plan §5.2 item 5 要求 `response_row_range == requested_row_range`。Live 验证确认响应回显请求值。此断言确保 provider 执行了当前累计请求，不是第二 completeness owner。

5. **无 alias/coercion**: Plan §3.3 non-goals 明确禁止 "generic total aliases、per-row TOTAL_COUNT、字符串/float count coercion、loose parsing、fallback"。§5.3 要求删除 `_coerce_non_negative_int` 和八个 generic total aliases。

**结论**: parser 严格类型与官方证据一致，无 alias/coercion/第二 owner。无 finding。

### 3.4 typed provider error 跨 list/workflow 保留 type/cause 验证（重点挑战 #4）

**攻击路径**: 尝试证明 typed error 被 generic RuntimeError 抹平。

**证据与结论**:

1. **当前代码行为**: `hkexnews_downloader.py:294-299` 当前 `list_report_candidates` 对 `HkexnewsDiscoveryTruncatedError` 做 `raise`（保留 type/cause），对其他 `RuntimeError` 做 `raise RuntimeError("披露易公告分类查询失败...") from exc`（包装）。

2. **Plan 要求**: §5.3 要求 `HkexnewsProviderProtocolError` "保持 type/cause，不得被通用 RuntimeError 抹平"。实现时需要在现有 `except HkexnewsDiscoveryTruncatedError: raise` 之后、`except RuntimeError as exc` 之前添加 `except HkexnewsProviderProtocolError: raise`。

3. **Precedence 明确**: Plan §5.3 区分三类错误：provider protocol failure（typed）、cancel（`CnDownloadCancelledError`）、HTTP/JSON transport failure（RuntimeError + retry）。§8 有 "checker failure" 和 "HTTP initial/later failure" 测试用例覆盖。

4. **Workflow 传播**: Plan §5.3 要求 `list_report_candidates` 让 typed error 保持 type/cause。当前代码已有 `except HkexnewsDiscoveryTruncatedError: raise` 模式，新的 `HkexnewsProviderProtocolError` 用同样模式处理。Workflow 层 `_raise_if_cancelled` 在 discovery 调用前后检查取消，不捕获 provider error。

**结论**: typed error 传播路径清晰，实现 agent 有足够指引。但需注意实现时 exception handler 顺序——这是一个实现细节，plan 描述已充分。无 finding。

### 3.5 final-only parse/HEAD、query invariance、count growth、language isolation、live smoke 验证（重点挑战 #5）

**攻击路径**: 尝试证明这些行为无法由测试或 evidence manifest 实际证明。

**证据与结论**:

1. **Final-only parse/HEAD**: Plan §6.2 要求 "只有 complete 后才把 final rows 交给 `_parse_announcement(...)`、stock match 与 selection"。§8 "overlapping/replacement" 和 "final no duplicate" 测试用例覆盖。实现：每轮 `latest_rows = snapshot.rows`（替换），complete 后才 parse。

2. **Query invariance**: Plan §6.1 要求构造 immutable base params，每轮只派生新 dict 写入 `rowRange`。§8 "query invariance" 测试用例要求去除 `rowRange` 后 dict exact equality。

3. **Count growth**: Plan §6.2 要求 "recordCnt 不缓存为第一次总数。每轮用最新值计算 next range"。§8 "multi-round count growth" 测试用例覆盖 `100/150/true → 200/350/true → 400 complete` 场景。

4. **Language isolation**: Plan §6.2 要求 "每个 language/category 独立完整续取"。§8 "per-language isolation" 测试用例覆盖。当前代码 `hkexnews_downloader.py:391` 已按 `self._languages` 循环，每个 language 独立构造请求。Plan 保持此结构。

5. **Live smoke**: Plan §9.3 要求 opt-in、非默认、只读 smoke。§12 说明外部 endpoint 不可达时记录环境限制，local deterministic gates 仍必须通过。§9.2 要求 captured fixture + 程序化 fixtures 必须覆盖，live smoke 不替代。

**结论**: 所有行为都有明确测试矩阵和/或 evidence manifest 覆盖。无 finding。

### 3.6 exact allowlist、单 slice、coverage、安全/deferred/no-touch 完整性验证（重点挑战 #6）

**攻击路径**: 尝试证明 allowlist 不完整、slice 过粗、coverage 不可执行、或安全/deferred 边界缺失。

**证据与结论**:

1. **Exact allowlist 完整性**: Plan §4.2 列出4个 production 文件、6个 test/fixture 文件、2个 README。与实现需求一一对应：
   - HKEX downloader: 唯一业务 owner
   - `cn_download_protocols.py`: protocol 签名
   - `cn_download_workflow.py`: 透传 cancel_checker
   - `cninfo_downloader.py`: 同一 protocol 签名
   - 6个 test 文件: owner tests、seam tests、propagation tests
   - fixture: captured official shape
   - 2个 README: developer docs

2. **单 slice 合理性**: Plan §1 和 §7 论证：协议解析、累计状态机、取消、owner tests、direct workflow propagation、README 同步和完整验证共享同一 owner、failure blast radius 与验收矩阵。拆分会产生不能独立接受的中间态。R10 改动范围有限（4个 production 文件），单 slice 不过粗。

3. **逐文件 coverage**: Plan §10.3 要求四个 modified production file 各自 branch coverage `>=80%`，使用 `coverage report --include=<file> --fail-under=80`。命令已具体到文件路径。可执行。

4. **安全保留**: Plan §11.2 明确保留 HTTP timeout、retry 上限、throttle、公开 HTTPS endpoint、PDF magic/size 校验、stock matching、error 不含 raw body/secret/local path。不新增 permission schema/auth profile。

5. **Deferred/no-touch**: Plan §3.3 non-goals 和 §10.6 明确禁止 Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9。§10.6 要求对最终 diff 做 deferred scope audit。

6. **不过度设计**: Plan §603-605 自评"没有过度设计"。验证：HKEX 累计协议只留在 provider-private model/state machine；共享改动只是为现有取消信号增加直接参数运输；没有新增通用分页抽象、配置、durable state、schema、第二 completeness owner。正确。

**结论**: allowlist 完整、单 slice 合理、coverage 可执行、安全/deferred 边界完整、不过度设计。无 finding。

## 4. Open questions

无。所有关键设计决策已由 Controller discussion Topic 6.6 裁决、`docs/fins/design.md` §8 写入、Controller validation PASS 确认。

## 5. Residual risks

| Risk | Classification | Owner |
|---|---|---|
| 外部 HKEX endpoint DNS/网络/challenge/限流不可用 | 环境限制；local deterministic gates 不受影响 | implementation agent 记录环境限制 |
| Provider 可能未来引入 rowRange hard cap | evidence-driven residual；当前无证据 | 未来独立 HKEX provider WU |
| `cancel_checker` 传递 seam 增加 protocol 签名 surface | 最小必要；符合项目朴素接口原则 | R10 owner |
| 实现时需注意 `HkexnewsProviderProtocolError` 在 `list_report_candidates` 的 exception handler 顺序 | 实现细节；plan §5.3 描述充分 | implementation agent |

## 6. Final plan review conclusion

**PASS**

Plan 是 code-generation-ready 的。所有六个 Controller-flagged 高风险点均经 adversarial 验证确认自洽：

1. cancel_checker seam production-reachable、最小、不改变 CNInfo。
2. no-progress 检测正确阻止无限 doubling，不拒绝合法 terminal snapshot。
3. strict parser 类型与官方证据一致，无 alias/coercion/第二 owner。
4. typed provider error 传播路径清晰，exception handler 顺序有明确指引。
5. final-only parse/HEAD、query invariance、count growth、language isolation、live smoke 均有可执行的测试矩阵和/或 evidence manifest。
6. exact allowlist 完整、单 slice 合理、逐文件 coverage 可执行、安全/deferred 边界完整、不过度设计。

Plan 满足 `docs/fins/design.md` §8、Controller discussion Topic 6.6 final adjudication、AGENTS.md 语义所有权/编码/测试约束，以及 umbrella plan §7.3 的 sub-WU plan 要求。可以交给 implementation agent。
