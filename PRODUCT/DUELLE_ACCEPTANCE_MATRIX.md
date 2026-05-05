# Duelle Acceptance Matrix

Джерело: `PRODUCT/DUELLE_VISION.md`.

Цей файл є release-gate checklist для доведення `Duelle` до vision-complete стану.
Статуси:

- `implemented` - вимога вже покрита кодом або документацією.
- `missing` - вимога відсутня або реалізована лише частково і не може вважатися release-ready.
- `blocked` - потрібне окреме продуктове або schema-рішення перед виконанням.

## UX

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | Home entrypoint називається `⚔️ Duelle`. | `app/bot/keyboards/home.py` показує `⚔️ Duelle`. |
| implemented | `Duelle` menu має тільки два основні режими: `🏟 Offene Arena` і `👤 Freundesduell`. | `app/bot/keyboards/duels.py` рендерить два mode CTA і back button. |
| implemented | Duel menu copy описує два режими без legacy-surface. | `app/bot/texts/de.py` має окремий `duels.menu` для Arena і Freundesduell. |
| implemented | У duel / arena / friend question screens не показується `Thema`. | `app/bot/handlers/gameplay_views_question.py` і `app/bot/handlers/start_views.py` приховують theme line для `ARENA_DUEL` і `FRIEND_CHALLENGE`. |
| implemented | У duel UX немає вибору topic / level / length. | Основний duel menu і friend create flow мають тільки canonical direct `7`; private tournament callbacks винесені в `tournament:*`. |
| missing | На кожному duel screen є один головний CTA і очевидний шлях назад. | Arena result/published keyboards вирівняні; friend share/created surfaces ще мають кілька рівнозначних дій і лишаються gap. |
| implemented | Empty arena state веде до створення першого arena duel або назад. | `app/bot/keyboards/duels.py` має `arena_empty_keyboard()`. |
| implemented | Arena result screen дає наступну дію після завершення. | `duel_arena_result_keyboard()` показує один primary action і `🏟 Zur Arena` як navigation. |
| implemented | `👤 Freund herausfordern` після arena duel створює direct friend duel із тим самим mode/question set. | `arena:challenge_friend:{arena_duel_id}` створює direct friend challenge з arena `mode_code`, `question_ids` і `7` rounds. |
| missing | Friend challenge creation screen має publish/share шлях згідно vision. | `friend_challenge_created_keyboard()` має share/play/wait CTA, але publish-to-arena доступний тільки після завершення creator baseline. |

## Gameplay

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | Arena duel завжди має рівно `7` питань. | `DUEL_QUESTION_COUNT = 7`, `ArenaDuel.question_ids` має DB check на довжину `7`, service validation перевіряє `7`. |
| implemented | Friend duel canonical total rounds всюди дорівнює `7`. | `FRIEND_CHALLENGE_TOTAL_ROUNDS` бере `DUEL_QUESTION_COUNT`, `resolve_duel_rounds()` приймає тільки `7`. |
| implemented | Обидва гравці отримують той самий question set. | Arena і friend flows зберігають `question_ids` і примусово використовують expected question per round. |
| missing | Score + time визначають переможця для всіх duel flows. | Arena scoring порівнює score/time; friend challenge completion зараз визначає winner лише за score. |
| implemented | Arena creator не може прийняти власний duel. | `arena_duels.accept.accept_arena_duel()` відхиляє self-accept. |
| implemented | Користувач має тільки одну спробу на arena duel. | `arena_duel_attempts` має unique constraint по `(duel_id, user_id)` і service guard. |
| implemented | Expired arena duel не можна прийняти. | Accept flow перевіряє inactive/expired duel до старту challenger attempt. |
| implemented | Expired arena duels закриваються worker-ом. | `app/workers/tasks/arena_duels.py` і schedule запускають expiry cleanup. |
| implemented | Friend duel можна опублікувати в arena зі збереженим question set. | `publish_friend_challenge_to_arena()` створює `ArenaDuel` з `question_ids`, score і duration creator baseline. |
| missing | Friend duel publish-to-arena доступний у потрібному UX-місці. | Service підтримує publish після `CREATOR_DONE`; creation screen не має `🏟 In der Arena veröffentlichen`. |
| implemented | Arena -> friend send створює direct friend challenge з тим самим question set і mode. | `create_friend_challenge_from_arena_duel()` clone-ить active creator arena duel у direct friend challenge без topic/length UI. |
| implemented | Legacy callbacks `5/12/open/tournament/best3` не створюють duel-flow. | Friend create parser приймає тільки `direct:7`; open/series regex не матчать; private tournaments moved to `tournament:*`. |
| implemented | Extra surfaces не лишаються в `Duelle` namespace/UI. | `Meine Duelle` fallback button і registration прибрані; open/series runtime callbacks більше не зареєстровані; tournament callbacks не мають `friend:` namespace. |
| implemented | Private tournament behavior не змішується з `Duelle`. | Private tournament callbacks використовують окремий `tournament:*` namespace, не `friend:tournament:*`. |

