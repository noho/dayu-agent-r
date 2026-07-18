# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 第二路独立完整 Code Review（AgentDS）

## 1. Gate 身份

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- 本 artifact 是第二路（AgentDS）独立完整 code review，不是新 WU，不授权 S2/S3、fix、
  stage、commit 或 PR。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Accepted immutable plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，
  608 lines，SHA-256 `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- Controller validation artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md`，
  166 lines，SHA-256 `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19`。
- AgentCodex completion artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md`，
  248 lines，SHA-256 `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed`。

## 2. Review scope

### 2.1 完整读取的 artifacts

| 文件 | 读取状态 |
|---|---|
| `AGENTS.md`（项目指令，128 行） | 完整 |
| `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`（608 行） | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md`（166 行） | 完整 |
| `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md`（248 行） | 完整 |

### 2.2 逐行走读的 production/test 文件

| 文件 | 行数 | SHA-256 | 走读状态 |
|---|---:|---|---|
| `dayu/cli/init_catalog.py` | 854 | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | 完整逐行走读 |
| `dayu/cli/init_environment.py` | 570 | `754e441e0f7de9c0384375eb7e1924a459e68f406f8398216df2edc97fdde845` | 完整逐行走读 |
| `tests/cli/test_init_catalog.py` | 610 | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` | 完整逐行走读 |
| `tests/cli/test_init_environment.py` | 567 | `40f0d9b2a75545a19b18c3090fd578394ac83d3c404fc1e2b93a659e474b7111` | 完整逐行走读 |

### 2.3 排除范围

- Controller-owned `docs/host/issues-implementation-control.md`（有意 dirty，非 S1 scope）。
- 所有不在 S1 allowlist 的既有 production/test 文件（未修改，非本 review scope）。
- Package config、manifests、`models.json`（只读锚点，SHA 未漂移，非 S1 实现产物）。

### 2.4 并行 review 覆盖

本 review 是单 agent 完整独立执行，未使用 subagent 分片。所有四个 S1 文件均由同一 reviewer
完整逐行走读。

## 3. 独立机械验证

### 3.1 Focused tests

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

**结果**：exit `0`，`56 passed in 0.20s`。与 Controller 验证一致。

### 3.2 单文件覆盖率

```bash
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
```

**结果**：`276 statements / 27 miss / 90%` → `90.22%` ≥ 80%。通过。

```bash
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

**结果**：`226 statements / 13 miss / 94%` → `94.25%` ≥ 80%。通过。

### 3.3 Full pyright

```bash
python -m pyright dayu/ tests/ utils/
```

**结果**：`0 errors, 0 warnings, 0 informations`。通过。

### 3.4 Changed-path Ruff

```bash
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

**结果**：`All checks passed!`。通过。

### 3.5 Full Ruff immutable fingerprint

```bash
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
```

**结果**：raw exit `1`（预期）、count `144`、SHA-256
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`、
`cmp` vs baseline exit `0`（逐字节相同）。通过。

### 3.6 Git diff 与 scope

- `git diff --check`：exit `0`，无诊断。
- `git diff --cached --name-only`：空。
- `git status --short`：符合预期（control dirty + 四个 S1 untracked paths + 本 artifact）。

### 3.7 Source scans

| 扫描项 | 范围 | 结果 |
|---|---|---|
| Weak typing (`Any`, `object`, `hasattr`, `getattr`) | S1 production + tests | 零命中 |
| Legacy compat (`_init_model_role`, `default_name`, `compat`, `fallback`, `shim`) | S1 production + tests | 仅测试负断言命中 |
| Network client (`requests`, `httpx`, `socket`, `download`) | S1 production | 仅 `urllib.parse.urlsplit`（本地 URL 解析） |
| Runtime assembly (`prepare_entrypoint_runtime`, `open_host`, `asyncio.run`) | S1 production | 零命中 |
| Secret leak (`print`, `logging`) | S1 production | 零命中 |
| Unsafe shell (`shell=True`) | S1 production | 零命中 |

