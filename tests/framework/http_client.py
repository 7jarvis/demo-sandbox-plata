"""Transport layer: send a request, return status, headers and body.

The only module that imports ``requests``. Swapping the HTTP library means
changing this file and nothing else. Every exchange is attached to the Allure
report with a request id that the service also writes to its log, so a failed
test can be matched to the server side.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import allure
import requests

SECRET_HEADERS = ("authorization",)
TOKEN_FIELD = re.compile(r'("access_token"\s*:\s*")[^"]+(")')


@dataclass(frozen=True)
class HttpResponse:
    method: str
    url: str
    status: int
    headers: dict[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    request_id: str

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def json(self) -> Any:
        return json.loads(self.body)

    @property
    def text(self) -> str:
        return self.body.decode(errors="replace")


class HttpClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        raw_body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> HttpResponse:
        request_id = uuid.uuid4().hex[:16]
        all_headers = {"Accept": "application/json", "X-Request-Id": request_id, **(headers or {})}
        data: bytes | str | None = raw_body
        if json_body is not None:
            data = json.dumps(json_body)
        if data is not None:
            all_headers.setdefault("Content-Type", "application/json")

        url = f"{self.base_url}{path}"
        resp = self._session.request(
            method, url, data=data, headers=all_headers, params=params, timeout=self.timeout
        )
        result = HttpResponse(
            method=method,
            url=resp.url,
            status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            body=resp.content,
            request_id=request_id,
        )
        self._attach(result, all_headers, data)
        return result

    def close(self) -> None:
        self._session.close()

    @staticmethod
    def _attach(resp: HttpResponse, headers: dict[str, str], body: bytes | str | None) -> None:
        shown_headers = {k: ("***" if k.lower() in SECRET_HEADERS else v) for k, v in headers.items()}
        req_body = body.decode(errors="replace") if isinstance(body, bytes) else (body or "")
        resp_body = TOKEN_FIELD.sub(r"\1***\2", resp.text)
        text = (
            f"{resp.method} {resp.url}\n"
            + "".join(f"{k}: {v}\n" for k, v in shown_headers.items())
            + f"\n{req_body}\n\n"
            + f"--> {resp.status}  (X-Request-Id: {resp.request_id})\n{resp_body}\n"
        )
        allure.attach(
            text,
            name=f"{resp.method} {resp.url.split('/api/v1', 1)[-1]} -> {resp.status}",
            attachment_type=allure.attachment_type.TEXT,
        )
