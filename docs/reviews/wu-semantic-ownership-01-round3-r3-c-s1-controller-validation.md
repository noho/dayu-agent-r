# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Gate: controller validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`
- Accepted plan commit: `7b24b070`
- Implementer: AgentCodex

## File Scope

Changed production files are within the accepted S1 allowed set:

- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/local_file_store.py`
- `dayu/fins/storage/repository_protocols.py`

Changed test/artifact files:

- `tests/fins/test_fins_storage_atomicity.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`

No S2/S3 files, Host/Service wait adapter files, upload/download workflow files, prompt files, or tool schema files were modified.

## Controller Validation Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
```

Result: `118 passed, 3 warnings`. Warnings are existing `edgar` deprecation warnings.

```bash
source .venv/bin/activate
pytest tests/fins -q
```

Result: `491 passed, 1 skipped, 3 warnings`.

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: pass, no output.

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q \
  --cov=dayu/fins/storage --cov-report=term-missing
```

Result: `118 passed, 3 warnings`. Modified production file coverage:

| File | Coverage |
| --- | ---: |
| `dayu/fins/storage/_fs_blob_core.py` | `87%` |
| `dayu/fins/storage/_fs_storage_infra.py` | `81%` |
| `dayu/fins/storage/_fs_storage_utils.py` | `88%` |
| `dayu/fins/storage/local_file_store.py` | `99%` |
| `dayu/fins/storage/repository_protocols.py` | `100%` |

## Contract Checks

- `SWAPPED_TARGET` before `COMMITTED` is treated as uncommitted: recovery removes or withdraws the new target and restores backup when present.
- `COMMITTED` is the only commit point. Backup and journal cleanup after `COMMITTED` is best-effort and does not turn a committed batch into caller-visible failure.
- Commit failure plus rollback failure preserves the original commit exception as primary and the rollback exception as `__cause__`, with a note that recovery evidence is retained.
- `LocalFileStore.put_object()` uses unique same-directory temp files, file fsync before atomic replace, parent-directory fsync after replace, and temp cleanup on failure.
- Blob `store_file()` now confirms both Source and Processed handles exist before building keys or calling `FileStore`.
- Object key and local URI parsing share the storage-owned key/component validation path.

## Tool-Security Scope Check

S1 did not implement tool-security policy. Keyword scan for `allowlist`, `symlink-safe`, `SSRF`, `byte-budget`, `tool schema`, `prompt`, `TLS`, and `redirect` found matches only in this WU's documentation/artifact exclusion text, not in production or test code.

The added symlink containment tests are storage identity tests for `local://` object key resolution under the storage root. They do not implement upload source authority, upload allowlists, URL provenance, remote egress policy, byte budgets, or LLM-facing security schema/prompt behavior.

## README Decision

Controller accepts the implementation artifact's README decision: README/current-fact synchronization is deferred until S1, S2, and S3 production/test changes have all landed and passed slice review, per `R3-C-PF-09`.

## Controller Decision

Status: `ready-for-code-review`.

Next gate: AgentMiMo and AgentDS S1 code review. No commit is authorized before review/adjudication.
