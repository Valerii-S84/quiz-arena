---
version: 1.0.0
status: normative
scope: universal
---

# SECURITY_RULES

Цей документ задає універсальну матрицю безпечної поведінки.

## 1. Інтерпретація матриці

- `Always`: обов'язковий контроль, який застосовується завжди.
- `Ask First`: зупинись і дочекайся явного підтвердження.
- `Never`: заборонена дія; не виконувати.
- Якщо правила конфліктують, застосовуй суворіше.

## 2. Security matrix

| Зона | Always | Ask First | Never |
|---|---|---|---|
| Input і boundaries | Розглядай будь-який зовнішній input як недовірений. Явно валідуй структуру, типи, формат і межі перед використанням. | Ослаблення валідації, прийом нових типів payload або пропуск нормалізації. | Довіряти сирому input, LLM output, webhook payload або даним із зовнішніх API без перевірки. |
| Auth і access control | Перевіряй права на кожну дію, яка читає, змінює або публікує дані. | Тимчасові обходи auth, impersonation, manual privilege escalation. | Прибирати перевірку доступу, обходити ownership або публікувати від імені іншого користувача без авторизації. |
| Database | Використовуй параметризовані запити, транзакції і чіткі `WHERE`-обмеження для write-операцій. | Schema changes, backfill, масові правки даних, видалення даних, ручні SQL-операції поза ORM/approved flow. | Будувати SQL через конкатенацію або format/f-string з input, запускати destructive SQL без scoped filter. |
| Filesystem | Нормалізуй шляхи, обмежуйся робочим деревом або allowlisted директоріями, перевіряй ціль перед записом чи видаленням. | Запис поза репозиторієм, будь-яке видалення файлів, масове переміщення файлів, зміни deploy/runtime config, зміна CI/CD конфігурації, доступ до системних директорій. | Слідувати untrusted path у системні шляхи, читати або змінювати довільний файл через user-controlled path. |
| Shell і subprocess | Використовуй список аргументів, `shell=False`, timeout, явну перевірку аргументів і шляхів. | Інсталяція нових інструментів, виконання довгих або потенційно destructive скриптів, мережеве завантаження бінарників. | `shell=True` з input, `os.system` з input, `curl | sh`, підстановка сирого input у командний рядок. |
| Sensitive files і secrets | Маскуй секрети в логах і відповідях. Вважай секретними всі файли, що потенційно містять credentials або key material. | Зміни в secret-template, credential wiring або secret-loading code, якщо це прямо в scope. | Відкривати, друкувати, diff-ити, цитувати або копіювати вміст `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*_secret*`, `*secret*`, `*credentials*`, `.npmrc`, `.pypirc`, `.netrc`, cloud credential files. |
| Logging і telemetry | Логуй мінімально необхідне для діагностики, редагуй PII, tokens, cookies, headers, secrets. | Підвищення деталізації логів у prod-like середовищі або додавання audit trails з чутливими полями. | Логувати секрети, повні токени, приватні ключі, сесії, паролі або повні dumps request/response з чутливими полями. |
| External services і webhooks | Перевіряй схему payload, тайм-аути, retry policy і джерело виклику. | Підключення нового зовнішнього сервісу, зміна webhook trust boundary, відправка реальних prod payload. | Довіряти зовнішньому сервісу як внутрішньому джерелу істини без перевірки і без fallback. |
| LLM boundaries | Розглядай LLM output як недовірений input. Валідовуй перед збереженням, публікацією, SQL, shell або filesystem use. | Дозвіл LLM генерувати payload для дій, що змінюють стан, без human/rule gate. | Дозволяти LLM напряму виконувати destructive action, shell-команду, SQL або публікацію без перевірки. |
| Dependencies | Додавай або оновлюй залежності тільки коли це прямо потрібно для задачі. | Будь-яке оновлення lockfile/dependencies, зміна package manager policy, ручне обхідне встановлення. | Додавати неперевірену залежність "про всяк випадок" або підтягувати код/пакет без явної потреби. |
| Git і review workflow | Дотримуйся правил protected branch, review flow і локальних hooks. | Зміна branch protection, зміна review policy або ручний обхід git guardrails. | Виконувати `git push --force` або `git push -f` у protected branch, пропускати hooks через `--no-verify`, обходити обов'язковий review flow. |
| Production і deploy | Вважай prod-системи та deploy-пайплайни чутливими межами. | Будь-який deploy, push у protected branch, зміна infra/CI/prod config або доступ до prod host. | Виконувати deploy, змінювати prod-конфіг, ротацію секретів або операції на prod host без прямого запиту і підтвердження. |

## 3. Blocking rule

- Порушення `Never` блокує виконання.
- Поки дія залишається в `Ask First`, статус `Done` неможливий без
  явного підтвердження користувача.
