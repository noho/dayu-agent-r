# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator implementation evidence

## 1. 结论

`COMPLETE`。

AgentCodex 已按 `$phaseflow` 当前 R09 implementation gate 与 Controller authorization，在同一未提交 cumulative tree 中依次完成 S1 唯一 Fins owner checkpoint 和 S2 Service/CLI mechanical cutover。R09 仍是现有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU，不是新 WU、feature 或 issue。

最终实现把 direct stream 的 exactly-one-and-last `RESULT`、`EVENT_AFTER_RESULT`、clean-exhaustion terminal availability、primary exception identity、cleanup cause chaining 与 raw source close-at-most-once 收敛到唯一 owner `dayu.fins.direct_stream.ValidatedFinsEventStream`。Service 只透传同一 typed stream；CLI 完整消费后读取 `terminal_result`，只保留既有 presentation、exit mapping 与取消语义。没有兼容层、fallback、第二 validator/error schema 或 speculative producer protocol channel。

受影响、R06、R08 与 full Fins tests 全绿；5 个 changed production Python 文件 coverage 均高于 80.00%；full pyright、scoped Ruff、diff、source/propagation/security/deferred/no-touch scans 全绿；真实 SEC download、真实 process/Docling、真实 upload smoke 均 exit 0。实现未 stage、commit、push、创建 PR 或进入 review。

## 2. Entry locks 与动机/owner 判定

开始实现前独立核对结果：

| Lock | Entry evidence |
|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` |
| branch | `phaseflow/host-issues-control` |
| accepted-plan parent | `a31ded764da0621b6e7a6c7c6a083b4bb6593d21` |
| accepted-plan tree | `4112761a35ed2a6b806caaaedd5654e93acfee9e` |
| fixed plan SHA-256 | `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` |
| authorization SHA-256 | `c9341d7b6c0c1eaa62578d68f7f34ed973ab63d67e3da6c4c1442d988d3a49e4` |
| staged tree | empty |
| Controller dirty evidence | existing modified control doc and existing untracked authorization only |

Authorization §3 source locks 全部精确匹配：

| Path | Entry SHA-256 / state |
|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d70205a23d1e1853c260ea0c9353567082710699bfc4000e485578cf3` |
| `dayu/fins/ingestion_runtime.py` | `176d8ab974c263f6aedc99b1d8b9a8fbd60ebed441a3aa950d5d9a718c64908a` |
| `dayu/service/fins_direct.py` | `875d5396b1d98bdc28f13480241e081529db5e9fa33416914fa6d47e9663b696` |
| `dayu/cli/commands/fins.py` | `666d9dc2793a706a5f00301f215ca324857e4593fcc4c98b18cc90fdc9e245bf` |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be571d2118648b7829714b885cd0c8a030b6499ec48625af7d207e57ebf4` |
| `tests/service/test_fins_direct.py` | `9c533d7e632762e3fe02a5ae1c58939d71bc7d8c6cb853bd21ad8b4e3a6f2e9b` |
| `tests/cli/test_fins_commands.py` | `525414da8675fdada4ad458271861cf2801c21f57544d62f436594218dafa26c` |
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` |
| `dayu/service/README.md` | `8d7d7680e82642a769da9a3acc28ea429f8ff32550dff732e6a0478c7aabb2d5` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `dayu/fins/direct_stream.py` | absent |
| `tests/fins/test_fins_direct_stream.py` | absent |

第一性原理判断：direct producer 的 terminal invariant 是同一业务事实；当前 runtime、Service、CLI 分散判断会允许同一 raw sequence 被多个层独立解释，产生 owner drift、provenance 改写和边界重复状态机。正确边界是 Fins direct typed stream：它直接拥有 raw async-generator 输入、operation provenance、terminal `RESULT` 与 close 生命周期，能在信息最完整处一次校验；Service/CLI 没有产生该事实所需的信息，因此只能消费同一 owner contract。R09 动机成立，accepted plan 的 owner 路径与最小修复边界成立。

## 3. 实现结果

### 3.1 S1：唯一 Fins owner checkpoint

