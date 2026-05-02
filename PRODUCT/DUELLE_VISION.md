# Візія режиму “Duelle”

## 1. Головний принцип

Ми **не міняємо головне меню**.

У головному меню залишається поточна кнопка:

text
⚔️ Duelle


Після натискання відкривається простий екран із двома режимами:

text
⚔️ Duelle
├── 🏟 Offene Arena
└── 👤 Freundesduell


Жодних додаткових режимів.
Жодного вибору теми.
Жодного вибору рівня.
Жодного кабінету.
Жодної складної social-системи.
Жодного спаму між підписниками.

---

# 2. Канонічні правила

Це треба зафіксувати як незмінні продуктові правила.

| Правило                                     | Рішення                                              |
| ------------------------------------------- | ---------------------------------------------------- |
| Головне меню не перебудовуємо               | Змінюємо тільки екран після кнопки **Duelle**        |
| Режимів тільки два                          | **Offene Arena** і **Freundesduell**                 |
| Користувач не вибирає тему                  | Бот сам формує набір питань                          |
| Користувач не вибирає рівень                | Бот використовує поточний рівень/профіль користувача |
| Користувач не налаштовує дуель              | Натиснув — створив або прийняв                       |
| Усе user-facing тільки німецькою            | Повідомлення, кнопки, помилки, paywall, share-тексти |
| Premium 3 Tage не продається                | Тільки нагорода в турнірі                            |
| У duel-flow продається тільки Premium-Woche | Не trial, не 3 дні                                   |
| Немає random direct invite                  | Користувачі не можуть спамити інших підписників      |
| Premium не дає перевагу в питаннях          | Однакові правила для всіх                            |

---

# 3. Екран після кнопки “Duelle”

Користувач натискає:

text
⚔️ Duelle


Бот показує:

text
⚔️ Duelle

Wähle deinen Duellmodus.

🏟 Offene Arena
Spiele gegen Ergebnisse anderer Spieler im Bot.

👤 Freundesduell
Erstelle ein Duell und teile den Link mit einem Freund.

[🏟 Offene Arena]
[👤 Freundesduell]
[↩️ Zurück]


Цей екран має бути максимально чистий.
Не пояснювати зайвого. Не давати вибір теми. Не давати вибір складності.

Користувач вирішує тільки одне:

text
Грати проти всіх всередині бота
або
створити дуель для друга


---

# 4. Режим 1 — 🏟 Offene Arena

## 4.1. Що це таке

**Offene Arena** — це внутрішній режим, де користувачі змагаються між собою всередині бота.

Суть:

> Один користувач створює Arena-Duell.
> Бот дає йому автоматичний набір питань.
> Його результат з’являється в арені.
> Інші користувачі можуть прийняти цей виклик і спробувати побити результат.

Тут немає Telegram-груп.
Немає розсилки всім.
Немає direct spam.
Користувач сам заходить в арену і сам приймає виклик.

---

## 4.2. Основна логіка Offene Arena

mermaid
flowchart TD
    A[User öffnet Duelle] --> B[Offene Arena]
    B --> C{Aktion}
    C --> D[Bestehendes Arena-Duell annehmen]
    C --> E[Eigenes Arena-Duell erstellen]

    D --> F[Bot startet gleiche Fragen]
    F --> G[User spielt Runde]
    G --> H[Bot vergleicht Score und Zeit]
    H --> I[Ergebnis anzeigen]

    E --> J[Bot startet automatisch eine Runde]
    J --> K[User spielt Runde]
    K --> L[Ergebnis wird 24h in Arena veröffentlicht]
    L --> M[Andere Spieler können es schlagen]


Ключове:

text
Немає вибору теми.
Немає вибору рівня.
Немає налаштувань.


Бот сам створює duel-set.

---

# 5. Екран Offene Arena

Користувач натискає:

text
[🏟 Offene Arena]


Бот показує:

text
🏟 Offene Arena

Schlage Ergebnisse anderer Spieler.
Gleiche Fragen. Gleiche Regeln.

