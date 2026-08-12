# UF-FIX09 shared interruptible Docling converter — Plan Gate

## 1. Gate 元数据

- **work unit**：`UF-FIX09 shared-interruptible-docling-converter`
- **gate**：plan
- **plan 状态**：`plan-review-fix-complete / implementation-not-started`
- **目标分支**：`codex/upload-filing-oracle`
- **target baseline / 当前 HEAD**：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- **goal confirmation**：已由用户确认；输入为
  `docs/gateflow/uf-fix09-shared-interruptible-docling-converter-goal-confirmation-20260812.md`
- **artifact path**：
  `docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-20260812.md`
- **本 gate 允许变更**：仅本 plan artifact。
- **本 gate 禁止变更**：生产代码、测试、README、accepted oracle/scenario registry、commit、push、PR。
- **plan review 输入**：
  `docs/reviews/plan-review-20260812154406.md`、
  `docs/reviews/plan-review-20260812-154453.md` 与
  `docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-review-adjudication-20260812.md`。
- **后继入口**：两路独立 plan re-review；本 artifact 不授权直接实现。

## 2. 动机、直接证据与问题定性

### 2.1 动机成立，且严重性评估正确

问题不是 CLI 显示瑕疵，而是两个 owner 级缺陷叠加：

1. `DoclingUploadService._build_pending_assets` 在 producer 线程内同步执行
   `convert_pdf_bytes_with_docling`，取消只能在转换前后观察，不能在运行中的 Docling
   converter 上生效。
2. `FinsIngestionRuntime._produce_direct_upload` 在 runner 返回后先投影
   `upload.completed`，再检查 cancellation；`_upload_completed_progress_type` 又把
   `cancelled` 摘要归入 completed 分支。

冻结实测报告
`/Users/leo/workspace/.dayu-cli-ci/upload-filing-calibration-20260811-tF6OnN/observed-behavior.md`
提供同源证据：

- UF-L01 转换前取消：`0.035909s`、exit 130、无发布，行为正确。
- UF-L02 HK PDF 转换中取消：`31.780388s` 后才退出，stdout 已出现
  `upload.completed`，随后才投影 cancelled/130；无 source publication。
- UF-L03 同输入重试成功，证明冻结输入与仓储本身可用。
- UF-L04 US DOCX 转换中取消：`21.564391s` 后才退出，同样先 completed 后
  cancelled；无 source publication。
- UF-L05 同输入重试成功。

这与 `docs/cli_ci_oracles.json` 的
`upload_filing.sigint-cancellation`、`download.cancellation-crash-and-recovery`
以及 `docs/cli_ci_scenarios.json` 的 UF-FIX09、UF-PF09 一致：产品必须在转换运行中
中断整个受控进程树、等待 canonical cancelled terminal、返回 130，且不得留下半发布
source 或先显示 completed。

### 2.2 不采用的路径

- 不在 CLI/UI 过滤 `upload.completed`：该层不是上传终态语义 owner，也无法修复 durable
  job event/observation 的错误顺序。
- 不给同步 converter 增加更多前后 cancellation checkpoint：不能中断正在执行的
  Docling 调用。
- 不复制 download runner 给 upload：会形成两套 poll、signal、cleanup、错误映射和
  后续漂移。
- 不把 Docling contract 下沉到 `dayu.runtime`：runtime 不得拥有 Fins/Docling 业务语义。
- 不用 callback/factory/profile、`hasattr/getattr`、loose parsing、默认值、兼容 shim
  或下游重算绕过 typed owner。

## 3. 冻结 scope 与非目标

### 3.1 In scope

1. 建立唯一的 Fins shared interruptible Docling converter owner。
2. 让 CN/HK download、SEC upload filing/material、CN/HK upload filing/material 使用同一
   converter contract 和同一进程状态机。
3. 修正 direct 与 durable ingestion upload 的 terminal arbitration，使 cancelled summary
   不产生 completed，并落实 source publication commit 的 first-committer 规则。
4. 补齐 deterministic、真实 Docling、focused-real UF-PF09 验证以及必要 README 更新。

### 3.2 冻结非目标（原样继承 goal artifact）

不处理 UF-O09、UF-O10、格式/help 漂移、XBRL companion、multi-file
primary/collision、renamed update、delete 后 auto、existing source auto repair、计数、
company meta refresh、并发、其它 upload_filing 修复、Host cancel 状态机、Engine
event/schema、ToolAwaiting、schema migration、旧接口兼容或 137 条 full-real matrix。
review 命中这些内容时只能归为 `assigned to later work unit`。

此外：不修改 `docs/cli_ci_oracles.json` 或 `docs/cli_ci_scenarios.json` 中已 accepted/frozen
内容，不执行其余 137 条 full-real，不 push、不创建 PR。

## 4. 唯一 owner 与依赖方向

### 4.1 Owner 决策

| 语义 | 唯一 owner | 职责边界 |
| --- | --- | --- |
| 进程 spawn、POSIX session/process group、异步 wait、terminate/kill、join/reap、queue close | `dayu.runtime.interruptible_process` | 层中立 primitive；不认识 Docling、文件格式、Fins error 或 publication |
| Fins Docling 输入、配置、child construction invocation、JSON bytes、IPC descriptor、closed error/cancel mapping、poll/grace/temp policy | 新模块 `dayu.fins.pipelines.docling_process_converter` | 唯一 shared converter owner；替代并删除 CN 专属 runner |
| Docling 库的低层 converter/options/`DocumentStream` 机械构造 | `dayu.documents.docling_runtime` | 继续作为可复用 library helper；Fins child target 是 Fins 场景唯一调用/配置 owner，不加入取消或发布语义 |
| filing/material 的业务元数据、资产组合、storage batch 与 publication commit | 各 Fins workflow + `DoclingUploadService` + storage batch owner | converter 返回只代表 bytes 已生成，不代表 source 已发布 |
| direct/durable upload 的 terminal summary 仲裁和 progress/result 投影 | `FinsIngestionRuntime` | cancelled summary 不产生 completed；accepted committed result 不被迟到 cancel 回滚 |
| SIGINT 转成 operation cancellation token、等待 canonical terminal、exit 130 | CLI 现有 direct stream owner | 只消费 runtime terminal，不修补业务状态 |

### 4.2 依赖方向

```text
CLI -> FinsIngestionRuntime -> Fins service/pipelines/workflows
                             -> shared Fins Docling converter
                                  -> dayu.documents.docling_runtime
                                  -> dayu.runtime.interruptible_process
                             -> dayu.fins.storage
```

- `dayu.runtime` 只依赖标准库/底层公共契约，不 import Fins、documents、Host、Engine、
  Service 或 UI。
- Fins converter 可以依赖 `dayu.runtime` 与 `dayu.documents`；二者不得反向依赖 Fins。
- Host/Engine 不参与 direct upload lifecycle，也不新增 durable Run/Event/Trace/Memory
  投影。冻结 UF-L01–L05 中这些对象均不存在，架构文档也将 direct Fins lifecycle
  归给 Fins runtime/CLI。

## 5. 生产 Docling call-site inventory 与迁移裁决

