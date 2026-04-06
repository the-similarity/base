---
description: How to run the fractal terrain visualizer
---

## Run the Fractal Terrain App

### Classic mode only (no API needed)

// turbo
1. Start the static file server:
```bash
cd /Users/buyantogtokh/Projects/14/the-similarity-fractal && python3 -m http.server 8080
```

2. Open http://localhost:8080 in your browser

### Engine mode (with terrain generation API)

// turbo
1. Start the Python API backend:
```bash
cd /Users/buyantogtokh/Projects/14/the-similarity-api && uvicorn app.main:app --reload
```

// turbo
2. Start the static file server:
```bash
cd /Users/buyantogtokh/Projects/14/the-similarity-fractal && python3 -m http.server 8080
```

3. Open http://localhost:8080 in your browser
4. Click the **Engine** button to switch to API-driven terrain generation
