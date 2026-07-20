# WU-SEMANTIC-OWNERSHIP-01 / R11 upload-script placeholder removal plan — Adversarial Plan Review (MiMo)

## 1. Reviewed target and scope

- **Plan artifact**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **Artifact lock**: 711 lines / 52,389 bytes；SHA-256 `c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5`
- **Baseline**: branch `phaseflow/host-issues-control`，HEAD `2b14b2fbc89654267e3d33daa2ae410ceff45e68`，staged tree empty
- **Scope**: 对 R11 plan 做第一路完整 adversarial plan review，覆盖 owner 唯一性、OLD classification、CLI grammar、Windows 可执行性、placeholder deletion、wheel scan、sequencing、validation gates 等全部攻击面
- **Authority order**: AGENTS.md → 设计真源 → Controller discussion Topic 7 → umbrella remediation plan → phaseflow umbrella optimization control → Controller control → CURRENT code/tests/README → OLD files

## 2. Assumptions tested

1. Fins batch owner 未拥有完整 OLD-aligned domain facts（已验证：当前 `upload_batch.py` 只有 generic entries/path-only skips）
2. CLI 输出 JSON argv protocol 而非 executable script（已验证：`fins.py:70-72` 定义 `_UPLOAD_BATCH_SCHEMA_VERSION = 1`）
3. CLI action 默认为 `create` 而非 `auto`（已验证：`arg_parsing.py:904` `default="create"`）
4. placeholder packages 仍存在（已验证：`dayu/web/`, `dayu/wechat/`, `dayu/render/` 均有 tracked files）
5. `.github/workflows/` 不存在（已验证：目录不存在）
6. `FmpCompanyInfoResolver` 存在且可消费（已验证：`dayu/fins/resolver/fmp_company_info.py:98`）
7. `requirements.txt` 仍消费 `[web]` extra（已验证：`requirements.txt:12` `-e .[test,dev,browser,web]`）

## 3. Findings

### 01-未修复-中-action auto 默认值变更的 backward compatibility 风险

- **位置**: §6.2 条 2、§3.2 条 3
- **问题类型**: 契约缺失 / backward compatibility
- **当前写法**: Plan 要求将 `FILING_ACTION_CHOICES` 改为 `auto|create|update|delete`，`BATCH_UPLOAD_ACTION_CHOICES` 为 `auto|create|update`，所有 upload parser default 改为 `auto`。生成 entry 为 `auto` 时省略 `--action`。
- **反例/失败场景**: 当前 CLI 用户已习惯默认 `create` 行为。改为 `auto` 后，现有脚本/用户未传 `--action` 时行为会变化（`auto` 会调用 Service 的 auto-detect 逻辑，可能对已有文档执行 update 而非 create）。这不是 bug，但需要明确告知用户行为变化。
- **为什么有问题**: plan 没有说明如何处理这个行为变化。如果 Service 的 `auto` 逻辑对已有 ticker 的文档执行 update，现有用户未传 `--action` 的脚本行为会变化。
- **直接证据**: `arg_parsing.py:904` `default="create"`；plan §6.2 条 2 要求改为 `default="auto"`
- **影响**: 用户未显式传 `--action` 的现有脚本行为变化；可能不是 blocker 但需要在 README/changelog 中说明
- **建议改法和验证点**: 在 README 中明确说明默认行为从 `create` 变为 `auto`；或保留 `create` 作为 default 但允许 `auto` 作为 choice。验证：检查 Service `auto` 逻辑对已有文档的实际行为。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-高-Windows cmd.exe quoting algorithm 的可实现性存疑