| 生产路径/构造点 | 当前证据 | 裁决 |
| --- | --- | --- |
| `dayu/documents/docling_runtime.py` 的 `build_docling_pdf_converter`、`DocumentConverter(...)`、`convert_pdf_bytes_with_docling` | 仓库中唯一直接 `DocumentConverter` 构造；无 Fins storage/cancel | **不迁移**；保留低层 helper，由 shared Fins child target 调用 |
| `dayu/fins/pipelines/cn_docling_process.py` 的 `ProcessCnDoclingConversionRunner` | 已用 `InterruptibleProcessHandle`，但名称、协议、配置、错误均绑定 CN download | 最终由 `docling_process_converter.py` **替代**；S1 先独立新增 shared owner，S2 同步迁移 caller 并删除旧文件，不留 re-export/wrapper |
| `cn_download_filing_workflow.py` | `convert_pdf_to_docling_json` 在 source batch 前 await | **迁移**到 shared converter typed contract；CN 与 HK 共用同一路径 |
| `CnPipeline.__init__`、`build_cn_download_adapter`、`build_hk_download_adapter` | 构造 CN 专属 runner；upload service 又走同步 converter | **迁移**为同一个 `DoclingConverter` 注入 download 和 upload service |
| `SecPipeline.__init__`、`sec_upload_workflow.py` filing/material | `DoclingUploadService.prepare_upload` 同步转换 | **迁移**；两个 async stream await shared converter |
| `CnPipeline` upload filing/material | 同一个 upload service 同步转换 | **迁移**；CN/HK upload 均 await shared converter |
| `DefaultFinsRuntime` / `ProductionFinsUploadRunner` composition | CN/HK download adapters、SEC/CN upload pipelines 分别构造，未共享 converter | **迁移构造**；创建一个无跨调用可变状态的 `ProcessDoclingConverter` 实例并显式传入所有 Fins 路径 |
| `dayu/tools/web/web_fetch_orchestrator.py::_docling_convert_to_markdown` | 直接调用 documents helper，输出 markdown；tools/web 不能依赖 Fins，且无 Fins publication | **不迁移**；若未来需要 web fetch 中断，归 later work unit，不能反向依赖本 owner |
| Fins `process` / `read` | 消费已发布的 `*_docling.json`，没有 converter construction/invocation | **不迁移**；只做回归，确保 shared converter JSON contract 不破坏读取 |

`rg` 证据表明，除 documents 内部构造外，生产 conversion invocation 仅上述三类：旧 CN
runner、upload service、web fetch；没有隐藏的第四套 Fins converter。

## 6. Shared Fins converter 的直接 typed contract

### 6.1 类型与签名

在 `dayu.fins.pipelines.docling_process_converter` 定义：

```python
@dataclass(frozen=True, slots=True)
class DoclingConversionConfig:
    do_ocr: bool
    do_table_structure: bool
    table_mode: Literal["accurate"]
    do_cell_matching: bool

@dataclass(frozen=True, slots=True)
class DoclingConversionResult:
    json_bytes: bytes
    size: int
    sha256: str

class DoclingConverter(Protocol):
    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult: ...
```

约束：

- `bytes` 是不可变输入/输出；不接收 path、开放 Mapping、request bag 或 `extra payload`。
- `stream_name` 是 Docling 业务可读输入名，必须非空且只传给 `DocumentStream`/诊断，不从
  后缀反推业务 owner。
- config 是 frozen、字段闭合的直接参数；模块只提供一个
  `DEFAULT_FINS_DOCLING_CONVERSION_CONFIG`，值保持现状：OCR、table structure、accurate、
  cell matching 均开启。当前 Fins caller 没有 `fast` 使用事实，因此本 WU 不承诺或测试
  `fast`；`table_mode` 只接受字面量 `"accurate"`，禁止 profile 字符串或 loose dict。
- `cancellation` 是必传 keyword；`None` 明确表示调用方没有取消源，不是隐式 fallback。
  有取消源时直接使用层中立公共契约
  `dayu.contracts.cancellation.CancellationToken`；不得定义 `DoclingCancellationInput`、
  callback alias、lambda/adapter、第二取消 flag 或 converter-only wrapper。
- `DoclingConversionResult` 构造时校验 `size == len(json_bytes)`、SHA-256 为对应 64 位
  lowercase hex；消费者使用 `json_bytes`，不重算第二份业务结果。
- `ProcessDoclingConverter` 不保存 operation process/temp/IPC/cancellation 状态；**每次**
  `convert_to_json_bytes` 都创建自己的 `InterruptibleProcessHandle`、temp tree、输入/输出文件和
  IPC queue，且只由该调用关闭/删除。shared concrete instance 因而没有 operation mutable
  state；这只证明同一实例可安全注入多个既有 caller，不把同请求并发或新调度器扩入本 WU。

### 6.2 同步 producer 线程与 async handle 的组合

当前 ingestion producer 是同步线程；现有 `ProductionFinsUploadRunner.run_upload` 调用
`CnPipeline.upload_filing/upload_material` 或 `SecPipeline.upload_filing/upload_material` 的同步
facade，而这些 facade 已在 producer 线程内用既有 `_run_async_upload_sync` / `asyncio.run`
消费对应 async stream，建立该线程唯一私有 event loop。实现应：

1. 将 `DoclingUploadService.prepare_upload`、`_build_pending_assets` 改为 async。
2. CN/SEC filing/material async upload workflow 直接 `await prepare_upload(...)`。
3. 现有 sync pipeline facade 继续且仅继续在 producer 线程内执行一次
   `asyncio.run(async stream collector)`；service、workflow、converter 均不得创建 loop 或调用
   `asyncio.run`，因此没有 nested loop。
4. CN/HK download workflow 已是 async，直接 await 同一 converter。
5. shared converter 在该私有 loop 上 await `InterruptibleProcessHandle.wait()`；CLI 主 loop
   继续接收 SIGINT。`FinsIngestionRuntime` 创建的同一个 concrete composite token 依次经过
   execution context -> `ProductionFinsUploadRunner` / download adapter -> pipeline async workflow
   -> `DoclingUploadService` -> `DoclingConverter`，每层原样传 identity，不投影 callback。

`FinsJobCancellationChecker` 保留是因为其它既有 download checkpoint 仍调用 `__call__`，但它应
扩展 canonical `CancellationToken`；`_RuntimeJobCancellationChecker` 与
`_DirectCancellationChecker` 都实现 `is_cancelled/cancel_reason/requested_at`，其 `__call__`
只委托 `is_cancelled`。converter、upload service 与新签名只声明 `CancellationToken | None`。

- direct 路径：`_DirectStreamCancellationState.threading.Lock` 是跨 CLI 主线程、producer 线程和
  producer 私有 loop 的唯一可见性 owner。同一 locked state 保存首次取消的 bool、reason、
  requested-at 和 terminal claim；外部 CLI token 被首次观察时，把其
  `cancel_reason()/requested_at()`（为空则使用固定 direct reason/当前 UTC）写入该 state；
  consumer abort 也在同一锁内写固定 reason/UTC。三个 token 观察方法都从这份 locked snapshot
  返回，不增加第二 flag。
- durable 路径：`_RuntimeJobCancellationChecker` 从 job store 的同一 record snapshot 判断
  `cancellation_requested/CANCELLING/CANCELLED`；首次观察到取消时，以固定
  `job_cancel_requested` 为 reason，并以该首次 persisted cancelling record 的 `updated_at` 解析
  requested-at。该 operation-scoped snapshot 只补齐 canonical token 观察面，不新增 job schema。

测试必须断言从 ingestion 到 converter 的对象 identity 相同、direct 跨线程读写可见、reason/time
稳定且与上述真源一致；不得用 callback fake 固化旧接口。

所有新增/修改的 module、class、function/method 都按根 `AGENTS.md` 提供完整中文 docstring
（参数、返回值、异常）；签名禁止 `Any`、`object`、无类型参数/返回值。复杂 cleanup/race 只在
owner 内加解释意图的中文注释，不把状态机复制到消费者。

