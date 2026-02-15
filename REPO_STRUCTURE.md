# REPO_STRUCTURE.md

## Ziel

Diese Struktur verhindert Chaos, trennt UI von Domänenlogik und hält Module klein (&lt;250 Zeilen pro Datei).

## Struktur

```
/app
  /bot
    /handlers
    /keyboards
    /texts
  /game
    /modes
    /selection
    /scoring
    /anti_abuse
  /tournaments
    /lifecycle
    /ranking
    /rewards
  /economy
    /packages
    /entitlements
    /referrals
  /db
    /models
    /migrations
    /repo
  /services
    /scheduler
    /payments
    /analytics
  /config
/tests
/docs
```

## Regeln

* Keine zyklischen Imports zwischen Domänen.
* `app/bot/` enthält **keine** Business-Logik (nur UI/Handlers/Keyboards/Texts).
* Business-Logik liegt in:

  * `app/game/`
  * `app/tournaments/`
  * `app/economy/`
* DB-Zugriff:

  * Models in `app/db/models/`
  * Repositories/Queries in `app/db/repo/`
  * Migrationen in `app/db/migrations/`
* Services (Integration/Infra) nur in `app/services/`.
* Konfiguration zentral in `app/config/`.

## Import-Guidelines

* `bot -> (services/domains)` ist erlaubt.
* `domains -> bot` ist verboten.
* `domains -> db/repo` ist erlaubt.
* `db -> domains` nur über klar definierte Interfaces (keine „Back-Imports“).
