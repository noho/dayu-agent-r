# PR206 0.1.5 增量 V1：最小修复与验证回执

## 范围、依据与当前入口

本轮仅实现主控已裁决 V1 的修复，依据为 [version-adjudication](public-original-read-r1-r3-20261020-version-adjudication.md)、其中引用的独立报告 [DS 163643](../reviews/code-review-20261020-163643.md) 与 [MiMo 164952](../reviews/code-review-20261020-164952.md)，以及用户本次限定。两份报告均已完整读取；采用主控对 V1 的最终裁决，不沿用 MiMo 将正确安装后 baseline 误失败转交后续 metadata 框架的解释，也不引入 DS 建议的安装 metadata 扫描机制。

Preflight：分支 `fix/public-original-read-r1-r3-20261020`，HEAD `090eb4f566fd94a57d9b758f5dd67cf30f814141`，已核收 R1–R3 base 为 `f854a6e6ff3e3a1cee24745eaae96148843d6401`。开始时主控维护的 authorization/control/adjudication 和独立报告已有工作树变化；执行期间 version-increment 也由主控更新。这些文件均只读，不回写、不纳入本 writer 的修改范围。

用户与主控已明确目标、owner、最小方案和验证边界，本轮直接承接既有 `fix`，一个 slice，不新增 plan review 或架构决策。V1 修复实现与受影响验证已完成；下一入口是主控安排双路窄复审并核销 V1。本报告不裁定审核通过、PR 交付或安装完成，不推进提交、push 或 PR gate。

## 根因、owner 与实际修复

动机成立。`_assert_package_version` 把 baseline/current 源码的 `pyproject.toml` 声明当成同一 `.venv` 中 `importlib.metadata` 解析值的期望，混淆了源码身份与运行环境 metadata。baseline 没有独立 metadata，升级后解析到当前安装的 `0.1.5` 是正常现象；current 查询也可能先命中 ignored 源码 egg-info。更换固定常量或另建 baseline metadata 都没有修正这个职责错误。

职责保持为：`pyproject.toml [project].version` 是发行声明 owner，setuptools 生成 wheel metadata；真实 CLI provenance 测试以原有源码路径、七个 producer 指纹及下载版本验证源码身份；observer 的 `package_version` 只记录运行环境按路径解析的实际 metadata，不证明 baseline 源码版本或安装成功。实际安装版本属于后续明确授权的 sync 后核对。

本 writer 仅修改：

| 文件 | 实际变化 |
|---|---|
| `tests/fins/test_sec_html_image_assets_real_cli.py` | 删除本轮新增的 `_assert_package_version`、其调用和 `tomllib` 导入；不恢复历史 `package_version == "0.1.4"`，不改成 `0.1.5` 常量。保留原 observer，并增加一条明确 metadata 观测边界的中文源码注释。 |
| `tests/README.md` | 将错误的 baseline/current 声明比较职责改为 metadata 仅观测、源码身份断言、wheel 同源验证及后续 sync 安装核对的正确职责说明；原隔离 wheel 说明保留。 |
| 本报告 | 保存修复事实、纠正历史结论、实际验证和接续事项。 |

`pyproject.toml` 的 `0.1.5`、隔离 wheel 测试及公开入口均保持不变；没有 production Python、版本 API、fallback、兼容分支或永久镜像测试。R1–R3 未变源码与业务回归未重开。

## 对错误初版报告的纠正

[version-implementation.md](public-original-read-r1-r3-20261020-version-implementation.md) 原文作为错误初版历史保留，文件 SHA-256 前后核对不变。本报告明确替代其以下推论：

1. “正确修复是让测试按对应源码声明判断实际 metadata”及 `_assert_package_version` 的正确性结论错误。二者不是同一 owner 的事实，本轮已删除该比较。
2. 原四向 helper 探针只能证明比较表达式按输入数字工作，不能证明实际 baseline/current 的 metadata 归属正确；原两正例及两拒绝不能作为 V1 修复证据。
3. 原 residual risk 中“按对应声明比较已修复”和“未来运行必须使各自实际 metadata 匹配，旧版/错版仍应失败”的要求错误。baseline 不需要另建安装 metadata 或影子框架；源码身份继续由原断言核定。
4. 原报告对 wheel 的同源验证、隔离构建与安装 metadata 的区分不因此失效，但本轮 mandatory 测试和 pyright 均重新实际执行，不用旧 pass 代替当前验证。plan/control/adjudication 的现状由主控维护。

## 可取回版本与原源码身份断言核对

本轮全部临时证据根目录：

`workspace/tmp/public-original-read-r1-r3-20261020/version-fix-20261020T085324Z/`

