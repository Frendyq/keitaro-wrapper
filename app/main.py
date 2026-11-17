from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign, Stream, StreamOffer
from app.services import creator, editor, stats
from app.services.creator import CreatorError
from app.services.editor import EditorError

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Keitaro wrapper")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@lru_cache
def _keitaro() -> KeitaroClient:
    return KeitaroClient(get_settings())


def get_keitaro() -> KeitaroClient:
    return _keitaro()


@app.exception_handler(EditorError)
@app.exception_handler(CreatorError)
async def bad_request(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


@app.exception_handler(KeitaroError)
async def keitaro_failed(_: Request, error: KeitaroError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=502)


# Serialization


def offer_to_dict(offer: StreamOffer, stat: dict | None) -> dict:
    return {
        "id": offer.id,
        "offer_id": offer.kt_offer_id,
        "name": offer.name,
        "status": offer.status,
        "share": offer.share,
        "kt_share": offer.kt_share,
        "pinned": offer.pinned,
        "dirty": offer.is_dirty,
        "stats": stat,
    }


def stream_to_dict(stream: Stream, all_stats: dict) -> dict:
    return {
        "id": stream.id,
        "kt_id": stream.kt_id,
        "name": stream.name,
        "position": stream.position,
        "has_offers": stream.has_offers,
        "dirty": stream.is_dirty,
        "offers": [
            offer_to_dict(o, all_stats.get(f"{stream.kt_id}:{o.kt_offer_id}")) for o in stream.offers
        ],
    }


def campaign_to_dict(campaign: Campaign, all_stats: dict | None = None) -> dict:
    all_stats = all_stats or {}
    return {
        "id": campaign.id,
        "kt_id": campaign.kt_id,
        "name": campaign.name,
        "geo": campaign.geo,
        "streams": [stream_to_dict(s, all_stats) for s in campaign.streams],
    }


def _campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    return campaign


def _stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(404, "Stream not found")
    return stream


def _offer(db: Session, stream_id: int, offer_id: int) -> StreamOffer:
    offer = db.get(StreamOffer, offer_id)
    if offer is None or offer.stream_id != stream_id:
        raise HTTPException(404, "Offer not found in this stream")
    return offer


# Pages


@app.get("/", response_class=HTMLResponse)
def index(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(request, "index.html", {"prefix": settings.name_prefix})


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_page(request: Request, campaign_id: int, db: Session = Depends(get_db)):
    campaign = _campaign(db, campaign_id)
    return templates.TemplateResponse(request, "campaign.html", {"campaign": campaign})


# Campaign creator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    geo: str = Field(min_length=2, max_length=2)
    offer_id: int = Field(gt=0)


@app.get("/api/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    campaigns = db.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    return [{"id": c.id, "kt_id": c.kt_id, "name": c.name, "geo": c.geo} for c in campaigns]


class CampaignImport(BaseModel):
    kt_id: int = Field(gt=0)


@app.post("/api/campaigns/import")
def import_campaign(body: CampaignImport, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    campaign = editor.import_campaign(db, kt, body.kt_id)
    return campaign_to_dict(campaign)


@app.post("/api/campaigns", status_code=201)
def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(get_keitaro),
    settings: Settings = Depends(get_settings),
):
    campaign = creator.create_campaign(db, kt, settings, body.name, body.geo, body.offer_id)
    return campaign_to_dict(campaign)


# Editor


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    campaign = _campaign(db, campaign_id)
    return campaign_to_dict(campaign, stats.offer_stats(kt, campaign))


@app.post("/api/campaigns/{campaign_id}/fetch")
def fetch_streams(campaign_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    campaign = _campaign(db, campaign_id)
    editor.sync_campaign_streams(db, kt, campaign)
    db.commit()
    db.refresh(campaign)
    return campaign_to_dict(campaign, stats.offer_stats(kt, campaign))


@app.get("/api/offers")
def search_offers(q: str = "", kt: KeitaroClient = Depends(get_keitaro)):
    needle = q.strip().lower()
    result = []
    for offer in kt.list_offers():
        text = f"{offer['id']} {offer.get('name', '')}".lower()
        if not needle or needle in text:
            result.append({"id": offer["id"], "name": offer.get("name", "")})
        if len(result) >= 30:
            break
    return result


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0)


class PinBody(BaseModel):
    pinned: bool


@app.post("/api/streams/{stream_id}/offers", status_code=201)
def add_offer(
    stream_id: int, body: OfferAdd, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)
):
    stream = _stream(db, stream_id)
    editor.add_offer(db, kt, stream, body.offer_id)
    db.refresh(stream)
    return stream_to_dict(stream, {})


@app.delete("/api/streams/{stream_id}/offers/{offer_id}")
def remove_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db)):
    offer = _offer(db, stream_id, offer_id)
    editor.remove_offer(db, offer)
    db.refresh(offer.stream)
    return stream_to_dict(offer.stream, {})


@app.post("/api/streams/{stream_id}/offers/{offer_id}/restore")
def restore_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db)):
    offer = _offer(db, stream_id, offer_id)
    editor.restore_offer(db, offer)
    db.refresh(offer.stream)
    return stream_to_dict(offer.stream, {})


@app.post("/api/streams/{stream_id}/offers/{offer_id}/pin")
def pin_offer(stream_id: int, offer_id: int, body: PinBody, db: Session = Depends(get_db)):
    offer = _offer(db, stream_id, offer_id)
    editor.set_pin(db, offer, body.pinned)
    db.refresh(offer.stream)
    return stream_to_dict(offer.stream, {})


@app.post("/api/streams/{stream_id}/push")
def push_stream(stream_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    stream = _stream(db, stream_id)
    editor.push_stream(db, kt, stream)
    db.refresh(stream)
    return stream_to_dict(stream, {})


@app.post("/api/streams/{stream_id}/cancel")
def cancel_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = _stream(db, stream_id)
    editor.cancel_changes(db, stream)
    return stream_to_dict(stream, {})
