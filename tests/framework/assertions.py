"""Assertions that read like the business rule they check."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import allure
import pytest

from framework.services import ApiError


@dataclass
class Rejection:
    error: ApiError | None = None


@contextmanager
def rejected(status: int, code: str, *, field: str | None = None) -> Iterator[Rejection]:
    """The block must end with a documented business rejection.

    A success fails the test; so does a 5xx or a broken error body (those raise
    UnexpectedResponse, which is not caught here).
    """
    caught = Rejection()
    with pytest.raises(ApiError) as info:
        yield caught
    exc = caught.error = info.value
    with allure.step(f"Rejected with {status} {code}" + (f" on field {field}" if field else "")):
        assert (exc.status, exc.code) == (status, code), f"expected {status} {code}, got {exc}"
        if field is not None:
            assert field in exc.fields, f"expected an error on '{field}', got {exc.fields}"
