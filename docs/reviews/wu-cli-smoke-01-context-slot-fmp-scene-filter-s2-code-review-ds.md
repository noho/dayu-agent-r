# Code Review

## Metadata

- **Reviewer**: AgentDS (S2 independent code review)
- **Work unit**: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- **Review target**: workspace changes since commit `a124e0a8` (S2 on top of accepted S1)
- **Plan**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Controller adjudication**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-controller-adjudication.md`
- **Implementation artifact**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-implementation-codex.md`
- **Branch**: `phase/host-issues-control`
- **Review date**: 2026-07-07

## Scope

- **Mode**: current changes
- **Base**: `a124e0a8`
- **Output file**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-ds.md`
- **Included scope**:
  - `dayu/fins/resolver/__init__.py`
  - `dayu/fins/resolver/fmp_company_info.py`
  - `dayu/service/scene_context.py`
  - `dayu/cli/commands/prompt.py`
  - `dayu/cli/commands/interactive.py`
  - `dayu/cli/commands/session.py`
  - `tests/fins/test_fmp_company_info_resolver.py`
  - `tests/service/test_entrypoint_runtime.py` (新增 scene context 测试)
  - `tests/service/test_entrypoint_runtime_interactive_path.py`
  - `tests/service/test_import_boundary.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/cli/test_session_command.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
- **Excluded scope**: S1-only 文件（scene filter 相关）、未变更的 Service/Host/Engine 内部模块
- **Parallel review coverage**: 无；本 review 由单个 reviewer 逐条走读全部变更

## Pre-review Validation

```
tests/fins/test_fmp_company_info_resolver.py:                     7 passed
tests/cli/test_{prompt,interactive,session}_command.py:          90 passed
tests/service/test_entrypoint_runtime*.py:                        48 passed
tests/service/test_import_boundary.py + test_weak_typing_guard:   2 passed
pyright:                                                           0 errors, 0 warnings
git diff --check:                                                 passed
```

全部 147 个测试通过，pyright 零报错。Warnings 均为已有 `edgar` deprecation warning，与本次变更无关。

## Findings

### F1-Nonblocking-Low: `_resolve_company_name_for_subject` 中超时校验位于 API key 检查之前

- **入口/函数**: `_resolve_company_name_for_subject`
- **文件(行号)**: `dayu/service/scene_context.py:129`
- **输入场景**: 调用方显式传入非法 `fmp_timeout_seconds`（如 0、NaN、负无穷）且同时未传入 `fmp_api_key`（即 `fmp_api_key=None`）
- **实际分支**: 代码在第 129 行先执行超时校验并抛出 `ValueError`，第 131-133 行才检查 `api_key is None` 并提前返回 `None`
- **预期行为**: 当 `fmp_api_key` 为 `None` 时，FMP 不会被调用，timeout 不会被消费；此时超时非法不应触发异常，应直接返回 `None`
- **实际行为**: 非法超时值在 API key 检查之前触发 `ValueError("fmp_timeout_seconds must be positive finite seconds")`
- **直接证据**:
  ```python
  # scene_context.py:125-140
  def _resolve_company_name_for_subject(request):
      normalized_ticker = _normalize_optional_ticker(request.ticker)
      if normalized_ticker is None:
          return None
      # line 129 — 超时校验在 api_key 检查之前
      if not math.isfinite(request.fmp_timeout_seconds) or request.fmp_timeout_seconds <= 0:
          raise ValueError(...)
      # line 131-133 — api_key 检查在超时校验之后
      api_key = _optional_stripped_text(request.fmp_api_key)
      if api_key is None:
          return None
  ```
- **影响**: 当前所有 CLI 调用方均使用默认 `fmp_timeout_seconds=5.0`，不会触发此路径。仅在未来的非 CLI 调用方显式传入非法 timeout + 无 key 时才会触发。实际影响极低，但校验顺序违背"不调用就不校验"的最小权限原则。
- **建议改法和验证点**: 将 `api_key` 的 None 检查移到 timeout 校验之前（第 129 行之前），使 timeout 只在确定会调用 FMP 时才被校验。验证点：构造 `fmp_timeout_seconds=0` 且 `fmp_api_key=None` 的请求，确认返回 `None` 而非抛出异常。
- **修复风险（低）**: 仅调整两行代码的顺序，不改变正常路径行为。
- **严重程度（低）**: 当前无触发场景，属于防御性代码顺序优化。

