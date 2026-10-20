# PR206 版本 0.1.5 增量：实现与验证

## 范围、版本与当前状态

本轮是已核收 R1–R3 head `f854a6e6ff3e3a1cee24745eaae96148843d6401` 上的单个版本增量 slice。工作分支为 `fix/public-original-read-r1-r3-20261020`；依据 [主控已批准的最小计划](public-original-read-r1-r3-20261020-version-increment.md) 和 [授权记录](public-original-read-r1-r3-20261020-authorization-update.md)，仅完成实现与必要验证，交回主控进入本增量的独立代码审核。本报告不宣称 review-pass、draft-PR-pass 或 final closeout pass。

动机成立：`pyproject.toml` 的 `[project].version` 原为 `0.1.4`，现需发布 `0.1.5`；真实 SEC CLI observer 已查询 distribution metadata，断言却固定为 `0.1.4`，会在正确升级后误拒绝。正确修复是让测试按对应源码声明判断实际 metadata，不能另建版本常量或将观察值替换成期望值。

本轮未修改 production Python，未重开 R1–R3 实现或全业务回归。未安装本包、提交、push、merge、修改 PR 或发送 tmux 消息；未访问调用方或 OLD 运行环境。版本基线只从指定 Git commit 读取源码声明。主控维护的 control、authorization、increment 记录以及旧 review、冻结 goal 均未由本 writer 修改。

## 实际改动与 owner

| 文件 | 改动及语义 owner |
|---|---|
| `pyproject.toml` | 唯一版本 owner `[project].version` 从 `0.1.4` 改为 `0.1.5`；setuptools 继续负责由该声明生成 distribution metadata。 |
| `tests/fins/test_sec_html_image_assets_real_cli.py` | observer 继续使用 `importlib.metadata.version("dayu-agent")` 观察实际版本；移除固定 `0.1.4` 断言，模块级 `_assert_package_version` 读取对应 baseline/current 源码的 `pyproject.toml`，严格比较观察值与声明，错版即失败，无 fallback。baseline 选择及七个生产 owner 的源码身份检查保持原行为。新增函数含中文参数、返回值、异常说明及完整类型签名。 |
| `tests/cli/test_public_package_entrypoints.py` | 复用原真实 wheel 测试，从 pytest 独立目录内的源码副本构建，避免本树 egg-info 被构建改写；解析真实 wheel `METADATA` 的 `Name`、`Version`，与 `pyproject.toml` 比较，保留原公开入口和 placeholder 排除断言。保存内部构建命令、退出码和完整双通道。没有新增镜像版本字面量测试。 |
| `tests/README.md` | 在既有真实 CLI、包入口测试说明中补充版本同源核对、错版失败和隔离构建的当前行为。 |

没有新增 `__version__`、`dayu-cli --version` 或平行版本真源；`dayu-cli = dayu.cli.__main__:exit_module` 不变。

## 可取回源码与 wheel

独立证据根目录（下文相对证据文件均位于此处）：

`workspace/tmp/public-original-read-r1-r3-20261020/version-implementation-20261020T082024334543Z/`

- `source-snapshot/` 保存 500 个文件的准确字节，包括完整构建输入 `dayu/`、`pyproject.toml`、`README.md`、`LICENSE`，以及受影响测试、测试 README、约束和类型检查配置；`source-snapshot.sha256.json` 为逐文件 SHA-256 清单，其自身 SHA-256 为 `142badc015aa17f548ea203d3be4f26832e22b4abec66df79b98c0b6cef2d200`。指纹用于核对，保存的文件用于取回版本。
- `head`、`branch`、`slice.diff` 保存基准身份与本轮源码差异；`production.diff` 为空，确认 production Python 未变。`baseline-pyproject.toml` 来自 `297bfbbc67b7d7468e3dfb6669a3385c4dd10d18:pyproject.toml`，`accepted-head-pyproject.toml` 来自已核收 HEAD；两者声明均为 `0.1.4`。
- 保留 wheel：`pytest-tmp/test_wheel_excludes_placeholde0/wheel/dayu_agent-0.1.5-py3-none-any.whl`，大小 `2676445` 字节，SHA-256 `e012225e91931b2dd46c1776c45f7cce261c7105e86c5d118a81bb4644a63625`。
- 构建副本：`pytest-tmp/test_wheel_excludes_placeholde0/source/`。补充探针逐字核对该副本的构建输入与保存快照一致，wheel 内 478 个 `dayu/` 文件与快照一致；并保存原始 `wheel.METADATA` 与 `wheel.entry_points.txt`。实际 `Name: dayu-agent`、`Version: 0.1.5`，公开入口仍为上述 target。