## 7. Child、IPC 与 closed outcome mapping

### 7.1 Child construction 与 JSON 输出

shared owner 的 top-level、可 pickle child target 接收输入临时文件、输出临时文件、
`stream_name` 和 frozen config：

1. child 由 `InterruptibleProcessHandle` 的 wrapper 启动；runtime wrapper 在 POSIX 调用
   `setsid()`，建立独立 session/process group。
2. child 读取 immutable input bytes，在 child 内按 config 调用
   `dayu.documents.docling_runtime.convert_pdf_bytes_with_docling`；因此真正的 Docling
   converter construction/fallback/execution 绝不发生在父 producer 线程。
3. top-level target 自己闭合三段失败边界，而不是让已知业务失败逃到 runtime wrapper：
   - helper 抛 `DoclingRuntimeInitializationError` -> 写
     `CONVERTER_CONSTRUCTION` failure descriptor；
   - helper 的其它 conversion/fallback 异常 -> 写 `CONVERTER_EXECUTION` descriptor；
   - `export_to_dict`、closed mapping 校验、`json.dumps`、UTF-8 encode 或 output write 失败 ->
     写 `RESULT_SERIALIZATION` descriptor。
   三类都返回 exact failure descriptor 并**正常 return**，使 runtime 返回
   `InterruptibleProcessCompleted`；message 由 failure kind 对应的固定 bounded 安全文本产生，
   不包含 exception string、traceback 或 path。
4. child 对 export mapping 使用唯一序列化规则：
   `json.dumps(..., ensure_ascii=False, indent=2).encode("utf-8")`。
5. JSON bytes 写到 output temp file；process queue 只传小型 closed descriptor，不传大
   payload。

### 7.2 IPC descriptor

descriptor 是 exact-key、versioned JSON value，而不是开放 payload：

- common：`schema_version`（固定整数常量）、`status`（`success`/`failure`）。
- success：精确增加 `size: int`、`sha256: str`。
- failure：精确增加 `failure_kind`（仅 child 可产生的 closed enum）和 bounded、稳定、
  不含内部 traceback/path 的 `message`。

父进程按 status 做 exact-key/type/value 校验；未知版本、未知 key、漏 key、bool 冒充 int、
digest 格式错误、output 缺失、size/digest 不符均归 `IPC_PROTOCOL`，绝不 loose parse 或从
message 推断。只有父进程确实取得且完整校验通过的 descriptor 才可信：

- child 正常退出并返回 exact failure descriptor：按 descriptor 的 closed kind 映射；
- child 正常退出但 descriptor 丢失、不可解码或结构非法：`IPC_PROTOCOL`；
- runtime 返回 `InterruptibleProcessFailed`、child 非零/异常退出或 signal crash，且没有可信
  descriptor：`CHILD_CRASH`；
- descriptor 本身因 queue/pickle/transport 故障无法到达时，只按父进程可观察到的上述
  `IPC_PROTOCOL`（clean exit）或 `CHILD_CRASH`（abnormal/signal exit）事实闭合，禁止猜原始
  child exception。

### 7.3 Closed error/cancel 类型

定义 `DoclingConversionFailureKind` closed enum：

- `CONVERTER_CONSTRUCTION`
- `CONVERTER_EXECUTION`
- `RESULT_SERIALIZATION`
- `IPC_PROTOCOL`
- `CHILD_CRASH`
- `CLEANUP`

定义：

- `DoclingConversionError(kind, safe_message, exit_code: int | None)`：所有非取消失败的
  唯一 public exception；字段 typed、message bounded。
- `DoclingConversionCancelledError`：只有已完成进程与资源收口的请求取消才抛出。

映射必须闭合：

| 事实 | public mapping |
| --- | --- |
| child 内 helper construction/initialization 失败，target 正常返回 | `CONVERTER_CONSTRUCTION` descriptor -> `DoclingConversionError` |
| child 内 Docling convert/fallback 执行失败，target 正常返回 | `CONVERTER_EXECUTION` descriptor -> error |
| child 内 export/mapping/JSON encode/output write 失败，target 正常返回 | `RESULT_SERIALIZATION` descriptor -> error |
| descriptor/output 文件/schema/size/digest 不一致 | `IPC_PROTOCOL` |
| runtime `InterruptibleProcessFailed`、无可信 descriptor 的异常退出或 signal crash | `CHILD_CRASH`，只保留 exit code，不把 runtime `error_type/message` 变成 public 稳定语义，也不解析字符串 |
| request cancel 且 terminate/kill/close/temp cleanup 全部成功 | `DoclingConversionCancelledError` |
| cancel 或正常路径的 join/queue close/temp cleanup 未完成 | `CLEANUP`；不能伪装为成功或已安全取消，原始异常作为 cause/note 保留 |

contract 边界的空 bytes、空 stream name、非法 config 直接 `ValueError`；它们不是 child
运行失败，也不进入 IPC。

## 8. 唯一进程/清理状态机

### 8.1 常量 owner

Docling-specific 常量只存在于 `docling_process_converter.py`：

- poll interval：保留现有 `0.05s`。
- terminate grace：保留 `2.0s`。
- kill grace：保留 `1.0s`。
- temp prefix/input/output file name、descriptor version、JSON serialization policy。

`dayu.runtime.interruptible_process` 继续唯一拥有通用 process signal/join/queue cleanup
实现，不复制这些 primitive。其他 workflow/service 不得声明第二套 grace/poll 常量。

### 8.2 状态机

```text
VALIDATE
  -> PRE_CANCELLED (无 temp/handle，抛 Cancelled)
  -> TEMP_READY
  -> CHILD_STARTED
  -> POLLING
       -> CHILD_TERMINAL -> HANDLE_CLOSE -> DESCRIPTOR_VALIDATE
                                      -> OUTPUT_VALIDATE -> RETURN
       -> CANCEL_OBSERVED -> TERMINATE_GROUP
              -> terminal -> HANDLE_CLOSE -> TEMP_CLEAN -> CANCELLED
              -> grace expiry -> KILL_GROUP
                    -> terminal -> HANDLE_CLOSE -> TEMP_CLEAN -> CANCELLED
                    -> still alive/cleanup failure -> CLEANUP_ERROR
       -> wait/runtime failure -> HANDLE_CLOSE -> typed error
finally -> TEMP_CLEAN
```

不变量：

- POSIX child 先进入新 session；terminate/kill 使用 runtime 的安全 process-group 信号，
  覆盖 Docling 后代；非 POSIX 保留 runtime 的 direct-process 能力，不伪称 group guarantee。
- 每个已 start 的 handle 最终且仅由同一调用 `close()`；close 负责 join/reap、process close、
  IPC queue close/join-thread。
- close 在读取/信任 output 前完成，防止仍运行 child 修改文件。
- temp directory 仅由 converter owner 建立并在所有出口清理；very-early cancel 不创建 temp。
- 每次调用的 handle、temp tree、input/output path 与 IPC queue 都是该 invocation 的局部 owner；
  shared `ProcessDoclingConverter` instance 不缓存、复用或跨调用关闭它们。
- outer task cancellation 不能绕过 close；沿用 runtime shielded cleanup 语义，完成收口后再传播。
- terminate/kill、close、temp cleanup 的次生错误不得吞掉，且不得把未知存活状态映射成
  cancelled。
