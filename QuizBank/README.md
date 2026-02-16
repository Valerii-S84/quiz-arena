# QuizBank

Короткий опис папки `QuizBank` для продакшн використання.

## Що тут є

- Основний набір вікторин у форматі `CSV`.
- Усі продакшн банки уніфіковані під одну схему колонок.
- Окремо є службовий шаблон для логік-банку.

## Поточний склад

- Файлів у папці: `20`
- Загальна кількість вікторин: `5150`
- Продакшн вікторин: `5150`
- Службові шаблони: `1` файл (`0` рядків контенту)

## Продакшн банки

- `Adjektivendungen_Beginner_Bank_A1_A2_210.csv` — `210`
- `Akkusativ_Dativ_Bank_A1_B1_210.csv` — `210`
- `Antonym_Match_Bank_A1_B1_210.csv` — `210`
- `Artikel_Sprint_Bank_A1_B2_1000.csv` — `1000`
- `LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv` — `500`
- `Lexical_Gap_Fill_Bank_A2_B1_210.csv` — `210`
- `Mini_Dialog_Bank_A2_B1_210.csv` — `210`
- `Modalverben_Bank_210.csv` — `210`
- `Negation_Quiz_Bank_A2_B1_210.csv` — `210`
- `Plural_Check_Bank_500.csv` — `500`
- `Possessive_Adjectives_Bank_A2_B1_210.csv` — `210`
- `Preposition_Selection_Bank_A2_B1_210.csv` — `210`
- `Satzbau_Bank_A2_B1_210.csv` — `210`
- `Synonym_Match_Bank_A1_B1_210.csv` — `210`
- `Topic_Vocabulary_Themes_Bank_A2_B1_210.csv` — `210`
- `Verb_Conjugation_Bank_A2_B1_210.csv` — `210`
- `W_Fragen_Bank_210.csv` — `210`
- `trennbare_verben_210_korrigiert.csv` — `210`

## Службовий файл

- `logik_luecke_sheet_template.csv` — шаблон для ручного створення нових логік-рядів.

## Перевірка якості

Запускати з кореня репозиторію:

```bash
python tools/quizbank_audit.py
python tools/quizbank_ambiguity_scan.py
```

Звіти генеруються в папку `reports/`.