## 验证命令、退出码与完整输出

外层验证由证据目录内的 `record_command.py` 记录：每个 label 对应 `*.command.json`（完整 argv/cwd）、`*.execution.json`（真实退出码及 UTC 起止时间）、`*.stdout`、`*.stderr`（未截断双通道）。未以摘要替代 raw 输出。

### 受影响测试

仓库根 cwd 下实际执行：

```bash
source .venv/bin/activate && env -u DAYU_SEC_IMAGE_REAL_VALIDATION PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 python -m pytest -q -rs tests/cli/test_public_package_entrypoints.py tests/fins/test_sec_html_image_assets_real_cli.py --basetemp /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/version-implementation-20261020T082024334543Z/pytest-tmp
```

label `affected-tests`，退出 `0`：`4 passed, 2 skipped, 3 warnings in 6.99s`。四个包入口测试通过，包括真实 wheel 构建及新增实际 metadata 同源断言；三个 warning 是既有 edgartools 弃用提示。两个 SEC 网络用例因未启用 opt-in 明确 skip，**不构成真实网络验收**，不重跑既核收业务矩阵。

wheel 测试内部实际命令如下，cwd 为前述独立构建副本 `source/`，退出 `0`：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/version-implementation-20261020T082024334543Z/pytest-tmp/test_wheel_excludes_placeholde0/wheel .
```

内部完整证据为 `pytest-tmp/test_wheel_excludes_placeholde0/build.command.json`、`build.stdout`、`build.stderr`。构建使用现有 backend，不安装项目或依赖，不联网拉取构建依赖。pip 报用户 cache 目录不可写并禁用 cache，构建仍成功；未提权或改变该环境。

### 全量 pyright

```bash
source .venv/bin/activate && pyright
```

label `pyright`，退出 `0`：`0 errors, 0 warnings, 0 informations`，使用仓库现有配置检查 `dayu/`、`tests/`、`utils/`。stderr 只有 pyright 新版本通知，未执行升级。没有通过忽略、放宽配置或类型绕过掩盖错误。没有修改 production Python，按本轮约束不增加无意义 coverage。

### 实际 metadata 正例、错版拒绝与快照一致性

仓库根 cwd 下实际执行（最终成功的一次）：

```bash
source .venv/bin/activate && python workspace/tmp/public-original-read-r1-r3-20261020/version-implementation-20261020T082024334543Z/metadata_probe.py
```

label `metadata-probe-2`，退出 `0`，详细结果为 `metadata-probe.json`。探针实际调用修改后的测试 helper，使用真实 wheel metadata 和本环境既有安装 metadata，不伪造版本观察值：

1. wheel 的实际 `0.1.5` 对 current 源码声明：通过。
2. 既有安装 metadata 的实际 `0.1.4` 对指定 baseline 源码声明：通过。
3. 实际 wheel `0.1.5` 对 baseline 的 `0.1.4`：断言拒绝。
4. 实际既有安装 metadata `0.1.4` 对 current 的 `0.1.5`：断言拒绝。

该探针也核对全部保存源码、构建输入、wheel 包文件，以及本树 egg-info 和本环境已有 dist-info 的前后 SHA-256；全部一致，见 `metadata-before.sha256.json`、`metadata-after.sha256.json`。这是离线版本判断验证，不代表 SEC 下载网络矩阵已执行。

首次 label `metadata-probe` 退出 `1`：探针把 pytest 的 `...current` 目录符号链接与实体目录误计为两个 wheel，在检查产物数量时即失败。只修正临时探针为按 resolve 后路径去重，再运行上述成功命令。首次完整日志及失败脚本 `metadata_probe.attempt-1.py` 保留；未修改包或测试源码来迁就该探针。

### 版本查询及 cwd 影子来源

实际查询核心为 `importlib.metadata.version("dayu-agent")` 与 `python -m pip show dayu-agent`；使用同一 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`，每次先 `source .venv/bin/activate` 再切换下表 cwd。查询同时输出 cwd 和解释器，完整命令及双通道见 `query-repo`、`query-neutral`、`query-build-source` 各自记录。额外 `origin-repo`、`origin-neutral`、`origin-build-source` 均退出 `0`，用 public `distribution().locate_file("")` 及实际 metadata 文件存在性核对来源。