全部 source scans 通过。

## 4. Findings

### DS-R12-S1-01 — CRITICAL — `_parse_managed_block()` 全文 `content.count()` 对合法 quoted secret 的 marker 子串误判

**是否为 current accepted candidate**：是。Controller validation §5 已提出并授权两路 reviewer
独立裁决。本 finding 经独立复现确认为 accepted S1 correctness finding。

- **入口/函数**：`_parse_managed_block()` → `persist_environment()` → `_verify_written_profile()`
- **文件（行号）**：`dayu/cli/init_environment.py:457`
- **输入场景**：
  1. 用户提供一个满足 §5.1 所有 entry contract 的 secret（非空且不含 NUL、CR、LF），
     但其值包含 begin marker `# >>> dayu-cli init >>>` 或 end marker
     `# <<< dayu-cli init <<<` 的子串；
  2. Profile 已存在且包含恰好一对结构正确的 Dayu marker block（或不存在 block 需首次追加）；
  3. 用户已确认 persistence plan（`confirmed=True`）。
- **实际分支**：
  1. `_render_profile_content()` 调用 `_parse_managed_block(content)` 识别已有 block
     （行 415）——此时 content 是**旧** profile 文本，旧 block 不含 marker 子串值，
     所以 line-by-line 解析正确返回 `_ManagedProfileBlock`；
  2. `_render_managed_block()`（行 433）用 `shlex.quote(entry.value)` 把含 marker
     子串的 secret 渲染为 `export NAME='...marker...'`；
  3. `_write_profile_atomically()`（行 492）用 `os.replace` 原子发布新 profile；
  4. `_verify_written_profile()`（行 528）从磁盘重读新 profile，再次调用
     `_parse_managed_block(state.content)`（行 539）；
  5. **此时 `content` 已是新 profile 文本**，其中 `shlex.quote` 的输出包含 marker 子串；
  6. 行 457：`content.count(_DAYU_BLOCK_BEGIN) != len(begin_indexes)` 求值为 `True`
     ——全文 substring count 把 quoted value 内的 marker 也算进去了，而
     `begin_indexes`（行 455）是基于 `splitlines` + 逐行精确匹配，只统计了真正的
     独立 marker 行。count 不匹配 → 抛出 `EnvironmentPersistenceError`。
- **预期行为**：合法的 secret 值（不含 NUL/CR/LF）不应因 quoted 形式包含 marker
  子串而被拒绝。只要 profile 的 marker **结构**正确（零个或恰好一对 begin/end 在独立行上，
  无重叠、无多块），persistence 应成功，env 应注入当前进程。
- **实际行为**：Profile 已被 `os.replace` 原子替换（旧内容丢失），新内容在结构上完全正确
  （1 begin + 1 end + 合法 export 行），但 `_verify_written_profile` 的
  `content.count()` 检查误判"发现嵌入式 marker"，抛出异常。结果：
  - Profile 已变异（旧 secret 丢失，新 block 已在磁盘上）；
  - `os.environ` 未注入（defense-in-depth 仍然生效——行 262-264 的 `result.succeeded`
    检查阻止了注入）；
  - 用户收到错误报告，但被报告为"失败"的操作实际上已经修改了磁盘状态。