- **位置**: §6.5
- **问题类型**: 非最优方案 / 可实现性风险
- **当前写法**: Plan 要求实现一个 Windows renderer，能处理 `% ! & | ^ ( )`、quotes、backslashes、Unicode、empty args，且不使用 `subprocess.list2cmdline`。Plan 承认"具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定"，要求实现时先写对抗矩阵再实现候选算法。
- **反例/失败场景**: Windows `cmd.exe` 的 quoting 规则极其复杂且文档不完整。`%` 需要 `%%` 转义（但只在 batch 文件中），`!` 在 delayed expansion 开启时有特殊含义，`& | ^ ( )` 是 metacharacter 需要 `^` 转义，`"` 的嵌套规则不直观。Plan 要求"单一算法"覆盖所有这些 case，且必须通过真实 `cmd.exe` 验证，但没有给出任何算法 sketch 或已知可工作的参考实现。
- **为什么有问题**: 这是整个 plan 中技术风险最高的部分。Windows batch quoting 是已知的"坑"，很多成熟工具（如 Python 自己的 `subprocess.list2cmdline`）都有已知 edge case。Plan 要求"禁用 `list2cmdline`、禁用 fallback、禁用双算法"，但没有给出任何可工作的替代方案。
- **直接证据**: §6.5 "具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定"；§6.5 "禁止 compat/fallback/双算法/platform test shim"
- **影响**: 实现 agent 可能无法找到满足所有 edge case 的单一算法，导致反复迭代或最终不得不使用 `list2cmdline`（违反 plan constraint）
- **建议改法和验证点**: 考虑先允许使用 `list2cmdline` 作为 baseline，再通过真实 `cmd.exe` 测试验证其是否满足 edge case。如果 `list2cmdline` 不满足，再实现自定义算法。验证：先用 `list2cmdline` 跑完整对抗矩阵，记录哪些 case 失败。
- **修复风险（低/中/高）**: 高
- **严重程度（低/中/高/严重）**: 高

### 03-未修复-中-Windows workflow 的 trigger paths 可能过于宽泛

- **位置**: §7.2
- **问题类型**: 最佳实践偏离
- **当前写法**: Workflow trigger `pull_request.paths` 精确列出 §4 closed product allowlist 中所有文件。Plan 要求"不得使用更宽 glob"。
- **反例/失败场景**: §4 allowlist 包含 20+ 个具体文件路径。如果任何文件被重命名或移动，workflow trigger 会失效但不会报错。此外，如果新增文件属于同一 semantic scope 但路径不同，workflow 不会触发。
- **为什么有问题**: 这是一个 trade-off：精确路径 vs 语义范围。Plan 选择了精确路径，但这意味着 allowlist 变化时必须同步更新 workflow trigger。
- **直接证据**: §7.2 "trigger `pull_request.paths` 精确列出 §4 closed product allowlist"
- **影响**: 低——allowlist 在 plan 中是固定的，implementation 完成后不会频繁变化
- **建议改法和验证点**: 可以接受，但应在 workflow 文件中注释说明 trigger paths 必须与 allowlist 同步。验证：实现时检查 trigger paths 是否完整覆盖 allowlist。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-中-Fins batch plan 的 `auto` action 省略 `--action` 可能导致歧义

- **位置**: §6.2 条 2
- **问题类型**: 契约缺失
- **当前写法**: Plan 要求"生成 entry 为 `auto` 时省略 `--action`"，即脚本中不写 `--action auto`。
- **反例/失败场景**: 当前 CLI parser 的 `--action` 参数没有 `auto` choice（只有 `create|update|delete`）。如果脚本省略 `--action`，CLI 会使用 default。但如果 default 改为 `auto`（§6.2 条 2 要求），那么省略 `--action` 等价于 `--action auto`。然而，如果用户手动生成脚本时想显式写 `--action auto`，当前 parser 会拒绝。
- **为什么有问题**: Plan 要求两个看似矛盾的 things：(1) 将 `auto` 加入 choices，(2) 生成 `auto` entry 时省略 `--action`。这实际上是自洽的——省略是因为 default 就是 `auto`。但需要确保 parser 确实接受 `--action auto`（如果用户手写）。
- **直接证据**: §6.2 条 2 "`FILING_ACTION_CHOICES` 改为 `auto|create|update|delete`"；"生成 entry 为 `auto` 时省略 `--action`"
- **影响**: 低——实现时只需确保 parser choices 包含 `auto` 且 default 为 `auto`
- **建议改法和验证点**: 确认 parser 确实接受 `--action auto` 且 default 为 `auto`。验证：测试 `--action auto` 和省略 `--action` 的行为一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 05-未修复-高-Fins structured auto-recursion 的判断规则可能过度依赖 OLD

