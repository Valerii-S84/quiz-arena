# M2 DB Changes

## Migrations
- `alembic/versions/2f4a1d9c0e11_m2_core_data_model_part1.py`
- `alembic/versions/4e5f6a7b8c90_m2_core_data_model_part1b.py`
- `alembic/versions/8b7c6d5e4f32_m2_core_data_model_part2.py`
- `alembic/versions/9a0b1c2d3e4f_m2_core_data_model_part2b.py`
- `alembic/versions/c1d2e3f4a5b6_m2_core_data_model_part3.py`

## Schema Impact
- Added complete section-6 data model tables, constraints, indexes, and key foreign keys.
- Added purchases -> promo_codes FK in phase 2 after `promo_codes` creation.

## Rollback
1. `alembic downgrade 9a0b1c2d3e4f`
2. `alembic downgrade 8b7c6d5e4f32`
3. `alembic downgrade 4e5f6a7b8c90`
4. `alembic downgrade 2f4a1d9c0e11`
5. `alembic downgrade 1c7257851be3`

## Compatibility
- Changes are additive from bootstrap revision.
- Downgrade chain is explicitly defined per revision.
