import pytest

from app.services import creator
from app.services.creator import CreatorError


def test_creator_builds_two_streams(db, kt, settings):
    campaign = creator.create_campaign(db, kt, settings, "test_musaev_c1", "kz", 2)

    created = kt.campaigns[campaign.kt_id]
    assert created["domain_id"] == 10 and created["group_id"] == 20 and created["traffic_source_id"] == 30

    flows = sorted(kt.list_streams(campaign.kt_id), key=lambda s: s["position"])
    assert flows[0]["filters"] == [{"name": "country", "mode": "accept", "payload": ["KZ"]}]
    assert flows[0]["action_payload"] == "https://google.com"
    assert flows[1]["offers"] == [{"offer_id": 2, "share": 100, "state": "active"}]
    assert [s.has_offers for s in campaign.streams] == [False, True]


def test_creator_rejects_bad_country(db, kt, settings):
    with pytest.raises(CreatorError):
        creator.create_campaign(db, kt, settings, "test_musaev_c1", "K", 2)


def test_creator_rejects_unknown_offer(db, kt, settings):
    with pytest.raises(CreatorError):
        creator.create_campaign(db, kt, settings, "test_musaev_c1", "KZ", 999)


def test_creator_needs_the_configured_group(db, kt, settings):
    kt.groups = []
    with pytest.raises(CreatorError):
        creator.create_campaign(db, kt, settings, "test_musaev_c1", "KZ", 2)
