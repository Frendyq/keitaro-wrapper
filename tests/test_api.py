from test_editor import make_campaign, offers_stream


def test_create_campaign_through_the_api(client, kt):
    response = client.post("/api/campaigns", json={"name": "test_musaev_a", "geo": "KZ", "offer_id": 1})
    assert response.status_code == 201
    body = response.json()
    assert [s["has_offers"] for s in body["streams"]] == [False, True]
    assert client.get("/api/campaigns").json()[0]["name"] == "test_musaev_a"


def test_create_campaign_validation_error(client):
    response = client.post("/api/campaigns", json={"name": "x", "geo": "KAZ", "offer_id": 1})
    assert response.status_code == 422


def test_unknown_offer_gives_a_readable_error(client):
    response = client.post("/api/campaigns", json={"name": "test_musaev_a", "geo": "KZ", "offer_id": 999})
    assert response.status_code == 400
    assert "999" in response.json()["detail"]


def test_edit_flow(client, db, kt):
    campaign = make_campaign(db, kt)
    stream = offers_stream(campaign)

    added = client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 4}).json()
    assert added["dirty"] is True
    assert [o["share"] for o in added["offers"]] == [25, 25, 25, 25]

    offer_id = added["offers"][0]["id"]
    removed = client.delete(f"/api/streams/{stream.id}/offers/{offer_id}").json()
    assert removed["offers"][0]["status"] == "removed"
    assert [o["share"] for o in removed["offers"][1:]] == [33, 33, 34]

    pushed = client.post(f"/api/streams/{stream.id}/push").json()
    assert pushed["dirty"] is False
    assert {o["offer_id"] for o in kt.streams[stream.kt_id]["offers"]} == {2, 3, 4}

    restored = client.post(f"/api/streams/{stream.id}/offers/{offer_id}/restore").json()
    assert restored["dirty"] is True
    cancelled = client.post(f"/api/streams/{stream.id}/cancel").json()
    assert cancelled["dirty"] is False
    assert cancelled["offers"][0]["status"] == "removed"


def test_removing_an_unpublished_offer_through_the_api(client, db, kt):
    stream = offers_stream(make_campaign(db, kt))
    added = client.post(f"/api/streams/{stream.id}/offers", json={"offer_id": 4}).json()
    new_id = next(o["id"] for o in added["offers"] if o["offer_id"] == 4)

    body = client.delete(f"/api/streams/{stream.id}/offers/{new_id}").json()

    assert [o["offer_id"] for o in body["offers"]] == [1, 2, 3]
    assert [o["share"] for o in body["offers"]] == [33, 33, 34]
    assert body["dirty"] is False


def test_pin_endpoint(client, db, kt):
    stream = offers_stream(make_campaign(db, kt, {1: 25, 2: 25, 3: 25, 4: 25}))
    first = stream.offers[0].id
    pinned = client.post(f"/api/streams/{stream.id}/offers/{first}/pin", json={"pinned": True}).json()
    assert pinned["offers"][0]["pinned"] is True


def test_offer_search(client):
    found = client.get("/api/offers", params={"q": "three"}).json()
    assert found == [{"id": 3, "name": "Offer three"}]
    assert len(client.get("/api/offers").json()) == 5


def test_stats_and_trend(client, db, kt):
    campaign = make_campaign(db, kt)
    stream = offers_stream(campaign)
    kt.report_rows["today"] = [{"stream_id": stream.kt_id, "offer_id": 1, "clicks": 7, "conversions": 1, "revenue": 3}]
    kt.report_rows["yesterday"] = [{"stream_id": stream.kt_id, "offer_id": 1, "clicks": 4}]

    body = client.get(f"/api/campaigns/{campaign.id}").json()
    first = next(s for s in body["streams"] if s["has_offers"])["offers"][0]
    assert first["stats"]["clicks"] == 7
    assert first["stats"]["trend"] == 1


def test_pages_render(client, db, kt):
    campaign = make_campaign(db, kt)
    assert client.get("/").status_code == 200
    assert client.get(f"/campaigns/{campaign.id}").status_code == 200
    assert client.get("/campaigns/9999").status_code == 404


def test_import_campaign_through_the_api(client, kt):
    remote = kt.create_campaign({"name": "made_in_keitaro"})
    offers = kt.create_stream({"campaign_id": remote["id"], "name": "Offers", "position": 1, "schema": "landings"})
    kt.set_offers(offers["id"], {1: 100})

    response = client.post("/api/campaigns/import", json={"kt_id": remote["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "made_in_keitaro"
    assert body["streams"][0]["offers"][0]["share"] == 100

    missing = client.post("/api/campaigns/import", json={"kt_id": 999999})
    assert missing.status_code == 400