### F2-Nonblocking-Low: `_interactive_context_slot_values` 返回类型与同层函数不一致

- **入口/函数**: `_interactive_context_slot_values`
- **文件(行号)**: `dayu/cli/commands/interactive.py:898`
- **输入场景**: 任意调用（无输入参数）
- **实际分支**: 函数返回 `{CONTEXT_SLOT_BASE_USER: DEFAULT_BASE_USER}`，返回类型声明为 `dict[str, str]`
- **预期行为**: 与 `_prompt_context_slot_values`（`prompt.py:656`，返回 `dict[str, JsonValue]`）和 `_session_context_slot_values`（`session.py:647`，返回 `dict[str, JsonValue]`）保持一致的类型声明
- **实际行为**: `interactive.py` 使用更窄的 `dict[str, str]`
- **直接证据**:
  ```python
  # interactive.py:898
  def _interactive_context_slot_values() -> dict[str, str]:

  # prompt.py:656
  def _prompt_context_slot_values(...) -> dict[str, JsonValue]:

  # session.py:647
  def _session_context_slot_values() -> dict[str, JsonValue]:
  ```
  三者均将返回值注入 `EntrypointRuntimeRequest.context_slot_values: dict[str, JsonValue]`
- **影响**: `dict[str, str]` 是 `dict[str, JsonValue]` 的子类型，类型系统接受。但三个 CLI command 对同一语义返回值的类型声明不一致，增加维护者的认知负担——未来若有人想在 interactive 的 slot 中加入非 str 值（如 bool），会被当前窄类型阻拦，而 prompt/session 不会。
- **建议改法和验证点**: 将 `_interactive_context_slot_values` 返回类型统一为 `dict[str, JsonValue]`。验证点：pyright 零报错。
- **修复风险（低）**: 纯类型标注变更，运行时行为不变。
- **严重程度（低）**: 仅影响代码可读性与一致性，不影响运行时正确性。

## Architecture Boundary Verification

逐项验证 plan 规定的架构约束：

| 约束 | 验证结果 | 证据 |
|---|---|---|
| Service 可依赖 Fins public resolver | ✅ 通过 | `dayu/service/scene_context.py:17` import `dayu.fins.resolver` |
| Service 可依赖 Fins ticker_normalization | ✅ 通过 | `dayu/service/scene_context.py:18` import `dayu.fins.ticker_normalization` |
| Service 不得导入 Fins storage/pipelines | ✅ 通过 | AST 扫描 `dayu/service/` 无 `dayu.fins.storage` / `dayu.fins.pipelines` 导入 |
| Service 不得导入 Host/Engine internals | ✅ 通过 | AST 扫描 `dayu/service/` 无 `dayu.host.durable` / `dayu.engine` 导入 |
| Runtime 不受影响 | ✅ 通过 | `dayu.runtime` 无变更 |
| Fins 包根不 re-export resolver 符号 | ✅ 通过 | `dayu/fins/__init__.py` 无 resolver import |
| Import boundary 测试已更新 | ✅ 通过 | `tests/service/test_import_boundary.py:26-28` 新增 `dayu.fins.resolver` 和 `dayu.fins.ticker_normalization` 到白名单 |
| CLI 读 FMP_API_KEY 在边界 | ✅ 通过 | `prompt.py:238` 通过 `os.environ.get(FMP_API_KEY_ENV)`；resolver 不读环境变量 |

## Key Path Walkthrough

### Path 1: prompt --ticker V（有 FMP_API_KEY）

