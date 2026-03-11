"""m42_add_quick_mix_eligibility

Revision ID: f3b4c5d6e7f8
Revises: c3d4e5f6a7b8
Create Date: 2026-03-11 11:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b4c5d6e7f8"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

quiz_questions = sa.table(
    "quiz_questions",
    sa.column("source_file", sa.String(length=128)),
    sa.column("quick_mix_eligible", sa.Boolean()),
)
QUICK_MIX_ELIGIBLE_SOURCE_FILES = (
    "Adjektivendungen_Beginner_Bank_A1_A2_210.csv",
    "Antonym_Match_Bank_A1_B1_210.csv",
    "LOGIK_LUECKE_Denken_auf_Deutsch_Bank_500.csv",
    "Lexical_Gap_Fill_Bank_A2_B1_210.csv",
    "Mini_Dialog_Bank_A2_B1_210.csv",
    "Modalverben_Bank_210.csv",
    "Negation_Quiz_Bank_A2_B1_210.csv",
    "Plural_Check_Bank_500.csv",
    "Possessive_Adjectives_Bank_A2_B1_210.csv",
    "Preposition_Selection_Bank_A2_B1_210.csv",
    "Synonym_Match_Bank_A1_B1_210.csv",
    "Topic_Vocabulary_Themes_Bank_A2_B1_210.csv",
    "Verb_Conjugation_Bank_A2_B1_210.csv",
    "W_Fragen_Bank_630.csv",
)


def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column(
            "quick_mix_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        quiz_questions.update()
        .where(quiz_questions.c.source_file.in_(QUICK_MIX_ELIGIBLE_SOURCE_FILES))
        .values(quick_mix_eligible=True)
    )


def downgrade() -> None:
    op.drop_column("quiz_questions", "quick_mix_eligible")
