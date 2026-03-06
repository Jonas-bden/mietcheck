# MietCheck — Deployment Guide

## Hosting-Optionen im Überblick

| Plattform | Kosten | Setup-Zeit | Empfehlung |
|-----------|--------|------------|------------|
| **Render.com** | ✅ Kostenlos (Free Tier) | 5 Min | ⭐ **Beste Wahl für den Start** |
| **Railway.app** | $5/Mo (500h gratis) | 5 Min | Gut für mehr Traffic |
| **Fly.io** | ✅ Kostenlos (3 VMs free) | 10 Min | Bester Server-Standort (Frankfurt) |
| **Eigener Server** | Ab 3€/Mo (Hetzner) | 15 Min | Volle Kontrolle |
| **Lokal (Mac)** | ✅ Kostenlos | 1 Min | Nur für dich persönlich |

---

## Option 1: Render.com (Empfohlen — Kostenlos)

Der einfachste Weg. Keine Kreditkarte nötig.

### Schritt 1: Repository erstellen
```bash
cd MietCheck-Deploy
git init
git add .
git commit -m "MietCheck v2"
```

### Schritt 2: Auf GitHub pushen
```bash
gh repo create mietcheck --private --push --source=.
```
Oder manuell: GitHub → New Repository → Push.

### Schritt 3: Auf Render deployen
1. Gehe zu **https://render.com** → Sign up (GitHub Login)
2. → **New** → **Web Service**
3. → Dein `mietcheck` Repo verbinden
4. Einstellungen:
   - **Name:** `mietcheck`
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`
5. → **Environment Variables** hinzufügen:
   - `SECRET_KEY` = (beliebiger langer String)
   - `ADMIN_USER` = `admin`
   - `ADMIN_PASS` = `dein-sicheres-passwort`
6. → **Create Web Service**

Fertig. Deine App läuft unter `https://mietcheck.onrender.com`

**Achtung Free Tier:** Der Server schläft nach 15 Min Inaktivität ein. Erster Aufruf dauert dann ~30 Sek. Für 7$/Mo bekommst du "Always On".

---

## Option 2: Fly.io (Kostenlos — Server in Frankfurt)

Beste Performance für Deutschland. Server steht in Frankfurt.

```bash
# Fly CLI installieren
brew install flyctl

# Account erstellen & einloggen
fly auth signup

# App deployen (aus dem MietCheck-Deploy Ordner)
fly launch --name mietcheck --region fra --no-deploy

# Passwort setzen
fly secrets set SECRET_KEY="dein-geheimer-key" ADMIN_USER="admin" ADMIN_PASS="dein-passwort"

# Persistenten Speicher anlegen (für data.json)
fly volumes create mietcheck_data --region fra --size 1

# Deployen
fly deploy
```

Deine App läuft unter `https://mietcheck.fly.dev`

---

## Option 3: Eigener Server (Hetzner — ab 3,29€/Mo)

Volle Kontrolle, eigene Domain möglich.

### Server bestellen
1. **https://hetzner.cloud** → Cloud Server → CX22 (2 vCPU, 4GB RAM) = 3,29€/Mo
2. Ubuntu 22.04 wählen → SSH-Key hinterlegen

### Auf dem Server
```bash
# Docker installieren
curl -fsSL https://get.docker.com | sh

# App klonen
git clone https://github.com/DEIN_USER/mietcheck.git
cd mietcheck

# .env erstellen
cp .env.example .env
nano .env  # Passwort etc. anpassen

# Starten
docker compose up -d
```

Läuft auf `http://DEINE-SERVER-IP:5050`

### HTTPS mit eigener Domain (Optional)
```bash
# Caddy als Reverse Proxy (automatisches HTTPS)
apt install caddy
echo "mietcheck.deine-domain.de {
    reverse_proxy localhost:5050
}" > /etc/caddy/Caddyfile
systemctl restart caddy
```

---

## Option 4: Lokal auf dem Mac

Für persönliche Nutzung — kein Internet nötig.

```bash
cd MietCheck-Deploy
pip3 install -r requirements.txt
python3 app.py
```

Öffne `http://localhost:5050` — fertig.

---

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `SECRET_KEY` | dev-key | Session-Verschlüsselung (in Produktion ändern!) |
| `ADMIN_USER` | admin | Login-Benutzername |
| `ADMIN_PASS` | mietcheck2026 | Login-Passwort |
| `PORT` | 5050 | Server-Port |
| `DATA_DIR` | . | Verzeichnis für data.json |

---

## Anderen Zugang geben

1. Deploy auf Render/Fly/Hetzner (s.o.)
2. Teile die URL + Login-Daten
3. Fertig — jeder mit Login kann die App nutzen

Für **mehrere getrennte Nutzer** (z.B. verschiedene Vermieter mit eigenen Portfolios):
→ Dann braucht es eine DB statt JSON. Sag Bescheid, dann baue ich das um.
