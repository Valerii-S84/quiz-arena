# COMPLIANCE_CHECKLIST
<!-- bundle: agent-rules | version: 1.0 -->

Цей документ є самостійним аудитом агента.
Агент виконує його без допомоги користувача одразу після старту в репо.

---

## Як виконувати

1. Прочитай кожен пункт.
2. Перевір відповідний файл командою або reread.
3. Постав `[x]` якщо виконано, `[ ]` якщо ні.
4. Якщо будь-який пункт у розділі БЛОКЕРИ не виконано —
   зупинись і повідом користувача до початку будь-якої роботи.

---

## БЛОК 1 — Структура (обов'язкова наявність файлів)

Команда: `find .agent -type f | sort`

```
[ ] .agent/AGENTS.md існує
[ ] .agent/CHANGELOG.md існує
[ ] .agent/core/WORK_SCOPE.md існує
[ ] .agent/core/DEFINITION_OF_DONE.md існує
[ ] .agent/core/TASK_OUTPUT_FORMAT.md існує
[ ] .agent/core/AUTO_CHECKLIST.md існує
[ ] .agent/core/SECURITY_RULES.md існує
[ ] .agent/core/GIT_WORKFLOW.md існує
[ ] .agent/core/PRINCIPLES.md існує
[ ] .agent/project/PROJECT_CONTEXT.md існує
[ ] .agent/project/CODE_STYLE.md існує
```

**Якщо будь-який файл відсутній → БЛОКЕР. Зупинись.**

---

## БЛОК 2 — Entrypoint і навігація

Файл: `.agent/AGENTS.md`
Команда: `rg -n "Quick Start|порядок читання|core/|project/|stop.rule\|stop-rule|FILL_PER_PROJECT" .agent/AGENTS.md`

```
[ ] Є явний порядок читання: core/ → project/
[ ] Є розділ Quick Start For New Repo
[ ] Є stop-rule: якщо project/ не заповнений — зупинись
[ ] Є реєстр усіх документів з коротким описом
[ ] Є bundle version (рядок виду "version: X.Y")
[ ] Є правило: у разі конфлікту project/ > core/
```

---

## БЛОК 3 — Scope control

Файл: `.agent/core/WORK_SCOPE.md`
Команда: `rg -n "scope|дозвол|заборон|побічн|ескалац" .agent/core/WORK_SCOPE.md`

```
[ ] Визначено що входить у scope (явний запит + мінімум змін)
[ ] Визначено що є поза scope (рефакторинг, перейменування, конфіги)
[ ] Визначено що заборонено без прямого дозволу
[ ] Є протокол для знайденої побічної проблеми (не виправляй, згадай в ризиках)
[ ] Є протокол ескалації якщо межа задачі неочевидна
```

---

## БЛОК 4 — Definition of Done

Файл: `.agent/core/DEFINITION_OF_DONE.md`
Команда: `rg -n "Done|Partial|Incomplete|доведен|перевірк|факт|припущ" .agent/core/DEFINITION_OF_DONE.md`

```
[ ] Визначено умови для статусу Done
[ ] Визначено що НЕ є Done ("майже готово", "має працювати" тощо)
[ ] Визначено статуси Partial і Incomplete з вимогою заповнити ризики
[ ] Факти відділені від припущень як вимога
[ ] Є вимога відповідності звіту фактичному стану репо
```

---

## БЛОК 5 — Output format

Файл: `.agent/core/TASK_OUTPUT_FORMAT.md`
Команда: `rg -n "Статус|Scope|Створені|Що зроблено|Що НЕ|Перевірка|Недоведено" .agent/core/TASK_OUTPUT_FORMAT.md`

```
[ ] Є обов'язкова структура відповіді (6 полів)
[ ] Є правило: без преамбули
[ ] Є правило: без порад без прямого запиту
[ ] Є правило: порожній пункт = "- Немає"
[ ] Є прив'язка Partial/Incomplete до поля Недоведено / ризики
```

---

## БЛОК 6 — Auto-checklist

Файл: `.agent/core/AUTO_CHECKLIST.md`
Команда: `rg -n "Scope|Межі змін|Доказовість|Перевірки|Фінальний" .agent/core/AUTO_CHECKLIST.md`

```
[ ] Є перевірка scope drift перед завершенням
[ ] Є перевірка меж змін (тільки потрібні файли)
[ ] Є перевірка доказовості (факт vs припущення)
[ ] Є перевірка результатів тестів
[ ] Є перевірка відповідності формату TASK_OUTPUT_FORMAT
```

---

## БЛОК 7 — Security

Файл: `.agent/core/SECURITY_RULES.md`
Команда: `rg -n "Always|Ask First|Never|\.env|\.pem|\.key|id_rsa|_secret|credentials" .agent/core/SECURITY_RULES.md`

```
[ ] Є матриця у форматі Always / Ask First / Never
[ ] Always: перелік дій які агент виконує завжди без питань
[ ] Ask First: перелік дій які вимагають підтвердження
[ ] Never: перелік абсолютно заборонених дій
[ ] Never: заборона читати .env* файли
[ ] Never: заборона читати *.pem, *.key, id_rsa*, *_secret*, *credentials*
[ ] Never: заборона force push до protected branch
[ ] Never: заборона пропускати pre-commit hooks (--no-verify)
[ ] Never: заборона виконувати деструктивні операції на prod без explicit дозволу
[ ] Ask First: зміна залежностей
[ ] Ask First: видалення файлів
[ ] Ask First: зміна CI/CD конфігурації
```