- shared owner 为真实运行诊断记录结构化 cleanup phase（不是测试开关或 public schema）：至少
  `child_started`、`cancel_observed`、`terminate_started/completed`、`kill_started/completed` 或
  `kill_not_needed`、`handle_close_started/completed`、`temp_cleanup_completed`、
  `cancelled_terminal_ready`，每条带 monotonic elapsed、PID/PGID 可用值和 outcome，不带输入 path/
  traceback。正常 production 也保留同一诊断，测试不得增加 marker/event/sleep 来触发它。

## 9. Publication first-committer boundary

### 9.1 唯一规则

conversion return 只证明 JSON bytes 可用，不是 publication commit。每个 document batch 由
workflow caller 用一个局部 closed state（不得复用 cancellation flag）执行如下
first-committer 状态机：

```text
CALLER_OWNED_OPEN
  -> PRECOMMIT_CANCELLED -> ROLLBACK_ONCE -> CANCELLED_SUMMARY
  -> PRECOMMIT_FAILURE   -> ROLLBACK_ONCE -> RAISE_FAILURE
  -> FINAL_CHECKPOINT_NOT_CANCELLED -> COMMIT_OWNERSHIP_TRANSFERRED
       -> commit_batch returns -> COMMITTED -> COMPLETED_SUMMARY
       -> commit_batch raises  -> COMMIT_OUTCOME_UNKNOWN -> RAISE_STORAGE_FAILURE
```

1. `docling_upload_service.py` 提供一个有真实状态机语义的 module-level
   `commit_prepared_upload_batch` helper，作为 SEC/CN upload 共享的 publication lifecycle owner；
   workflow caller 显式传入 service、batching repository、caller-owned batch、prepared mutation
   与 canonical token。`publish_prepared_upload` 本身只对 batch 写入，不 commit、不 rollback；
   helper 对逐文件/最后 checkpoint 的 cancel 或 precommit failure **恰好调用一次**
   `rollback_batch`，service/workflow 不重复 rollback。该 helper 不是透传 facade。
2. workflow 在所有 conversion、asset write、source/meta/manifest staging 完成后，紧邻 commit
   ownership transfer 执行最后一次 `CancellationToken.is_cancelled()`。命中则保持
   `CALLER_OWNED_OPEN`，caller rollback once 并返回 cancelled；不投影 completed。
3. checkpoint 未命中后，workflow 原子地把局部 publication state 转为
   `COMMIT_OWNERSHIP_TRANSFERRED`，随后立刻调用 `commit_batch`。该 transition 是 commit 开始的
   语义边界；最后一次 `is_cancelled()` 返回的瞬间就是 cancel-vs-commit linearization point，
   barrier 只允许放在其前或 transition 后，不留下第三种解释。从此 token 已交给 storage owner，
   caller 不再读取 cancel，也绝不 rollback。
4. `commit_batch` 正常返回是 source publication first committer。workflow 必须转为 `COMMITTED`
   并构造 completed summary；commit 后、summary 构造前或返回前的取消都是 late cancel，不能
   删除、回滚或重解释结果。
5. `commit_batch` 抛错时 caller 无法从时间、cancel flag 或 exception string 证明 publication
   结果，进入 `COMMIT_OUTCOME_UNKNOWN`：不 rollback、不返回 cancelled/success，原样进入 typed
   storage failure 路径，并保留 repository recovery evidence。该内部 unknown 不新增 public
   schema/status。
6. delete、skipped/no-op 也必须由 workflow 在返回 summary 前确定其业务 terminal disposition；
   只有真正持有 batch 的路径执行上述 rollback/commit transition。

现有 `_commit_cn_filing_assets_batch` 与 SEC/CN upload workflow 的 caller-owned batch 已接近此
边界；实现只统一 final checkpoint、ownership transfer 与结果传播，不创建跨 company/document
的大事务。

### 9.2 Company meta 明确不扩 scope

SEC/CN upload filing/material 当前先用独立 batch 提交 company meta，再转换和提交 source。
因此 source conversion 被取消时 company meta 可能已经存在。该事实与本 work unit 的 source
publication 原子性不冲突；合并/回滚 company-meta 会改变已有业务事务边界，属于冻结的
`company meta refresh`/later work unit。本计划不得顺手修改。

## 10. FinsIngestionRuntime owner 级终态修正

### 10.1 统一 typed disposition

在 `ingestion_runtime.py` 的 upload summary owner 附近定义 closed
`FinsUploadTerminalDisposition`（`COMPLETED`、`FAILED`、`CANCELLED`），并由
module-level `_upload_terminal_disposition_from_status(status: str) ->
FinsUploadTerminalDisposition` 作为唯一 status validation/mapping 真源；
`FinsUploadPipelineResult.from_pipeline_json` 与 `FinsUploadResultSummary.__post_init__` 都只调用该
helper，`terminal_disposition()` 直接返回其结果，不复制 mapping。它只接受 production pipeline
当前合法的 exact lowercase status。禁止
`strip().lower()`、兼容 alias、未知值默认 completed 或 UI 过滤。closed mapping 为：

| exact summary status | typed terminal disposition | 含义 |
| --- | --- | --- |
| `ok` | `COMPLETED` | source publication 已 commit |
| `skipped` | `COMPLETED` | 已确定的无写入成功 no-op |
| `deleted` | `COMPLETED` | delete publication 已 commit |
| `failed` | `FAILED` | workflow 已接受失败 |
| `cancelled` | `CANCELLED` | cancellation 在 publication first-commit 前胜出 |

upload service 内部的 `uploaded` 只能在 SEC/CN workflow owner 处 exact 映射为 summary `ok`，
不得泄漏为 runtime summary；现有测试 fake 直接构造 `status="uploaded"` 是偶然行为，应迁移到
`ok`，不能倒逼生产兼容。任何其它值（包括大小写/空白变体）在上述 owner boundary 抛
`ValueError`。本 WU 不为该映射引入额外 public schema。

### 10.2 Direct stream

`_produce_direct_upload` 在 runner 返回后先读取 typed disposition：

- `CANCELLED`：不发任何 upload completed progress，直接以 cancelled summary claim 唯一
  terminal 并投影 cancelled RESULT/exit 130。
- `FAILED`：runner 返回的失败 summary 是 workflow 已接受的 terminal；原子 claim 后才投影
  失败 progress 和 FAILURE result。
- `COMPLETED`：summary 已代表 workflow 的 publication/no-op 结果；原子 claim accepted
  terminal 后再投影 completed progress 与 SUCCESS result。

扩展 `_DirectStreamCancellationState` 为显式的 `claim_upload_summary(disposition)`，而不是在
`_emit_direct_result` 中再次无条件调用 cancellation checker。runner 返回 summary 前已经完成第
9 节仲裁：`CANCELLED` 表示 cancel first-commit，`FAILED/COMPLETED` 表示 workflow terminal 已
first-commit。因此这个 claim 在同一 lock 内只拒绝已有 terminal/consumer-abort，**不得**再用
随后写入的 cancellation flag 改写非-cancelled disposition。claim 成功后才从同一返回值依次
投影 progress 和 RESULT；cancelled 不投影 completed，failed 只投影
completed-with-failures，completed 只投影 completed，禁止 progress/result 分裂。CLI/UI 不过滤。

direct barrier tests 必须覆盖：(a) runner 内 final checkpoint 前 cancel；(b) commit 成功后、
summary 构造前 cancel；(c) completed summary 返回后、`claim_upload_summary` 前 cancel；(d) claim
后 cancel。只有 (a) 为 cancelled；(b)-(d) 均保持 completed。另覆盖 cancelled/failed summary
在 claim 前后的单终态投影。

### 10.3 Durable job

`_run_upload_job` 也先按 typed disposition 终结：

