# ENGINEERING_RULES.md

## Pre-commit Gate (Pflicht)

Ein Merge ist nur erlaubt, wenn alle Checks grün sind.

### Muss bestehen

1. Formatting: **black**
2. Imports: **isort**
3. Lint: **ruff**
4. Type-Check: **pyright** oder **mypy**
5. Tests: **pytest**

### Merge-Policy

* **No merge**, wenn irgendein Check fehlschlägt.
* Hotfixes sind keine Ausnahme: Qualität bleibt konstant.

## Review-Regeln

* Jede PR beschreibt:

  * Ziel
  * betroffene Module
  * Test-Nachweis
  * Migrations (falls DB)
* Änderungen an Kernregeln (Selection/Ranking/Economy) brauchen:

  * Unit Tests
  * kurze Design-Notiz in DEVLOG

## Security & Datenschutz

* Keine Secrets im Repo.
* Keine personenbezogenen Daten in Logs.
* Telegram User IDs nur als Token/Hash in Logs.

## Architektur-Invarianten

* Handler sind dünn.
* Domänenmodule sind klein, testbar, deterministisch.
* Jede neue Funktion hat klaren Owner (Modul/Domain) und Tests, wenn sie Regeln beeinflusst.
