# Agenten HQ

Pixel-Büro mit Nicos KI-Agenten. Live: https://nicoklein-nkzsde.github.io/agenten-hq/

- `index.html` – die Seite (GitHub Pages, Branch `main`)
- Live-Status: `status.json` auf dem Branch `status`, kommt vom MacBook
- `hq/hq.py` – meldet den Status (installiert unter `~/Library/Application Support/agenten-hq/`)
  - Claude-Code-Hooks (`UserPromptSubmit`, `Stop`) → Chat-Sessions und Agenten automatisch
  - Agenten melden sich zusätzlich selbst: `hq.py set <agent> working|idle|error "Text"`
  - LaunchAgent `de.nicoklein.agentenhq` → Herzschlag alle 15 Min („Mac wach“)
- `?demo` an die Adresse hängen = Vorschau mit wechselnden Zuständen

Öffentlich sichtbar ist nur: Zustand, kurzer Statustext, Zeiten, Anzahl aktiver Chats.