- **直接证据**：

  **复现脚本输出（独立于 Controller 执行）**：

  ```text
  Secret value: 'prefix # >>> dayu-cli init >>> suffix'
  Secret does NOT contain NUL/CR/LF (valid by §5.1)
  ERROR: POSIX profile contains an embedded Dayu init marker
  Profile exists: True
  Profile content:
  # >>> dayu-cli init >>>
  export OPENAI_API_KEY='prefix # >>> dayu-cli init >>> suffix'
  # <<< dayu-cli init <<<
  ```

  **代码证据链**：

  - 行 455：`begin_indexes = tuple(... if line == _DAYU_BLOCK_BEGIN)` — 逐行精确匹配，正确。
  - 行 456：`end_indexes = tuple(... if line == _DAYU_BLOCK_END)` — 逐行精确匹配，正确。
  - 行 457：`if content.count(_DAYU_BLOCK_BEGIN) != len(begin_indexes) or content.count(_DAYU_BLOCK_END) != len(end_indexes)` — **全文 substring count，过度宽泛**。

  **复现覆盖的五个场景**：

  | 场景 | secret 值 | 结果 | 应得结果 |
  |---|---|---|---|
  | begin marker 子串（quoted） | `'prefix # >>> dayu-cli init >>> suffix'` | 错误拒绝 | 应成功 |
  | end marker 子串（quoted） | `'prefix # <<< dayu-cli init <<< suffix'` | 错误拒绝 | 应成功 |
  | 精确等于 marker（quoted） | `'# >>> dayu-cli init >>>'` | 错误拒绝 | 应成功 |
  | 双引号中的 marker（quoted） | `"prefix # >>> dayu-cli init >>> suffix"` | 错误拒绝 | 应成功 |
  | 两个 marker 都在 quoted 值中 | `'begin ... and end ...'` | 错误拒绝 | 应成功 |
  | 正常值（无 marker 子串） | `my-normal-secret` | 成功 | 成功 |

  **Legitimate embedded-marker 检测（修复后必须保留）**：

  | 场景 | 内容 | 当前结果 | 修复后应保持 |
  |---|---|---|---|
  | Marker 嵌入非 marker 行 | `prefix # >>> dayu-cli init >>> embedded\n` | 正确拒绝 | 正确拒绝 |
  | Marker 出现在注释行 | `# >>> dayu-cli init >>> is a marker\n` | 正确拒绝 | 正确拒绝 |
  | 多块 | 两个完整 block | 正确拒绝 | 正确拒绝 |
  | 缺配对 | 只有 begin 无 end | 正确拒绝 | 正确拒绝 |

- **影响**：
  - **Correctness**：合法 secret 被错误拒绝，用户无法使用恰好包含 marker 字样的
    API key（如 `sk-# >>> dayu-cli init >>> -xxxx` 这类边缘但合法的 key 格式）。
  - **Data integrity**：Profile 已被 `os.replace` 原子替换，旧 secret 丢失且无法
    自动恢复（旧 profile 内容已被新内容覆盖）。虽然旧 block 的内容（旧 secret）也
    被替换是新 block 的预期行为，但错误消息误导用户认为"什么都没变"。
  - **Silent half-failure**：磁盘已写入但进程报告失败。用户若重试（修改 secret
    去掉 marker 子串），会发现 profile 中已有上一次的"失败"写入残留。
