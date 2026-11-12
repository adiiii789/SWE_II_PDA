# EVE

Enhanced Virtual Entity

Desktop-Anwendung für macOS und Windows: Ein Klick auf das Symbol öffnet ein Popup mit einem
**Anzeigebereich** (oben) und einem **Chat mit einem Assistenten** (unten). Rechtsklick öffnet
das Kontextmenü mit „Proaktive Meldung testen“ und „Beenden“.

Das Projekt ist die **Grundlage** für einen persönlichen Assistenten mit Gemini als
Sprachmodell (wahlweise lokal mit Ollama). Er hat drei **Fähigkeiten**: Morning-Briefing,
Weg zum nächsten Termin (Travel) und Organisation von Nachrichten und Terminen (im Projektplan
„Assistant²“). Umgesetzt ist der **Reise-Assistent** (siehe unten); Morning-Briefing und
Organisation folgen. Außerdem nutzt der Assistent Werkzeuge von **MCP-Servern** (eingetragen in
[mcp_servers.json](mcp_servers.json)): E-Mail, Google Kalender und Google Tasks. Feste Befehle wie
`hilfe`, `uhrzeit`, `system`, `start`, `neu` und `reise` funktionieren auch ohne Modell.

## Starten

Python 3.12 oder 3.13 verwenden. Auf beiden Betriebssystemen startet dieselbe `main.py`;
die Plattform wird automatisch erkannt. Unter macOS erscheint das Symbol oben in der
Menüleiste, unter Windows unten im Infobereich. Ein Klick öffnet bzw. schließt das Popup.

### macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Danach kann auch `Start.command` per Doppelklick verwendet werden. Die Anwendung bleibt
im Hintergrund aktiv und hat auf dem Mac kein zusätzliches Dock-Symbol. Das Popup öffnet
sich unter dem Menüleistensymbol und bleibt auch beim Vergrößern im sichtbaren Bildschirm.
Die genaue Symbolposition bestimmt die Anordnung der Menüleiste; bei wenig Platz neben
der Notch können Symbole verborgen sein.

### Windows

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Danach kann auch `Start.bat` verwendet werden. Das Popup öffnet sich oberhalb des Symbols.

### PyCharm

Als Projektinterpreter die lokale Umgebung auswählen: `.venv/bin/python` am Mac bzw.
`.venv\Scripts\python.exe` unter Windows. Dann `main.py` starten.

### Sprachmodell

