"""In-memory replacement of KeitaroClient for the tests."""

import itertools

from app.keitaro import KeitaroClient, KeitaroError


class FakeKeitaro(KeitaroClient):
    def __init__(self):  # no http client needed
        self.offers = {
            1: "Offer one",
            2: "Offer two",
            3: "Offer three",
            4: "Offer four",
            5: "Offer five",
        }
        self.domains = [{"id": 10, "name": "in.posdk.xyz"}]
        self.groups = [{"id": 20, "name": "FORTESTS", "type": "campaigns"}]
        self.sources = [{"id": 30, "name": "FORTESTS"}]
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.report_rows: dict[str, list[dict]] = {"today": [], "yesterday": []}
        self._ids = itertools.count(100)

    # reference data
    def list_domains(self):
        return self.domains

    def list_groups(self, group_type="campaigns"):
        return self.groups

    def list_traffic_sources(self):
        return self.sources

    def list_offers(self):
        return [{"id": i, "name": n} for i, n in self.offers.items()]

    def get_offer(self, offer_id):
        if offer_id not in self.offers:
            raise KeitaroError("not found", 404)
        return {"id": offer_id, "name": self.offers[offer_id]}

    # campaigns and streams
    def create_campaign(self, payload):
        campaign = {**payload, "id": next(self._ids)}
        self.campaigns[campaign["id"]] = campaign
        return campaign

    def get_campaign(self, campaign_id):
        return self.campaigns[campaign_id]

    def list_streams(self, campaign_id):
        return [s for s in self.streams.values() if s["campaign_id"] == campaign_id]

    def create_stream(self, payload):
        stream = {**payload, "id": next(self._ids)}
        stream.setdefault("offers", [])
        self.streams[stream["id"]] = stream
        return stream

    def update_stream(self, stream_id, payload):
        self.streams[stream_id].update(payload)
        return self.streams[stream_id]

    def build_report(self, payload):
        return {"rows": self.report_rows[payload["range"]["interval"]]}

    # helpers for the tests
    def set_offers(self, stream_id, shares: dict[int, int]):
        self.streams[stream_id]["offers"] = [
            {"offer_id": offer_id, "share": share, "state": "active"} for offer_id, share in shares.items()
        ]