Der bessere Score gewinnt.
Bei Gleichstand zählt die Zeit.

Aktive Duelle:

🔥 Max
6/7 · 00:48

👑 Anna
7/7 · 00:55

⚡ Spieler #184
5/7 · 00:31

[🔥 Max schlagen]
[👑 Anna schlagen]
[⚡ Spieler #184 schlagen]
[🎯 Eigenes Arena-Duell erstellen]
[↩️ Zurück]


Важливо: тут немає тем, рівнів, фільтрів.

Не так:

text
❌ Artikel
❌ Wortschatz
❌ Grammatik
❌ A1 / A2 / B1


А тільки:

text
✅ Ось активні результати
✅ Прийняти
✅ Створити свій


---

# 6. Прийняття Arena-Duell

Користувач натискає:

text
[🔥 Max schlagen]


Бот показує:

text
🔥 Arena-Duell

Schlage Max' Ergebnis.

Max:
6/7 · 00:48

Du spielst dieselben Fragen.
Du hast genau einen Versuch.

[▶️ Starten]
[↩️ Zur Arena]


Після натискання:

text
[▶️ Starten]


Бот одразу запускає раунд.

Жодного проміжного вибору.
Жодної теми.
Жодного рівня.

---

# 7. Правила Arena-Duell

| Параметр                         | Значення                                 |
| -------------------------------- | ---------------------------------------- |
| Кількість питань                 | 7                                        |
| Набір питань                     | однаковий для автора і того, хто приймає |
| Вибір теми                       | немає                                    |
| Вибір рівня                      | немає                                    |
| Перемога                         | вищий score                              |
| Tie-break                        | швидший час                              |
| Спроба                           | одна спроба на один Arena-Duell          |
| TTL                              | 24 години                                |
| Автор не може грати проти себе   | так                                      |
| Повторна спроба того самого duel | ні                                       |

---

# 8. Результат після Arena-Duell

## 8.1. Користувач переміг

text
🎉 Gewonnen!

Du:
7/7 · 00:52

Max:
6/7 · 00:48

Du hast Max' Ergebnis geschlagen.

[🔁 Revanche]
[🎯 Eigenes Arena-Duell erstellen]
[🏟 Zur Arena]


## 8.2. Користувач програв

text
Max bleibt vorne.

Du:
5/7 · 00:44

Max:
6/7 · 00:48

Versuch ein anderes Duell oder erstelle dein eigenes Arena-Duell.

[🏟 Zur Arena]
[🎯 Eigenes Arena-Duell erstellen]


## 8.3. Однаковий score, але користувач швидший

text
🎉 Gewonnen!

Ihr habt beide 6/7.
Du warst schneller.

Du:
6/7 · 00:42

Max:
6/7 · 00:48

[🔁 Revanche]
[🎯 Eigenes Arena-Duell erstellen]
[🏟 Zur Arena]


## 8.4. Однаковий score, але користувач повільніший

text
Knapp verloren.

Ihr habt beide 6/7.
Max war schneller.

Du:
6/7 · 00:55

Max:
6/7 · 00:48

[🔁 Revanche]
[🏟 Zur Arena]


---

# 9. Створення власного Arena-Duell

Користувач натискає:

text
[🎯 Eigenes Arena-Duell erstellen]


Бот показує:

text
🎯 Arena-Duell erstellen

Spiele eine kurze Runde.
Dein Ergebnis bleibt 24 Stunden in der Offenen Arena.

Andere Spieler können versuchen, dich zu schlagen.

[▶️ Starten]
[↩️ Zur Arena]


Після натискання:

text
[▶️ Starten]


Бот одразу запускає раунд.

Не показуємо:

text
❌ Wähle ein Thema
❌ Wähle dein Niveau
❌ Wähle die Länge
❌ Casual / Ranked


Після завершення:

text
🏟 Dein Arena-Duell ist aktiv!

Dein Ergebnis:
6/7 · 00:48

Andere Spieler können dein Ergebnis jetzt schlagen.
Dein Duell läuft 24 Stunden.

[🏟 Zur Arena]
[👤 Freund herausfordern]
[🎯 Neues Arena-Duell erstellen]


---

# 10. Порожня Offene Arena

Якщо активних викликів немає, не можна показувати мертвий екран.

Правильний empty state:

text
🏟 Offene Arena

Noch gibt es keine aktiven Arena-Duelle.

Starte das erste Duell und setze ein Ergebnis, das andere Spieler schlagen können.

[🎯 Erstes Arena-Duell erstellen]
[↩️ Zurück]


Це важливо для маленької бази користувачів.

---

# 11. Notification, коли результат побили

Бот не має пушити всім нові арена-дуелі.

Але бот може повідомити автора, якщо його результат побили.

text
⚔️ Dein Arena-Duell wurde geschlagen.

Anna hat dein Ergebnis übertroffen.

Du:
6/7 · 00:48

Anna:
7/7 · 00:52

[🔁 Revanche]
[🏟 Zur Arena]


Ліміти:

| Подія                           | Пуш                                       |
| ------------------------------- | ----------------------------------------- |
| Хтось створив нове Arena-Duell  | ні                                        |
| Хтось прийняв твій виклик       | ні                                        |
| Хтось програв твоєму результату | ні або digest                             |
| Хтось побив твій результат      | так                                       |
| Реванш                          | тільки якщо вже була дуель між цими двома |

Тобто пуш тільки там, де є особиста емоція.

---

# 12. Режим 2 — 👤 Freundesduell

## 12.1. Суть

**Freundesduell** залишається простим:

> Користувач створює дуель.
> Бот генерує посилання.
> Користувач сам надсилає посилання другу.
> Друг відкриває посилання і грає той самий duel-set.
> Бот порівнює результати.

Тут теж немає вибору теми.

---

# 13. Екран Freundesduell

Користувач натискає:

text
[👤 Freundesduell]


Бот показує:

text
👤 Freundesduell

Erstelle ein Duell und teile den Link mit einem Freund.

Ihr spielt dieselben Fragen.
Der bessere Score gewinnt.
Bei Gleichstand zählt die Zeit.

[⚔️ Freundesduell erstellen]
[↩️ Zurück]


Немає:

text
❌ Wähle ein Thema
❌ Wähle Schwierigkeit
❌ Wähle Anzahl der Fragen


Є тільки:

text
[⚔️ Freundesduell erstellen]


---

# 14. Створення Freundesduell

Користувач натискає:

text
[⚔️ Freundesduell erstellen]


Бот створює дуель автоматично і показує:

text
👤 Freundesduell erstellt!

Teile diesen Link mit einem Freund.
Dein Freund spielt dieselben Fragen und versucht, dich zu schlagen.

[📤 Link teilen]
[🏟 In der Arena veröffentlichen]
[❌ Duell abbrechen]
[↩️ Zurück]


Тут важливо:

* користувач не вибирав тему;
* бот сам створив duel-set;
* користувач отримав share-link;
* є можливість опублікувати в Arena, якщо він хоче не чекати друга.

---

# 15. Що бачить друг після відкриття link

Друг відкриває deep link.

Бот показує:

text
👤 Freundesduell

Max fordert dich heraus.

Ihr spielt dieselben Fragen.
Der bessere Score gewinnt.
Bei Gleichstand zählt die Zeit.

[▶️ Duell starten]
[↩️ Später]


Після натискання:

text
[▶️ Duell starten]


Бот запускає раунд.

Без вибору теми.
Без налаштувань.
Без додаткового пояснення.

---

# 16. Результат Freundesduell

## 16.1. Друг переміг

text
🎉 Gewonnen!

Du hast Max geschlagen.

Du:
7/7 · 00:52

Max:
6/7 · 00:48

[🔁 Revanche]
[🏟 Offene Arena]


## 16.2. Друг програв

text
Max gewinnt dieses Duell.

Du:
5/7 · 00:44

Max:
6/7 · 00:48

[🔁 Revanche]
[🏟 Offene Arena]


## 16.3. Автор отримує повідомлення

Якщо автора побили:

text
⚔️ Dein Freundesduell ist entschieden.

Anna hat dich geschlagen.

Du:
6/7 · 00:48

Anna:
7/7 · 00:52

[🔁 Revanche]
[🏟 Zur Arena]


Якщо автор переміг:

text
🛡️ Dein Ergebnis hält.

Anna hat dein Freundesduell gespielt.

Du:
6/7 · 00:48

Anna:
5/7 · 00:44

[🔁 Revanche]
[🏟 Zur Arena]


---

# 17. Зв’язок Freundesduell і Offene Arena

Це лишаємо, але без ускладнень.

## 17.1. Friend-duel можна опублікувати в Arena

Після створення friend-duel є кнопка:

text
[🏟 In der Arena veröffentlichen]


Сенс:

> Якщо користувач не хоче чекати друга або друг не зіграв, цей duel-set може стати Arena-Duell.

Повідомлення:

text
🏟 In der Arena veröffentlicht!

Andere Spieler können dein Duell jetzt annehmen.

[🏟 Zur Arena]
[📤 Link teilen]


---

## 17.2. Якщо friend-duel довго не зіграли

Один reminder тільки автору:

text
Dein Freundesduell wurde noch nicht gespielt.

Du kannst es in der Offenen Arena veröffentlichen, damit andere Spieler es annehmen können.

[🏟 In der Arena veröffentlichen]
[⏳ Weiter warten]
[❌ Schließen]


Це не спамить друга.
Це не спамить підписників.
Це просто дає автору корисну дію.

---

# 18. Реванш

Реванш можна показувати тільки після реальної взаємодії:

* після Arena-Duell між двома користувачами;
* після Freundesduell;
* коли твій результат побили.

Не можна:

text
❌ реванш випадковому користувачу, з яким ти не грав;
❌ багаторазово пушити одну людину;
❌ Premium як дозвіл спамити реваншами.


Екран реваншу:

text
🔁 Revanche

Fordere Max zu einer Revanche heraus.

Max erhält genau eine Nachricht.

[🔁 Revanche senden]
[↩️ Zurück]


Повідомлення отримувачу:

text
🔁 Revanche?

Max möchte noch einmal gegen dich spielen.

[▶️ Revanche annehmen]
[❌ Ablehnen]
[🔕 Keine Revanchen von Max]


---

# 19. Монетизація

Фіксуємо твоє правило:

text
Premium 3 Tage не продається.
Premium 3 Tage тільки для переможця турніру.


У duel-flow продаємо:

text
🎟 Duell-Ticket
👑 Premium-Woche


Без Premium 3 Tage.

---

## 19.1. Free-ліміти

Щоб режим був корисним, free-користувач має реально пограти.

Пропозиція:

| Дія                    |   Free |
| ---------------------- | -----: |
| Прийняти Arena-Duell   | 3/день |
| Створити Arena-Duell   | 1/день |
| Створити Freundesduell | 2/день |
| Revanche               | 1/день |

Це можна підкрутити пізніше, але головна логіка така:

> Перша емоція безкоштовна.
> Монетизація — коли користувач хоче продовжити.

---

## 19.2. Paywall після ліміту

Коли користувач вперся в ліміт:

text
Dein kostenloses Duell-Limit für heute ist erreicht.

Du kannst morgen kostenlos weiterspielen oder jetzt direkt weitermachen.

[🎟 Duell-Ticket – 5⭐]
[👑 Premium-Woche – 29⭐]
[↩️ Später]


---

## 19.3. Paywall після емоційного моменту

Коли користувач програв дуже близько:

text
Knapp verloren.

Du warst nur eine Frage entfernt.
Willst du direkt weiterspielen?

[🎟 Duell-Ticket – 5⭐]
[👑 Premium-Woche – 29⭐]
[↩️ Später]


Коли його результат побили:

text
Anna hat dein Ergebnis geschlagen.

Hol dir die Spitze zurück.

[🔁 Revanche]
[🎟 Duell-Ticket – 5⭐]
[👑 Premium-Woche – 29⭐]


---

## 19.4. Premium-Woche

User-facing текст:

text
👑 Premium-Woche

Mehr Duelle. Mehr Revanchen. Keine Energiepause während deiner Duelle.

Premium ändert keine Fragen und keine Wertung.
Alle Duelle bleiben fair.

[👑 Premium-Woche – 29⭐]
[↩️ Später]


Premium може давати:

| Перевага                     | Дозволено |
| ---------------------------- | --------- |
| Більше дуелей на день        | так       |
| Більше реваншів              | так       |
| Без energy-pause в duel-flow | так       |
| Premium badge                | так       |
| Більше активних Arena-Duelle | так       |
| Легші питання                | ні        |
| Бонус до score               | ні        |
| Кращий tie-break             | ні        |
| Більше очок за перемогу      | ні        |

---

# 20. Premium 3 Tage

Це окрема турнірна нагорода.

Не показувати в:

text
❌ Shop
❌ Duel paywall
❌ Premium upsell
❌ invoice list


Показувати тільки в турнірному контексті:

text
🏆 Turnierpreis

Der Gewinner erhält:
👑 3 Tage Premium

Nicht kaufbar. Nur als Turnierpreis.


---

# 21. Антиспам

## 21.1. Заборонено

text
❌ користувач не може вибрати випадкового підписника і викликати його;
❌ бот не пушить усім нові Arena-Duelle;
❌ Premium не дає право пушити більше людей;
❌ немає масових invite;
❌ немає списку всіх гравців із кнопкою “викликати”.


## 21.2. Дозволено

text
✅ користувач сам заходить в Offene Arena;
✅ користувач сам приймає Arena-Duell;
✅ користувач сам створює Freundesduell-link;
✅ користувач сам ділиться link;
✅ бот повідомляє автора, якщо його результат побили;
✅ бот повідомляє про завершений Freundesduell;
✅ реванш тільки після реальної дуелі.


Це безпечна social-механіка без спаму.

---

# 22. Технічна логіка question set

Тут важливо не допустити помилки з UI.

Користувач не має бачити вибір теми, але backend все одно має сформувати набір питань.

Правильна модель:

text
User натискає Start
↓
Backend автоматично створює duel question set
↓
Set фіксується seed/id
↓
Обидва гравці проходять той самий set
↓
Score/time порівнюються


Backend може враховувати:

text
- поточний learning level користувача;
- доступний question pool;
- баланс типів питань;
- уникнення повторів;
- валідність question set;


Але user-facing цього немає.

Користувач бачить тільки:

text
[▶️ Starten]


---

# 23. Edge cases

## 23.1. Дуель протухла

text
Dieses Duell ist abgelaufen.

Wähle ein neues Duell in der Offenen Arena.

[🏟 Zur Arena]
[🎯 Eigenes Arena-Duell erstellen]


## 23.2. Користувач уже грав цей Arena-Duell

text
Du hast dieses Arena-Duell bereits gespielt.

Jedes Arena-Duell hat nur einen Versuch.

[🏟 Zur Arena]


## 23.3. Користувач натиснув власний Arena-Duell

text
Das ist dein eigenes Arena-Duell.

Andere Spieler können versuchen, dein Ergebnis zu schlagen.

[🏟 Zur Arena]


## 23.4. Немає активних дуелей

text
Noch gibt es keine aktiven Arena-Duelle.

Starte das erste Duell und setze ein Ergebnis.

[🎯 Erstes Arena-Duell erstellen]
[↩️ Zurück]


## 23.5. Ліміт вичерпано

text
Dein kostenloses Duell-Limit für heute ist erreicht.

[🎟 Duell-Ticket – 5⭐]
[👑 Premium-Woche – 29⭐]
[↩️ Später]


---

# 24. Аналітика

Події мають чітко показувати, чи працюють обидва режими.

text
duel_menu_opened
duel_mode_selected

arena_opened
arena_duel_created
arena_duel_started
arena_duel_completed
arena_duel_published
arena_duel_accepted
arena_result_shown
arena_result_beaten_notification_sent
arena_revanche_clicked

friend_duel_opened
friend_duel_created
friend_duel_share_clicked
friend_duel_joined
friend_duel_started
friend_duel_completed
friend_duel_published_to_arena
friend_duel_revanche_clicked

duel_limit_hit
duel_paywall_shown
duel_ticket_clicked
premium_week_clicked
purchase_credited


Головні метрики:

| Метрика                                        | Навіщо                             |
| ---------------------------------------------- | ---------------------------------- |
| duel_menu_opened -> arena_opened             | чи люди заходять у новий режим     |
| arena_opened -> arena_duel_accepted          | чи цікава арена                    |
| arena_duel_created -> accepted               | чи результати знаходять суперників |
| arena_duel_accepted -> completed             | чи gameplay не ламається           |
| friend_duel_created -> share_clicked         | чи friend-flow простий             |
| friend_duel_not_played -> published_to_arena | чи Arena рятує неприйняті дуелі    |
| result_beaten -> revanche_clicked            | чи є емоція реваншу                |
| duel_limit_hit -> purchase_credited          | чи монетизація працює              |

---

# 25. Definition of Done

Щоб це було зроблено “на висоті”, реліз вважається готовим тільки коли виконано все нижче.

## UX

text
✅ Усі user-facing тексти німецькою.
✅ Немає вибору теми.
✅ Немає вибору рівня.
✅ Немає зайвих налаштувань.
✅ Кожен екран має один головний CTA.
✅ Кожен екран має шлях назад.
✅ Empty state Offene Arena виглядає нормально.
✅ Після кожного результату є наступна дія.


## Gameplay

text
✅ 7 питань.
✅ Однаковий question set для обох гравців.
✅ Score + time.
✅ Одна спроба на Arena-Duell.
✅ Автор не може грати проти себе.
✅ Expired duels обробляються.
✅ Friend-duel можна опублікувати в Arena.
✅ Arena-Duell можна надіслати другу.


## Anti-spam

text
✅ Немає random direct invite.
✅ Немає масових пушів.
✅ Пуш тільки про особисто важливі події.
✅ Revanche тільки після реальної дуелі.
✅ Premium не обходить антиспам.


## Monetization

text
✅ Premium 3 Tage не продається.
✅ Duel paywall показує тільки Duell-Ticket і Premium-Woche.
✅ Premium-Woche не змінює scoring.
✅ Premium не дає unfair advantage.
✅ Paywall з’являється після дії або емоції, не до першої гри.


## Engineering

text
✅ Question set фіксується через seed/id.
✅ Неможливо повторно пройти той самий Arena-Duell.
✅ Неможливо обійти daily limit callback-ами.
✅ Notifications не дублюються.
✅ Purchases idempotent.
✅ Expired duels чистяться worker-ом.
✅ Усі ключові кроки пишуть analytics events.


---

# 26. Фінальна структура

Остаточна структура така:

text
⚔️ Duelle
│
├── 🏟 Offene Arena
│   ├── список активних Arena-Duelle
│   ├── прийняти чужий результат
│   ├── зіграти той самий question set
│   ├── порівняти score + time
│   ├── створити власний Arena-Duell
│   ├── отримати notification, якщо тебе побили
│   ├── Revanche
│   └── Duell-Ticket / Premium-Woche після ліміту або емоції
│
└── 👤 Freundesduell
    ├── створити дуель
    ├── отримати link
    ├── поділитися з другом
    ├── друг грає той самий question set
    ├── результат порівнюється
    ├── Revanche
    ├── опублікувати в Arena
    └── Duell-Ticket / Premium-Woche після ліміту або емоції


Головна логіка:

text
Користувач не налаштовує дуель.
Користувач просто грає.


Німецькою це має відчуватися так:

text
Erstellen.
Starten.
Schlagen.
Revanche.
