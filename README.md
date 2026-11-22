# KASORA AI

_Repository: AI-Business-Platform. KASORA AI is the product name; the logo mark is `frontend/src/components/brand/KasoraMark.tsx` and the app icons are `frontend/src/app/icon.svg`, `apple-icon.png` and `frontend/public/icon-*.png`._

## Running the backend

```
cd backend
pip install -r requirements.txt
python -m pytest                      # 160+ tests, no network, SQLite
# against PostgreSQL: apply migrations/0001 then 0002 with psql, then
TEST_DATABASE_URL=postgresql+asyncpg://user@host/db python -m pytest tests/api
# run the API
DATABASE_URL=postgresql+asyncpg://... python -m uvicorn app.main:create_app --factory --port 8000
```

Frontend: `cd frontend && npm install && npm run build && npm start` (set `NEXT_PUBLIC_API_BASE_URL`; the API's `CORS_ORIGINS` must list the frontend's exact origin).