```
CLI: ticker = "V", fmp_api_key = os.environ["FMP_API_KEY"]
  → _prompt_context_slot_values(ticker="V", fmp_api_key="sk-...")
    → build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker="V", fmp_api_key="sk-..."))
      → _resolve_company_name_for_subject: normalize_ticker("V") → "V"; api_key exists
        → FmpCompanyInfoResolver(api_key="sk-...").resolve_company_info("V")
          → search-symbol?query=V → "Visa Inc."
          → search-name?query=Visa Inc. → aliases
          → FmpCompanyInfo(canonical="V", company_name="Visa Inc.", aliases=("V",...))
        → returns "Visa Inc."
      → fins_default_subject("V", "Visa Inc.") → "# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"
      → current_time(...) → "# 当前时间\n现在是 2026年7月7日 ..."
    → {"fins_default_subject": "# 当前分析对象\n...", "current_time": "# 当前时间\n..."}
  → + {"base_user": "本地 CLI 用户"}
→ EntrypointRuntimeRequest.context_slot_values
```

✅ 路径正确。公司名来自 FMP，slot 格式为 OLD-compatible Markdown。

### Path 2: prompt（无 --ticker）

```
CLI: ticker = None, fmp_api_key = os.environ.get("FMP_API_KEY")
  → _prompt_context_slot_values(ticker=None, fmp_api_key=...)
    → build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=None, ...))
      → _resolve_company_name_for_subject: _normalize_optional_ticker(None) → None → return None
      → fins_default_subject(None) → ""
    → {"fins_default_subject": "", "current_time": "..."}
  → + {"base_user": "本地 CLI 用户"}
```

✅ 路径正确。无 ticker 时 `fins_default_subject` 为空字符串，不再输出 "未指定具体公司"。

### Path 3: prompt --ticker V（FMP 失败）

```
CLI: ticker = "V", fmp_api_key = "sk-..."
  → _resolve_company_name_for_subject: FmpCompanyInfoResolver raises FmpCompanyInfoResolutionError
    → except → return None
  → fins_default_subject("V") → "# 当前分析对象\n你正在分析的是 V。"
```

✅ 路径正确。FMP 失败时回退到 ticker-only，错误文本 "boom" 不泄漏到 slot 值。

### Path 4: interactive

```
CLI: ticker 仍被解析（供 invocation 元数据使用）但不传入 context_slot_values
  → _interactive_context_slot_values() → {"base_user": "本地 CLI 用户"}
→ EntrypointRuntimeRequest.context_slot_values
```

✅ 路径正确。interactive 不再提供 `fins_default_subject`。

### Path 5: session

```
CLI: _session_context_slot_values()
  → build_entrypoint_context_slot_values(EntrypointContextSlotRequest(ticker=None))
    → _resolve_company_name_for_subject: ticker None → return None
    → fins_default_subject(None) → ""
    → current_time(...) → "..."
  → {"fins_default_subject": "", "current_time": "..."}
  → + {"base_user": "本地 CLI 用户"}
```

✅ 路径正确。session 不再使用 "未指定具体公司"。

## FMP Resolver Correctness

逐函数验证 `dayu/fins/resolver/fmp_company_info.py`：

| 函数 | 检查项 | 结果 |
|---|---|---|
| `FmpCompanyInfo` | frozen dataclass, `ticker_aliases: tuple[str, ...]` 不可变 | ✅ |
| `FmpCompanyInfoResolver.__init__` | 显式 api_key, 显式 timeout, 不读 env | ✅ |
| `_build_fmp_search_url` | query 和 api_key 均 `urllib.parse.quote` | ✅ |
| `_parse_fmp_search_results` | JSON 解析 → isinstance list 检查 → 逐项提取 symbol/name | ✅ |
| `_select_symbol_result` | 精确规范化匹配 → fallback results[0]（OLD 行为） | ✅ |
| `_filter_same_name_results` | NFKC 归一 + 大写 + 空白折叠后严格比较 | ✅ |
| `_normalize_ticker_token` | try_normalize_ticker 优先 → 手动 fallback | ✅ |
| `_dedupe_ticker_aliases` | canonical 恒为首项, 去重, 空字符串过滤 | ✅ |
| `_string_field` | 防御性 `.get()` + `isinstance(str)` + `.strip()` | ✅ |
| HTTP 错误包装 | 所有 Exception → `FmpCompanyInfoResolutionError` | ✅ |
| 无 `Any`/`object` 签名 | 全部函数有完整类型标注 | ✅ |