- **位置**: §5.2 条 2
- **问题类型**: 过度耦合 / OLD 依赖
- **当前写法**: Plan 要求"用户 `--recursive` 或顶层存在 OLD structured directory `20YY` / `20YYQ1..Q4` / `20YYH1` 时 effective recursive"。即自动检测目录名是否包含年份/季度模式来决定是否递归。
- **反例/失败场景**: 这个规则来自 OLD 的目录结构习惯。但当前项目可能没有这种目录结构。如果用户目录恰好有 `2024` 子目录但不是财报目录，auto-recursion 会扫描无关文件。
- **为什么有问题**: Plan 把 OLD 的目录结构习惯硬编码为 auto-recursion 触发条件。这可能对当前项目不适用，且用户可能不知道这个隐式行为。
- **直接证据**: §5.2 条 2 "顶层存在 OLD structured directory `20YY` / `20YYQ1..Q4` / `20YYH1` 时 effective recursive"
- **影响**: 中——可能导致意外递归扫描，但不会产生错误结果（只会扫描更多文件）
- **建议改法和验证点**: 考虑只在用户显式 `--recursive` 时递归，不自动检测。或者在 README 中明确说明 auto-recursion 触发条件。验证：测试含 `2024` 子目录但非财报目录的场景。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 06-未修复-中-Plan 没有说明 `--overwrite` 参数如何加入 `upload_filings_from` grammar

- **位置**: §6.2 条 6
- **问题类型**: 契约缺失
- **当前写法**: Plan 要求"`upload_filings_from` grammar 必须显式加入 `--overwrite`"。但当前 `arg_parsing.py:800-806` 的 `_register_upload_filings_from_command` 没有 `--overwrite` 参数。
- **反例/失败场景**: 实现 agent 需要修改 `arg_parsing.py` 添加 `--overwrite` 参数。Plan 应该明确说明这个新增参数的 type、default 和 help text。
- **为什么有问题**: Plan 要求新增参数但没有给出具体定义。实现 agent 需要自行决定参数设计。
- **直接证据**: §6.2 条 6 "为完成 current metadata 传播，`upload_filings_from` grammar 必须显式加入 `--overwrite`"；`arg_parsing.py:800-806` 无 `--overwrite`
- **影响**: 低——实现 agent 可以参考其他 upload command 的 `--overwrite` 定义
- **建议改法和验证点**: 在 plan 中明确 `--overwrite` 的 type (`store_true`)、default (`False`)、help text。验证：实现后测试 `--overwrite` 参数。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 07-未修复-中-Plan 没有说明 `--infer` 参数的具体实现

- **位置**: §6.2 条 4
- **问题类型**: 契约缺失
- **当前写法**: Plan 要求"`--infer` 只注册在 `upload_filings_from`"，传入时从 `FMP_API_KEY` 读取 key 并调用 `resolve_company_info(canonical)`。但没有说明 `--infer` 参数的 type（boolean? string?）、是否需要值、以及如何处理 key 缺失。
- **反例/失败场景**: 实现 agent 需要决定 `--infer` 是 `store_true` 还是接受一个值（如 provider URL）。Plan 说"从 `FMP_API_KEY` 显式读取"，但这意味着 `--infer` 只是一个 flag，不接受 key 作为参数。
- **为什么有问题**: Plan 的描述足够清晰（`--infer` 是 flag，key 从 env 读取），但没有明确写成参数定义。
- **直接证据**: §6.2 条 4 "`--infer` 只注册在 `upload_filings_from`。未传时零 resolver/env 访问；传入时 CLI 从 `FMP_API_KEY` 显式读取"
- **影响**: 低——实现 agent 可以推断出 `--infer` 是 `store_true`
- **建议改法和验证点**: 在 plan 中明确 `--infer` 的 type (`store_true`)、default (`False`)。验证：测试 `--infer` 有/无 `FMP_API_KEY` 的行为。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 08-未修复-低-Plan 的 `shlex.quote`/`shlex.join` 在 POSIX renderer 中的使用可能不适用于所有 shell

- **位置**: §6.4
- **问题类型**: 最佳实践偏离
- **当前写法**: Plan 要求 POSIX renderer 使用 `shlex.quote`/`shlex.join` 编码 argv。Header 是 `#!/usr/bin/env sh`、`set -eu`。
- **反例/失败场景**: `shlex.quote` 遵循 POSIX shell quoting 规则，但 `#!/usr/bin/env sh` 可能指向不同 shell（bash、dash、zsh 等）。大多数 POSIX shell 的 quoting 规则兼容，但某些 edge case（如 `!` 在 bash interactive mode）可能不同。
- **为什么有问题**: 这是一个已知的 trade-off。`shlex.quote` 是 Python 标准库中 POSIX quoting 的标准实现，对大多数场景足够。但 plan 应该明确说明这是 POSIX sh quoting，不是 bash-specific。
- **直接证据**: §6.4 "每个固定 argv 只由 renderer 使用 `shlex.quote`/`shlex.join` 编码"
- **影响**: 低——POSIX sh quoting 在绝大多数 shell 中兼容
- **建议改法和验证点**: 可以接受。验证：真实 `/bin/sh` recorder smoke 测试覆盖。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 09-未修复-中-Plan 的 wheel scan 可能漏检 `dayu.render` package-data