- `FinsDirectStreamProtocolErrorKind` 新增唯一 `EVENT_AFTER_RESULT` code。
- 新增 `ValidatedFinsEventStream`，以显式 `OPEN / RESULT_BUFFERED / RESULT_YIELDED / CLOSED` 状态管理 direct stream。
- progress 在 result 前原样 yield；首个 result 先 buffer，只有 raw source clean exhaustion 后才 yield。missing、duplicate、result 后任意 event 分别由 owner 构造 typed error。
- `terminal_result` 只在 clean exhaustion 后可用且与 yielded result 为同一对象；OPEN、buffered 未确认、abortive close 均抛固定普通 `RuntimeError`。
- raw upstream exception/cancellation 保持同一 object；协议错误保持 owner object。cleanup 失败不替换 primary，而以 `primary.__cause__ is close_error` 链接；无 primary 的显式 close 传播同一 close error。
- raw `aclose()` 在成功、失败、重复 close 与 primary error 各路径最多调用一次。
- runtime public `download/preprocess/upload` 改为 plain `def`，直接返回 validator；raw `_run_direct_stream` 保留 `AsyncGenerator`，删除 terminal checker/buffering/speculative protocol channel，只转发 producer event 与原生异常/取消。
- 18 个 owner nodes 完整覆盖 event order、error/cancellation identity、cleanup precedence、close count 与 terminal availability；runtime 删除 3 个固化旧私有 checker 的 tests，保留 direct integration/security tests。

S1 checkpoint 未 stage、commit 或单独 review；随后在同一 tree 上继续 S2。

### 3.2 S2：Service/CLI mechanical cutover

- `FinsDirectRuntimeProtocol`、Service public/private direct methods 全部返回 `ValidatedFinsEventStream`；Service 直接返回 runtime 的同一 object，不 await、不 iterate、不 wrap、不 rebuild。
- 删除 Service `_ensure_result_event` 及其 missing/duplicate decision；Fins typed error、operation kind、message 与 object identity 原样传播。
- `process_filing` / `process_material` 保留 runtime `PREPROCESS` provenance，不改写为命令别名。
- CLI helpers 全部切到 typed validator；删除 `_direct_operation_kind`、terminal validation 的 `operation_kind` 参数和 missing fallback。
- CLI consumer 完整 `async for` 后读取 `events.terminal_result`；保留 `dayu-cli {command}: {message}`、exit 1、business result exit `0/1/130` 与 SIGINT race；不读取或展示 `reason.value`。
- Service/CLI fakes 只返回 production validator，invalid sequence 仍由唯一 owner 注入和判定；新增 identity/provenance tests，不复制协议算法。

## 4. S1 checkpoint validation

所有命令均先执行 `source .venv/bin/activate`。

| Command | Exact result |
|---|---|
| `pytest -q tests/fins/test_fins_direct_stream.py` 加 plan 指定 4 个 runtime exact nodes | `22 passed, 3 warnings` |
| `python -m pyright dayu/fins/direct_events.py dayu/fins/direct_stream.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_direct_stream.py tests/fins/test_fins_ingestion_runtime.py` | `0 errors, 0 warnings, 0 informations` |
| scoped S1 Ruff 初跑 | 发现 `ingestion_runtime.py` 一个未使用 `AsyncIterator` import；删除后重跑 |
| scoped S1 Ruff 最终重跑 | `All checks passed!` |
| `git diff --check` | pass，零输出 |
| runtime protocol-owner scan | exit 1，预期零命中 |
| `git diff --cached --name-only` | empty |

S1 sorted 5-path manifest（newline-delimited）SHA-256：`5456dc51702f7a1a71e06ac8fa6ed50e66ad1a061e4cdb30235f8cfc2a0139db`。

S1 canonical binary diff 由 tracked 3-path `git diff --binary HEAD` 后顺序拼接两个新增文件各自的 `git diff --no-index --binary /dev/null <path>` 组成，SHA-256：`ecda0918507e212331de0df998c92d7c83c0acaea4f8cc4741ffd73dba05aeab`。

S1 manifest：

