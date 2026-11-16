"""Creates a campaign with two streams, the way the assignment describes it."""

import secrets
import string

from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign
from app.services.editor import sync_campaign_streams


class CreatorError(ValueError):
    pass


def _find_by_name(items: list[dict], name: str, kind: str) -> dict:
    wanted = name.strip().lower()
    for item in items:
        if str(item.get("name", "")).strip().lower() == wanted:
            return item
    raise CreatorError(f"{kind} '{name}' was not found in Keitaro")


def _domain_matches(item: dict, name: str) -> bool:
    wanted = name.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    return str(item.get("name", "")).strip().lower().strip("/") == wanted


def _pick_domain(domains: list[dict], name: str) -> dict:
    if name.strip():
        found = next((d for d in domains if _domain_matches(d, name)), None)
        if found is None:
            raise CreatorError(f"Domain '{name}' was not found in Keitaro")
        return found
    active = [d for d in domains if d.get("state", "active") == "active"]
    if not active:
        raise CreatorError("There is no active domain in Keitaro")
    return active[0]


def _alias() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def normalize_geo(geo: str) -> str:
    geo = geo.strip().upper()
    if len(geo) != 2 or not geo.isalpha():
        raise CreatorError("Country code must be two letters, for example KZ")
    return geo


def create_campaign(db: Session, kt: KeitaroClient, settings: Settings, name: str, geo: str, offer_id: int) -> Campaign:
    name = name.strip()
    if not name:
        raise CreatorError("Campaign name is required")
    geo = normalize_geo(geo)

    try:
        offer = kt.get_offer(offer_id)
    except KeitaroError as error:
        if error.status_code == 404:
            raise CreatorError(f"Offer {offer_id} was not found in Keitaro") from error
        raise

    domain = _pick_domain(kt.list_domains(), settings.domain_name)
    group = _find_by_name(kt.list_groups(), settings.group_name, "Group")
    source = _find_by_name(kt.list_traffic_sources(), settings.source_name, "Traffic source")

    campaign = kt.create_campaign(
        {
            "name": name,
            "alias": _alias(),
            "type": "position",
            "state": "active",
            "domain_id": domain["id"],
            "group_id": group["id"],
            "traffic_source_id": source["id"],
            "cost_type": "CPC",
            "cost_value": 0,
            "cost_currency": "USD",
            "cost_auto": True,
        }
    )

    # The first stream catches everybody from the country and sends them to Google.
    kt.create_stream(
        {
            "campaign_id": campaign["id"],
            "type": "regular",
            "name": "Google",
            "position": 1,
            "schema": "redirect",
            "action_type": "http",
            "action_payload": settings.redirect_url,
            "collect_clicks": True,
            "filter_or": False,
            "filters": [{"name": "country", "mode": "accept", "payload": [geo]}],
        }
    )
    # The second stream sends everybody else to the chosen offer.
    kt.create_stream(
        {
            "campaign_id": campaign["id"],
            "type": "regular",
            "name": "Offers",
            "position": 2,
            "schema": "landings",
            "action_type": "http",
            "action_payload": "",
            "collect_clicks": True,
            "filter_or": False,
            "filters": [],
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        }
    )

    local = Campaign(kt_id=campaign["id"], name=name, alias=campaign.get("alias"), geo=geo)
    db.add(local)
    db.flush()
    sync_campaign_streams(db, kt, local)
    db.commit()
    return local