- **建议改法和验证点**：

  **Root cause**：`content.count()` 在全文范围内做子串搜索，无法区分独立 marker
  行和 quoted value 中的偶然子串匹配。

  **修复方向（owner-level 最小修复）**：将 `_parse_managed_block()` 中行 457 的
  `content.count()` 检查替换为按 `splitlines` + `rstrip("\r\n")` 归一化后的
  逐行子串扫描，且**跳过已识别为合法 export 行的行**。修改仅限于
  `dayu/cli/init_environment.py` 的 `_parse_managed_block()` 函数，不改变其公开
  契约（返回值与异常语义），不放宽真正的 malformed marker 结构检测。

  具体方案：

  ```python
  # 替换 行 457：
  # OLD:
  # if content.count(_DAYU_BLOCK_BEGIN) != len(begin_indexes) or \
  #    content.count(_DAYU_BLOCK_END) != len(end_indexes):
  #     raise EnvironmentPersistenceError("POSIX profile contains an embedded Dayu init marker")

  # NEW: 只对非独立 marker 行且非合法 export 行做子串扫描
  for idx, line in enumerate(normalized_lines):
      if idx in begin_indexes or idx in end_indexes:
          continue  # 真正的 marker 行，跳过
      if line.startswith(_EXPORT_PREFIX) and "=" in line:
          continue  # 合法 export 行可能包含 quoted marker 子串，跳过
      if _DAYU_BLOCK_BEGIN in line or _DAYU_BLOCK_END in line:
          raise EnvironmentPersistenceError(
              "POSIX profile contains an embedded Dayu init marker"
          )
  ```

  该修改：
  - 不再依赖 `content.count()` 的全文子串计数；
  - 仍然检测"marker 嵌入非 marker 行"（如注释行 `# >>> dayu-cli init >>> is a marker`）；
  - 不检测 quoted export value 内的偶然子串（因为 `line.startswith(_EXPORT_PREFIX) and "=" in line` 跳过）；
  - 不改变对缺失、多块、不配对、重叠 marker 结构的检测（行 461 的
    `len(begin_indexes) != 1 or len(end_indexes) != 1 or begin_indexes[0] >= end_indexes[0]` 不动）；
  - 不改变 `_parse_export_name` 对非法 export 行的检测（非法行不以
    `export ` 开头或不含 `=`，不会命中 skip 条件，子串检查仍生效）。

  **必需回归测试**：
  1. 新增：secret 含 begin marker 子串 + 已有 block → 成功，profile 正确替换，env 注入；
  2. 新增：secret 含 end marker 子串 + 首次创建 → 成功，profile 正确创建，env 注入；
  3. 新增：secret 同时含 begin/end 子串 + 双引号 → 成功；
  4. 保留现有：`test_malformed_marker_structures_fail_closed` 全部 5 个参数化场景
     仍必须拒绝；
  5. 保留现有：所有合法 persistence 测试仍通过；
  6. 新增：profile 有非 Dayu 注释含 marker 子串（如
     `# see # >>> dayu-cli init >>> docs`）→ 应拒绝（真正的嵌入式 marker）。

- **修复风险**：**低**。修改范围限于 `_parse_managed_block()` 内部实现的嵌入式检测
  逻辑，公开 API 不变。修复逻辑简单（逐行扫描 + 跳过 export 行），等价于把现有的
  `content.count()` 全局搜索收紧为带上下文的逐行搜索。
- **严重程度**：**严重（CRITICAL）**。
  - 直接违反 plan §5.2 的 marker **结构** owner（只应检测缺失/恰好一对/重叠/不配对/多块）；
  - 把合法 secret 错当成 malformed marker 结构拒绝；
  - 拒绝发生在 profile 已原子替换之后，用户收到错误但磁盘已变更；
  - plan §5.1 明确只拒绝空值/NUL/CR/LF，marker 子串不在合法拒绝集合中。

---

### DS-R12-S1-02 — 无 finding — InitModelSelection dataclass value equality 符合 value-object contract

**是否为 current accepted candidate**：否。经独立对抗检查，确认为无 finding。

- **审查入口**：`dayu/cli/init_catalog.py:358`
  ```python
  if self.choice not in INIT_MODEL_CHOICES:
      raise InitCatalogError(...)
  ```
- **审查方法**：构造语义完全相同的 value copy 和语义不同的 forged choice，验证
  `not in` 检查对两者的行为。
- **独立复现结果**：

  ```text
  Original is copy: False         # 不同 Python 对象
  Original == copy: True          # 值相等
  Original in INIT_MODEL_CHOICES: True
  Copy in INIT_MODEL_CHOICES: True   # 语义相同 → 通过 catalog membership
  InitModelSelection with copy: ACCEPTED (value-object contract holds)

  Forged == openai_original: False   # choice_id 不同
  Forged in INIT_MODEL_CHOICES: False
  Forged selection: REJECTED (correct)
  ```

- **裁决**：`InitModelChoice` 是 `@dataclass(frozen=True, slots=True)`。`__eq__`
  对所有字段做值比较。语义完全相同的 copy 通过 membership 检查是 value-object
  的正确行为——它表示"相同的选择内容"。语义不同的 forged choice（`choice_id`
  不同）被正确拒绝。无需引入 identity shim、registry 或 framework。

- **不满足 finding 条件**。不报告。

## 5. 补充 adversarial review

以下各项经过独立逐行走读和对抗测试，均未发现 material finding：

