# Quad — UBC Club Alerts frontend

Student-facing site for UBC Club Alerts. Designed in [Lovable](https://lovable.dev), built with TanStack Start, React and Tailwind. All event data comes from the FastAPI backend in the repo root (`../app`).

| Page | Backend call |
| --- | --- |
| Discover `/`, Explore `/explore` | `GET /api/events` (filtering and ranking run in the browser, see `src/lib/events.ts`) |
| Event `/events/:id` | `GET /api/events/{id}` |
| Get alerts `/subscribe` | `POST /api/subscriptions`, then `POST /verify` (demo mode confirms in-page) |
| Sign up `/signup`, Log in `/login` | `POST /api/auth/signup`, `POST /api/auth/login` (session token kept in localStorage, see `src/lib/auth.tsx`) |
| Account setup `/setup` | `PUT /api/me/profile`: birthday → major → gender → interests → hobbies |
| Account `/account` | `GET /api/me`, `POST /api/auth/logout` |
| Map `/map?day=YYYY-MM-DD` | `GET /api/events`; each event's `place` (building + lat/lng) comes from `app/places.py` matching the venue against `fixtures/ubc_buildings.json`. Leaflet + OpenStreetMap tiles. |

Discover's topic sections come from `topInterests()` in `src/lib/events.ts`: topics picked on the page, then the profile's interests, then topics of saved events, falling back to the busiest topics.

The API client and the mapping from the backend's event shape to the UI model live in `src/lib/api.ts`.

## Run locally

Start the backend first (from the repo root):

```sh
python -m scripts.run_demo all        # seed fixtures A–D
python -m uvicorn app.main:app --port 8000
```

Then the frontend:

```sh
cd frontend
npx bun install    # use Bun: `npm i` crashes on the rolldown override (npm bug, "edgesOut")
npm run dev        # http://localhost:8080
```

Set `VITE_API_URL` in `frontend/.env.local` if the API is not on `http://127.0.0.1:8000` (see `.env.example`). The backend allows the origins in `CORS_ORIGINS`, which defaults to localhost:8080/3000/5173.

`npm test` runs the Vitest suite and `npm run lint` runs ESLint.