- cancelled summary 调用 `save_cancelled_if_active`。
- failed/completed summary 使用 upload 专用 job-store atomic save，在 file lock 内只尊重“已有
  terminal 不覆盖”，按已经由 workflow 接受的 summary 分别保存 failed/succeeded；**不**读取或
  依据 runner 返回后的 `cancellation_requested/CANCELLING` 重解释。workflow 在返回前观察到的
  durable cancellation 必须产出 cancelled summary。
- 该协议方法定名为 `save_accepted_upload_terminal_if_active`，直接接收
  `FinsUploadTerminalDisposition`、result/failure summary 与 finished-at，只允许
  `COMPLETED/FAILED`；传 `CANCELLED` 或字段不匹配时 `ValueError`。既有 download/preprocess 的
  `save_succeeded_or_cancelled` / `save_failed_or_cancelled_if_active` 语义不改，禁止为了 upload
  late-cancel 修复改写其它 operation。
- atomic save 返回后，progress 与 terminal event 只从最终保存 record/disposition 投影；先保存
  terminal，再追加恰当的 completed/completed-with-failures progress，cancelled 不追加 completed。
  移除“runner 返回 -> 先 completed -> 再读 job record”的旧顺序。

durable barrier tests 与 direct 使用同一四个时点，并额外断言 save 前/后 cancel 均不能覆盖
已接受的 completed/failed summary、已有 terminal 不覆盖、cancelled summary 只保存 cancelled。
direct result 与 durable record/event 必须从同一 typed disposition contract 派生。

不得修改 Host/Engine cancel 状态机，也不得在 CLI renderer 删除 event。

## 11. 数据流、类型和调用路径迁移

### 11.1 Download CN/HK

```text
FinsIngestionRuntime
 -> CN/HK adapter
 -> CnPipeline async download stream
 -> cn_download_filing_workflow
 -> await DoclingConverter.convert_to_json_bytes(pdf_bytes, stream_name,
                                                  config=DEFAULT_...,
                                                  cancellation=same canonical token)
 -> DoclingConversionResult.json_bytes
 -> final cancel checkpoint
 -> one source batch(original PDF + docling JSON + meta/manifest)
 -> commit -> typed download summary
```

- 删除 `CnDoclingConversionRunner` 与 `convert_pdf_to_docling_json` 命名；协议统一为
  `DoclingConverter`。
- `CnDownloadCancelledError` 只保留下载 workflow 自身 cancellation 语义；shared converter 的
  `DoclingConversionCancelledError` 在 workflow owner 边界一次映射，不比较 message、不丢
  exception cause。
- conversion error 使用 closed kind 投影现有业务安全失败；不从 child string 反推分类。
- adapter request 中现有 `FinsJobCancellationChecker` concrete object 同时实现
  `CancellationToken`；download workflow 的普通 checkpoint 可继续调用其 `__call__`，传给 shared
  converter 时原样作为 canonical token，不创建 adapter。

### 11.2 Upload filing/material（SEC 与 CN/HK）

```text
FinsIngestionRuntime producer thread
 -> ProductionFinsUploadRunner
 -> sync pipeline facade / private async loop
 -> SEC or CN async filing/material workflow
 -> company-meta batch（现状，非本 WU）
 -> await DoclingUploadService.prepare_upload(cancellation=same canonical token)
      -> await shared DoclingConverter for each required convertible file
      -> PreparedUploadMutation（仅内存 bytes）
 -> document storage batch
 -> publish_prepared_upload + final cancel checkpoint
 -> commit
 -> UploadOperationResult/FinsUploadResultSummary
 -> ingestion typed terminal arbitration
```

- `ProductionFinsUploadRunner.run_upload` 接收 runtime composite token，并把同一 object identity
  原样传给 SEC/CN sync facade；facade 传入 async stream，workflow 传给 service，service 再传
  converter。各层参数使用 `CancellationToken`（无取消源的 standalone caller 才允许 `None`）。
- `DoclingUploadService` 构造参数改为显式 `docling_converter: DoclingConverter`；删除
  `DoclingUploadConverter`、`convert_with_docling`、`_convert_bytes_with_docling`、
  `_convert_with_docling` 以及 `UploadCancellationChecker` callback alias。publication checkpoint
  直接调用 canonical token 的 `is_cancelled()`；不得保留旧 private helper、monkeypatch seam、
  wrapper 或 re-export。
- 测试使用实现 `DoclingConverter` 的 typed fake class，不 monkeypatch 私有字段。
- `_build_pending_assets` 直接消费 `DoclingConversionResult.json_bytes`，不再取得 dict、重复
  `json.dumps` 或形成第二份 serialization owner。
- filing/material 复用同一 prepare/publish contract；不各自重算 JSON、digest 或 cancel status。
- `SecPipeline`、`CnPipeline` 均接收 typed converter 并传给 upload service；CN pipeline 同一
  instance 也传给 download workflow。
- `DefaultFinsRuntime.get_ingestion_runtime()` 在构造任何 CN/HK download adapter、CN upload
  pipeline 或 SEC upload pipeline **之前**只执行一次
  `docling_converter = ProcessDoclingConverter()`，然后按同一 identity 顺序注入：
  `build_cn_download_adapter(..., docling_converter=...)`、
  `build_hk_download_adapter(..., docling_converter=...)`、
  `SecPipeline(..., docling_converter=...)`、
  `CnPipeline(..., docling_converter=...)`。CN download、HK download 与 CN/HK upload 保留三个
  独立 `CnPipeline` instance，以保留 source/downloader defaults 与 adapter identity；三者及
  SEC upload 都持有同一个 converter identity。`SecPipeline.__init__` 新增 typed 参数，
  `CnPipeline.__init__` 用该参数替换旧 runner 参数，两个 adapter builder 显式透传。
- standalone `CnPipeline`/`SecPipeline` 若参数为 `None`，只允许各自默认构造同一个 concrete
  class `ProcessDoclingConverter`；这不是第二实现。禁止 factory、registry、旧 runner fallback。

### 11.3 process/read 与 web fetch

- process/read 只消费已提交 JSON，保持原路径；加入 JSON bytes 可读回归，不引入 converter。
- web fetch 保持 `tools -> documents` 依赖和 markdown contract；不能依赖 Fins shared owner。

## 12. Implementation slices

以下 slice 按顺序执行，每个 slice 只允许由 **AgentCodex** 在后续获得 implementation gate
授权后实施。任何超出 allowed files 或命中冻结非目标的发现必须停止并回到 review，不得自行
扩 scope。

### Slice UF-FIX09-S1 — 新 shared converter 以独立可验证增量落地

- **objective**：新增格式中立的 typed shared converter 与 owner-level tests；旧 CN runner 和
  既有 caller 本 slice 暂不改，避免删除 protocol 后留下 broken import。S2 完成后才达到全仓
  唯一 owner。
- **prerequisites**：baseline 未漂移；S1 开始前确认 goal artifact 和本 plan 仍为 accepted
  输入。
- **allowed files/modules**：
  - 新增 `dayu/fins/pipelines/docling_process_converter.py`
  - 新增 `tests/fins/test_docling_process_converter.py`
- **exact allowed changes**：
  1. 定义第 6、7、8 节的 config、result、converter protocol、closed
     enum/exceptions、child target、descriptor 和 concrete converter。
  2. 直接接收公共 `CancellationToken | None`；每次调用独立 handle/temp/IPC。
  3. 复用现有 `InterruptibleProcessHandle` 和 documents helper；本 slice 不修改二者；按第 8.2
     节在 shared owner 记录通用 cleanup phase diagnostics，不增加测试开关。
  4. 旧 `cn_docling_process.py`、旧 protocol/test 和所有 caller 保持原样；不得为二者建立
     adapter、alias、re-export 或 wrapper。