### 5.1 Catalog / model / manifest owner

| 检查项 | 结果 |
|---|---|
| 15 项选择顺序与 plan §4.1 精确对应 | 通过 |
| 13 静态 pair 通过真实 `ConfigLoader.load_models()` + extends resolver 校验 | 通过 |
| Package `ollama` template `provider=ollama`、`api_key_ref=None` | 通过 |
| Package 缺少 `custom-openai` 不是静态错误 | 通过 |
| Ollama record 复制完整 template，只替换 model/endpoint/context | 通过 |
| Custom record 完全匹配 plan §4.2 锁定的字段（headers、capabilities、timeout/retry/SSE、八 hints） | 通过 |
| 八 hints 精确匹配 plan §4.2 的 temperature/top_p/stream 投影 | 通过 |
| Dynamic 输入在 mutation 前拒绝空/外围空白/控制字符/非 HTTP(S) URL/非正整数/bool | 通过 |
| Dynamic record 写回后由真实 `ConfigLoader` 重载校验 | 通过 |
| 16 known manifest role 集合互斥、无交集、并集等于 package basenames | 通过 |
| Projection 只改写 `model.default_model_id`，保留其他字段 | 通过 |
| 用户自建 manifest 不被枚举或改写 | 通过 |
| 13 production / 3 test-owned manual-smoke 边界正确 | 通过 |
| 全部 16 个投影由 current `prepare_scene` 读取 | 通过 |
| Production 不含 `manual-smoke` catalog/fixture/provider 构造 | 通过 |

### 5.2 Environment persistence owner

| 检查项 | 结果 |
|---|---|
| Entry `value` 使用 `repr=False`（脱敏） | 通过 |
| Name 必须来自 allowlist（catalog + 五个 optional names） | 通过 |
| 空值、NUL、CR、LF 在 entry 构造时拒绝（含变量名，不含值） | 通过 |
| POSIX plan 只接受 `.zshrc` / `.bashrc` target | 通过 |
| 未确认 plan 拒绝执行（confirmed=False） | 通过 |
| Profile symlink / dangling symlink 拒绝（`is_symlink()` 优先检查） | 通过 |
| Profile 目录 / 非普通文件拒绝（`S_ISREG` 检查） | 通过 |
| 缺失 profile 以 `0600` 创建（通过 `_NEW_PROFILE_MODE` + `fchmod`） | 通过 |
| 已存在 profile 保留原 mode（`stat.S_IMODE`） | 通过 |
| `shlex.quote` 正确应用于所有值 | 通过 |
| 原子写入：同父目录 `mkstemp` → `fchmod` → `flush`/`fsync` → `os.replace` | 通过 |
| 写后从磁盘重读校验 marker/name/mode 结构 | 通过 |
| 写后校验失败时不注入 env | 通过 |
| 异常/result/captured output 不含 secret value | 通过 |
| Windows：`("setx", name, value)` argument tuple | 通过 |
| Windows：`shell=False`、`capture_output=True`、`text=False`、`check=False` | 通过 |
| Windows：首个失败停止后续调用 | 通过 |
| Windows：partial failure 只报告 written/unwritten names | 通过 |
| Windows + POSIX：只有 whole-batch success 后才注入 `os.environ` | 通过 |

### 5.3 类型安全

| 检查项 | 结果 |
|---|---|
| 无 `Any`、`object`、无类型签名 | 通过 |
| 无 `hasattr`/`getattr` | 通过 |
| 全部函数有完整中文 docstring（参数、返回值、异常） | 通过 |
| 类/模块有中文概览 docstring | 通过 |
| 无嵌套函数/类 | 通过 |
| 无 magic number / magic string（仅 tool schema 内字面量） | 通过 |

### 5.4 架构边界

| 检查项 | 结果 |
|---|---|
| Catalog 不复制 ConfigLoader extends resolver | 通过 |
| Catalog 不实现 manifest parser | 通过 |
| Environment 不接触 workspace transaction | 通过 |
| 无反向 import（`dayu.runtime` → 上层） | 通过 |
| 无 network/runtime assembly | 通过 |
| 无 `print`/logging/secrets in production output | 通过 |

