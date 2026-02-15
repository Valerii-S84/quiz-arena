# CODE_STYLE.md

## Grundprinzipien

* **Klarheit > Cleverness.**
* Keine „magischen“ Abkürzungen, keine impliziten Side-Effects.
* Jede Datei hat **einen** klaren Zweck.
* Bevorzugt: einfache, deterministische Logik statt „Smartness“.

## Dateigröße

* **Max. 250 Zeilen pro Datei (Hard Limit).**
* Ausnahmen **nur** mit expliziter Begründung im PR/DEVLOG und Link auf die Entscheidung.

## Modularität

* **Eine Datei = ein Modul = ein Verantwortungsbereich.**
* Keine Sammeldateien wie `utils.py`.

  * Stattdessen: `strings.py`, `time.py`, `ids.py`, `validation.py`, `hashing.py`, `randomness.py` usw.
* Business-Logik darf nicht in UI-/Transport-Schichten landen.

## Benennung

* Python:

  * Funktionen/Variablen: `snake_case`
  * Klassen: `PascalCase`
  * Konstanten: `UPPER_SNAKE_CASE`
* Funktionen sind Verben: `build_session()`, `select_questions()`, `apply_rewards()`.
* Keine Mehrdeutigkeit: Namen müssen Zweck und Kontext klar machen.

## Typisierung

* Type Hints sind **verpflichtend**.
* Ziel: **pyright/mypy „strict-ish“** (mindestens konsequent, keine „Any“-Durchseuchung).
* Public APIs (Service-Layer/Repo-Layer) müssen sauber typisiert sein.

## Fehlerbehandlung

* Kein `except Exception: pass`.
* Exceptions werden:

  * **gezielt** gefangen (konkret), oder
  * sauber bis zum zentralen Handler propagiert.
* Fehlertexte sind präzise und enthalten **keine** sensitiven Daten.

## Logging

* **Structured Logging**, kein `print()`.
* Level:

  * `DEBUG` für Diagnose
  * `INFO` für normale Events
  * `WARNING` für Abweichungen
  * `ERROR` für Fehlerfälle
* **Keine personenbezogenen Daten** loggen (z. B. Name, Telefonnummer, exakte Nachrichtentexte, Payment-IDs im Klartext).
* Logs müssen Ereignisse rekonstruierbar machen (Request-ID / Tournament-ID / User-ID als Hash/Token).

## Docstrings

* Für public Functions/Classes: **1–5 Zeilen** („was & warum“).
* Keine Romane.
* Beispiel:

  * „Selects questions with anti-repeat constraints across recent history.“

## Tests

* Jeder Core-Algorithmus braucht Unit Tests:

  * Selection (Anti-Repeat, Difficulty-Balancing)
  * Scoring/Ranking
  * Tournament Lifecycle
  * Economy Entitlements
  * Anti-Abuse Regeln
* Keine ungetesteten Kernregeln.
* Tests sind deterministisch (Seeds / Fixures / Clock Mock).

## Formatierung & Lint

* Pflicht:

  * `black`
  * `isort`
  * `ruff`
* Keine Style-Diskussionen: Tool-Output ist die Quelle der Wahrheit.

## Datenbank

* Migrationen sind **verpflichtend** (z. B. Alembic).
* Kein Schema-Drift: DB-Schema = Migrations = Models.
* Keine „Quick Fixes“ direkt in der DB.

## API & Telegram

* Telegram UI-Texte **nur Deutsch**.
* Alle Bot-Texte zentral in `app/bot/texts/de.py` (auch wenn nur DE).
* Handler enthalten keine Business-Logik, nur Orchestrierung & Input/Output.
