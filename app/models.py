from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ACTIVE = "active"
REMOVED = "removed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    kt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geo: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position, Stream.id"
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    kt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Streams without offers (for example a plain redirect) are stored but never parsed.
    has_offers: Mapped[bool] = mapped_column(Boolean, default=False)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )

    @property
    def active_offers(self) -> list["StreamOffer"]:
        return [o for o in self.offers if o.status == ACTIVE]

    @property
    def is_dirty(self) -> bool:
        """True when the local state differs from what Keitaro has (the yellow state in the UI)."""
        return any(o.is_dirty for o in self.offers)


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "kt_offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    kt_offer_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(500), default="")

    status: Mapped[str] = mapped_column(String(16), default=ACTIVE)
    # Weight we want to have in percent. Removed offers always have 0.
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    # Weight that Keitaro has right now, None when the offer is not in Keitaro.
    kt_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True once the offer has been in Keitaro. An offer that never was there is simply
    # dropped when the changes are cancelled, a published one goes back to "removed".
    published: Mapped[bool] = mapped_column(Boolean, default=False)

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def in_kt(self) -> bool:
        return self.kt_share is not None

    @property
    def is_dirty(self) -> bool:
        if self.status == ACTIVE:
            return not self.in_kt or self.share != self.kt_share
        return self.in_kt
