# Morgen-Briefing

Privates News-Dashboard mit drehbarem 3D-Globus. Zeigt täglich aktuelle
Meldungen aus den Bereichen Politik, Wirtschaft, Kriege & Konflikte,
Weltgeschehen und Sport, jeweils mit Marker auf dem Globus am Ort des
Geschehens.

## Wie es funktioniert

- `index.html` – das Dashboard selbst (Globus + Kategorie-Listen)
- `news.json` – die aktuellen Nachrichtendaten, wird täglich automatisch neu erzeugt
- `scripts/fetch_news.py` – holt Nachrichten von RSS-Feeds und schreibt `news.json`
- `.github/workflows/update-news.yml` – GitHub Action, die das Script jeden Morgen um 06:00 Uhr (Europe/Berlin) automatisch ausführt und die aktualisierten Daten committet

## Neue Kategorie hinzufügen (z.B. weitere Themen)

In `scripts/fetch_news.py` im `CATEGORIES`-Array einen neuen Eintrag ergänzen:

```python
{
    "id": "meine-kategorie",
    "label": "Meine Kategorie",
    "color": "#xxxxxx",
    "feeds": ["https://beispiel.de/rss.xml"],
}
```

Das Dashboard übernimmt neue Kategorien automatisch, kein Frontend-Code nötig.

## Setup (einmalig)

1. Repo auf GitHub veröffentlichen (public, damit GitHub Pages kostenlos funktioniert)
2. Unter **Settings → Pages** → Source: "Deploy from a branch" → Branch `main` / `(root)` auswählen
3. Unter **Settings → Actions → General → Workflow permissions** → "Read and write permissions" aktivieren (damit die Action `news.json` committen darf)
4. Optional: unter **Actions** den Workflow "Update news daily" einmal manuell über "Run workflow" starten, um sofort echte Daten zu bekommen
