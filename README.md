# TT-CUP

Turnierbaum-Darstellung (Doppel-KO, 16 Startplätze) für die WTTV-Cup-Bewerbe 2026/27.

- `data/bewerbe.json`: die Bewerbe und ihre WTTV-Liga-IDs
- `tools/fetch.py`: holt die Spiele über die WTTV-API (Schlüssel als GitHub-Secret `WTTV_API_KEY`)
- `.github/workflows/abruf.yml`: läuft zweimal täglich und speichert neue Daten in `data/`

Veröffentlicht werden nur Mannschaftsdaten (Paarungen, Ergebnisse, Termine), keine Spielerdaten.