- **functions/classes/types/call paths**：`ProcessDoclingConverter.convert_to_json_bytes` ->
  top-level child target -> documents helper；`DoclingConversionResult` 是唯一成功输出。
- **state transitions/error handling/invariants**：严格实现第 7、8 节；handle close 先于 output
  validation；very-early cancel 无 temp；POSIX nested descendant 经 process group 清理。
- **non-goals**：不接 pipeline、storage、ingestion terminal；不改 documents helper；不加
  Windows job-object 设计；不在本 slice 声称旧 owner 已删除。
- **deterministic tests/assertions**：
  - immutable input/name/config 正确到 child；PDF/DOCX 名称不触发特例。
  - 成功 bytes、size、digest 一致，descriptor exact schema。
  - child construction/execution/serialization 各自在 target 内返回 failure descriptor 且 runtime
    observed completion；malformed/missing descriptor、digest mismatch、clean-exit IPC loss、
    abnormal/signal crash 分别映射第 7 节 closed kind。
  - early cancel、terminate success、ignore terminate 后 kill、nested POSIX process group、close
    before output、temp cleanup、cleanup failure/outer cancellation identity。
- **commands**：
  ```bash
  source .venv/bin/activate
  pytest -q tests/fins/test_docling_process_converter.py tests/fins/test_cn_docling_process.py tests/runtime/test_interruptible_process.py tests/documents/test_docling_runtime.py
  pyright dayu tests utils
  ```
- **completion condition**：新 module 可独立 import，new/legacy focused tests 与 full pyright 通过；
  既有 caller 仍可 import/run，且没有新增 compatibility seam。
- **stop condition**：runtime primitive 无法表达安全 close/process-group，或 documents helper
  无法在 spawned child pickle/import；记录 blocker，禁止复制 runner。

### Slice UF-FIX09-S2 — 迁移全部 Fins download/upload call sites 与 publication 边界

- **objective**：让 CN/HK download、SEC/CN/HK filing/material upload 全部 await 同一 converter，
  并保持 source batch first-committer 不变量。
- **prerequisites**：S1 完成且 contract tests 通过。
- **allowed files/modules**：
  - 删除 `dayu/fins/pipelines/cn_docling_process.py`
  - `dayu/fins/pipelines/docling_upload_service.py`
  - `dayu/fins/pipelines/cn_download_protocols.py`
  - `dayu/fins/pipelines/cn_download_filing_workflow.py`
  - `dayu/fins/pipelines/cn_pipeline.py`
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `dayu/fins/pipelines/sec_upload_workflow.py`
  - `dayu/fins/service_runtime.py`
  - `dayu/fins/ingestion_runtime.py`（本 slice 仅 cancellation input 方法/type wiring，不改终态）
  - 删除 `tests/fins/test_cn_docling_process.py`
  - `tests/fins/test_docling_upload_service.py`
  - `tests/fins/test_docling_upload_service_integration.py`
  - `tests/fins/test_cn_download_workflow.py`
  - `tests/fins/test_cn_download_runtime.py`
  - `tests/fins/test_cn_pipeline.py`
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py`
  - `tests/fins/test_sec_pipeline_upload_material_stream.py`
  - `tests/fins/test_fins_ingestion_runtime.py`（仅 composite token、identity 与装配断言）
  - `tests/fins/test_processor_read_consistency.py`
- **exact allowed changes**：
  1. `prepare_upload`/`_build_pending_assets` async 化并注入 typed converter；删除
     `DoclingUploadConverter`、`convert_with_docling`、`_convert_bytes_with_docling`、
     `_convert_with_docling` 与 `UploadCancellationChecker`。
  2. SEC/CN filing/material stream await prepare；CN/HK download await shared converter。
  3. `FinsJobCancellationChecker` 扩展 canonical token；direct/durable concrete composite checker
     实现同一 contract，并按第 6.2 节原样逐层传递 object identity。
  4. 按第 11.2 节顺序，在 `DefaultFinsRuntime` 创建一次 concrete instance 并注入 CN download、
     HK download、CN/HK upload 与 SEC upload；standalone 只默认构造同一 concrete class。
  5. 删除旧 CN runner module/protocol/name/test；最终 import/symbol 零，不保留兼容转发。
  6. service 只写 caller-owned batch；SEC/CN workflow 共同调用第 9.1 节
     `commit_prepared_upload_batch`，由该唯一 helper 执行 final checkpoint、rollback once、commit
     ownership transfer、commit-success 与 commit-exception state machine。
  7. converter cancel 在 workflow 边界映射业务 cancelled；所有 converter error 按 closed kind
     进入既有安全失败投影。
- **functions/classes/types/call paths/data flow**：严格按第 11 节；移除
  `_convert_with_docling` 私有 monkeypatch seam；typed fake 通过 constructor 注入。
- **state transitions/error handling/invariants**：prepare 只构建内存资产；publish 只写 caller
  batch；precommit cancel/failure 由 caller rollback exactly once；ownership transfer 后 caller
  不再 rollback/read cancel；commit return 固定 completed，commit exception 固定 storage failure/
  unknown；company-meta batch 原样保留。
- **non-goals**：不改 web fetch、process/read 实现；不合并 company-meta/document transaction；
  不改格式 allowlist、多文件/repair/count/concurrency。
- **deterministic tests/assertions**：
  - CN/HK download success/error/cancel before conversion/cancel during converter/cancel after return
    before final checkpoint/commit winner；original+Docling+meta/manifest 单 batch。
  - SEC/CN filing/material 都经过 injected shared fake；转换中 cancel 不进入 publish；已有文档
    overwrite cancel 保持旧版本；precommit cancel/exception rollback exactly once；commit
    exception 不 rollback且返回失败；commit return 后不再读 cancel。
  - canonical token identity 从 ingestion 逐层到 converter 不变，direct reason/time 跨线程稳定，
    durable reason/time 来自首次 persisted cancelling record；没有第二 flag/adapter。
  - DefaultFinsRuntime 的 CN download、HK download、CN/HK upload、SEC upload 观察到同一 converter
    identity；三个独立 CnPipeline identity 保留；没有第二 concrete runner construction。
  - process/read 能读取 shared converter 产生的 UTF-8 JSON fixture；web fetch import graph 不变。
- **commands**：
  ```bash
  source .venv/bin/activate
  pytest -q \
    tests/fins/test_docling_upload_service.py \
    tests/fins/test_cn_download_workflow.py \
    tests/fins/test_cn_download_runtime.py \
    tests/fins/test_cn_pipeline.py \
    tests/fins/test_sec_pipeline_upload_filing_stream.py \
    tests/fins/test_sec_pipeline_upload_material_stream.py \
    tests/fins/test_fins_ingestion_runtime.py \
    tests/fins/test_processor_read_consistency.py \
    tests/fins/test_docling_upload_service_integration.py
  pyright dayu tests utils
  ```
- **completion condition**：第 5 节所有 migrate call site 均使用同一 contract；生产代码对旧
  module/symbol、同步 upload converter callback 的 `rg` 结果为零；focused tests/pyright 通过。
- **stop condition**：任一 call site 需要反向依赖、第二 runner 或下游 fallback 才能接入；
  停止并重新裁决 owner。

### Slice UF-FIX09-S3 — 终态仲裁、CLI/真实验证与文档收口

- **objective**：修复 ingestion terminal owner，证明 SIGINT 中断真实 Docling 且 UI/durable
  投影、source publication、重试一致。
- **prerequisites**：S1、S2 完成；deterministic pipeline tests 通过。
- **allowed files/modules**：
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/cli/test_fins_commands.py`
  - `dayu/fins/README.md`
  - 根 `README.md`
  - `tests/README.md`
  - 新的 workspace-external UF-PF09 calibration evidence directory（只写 stdout/stderr、process/
    stack/time-line、workspace snapshot、queried-absent 与 retry evidence，不修改 registry）
