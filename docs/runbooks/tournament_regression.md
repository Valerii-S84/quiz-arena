# Tournament Regression

Канонічний локальний entrypoint для `PRIVATE` і `DAILY_ARENA` regression:

```bash
make test-tournaments
```

Альтернатива без `make`:

```bash
bash scripts/tournament_regression.sh
```

Що робить цей набір:

- перевіряє Python `3.12` і безпечний `TEST_DATABASE_URL`;
- піднімає локальні `postgres` і `redis` та прибирає docker-compose orphan services, щоб живі `worker/beat` контейнери не втручалися в regression run;
- проганяє фіксований набір tournament bot/game/worker tests;
- застосовує Alembic migrations до test DB;
- проганяє фіксований набір tournament integration tests для `PRIVATE` і `DAILY_ARENA` одним `pytest` invocation у підтримуваному локальному test-оточенні.

Merge gate:

- unit/bot/game/worker частина цього inventory входить у mandatory `CI / lint_unit`;
- integration частина цього inventory входить у mandatory `CI / integration`;
- додано dedicated `CI / tournament_regression` job, який запускає `make test-tournaments` як обов’язковий гейт для PR/merge.

Правило підтримки:

- при додаванні нового tournament regression `test_*.py` його треба додати в `scripts/tournament_regression.sh`, щоб локальний entrypoint лишався повним і детермінованим.
