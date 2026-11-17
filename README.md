# Keitaro wrapper

A small web app on top of the [Keitaro](https://keitaro.io) tracker admin API. It does two things:

1. **Campaign creator.** Takes a campaign name, a country code and an offer ID and creates a campaign in Keitaro with two streams: the first one sends everybody from the country to Google, the second one sends everybody else to the chosen offer. Domain, group and traffic source are set from the API.
2. **Campaign editor.** Shows the streams of a campaign and lets you add and remove offers with correct weights. Changes are kept locally until you push them to Keitaro.

Stack: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, httpx. The front end is plain HTML with jQuery.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then put your Keitaro API key into .env
```

The API key is created in Keitaro under Profile, API keys. Settings in `.env`:

| Variable | Meaning |
|----------|---------|
| `KEITARO_URL` | address of the tracker, for example `https://tlgk.host` |
| `KEITARO_API_KEY` | admin API key |
| `DATABASE_URL` | SQLite by default, PostgreSQL works too (`postgresql+psycopg://user:password@localhost:5432/wrapper`, install `psycopg[binary]`) |
| `DOMAIN_NAME` | domain for new campaigns, empty means the first active domain of the account |
| `GROUP_NAME`, `SOURCE_NAME` | group and traffic source for new campaigns, both are looked up by name (`FORTESTS` by default) |
| `NAME_PREFIX` | prefilled in the campaign name field |

## Migrations

The schema is managed by Alembic. Create or update the database with:

```bash
alembic upgrade head
```

To roll back everything: `alembic downgrade base`. After a change in `app/models.py` create a new migration with `alembic revision --autogenerate -m "describe the change"`.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

- The start page has the creation form, a form to take an existing Keitaro campaign under the editor by its ID, and the list of campaigns known to the app.
- The editor of a campaign opens with "Open editor".

## How the editor works

The editor works with any campaign of the account: create one here, or import an existing one by its Keitaro ID (importing twice gives the same campaign). It keeps its own copy of the streams and offers of a campaign. A stream whose copy differs from Keitaro is highlighted in yellow and marked "not published".

- **Fetch streams from KT** loads the streams from Keitaro. Only streams that contain offers are editable. Other streams (a redirect, for example) are stored without any details. Unpublished local changes are kept. An offer that was deleted in Keitaro does not disappear here, it becomes grey and is marked "removed".
- **Add.** Search an offer by ID or name and add it. The weights are recalculated at once, four offers get 25% each. Nothing is sent to Keitaro yet.
- **Remove.** The offer turns grey and its weight becomes 0%. After publishing it is gone from Keitaro but stays here, so it can be brought back with **Bring back**. An offer that was added here and not pushed yet is simply dropped, there is nothing to bring back.
- **Pin.** A pinned weight is kept by all later changes. The rest of the percents is split evenly between the other offers. Weights are whole numbers and always add up to 100%, the remainder goes to the last offers (33, 33, 34).
- **Push to KT** sends the offers of the stream with their weights to Keitaro.
- **Cancel** drops everything that was not pushed: offers that were never in Keitaro are deleted, removed offers come back to their published weights.
- **Stats** show clicks, conversions and revenue per offer for today. The trend arrow compares today with yesterday.

## Tests

```bash
pytest
```

The tests use an in-memory replacement of the Keitaro client and an in-memory SQLite database, so no network and no API key are needed. They cover the weight distribution, the editor and creator services, the HTTP API, the Keitaro client (with a mocked transport) and the migration, which has to build exactly the schema of the models.

The same tests run in GitHub Actions on every push.

## Project layout

```
app/
  main.py            routes and pages
  config.py          settings from the environment
  db.py              database engine and session
  models.py          Campaign, Stream, StreamOffer
  keitaro.py         client of the Keitaro admin API
  services/
    creator.py       campaign creation
    editor.py        fetching, adding, removing, pushing, cancelling
    weights.py       weight distribution
    stats.py         clicks per offer from the report API
  templates/, static/   pages and scripts
alembic/             migrations
tests/
```

## Keitaro API calls

`GET /domains`, `GET /groups?type=campaigns`, `GET /traffic_sources`, `GET /offers`, `GET /offers/{id}`, `POST /campaigns`, `GET /campaigns/{id}`, `GET /campaigns/{id}/streams`, `POST /streams`, `PUT /streams/{id}` and `POST /report/build`.

The list of offers is large, so the client keeps it for one minute.