Standardmäßig verwendet der Assistent **Gemini 3.5 Flash-Lite** über die Google Gemini API.
Erstelle in [Google AI Studio](https://aistudio.google.com/api-keys) einen API-Schlüssel.
Speichere ihn als einzige Zeile in `gemini-api-key.txt` im App-Datenordner, außerhalb des Git-Projekts.
Die Datei ist Klartext und sollte nur für dein Benutzerkonto lesbar sein.

- macOS: `~/Library/Application Support/PersonalDigitalAgent/gemini-api-key.txt`
- Windows: `%APPDATA%\PersonalDigitalAgent\gemini-api-key.txt`

Auf macOS kannst du den Schlüssel im Terminal verdeckt einfügen und mit Enter speichern:

```zsh
(
  umask 077
  dir="$HOME/Library/Application Support/PersonalDigitalAgent"
  mkdir -p "$dir" || exit
  read -rs "key?Gemini-API-Schlüssel: "
  printf '\n'
  if [[ -n "$key" ]]; then
    printf '%s\n' "$key" > "$dir/gemini-api-key.txt"
    chmod 600 "$dir/gemini-api-key.txt"
  fi
)
```

Alternativ liest das Programm die Umgebungsvariable `GEMINI_API_KEY`. Sie hat Vorrang
vor der Datei und wird nicht an MCP-Server weitergegeben. Welche Modelle dein Konto nutzen kann,
hängt von den [Kontingenten deines Projekts](https://ai.google.dev/gemini-api/docs/rate-limits) ab.
Bei Gemini gehen Gesprächskontext und benötigte Werkzeugergebnisse (z. B. gelesene Mails) an Google.

### Modellauswahl und Ollama

Im Popup links neben dem Eingabefeld oder per Chat lässt sich das Modell wechseln; die Wahl bleibt
gespeichert. `modelle` zeigt alle Modelle, `modell gemini-3.5-flash` wechselt. Zur Auswahl stehen
Gemini 3.5 Flash-Lite, 3.5 Flash und 3.8 Flash sowie alle **lokal** in [Ollama](https://ollama.com)
installierten Modelle (Präfix `ollama/` bzw. `gemini/`, falls ein Name doppelt vorkommt). Gemini und
Ollama führen getrennte Gesprächsverläufe. `PDA_GEMINI_MODEL` fügt eine weitere Gemini-Modell-ID
hinzu und legt die Vorgabe fest, solange noch kein Modell gespeichert ist.

Für Ollama die Ollama-App oder `ollama serve` starten und ein Modell mit Tool-Calling laden
(z. B. `ollama pull qwen3:8b`). Cloud-Modelle von ollama.com werden nicht angeboten.
Nur einen Anbieter verwenden: `PDA_ASSISTANT_BACKEND=gemini` bzw. `=ollama`.

Nur feste Befehle, ohne Sprachmodell:

```sh
# macOS
PDA_ASSISTANT_BACKEND=commands .venv/bin/python main.py
```

```bat
rem Windows
set PDA_ASSISTANT_BACKEND=commands
.venv\Scripts\python main.py
```

### Sprache

Rechts neben dem Eingabefeld startet 🎤 die Spracheingabe, ein zweiter Klick sendet die Nachricht,
**Escape** bricht ab. Antworten auf gesprochene Nachrichten werden vorgelesen (Escape stoppt das
Vorlesen). Aufnahme, Spracherkennung und Sprachausgabe laufen lokal; der transkribierte Nachrichtentext
geht bei Verwendung von Gemini zur Beantwortung an Google:

- Spracherkennung: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Modell `small`
  (≈ 480 MB)
- Sprachausgabe: [Piper](https://github.com/OHF-Voice/piper1-gpl), Stimme `de_DE-pavoque-low`
  (≈ 60 MB); geht Piper nicht, eine installierte macOS-Stimme bzw. die eingebaute Windows-Stimme

Modell und Stimme werden beim ersten Gebrauch im Datenordner unter `speech` geladen,
die erste Aufnahme dauert deshalb länger. Die macOS-Ersatzstimme benötigt keinen Modelldownload.
Beim ersten Klick auf das Mikrofon fragt macOS nach der Aufnahmefreigabe. Wird sie abgelehnt,
kann sie unter Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon geändert werden;
beim Start aus PyCharm kann die Freigabe PyCharm oder Python zugeordnet sein. Andere Größen und Stimmen über
`PDA_WHISPER_MODEL` (`tiny`, `base`, `medium` …), `PDA_PIPER_VOICE` und `PDA_SPEECH_LANGUAGE`
(siehe [config.py](backend/config.py)). `PDA_MAC_VOICE` legt optional eine installierte Mac-Stimme fest.

### Keys und Zugangsdaten (`.env`)

Alle API-Keys und Zugangsdaten stehen in **einer** Datei `.env` im Projektordner:
[.env.example](.env.example) nach `.env` kopieren und ausfüllen. Die `.env` steht in
`.gitignore` und wird nicht eingecheckt. Gelesen wird sie von [backend/config.py](backend/config.py)
(App, Reise-Assistent) und von den Mail-Werkzeugen in `mcp_servers/`. Gesetzte
Umgebungsvariablen haben Vorrang vor der Datei. Nach einer Änderung die App neu starten;
Mail-Einstellungen wirken sofort. Auch die übrigen `PDA_…`-Einstellungen (Sprache, proaktive
Meldungen, Modell) lassen sich dort setzen.

### Reise-Assistent

„Wie komme ich zum nächsten Termin?“ – oder der feste Befehl `reise`. Der Assistent nimmt den
nächsten Termin mit Ort aus Google Calendar. Start ist der Ort des vorigen Termins, beim ersten
Termin des Tages die Heimatadresse (fragt der Assistent beim ersten Mal ab). Verglichen werden
Auto, Bahn/ÖPNV (mit Bus und Tram), Taxi, Fahrrad und zu Fuß; empfohlen wird das Verkehrsmittel mit den
geringsten **Kosten = Preis + Reisezeit × Zeitwert × Wetterfaktor** (Standard 25 €/h) – Zeit zählt
also mit. **Kostenlose Verkehrsmittel** (zu Fuß, Fahrrad, mit Deutschlandticket auch Bus und Bahn)
stehen grundsätzlich vorn – außer Rad und zu Fuß bei schlechtem Wetter; wäre nach Kosten etwas anderes
besser, sagt die Ansicht das dazu. Die Ansicht hat **je Verkehrsmittel einen Reiter** (zuerst ist die
Empfehlung gewählt; auch ein Klick auf eine Zeile der Vergleichstabelle wählt) mit Zeiten, Preis,
Wegbeschreibung und Karte. **Bus und Bahn** sehen aus wie in der DB- bzw. VVS-App: oben Abfahrt –
Ankunft, Dauer, Umstiege und ein Balken aus den Etappen in Linienfarben, darunter die Zeitleiste mit
Soll-Zeit und Prognose (grün pünktlich, rot verspätet), Gleis/Steig, Linie mit Richtung,
aufklappbaren Zwischenhalten, Hinweisen, Fußwegen und Umstiegszeiten. Die Karte zeigt jede Fahrt in
der Farbe ihrer Linie, Fußwege gepunktet, Umstiege gelb. Die OpenStreetMap-Kacheln holt das
Backend und bettet sie ein, jede nur einmal für alle Karten – das iframe lädt selbst nichts aus dem
Netz; gespeichert werden sie zwei Wochen in `map_tiles/` im App-Datenordner. Ohne Netz bleibt die
Linie ohne Karte.

- **Heimweg:** Steht heute kein Termin mit Ort mehr an, zeigt `reise` den Weg vom letzten Termin
  nach Hause, mit Abfahrt zum Terminende – bis 3 Stunden danach, dann wieder den nächsten Termin.
  Im Chat geht auch „Wie komme ich heim?“ (Werkzeug `plan_trip_home`).
- **Erinnerung:** 15 Minuten vor der empfohlenen Abfahrt meldet sich EVE von selbst – wie die
  proaktiven Meldungen als Popup, Systembenachrichtigung oder nur im Chat, auf Wunsch vorgelesen.
  Das gilt auch für den Heimweg, also z. B. 15 Minuten vor Ende des letzten Termins.
- **Wetter:** Bei Regen oder Schnee zählt die Zeit auf dem Rad und zu Fuß doppelt, bei Kälte und
  (nur Rad) starkem Wind zusätzlich ×1,3. So gewinnt bei Regen eher Auto oder Bahn. Die Vorhersage
  kommt von Open-Meteo, für den Startort zur Abfahrt.
- **Bahn/ÖPNV:** Liegen Start und Ziel im **VVS-Gebiet** (Stuttgart und Umland), fragt der
  Assistent die **VVS-Auskunft** – mit Echtzeit, Gleisen/Steigen und dem echten Preis
  (EinzelTicket Erwachsene; mit Deutschlandticket 0 €). Sonst sucht er bei
  **[Transitous](https://transitous.org)** – wie im DB Navigator von Tür zu Tür, mit Bus, Tram,
  S-Bahn und Fernzügen, deutschlandweit. Beide ohne Key. Hat der VVS keine Verbindung oder ist nicht
  erreichbar, kommt Transitous dran. Erlaubt sind **bis zu zwei Umstiege** (einstellbar: 0 bis 3, je mindestens 5 Minuten); ein
  Umstieg zählt beim Vergleich wie 10 Minuten mehr Fahrzeit. Transitous ist ein ehrenamtliches
  Projekt für nicht-kommerzielle Nutzung, ohne Garantie und mit Echtzeit nur, wo Verbünde sie
  liefern. Fällt es aus oder findet nichts, sucht der Assistent wie früher über die DB-Tafeln (nur
  Züge, siehe unten). Abschalten bzw. eigene MOTIS-Instanz: `PDA_TRANSITOUS_URL`, VVS abschalten:
  `PDA_VVS_URL=` in der `.env`. Die VVS-Auskunft ist die Schnittstelle der VVS-Website (EFA) ohne
  dokumentierte Nutzungsbedingungen; die offizielle für Baden-Württemberg wäre TRIAS über
  [MobiData BW](https://mobidata-bw.de/dataset/trias) (Zugang auf Antrag).

**Einstellungen:** alles unter ⚙ Einstellungen → **Reise**:
- **Allgemein:** Heimatadresse, welche Verkehrsmittel verglichen werden (z. B. ohne Auto),
  „Kostenlose Verkehrsmittel zuerst“ (Standard an, optional nur bis zu einer Mehrdauer in Minuten),
  Zeitwert, Puffer vor dem Termin
- **Bus und Bahn:** Deutschlandticket, Umstiege (0–3), Umsteigezeit, längster Fußweg zur Haltestelle
- **Auto und Taxi**, **Fahrrad und zu Fuß**, **Wetter**, **Erinnerung und Heimweg**
- **Preise schätzen:** nur wo die Auskunft keinen Preis kennt (außerhalb des VVS)

Gruppen, deren Dienst keinen Key hat, sind als „gerade nicht verfügbar“ markiert.

Einrichtung – ohne Key fällt nur der betroffene Teil weg:

| Was | Wofür | Einrichtung |
|---|---|---|
| openrouteservice (Pflicht) | Adressen, Routen und Fahrzeiten für Auto, Taxi, Fahrrad, zu Fuß | kostenloser Key: [openrouteservice.org](https://openrouteservice.org/dev/#/signup) → `PDA_ORS_KEY` in der `.env` |
| VVS-Auskunft | ÖPNV im VVS-Gebiet mit Echtzeit und Preis | nichts – ohne Key |
| Transitous | Bahn/ÖPNV-Verbindungen mit Bus und Tram | nichts – kostenlos und ohne Key ([Nutzungsregeln](https://transitous.org/api/): nicht-kommerziell) |
| DB API Marketplace | Bahn-Ersatz, wenn Transitous ausfällt (Fahrplan mit Echtzeit); Bahnhöfe | kostenlos: [developers.deutschebahn.com](https://developers.deutschebahn.com) → Anwendung anlegen, die APIs „OpenBoards“ (Tafeln mit Verspätungen und Störungen), „StaDa - Station Data“ (Bahnhöfe mit Koordinaten) und „Timetables“ (Ersatz) abonnieren → `PDA_DB_CLIENT_ID` und `PDA_DB_API_KEY` in der `.env` |
| Google Calendar | Termine | dieselbe Anmeldung wie die Kalender-Werkzeuge, Einrichtung unter [Google Kalender](#google-kalender) |
| Tankerkönig | aktuelle Spritpreise (sonst 1,80 €/l) | kostenloser Key: [creativecommons.tankerkoenig.de](https://creativecommons.tankerkoenig.de) → `PDA_TANKERKOENIG_KEY` in der `.env` |
| Open-Meteo | Wetter | nichts – kostenlos und ohne Key |

Alle Dienste sind kostenlos. **Grenzen:** openrouteservice kennt keinen Echtzeit-Verkehr; die
Autofahrzeit wird deshalb mit einem Stau-Aufschlag (Standard 1,15) verlängert. Die
DB-APIs (Ersatz für Transitous) liefern nur Abfahrts- und Ankunftstafeln, keine Verbindungssuche: Der Assistent setzt
Verbindungen aus den Laufwegen der Züge selbst zusammen, mit **höchstens drei Umstiegen**, zwischen
den Bahnhöfen der beiden Orte (Hauptbahnhof bevorzugt) und nur für die nächsten Stunden. Als
Umstiegsbahnhöfe prüft er je Umstieg zwei bis drei: zuerst die, an denen sich Züge ab dem Start und
Züge zum Ziel kreuzen (meist die großen Knoten), sonst die größten Bahnhöfe ungefähr auf dem Weg
(Kategorie und Lage aus StaDa) – deren Tafeln verbinden dann beim nächsten Umstieg. Mit **OpenBoards** rechnet er mit den Prognosezeiten: Verspätete Züge, die zu spät
ankommen, und geplatzte Anschlüsse fallen weg, ausgefallene Halte ebenso; Verspätungen („09:37 (+5)“)
und Störungstexte stehen in der Wegbeschreibung. Ist OpenBoards nicht abonniert oder gestört, sucht
er im Soll-Fahrplan von Timetables und sagt das in den Hinweisen. **Bahnhof zur Adresse:** aus der
StaDa-Liste aller Bahnhöfe (einmal pro Woche geladen, gespeichert in `db_stations.json` im
App-Datenordner) der nächste – ein großer Bahnhof darf etwas weiter weg sein als ein kleiner Halt.
Findet die Suche ab dort nichts, versucht sie es ab den nächsten großen Bahnhöfen (z. B. Heidelberg Hbf
statt Schwetzingen). Ohne StaDa sucht sie den Bahnhof über den Ortsnamen (Timetables), was bei Namen
wie „Freiburg(Breisgau) Hbf“ oft danebengeht. Busse und Straßenbahnen kennt er nicht: Ist der Bahnhof mehr
als 20 Minuten Fußweg entfernt, schätzt er die Zeit für Bus/Tram. **Bahnpreise** gibt die DB nicht
heraus, sie sind eine Tarif-Schätzung (mit ≈ markiert). Mit Deutschlandticket kostet der
Nahverkehr nichts. Das Wetter zählt nur für Fahrrad und zu Fuß, nicht für die Fußwege zum Bahnhof.

Gespeichert wird in `preferences.json` im App-Datenordner (unter `travel_settings`, die
Heimatadresse unter `travel_home_address`). Ältere, von Hand eingetragene Werte wie
`"travel_value_of_time": 40` gelten weiter, die Werte aus den Einstellungen haben Vorrang.
„Standard wiederherstellen“ setzt alles zurück außer der Heimatadresse.

### MCP-Server einbinden

In [mcp_servers.json](mcp_servers.json) eintragen – dasselbe Format wie bei Claude Desktop, sodass
sich Einträge aus den Anleitungen fertiger Server meist direkt übernehmen lassen:

```json
{
  "mcpServers": {
    "pda":        { "command": "python", "args": ["mcp_servers/pda_server.py"] },
    "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"] }
  }
}
```

Unterstützt werden Server über **stdio** (Unterprozess). `"python"` startet dasselbe Python, mit
dem das Programm läuft; `"disabled": true` schaltet einen Eintrag ab. Nach Änderungen das
Programm neu starten.

Der eigene Server ist [mcp_servers/pda_server.py](mcp_servers/pda_server.py), geschrieben mit dem
offiziellen MCP-SDK. Er bietet `get_current_time`, `calculate`, `send_email`, `list_emails`, `read_email`,
`read_attachment`, `reply_email`, `save_email_draft`, `organize_email`, `delete_email`,
`list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`,
`find_free_time`, `respond_to_calendar_invitation`, `list_tasks`, `create_task`, `update_task`,
`complete_task`, `delete_task`, `move_task` und `create_task_list`. Ein neues Tool ist dort eine
Funktion mit `@mcp.tool()`. Mit `mcp dev mcp_servers/pda_server.py` lässt er sich ohne Assistent im
Browser ausprobieren. Werkzeuge mit dem Präfix `watch_` sind nur für den Wächter (siehe
[Proaktive Meldungen](#proaktive-meldungen)) und für das Sprachmodell unsichtbar.

**Rückfrage bei riskanten Aktionen:** Löschen von Aufgaben, Termine ändern oder löschen, Einladungen
beantworten und Mails löschen führt der Assistent erst aus, wenn deine nächste Nachricht zustimmt
(z. B. „ja“). Das ist fest eingebaut und nicht abschaltbar: So kann Text aus einer fremden Mail oder
Einladung nichts allein auslösen.

#### E-Mail

In der `.env` (siehe [Keys und Zugangsdaten](#keys-und-zugangsdaten-env)) SMTP-Zugang sowie
die erlaubten Empfänger (`PDA_MAIL_RECIPIENTS`) eintragen. Bei Gmail braucht ihr ein App-Passwort.
Der Assistent kann nur an diese Adressen schreiben. Steht ein Name davor
(`Mama <mama@example.com>, Anna Müller <anna@example.com>`), reicht beim Senden der Name („schick
Anna eine Mail …“). Mails unterschreibt der Assistent mit „EVE“.

Zum **Lesen** (IMAP) reicht das meist schon: Der IMAP-Server wird aus dem SMTP-Server abgeleitet
(`smtp.gmail.com` → `imap.gmail.com`), Login und App-Passwort werden übernommen. Abweichend lässt
sich alles mit `PDA_IMAP_HOST`, `PDA_IMAP_PORT`, `PDA_IMAP_USER`, `PDA_IMAP_PASSWORD` setzen.
Lesen ändert nichts, Mails bleiben dabei ungelesen. Auf Wunsch beantwortet der Assistent Mails im selben
Verlauf (nur an freigegebene Empfänger), legt Entwürfe im Postfach ab (an jede Adresse, abgeschickt wird
nichts), markiert Mails als gelesen oder ungelesen und archiviert sie. Löschen verschiebt nur in den
Papierkorb. Beim Senden lassen sich Dateien aus Downloads, Dokumente, Desktop, Bilder und OneDrive
sowie Anhänge gelesener Mails anhängen.

**Anhänge** erscheinen im Chat unter der Antwort und lassen sich dort öffnen oder in den
Download-Ordner speichern. Den Text von PDF-, Word-, Excel-, PowerPoint- und Textdateien kann der
Assistent lesen und zusammenfassen (dafür `pypdf` und `openpyxl` aus `requirements.txt`).

#### Google Kalender

Der Assistent liest Termine aller eingeblendeten Kalender, legt neue an (auch in anderen Kalendern,
als Serie und mit Erinnerungen), findet freie Zeit und warnt vor Überschneidungen. Einladen kann er
nur Kontakte aus `PDA_MAIL_RECIPIENTS`. Einmalig einzurichten:

1. In der [Google Cloud Console](https://console.cloud.google.com/) ein Projekt anlegen und die
   **Google Calendar API** und die **Google Tasks API** aktivieren.
2. Unter *Google Auth Platform* den Zustimmungsbildschirm einrichten (App-Name, Kontakt-Mails) und
   unter *Datenzugriff* die Bereiche `calendar.events`, `calendar.readonly` und `tasks` hinzufügen.
3. Unter *Zielgruppe* **Extern** und **Testen** einstellen und bei *Testnutzer* die eigene
   Gmail-Adresse eintragen. Ohne diesen Eintrag lehnt Google die Anmeldung ab (`403 access_denied`).
4. Unter *Clients* einen OAuth-Client vom Typ **Desktop-App** anlegen und die JSON-Datei herunterladen.
5. Im Projektordner mit dem Python der `.venv` ausführen:
   `.venv/bin/python mcp_servers/google_calendar.py "<Pfad zur JSON-Datei>"` (macOS) bzw.
   `.venv\Scripts\python mcp_servers\google_calendar.py "<Pfad zur JSON-Datei>"` (Windows).
6. Im Browser mit der Gmail-Adresse anmelden und alle Berechtigungen erlauben. Die Warnung
   vor einer nicht überprüften App überspringt man mit *Erweitert* → *Weiter zu …*. Im Terminal steht
   danach `Google Kalender und Google Tasks sind eingerichtet`, die heruntergeladene JSON-Datei kann weg.
7. EVE komplett beenden und neu starten. Test: „Was steht diese Woche an?“

**Alle 7 Tage neu anmelden:** Im Status „Testen“ läuft die Anmeldung nach 7 Tagen ab, der Assistent
meldet das im Chat. Dann reicht derselbe Befehl ohne Pfad und die Anmeldung im Browser. Dauerhaft geht
es nur, wenn die App veröffentlicht ist: Dafür verlangt Google unter *Branding* eine Startseiten-URL
und eine URL zur Datenschutzerklärung.

Zugangsdaten und Anmeldung liegen außerhalb des Repos, unter Windows in
`%APPDATA%\PersonalDigitalAgent\google\`, unter macOS in `~/PersonalDigitalAgent/google/`
(eigener Ort: `PDA_GOOGLE_DIR`). Beim Erstellen fragt der Assistent standardmäßig nach. Das lässt
sich im Popup unter ⚙ Einstellungen → Werkzeuge → Google Kalender abschalten.

#### Google Tasks

Der Assistent liest offene und erledigte Aufgaben aller Listen, legt Aufgaben und Unteraufgaben an,
ändert, erledigt, löscht und verschiebt sie und erstellt neue Listen. Tasks nutzt dieselbe Anmeldung
wie der Kalender, die Einrichtung oben deckt beides ab. Wer den Kalender schon vor Tasks eingerichtet
hat, aktiviert nur noch die **Google Tasks API**, fügt unter *Datenzugriff* den Bereich `tasks` hinzu
und meldet sich einmal mit `mcp_servers/google_calendar.py` (ohne Pfad) neu an. Die Rückfrage vor dem
Erstellen lässt sich unter ⚙ Einstellungen → Werkzeuge → Google Tasks abschalten.

### Einstellungen (Präferenzen)

**⚙ Einstellungen** oben links im Chat öffnet ein Formular über dem ganzen Popup. Gespeichert wird
in `preferences.json` im Datenordner, gültig ab der nächsten Nachricht.

- macOS: `~/Library/Application Support/PersonalDigitalAgent`
- Windows: `%APPDATA%\PersonalDigitalAgent`
- Eigener Ort: Umgebungsvariable `PDA_APP_DATA_DIR`.

Einstellbar sind:

- **Antworten:** Länge, Tiefe, Darstellung (Fließtext, Stichpunkte, strukturiert …), Ton, Anrede
  (du/Sie), Sprache, Emojis, Rückfragen statt Raten und ein Freitext für weitere Wünsche.
- **Werkzeuge:** Für jede Werkzeuggruppe (E-Mail, Google Kalender, Google Tasks, Uhrzeit und Rechnen)
  einstellbar, ob der Assistent sie überhaupt nutzt, wie ausführlich er Ergebnisse im Chat wiedergibt,
  ob oben eine Tabelle der Aufrufe erscheint (aus, gekürzt, vollständig) und ein Freitext zur
  Darstellung. **E-Mail** zusätzlich: welche Angaben je Mail (Absender, Betreff, Datum, Vorschau,
  Anhänge …), wie viel Inhalt (nur Angaben, Zusammenfassung, Wichtiges, Volltext), Liste oder Tabelle,
  Höchstzahl, Rückfrage vor dem Senden. **Kalender** und **Tasks**: Rückfrage vor dem Erstellen.
- **Neue Werkzeuge** (z. B. aus einem weiteren MCP-Server) erscheinen automatisch mit den
  Grundeinstellungen. Eigene Zusatzfelder: `ToolGroup` in
  [backend/assistant/settings.py](backend/assistant/settings.py) eintragen.

### Proaktive Meldungen

EVE kann sich **von sich aus** melden, ohne dass man etwas gefragt hat. Zum Vorführen gibt es
ein Test-Makro: **⌘+⌥+P** auf macOS bzw. **Strg+Alt+P** unter Windows (auch bei geschlossenem Popup) oder
Rechtsklick aufs Symbol → „Proaktive Meldung testen“. Dann

1. formuliert das Sprachmodell eine kurze Meldung (ohne Modell: fester Text),
2. **öffnet sich das Popup von selbst** – genau wie bei einem Klick aufs Symbol (am Symbol, mit
   passender Einfahr-Animation; schließt sich beim Klick daneben),
3. steht die Meldung im Chat, markiert mit 🔔, und oben eine Ansicht mit Zeitpunkt und Auslöser,
4. wird sie vorgelesen, wenn die Sprachausgabe verfügbar ist.

Man kann direkt im Chat antworten – das Modell kennt seine Meldung. Einstellungen fürs Makro:
`PDA_PROACTIVE_HOTKEY` (z. B. `Ctrl+Shift+F9`, leer = aus), `PDA_PROACTIVE_SPEAK=0` (nicht vorlesen),
`PDA_PROACTIVE_OPEN_POPUP=0` (statt des Popups nur eine Systembenachrichtigung; Klick öffnet es).

Im Betrieb prüft ein **Wächter** im Hintergrund alle paar Minuten Postfach, Aufgaben und Kalender
([backend/watcher.py](backend/watcher.py)). Eingestellt wird alles im Popup unter
**⚙ Einstellungen → Proaktive Meldungen**:

- **Allgemein:** Prüfabstand, Art der Meldung (Popup, Systembenachrichtigung, nur Chat), Vorlesen,
  Formulierung, Ruhezeit, Wochentage, Höchstzahl pro Stunde.
- **E-Mail:** Das Sprachmodell entscheidet, was wichtig ist, nach deinen Kriterien. Vorrang haben
  eigene Regeln (Absender und Wörter für „immer“ und „nie“). Newsletter werden an ihren Kopfzeilen
  erkannt. Mails bleiben ungelesen, beim ersten Start gilt das Postfach als gesehen.
- **Aufgaben:** Eine Uhrzeit in Notiz oder Titel (`ca um 18 Uhr`, `18:30`, `um 9`, `8 Uhr abends`)
  gilt am Fälligkeitstag als Termin. „halb 7“ oder „Viertel nach“ werden nicht erkannt.
- **Kalender:** bis zu zwei Erinnerungen, ganztägige Termine, neue Einladungen, Filter nach Kalender
  und Titel.

`PDA_PROACTIVE_WATCH=0` schaltet den Wächter ganz ab.

## Testen

```sh
# macOS
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

```bat
rem Windows
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

`pytest` misst die Testabdeckung und schlägt fehl, wenn sie unter 80 % liegt. Gemini, Ollama, Google
und das Postfach werden in den Tests durch Attrappen ersetzt; es braucht weder Schlüssel noch Anmeldung.

## Wo arbeite ich?

Für die eigentliche Projektarbeit braucht ihr nur diese Stellen:

| Aufgabe | Ort |
|---|---|
| Integration eines Dienstes (Calendar, Wetter, Gmail …) | [backend/integrations/](backend/integrations/__init__.py) – Anleitung in der `__init__.py` |
| Fähigkeit des Assistenten (morning, travel, organization) | [backend/assistant/skills/](backend/assistant/skills/__init__.py) – Anleitung in der `__init__.py`, Beispiel: [travel/](backend/assistant/skills/travel/__init__.py) |
| Darstellung im Anzeigebereich | [frontend/templates/](frontend/templates/) – Vorlage: `default.html.j2` |
| Funktion, die das Frontend aufrufen kann | [backend/api.py](backend/api.py) |
| eigenes Werkzeug (MCP) | [mcp_servers/pda_server.py](mcp_servers/pda_server.py) – Funktion mit `@mcp.tool()` |
| fremder MCP-Server | [mcp_servers.json](mcp_servers.json) |
| Verhalten des Assistenten (Anweisungen, Tool-Schleife, Rückfragen) | [backend/assistant/model_assistant.py](backend/assistant/model_assistant.py) |
| Proaktive Meldungen und Wächter | [backend/proactive.py](backend/proactive.py), [backend/watcher.py](backend/watcher.py) |
| Sprache (Erkennung, Vorlesen) | [backend/speech.py](backend/speech.py) |

Alles andere ist **Infrastruktur** und muss für neue Funktionen nicht angefasst werden:
`backend/bridge/`, `backend/desktop/`, `rendering.py`, `presenter.py`, `events.py`, `views.py`.

## So hängt es zusammen

```
FRONTEND (frontend/, läuft im Browser)      BACKEND (backend/, läuft in Python)

popup.js ── await chat("…") ─────────────►  api.py ──► Assistent (assistant/)
                                                          │  Fähigkeiten (skills/) mit
                                                          │  Integrationen (integrations/)
                                                          ▼
iframe   ◄── fertiges HTML ◄── Template (frontend/templates/) + Daten des Assistenten
Chat     ◄── Nachricht ohne Eingabe ◄──── presenter.push(…)   z. B. Morning-Briefing
```

## Zwei Beispiele

**Python-Funktion im Frontend aufrufen**: Jede Funktion in `backend/api.py` ist in JavaScript
unter demselben Namen verfügbar.

```python
# backend/api.py
def add(a, b):
    return a + b
```

```js
// frontend/popup.js
const sum = await add(2, 3);
```

**Assistent zeigt Daten im Anzeigebereich an**: Er liefert nur Daten, das Template macht daraus
die Ansicht.

```python
return AssistantReply(
    "Hier ist das Wetter.",
    TemplateView("default", {"title": "Wetter", "text": "18 °C, sonnig"}),
)
```

## Mehr Details

[ARCHITEKTUR.md](ARCHITEKTUR.md) erklärt den Aufbau ausführlich. Dort stehen der
Programmablauf, die Brücke zwischen JavaScript und Python, der Weg einer Chat-Nachricht,
Templates und Sicherheit, die Schnittstellen für Sprachmodelle und Integrationen (inkl. Tool-Calling
und MCP), die Tests und bekannte Fallstricke.
