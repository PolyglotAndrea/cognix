# Installation

## Prerequisites

- Python 3.11 or higher
- Node.js 18+ (for the web frontend)
- Git

## Install from Source

```bash
git clone https://github.com/PolyglotAndrea/cognix.git
cd cognix
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development with docs and testing tools:

```bash
pip install -e ".[dev,docs]"
```

## Install the Web Frontend

```bash
cd web
npm install
```

## Verify Installation

```bash
# Check CLI
cognix --help
cognix version

# Check API server
cognix server start --port 8000

# Check web frontend
cd web && npm run dev
```

## Docker (Optional)

```bash
docker build -t cognix .
docker run -p 8000:8000 -e COGNIX_LLM_API_KEY=sk-... cognix
```

!!! note
    Docker support is planned but not yet fully implemented. Use source installation for now.