- **位置**: §7.3
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求 wheel `METADATA` 必须无 `Provides-Extra: web` 与 Streamlit requirement，`entry_points.txt` 只含真实 scripts，archive 中必须零 `dayu/web`、`dayu/wechat`、`dayu/render`。检查命令使用 `rg -n 'dayu-(web|wechat|render)' workspace/tmp/r11-wheel-extract/*.dist-info/entry_points.txt`。
- **反例/失败场景**: `pyproject.toml:130-137` 定义了 `dayu.render` 的 package-data mapping（`*.css`, `*.html`, `*.lua` 等）。删除 `dayu/render/` 目录后，这些 package-data 也应该从 wheel 中消失。但 plan 的 scan 只检查 `entry_points.txt` 和 `METADATA`，没有检查 wheel archive 中是否还有 `dayu/render/` 的非 `.py` 文件。
- **为什么有问题**: wheel archive 可能包含 `dayu/render/` 的 `.css`/`.html` 文件（如果 package-data mapping 没有被删除）。Plan 的 `rg` 命令只检查 `.py` importability，不检查非 `.py` 资源文件。
- **直接证据**: `pyproject.toml:130-137` `"dayu.render" = ["*.css", "*.html", "*.lua", "*.docx", "*.xlsx", "*.mmd"]`；§7.3 scan 命令
- **影响**: 中——wheel 可能包含不应发布的 render 资源文件
- **建议改法和验证点**: 在 wheel scan 中增加检查：`python -c "import zipfile; z=zipfile.ZipFile('...whl'); print([n for n in z.namelist() if 'dayu/render/' in n or 'dayu/web/' in n or 'dayu/wechat/' in n])"` 应输出空列表。验证：wheel extract 后检查目录结构。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 10-未修复-低-Plan 的 `test_public_package_entrypoints.py` 修改范围需要更精确

- **位置**: §7.1 条 4、§4
- **问题类型**: 契约缺失
- **当前写法**: Plan 要求"`test_public_package_entrypoints.py` 删除 placeholder 成功/失败/help contract，保留 Docling dependency/constraints 等真实 packaging tests"。但没有说明哪些 test function 是 placeholder，哪些是 real。
- **反例/失败场景**: 实现 agent 需要自行判断哪些 test 是 placeholder。如果判断错误，可能误删 real packaging tests。
- **为什么有问题**: Plan 应该列出需要删除的 test function 名称或 pattern。
- **直接证据**: §7.1 条 4 "`test_public_package_entrypoints.py` 删除 placeholder 成功/失败/help contract，保留 Docling dependency/constraints 等真实 packaging tests"
- **影响**: 低——实现 agent 可以读取 test 文件自行判断
- **建议改法和验证点**: 在 plan 中列出需要删除的 test function 名称或 pattern（如 `test_dayu_web_*`、`test_dayu_wechat_*`、`test_dayu_render_*`）。验证：实现后检查 test file 的 diff。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 11-未修复-中-Plan 的 POSIX real upload smoke 可能依赖外部 fixture

- **位置**: §6.6
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求"在 `workspace/tmp/r11-posix-real` 复制现有 AAPL HTML fixture 并命名为 OLD 可识别的 filing/material 文件"。
- **反例/失败场景**: Plan 假设"现有 AAPL HTML fixture"存在。如果当前仓库没有这个 fixture，测试会失败。
- **为什么有问题**: Plan 没有说明 fixture 的具体路径或如何获取。
- **直接证据**: §6.6 "在 `workspace/tmp/r11-posix-real` 复制现有 AAPL HTML fixture"
- **影响**: 中——如果 fixture 不存在，实现 agent 需要创建或找到替代
- **建议改法和验证点**: 明确 fixture 路径（如 `tests/fixtures/` 或 `workspace/` 下的某个文件）。或者说明如何创建 minimal fixture。验证：实现前检查 fixture 是否存在。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 12-未修复-低-Plan 的 coverage 要求可能不适用于新增文件