1. `dayu/fins/direct_events.py`
2. `dayu/fins/direct_stream.py`
3. `dayu/fins/ingestion_runtime.py`
4. `tests/fins/test_fins_direct_stream.py`
5. `tests/fins/test_fins_ingestion_runtime.py`

## 5. Complete-tree validation ledger

### 5.1 Tests 与 regression

所有结果来自最终 production/tests/README 内容相同的 cumulative tree；pytest 的 3 个 warnings 均为既有 edgartools deprecation warnings。

| Exact command | Result |
|---|---:|
| `pytest -q tests/service/test_fins_direct.py tests/cli/test_fins_commands.py` | `52 passed, 3 warnings` |
| `pytest -q tests/fins/test_fins_direct_stream.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py` | `155 passed, 3 warnings in 4.10s` |
| 同一 complete-tree suite 的 coverage run | `155 passed, 3 warnings in 4.89s` |
| `pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py` | `242 passed, 3 warnings in 24.24s` |
| `pytest -q tests/fins/test_financial_read_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py tests/fins/test_processor_read_consistency.py` | `180 passed, 3 warnings in 5.43s` |
| `pytest -q tests/fins` | `874 passed, 1 skipped, 3 warnings in 39.07s` |
| 12 个 exact injected owner/Service/CLI adversarial nodes | `12 passed, 3 warnings in 0.91s` |

首次并行 full-Fins 捕获只返回到 65% 且没有可靠 exit status，因此未计为证据；随后重新独立执行完整命令并取得上述 exit 0 与完整结果。full-Fins 的 1 个 skip 是既有环境测试，本实现没有新增或修改 skip/xfail；真实 Docling smoke 另行实际成功，未以该 skip 代替。

12 个 injected nodes 覆盖 owner missing/duplicate/event-after/result-then-error、Service identity 与两个 preprocess alias、CLI presentation/object identity 与两个 preprocess alias。pytest fake 没有被记为真实 smoke。

### 5.2 Changed production file coverage

数据命令：

```bash
coverage erase --data-file=workspace/tmp/.coverage-r09
coverage run --data-file=workspace/tmp/.coverage-r09 -m pytest -q \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
coverage report --data-file=workspace/tmp/.coverage-r09 --include=<each-changed-production-path> --fail-under=80
coverage json --data-file=workspace/tmp/.coverage-r09 -o workspace/tmp/coverage-r09.json
```

五次单文件 report 与 JSON 生成均 exit 0；无 waiver、omit、changed-line 或 aggregate threshold 替代。

| Production path | Statements | Missing | Exact JSON coverage |
|---|---:|---:|---:|
| `dayu/fins/direct_events.py` | 154 | 12 | 92.20779220779221% |
| `dayu/fins/direct_stream.py` | 90 | 3 | 96.66666666666667% |
| `dayu/fins/ingestion_runtime.py` | 1684 | 161 | 90.43942992874109% |
| `dayu/service/fins_direct.py` | 61 | 6 | 90.16393442622950% |
| `dayu/cli/commands/fins.py` | 343 | 40 | 88.33819241982508% |

Coverage JSON SHA-256：`8ba9abf67272ad157d807234731a9907f320624b1e30c97bb6593cd9571becef`。

### 5.3 Type、lint 与 diff

| Exact command | Result |
|---|---|
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| plan §8.3 全部 9 个 changed Python files 的 `python -m ruff check ...` | `All checks passed!` |
| `git diff --check` | pass，零输出 |
| `git diff --cached --name-only` | empty |

S2 初始 scoped Ruff 发现 CLI production 3 个未使用 import 与 Service test 1 个未使用 import；均在 allowlist 内删除，最终 cumulative Ruff 为零。没有 ignore、配置排除或 cast-away 类型错误。

## 6. Source、propagation、安全与 no-touch scans

按 accepted plan §8.4 逐组运行并分类：

