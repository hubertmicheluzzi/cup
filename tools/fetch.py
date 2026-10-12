#!/usr/bin/env python3
"""Holt die Cup-Daten aller Bewerbe über die WTTV-API und legt sie als JSON ab.

- Der API-Schlüssel kommt aus der Umgebungsvariable WTTV_API_KEY (GitHub-Secret)
  und wird nie ausgegeben oder gespeichert.
- Gespeichert werden nur Mannschafts-Daten (Paarungen, Ergebnisse, Termine),
  keine Spielerdaten.
- data/<id>.json   : aufbereitete Spiele je Bewerb
- data/raw/<id>.xml: Rohantwort ohne Spieler-Elemente (zur Kontrolle der Zuordnung)
"""
import json, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BASE = "https://oettv.xttv.at/xml/v1/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("WTTV_API_KEY", "").strip()


def call(method, **params):
    q = urllib.parse.urlencode({"apikey": KEY, **params})
    req = urllib.request.Request(BASE + method + ".php?" + q, headers={"User-Agent": "tt-cup/1 (github actions)"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # Schlüssel steckt in der URL: Fehlermeldung ohne URL ausgeben
            last = type(e).__name__ + (": HTTP %s" % e.code if hasattr(e, "code") else "")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{method} fehlgeschlagen ({last})")


def txt(el, tag):
    v = el.find(tag)
    return (v.text or "").strip() if v is not None and v.text else ""


def num(el, tag):
    v = txt(el, tag)
    try:
        return int(v)
    except ValueError:
        return None


def strip_players(root):
    for parent in root.iter():
        for child in list(parent):
            if child.tag in ("player", "double_player", "players", "doubles"):
                parent.remove(child)


def main():
    if not KEY:
        sys.exit("WTTV_API_KEY fehlt (GitHub: Settings > Secrets and variables > Actions).")
    cfg = json.load(open(os.path.join(DATA, "bewerbe.json"), encoding="utf-8"))
    os.makedirs(os.path.join(DATA, "raw"), exist_ok=True)
    stand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = 0
    for b in cfg["bewerbe"]:
        lid = b["leagueId"]
        try:
            raw = call("getLeagueResults", leagueId=lid)
            root = ET.fromstring(raw)
            strip_players(root)
            ET.ElementTree(root).write(os.path.join(DATA, "raw", b["id"] + ".xml"), encoding="utf-8", xml_declaration=True)
            spiele = []
            for g in root.iter("game"):
                spiele.append({
                    "gameId": num(g, "game_id"),
                    "runde": num(g, "round_nr"),
                    "rundeName": txt(g, "round_name"),
                    "periode": num(g, "period_nr"),
                    "datum": txt(g, "date"),
                    "zeit": txt(g, "time"),
                    "heim": txt(g, "team_home_code") or txt(g, "team_home_short_name"),
                    "gast": txt(g, "team_away_code") or txt(g, "team_away_short_name"),
                    "heimName": txt(g, "team_home_short_name"),
                    "gastName": txt(g, "team_away_short_name"),
                    "heimVerein": txt(g, "club_home"),
                    "gastVerein": txt(g, "club_away"),
                    "gespielt": txt(g, "played") == "1",
                    "bestaetigt": txt(g, "confirmed") == "1",
                    "punkteHeim": num(g, "matches_won_home"),
                    "punkteGast": num(g, "matches_won_away"),
                })
            teams = []
            try:
                troot = ET.fromstring(call("getLeagueTeams", leagueId=lid))
                for t in troot.iter("team"):
                    teams.append({"id": num(t, "id"), "code": txt(t, "code"), "verein": txt(t, "club_name")})
            except Exception as e:
                print(f"  {b['name']}: Mannschaftsliste nicht abrufbar ({e})")
            out = {"format": "tt-cup-wttv/1", "stand": stand, "bewerb": b, "mannschaften": teams, "spiele": spiele}
            path = os.path.join(DATA, b["id"] + ".json")
            old = None
            if os.path.exists(path):
                old = json.load(open(path, encoding="utf-8"))
                old.pop("stand", None)
            cmp = dict(out); cmp.pop("stand")
            if old != cmp:
                json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(f"  {b['name']}: {len(spiele)} Spiele, {len(teams)} Mannschaften (aktualisiert)")
            else:
                print(f"  {b['name']}: {len(spiele)} Spiele (unverändert)")
            ok += 1
        except Exception as e:
            print(f"  {b['name']}: FEHLER {e}")
    print(f"{ok} von {len(cfg['bewerbe'])} Bewerben abgerufen")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
