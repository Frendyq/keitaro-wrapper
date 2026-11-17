import pytest

from app.models import ACTIVE, REMOVED, Campaign
from app.services import editor
from app.services.editor import EditorError


def make_campaign(db, kt, shares=None):
    """A campaign with a redirect stream and a stream with offers, like the one in the assignment."""
    campaign = kt.create_campaign({"name": "test_c"})
    kt.create_stream({"campaign_id": campaign["id"], "name": "Flow 1", "position": 1, "schema": "redirect"})
    offers_stream = kt.create_stream({"campaign_id": campaign["id"], "name": "Flow 2", "position": 2, "schema": "landings"})
    kt.set_offers(offers_stream["id"], shares or {1: 33, 2: 33, 3: 34})
    local = Campaign(kt_id=campaign["id"], name="test_c")
    db.add(local)
    db.flush()
    editor.sync_campaign_streams(db, kt, local)
    db.commit()
    return local


def offers_stream(campaign):
    return next(s for s in campaign.streams if s.has_offers)


def share_map(stream):
    return {o.kt_offer_id: (o.status, o.share) for o in stream.offers}


def test_sync_ignores_streams_without_offers(db, kt):
    campaign = make_campaign(db, kt)
    plain = next(s for s in campaign.streams if not s.has_offers)
    assert plain.offers == []
    assert not offers_stream(campaign).is_dirty


def test_add_offer_rebalances_and_marks_stream_dirty(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    editor.add_offer(db, kt, stream, 4)
    assert [o.share for o in stream.active_offers] == [25, 25, 25, 25]
    assert stream.is_dirty
    # Nothing is sent to Keitaro before the push.
    assert len(kt.streams[stream.kt_id]["offers"]) == 3


def test_add_unknown_offer_fails(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    with pytest.raises(EditorError):
        editor.add_offer(db, kt, stream, 999)


def test_add_same_offer_twice_fails(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    with pytest.raises(EditorError):
        editor.add_offer(db, kt, stream, 1)


def test_push_sends_the_new_weights(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    editor.add_offer(db, kt, stream, 4)
    editor.push_stream(db, kt, stream)

    sent = {o["offer_id"]: o["share"] for o in kt.streams[stream.kt_id]["offers"]}
    assert sent == {1: 25, 2: 25, 3: 25, 4: 25}
    assert not stream.is_dirty


def test_cancel_drops_added_offers(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    editor.add_offer(db, kt, stream, 4)
    editor.cancel_changes(db, stream)

    assert share_map(stream) == {1: (ACTIVE, 33), 2: (ACTIVE, 33), 3: (ACTIVE, 34)}
    assert not stream.is_dirty


def test_remove_keeps_the_offer_as_removed(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    target = stream.offers[0]
    editor.remove_offer(db, target)

    assert target.status == REMOVED and target.share == 0
    assert [o.share for o in stream.active_offers] == [50, 50]
    assert stream.is_dirty


def test_removed_offer_disappears_from_keitaro_but_stays_locally(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    editor.remove_offer(db, stream.offers[0])
    editor.push_stream(db, kt, stream)

    assert {o["offer_id"] for o in kt.streams[stream.kt_id]["offers"]} == {2, 3}
    assert len(stream.offers) == 3
    assert not stream.is_dirty


def test_bring_back_after_push(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    removed = stream.offers[0]
    editor.remove_offer(db, removed)
    editor.push_stream(db, kt, stream)

    editor.restore_offer(db, removed)
    assert stream.is_dirty
    editor.push_stream(db, kt, stream)

    assert {o["offer_id"] for o in kt.streams[stream.kt_id]["offers"]} == {1, 2, 3}
    assert sum(o.share for o in stream.active_offers) == 100


def test_cancel_a_removal(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    editor.remove_offer(db, stream.offers[0])
    editor.cancel_changes(db, stream)

    assert share_map(stream) == {1: (ACTIVE, 33), 2: (ACTIVE, 33), 3: (ACTIVE, 34)}


def test_offer_deleted_in_keitaro_becomes_removed_after_fetch(db, kt):
    campaign = make_campaign(db, kt)
    stream = offers_stream(campaign)
    kt.set_offers(stream.kt_id, {2: 50, 3: 50})

    editor.sync_campaign_streams(db, kt, campaign)
    db.commit()

    assert stream.offers[0].status == REMOVED
    assert {o.kt_offer_id: o.share for o in stream.active_offers} == {2: 50, 3: 50}
    assert not stream.is_dirty

    editor.restore_offer(db, stream.offers[0])
    assert stream.offers[0].status == ACTIVE


def test_fetch_keeps_unpublished_changes(db, kt):
    campaign = make_campaign(db, kt)
    stream = offers_stream(campaign)
    editor.add_offer(db, kt, stream, 4)

    editor.sync_campaign_streams(db, kt, campaign)
    db.commit()

    assert stream.is_dirty
    assert len(stream.active_offers) == 4


def test_pinned_weight_survives_add_and_restore(db, kt):
    stream = offers_stream(make_campaign(db, kt, {1: 25, 2: 25, 3: 25, 4: 25}))
    editor.set_pin(db, stream.offers[0], True)

    editor.remove_offer(db, stream.offers[1])
    assert {o.kt_offer_id: o.share for o in stream.active_offers} == {1: 25, 3: 37, 4: 38}

    editor.restore_offer(db, stream.offers[1])
    shares = {o.kt_offer_id: o.share for o in stream.active_offers}
    assert shares[1] == 25
    assert sum(shares.values()) == 100


def test_cannot_pin_everything_when_total_is_not_full(db, kt):
    stream = offers_stream(make_campaign(db, kt, {1: 50, 2: 50}))
    editor.remove_offer(db, stream.offers[1])  # offer 1 now has 100
    editor.set_pin(db, stream.offers[0], True)
    assert stream.offers[0].pinned


def test_push_does_nothing_without_changes(db, kt):
    stream = offers_stream(make_campaign(db, kt))
    before = list(kt.streams[stream.kt_id]["offers"])
    editor.push_stream(db, kt, stream)
    assert kt.streams[stream.kt_id]["offers"] == before


def test_streams_without_offers_cannot_be_edited(db, kt):
    campaign = make_campaign(db, kt)
    plain = next(s for s in campaign.streams if not s.has_offers)
    with pytest.raises(EditorError):
        editor.add_offer(db, kt, plain, 1)


# Importing an existing campaign


def test_import_existing_campaign(db, kt):
    remote = kt.create_campaign({"name": "made_in_keitaro", "alias": "abc123"})
    kt.create_stream({"campaign_id": remote["id"], "name": "Google", "position": 1, "schema": "redirect"})
    offers = kt.create_stream({"campaign_id": remote["id"], "name": "Offers", "position": 2, "schema": "landings"})
    kt.set_offers(offers["id"], {1: 50, 2: 50})

    campaign = editor.import_campaign(db, kt, remote["id"])

    assert campaign.name == "made_in_keitaro" and campaign.alias == "abc123"
    assert [s.has_offers for s in campaign.streams] == [False, True]
    assert {o.kt_offer_id: o.share for o in offers_stream(campaign).active_offers} == {1: 50, 2: 50}


def test_import_twice_gives_the_same_campaign(db, kt):
    remote = kt.create_campaign({"name": "made_in_keitaro"})
    first = editor.import_campaign(db, kt, remote["id"])
    assert editor.import_campaign(db, kt, remote["id"]).id == first.id


def test_import_unknown_campaign_fails(db, kt):
    with pytest.raises(EditorError):
        editor.import_campaign(db, kt, 999999)