- `before/` 保存修改前两个测试文件、测试 README 和版本声明；`branch.stdout`、`head.stdout`、`initial-status.*`、`initial-diff.*` 保存开始身份。
- `source-snapshot/` 保存 895 个 tracked 源码、包资源、受影响 README、构建/类型检查配置及约束文件，包括 `dayu/`、`tests/`、`utils/` 下全部 tracked Python；清单 `source-snapshot.sha256.json` 的 SHA-256 为 `08c2d93a85866f8ebf609e2288d42ebaca378f416a23af450755ac287ef90269`。
- `f854a6e6-real-cli.py` 保存已核收原测试的准确字节。`source-identity-check.json` 与最终成功探针 `offline-probe.json` 记录直接比较：从该原文件的 AST **只删除唯一历史 `assert origin["package_version"] == "0.1.4"`** 后，与当前整份测试 AST 完全相同。注释不影响 AST，observer 字符串逐字不变。该检查覆盖整个测试，确认 `code_root`、七个 producer 的集合/路径/hash、独立 downloader hash、各模块来源、`download_version` 及全部其它下载语义断言完整保留。
- `slice.diff` 保存 HEAD 到本次测试/README 修复的准确差异，`base-to-fixed.diff` 保存 `f854a6e6` 到当前四个版本增量文件的差异。`production.diff` 为空；本报告另有 `report-snapshot.md` 和最终 hash 清单。
- 上述 AST 检查是临时证据核对，不是新增永久测试。旧 R1–R3 核收证据只适用于未变部分，本轮不重新背书；旧 `4 passed` / pyright 不作为本轮 mandatory 结果。

## 实际验证、命令、双通道与退出

每个外层 label 都保存 `*.command.json`（完整 argv/cwd）、`*.execution.json`（真实退出码及 UTC 起止时间）、`*.stdout`、`*.stderr`。`record_command.py` 只负责记录命令。下列命令均在仓库根先激活本 `.venv`，没有安装本包。

### 受影响测试

```bash
source .venv/bin/activate && env -u DAYU_SEC_IMAGE_REAL_VALIDATION PYTHONDONTWRITEBYTECODE=1 PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 python -m pytest -q -rs -p no:cacheprovider tests/cli/test_public_package_entrypoints.py tests/fins/test_sec_html_image_assets_real_cli.py --basetemp /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/version-fix-20261020T085324Z/pytest-tmp
```

label `affected-tests`，退出 `0`：`4 passed, 2 skipped, 3 warnings in 2.14s`。三条 warning 是 edgartools 弃用提示。两例真实 SEC CLI 用例均因未启用 opt-in 明确 skip，文案注明“这不是实际网络验收通过”。本轮不把 skip 算成网络通过，也不把整轮业务回归或实际安装作为 V1 修复门槛。

保留的真实 wheel 位于：

`pytest-tmp/test_wheel_excludes_placeholde0/wheel/dayu_agent-0.1.5-py3-none-any.whl`

大小 `2676445` 字节，SHA-256 `271433ac5c33798f560eecb7a5af6e826b44389b0d2b9be6ca5f58b83a1d958d`。其内部命令记录在 `pytest-tmp/test_wheel_excludes_placeholde0/build.command.json`，cwd 为同级 `source/`，真实退出 `0`；完整双通道在 `build.stdout` / `build.stderr`：

```text
/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/version-fix-20261020T085324Z/pytest-tmp/test_wheel_excludes_placeholde0/wheel .
```

`wheel.METADATA`、`wheel.entry_points.txt` 保存产物原始字节。`wheel-verification.json` 记录重新核验：`Name: dayu-agent`、`Version: 0.1.5` 与当前 `pyproject.toml` 同源；入口仍仅为 `dayu-cli = dayu.cli.__main__:exit_module`。478 个 wheel 包文件逐字等于源码快照。`build-input-snapshot/` 另保存该构建副本 489 个实际输入文件（含未跟踪的系统目录文件）；清单为 `build-input-snapshot.sha256.json`，逐字与本树对应输入核对一致。pip cache 不可写的 warning 已保留，构建未提权。

### 当前全量 pyright

```bash
source .venv/bin/activate && pyright
```

label `pyright`，退出 `0`：`0 errors, 0 warnings, 0 informations`；使用未改动的配置覆盖 `dayu/`、`tests/`、`utils/`。stderr 仅工具新版本通知，未升级或绕过类型检查。没有改 production Python；本轮仅删除错误断言，不用网络/覆盖率扩张为未变业务重新设门槛。

### 无网络 provenance / metadata 独立事实 probe

```bash
source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/public-original-read-r1-r3-20261020/version-fix-20261020T085324Z/offline_probe.py
```

最终 label `offline-probe-2`，退出 `0`。探针导出当前未经改写的 `_OBSERVER_SCRIPT`，只运行同一解释器的 `-c pass`，不进入 CLI 下载或网络请求；baseline 从 `297bfbbc67b7d7468e3dfb6669a3385c4dd10d18` archive 取源码，确认其中无独立 egg-info/dist-info。将本轮真实 wheel 的 metadata 复制到全新的临时路径模拟解析，不写入 `.venv`、不安装。

