# D1 实施与验证

后续 Finding1 的 owner 输入校验修复及新组合版本证据见 [D1 owner 修复报告](tsm-6k-rejection-20261023-d1-owner-fix.md)；本报告保留原实施版本的历史事实。

implementation/validation 一个 slice 已完成；下一入口为总控对最终组合版本执行完整 code review。本记录不宣布审核或 work unit 完成。真正 blocker：无。

## 范围与被测身份

按 [D1 控制记录的 Plan 核对通过](tsm-6k-rejection-20261023-d1.md#plan-核对通过) 实施。基线仍为 `investigation/tsm-6k-20261022` / HEAD `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`；全部修改未提交，不能只凭 HEAD 识别修后版本。

新证据根目录：`workspace/tmp/tsm-6k-20261022/d1/`（下文 D）。保留：

- `D/source-snapshot/`：四个改动生产模块、pyproject、三个测试文件及两个 README 的实际文件副本。
- `D/source-manifest.json`：逐文件 SHA256、版本、基线及聚合身份。
- `D/source-changes.patch`：以上文件相对基线的完整差异，包含两个新增文件；`D/git-status.txt` 保存未提交状态。
- 四个生产模块的聚合 SHA256：`5e24aa2365968c1bfb25ab5711a0ab6b5ed6017f9254248d1543323a0830484b`。
- 十文件快照聚合 SHA256：`be625a1583bb1b98a78d345e7ef6488a72e941f2a8eda0aff0c1804896308cbc`。聚合算法为排序后的路径→文件 SHA256 JSON 的 SHA256，脚本 `D/capture_state.py` 可查。

验证使用仓库 `.venv` / Python 3.11.15，实际生产导入为当前 checkout；离线 `invocation.json` 保留 `dayu_file`。版本只将 `pyproject.toml` 的 project version 从 `0.1.5` 改为 `0.1.6`；`SEC_PIPELINE_DOWNLOAD_VERSION` 仍为 `sec_pipeline_download_v1.3.0`。

## 实际改动与 owner

新增 `dayu/fins/pipelines/sec_download_disposition.py`，唯一入口 `project_sec_filing_disposition(Mapping[str, JsonValue]) -> FinsDownloadDocumentDisposition`：严格读取状态；四值直接映射，只有 skipped 的两个既有原因入口命中 `6k_filtered` 才投影 REJECTED。参与判定的非法字段抛 ValueError，不转换非法值，不修改原行，也不查询仓储或注册表。

`sec_download_workflow._build_sec_download_result` 统一按 enum 互斥计数；`_cancelled_pipeline_completed_event` 复用同一 builder。完整性中止保持既有快照路径。`sec_pipeline._project_sec_document_row` 消费相同分类，保留原原因类别、安全文案、业务字段校验与 locator 行为；typed summary 仍由 `from_document_rows` 派生。两份重复 `_is_rejected_filing_result` 均删除。

`warn_insufficient_filings` 三组数量仅统计统一分类为 DOWNLOADED/SKIPPED 的行；阈值及注册表补充说明不变。没有在 warning/CLI 按原因码或文件补分支，没有新 schema/framework、反向依赖或兼容转发。生产改动限定为上述四个模块；未改 CLI/Service 调用方、下载器、6-K 筛选、原始 status/reason、存储与发布协议。

## 实际命令、退出与覆盖率

每条验证命令均先 `source .venv/bin/activate`，由 `D/run_logged.py` 保存独立目录。以下标签对应 `D/commands/<标签>/command.json` 中完整 argv/cwd/时间/退出码；同目录 `stdout`、`stderr` 保留完整原输出，未用摘要替代。未复用旧 129/43 项结果作为修后证据。

| 标签 | 实际验证 | 退出与结果 |
| --- | --- | --- |
| `focused` | 新 owner、数量/失败/取消/完整性边界聚焦 pytest | 0；44 passed |
| `affected-coverage` | disposition、pipeline download/stream、upload filing/material stream、earnings repair 六文件 pytest；四模块 coverage | 0；328 passed，67.17 秒 |
| `final-boundaries` | 三成功信号、拒绝资产失败、取消快照、完整性中止、追加显式 rejected 原因契约 | 0；10 passed，包含新增的两项显式 rejected 用例 |
| `pyright-1` / `pyright-final` | `pyright --outputjson` | 均 0；最终 841 files，0 errors / 0 warnings |
| `scripts-pyright` | 总控用显式 config 检查四个 D1 临时脚本 | 1；4 files，1 error，原证据保留 |
| `scripts-pyright-final` | 修正后使用相同 config 显式检查四脚本 | 0；4 files，0 errors / 0 warnings |
| `package-entrypoints` | `python -m pytest tests/cli/test_public_package_entrypoints.py -q` | 0；4 passed |
| `offline-1` | 严格离线脚本首轮 | 1；脚本误将 public JSON 当持久摘要读取 `rejected_count`，真实 public 为 `summary.counts.rejected`；仅修脚本 |
| `offline-2` | 新 fresh base 严格离线重跑 | 0；10/10 请求消费，全部对账通过 |
| `offline-final` | 脚本类型修正后再用权威捕获重跑至全新目录 | 0；10/10 请求消费，全部对账通过 |
| `wheel-verification` | 隔离副本/wheel metadata 与源码字节核对 | 0；0.1.6，四模块一致，产物另保留 |
| `diff-check` | `git diff --check` | 0 |
| `source-snapshot` | 源码快照与 wheel 源码摘要比对 | 0 |
| `script-snapshot-final` | 保存四脚本真实副本/hash，核对产品快照未变 | 0；逐文件字节一致 |
| `coverage-no-exclusions` / `coverage-strict-report` | 用同一 raw coverage 数据清空默认 exclude 后重新生成报告 | 均 0；四文件达标 |

`D/affected-pytest.xml`、`D/.coverage` 保存主回归原始证据。默认 `D/coverage.json` 排除了 Protocol 空体；最终采信 `D/coverage-no-exclusions.json`，配置 `D/coverage-strict.ini` 的 `exclude_lines` 为空，四文件 excluded_lines 均为 0，无新增排除或为追数改产品逻辑：

| 生产文件 | 已覆盖/语句 | 最终覆盖率 |
| --- | --- | --- |
| `sec_download_disposition.py` | 29/29 | 100% |
| `sec_download_diagnostics.py` | 59/60 | 98.33% |
| `sec_download_workflow.py` | 243/282 | 86.17% |
| `sec_pipeline.py` | 416/467 | 89.08% |

主回归之后只追加两项显式 rejected 原因投影测试，并执行最终 10 项边界回归与全量 pyright；生产源码未变化，已有覆盖率与 wheel 证据仍适用。pytest 的三条告警均为既有 edgartools DeprecationWarning。

## 三个成功信号与失败/取消

`test_sec_quantity_warning_matches_real_fs_and_typed_result` 仅替代外部响应，真实运行分类、工作流、Fs 发布及 typed 投影；同一确认行联合断言：

| 场景 | downloaded / skipped / rejected / failed | warning 有效数 | 仓储 active |
| --- | --- | --- | --- |
| 拒绝一份 | 0 / 0 / 1 / 0 | 0，仍不足 3 | 0 |
| 一份完整来源再次下载跳过 | 0 / 1 / 0 / 0 | 1，仍不足 3 | 1 |
| 有效两份加拒绝一份 | 2 / 0 / 1 / 0 | 2，仍不足 3 | 2 |

raw summary 与 typed summary 逐类相等，拒绝行原 reason/registry/artifact 一致且 locator 为 null。`final-boundaries/stdout` 保存每组 raw/public 摘要。

新增/增强验证还包括四值与两原因入口、严格非法字段、三个数量组阈值控制、拒绝资产下载失败仍为 `rejected_artifact_download_failed`、显式 rejected 的既有原因缺省/显式规则；真实拒绝后取消只保留已确认一行，后续候选未请求。完整性中止的拒绝前缀/失败行与 typed 摘要互斥一致并保留原 cause；原三个循环尾取消、repair 后取消、早期零行取消均经过主回归。早期取消 builder 的非空行仅是同一真实行集的构造契约测试，不宣称该场景在当前早期调用点可达。

## 权威输入的严格离线补证

仅读取 `s1/pipeline-clean-requests`。`D/verify_offline.py` 为本轮新脚本；历史 probe、旧 s1/controller 数据均未写入。HTTP 替身只按捕获 method/URL/顺序提供原响应，核验 body 长度与 SHA256，移除已解码响应的 wire 编码/长度头；未知或乱序请求立即失败，未持有网络 transport，无缺项回退。观测数量函数只保存原入参与原函数返回值，不修改分类。

最终采信 `D/offline-final/`（脚本类型修正后全新 fresh base）；上一轮 `D/offline/` 保留不覆盖。两轮均经真实公开 CLI→workflow→仓储，退出 0，消费全部 10 个请求：

- `quantity-current-input.json`：当前唯一 raw 行仍为 `status=skipped`、`skip_reason=reason_code=6k_filtered`，季度 warning 为“有效落盘数 0 低于期望 3”。
- `public.json`：唯一 public 文档为 rejected，`summary.counts` 为 discovered1/downloaded0/skipped0/rejected1/failed0，原因 `6k_filtered`、locator null。
- `reconciliation.json` 与 `base/`：active0、registry1、拒绝 artifact 原因一致；原件 SHA256 `021c698879a544fc41f2f0064d478480308ef1b0e9e30049299f8210945aa4a2`，与捕获 GET 字节逐字节相等。
- `requests.json`、`invocation.json`、`exit.json`、stdout/stderr/dayu.log 保留输入来源、实际入口、请求消费和原输出。失败首轮 `D/offline-1/` 原样保留，不将其标为通过。

## 临时脚本显式类型补验

项目默认 pyright 排除 workspace，因此总控通过 `workspace/tmp/tsm_d1_pyrightconfig.json` 显式包含 `run_logged.py`、`check_wheel.py`、`verify_offline.py`、`capture_state.py`。首次 `scripts-pyright` 退出 1，分析 4 文件，仅 `verify_offline.py:188` 的 invocation JSON 将 `list[str]` 直接赋给要求 `list[JsonValue]` 的值，触发容器不变性错误；原失败 stdout/stderr/command.json 保留。

唯一脚本改动：显式构造 `invocation_argv: list[JsonValue] = [argument for argument in argv]`，以真实逐项复制生成 JSON 数组，原 `argv` 仍用于 CLI 调用。未使用 Any、ignore、类型强转或默认回退，输出内容及重放规则不变。

实际重跑命令如下；激活环境后的完整 argv/输出/退出仍分别保存在上述同名 command 目录：

```bash
source .venv/bin/activate
python workspace/tmp/tsm-6k-20261022/d1/run_logged.py scripts-pyright-final pyright --project workspace/tmp/tsm_d1_pyrightconfig.json --outputjson
python workspace/tmp/tsm-6k-20261022/d1/run_logged.py offline-final python workspace/tmp/tsm-6k-20261022/d1/verify_offline.py --capture workspace/tmp/tsm-6k-20261022/s1/pipeline-clean-requests --output workspace/tmp/tsm-6k-20261022/d1/offline-final
```

`scripts-pyright-final` 退出 0，filesAnalyzed=4、errorCount=0、warningCount=0；`offline-final` 退出 0，全部 10 请求耗尽，warning 有效0、public rejected1、仓储 active0、原原因与原件 SHA256 均与上节一致。

四脚本的独立真实副本位于 `D/script-snapshot-final/`；该目录 `manifest.json` 保存逐脚本 SHA256、显式 config 原路径/hash、成功命令及最终离线对账 hash，另保存 `pyrightconfig-used.json` 原配置内容供核查。四脚本聚合 SHA256 为 `2e9e1ab0f313b97f1315d71c7b656368e7b2edcb4a6a7d0056cd0c92f8c26e06`；最终 `verify_offline.py` SHA256 为 `7923c8a5e07339698cd8d4e60dffb1ff1b702b24246f2d95974569a25d26c0a0`。

快照命令同时逐一核验原 `source-manifest.json` 的十个源码/测试/README 文件均未变化，生产聚合身份仍为 `5e24aa2365968c1bfb25ab5711a0ab6b5ed6017f9254248d1543323a0830484b`。本轮未修改产品源码或测试，原产品快照、回归、覆盖率及 wheel 证据继续适用；未重跑无影响测试/wheel 或项目全量 pyright。

## 隔离构建与文档决定

复用 package entrypoints 测试的隔离副本及构建产物，实际构建 cwd 为 `D/package-pytest/test_wheel_excludes_placeholde0/source`，完整构建命令/输出在其父目录 `build.command.json`、`build.stdout`、`build.stderr`。未在 checkout 执行 pip wheel，未安装本包。

保留 wheel：`D/wheel/dayu_agent-0.1.6-py3-none-any.whl`；SHA256 `1fdc32e36b2161cfa9941b7e7d2662ebeb53f21c2355bf7d5fca5b2985c29f84`。`D/wheel-verification.json` 证明当前及复制的 pyproject 声明、wheel 文件名/METADATA 均为 0.1.6，四个改动模块在当前源码、隔离副本和 wheel 中完全相同。没有以已安装包 metadata 代表修后版本。

已按职责更新 Fins README 的稳定分类/数量语义和 tests README 的回归边界/运行命令。根 README 的用户操作、排障步骤与总体分层均未变化，根 README、`dayu/README.md` 无需更新；未记录治理流水账。

## 风险、未覆盖项与交接

- `fixed in current slice`：数量诊断 owner 漂移、重复投影及取消 builder 重复计数；owner 为 SEC disposition/workflow/diagnostics，destination 为本次源码与上列验证，无范围内待修失败。
- 验收边界：离线证据只证明保存响应在当前修后代码的行为；未联网重抓，也不复原历史 GET。剩余未覆盖行详见严格 coverage JSON，不宣称全仓测试或线上恢复。原调查已核收的证据限制持续有效，无 D1 扩围动作。
- `requiring new issue or explicit user decision`：live 同步/安装及 merge 尚无授权；owner 为用户/总控，destination 为审核核收后的明确授权流程，不阻塞当前 implementation/validation 交接。

未 stage/commit/push/PR/安装/merge，未派 Agent、未发外部消息，未改总控记录或历史业务证据。下一步由总控派 MiMo/DS 对最终组合及上述源码身份执行完整审核。
