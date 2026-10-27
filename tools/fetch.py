#!/usr/bin/env python3
"""Holt die Cup-Daten aller Bewerbe über die WTTV-API und legt sie als JSON ab.

- Der API-Schlüssel kommt aus der Umgebungsvariable WTTV_API_KEY (GitHub-Secret)
  und wird nie ausgegeben oder gespeichert.
- Gespeichert werden Mannschafts-Daten (Paarungen, Ergebnisse, Termine) und
  seit 27.10.2026 die Einzelspiele gespielter Paarungen: Spieler NUR MIT
  VORNAMEN, keine Nachnamen, keine Passnummern (Entscheidung Hubert).
  Quelle der Einzelspiele: der öffentliche XTTV-Spielbericht
  (oettv.xttv.at/ed/index.php?meid=<gameId>), kein API-Schlüssel nötig.
  Bereits geholte Einzelspiele werden wiederverwendet, solange sich das
  Ergebnis der Paarung nicht geändert hat.
- data/<id>.json   : aufbereitete Spiele je Bewerb (mit "einzel" je gespieltem Spiel)
- data/raw/<id>.xml: Rohantwort ohne Spieler-Elemente (zur Kontrolle der Zuordnung)
"""
import json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BASE = "https://oettv.xttv.at/xml/v1/"
BERICHT = "https://oettv.xttv.at/ed/index.php?meid={}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("WTTV_API_KEY", "").strip()
UA = {"User-Agent": "tt-cup/1 (github actions)"}


def call(method, **params):
    q = urllib.parse.urlencode({"apikey": KEY, **params})
    req = urllib.request.Request(BASE + method + ".php?" + q, headers=UA)
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


# ---------------------------------------------------------------- Einzelspiele
def holen_html(url):
    req = urllib.request.Request(url, headers=UA)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                roh = r.read()
            m = re.search(rb'charset=["\']?([A-Za-z0-9_\-]+)', roh[:4000])
            for cs in ([m.group(1).decode()] if m else []) + ["utf-8", "windows-1252"]:
                try:
                    return roh.decode(cs)
                except (LookupError, UnicodeDecodeError):
                    pass
            return roh.decode("windows-1252", errors="replace")
        except Exception as e:
            last = type(e).__name__
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Spielbericht nicht abrufbar ({last})")


def _zeilen(fragment):
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ").replace("\xa0", " ")
    return [re.sub(r"\s+", " ", z).strip() for z in t.split("\n") if z.strip()]


def vorname(name):
    """'Nachname Vorname' -> 'Vorname' (öffentlich nur Vornamen)."""
    teile = re.sub(r"\b(sen|jun)\.?$", "", (name or "").strip()).split()
    return teile[-1] if teile else "?"


def _spieler(td):
    """-> ('H'|'G', 'Einzel'|'Doppel', 'Vorname' bzw. 'Vorname / Vorname') oder None"""
    m = re.search(r'<div class="(heimSpieler|gastSpieler)">(.*?)</div>', td, re.S)
    if not m:
        return None
    z = _zeilen(m.group(2))
    seite = "H" if m.group(1) == "heimSpieler" else "G"
    if z and re.match(r"^[A-Z0-9]+:\s*Passnr\.", z[0]) and len(z) >= 2:
        return seite, "Einzel", vorname(z[1])
    if z and z[0].startswith("Doppel") and len(z) >= 4:
        return seite, "Doppel", " / ".join(vorname(n) for n in z[2:4])
    return None


def einzelspiele(game_id):
    """Einzel/Doppel einer Paarung: [{nr, art, heim, gast, saetze (Heim:Gast), sieger}]"""
    html = holen_html(BERICHT.format(game_id))
    reihen = re.findall(r'<tr class="spb-spiele">(.*?)</tr>', html, re.S)
    if not reihen:
        return []
    tds = lambda reihe: re.findall(r"<td[^>]*>(.*?)</td>", reihe, re.S)
    spalten = [_spieler(td) for td in tds(reihen[0])[1:]]
    out = []
    for reihe in reihen[1:]:
        zellen = tds(reihe)
        if not zellen:
            continue
        zeile = _spieler(zellen[0])
        if not zeile:
            continue
        for j, td in enumerate(zellen[1:]):
            m_nr = re.search(r'<div class="spielNummer">\((.*?)\)</div>', td)
            m_e = re.search(r'<div class="spielErgebnis">\s*(\d+)\s*:\s*(\d+)\s*</div>', td)
            m_s = re.search(r'<div class="spielSieger(Heim|Gast)">', td)
            if not (m_nr and m_e and m_s) or j >= len(spalten) or not spalten[j]:
                continue
            seiten = {zeile[0]: zeile, spalten[j][0]: spalten[j]}
            if set(seiten) != {"H", "G"}:
                continue
            a, b = int(m_e.group(1)), int(m_e.group(2))
            hoch, tief = max(a, b), min(a, b)
            sieger = "H" if m_s.group(1) == "Heim" else "G"
            out.append({
                "nr": m_nr.group(1).strip(),
                "art": seiten["H"][1],
                "heim": seiten["H"][2],
                "gast": seiten["G"][2],
                "saetze": f"{hoch}:{tief}" if sieger == "H" else f"{tief}:{hoch}",
                "sieger": sieger,
            })
    out.sort(key=lambda e: _nr_wert(e["nr"]))
    return out


def _nr_wert(nr):
    """Spielnummer sortierbar: '3' -> 3, 'IV' -> 4, 'IIIA' -> 3.5"""
    if nr.isdigit():
        return int(nr)
    zusatz = 0.5 if nr.endswith("A") else 0
    rom = {"I": 1, "V": 5, "X": 10}
    s = nr.rstrip("A")
    wert = 0
    for i, c in enumerate(s):
        v = rom.get(c, 0)
        wert += -v if i + 1 < len(s) and rom.get(s[i + 1], 0) > v else v
    return wert + zusatz


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

            path = os.path.join(DATA, b["id"] + ".json")
            old = None
            if os.path.exists(path):
                old = json.load(open(path, encoding="utf-8"))
                old.pop("stand", None)

            # Einzelspiele: wiederverwenden, solange das Ergebnis gleich ist; sonst Spielbericht lesen
            alt_einzel = {}
            for og in (old or {}).get("spiele", []):
                if og.get("einzel") is not None:
                    alt_einzel[og.get("gameId")] = (og.get("punkteHeim"), og.get("punkteGast"), og["einzel"])
            neu_gelesen = 0
            for s in spiele:
                if not (s["gespielt"] and s["gameId"]):
                    continue
                vorher = alt_einzel.get(s["gameId"])
                if vorher and vorher[0] == s["punkteHeim"] and vorher[1] == s["punkteGast"]:
                    s["einzel"] = vorher[2]
                    continue
                try:
                    s["einzel"] = einzelspiele(s["gameId"])
                    neu_gelesen += 1
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  {b['name']}: Einzelspiele zu {s['heim']}-{s['gast']} nicht lesbar ({e})")
                    if vorher:
                        s["einzel"] = vorher[2]

            out = {"format": "tt-cup-wttv/1", "stand": stand, "bewerb": b, "mannschaften": teams, "spiele": spiele}
            cmp = dict(out); cmp.pop("stand")
            if old != cmp:
                json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(f"  {b['name']}: {len(spiele)} Spiele, {len(teams)} Mannschaften, "
                      f"{neu_gelesen} Spielberichte neu gelesen (aktualisiert)")
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