- **位置**: §8.2
- **问题类型**: 最佳实践偏离
- **当前写法**: Plan 要求"每个 changed production Python file 的 line coverage `>=80%`"，包括新增 `dayu/cli/upload_script.py`。
- **反例/失败场景**: 新增文件的 coverage 容易达到 80%（因为可以从零开始写 tests）。但这不是问题。真正的问题是：如果新增文件的某些 edge case 很难测试（如 Windows quoting 的 edge case），80% 可能需要大量测试代码。
- **为什么有问题**: 这是一个合理的 coverage 目标，但 plan 应该说明 edge case 的处理方式。
- **直接证据**: §8.2 "每个 changed production Python file 的 line coverage `>=80%`"
- **影响**: 低——80% 是合理的 coverage 目标
- **建议改法和验证点**: 可以接受。验证：实现后检查 coverage report。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 13-未修复-中-Plan 没有说明如何处理 `dayu/render/` 的 `__pycache__` 目录

- **位置**: §7.1 条 3、§4
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求删除 `dayu/render/__init__.py`、`dayu/render/render.py`。但 `dayu/render/` 目录下还有 `__pycache__/` 目录（已验证）。
- **反例/失败场景**: 删除 `.py` 文件后，`__pycache__/` 目录可能残留。这不会影响功能，但会让 `git ls-files dayu/render` 输出不干净（因为 `__pycache__` 通常在 `.gitignore` 中）。
- **为什么有问题**: Plan 的 scan 命令 `git ls-files dayu/web dayu/wechat dayu/render` 只检查 tracked files。如果 `__pycache__` 在 `.gitignore` 中，它不会出现在 output 中。但如果不在 `.gitignore` 中，它会残留。
- **直接证据**: `ls -la /Users/leo/workspace/dayu-agent-r/dayu/render/` 显示 `__pycache__` 目录存在
- **影响**: 低——`__pycache__` 通常在 `.gitignore` 中，不会被 track
- **建议改法和验证点**: 在删除 `.py` 文件时同时删除 `__pycache__/` 目录。验证：`git ls-files dayu/render` 输出为空。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 14-未修复-中-Plan 的 `git diff --name-status` 检查可能遗漏 rename 操作

- **位置**: §8.3
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求"`git diff --name-status` 必须逐项等于 §4 closed allowlist 的实际变更子集"。
- **反例/失败场景**: 如果实现 agent 使用 `git mv` 重命名文件，`git diff --name-status` 会显示 `R100`（rename）。Plan 的 allowlist 没有说明如何处理 rename。
- **为什么有问题**: Plan 的 allowlist 列出的是"删除"和"新增"文件，没有考虑 rename。如果实现 agent 意外地 rename 了某个文件，`git diff --name-status` 的 output 会与 allowlist 不匹配。
- **直接证据**: §8.3 "`git diff --name-status` 必须逐项等于 §4 closed allowlist 的实际变更子集"
- **影响**: 低——R11 不涉及 rename 操作（只有 delete 和新增）
- **建议改法和验证点**: 在 plan 中明确说明 R11 不涉及 rename，任何 rename 操作都是错误。验证：`git diff --name-status` 不应包含 `R` 操作。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 15-未修复-低-Plan 的 `DisableDelayedExpansion` 正向 scan 可能过于宽泛

- **位置**: §8.3
- **问题类型**: 最佳实践偏离
- **当前写法**: Plan 要求"`DisableDelayedExpansion` 是正向命中"，即 scan 命令 `rg -n 'setlocal DisableDelayedExpansion' dayu/cli/upload_script.py tests/cli/test_upload_filings_from_command.py` 应该有输出。
- **反例/失败场景**: 如果实现 agent 在 renderer 中使用 `setlocal DisableDelayedExpansion` 但在 test 中不使用（因为 test 可能 mock renderer），scan 可能只命中一处。
- **为什么有问题**: Plan 的 scan 命令假设两处都有 `DisableDelayedExpansion`。但 test 可能不直接包含这个字符串（如果 test 使用 renderer 的 output 而不是 raw batch content）。
- **直接证据**: §8.3 scan 命令
- **影响**: 低——实现 agent 可以确保两处都有这个字符串
- **建议改法和验证点**: 可以接受。验证：实现后运行 scan 命令。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 4. Rejected / no-action observations