## Anti-Spam

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | Немає random direct invite або auto-match direct push. | Friend flow базується на explicit share link / inline share, не на випадкових direct invites. |
| implemented | Немає mass push для arena duels. | Arena worker надсилає тільки personal beaten notification попередньому best user. |
| implemented | Friend challenge reminders персональні і quota-limited. | Friend notification workers таргетять конкретного user і використовують push quota guard. |
| implemented | Revanche можлива тільки після реальної взаємодії з duel. | Arena revanche context вимагає completed source attempt і completed sender attempt. |
| implemented | Revanche dedupe / quota захищають від spam. | Revanche service перевіряє lock, already-sent state і analytics uniqueness. |
| implemented | Premium не дає mass push або anti-spam bypass. | Premium впливає на access/limits, не на push fanout або scoring. |
| missing | Unplayed friend duel reminder веде автора до publish-to-arena як описано у vision. | Наявні reminders/expired notices персональні, але creator notice не відкриває publish-to-arena path. |

## Monetization

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | `Premium 3 Tage` не продається. | Purchase catalog soft-disables `PREMIUM_3_DAYS` для sale. |
| implemented | `Premium 3 Tage` лишається reward-only. | Daily cup reward worker grant-ить `PREMIUM_3_DAYS` як tournament reward. |
| implemented | Duel paywall продає тільки `Duell-Ticket` і `Premium-Woche`. | Duel paywall keyboard має тільки `FRIEND_CHALLENGE_5` і `PREMIUM_WEEK`. |
| implemented | `Premium-Woche` не дає scoring advantage. | Premium access проходить через limit/access layer; question selection і scoring не залежать від premium. |
| implemented | Free limits відповідають vision baseline. | Constants задають arena create/accept, friend create і revanche daily limits. |
| implemented | Paywall зʼявляється після action/limit hit, не як стартовий маркетинг. | Arena/friend flows показують paywall після payment-required guard. |
| missing | Emotional close-loss / result-beaten paywall реалізований як окремий funnel. | Текст існує, але dedicated rendering/trigger для close-loss paywall не знайдений. |
| missing | Duel-specific click analytics покривають усі duel paywall buttons. | Payment handler пише duel click events тільки для callbacks із `:duel`; friend limit keyboard використовує generic buy callback. |
| implemented | Purchase crediting idempotent. | Purchase credit service має replay/idempotency handling і `purchase_credited` event. |