- `_ensure_result_event|Fins direct Service stream ended without RESULT|_direct_operation_kind`：Service/CLI production/tests 零命中，`rg` exit 1。
- `raise FinsDirectStreamProtocolError|FinsDirectStreamProtocolErrorKind|reason\.value`：Service/CLI production 零命中，`rg` exit 1。
- `FinsDirectStreamProtocolError`：ingestion runtime 与 Service 零命中，`rg` exit 1。
- `MISSING_RESULT|DUPLICATE_RESULT|EVENT_AFTER_RESULT`：只命中 `direct_events.py` enum 定义与 `direct_stream.py` owner decisions；runtime、Service、CLI 零 literal。
- `ValidatedFinsEventStream`：命中唯一 class、runtime 3 个直接构造位置、Service/CLI typed direct consumers 与对应 tests；无第二 wrapper/checker。
- implementation-base added-line `hasattr|getattr|compat|fallback|Any|object` 弱类型/兼容扫描：production added lines 零命中；新增 `direct_stream.py` 全文同类精确扫描也为零。
- no-deferred scan：Issue 142/151/175/177/178、R10/R11/R12、Topic 8/9、统一 authorization framework、Web、WeChat、`dayu/render` 零 implementation 命中。宽泛单词 `render` 只命中 CLI 既有 `render_*` presentation 名，人工分类为非 deferred scope。
- safe-text/security scan：`direct_events.py` production diff 仅新增一个 enum；validator 不包含 path、job id、raw payload/body/provider text。现有 leakage guard、operation cancellation、queue backpressure、late publication、storage containment/symlink、atomic publication、R06 transaction、authorization 与 process fencing未修改。
- no-touch：`README.md`、`dayu/README.md`、`docs/fins/design.md`、`docs/host/design.md`、Host/Engine/UI、storage/pipelines/processors/read contracts、R01-R08 artifacts 与 prior plan/review artifacts相对 base 零 authored diff。
- Controller-owned `docs/host/issues-implementation-control.md` 与 untracked authorization 在 entry 已存在；AgentCodex 没有修改、覆盖、stage 或纳入 implementation lock。

## 7. 真实 success smokes

所有 smoke 先激活 `.venv`，从 `python -m dayu.cli` 经过真实 Service、`DefaultFinsRuntime`、producer 与 validator；没有 mock、skip 或 fake 替代。

### 7.1 SEC download

```bash
python -m dayu.cli --base workspace/tmp/r09-real-download download \
  --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31
```

结果：exit 0；输出 `preparing/started/filing_started/filing_completed/completed` progress 与一个 success terminal；`discovered=1, downloaded=1, skipped=0, rejected=0, failed=0, written=1`。运行前 workspace 为 fresh。

### 7.2 Process / Docling

```bash
python -m dayu.cli --base workspace/tmp/r09-real-download process --ticker AAPL
```

结果：exit 0；真实 preprocess/Docling path 输出 progress 与一个 success terminal；`selected=1, processed=1, skipped=0, failed=0, not_supported=0`。

### 7.3 Upload filing

```bash
python -m dayu.cli --base workspace/tmp/r09-real-upload upload_filing \
  --ticker AAPL --action create \
  --files tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm \
  --fiscal-year 2024 --fiscal-period FY \
  --filing-date 2024-11-01 --report-date 2024-09-28 \
  --company-name 'Apple Inc.'
```

结果：exit 0；输出 progress 与一个 success terminal；`source_kind=filing, status=ok, uploaded_files=1`，document id 为 `fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283`。workspace 为 fresh。

## 8. README decision

修改前已读取三份目标 README 的 Agent 更新约束。

- `dayu/fins/README.md`：只同步 Fins public typed direct stream、raw bridge 与 unique validator contract。
- `dayu/service/README.md`：只同步 Service direct pass-through identity 与不拥有 terminal validation。
- `tests/README.md`：只同步 current owner/runtime/Service/CLI contract tests、identity/provenance 与 terminal availability。
- root `README.md`：CLI 命令、参数、输出格式、exit mapping 与用户工作流均未变，不触发。
- `dayu/README.md`：分层顺序与装配关系未变，不触发。

README 没有写 gate 历史、未来 R10-R12、Controller 决策或测试实现细节。

## 9. Final cumulative manifest 与 immutable locks