### R1-拒绝-plan 是否偷偷依赖 push/PR

- **观察**: Plan 多次强调"不授权 push/PR"，Windows gate 标为 `PENDING_RELEASE_BLOCKER`。Plan 没有偷偷依赖 push/PR。
- **结论**: 无问题。Plan 正确地将 push/PR 排除在 implementation scope 之外。

### R2-拒绝-plan 是否依赖 unified auth 或 Issue 142/151/175/177/178/R12

- **观察**: Plan §3.3 明确列出 deferred/no-touch 范围，包括 Issue 142、151、175、177、178、R12、统一 auth。Plan 没有依赖这些。
- **结论**: 无问题。Plan 正确地将这些排除在 scope 之外。

### R3-拒绝-plan 是否依赖 fallback/test shim

- **观察**: Plan §6.5 明确"禁止 compat/fallback/双算法/platform test shim"。
- **结论**: 无问题。Plan 正确地禁止了 fallback 和 shim。

### R4-拒绝-OLD classification 的 priority/caps 规则是否过于复杂

- **观察**: Plan §5.2 条 8-10 定义了复杂的 priority/caps 规则。这些规则来自 OLD，可能对当前项目过于复杂。
- **结论**: 这是 plan 的设计选择，不是 finding。Plan 已经明确这些规则来自 OLD 且是产品需求。

### R5-拒绝-plan 的 3-slice sequencing 是否合理

- **观察**: Plan 定义了 S1 (Fins batch owner) → S2 (CLI/renderer) → S3 (placeholder/packaging) 的顺序。这是 dependency-driven 的顺序，合理。
- **结论**: 无问题。sequencing 符合 dependency order。

## 5. Open questions

### Q1-Windows quoting algorithm 的具体实现策略

- **问题**: Plan 要求"禁用 `list2cmdline`、禁用 fallback、禁用双算法"，但没有给出任何可工作的替代方案。实现 agent 如何找到满足所有 edge case 的单一算法？
- **建议**: Controller 应该在 implementation 前明确：是否允许先用 `list2cmdline` 作为 baseline，再通过真实 `cmd.exe` 测试验证？如果 `list2cmdline` 满足所有 case，是否可以接受？

### Q2-POSIX real upload smoke 的 fixture 来源

- **问题**: Plan 假设"现有 AAPL HTML fixture"存在，但没有说明路径。
- **建议**: Controller 应该在 implementation 前确认 fixture 路径，或者说明如何创建 minimal fixture。

### Q3-`--overwrite` 和 `--infer` 的参数定义

- **问题**: Plan 要求新增这两个参数，但没有给出具体定义。
- **建议**: Controller 应该在 implementation 前明确参数的 type、default、help text。

## 6. Residual risks

| Risk | Severity | Owner | Destination |
|------|----------|-------|-------------|
| Windows quoting algorithm 可实现性 | 高 | implementation agent | R11-S2 实现 |
| action auto 默认值变更的 backward compatibility | 低 | README | R11-S3 README 更新 |
| Fins structured auto-recursion 可能过度依赖 OLD | 中 | implementation agent | R11-S1 实现 |
| wheel scan 可能漏检 package-data | 中 | implementation agent | R11-S3 wheel scan |

## 7. Final plan review conclusion

**Verdict: PASS-WITH-RISKS**

Plan 整体结构合理，owner 边界清晰，dependency order 正确，validation gates 完整。主要风险集中在：

1. **Windows quoting algorithm 的可实现性**（高风险）：Plan 禁用了所有已知的 fallback 机制，但没有给出任何可工作的替代方案。这是整个 plan 中技术风险最高的部分。
2. **Fins structured auto-recursion**（中风险）：OLD 的目录结构习惯可能对当前项目不适用。
3. **wheel scan 完整性**（中风险）：可能漏检 `dayu.render` 的 package-data 文件。

建议 Controller 在 implementation 前对 Q1（Windows quoting strategy）做出明确裁决。其他 finding 均为低风险，实现 agent 可以在 implementation 过程中自行处理。

---

**Reviewer**: AgentMiMo
**Review timestamp**: 20260717-213434
**Reviewed artifact SHA-256**: c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5

READY_FOR_CONTROLLER_ADJUDICATION
