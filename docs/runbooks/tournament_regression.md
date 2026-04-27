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
- за замовчуванням використовує окремий namespace:
  `quiz_arena_test_tournaments` + Redis DB `10/11/12`, щоб живі локальні
  `api/worker/beat` процеси на стандартних `quiz_arena_test` і Redis `0/1/2`
  не втручалися в regression run;
- піднімає локальні `postgres` і `redis` через Docker, якщо `docker` або
  `docker.exe` доступний;
  якщо Docker недоступний, чекає вже запущені локальні сервіси;
- створює test DB перед підключенням до target DB, тому clean DB namespace є
  repeatable;
- перевіряє, що Redis URLs локальні та не використовують зарезервовані DB
  `0/1/2`, потім очищає тільки ці ізольовані Redis DB;
- проганяє фіксований набір tournament bot/game/worker tests;
- застосовує Alembic migrations до test DB;
- проганяє фіксований набір tournament integration tests для `PRIVATE` і `DAILY_ARENA` одним `pytest` invocation у підтримуваному локальному test-оточенні.

Merge gate:

- unit/bot/game/worker частина цього inventory входить у mandatory `CI / lint_unit`;
- integration частина цього inventory входить у mandatory `CI / integration`;
- dedicated `CI / tournament_regression` job запускає `make test-tournaments`
  з власними Postgres/Redis services, `PYTHON_BIN=python`,
  `SKIP_LOCAL_SERVICES=1`, `quiz_arena_test_tournaments` і Redis DB `10/11/12`.

Правило підтримки:

- при додаванні нового tournament regression `test_*.py` його треба додати в `scripts/tournament_regression.sh`, щоб локальний entrypoint лишався повним і детермінованим.
