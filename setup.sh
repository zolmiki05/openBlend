#!/usr/bin/env bash
# setup.sh — openBlend environment setup wizard
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
ENV_FILE="$SCRIPT_DIR/.env"
TMP_FILE="$(mktemp)"

trap 'rm -f "$TMP_FILE"' EXIT

# ─── Colors ────────────────────────────────────────────────────────────────────
R='\033[0;31m'
G='\033[0;32m'
Y='\033[1;33m'
B='\033[0;34m'
C='\033[0;36m'
M='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
RST='\033[0m'

# ─── Print helpers ─────────────────────────────────────────────────────────────
p_ok()      { echo -e "  ${G}✓${RST}  $*"; }
p_info()    { echo -e "  ${C}ℹ${RST}  $*"; }
p_warn()    { echo -e "  ${Y}⚠${RST}  $*"; }
p_err()     { echo -e "  ${R}✗${RST}  $*" >&2; }
p_skip()    { echo -e "  ${DIM}↷  $* — kihagyva${RST}"; }
p_hint()    { echo -e "  ${DIM}    $*${RST}"; }
p_section() {
    echo ""
    echo -e "  ${BOLD}${B}▶ $*${RST}"
    echo -e "  ${DIM}──────────────────────────────────────────────${RST}"
}

# ─── Write to temp file ────────────────────────────────────────────────────────
wl()  { printf '%s\n'    "$1"      >> "$TMP_FILE"; }   # raw line
wkv() { printf '%s=%s\n' "$1" "$2" >> "$TMP_FILE"; }   # key=value

# ─── Python detection ──────────────────────────────────────────────────────────
detect_python() {
    if command -v python3 &>/dev/null; then
        echo "python3"; return 0
    fi
    if command -v python &>/dev/null \
       && python -c "import sys; sys.exit(0 if sys.version_info.major == 3 else 1)" 2>/dev/null; then
        echo "python"; return 0
    fi
    return 1
}

# ─── Generator functions ───────────────────────────────────────────────────────
gen_hex_key() {
    "$PY" -c "import secrets; print(secrets.token_hex(32))"
}

gen_fernet_key() {
    "$PY" -c "
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ImportError:
    import secrets, base64
    print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
"
}

gen_password() {
    "$PY" -c "
import secrets, string
chars = string.ascii_letters + string.digits + '_-#@'
print(''.join(secrets.choice(chars) for _ in range(24)))
"
}

read_p8_file() {
    "$PY" -c "
import sys
with open(sys.argv[1]) as f:
    content = f.read().strip()
print(content.replace('\n', r'\n'))
" "$1"
}

# ─── Input helpers ─────────────────────────────────────────────────────────────
# ask VARNAME DESCRIPTION DEFAULT [SKIPPABLE=false]
# Prints the resolved value to stdout; side-effects only via echo.
ask() {
    local varname="$1"
    local desc="$2"
    local default="$3"
    local skippable="${4:-false}"

    local suffix=""
    [[ -n "$default" ]]          && suffix+=" ${DIM}[↵ = ${default}]${RST}"
    [[ "$skippable" == "true" ]] && suffix+=" ${Y}[s = kihagyás]${RST}"

    local val
    IFS= read -rp "$(echo -e "  ${BOLD}${varname}${RST}  ${C}${desc}${RST}${suffix}: ")" val </dev/tty

    case "$val" in
        s|S|skip) echo "__SKIP__" ;;
        "")       echo "$default" ;;
        *)        echo "$val"     ;;
    esac
}

ask_port() {
    local service="$1"
    local default="$2"

    local val
    IFS= read -rp "$(echo -e "  ${BOLD}Port${RST}  ${C}${service}${RST} ${DIM}[↵ = ${default}]${RST}: ")" val </dev/tty

    if [[ -z "$val" ]]; then
        echo "$default"
    elif [[ "$val" =~ ^[0-9]+$ ]] && (( val >= 1 && val <= 65535 )); then
        echo "$val"
    else
        p_warn "Érvénytelen port '$val', alapértelmezett ($default) kerül beállításra." >&2
        echo "$default"
    fi
}

# ask_section SERVICE HINT
# Returns 0 if user wants to configure, 1 if skip.
ask_section() {
    local service="$1"
    local hint_text="$2"

    echo ""
    echo -e "  ${BOLD}${M}${service}${RST}"
    [[ -n "$hint_text" ]] && p_hint "$hint_text"

    local val
    IFS= read -rp "$(echo -e "  Konfiguráljuk? ${DIM}[↵ = igen${RST} / ${Y}s = kihagyás${RST}${DIM}]${RST}: ")" val </dev/tty

    [[ "$val" == "s" || "$val" == "S" || "$val" == "skip" ]] && return 1
    return 0
}

