from sqlalchemy import inspect
from reviewer.database import engine

inspector = inspect(engine)

tables = [
    "review_jobs",
    "review_findings",
    "review_reports",
]

for table in tables:
    print(f"\n{'=' * 50}")
    print(f"TABLE: {table}")
    print("=" * 50)

    for column in inspector.get_columns(table):
        print(
            f"Column: {column['name']:<25} "
            f"Type: {str(column['type']):<20} "
            f"Nullable: {column['nullable']}"
        )

    print("\nForeign keys:")
    for fk in inspector.get_foreign_keys(table):
        print(fk)