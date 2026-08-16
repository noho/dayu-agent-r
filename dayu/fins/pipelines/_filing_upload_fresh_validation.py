"""Filing upload fresh state 与 authoritative validation 共享边界。

本模块是 SEC/CN/HK workflow 在执行前重新读取 published state、运行同一
validator，并把可公开 prevalidation failure 投影为 closed reason 的唯一 owner。
它不判断 source integrity，不消费 raw meta，也不构造 market-specific event。
"""

from __future__ import annotations

import logging
from typing import Final

from dayu.fins.ingestion_runtime import (
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
    validate_fins_upload_filing_request,
)
from dayu.fins.storage import FilingUploadStateRepositoryProtocol
from dayu.fins.upload_failure import (
    FinsUploadFailureReason,
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_corruption_failure,
    fins_upload_prevalidation_io_failure,
)
from dayu.runtime.filelock import RuntimeFileLockError

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def resolve_fresh_filing_request(
    *,
    repository: FilingUploadStateRepositoryProtocol,
    request: ValidatedFinsUploadFilingRequest,
) -> ValidatedFinsUploadFilingRequest | FinsUploadFailureReason:
    """读取 fresh state 并运行 authoritative filing validator。

    Args:
        repository: filing published state 唯一仓储。
        request: preflight 已验证请求；仅复用 raw intent 与稳定 identity。

    Returns:
        fresh validator 产生的 authoritative request，或 upload-failure owner 产生的
        path-free typed failure reason。

    Raises:
        FinsUploadUsageError: fresh state 使用户动作不再合法时原样抛出。
        RuntimeError: validator 或 storage 的非公开内部 invariant 失败时原样抛出。
    """

    try:
        fresh_state = repository.read_filing_upload_state(
            request.normalized_ticker.canonical,
            request.document_id,
        )
        return validate_fins_upload_filing_request(
            request.request,
            published_state=fresh_state,
        )
    except FinsUploadPrevalidationError as exc:
        _LOGGER.exception("Filing upload fresh prevalidation failed")
        return exc.failure
    except FinsUploadUsageError:
        raise
    except (OSError, RuntimeFileLockError):
        _LOGGER.exception("Filing upload fresh state read failed")
        return fins_upload_prevalidation_io_failure()
    except ValueError:
        _LOGGER.exception("Filing upload fresh state is corrupted")
        return fins_upload_prevalidation_corruption_failure()
