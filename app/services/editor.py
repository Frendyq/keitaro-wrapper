"""Editing offers of an existing campaign.

Changes are kept in our database first. A stream whose local state differs from Keitaro is
"dirty" (yellow in the UI) until it is pushed to Keitaro or the changes are cancelled.
Offers removed from a stream are never deleted locally, they stay in the stream as
"removed" and can be brought back.
"""

from sqlalchemy.orm import Session

from app.keitaro import KeitaroClient, KeitaroError
from app.models import ACTIVE, REMOVED, Campaign, Stream, StreamOffer
from app.services.weights import WeightError, can_pin, rebalance


class EditorError(ValueError):
    pass


def _offer_names(kt: KeitaroClient) -> dict[int, str]:
    return {int(o["id"]): str(o.get("name", "")) for o in kt.list_offers()}


def _rebalance(stream: Stream) -> None:
    try:
        rebalance(stream.active_offers)
    except WeightError as error:
        raise EditorError(str(error)) from error


def sync_campaign_streams(db: Session, kt: KeitaroClient, campaign: Campaign) -> None:
    """Fetch the streams of the campaign from Keitaro and reconcile them with our database."""
    names = _offer_names(kt)
    remote_streams = kt.list_streams(campaign.kt_id)
    local_by_id = {s.kt_id: s for s in campaign.streams}
    remote_ids = set()

    for item in remote_streams:
        remote_ids.add(item["id"])
        stream = local_by_id.get(item["id"])
        if stream is None:
            stream = Stream(campaign=campaign, kt_id=item["id"], name=item.get("name") or "", position=0)
            db.add(stream)
        stream.name = item.get("name") or stream.name
        stream.position = item.get("position") or 0

        remote_offers = {int(o["offer_id"]): o for o in (item.get("offers") or [])}
        # A stream that holds no offers (a plain redirect, for example) is stored without any details.
        stream.has_offers = bool(remote_offers) or item.get("schema") == "landings" or bool(stream.offers)
        if not stream.has_offers:
            continue

        has_pending_changes = stream.is_dirty
        local_offers = {o.kt_offer_id: o for o in stream.offers}

        for offer_id, remote in remote_offers.items():
            share = int(remote.get("share") or 0)
            row = local_offers.get(offer_id)
            if row is None:
                row = StreamOffer(
                    stream=stream,
                    kt_offer_id=offer_id,
                    name=names.get(offer_id, f"Offer #{offer_id}"),
                    status=ACTIVE,
                    share=share,
                    kt_share=share,
                    published=True,
                )
                db.add(row)
                continue
            row.kt_share = share
            row.published = True
            row.name = names.get(offer_id, row.name)
            if not has_pending_changes:
                row.status = ACTIVE
                row.share = share

        for offer_id, row in local_offers.items():
            if offer_id in remote_offers:
                continue
            if row.in_kt:
                # The offer was deleted in Keitaro. We keep it as removed so it can be brought back.
                row.status = REMOVED
                row.share = 0
                row.pinned = False
                row.kt_share = None

        db.flush()
        if has_pending_changes:
            _rebalance(stream)

    for stream in list(campaign.streams):
        if stream.kt_id not in remote_ids:
            db.delete(stream)
    db.flush()


def _require_offer_stream(stream: Stream) -> None:
    if not stream.has_offers:
        raise EditorError("This stream has no offers, nothing to edit")


def add_offer(db: Session, kt: KeitaroClient, stream: Stream, offer_id: int) -> StreamOffer:
    _require_offer_stream(stream)
    existing = next((o for o in stream.offers if o.kt_offer_id == offer_id), None)
    if existing is not None and existing.status == ACTIVE:
        raise EditorError("This offer is already in the stream")

    if existing is not None:
        row = existing
        row.status = ACTIVE
        row.share = 0
    else:
        try:
            offer = kt.get_offer(offer_id)
        except KeitaroError as error:
            if error.status_code == 404:
                raise EditorError(f"Offer {offer_id} was not found in Keitaro") from error
            raise
        row = StreamOffer(
            stream=stream,
            kt_offer_id=offer_id,
            name=str(offer.get("name", "")),
            status=ACTIVE,
            share=0,
            kt_share=None,
            published=False,
        )
        db.add(row)
    db.flush()
    _rebalance(stream)
    db.commit()
    return row


def remove_offer(db: Session, offer: StreamOffer) -> None:
    if offer.status != ACTIVE:
        raise EditorError("The offer is already removed")
    offer.status = REMOVED
    offer.share = 0
    offer.pinned = False
    db.flush()
    _rebalance(offer.stream)
    db.commit()


def restore_offer(db: Session, offer: StreamOffer) -> None:
    if offer.status != REMOVED:
        raise EditorError("The offer is not removed")
    offer.status = ACTIVE
    offer.share = 0
    db.flush()
    _rebalance(offer.stream)
    db.commit()


def set_pin(db: Session, offer: StreamOffer, pinned: bool) -> None:
    if offer.status != ACTIVE:
        raise EditorError("Only active offers can be pinned")
    if pinned and not offer.pinned:
        try:
            can_pin(offer.stream.active_offers, offer)
        except WeightError as error:
            raise EditorError(str(error)) from error
    offer.pinned = pinned
    db.commit()


def push_stream(db: Session, kt: KeitaroClient, stream: Stream) -> None:
    _require_offer_stream(stream)
    if not stream.is_dirty:
        return
    active = stream.active_offers
    if active and sum(o.share for o in active) != 100:
        raise EditorError("Weights must add up to 100% before publishing")

    kt.update_stream(
        stream.kt_id,
        {"offers": [{"offer_id": o.kt_offer_id, "share": o.share, "state": "active"} for o in active]},
    )
    for offer in stream.offers:
        offer.kt_share = offer.share if offer.status == ACTIVE else None
        if offer.status == ACTIVE:
            offer.published = True
    db.commit()


def cancel_changes(db: Session, stream: Stream) -> None:
    """Drop everything that was not pushed yet and go back to what Keitaro has."""
    _require_offer_stream(stream)
    for offer in list(stream.offers):
        if offer.in_kt:
            offer.status = ACTIVE
            offer.share = offer.kt_share
        elif offer.status == ACTIVE:
            if offer.published:
                # Brought back, but not published yet: it is removed again.
                offer.status = REMOVED
                offer.share = 0
                offer.pinned = False
            else:
                # Added locally and never published.
                db.delete(offer)
    db.commit()
    db.refresh(stream)