- **exact allowed changes**：
  1. 建立第 10 节 typed terminal disposition 与 direct/durable single-claim 流程。
  2. cancelled summary 不发 completed；committed summary claim 后 late cancel 不覆盖。
  3. 建立 `ok/skipped/deleted/failed/cancelled` exact status validation/mapping owner；迁移旧
     `uploaded` test fake，未知/大小写/空白值 strict `ValueError`。
  4. CLI production code不改；测试只证明首次 SIGINT request token、等待 canonical terminal、
     exit 130，无 renderer filter。
  5. 更新 README 中现有 owner/cancellation/test coverage 说明；不扩写其他职责。
- **functions/classes/types/call paths/data flow/state transitions**：
  `FinsUploadResultSummary.terminal_disposition` -> `_produce_direct_upload`/
  `_run_upload_job` -> atomic terminal owner -> progress/result/job event；同一次仲裁决定可见输出。
- **error handling/invariants**：cancelled 无 completed；failure 不伪装 cancel；source commit accepted 后
  late cancel 不回滚；job/direct 终态都只能一次；CLI 不拥有修正语义。
- **non-goals**：不改 Host/Engine、oracle/scenario registry、其它 CLI output 规则，不运行 137
  full-real。
- **deterministic tests/assertions**：
  - runner 返回 cancelled summary：direct event 序列只有 preparing/started/cancelled RESULT，
    无 `upload.completed`/`upload.completed_with_failures`；exit 130。
  - durable job 同样无 completed event，终态 cancelled。
  - direct/durable barrier 使用 accepted runner summary 覆盖 summary claim/save 前与 claim/save 后；
    completed/failed 不被 late cancel 改写，cancelled 只产生 cancelled。final precommit、ownership
    transfer、commit return/exception 的 storage barrier 由 S2 的 workflow/service tests 负责。
  - CLI 首次 SIGINT 仅请求一次、等待 producer join/canonical terminal；二次 SIGINT 不制造第二终态。
- **commands**：见第 13 节完整 validation matrix。
- **completion condition**：deterministic、real Docling、UF-PF09 focused-real、full pyright、覆盖率、
  old-seam `rg`、diff check 全部通过；README trigger 已裁决并更新。
- **stop condition**：真实进程树无法在状态机上限内收口、出现任何半发布/双终态/先 completed
  后 cancelled、或重试不一致；不得以放宽 oracle/时间阈值收口。

## 13. Validation matrix

### 13.1 Deterministic unit/integration/CLI

```bash
source .venv/bin/activate
pytest -q \
  tests/runtime/test_interruptible_process.py \
  tests/documents/test_docling_runtime.py \
  tests/fins/test_docling_process_converter.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_processor_read_consistency.py \
  tests/cli/test_fins_commands.py
```

测试不得用 timing sleep 判 race；使用 Event/barrier/fake handle 精确控制：child target 三段
failure、terminate/kill、final precommit checkpoint 前、commit ownership transfer 后、
`commit_batch` return/exception、summary claim/save 前后。断言 rollback 只在 caller-owned state
恰好一次、ownership transfer 后为零次；direct/durable 只提交一次同源 terminal。所有 fake 实现
public typed protocol，禁止 monkeypatch 旧 private conversion seam、构造开放 descriptor 或复制
production 状态机。

### 13.2 真实 Docling integration

```bash
source .venv/bin/activate
DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1 \
  pytest -q tests/fins/test_docling_upload_service_integration.py
```

该测试必须走 `ProcessDoclingConverter`、spawned child 与真实 Docling，验证 UTF-8 JSON bytes
可发布并被 read/process 消费；不得直接调用 upload service 旧私有同步 helper。

### 13.3 Focused-real UF-PF09

只执行冻结 scenario UF-PF09，不执行其余 137 条 full-real：

1. 在新的 calibration evidence 目录复制 UF-L02/UF-L04 所用 HK PDF、US DOCX 输入与对应
   ticker/source 参数；记录输入 digest、baseline、命令、环境、signal timestamp。
2. 每 50ms 用 POSIX `ps` 快照记录 timestamp、PID、PPID、PGID、state、CPU time 与 command；
   `worker-spawned` 只在发现 CLI descendant 且该 child 已进入独立 PGID 时成立，不能冒充
   conversion entered。保存 signal 前完整 descendant baseline。
3. 不增加 marker file、event、sleep 或测试专用 production hook。对识别出的 child 用环境现有的
   非侵入 stack sampler（本机优先 `py-spy dump --pid`，Darwin 可用 `/usr/bin/sample`）重复采样；
   只有原始 stack 明确出现 `docling_process_converter` child target、
   `convert_pdf_bytes_with_docling` / `run_docling_pdf_conversion` 与 `DocumentConverter.convert` 的
   连续调用链时，才记录 `conversion-entered` timestamp 并立即向 CLI
   发送一次 SIGINT。采样权限不足、child 已退出或只看到 construction/worker spawn 时该次证据
   无效，必须重跑或作为 blocker，不得用固定 sleep/总耗时替代。
4. 对 HK PDF 与 US DOCX 分别执行上述协议，保存原始 stack、连续 PID/PPID/PGID/descendant 快照、
   CLI stdout/stderr、exit、workspace before/after snapshot。时间线至少记录：worker-spawned、
   conversion-entered、SIGINT sent、首次观察 child/PGID terminal、全部 descendant terminal、CLI
   canonical terminal、CLI exit、temp/IPC/staging/backup/lock residue scan complete；同时保存
   shared owner 的 production cleanup phase diagnostics，把 cancel-observed、terminate、必要时
   kill（未发生则明确 `kill_not_needed`）、close、temp cleanup 与 cancelled-terminal-ready 逐项
   对齐到同一时间线。若某 phase log 缺失，结合第 13.1 deterministic barrier 也不能证明该 phase
   时，本次 evidence 失败；不得添加测试专用 hook 或猜测。
5. 两次均断言：**从 SIGINT sent 到 canonical terminal** 的 wall-clock 不超过
   `poll 0.05 + terminate 2.0 + kill 1.0 + 2.0s harness margin = 5.05s`；exit 130；只有
   cancelled screen/result；没有 completed；没有存活 descendant；没有 source 文档、blob、
   meta/manifest 半发布；没有 converter temp、IPC、staging、backup 或 lock residue。
   2.0s margin 已包含 `asyncio.to_thread` 调度、process join 与 sampling/harness 收口抖动；失败时
   必须按上述 phase evidence 定位，不得调高 5.05s。
6. 对两份相同输入原样重试，不清理无关持久状态，断言 exit 0、发布 original + Docling JSON
   + meta/manifest，digest/文档 identity 与正常路径一致。
7. 复跑 `download.cancellation-crash-and-recovery` 的一条真实 CN/HK Docling cancellation 回归，
   断言相同 process owner、相同 descendant cleanup、无半发布、相同输入可重试。
8. 保留冻结报告的 queried-absent 维度：direct upload 不产生 Host Run/SQLite EventLog/Trace/
   Memory；这是读取证据，不新增 Host/Engine 行为。