## Analytics

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | `duel_menu_opened` пишеться. | Event constant і menu flow існують. |
| implemented | `duel_mode_selected` пишеться. | Event constant і mode selection flow існують. |
| implemented | `arena_opened` пишеться. | Event constant і arena open flow існують. |
| implemented | `arena_duel_created` пишеться. | Arena creation service emits event. |
| implemented | `arena_duel_started` пишеться. | Arena start/baseline flow emits event. |
| implemented | `arena_duel_completed` пишеться. | Arena baseline/challenger completion emits event. |
| implemented | `arena_duel_published` пишеться. | Arena publish path emits event. |
| implemented | `arena_duel_accepted` пишеться. | Arena accept flow emits event. |
| implemented | `arena_result_shown` пишеться. | Arena result flow emits event. |
| implemented | `arena_result_beaten_notification_sent` dedupe event існує. | Arena worker uses notification event key and uniqueness guard. |
| implemented | `arena_revanche_clicked` пишеться. | Arena revanche confirm flow emits canonical clicked event before send step. |
| implemented | `friend_duel_opened` пишеться. | Event constant існує для friend duel open. |
| implemented | `friend_duel_created` пишеться. | Friend create/rematch/arena-clone paths emit canonical `friend_duel_created`. |
| implemented | `friend_duel_share_clicked` пишеться. | Proof-card share flow emits canonical `friend_duel_share_clicked`. |
| implemented | `friend_duel_joined` пишеться. | Join flow emits canonical `friend_duel_joined` без legacy `duel_accepted`. |
| implemented | `friend_duel_started` пишеться. | Friend round start service emits canonical `friend_duel_started`. |
| implemented | `friend_duel_completed` пишеться. | Friend completion flow emits canonical `friend_duel_completed`. |
| implemented | `friend_duel_published_to_arena` пишеться. | Publish service emits event. |
| implemented | `friend_duel_revanche_clicked` пишеться. | Friend rematch analytics emits canonical `friend_duel_revanche_clicked`. |
| implemented | `duel_limit_hit` і `duel_paywall_shown` пишуться для duel access guard. | Event constants і payment-required flows існують. |
| missing | `duel_ticket_clicked` і `premium_week_clicked` повністю покривають friend + arena duel paywalls. | Duel-context callbacks покриті; friend limit keyboard використовує generic purchase callback без `:duel`. |
| implemented | `purchase_credited` пишеться після credit. | Purchase credit assets service emits event. |
| implemented | `docs/analytics/events_catalog.md` синхронізований з canonical duel events. | Catalog містить canonical friend/arena duel events і не містить legacy friend event names. |
| missing | Daily/funnel metrics для duel vision доступні з analytics layer. | `analytics_daily` не має dedicated duel funnel counters для create/share/join/complete/publish/revanche. |

## Engineering

| Status | Acceptance item | Evidence / gap |
| --- | --- | --- |
| implemented | Question set фіксується через seed/id і не перевибирається між players. | Arena/friend services зберігають `question_ids` і forced expected question per round. |
| implemented | DB/service guards не дозволяють arena duel з не-7 question set. | Arena model check constraint і service validation перевіряють довжину `7`. |
| implemented | One-attempt invariant enforced на DB і service рівнях. | Unique constraint plus accept guard. |
| implemented | Daily limit callbacks не обходять arena start guard. | Session start для arena викликає duel limit assertion перед round start. |
| implemented | Daily/format guards не приймають legacy friend formats як valid create paths. | Friend challenge parser і `resolve_duel_rounds()` приймають тільки canonical direct `7`. |
| implemented | Notifications deduped. | Arena beaten notices і revanche flows використовують event locks/unique keys. |
| implemented | Purchases idempotent. | Purchase credit service supports replay and credited-state checks. |
| implemented | Expired arena duel cleanup scheduled. | Worker schedule runs arena expiry cleanup every 5 minutes. |
| implemented | Усі ключові кроки мають canonical analytics events. | Canonical friend/arena create/share/join/start/complete/publish/revanche events покриті кодом і catalog contract test. |
| implemented | Regression coverage покриває всі gaps з matrix. | Callback, arena->friend, analytics, paywall і anti-spam negative tests закривають phase 4-8 gaps. |
| missing | Release quality gates пройдені після duel changes. | Phase 0 є audit artifact; lint/type/test/full smoke gates не запускалися як release validation. |
