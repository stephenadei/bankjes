# Stephen's Bankjes

Amsterdam straatmeubilair-explorer. FastAPI proxy over de Amsterdam DSO open-data
API met een Leaflet-kaart als frontend. Geen database — alles in-memory gecached.

## Wat zit erin

| Categorie | Bron |
|---|---|
| Banken | `bgt/straatmeubilair?plusType=bank` |
| Picknicktafels | `bgt/straatmeubilair?plusType=picknicktafel` |
| Afvalcontainers | `huishoudelijkafval/containerlocatie` |
| Fietspaaltjes | `fietspaaltjes/fietspaaltjes` |
| Sportvoorzieningen | `sport/openbaresportplek` |

Alle requests vragen `_format=geojson` zodat de DSO-API server-side van RD New (EPSG:28992) naar WGS84 (CRS84) projecteert.

## Lokaal draaien

```bash
docker compose up --build
# open http://localhost:4309
```

Of zonder Docker:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

## Environments

| Env | URL | Branch | Compose file | Port (VPS) |
|---|---|---|---|---|
| dev | `http://localhost:4309` | feature branches | `docker-compose.yml` | n.v.t. (laptop) |
| acc | `https://bankjes-acc.stephensprive.app` | `develop` | `docker-compose.acc.yml` | 4308 |
| prd | `https://bankjes.stephensprive.app` | `master` | `docker-compose.prd.yml` | 4307 |

Push naar `develop` → GHA bouwt `ghcr.io/stephenadei/bankjes:acc` en deployt naar acc.
Push (PR-merge) naar `master` → idem voor `prd`.

Handmatige deploy op de VPS:

```bash
cd /home/stephen/projects/bankjes-acc   # of /home/stephen/projects/bankjes-prd
git pull
./scripts/deploy.sh acc   # of prd
```

## Endpoints

- `GET /` — Leaflet UI
- `GET /healthz` — liveness check
- `GET /api/items` — alle features samengevoegd
- `GET /api/items?dataset=bench` — één categorie
- `GET /api/items?bbox=south,west,north,east` — alleen binnen viewport
