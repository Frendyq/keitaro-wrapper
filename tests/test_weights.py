from dataclasses import dataclass

import pytest

from app.services.weights import WeightError, can_pin, rebalance


@dataclass
class Item:
    share: int = 0
    pinned: bool = False


def shares(items):
    return [i.share for i in items]


def test_single_offer_gets_everything():
    items = [Item()]
    rebalance(items)
    assert shares(items) == [100]


def test_three_offers_split_with_remainder_at_the_end():
    items = [Item(), Item(), Item()]
    rebalance(items)
    assert shares(items) == [33, 33, 34]


def test_four_offers():
    items = [Item() for _ in range(4)]
    rebalance(items)
    assert shares(items) == [25, 25, 25, 25]


def test_pinned_weight_is_kept():
    items = [Item(25, True), Item(), Item()]
    rebalance(items)
    assert shares(items) == [25, 37, 38]
    assert sum(shares(items)) == 100


def test_all_pinned_is_left_alone():
    items = [Item(60, True), Item(40, True)]
    rebalance(items)
    assert shares(items) == [60, 40]


def test_not_enough_weight_for_free_offers():
    items = [Item(100, True), Item()]
    with pytest.raises(WeightError):
        rebalance(items)


def test_empty_list_is_fine():
    rebalance([])


def test_cannot_pin_over_one_hundred():
    items = [Item(70, True), Item(50), Item(0)]
    with pytest.raises(WeightError):
        can_pin(items, items[1])


def test_cannot_pin_the_last_free_offer_when_total_is_not_full():
    items = [Item(30, True), Item(50)]
    with pytest.raises(WeightError):
        can_pin(items, items[1])


def test_can_pin_when_others_stay_free():
    items = [Item(50), Item(25), Item(25)]
    can_pin(items, items[0])