### 5.5 状态机与并发

| 检查项 | 结果 |
|---|---|
| Environment persistence 是不可变批次（typed plan 构造后不可改） | 通过 |
| POSIX 单 profile 原子替换（`os.replace`） | 通过 |
| Whole-batch success 后才注入 env | 通过 |
| 无跨 root 分布式事务声明 | 通过 |
| 不在 S1 实现 lock/workspace transaction（属于 S2） | 通过 |

## 6. Open Questions

无。

## 7. Residual Risk

### 7.1 本 finding 修复后的残余

- **Marker 子串在非 export 行内的检测**：修复方案中的逐行扫描会跳过以 `export ` 开头
  且含 `=` 的行。如果未来有人手工编辑 profile，在 block 内部写入一个不以 `export `
  开头但含 marker 子串的行，该行仍会被正确拒绝。修复不改变此行为。

### 7.2 Windows `setx` 跨变量不可回滚

- 这是 accepted plan §10.1 的明确残余。当前实现正确地在首个 `setx` 失败后停止后续
  调用，并只报告 names。S1 未扩大此残余。

### 7.3 Windows `capture_output=True` 的潜在 secret 驻留

- `_persist_windows_environment()` 使用 `capture_output=True`，`subprocess.run`
  的返回对象 `CompletedProcess.stdout` / `CompletedProcess.stderr` 可能包含 secret
  value（取决于 Windows `setx` 是否在 stderr 中回显）。当前代码从不读取这些属性，
  对象在函数返回后由 GC 回收。但如果未来有人在此函数中添加 logging 或 debug
  输出，secret 可能通过 `completed.stderr` 泄漏。建议在函数 docstring 中明确
  标注此约束。**不在当前 S1 scope 内修复**。

### 7.4 测试覆盖缺口

- `_parse_managed_block` 的 `content.count()` 检查行（457）在覆盖报告中显示为
  covered（行 457 不在 `Missing` 列表中）。这是因为现有测试触发了该行的正常路径
  （正常 block 替换时 `content.count() == len(begin_indexes)`）。但 false positive
  路径（`content.count() > len(begin_indexes)`）仅在 edge-case input 下触发，
  当前未覆盖。修复后新增的逐行扫描逻辑需完整覆盖。

### 7.5 S1 不覆盖的范围（按计划延后）

- S2：real Service discovery、workspace transaction、四态编排。
- S3：非网络 prewarm、真实 POSIX/Windows subprocess smoke、README、CI workflow。
- Issue 142/151/175/177/178、Topic 8/9（计划 §1.3 明确排除）。

## 8. Reviewer conclusion

- **Material findings**：`1` 个（DS-R12-S1-01，CRITICAL，与 Controller mandatory
  evidence 一致的 marker 子串误判）。
- **Confirmed no-finding**：`1` 个（InitModelSelection value-object contract）。
- **Mechanical gates**：全部通过（56 tests、catalog 90.22%、environment 94.25%、
  full pyright zero、changed-path Ruff zero、full Ruff 144/SHA/cmp 零差异、
  `git diff --check` 通过）。
- **S1 review gate 裁决**：`NOT_PASS`。DS-R12-S1-01 是 CRITICAL correctness
  finding，必须在 S1 内修复并通过双路 re-review 后才能进入 S2。修复方案已在
  §4 详述，范围限于 `_parse_managed_block()` 内部，不改变公开契约。
- **下一入口**：Controller adjudication。Controller 收齐两路 review finding 后
  统一裁决 accepted/rejected/deferred；accepted finding 交回 AgentCodex 修复，
  完成后双路 re-review，未 PASS 不进入 S2。

## 9. Artifact metadata

- 本文件路径：`docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-ds.md`
- 本文件行数/字节数/SHA-256：由 Controller handoff 机械计算，不写入自身。
- 不修改 code/tests/control/plan/既有 artifacts，不 stage/commit。