# ─── Banner ────────────────────────────────────────────────────────────────────
clear 2>/dev/null || true
echo ""
echo -e "${BOLD}${B}"
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║       openBlend  ·  Telepítő Varázsló         ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo -e "${RST}"
echo -e "  Létrehozza a ${BOLD}.env${RST} fájlt a ${BOLD}.env.example${RST} alapján."
echo -e "  A biztonsági kulcsok ${G}automatikusan generálódnak${RST}."
echo -e "  Opcionális szolgáltatásokat kihagyhatsz (${Y}s${RST} = kihagyás)."
echo ""

# ─── Preflight ─────────────────────────────────────────────────────────────────
[[ ! -f "$ENV_EXAMPLE" ]] && { p_err ".env.example nem található: $ENV_EXAMPLE"; exit 1; }

if [[ -f "$ENV_FILE" ]]; then
    p_warn ".env fájl már létezik!"
    ow=""
    IFS= read -rp "$(echo -e "  Felülírjuk? ${R}[i/N]${RST}: ")" ow </dev/tty
    if [[ "$ow" != "i" && "$ow" != "I" && "$ow" != "y" && "$ow" != "Y" ]]; then
        p_info "Megszakítva — a meglévő .env érintetlen marad."
        exit 0
    fi
    cp "$ENV_FILE" "${ENV_FILE}.backup"
    p_ok "Biztonsági mentés: ${BOLD}.env.backup${RST}"
fi

# ─── Python ────────────────────────────────────────────────────────────────────
if ! PY=$(detect_python); then
    p_err "Python 3 szükséges, de nem található."
    exit 1
fi
p_ok "Python: $(command -v "$PY")"

# ═══════════════════════════════════════════════════════════════════════════════
# PORTS
# ═══════════════════════════════════════════════════════════════════════════════
p_section "Portok"

p_hint "Az URL-ek ezek alapján épülnek fel (FRONTEND_URL, API_URL)."

FRONTEND_PORT=$(ask_port "Frontend  (Angular)" "4200")
API_PORT=$(ask_port      "Backend API  (FastAPI)" "8000")

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════════
p_section "Adatbázis (PostgreSQL)"

DB_NAME=$(ask "POSTGRES_DB"   "adatbázis neve"  "openblend")
DB_USER=$(ask "POSTGRES_USER" "felhasználónév"  "openblend")

echo -e "  ${BOLD}POSTGRES_PASSWORD${RST}  ${DIM}biztonságos jelszó automatikus generálása...${RST}"
DB_PASS=$(gen_password)
p_ok "POSTGRES_PASSWORD generálva"

# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY KEYS
# ═══════════════════════════════════════════════════════════════════════════════
p_section "Biztonsági kulcsok (automatikus generálás)"

echo -e "  ${BOLD}SECRET_KEY${RST}            ${DIM}secrets.token_hex(32)...${RST}"
SECRET_KEY=$(gen_hex_key)
p_ok "SECRET_KEY generálva"

echo -e "  ${BOLD}TOKEN_ENCRYPTION_KEY${RST}  ${DIM}Fernet kulcs generálása...${RST}"
TOKEN_ENC_KEY=$(gen_fernet_key)
p_ok "TOKEN_ENCRYPTION_KEY generálva"

# ═══════════════════════════════════════════════════════════════════════════════
# SPOTIFY
# ═══════════════════════════════════════════════════════════════════════════════
SPOTIFY_ID="your_spotify_client_id"
SPOTIFY_SECRET="your_spotify_client_secret"

if ask_section "Spotify" "Szükséges a token-frissítéshez. App létrehozás: developer.spotify.com/dashboard"; then
    p_hint "→ Spotify Developer Dashboard → Create App → Settings → Client ID + Client Secret"
    val=$(ask "SPOTIFY_CLIENT_ID"     "Client ID"     "" false); SPOTIFY_ID="$val"
    val=$(ask "SPOTIFY_CLIENT_SECRET" "Client Secret" "" false); SPOTIFY_SECRET="$val"
    p_ok "Spotify konfigurálva"
else
    p_skip "Spotify"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# APPLE MUSIC
# ═══════════════════════════════════════════════════════════════════════════════
APPLE_TEAM_ID="your_team_id"
APPLE_KEY_ID="your_key_id"
APPLE_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'
APPLE_STOREFRONT="us"

