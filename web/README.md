# Web

React + TypeScript interface for Magonia, built with Vite.

```bash
npm install
npm run dev        # http://localhost:5173, forwards /api to the API on port 8000
npm run lint
npm run build
npm run test:e2e   # browser test with Playwright (API faked)
```

Run the API alongside (`uv run uvicorn api.main:app --reload` in `api/`) to use real data.

To run the browser tests while a dev server already holds port 5173 (a second checkout, for
example), point Playwright at another port with a copy of `playwright.config.ts`.
