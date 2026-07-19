# REPO_STRUCTURE.md

> Compatibility overview. The current runtime layout is documented in
> `docs/architecture/current_runtime_map.md`; active agent rules and project
> boundaries live under `.agent/`. This file must not override either source.

## Ziel

Diese Struktur verhindert Chaos, trennt UI von Domänenlogik und hält Module klein (&lt;250 Zeilen pro Datei).

## Struktur

```
/app
  /api
    /routes
  /bot
    /handlers
    /keyboards
    /texts
  /core
  /db
    /models
    /repo
  /economy
    /energy
    /offers
    /promo
    /purchases
    /referrals
    /streak
  /game
    /friend_challenges
    /modes
    /questions
    /sessions
    /tournaments
  /ops_ui
    /site
  /services
  /workers
    /tasks
/alembic
/tests
/docs
```

## Regeln

* Keine zyklischen Imports zwischen Domänen.
* `app/bot/` enthält **keine** Business-Logik (nur UI/Handlers/Keyboards/Texts).
* Business-Logik liegt in:

  * `app/game/`
  * `app/economy/`
* DB-Zugriff:

  * Models in `app/db/models/`
  * Repositories/Queries in `app/db/repo/`
  * Migrationen in `alembic/versions/`
* Services (Integration/Infra) nur in `app/services/`.
* Konfiguration zentral in `app/core/`.

## Import-Guidelines

* `bot -> (services/domains)` ist erlaubt.
* `domains -> bot` ist verboten.
* `domains -> db/repo` ist erlaubt.
* `db -> domains` nur über klar definierte Interfaces (keine „Back-Imports“).
