import os
import json
from db import execute, insert_row, get_conn
from psycopg2.extras import Json


EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")

# Tables in dependency order (no FK constraints here, but good practice)
TABLES = [
    "admin_users",
    "complaint",
    "governance",
    "integrity_events",
    "resources",
    "contact_messages",
    "processed_emails",
    "audit_logs",
]

# Tables where id is auto-generated and should not be inserted
# (contact_messages uses GENERATED ALWAYS AS IDENTITY)
IDENTITY_TABLES = {"contact_messages"}


def import_table(table_name):
    """Read JSON file and insert rows into PostgreSQL."""
    filepath = os.path.join(EXPORT_DIR, f"{table_name}.json")
    if not os.path.exists(filepath):
        print(f"  Skipping {table_name} (no export file)")
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not rows:
        print(f"  {table_name}: 0 rows (empty)")
        return 0

    print(f"  Importing {len(rows)} rows into {table_name}...")
    imported = 0

    for row in rows:
        try:
            # Remove 'id' for GENERATED ALWAYS tables
            if table_name in IDENTITY_TABLES and "id" in row:
                del row["id"]

            # Wrap list/dict values as JSONB
            clean = {}
            for k, v in row.items():
                if isinstance(v, (list, dict)):
                    clean[k] = Json(v)
                else:
                    clean[k] = v

            cols = list(clean.keys())
            vals = list(clean.values())
            col_names = ', '.join(f'"{c}"' for c in cols)
            placeholders = ', '.join(['%s'] * len(cols))

            sql = f'INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
            execute(sql, vals)
            imported += 1
        except Exception as e:
            print(f"    ERROR on row: {e}")

    # Reset sequences for serial/identity columns
    try:
        if table_name not in IDENTITY_TABLES:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Try to reset the sequence to max(id) + 1
                    cur.execute(f"""
                        SELECT column_default FROM information_schema.columns
                        WHERE table_name = %s AND column_name = 'id'
                    """, (table_name,))
                    result = cur.fetchone()
                    if result and result[0] and 'nextval' in str(result[0]):
                        seq_name = str(result[0]).split("'")[1]
                        cur.execute(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM {table_name}), 1))")
                conn.commit()
    except Exception as e:
        print(f"    WARNING: Could not reset sequence for {table_name}: {e}")

    print(f"  -> {imported} rows imported")
    return imported


def main():
    if not os.path.exists(EXPORT_DIR):
        print(f"Export directory not found: {EXPORT_DIR}")
        return

    total = 0
    for table in TABLES:
        total += import_table(table)

    print(f"\nDone. Imported {total} total rows.")


if __name__ == "__main__":
    main()
