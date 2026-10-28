"""A thin Elasticsearch REST client over httpx (plan decision 12).

The official 8.x Python client sends compatibility headers that ES 7.x rejects; kb-core must run on the company's
ES whatever its version (7.10 or later), so it speaks plain REST and uses only APIs that exist in 7.10 and 8.x.
"""

import json
from typing import Any

import httpx

from kb_core.config import Settings


class EsError(RuntimeError):
    def __init__(self, status: int, reason: str):
        super().__init__(f"Elasticsearch {status}: {reason}")
        self.status = status
        self.reason = reason


def _reason(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return r.text[:500]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return f"{err.get('type')}: {err.get('reason')}"
    return str(err or body)[:500]


class EsClient:
    def __init__(self, settings: Settings, timeout: float = 60.0):
        headers = {"Content-Type": "application/json"}
        auth = None
        if settings.es_api_key:
            headers["Authorization"] = f"ApiKey {settings.es_api_key}"
        elif settings.es_user:
            auth = (settings.es_user, settings.es_password or "")
        self._http = httpx.Client(base_url=settings.es_url, headers=headers, auth=auth, timeout=timeout,
                                  verify=settings.es_ca_certs or True)

    def request(self, method: str, path: str, json: Any = None, params: dict | None = None,
                allow_404: bool = False) -> Any:
        r = self._http.request(method, path, json=json, params=params)
        if r.status_code == 404 and allow_404:
            return None
        if r.status_code >= 400:
            raise EsError(r.status_code, _reason(r))
        if method == "HEAD" or not r.content:
            return {}
        return r.json()

    def info(self) -> dict:
        return self.request("GET", "/")

    def bulk(self, actions: list[dict], refresh: bool = False) -> dict:
        """actions: alternating action / source dicts, as the _bulk API takes them; raises on any item error."""
        body = "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in actions)
        r = self._http.post("/_bulk", content=body.encode(), params={"refresh": "true"} if refresh else None,
                            headers={"Content-Type": "application/x-ndjson"})
        if r.status_code >= 400:
            raise EsError(r.status_code, _reason(r))
        out = r.json()
        if out.get("errors"):
            first = next(next(iter(i.values())) for i in out["items"] if next(iter(i.values())).get("error"))
            raise EsError(first.get("status", 400), str(first.get("error"))[:500])
        return out

    def analyze(self, index: str, analyzer: str, text: str) -> list[str]:
        out = self.request("POST", f"/{index}/_analyze", json={"analyzer": analyzer, "text": text})
        return [t["token"] for t in out["tokens"]]

    def close(self) -> None:
        self._http.close()


def es_client(settings: Settings) -> EsClient:
    return EsClient(settings)