if ask_section "Apple Music" "App adatok: developer.apple.com/account → Certificates, IDs & Profiles → Keys"; then
    p_hint "→ developer.apple.com → Certificates, IDs & Profiles → Keys → + gomb → MusicKit"

    val=$(ask "APPLE_MUSIC_TEAM_ID" "Team ID (10 karakteres kód)" "" false)
    APPLE_TEAM_ID="$val"

    val=$(ask "APPLE_MUSIC_KEY_ID" "Key ID" "" false)
    APPLE_KEY_ID="$val"

    echo ""
    echo -e "  ${BOLD}APPLE_MUSIC_PRIVATE_KEY${RST}"
    p_hint "Add meg a .p8 fájl elérési útját, vagy illeszd be közvetlenül a kulcs tartalmát."
    p_hint "Fájl esetén a tartalmat automatikusan \\n-re konvertálom."
    pk_input=""
    IFS= read -rp "$(echo -e "  .p8 fájl elérési útja vagy kulcs tartalma: ")" pk_input </dev/tty

    if [[ -n "$pk_input" && -f "$pk_input" ]]; then
        APPLE_PRIVATE_KEY=$(read_p8_file "$pk_input")
        p_ok "Kulcs beolvasva: $pk_input"
    elif [[ -n "$pk_input" ]]; then
        APPLE_PRIVATE_KEY="$pk_input"
        p_ok "Kulcs megadva (közvetlen bemenet)"
    fi

    val=$(ask "APPLE_MUSIC_STOREFRONT" "Storefront ország kód" "us" false)
    APPLE_STOREFRONT="$val"

    p_ok "Apple Music konfigurálva"
else
    p_skip "Apple Music"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# LAST.FM
# ═══════════════════════════════════════════════════════════════════════════════
LASTFM_KEY="your_lastfm_api_key"
LASTFM_SECRET="your_lastfm_shared_secret"

if ask_section "Last.fm" "API fiók: last.fm/api/account/create"; then
    p_hint "→ last.fm/api/account/create → API Key + Shared Secret"
    val=$(ask "LASTFM_API_KEY"       "API Key"       "" false); LASTFM_KEY="$val"
    val=$(ask "LASTFM_SHARED_SECRET" "Shared Secret" "" false); LASTFM_SECRET="$val"
    p_ok "Last.fm konfigurálva"
else
    p_skip "Last.fm"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Z.AI
# ═══════════════════════════════════════════════════════════════════════════════
ZAI_KEY="your_zai_api_key"

if ask_section "Z.ai (GLM-5)" "API kulcs a Z.ai dashboardról (OpenAI-kompatibilis endpoint)"; then
    val=$(ask "ZAI_API_KEY" "API Key" "" false); ZAI_KEY="$val"
    p_ok "Z.ai konfigurálva"
else
    p_skip "Z.ai"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# WRITE .env
# ═══════════════════════════════════════════════════════════════════════════════
> "$TMP_FILE"

wl "# Database"
wkv "POSTGRES_DB"       "$DB_NAME"
wkv "POSTGRES_USER"     "$DB_USER"
wkv "POSTGRES_PASSWORD" "$DB_PASS"
wl ""
wl "# Security — auto-generated"
wkv "SECRET_KEY"            "$SECRET_KEY"
wl "# Fernet key — auto-generated"
wkv "TOKEN_ENCRYPTION_KEY"  "$TOKEN_ENC_KEY"
wl ""
wl "# Spotify (from Spotify Developer Dashboard — only needed for token refresh)"
wkv "SPOTIFY_CLIENT_ID"     "$SPOTIFY_ID"
wkv "SPOTIFY_CLIENT_SECRET" "$SPOTIFY_SECRET"
wl ""
wl "# Apple Music (from Apple Developer Portal)"
wkv "APPLE_MUSIC_TEAM_ID"      "$APPLE_TEAM_ID"
wkv "APPLE_MUSIC_KEY_ID"       "$APPLE_KEY_ID"
wkv "APPLE_MUSIC_PRIVATE_KEY"  "$APPLE_PRIVATE_KEY"
wkv "APPLE_MUSIC_STOREFRONT"   "$APPLE_STOREFRONT"
wl ""
wl "# Last.fm (create app at https://www.last.fm/api/account/create)"
wkv "LASTFM_API_KEY"       "$LASTFM_KEY"
wkv "LASTFM_SHARED_SECRET" "$LASTFM_SECRET"
wl ""
wl "# Z.ai — GLM-5 (OpenAI-compatible endpoint)"
wkv "ZAI_API_KEY" "$ZAI_KEY"
wl ""
wl "# URLs"
wkv "FRONTEND_URL" "http://localhost:${FRONTEND_PORT}"
wkv "API_URL"      "http://localhost:${API_PORT}"

mv "$TMP_FILE" "$ENV_FILE"

# ─── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${G}"
echo "  ╔════════════════════════════════════════════════╗"
echo "  ║      .env fájl sikeresen létrehozva!           ║"
echo "  ╚════════════════════════════════════════════════╝"
echo -e "${RST}"
p_info "Fájl mentve: ${BOLD}${ENV_FILE}${RST}"
echo ""
p_info "Következő lépés:"
echo -e "  ${BOLD}docker compose up --build${RST}"
echo ""
