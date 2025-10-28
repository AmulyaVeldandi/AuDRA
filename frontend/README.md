# AuDRA-Rad Frontend

Minimal Vite + React UI for reviewing AuDRA-Rad processing sessions.

## Development

1. Install dependencies:
   ```bash
   npm install
   ```
2. Start the backend API (from repository root):
   ```bash
   uvicorn src.api.app:app --reload
   ```
3. Run the frontend dev server:
   ```bash
   npm run dev
   ```
4. Open http://localhost:3000 in your browser. API calls are proxied to http://localhost:8000 during development.

## Build

```
npm run build
```

## Environment

Copy `.env.example` to `.env.local` and adjust `VITE_API_URL` if the backend is not running on the default `http://localhost:8000`.