| 真实 observer 场景 | 源码来源与断言事实 | 实际 metadata 观测 |
|---|---|---|
| baseline 源码 + 临时真实 wheel metadata | `code_root` 为 archive 目录；七个 producer 路径/hash 正确；`download_version=sec_pipeline_download_v1.2.0`；源码声明仍为 `0.1.4` | `0.1.5`，正确 baseline 源码与不同包 metadata 同时存在 |
| current 源码 + 同一临时真实 wheel metadata | `code_root` 为本仓；七个 producer 路径/hash 正确；`download_version=sec_pipeline_download_v1.3.0`；源码声明为 `0.1.5` | `0.1.4`，查询仍先解析本树旧 egg-info |

子进程的 argv、cwd、非敏感 `PYTHONPATH`、真实退出及完整双通道分别保存在 `observer-baseline.*` / `observer-current.*`；原始 observer 记录为对应 `*.jsonl`，汇总为 `offline-probe.json`。这是路径解析与源码 provenance 的独立事实演示，**不证明实际安装 0.1.5 成功**。错误比较的消除和真正源码断言的保留由实际源码差异/AST 核对证明，不用伪造业务结果替代。

首次 label `offline-probe` 退出 `1`：临时探针误以为构建输入全部 tracked，在比对 ignored `dayu/.DS_Store` 时找不到对应 tracked 快照。首次脚本 `offline_probe.attempt-1.py` 和全部失败输出保留。仅将临时探针改为保存并核验完整实际构建输入；被验证测试、版本声明、wheel 测试及生产源码均未修改，随后成功。没有通过删除包文件或放宽生产/测试断言处理该探针错误。

### 已有安装 metadata 未改变与最终一致性

`metadata-before.sha256.json` / `metadata-after.sha256.json` 对本树 egg-info 和本 `.venv` 的 dayu-agent dist-info 共 15 个文件核对：文件集合及每个 SHA-256 完全相同。直接读取 `.venv/lib/python3.11/site-packages/dayu_agent-0.1.4.dist-info` 的既有记录仍为 `0.1.4`，原始 `installed.METADATA` 与 `metadata-unchanged.json` 已保存；其 METADATA SHA-256 为 `8084f3b8ae20efebb23be5baf7408b64e7d4c6942063cd5c7503e78ecce35624`。这只证明本轮未改已有安装，不是新版本验收。

label `final-consistency` 执行 `final_verify.py`，记录当前 HEAD、895 文件源码快照/真实构建输入/wheel/报告 hash、原报告不变、metadata 集合与指纹不变、`git diff --check`、production 零差异及最终状态。各命令输出与真实退出保存在证据根；整体退出 `0`。源码在本轮测试和 pyright 后没有变化。

## README 决策、未覆盖项与接续

修改前已读 `tests/README.md` 开篇职责及真实 CLI、wheel 对应说明。本轮修正现存测试职责，属于该 README 读者范围；没有改变用户安装命令、产品入口或运行工作流，没有其它层 README 的职责变更。原版本实施报告保留，不覆盖；主控过程与独立审核报告不修改。

| 事项 | 分类、owner 与 destination |
|---|---|
| V1 错误版本比较及 README 固化错误职责 | `fixed in current slice`（实现和本轮验证事实，尚待独立复审核销）；owner：真实 CLI provenance 测试；destination：主控既定双路窄复审，不由 writer 宣布审核通过。 |
| 增量核收、后续实际安装及 sync to live 后版本核对 | `covered by later approved slice`；owner：主控/portfolio-manager 的 sync 接续。保留用户最新“升级后重新sync to live后对就行”；安装仍须增量核收并明确通知，本轮未安装、未 sync、未查调用方环境。wheel 与源码版本不能替代安装结果。 |
| SEC opt-in 真实网络矩阵 | `assigned to later work unit`；owner：Fins 真实 CLI 验收负责人；destination：后续显式安排的网络验收，不作为本次 V1 的新增门槛。 |
| 隔离构建手工输入清单的未来扩展维护 | `assigned to later work unit`；owner：CLI packaging test 维护者；destination：实际构建配置扩展时同步核验，沿用主控已有裁决，本轮无新增缺件反例。 |
| 原 S1 供应商接受度 | `assigned to later work unit`；owner：Provider/Engine 与 portfolio-manager；destination：既定调用方后续补验，维持原非阻塞 defer，不重开 R1–R3。 |

下一入口：主控以本报告、准确源码快照、实际 diff、真实 wheel 和原始命令证据安排 V1 受影响面双路窄复审，维护最终 finding 状态。提交、push、修改 PR、安装、sync 和交付核对均未由本 writer 执行。
