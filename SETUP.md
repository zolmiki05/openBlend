# OpenBlend — Setup Guide

OpenBlend is a shared playlist engine for two people: one on Spotify, one on Apple Music. It builds a single playlist published to both platforms, ranked by an LLM using each user's listening history.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [Spotify Developer](https://developer.spotify.com/dashboard) app
- An [Apple Developer](https://developer.apple.com) account with a MusicKit key
- A [Last.fm API](https://www.last.fm/api/account/create) app (for the Apple Music user's scrobbling)
- A [Z.ai](https://open.bigmodel.cn) account with API access to GLM-5

---

## 1. Clone and enter the repo

```bash
git clone https://gitlab.zolmiki.dev/zolmiki/openBlend.git
cd openBlend
```

---

## 2. Configure environment variables

Copy the example file and fill it in:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Database
POSTGRES_DB=openblend
POSTGRES_USER=openblend
POSTGRES_PASSWORD=<strong password>

# Security
SECRET_KEY=<run: openssl rand -hex 32>
TOKEN_ENCRYPTION_KEY=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Spotify — from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...

# Apple Music — from https://developer.apple.com (MusicKit key)
APPLE_MUSIC_TEAM_ID=...
APPLE_MUSIC_KEY_ID=...
# Paste the full .p8 key content with newlines escaped as \n
APPLE_MUSIC_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
APPLE_MUSIC_STOREFRONT=us

# Last.fm — from https://www.last.fm/api/account/create
LASTFM_API_KEY=...
LASTFM_SHARED_SECRET=...

# Z.ai / GLM-5
ZAI_API_KEY=...

# URLs (leave as-is for local development)
FRONTEND_URL=http://localhost:4200
API_URL=http://localhost:8000
```

### Generating the security keys

```bash
# SECRET_KEY
openssl rand -hex 32

# TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 3. Configure users

Copy the example and define your two users:

```bash
cp users_config.json.example users_config.json
```

Edit `users_config.json`:

```json
{
  "users": [
    {
      "username": "alice",
      "platform": "spotify"
    },
    {
      "username": "bob",
      "platform": "apple_music"
    }
  ]
}
```

- `platform` must be either `"spotify"` or `"apple_music"`
- Each user gets a randomly generated temporary password on first startup (printed to `backend/data/password_resets.log`)

---

## 4. Start the app

```bash
docker compose up --build
```

```bash
docker compose up --build
```

On first startup the backend will:
1. Run all database migrations (`alembic upgrade head`)
2. Provision users defined in `users_config.json`
3. Print temporary passwords to `backend/data/password_resets.log`

Once running:
- **Frontend:** http://localhost:4200
- **Backend API:** http://localhost:8000
- **API docs:** http://localhost:8000/docs

---

## 5. Get the temporary passwords

```bash
cat backend/data/password_resets.log
```

Or via Docker:

```bash
docker compose exec backend cat /app/data/password_resets.log
```

Each line contains the username and its generated password. Log in at http://localhost:4200 — you will be prompted to change the password on first login.

---

## 6. Connect accounts

After logging in, go to **Accounts** (`/accounts`) and connect each platform.

### Spotify user

1. Click **Connect via OAuth** — you will be redirected to Spotify
2. Alternatively, open [open.spotify.com/get_access_token](https://open.spotify.com/get_access_token) in your browser, copy the `accessToken` value from the JSON, and paste it into the **Paste token** field

### Apple Music user

1. Open [music.apple.com](https://music.apple.com) in your browser
2. Open DevTools → Console and run:
   ```js
   MusicKit.getInstance().musicUserToken
   ```
3. Copy the token and paste it into the **Paste token** field on the Accounts page

### Last.fm (Apple Music user only)

Last.fm is used to scrobble Apple Music plays and feed listening history into the scoring engine.

1. Click **Open Last.fm auth** — a new tab opens
2. Authorize the app on Last.fm
3. You will be redirected back — copy the token shown on the page
4. Paste it into the **Last.fm token** field and click **Save**

---

## 7. Run a sync

Go to the **Dashboard** and click **Run sync**. The pipeline will:

1. Scrobble recent Apple Music plays to Last.fm
2. Ingest Last.fm listening history
3. Ingest Spotify and Apple Music listening data
4. Normalize and match tracks across platforms
5. Score tracks using source weights, recency, saves, playlists, and Last.fm play counts
6. Generate a ranked candidate pool with GLM-5
7. Validate and repair the playlist
8. Publish to both Spotify and Apple Music

---

## Production deployment (behind a reverse proxy)

Use `docker-compose.prod.yml` instead of the default compose file. It is designed to sit behind a reverse proxy (nginx, Caddy, Nginx Proxy Manager, etc.) running on the same host.

### Architecture

```
Internet → Reverse proxy (Proxmox host) → 127.0.0.1:3000 → frontend container (nginx)
                                                                  ↓ /api/* (internal Docker network)
                                                              backend container :8000
                                                                  ↓
                                                           db + redis (no external ports)
```

API calls from the browser go to `yourdomain.com/api/...`, which the frontend nginx proxies internally to the backend over the Docker network. The reverse proxy only needs to forward traffic to a single upstream: `127.0.0.1:3000`.

### Steps

**1. Prepare the environment file**

In production, set `FRONTEND_URL` to your actual public URL:

```env
FRONTEND_URL=https://yourdomain.com
```

**2. Start with the production compose**

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**3. Get temporary passwords**

```bash
docker compose -f docker-compose.prod.yml exec backend cat /app/data/password_resets.log
```

**4. Configure your reverse proxy**

Point your reverse proxy to `127.0.0.1:3000`. Example nginx server block:

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    # SSL config here (cert, key, etc.)

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

No further config is needed — `/api/` routing is handled inside the frontend container.

### Production vs development compose differences

| Feature | `docker-compose.yml` | `docker-compose.prod.yml` |
|---------|---------------------|--------------------------|
| DB/Redis ports | Exposed to host | Internal only |
| Frontend port | `0.0.0.0:4200` | `127.0.0.1:3000` |
| Angular build | Dev (source maps) | Production (minified) |
| API URL in browser | `http://localhost:8000` | `/api` (proxied by nginx) |
| Log rotation | No | Yes (10 MB × 3 files) |
| Restart policy | `unless-stopped` | `always` |

---

## Development setup (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set DATABASE_URL to a local Postgres instance
export DATABASE_URL=postgresql://openblend:password@localhost:5432/openblend

alembic upgrade head
python -m provisioning.provision
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
```

The dev server runs at http://localhost:4200 and proxies API calls to http://localhost:8000.

---

## Environment variable reference

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `SECRET_KEY` | Yes | JWT signing key (32-byte hex) |
| `TOKEN_ENCRYPTION_KEY` | Yes | Fernet key for encrypting OAuth tokens |
| `SPOTIFY_CLIENT_ID` | Yes | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | Yes | Spotify app client secret (used for token refresh) |
| `APPLE_MUSIC_TEAM_ID` | Yes | Apple Developer team ID |
| `APPLE_MUSIC_KEY_ID` | Yes | MusicKit key ID |
| `APPLE_MUSIC_PRIVATE_KEY` | Yes | `.p8` key content, newlines as `\n` |
| `APPLE_MUSIC_STOREFRONT` | No | iTunes storefront (default: `us`) |
| `LASTFM_API_KEY` | Yes | Last.fm API key |
| `LASTFM_SHARED_SECRET` | Yes | Last.fm shared secret |
| `ZAI_API_KEY` | Yes | Z.ai API key for GLM-5 |
| `FRONTEND_URL` | No | CORS origin (default: `http://localhost:4200`) |
| `API_URL` | No | Backend URL used by frontend (default: `http://localhost:8000`) |