| 查询 cwd | importlib.metadata.version | importlib 实际来源 | pip show |
|---|---|---|---|
| 仓库根 | `0.1.4` | 本树 `dayu_agent.egg-info/PKG-INFO` | `0.1.4`，Location 为本 `.venv/lib/python3.11/site-packages`，Editable project location 为本仓库 |
| 本证据根下空目录 `query-cwd/` | `0.1.4` | 本 `.venv` 的 dist-info/METADATA | 同上 |
| 独立构建副本 `source/` | `0.1.5` | 该副本构建生成的 `dayu_agent.egg-info/PKG-INFO` | 仍为既有安装 `0.1.4`，Location 为本 `.venv` |

三组查询均退出 `0`。独立构建 cwd 的 importlib 结果是源码 metadata 影子，**不是已安装 0.1.5 的证据**；仓库根的查询也须区分源码 egg-info。另通过 `importlib.metadata.Distribution.at()` 明确读取本 `.venv/lib/python3.11/site-packages/dayu_agent-0.1.4.dist-info`，确认实际安装记录为 `0.1.4`。该记录与本树 egg-info 的原始文件指纹未变；本轮只构建 wheel，**0.1.5 尚未安装**。后续安装验收须使用目标解释器、明确 cwd/metadata 来源与实际安装位置，不能把 pyproject 或 wheel 版本当安装结果。

最终 label `final-consistency` 退出 `0`，完整命令见其 `command.json`：执行 `git diff --check`、`git diff --exit-code HEAD -- dayu`、`git status --short` 及本证据目录的 `final_consistency.py`。确认 500 个源码/配置快照文件、15 个既有 metadata 文件及 wheel 均未漂移，HEAD 仍为已核收 head，并记录本报告 SHA-256 至 `final-consistency.json`。类型检查后没有改动已验证源码。

## README 决策

修改前已读取根 README 的 `Agent更新约束` 和测试 README 开篇职责。测试 README 面向现有测试分层、运行方式与维护，故仅补充受影响的版本和隔离构建行为。根 README 面向最终用户安装与操作，本轮没有改变安装命令、入口参数或工作流，现有 wheel `<version>` 占位适用，故不机械添加固定版本或内部验证过程。`dayu/` 及各业务层 README 无触发变更。

## 未覆盖项、风险 owner 与接续

| 事项 | 分类、owner 与 destination |
|---|---|
| 固定 `0.1.4` 断言误拒正确新版本；版本错配可能被忽略 | `fixed in current slice`：按对应声明比较，实际 metadata 的正反例均验证；owner 为测试 provenance 边界。 |
| 构建改写本树 metadata、或把源码影子版本当成安装版本 | `fixed in current slice`：构建隔离；原 metadata 指纹未变；来源分开记录，当前无安装成功声明。 |
| 安装 `0.1.5` 及安装后的公开入口核对 | `covered by later approved slice`：owner 为主控/portfolio-manager 的安装接续；须先核收本增量并明确通知安装，才按 README 从核收的精确源码执行。本 writer 当前无安装放行。 |
| SEC 两例 opt-in 真实网络矩阵未执行 | `assigned to later work unit`：owner 为 Fins 真实 CLI 验收负责人；destination 为后续显式安排的网络验收。本轮只验证变更后的版本判断与真实构建，不新增网络门槛。基线声明与 current 声明已不同，未来运行必须使各自实际 metadata 匹配，旧版/错版仍应失败，不以 fallback 补救。 |
| 原 S1 真实供应商接受度 | `assigned to later work unit`：沿用已批准计划的 Provider/Engine 与 portfolio-manager owner，destination 为调用方后续补验；本轮不扩大或改变既有结论。 |

下一入口：主控对本增量执行既定独立审核和裁决，随后由主控处理提交/push、同 draft PR206 更新及交付核对。本 writer 交付源码、准确快照、wheel 和本报告；这些后续 gate 仍未完成，安装继续等待明确授权。
