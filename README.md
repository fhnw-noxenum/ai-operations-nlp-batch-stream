# ai-operations-nlp-batch-stream

Lokales Übungslab für vier Lektionen zu Batch Inference, Token-Streaming

## Build Base Image

```bash
cd base
docker build . -t batch-stream-base
```

## Start

```bash
docker compose up --build api prometheus grafana
```

- API: <http://localhost:8000/docs>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000> (admin / admin)

## Python Script Tests

See: https://docs.python.org/3/library/venv.html

### venv erstellen:
```bash
python -m venv .venv
```

### venv aktivieren (Windows):
```bash
.\.venv\Scripts\activate
```

### venv aktivieren (Mac / Linux):
```bash
source venv/bin/activate
```

### Install dependency (httpx):
```bash
pip install httpx
```

### Run test:
```bash
python scripts/client_sync.py --n 20
```

## Lokales Modell

Die API nutzt jetzt ein echtes lokales Hugging-Face/Transformers-Modell.

Default in `docker-compose.yml`:

```yaml
MODEL_ID: "HuggingFaceTB/SmolLM2-135M-Instruct"
MODEL_DEVICE: "cpu"
```

Beim ersten Start wird das Modell heruntergeladen und im Docker-Volume `hf-cache` gespeichert. Für sehr schwache Laptops kann testweise ein noch kleineres Modell gesetzt werden:

```bash
MODEL_ID=sshleifer/tiny-gpt2 docker compose up --build api prometheus grafana
```

Hinweis: Mit CPU sind k6-Lasttests deutlich langsamer. Für Unterrichtsmessungen daher `max_tokens` in den k6-Skripten klein halten oder die VUs reduzieren.

## Übungen

1. `baseline`: synchrone API messen
2. `batch`: Microbatching in `app/batcher.py` ergänzen
3. `stream`: SSE Token-Streaming in `app/main.py` ergänzen

Starter-Code enthält TODOs. Musterlösungen liegen in `solutions/app/`.

Ergänze `results/*.md` mit Messwerten, Screenshot-Hinweisen und kurzer Trade-off-Begründung.

## Loadtests

```bash
docker compose --profile load run --rm k6-sync
docker compose --profile load run --rm k6-batch
docker compose --profile load run --rm k6-stream
```