---

## БЛОК 8 — Git workflow

Файл: `.agent/core/GIT_WORKFLOW.md`
Команда: `rg -n "Conventional|FILL_PER_PROJECT|co-author|force.push|protected|merge.strateg" .agent/core/GIT_WORKFLOW.md`

```
[ ] Є вимога Conventional Commits (feat:, fix:, chore: тощо)
[ ] Є заборона push безпосередньо у protected/main branch
[ ] Є заборона агенту бути listed як co-author коміту
[ ] [FILL_PER_PROJECT]: default branch name
[ ] [FILL_PER_PROJECT]: branching strategy
[ ] [FILL_PER_PROJECT]: merge strategy (squash / merge / rebase)
[ ] [FILL_PER_PROJECT]: PR title format і вимоги
```

---

## БЛОК 9 — Universal principles

Файл: `.agent/core/PRINCIPLES.md`
Команда: `rg -n "SRP|single.responsib|naming|comment|nesting|вкладен|numeric|limit|anti.pattern" .agent/core/PRINCIPLES.md`

```
[ ] Є принцип single responsibility для функцій і модулів
[ ] Є правила іменування (описові імена, заборона сміттєвих назв)
[ ] Є правила для коментарів (чому, а не що)
[ ] Є обмеження вкладеності (max 3 рівні)
[ ] Є числові ліміти (рядки на файл / функцію / клас / параметри)
[ ] Є перелік дозволених винятків до числових лімітів
[ ] Є перелік заборонених антипатернів
[ ] Відсутній Python-specific або JS-specific контент (він у project/)
```

---

## БЛОК 10 — Project context (шаблон заповнений?)

Файл: `.agent/project/PROJECT_CONTEXT.md`
Команда: `rg -c "\[FILL_PER_PROJECT\]" .agent/project/PROJECT_CONTEXT.md`

```
[ ] Файл існує
[ ] Секція stack присутня
[ ] Секція project structure присутня
[ ] Секція key commands присутня (test / lint / build / dev)
[ ] Секція external dependencies присутня
[ ] Секція project constraints присутня (protected paths, deploy boundaries)
[ ] Секція git settings присутня (default branch, branching, merge strategy)
```

Якщо `rg -c "\[FILL_PER_PROJECT\]"` повертає число > 0:

```
[ ] БЛОКЕР: project/PROJECT_CONTEXT.md містить незаповнені placeholder-и.
    Виведи список незаповнених полів і зупинись до їх заповнення.
```

---

## БЛОК 11 — Code style (шаблон і вибір мови)

Файл: `.agent/project/CODE_STYLE.md`
Команда: `rg -n "primary_language\|active_sections\|FILL_PER_PROJECT" .agent/project/CODE_STYLE.md`

```
[ ] Є поле primary_language або active_sections
[ ] Є секції під різні мови (Python, JS/TS, Go, SQL, Shell)
[ ] Мовно-специфічний контент НЕ дублюється в core/PRINCIPLES.md
[ ] Якщо primary_language заповнений — агент знає яку секцію застосовувати
[ ] Якщо primary_language порожній → Ask First перед застосуванням стилю
```

---

## БЛОК 12 — Versioning і changelog

Файли: `.agent/AGENTS.md`, `.agent/CHANGELOG.md`
Команда: `rg -n "version:" .agent/AGENTS.md && head -20 .agent/CHANGELOG.md`

```
[ ] Bundle version присутній в AGENTS.md
[ ] CHANGELOG.md існує і містить хоча б один запис
[ ] Формат changelog читабельний (дата + що змінилось)
```

---

## БЛОК 13 — Відсутність repo-specific витоків у core/

Команда: `rg -rn "hoerbot|canonical_bank|valerchik|localhost:[0-9]" .agent/core .agent/AGENTS.md`

```
[ ] Результат порожній — у core/ немає repo-specific назв або адрес
```

---

## ПІДСУМКОВА ОЦІНКА

Порахуй кількість виконаних пунктів.

| Блок | Макс | Факт |
|---|---|---|
| 1. Структура | 11 | __ |
| 2. Entrypoint | 6 | __ |
| 3. Scope control | 5 | __ |
| 4. Definition of Done | 5 | __ |
| 5. Output format | 5 | __ |
| 6. Auto-checklist | 5 | __ |
| 7. Security | 12 | __ |
| 8. Git workflow | 7 | __ |
| 9. Principles | 8 | __ |
| 10. Project context | 8 | __ |
| 11. Code style | 5 | __ |
| 12. Versioning | 3 | __ |
| 13. Repo-specific витоки | 1 | __ |
| **Разом** | **81** | __ |

**Відповідність вимогам bundle: __ / 81**

| Діапазон | Висновок |
|---|---|
| 72–81 | Повна відповідність. Агент може стартувати. |
| 60–71 | Часткова відповідність. Є gap-и, але не блокери. |
| < 60 | Критичні прогалини. Заповни перед стартом. |

---

## БЛОКЕРИ (будь-який з них зупиняє роботу)

- [ ] Відсутній будь-який файл з Блоку 1
- [ ] Відсутній порядок читання в AGENTS.md
- [ ] PROJECT_CONTEXT.md містить незаповнені [FILL_PER_PROJECT]
- [ ] SECURITY_RULES.md не має матриці Never
- [ ] У core/ знайдено repo-specific назви (Блок 13)

Якщо жоден блокер не активований і оцінка ≥ 72 — агент може починати роботу.
