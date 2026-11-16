"""Weight (share) distribution between the offers of one stream.

Weights are integer percents and always add up to 100. Pinned offers keep their weight,
the rest of the percents is split evenly between the other offers. The remainder goes
to the last offers, so three offers get 33, 33 and 34.
"""

from typing import Protocol, Sequence


class WeightError(ValueError):
    pass


class WeightedOffer(Protocol):
    share: int
    pinned: bool


def rebalance(offers: Sequence[WeightedOffer]) -> None:
    """Recalculate the weights of the given (active) offers in place."""
    if not offers:
        return

    pinned = [o for o in offers if o.pinned]
    free = [o for o in offers if not o.pinned]
    if not free:
        # Everything is pinned, there is nothing to recalculate.
        return

    left = 100 - sum(o.share for o in pinned)
    if left < len(free):
        raise WeightError("Not enough weight left for the offers that are not pinned")

    base, extra = divmod(left, len(free))
    first_with_extra = len(free) - extra
    for index, offer in enumerate(free):
        offer.share = base + (1 if index >= first_with_extra else 0)


def can_pin(offers: Sequence[WeightedOffer], target: WeightedOffer) -> None:
    """Check that pinning `target` still leaves a valid distribution."""
    others_free = [o for o in offers if o is not target and not o.pinned]
    pinned_sum = sum(o.share for o in offers if o.pinned and o is not target) + target.share
    if pinned_sum > 100:
        raise WeightError("Pinned weights add up to more than 100%")
    if not others_free and pinned_sum != 100:
        raise WeightError("At least one offer must stay unpinned while the total is not 100%")
    if others_free and 100 - pinned_sum < len(others_free):
        raise WeightError("Not enough weight left for the offers that are not pinned")