Sorted product/test/README manifest 精确为 12 个路径：

1. `dayu/cli/commands/fins.py`
2. `dayu/fins/README.md`
3. `dayu/fins/direct_events.py`
4. `dayu/fins/direct_stream.py`
5. `dayu/fins/ingestion_runtime.py`
6. `dayu/service/README.md`
7. `dayu/service/fins_direct.py`
8. `tests/README.md`
9. `tests/cli/test_fins_commands.py`
10. `tests/fins/test_fins_direct_stream.py`
11. `tests/fins/test_fins_ingestion_runtime.py`
12. `tests/service/test_fins_direct.py`

该 newline-delimited sorted manifest SHA-256：`ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`。

逐文件 content locks：

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 988 | `c60e5152fa7e7db7d5795ce7845f7f285f3c52d9392df9140d66ef078a9b7e59` |
| `dayu/fins/README.md` | 789 | `81f788b1e935bb06293bb866f47be3dd907424dc86cb65fded18aaf0ba388252` |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `tests/README.md` | 293 | `3355e9652e7e373e4526ce1862ae6e270924487fa8e6a2d3a123ee02e7755d7e` |
| `tests/cli/test_fins_commands.py` | 1539 | `d425cf29aa909014c09ea92069cf3e41539a7720385f69fa64b6f7ae6a957f4c` |
| `tests/fins/test_fins_direct_stream.py` | 750 | `7607a6ff790031ad15b6fc66478dfad3d0d2db15dfc3cf65d30f1856d8ee6ceb` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4821 | `8fd5f5a95333da40df5ffb4b2dc1178c3c6e874d468c7659198fb6d820826f02` |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |

Cumulative canonical binary diff 由 tracked 10-path `git diff --binary HEAD` 后顺序拼接两个新增文件各自的 `git diff --no-index --binary /dev/null <path>` 组成，SHA-256：`531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8`。

本 artifact 是 authorization 允许的第 13 个 durable authored path，但无法在自身内容中递归嵌入最终原始 content SHA 而保持该值有效。写入完成后 AgentCodex 从外部计算它的行数与 SHA-256，并在最终 handoff 报告；Controller 锁树时应将该外部值加入 immutable manifest。

## 10. Exit locks

- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`，与 entry/accepted-plan commit 相同。
- branch：`phaseflow/host-issues-control`，与 entry 相同。
- fixed plan SHA-256：`a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`，与 entry 相同。
- authorization SHA-256：`c9341d7b6c0c1eaa62578d68f7f34ed973ab63d67e3da6c4c1442d988d3a49e4`，与 entry 相同。
- `git diff --check`：pass，零输出；两个新增 Python 文件与本 artifact 分别执行 `git diff --no-index --check /dev/null <path>`，均只有 Git 表示“存在 diff”的 exit 1，check 输出为空。
- staged tree：empty；未 stage、commit、push、创建 PR。
- `git status --short` 的 authored path 精确为上述 12 个 product/test/README 路径与本 artifact；另有 entry 已存在的 Controller modified control doc 和 untracked authorization，没有额外路径。

## 11. Residual risk 与 handoff

- R09 owner contract、real SEC/Docling execution、coverage、type/lint 与 no-regression 的 accepted-plan residual 为 0。
- full-Fins 仍有 1 个仓库既有 environment skip，和本次 changed owner/source 无交集；真实 process/Docling smoke 已成功，因此不构成 R09 waiver。
- pytest 仍报告 3 个既有 edgartools deprecation warnings；未升级为 error，也未进入 changed owner。
- Issue 175 继续拥有更广泛的 process isolation；Issues 142/151/177/178、R10-R12、Topic 8/9 与 Web/WeChat/render 均未实施，也不是本 gate 的遗留实现。
- workspace 仅在 `workspace/tmp/` 保留 coverage 与 smoke 临时证据；不属于 durable diff。

最终状态：`COMPLETE`。下一步只允许 Controller 复核 exit locks、锁定同一 immutable cumulative tree 并按既定 gate 发起双路 code review；AgentCodex 到此停止等待，不 stage、commit、push 或创建 PR。