如果环境/模型冷启动使 child 未真正进入 conversion，证据无效，应重跑而不是把 early-cancel
结果当 UF-PF09。若 5.05s 阈值失败，先报告 terminate/kill/cleanup 所处状态和进程树，不提高
阈值掩盖缺陷。

### 13.4 Pyright、coverage 与 repository hygiene

```bash
source .venv/bin/activate
pyright dayu tests utils

rg -n "ProcessCnDoclingConversionRunner|CnDoclingConversionRunner|DoclingUploadConverter|convert_with_docling|_convert_bytes_with_docling|_convert_with_docling|UploadCancellationChecker|DoclingCancellationInput" dayu tests
rg -n "ProcessDoclingConverter" dayu/fins

coverage erase
coverage run -m pytest -q \
  tests/runtime/test_interruptible_process.py \
  tests/documents/test_docling_runtime.py \
  tests/fins/test_docling_process_converter.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_processor_read_consistency.py \
  tests/cli/test_fins_commands.py
coverage report --include='dayu/runtime/interruptible_process.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/docling_process_converter.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/docling_upload_service.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/cn_download_filing_workflow.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/cn_pipeline.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/sec_upload_workflow.py' --fail-under=80
coverage report --include='dayu/fins/pipelines/sec_pipeline.py' --fail-under=80
coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
coverage report --include='dayu/fins/service_runtime.py' --fail-under=80

git diff --check
git status --short
```

第一个 `rg` 的 expected result 为零；第二个只能命中 shared owner 定义、显式 typed injection 与
standalone/default composition construction，不得命中第二 implementation、wrapper 或 registry。

新增 shared owner 文件单文件覆盖率必须 `>=80%`；其他实际修改文件也逐文件检查，不能用
总体平均数遮盖低覆盖文件。任何已有 pyright error 被本次 touched/import path 触及，应在 owner
边界一并修复；禁止 ignore/cast/Any 掩盖。

## 14. README trigger decision

- `dayu/fins/` 会修改，且当前 `dayu/fins/README.md` 明确描述 CN/HK process conversion 与
  upload cancellation/batch 边界：**命中并应更新**为 shared Fins converter、typed cancellation
  与 publication first-committer。
- `tests/` 会修改，`tests/README.md` 有测试职责说明：**命中并应更新**现有 runtime/Fins/CLI
  测试覆盖段，不新增无关测试目录介绍。
- upload CLI 的 SIGINT 用户工作流从“等待同步转换完成”修为快速 130：根 `README.md` 的 upload
  使用/排障职责范围内，**命中并应更新**取消行为和“不会发布半成品”的用户承诺。
- 分层/装配方向未改变，仍为 UI -> Service -> Host -> Engine，且 direct Fins 不纳入 Host；
  `dayu/README.md` **不更新**。
- `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/config/README.md` **不更新**，因为对应
  生产目录不改且 owner 不变。

实施前必须先重新阅读上述目标 README 内的 `Agent更新约束【必须遵守】`；只更新其读者职责
范围，不机械同步代码符号。

## 15. 为什么不过度设计

- 只增加一个 Fins owner module、一个直接 converter Protocol、一个 frozen config/result 和
  closed error enum；不创建 registry、factory、profile、plugin、scheduler 或跨层 service。
- 复用现有成熟的 runtime process primitive 与 documents helper，不重写 multiprocessing 或
  Docling options。
- 一个无跨调用状态的 concrete instance 注入全部 Fins call site，删除旧 CN runner，而不是在
  新旧路径间加 facade。
- upload service 只做必要 async 化；现有 producer thread/private event loop、storage batch、
  CLI token 与 Host/Engine 边界保持不变。
- 不借取消修复重做 company meta、格式、多文件、repair、计数或并发语义。

## 16. Residual risks、open questions 与归属

### 16.1 Blocking open questions

无。唯一 owner、依赖方向、call-site migration、first-committer 与验证输入均已有直接证据，
可以进入两路 plan re-review。

### 16.2 Residual risks

| 分类 | 风险 | 本 WU 处理 | 剩余归属 |
| --- | --- | --- | --- |
| third-party/process | Docling 版本可能改变 child 的 descendant/signal 行为 | deterministic nested process-group + 真实 UF-PF09 | 若真实进程树仍不可控，阻塞本 WU，不降级 oracle |
| platform | 非 POSIX 无 `setsid/killpg`，runtime 只能保证直接 process | 保持 typed diagnostics，不虚假承诺 | Windows descendant governance assigned to later work unit |
| transaction | company meta 在 source conversion 前已独立提交 | 明确不把它计为 source half-publication | company meta refresh/transaction assigned to later work unit |
| reverse dependency | web fetch 仍为 documents 同步 conversion | 保持 tools -> documents 正向依赖 | web cancellation assigned to later work unit |
| formats | focused-real 只覆盖冻结 HK PDF、US DOCX | shared contract 不按后缀分支；两种真实验证 | 格式集合/help 漂移 assigned to later work unit |
| timing | 模型冷启动、stack sampler 权限或机器负载可能影响 conversion-entered 采样 | worker/process-tree 与 conversion stack 分离取证；5.05s signal-to-terminal budget | 无可信 stack 则证据无效/重跑；不能用总运行时或调高阈值替代 |
| terminal race | cancel 与 final checkpoint/commit/summary claim 可能同 tick | commit ownership transfer + direct/durable barrier first-committer tests | 若无法按第 9/10 节单义表达则阻塞实现，不下游过滤 |

## 17. Gate validation 与 completion status

本 plan gate 已完成的只读验证：

- 核对 branch、HEAD 与 merge-base 均为目标 baseline。
- 完整阅读根 `AGENTS.md`、goal confirmation、Host/Engine design。
- 完整阅读两份 plan review 与综合 adjudication，并把 10 组 accepted findings 写回本 artifact；
  rejected/already-covered/later findings未扩入 scope。
- 读取两个 oracle、UF-FIX09/UF-PF09 scenario、冻结报告 UF-L01–UF-L05。
- 追踪 runtime、Fins、CLI、documents 指定实现、全部生产 Docling construction/invocation
  call site，以及指定 runtime/Fins/CLI/CN/SEC filing/material 测试。
- 阅读相关 README 更新约束并形成 trigger decision。
- 未运行实现测试：本 gate 无生产/测试变更，测试执行留给对应 implementation slice。
- 未修改 accepted oracle/scenario registry，未执行 137 条 full-real，未 commit/push/PR。

**completion status**：`PLAN REVIEW FIX COMPLETE — READY FOR TWO-PATH PLAN RE-REVIEW`。

## 18. 后续 implementation/final closeout 固定格式

后续实现全部 slice 并通过 final closeout gate 时，最终报告必须只包含：

1. **改了什么**：唯一 owner、迁移 call site、terminal/publication 行为；列出删除的旧模块，
   不声称非目标已解决。
2. **验证了什么**：deterministic 命令与结果、真实 Docling integration、UF-PF09 两输入与
   download regression、full pyright、逐文件 coverage、`git diff --check`。
3. **文档**：实际更新的 README 及为何命中；oracle/scenario registry 未改。
4. **残余风险/未覆盖项**：按第 16 节分类并标 `assigned to later work unit` 或 blocker；明确
   company-meta 先提交仍存在。
5. **交付状态**：branch、baseline、implementation commits（届时）、artifact/evidence path；
   PR URL 仅在 Gateflow 后续明确授权创建 draft PR 后填写，否则写 `N/A`。
6. **禁止性确认**：未执行其余 137 条 full-real，未 push（除非后续得到明确授权）。
