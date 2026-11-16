"""Clicks and conversions per offer, taken from the Keitaro report API."""

from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign

MEASURES = ["clicks", "conversions", "revenue"]


def _report(kt: KeitaroClient, campaign_id: int, interval: str) -> dict[tuple[int, int], dict]:
    result = kt.build_report(
        {
            "range": {"interval": interval},
            "dimensions": ["stream_id", "offer_id"],
            "measures": MEASURES,
            "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_id}],
        }
    )
    rows = {}
    for row in result.get("rows", []):
        try:
            key = (int(row["stream_id"]), int(row["offer_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        rows[key] = row
    return rows


def offer_stats(kt: KeitaroClient, campaign: Campaign) -> dict[str, dict]:
    """Stats for the table. The trend compares today with yesterday."""
    try:
        today = _report(kt, campaign.kt_id, "today")
        yesterday = _report(kt, campaign.kt_id, "yesterday")
    except KeitaroError:
        return {}

    stats = {}
    for key, row in today.items():
        before = (yesterday.get(key) or {}).get("clicks") or 0
        clicks = row.get("clicks") or 0
        stats[f"{key[0]}:{key[1]}"] = {
            "clicks": clicks,
            "conversions": row.get("conversions") or 0,
            "revenue": row.get("revenue") or 0,
            "yesterday_clicks": before,
            "trend": (clicks > before) - (clicks < before),
        }
    for key, row in yesterday.items():
        stats.setdefault(
            f"{key[0]}:{key[1]}",
            {
                "clicks": 0,
                "conversions": 0,
                "revenue": 0,
                "yesterday_clicks": row.get("clicks") or 0,
                "trend": -1 if (row.get("clicks") or 0) else 0,
            },
        )
    return stats