### 两跳算法验证

测试 `test_resolve_company_info_uses_two_hop_same_name_aliases` 覆盖：
- `search-symbol` 返回 3 条结果（"V"/"Visa Inc.", "VISA"/"Visa Inc. Class A", "V.BA"/"Visa Inc."）
- `_select_symbol_result` 精确匹配 "V" → 选中 company_name="Visa Inc."
- `_filter_same_name_results` 从 search-symbol 过滤同名 → "V", "V.BA"
- `search-name` 返回 4 条结果（含重复和不同名）
- `_filter_same_name_results` 从 search-name 过滤同名 → "V", "V.BA", "V.BA"
- `_dedupe_ticker_aliases` 去重且 canonical "V" 为首 → `("V", "V.BA")`

✅ 算法正确。严格同名过滤排除了 "VISA"/"Visa Inc. Class A"，去重排除了重复的 "V.BA"，canonical 始终在首位。

## Test Coverage Assessment

| 测试区域 | 覆盖场景 | 缺口 |
|---|---|---|
| FMP resolver contract | 两跳算法、精确匹配 fallback、空结果、非法 JSON、非数组 payload、HTTP/timeout、空 key、非法 timeout | 无 |
| scene_context slot 生成 | ticker-only、FMP 增强、无 ticker、缺 key fallback、FMP 失败 fallback、current_time 中文格式（含 naive/aware datetime） | 无 |
| prompt CLI wiring | ticker+FMP 公司名增强、无 ticker 空 subject、FMP_API_KEY 缺失、ValueError 转 CliCommandUsageError | 无 |
| interactive CLI wiring | 不再提供 fins_default_subject、仅 base_user | 无 |
| session CLI wiring | ticker=None 空 subject | 无 |
| import boundary | 新增 fins.resolver + fins.ticker_normalization 白名单 | 无 |

✅ 测试覆盖完整。所有 happy path、failure path、boundary condition 均有测试。

## Open Questions

无。

## Residual Risk

1. **无真实 FMP 网络 smoke**：所有 FMP HTTP 调用均通过 `_FakeFmpHttpClient` 模拟，未验证真实 FMP API 的响应格式兼容性。分类为 S3 或后续 smoke 覆盖。
2. **`current_time` slot 生成但 prompt manifest 未消费**：`build_entrypoint_context_slot_values` 始终生成 `current_time` slot，但当前 prompt scene manifest 可能尚未声明该 slot。若 ScenePrepare 对多余 slot 采取 fail-closed 策略，可能导致运行时错误。分类为 S3 覆盖（S3 将更新 manifest 与 assets 对齐 slot 使用）。
3. **`base_user` slot 仍保留**：prompt/interactive/session 仍传递 `base_user`，待 S3 全局移除。
4. **`_UrllibFmpHttpClient` 未设置 User-Agent**：默认 HTTP 客户端未设置 User-Agent 请求头，若 FMP API 对此有要求可能导致请求被拒。当前可通过注入自定义 `FmpHttpClientProtocol` 实现绕过，S3 可按需增强默认客户端。

## Conclusion

**Pass** — 0 blocking findings, 2 nonblocking findings (both Low), 4 documented residual risks (all deferred to S3).

实现严格遵循 accepted plan 和 controller adjudication。FMP resolver 算法正确（两跳、严格同名、去重、canonical 首项），scene_context 文本格式符合 OLD-compatible Markdown 约定，CLI wiring 正确分离了 prompt（读 FMP_API_KEY、生成 subject slot）和 interactive（不再提供 fins_default_subject），架构边界未穿透，测试覆盖完整，pyright 零报错。

### Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-ds.md`
- **Conclusion**: Pass
- **Blocking findings**: 0
- **Nonblocking findings**: 2 (both Low)
  - F1: `_resolve_company_name_for_subject` 超时校验顺序（`scene_context.py:129`）
  - F2: `_interactive_context_slot_values` 返回类型不一致（`interactive.py:898`）
- **Residual risks**: 4（无真实 FMP smoke、current_time 未消费、base_user 残留、默认 HTTP client 无 User-Agent）
