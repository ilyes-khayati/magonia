# Web

React + TypeScript interface for Magonia, built with Vite.

```bash
npm install
npm run dev        # http://localhost:5173, forwards /api to the API on port 8000
npm run lint
npm run build
npm run test:e2e   # browser test with Playwright (API faked)
```

Run the API alongside (`uv run fastapi dev src/api/main.py` in `api/`) to use real data.
