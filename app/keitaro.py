"""Thin client for the Keitaro admin API (v1)."""

from typing import Any

import httpx

from app.config import Settings, get_settings


class KeitaroError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class KeitaroClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        settings = settings or get_settings()
        self._http = httpx.Client(
            base_url=settings.keitaro_url.rstrip("/") + "/admin_api/v1",
            headers={"Api-Key": settings.keitaro_api_key, "Accept": "application/json"},
            timeout=settings.keitaro_timeout,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise KeitaroError(f"Keitaro is not reachable: {error}") from error
        if response.status_code >= 400:
            raise KeitaroError(
                f"Keitaro answered {response.status_code} on {method} {path}: {response.text[:300]}",
                response.status_code,
            )
        if not response.content:
            return None
        return response.json()

    # Reference data

    def list_domains(self) -> list[dict]:
        return self._request("GET", "/domains")

    def list_groups(self, group_type: str = "campaigns") -> list[dict]:
        return self._request("GET", "/groups", params={"type": group_type})

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")

    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def get_offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    # Campaigns and streams

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def list_streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=payload)

    # Statistics

    def build_report(self, payload: dict) -> dict:
        return self._request("POST", "/report/build", json=payload)
