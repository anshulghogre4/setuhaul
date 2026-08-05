"""Build the PostgreSQL baseline and seed from the authoritative SQLite SQL.

This script preserves table/column names, logical SQLite types, constraints,
indexes, views, and seed values. It only reorders DDL/DML to satisfy PostgreSQL
foreign-key requirements and applies PostgreSQL/Supabase syntax required for a
safe baseline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
from pathlib import Path


TABLE_ORDER = [
    "carriers",
    "vehicle_types",
    "facilities",
    "roles",
    "docks",
    "drivers",
    "facility_contacts",
    "facility_rules",
    "vehicles",
    "shipments",
    "appointment_slots",
    "chat_threads",
    "appointments",
    "eta_updates",
    "facility_checkins",
    "dock_status_events",
    "driver_exceptions",
    "chat_messages",
    "operational_messages",
    "users",
    "audit_logs",
    "api_logs",
]

EXPECTED_COUNTS = {
    "api_logs": 3,
    "appointment_slots": 106,
    "appointments": 20,
    "audit_logs": 4,
    "carriers": 4,
    "chat_messages": 20,
    "chat_threads": 12,
    "dock_status_events": 3,
    "docks": 9,
    "driver_exceptions": 10,
    "drivers": 15,
    "eta_updates": 12,
    "facilities": 2,
    "facility_checkins": 5,
    "facility_contacts": 5,
    "facility_rules": 6,
    "operational_messages": 5,
    "roles": 8,
    "shipments": 21,
    "users": 10,
    "vehicle_types": 5,
    "vehicles": 15,
}

EXPECTED_VIEW_COUNTS = {
    "v_latest_eta": 21,
    "v_slot_availability": 106,
    "v_inbound_operational_state": 21,
    "v_current_facility_queue": 3,
}


def parse_csv_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def normalize_dictionary_row(row: dict[str, str]) -> dict[str, object]:
    """Normalize both layouts present in the supplied data dictionary.

    The first 18 tables use the declared header. The four appended application
    tables use: table,column,type,nullable,pk,fk,description without replacing
    the header row. Supporting both formats preserves the supplied artifact
    while still validating it against executable SQL.
    """
    known_types = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}
    if row["column_name"].strip().upper() in known_types:
        description = row["foreign_key_target"].strip()
        reference = re.search(r"References\s+([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", description)
        return {
            "table_name": row["table_name"].strip(),
            "column_name": row["table_purpose"].strip(),
            "data_type": row["column_name"].strip().upper(),
            "not_null": row["data_type"].strip().upper() == "NO",
            "primary_key": row["not_null"].strip().upper() == "YES",
            "foreign_key_target": reference.group(1) if reference else "",
        }
    return {
        "table_name": row["table_name"].strip(),
        "column_name": row["column_name"].strip(),
        "data_type": row["data_type"].strip().upper(),
        "not_null": parse_csv_bool(row["not_null"]),
        "primary_key": parse_csv_bool(row["primary_key"]),
        "foreign_key_target": row["foreign_key_target"].strip(),
    }


def validate_data_dictionary(connection: sqlite3.Connection, path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [normalize_dictionary_row(row) for row in csv.DictReader(handle)]

    dictionary_tables = {row["table_name"] for row in rows}
    if dictionary_tables != set(TABLE_ORDER):
        raise ValueError(
            "Data dictionary table set differs from SQL: "
            f"dictionary={sorted(dictionary_tables)}, sql={sorted(TABLE_ORDER)}"
        )

    for table in TABLE_ORDER:
        dictionary_rows = [row for row in rows if row["table_name"] == table]
        table_info = list(connection.execute(f'pragma table_info("{table}")'))
        foreign_keys = {
            row[3]: f"{row[2]}.{row[4]}"
            for row in connection.execute(f'pragma foreign_key_list("{table}")')
        }

        if [row["column_name"] for row in dictionary_rows] != [
            row[1] for row in table_info
        ]:
            raise ValueError(f"Column order mismatch for {table}")

        for dictionary_row, pragma_row in zip(dictionary_rows, table_info):
            column = pragma_row[1]
            if dictionary_row["data_type"] != pragma_row[2].upper():
                raise ValueError(f"Data type mismatch for {table}.{column}")
            pragma_not_null = bool(pragma_row[3])
            primary_key_implies_not_null = bool(pragma_row[5]) and bool(
                dictionary_row["not_null"]
            )
            if dictionary_row["not_null"] != pragma_not_null and not primary_key_implies_not_null:
                raise ValueError(f"NOT NULL mismatch for {table}.{column}")
            if dictionary_row["primary_key"] != bool(pragma_row[5]):
                raise ValueError(f"Primary-key mismatch for {table}.{column}")
            expected_fk = dictionary_row["foreign_key_target"]
            actual_fk = foreign_keys.get(column, "")
            if expected_fk != actual_fk:
                raise ValueError(
                    f"Foreign-key mismatch for {table}.{column}: "
                    f"dictionary={expected_fk!r}, sql={actual_fk!r}"
                )
    return len(rows)


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError("Source SQL ends with an incomplete statement")
    return statements


def strip_comments(statement: str) -> str:
    statement = re.sub(r"/\*.*?\*/", "", statement, flags=re.DOTALL)
    statement = re.sub(r"^\s*--.*$", "", statement, flags=re.MULTILINE)
    return statement.strip()


def object_name(statement: str, pattern: str) -> str:
    match = re.search(pattern, statement, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not identify object in statement: {statement[:100]}")
    return match.group(1)


def postgres_ddl(statement: str) -> str:
    # SQLite accepts CURRENT_TIMESTAMP as a default for TEXT. PostgreSQL needs
    # an explicit cast to retain the source TEXT column contract.
    statement = re.sub(
        r"DEFAULT\s+CURRENT_TIMESTAMP",
        "DEFAULT (CURRENT_TIMESTAMP::text)",
        statement,
        flags=re.IGNORECASE,
    )
    return statement


def postgres_view(statement: str) -> str:
    # Supabase/Postgres views otherwise execute with the view owner's rights.
    return re.sub(
        r"^CREATE\s+VIEW\s+([^\s]+)\s+AS",
        r"CREATE VIEW \1 WITH (security_invoker = true) AS",
        statement,
        count=1,
        flags=re.IGNORECASE,
    )


def build(
    source: Path,
    dictionary: Path,
    migration: Path,
    seed: Path,
    parity: Path,
) -> None:
    source_sql = source.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_sql.encode("utf-8")).hexdigest()

    # Validate that the source itself is executable and internally consistent.
    connection = sqlite3.connect(":memory:")
    connection.executescript(source_sql)
    connection.execute("pragma foreign_keys=on")
    fk_errors = list(connection.execute("pragma foreign_key_check"))
    if fk_errors:
        raise ValueError(f"Source SQLite foreign-key violations: {fk_errors}")

    actual_counts = {
        row[0]: connection.execute(f'select count(*) from "{row[0]}"').fetchone()[0]
        for row in connection.execute(
            "select name from sqlite_master "
            "where type='table' and name not like 'sqlite_%' order by name"
        )
    }
    if actual_counts != EXPECTED_COUNTS:
        raise ValueError(
            f"Source row counts changed. Expected {EXPECTED_COUNTS}, got {actual_counts}"
        )

    actual_view_counts = {
        name: connection.execute(f'select count(*) from "{name}"').fetchone()[0]
        for name in EXPECTED_VIEW_COUNTS
    }
    if actual_view_counts != EXPECTED_VIEW_COUNTS:
        raise ValueError(
            "Source view counts changed. "
            f"Expected {EXPECTED_VIEW_COUNTS}, got {actual_view_counts}"
        )

    dictionary_columns = validate_data_dictionary(connection, dictionary)

    creates: dict[str, str] = {}
    inserts: dict[str, list[str]] = {name: [] for name in TABLE_ORDER}
    indexes: list[str] = []
    views: list[str] = []

    for raw in split_statements(source_sql):
        statement = strip_comments(raw)
        if not statement:
            continue
        upper = statement.upper()
        if upper in {"BEGIN TRANSACTION;", "BEGIN;", "COMMIT;"}:
            continue
        if upper.startswith("CREATE TABLE"):
            name = object_name(statement, r'CREATE\s+TABLE\s+["`]?([A-Za-z0-9_]+)')
            creates[name] = postgres_ddl(statement)
        elif upper.startswith("INSERT INTO"):
            name = object_name(statement, r'INSERT\s+INTO\s+["`]?([A-Za-z0-9_]+)')
            if name not in inserts:
                raise ValueError(f"Unexpected seed table: {name}")
            inserts[name].append(statement)
        elif upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX"):
            indexes.append(statement)
        elif upper.startswith("CREATE VIEW"):
            views.append(postgres_view(statement))
        else:
            raise ValueError(f"Unclassified SQL statement: {statement[:120]}")

    missing_tables = set(TABLE_ORDER) - set(creates)
    if missing_tables:
        raise ValueError(f"Missing table DDL: {sorted(missing_tables)}")

    header = (
        "-- Generated from docs/database_docs/setuhaul_schema_and_seed.sql\n"
        f"-- Source SHA-256: {source_hash}\n"
        "-- Do not edit this baseline by hand; regenerate it with\n"
        "-- supabase/tools/build_postgres_baseline.py.\n\n"
        "set search_path = public;\n\n"
    )

    migration_parts = [header]
    migration_parts.extend(creates[name] + "\n\n" for name in TABLE_ORDER)
    migration_parts.extend(statement + "\n\n" for statement in indexes)
    migration_parts.extend(statement + "\n\n" for statement in views)

    migration_parts.append("-- Deny direct Data API access until Auth/RLS policies are designed.\n")
    for name in TABLE_ORDER:
        migration_parts.append(f"alter table public.{name} enable row level security;\n")
        migration_parts.append(
            f"revoke all on table public.{name} from anon, authenticated;\n"
        )
        migration_parts.append(f"grant all on table public.{name} to service_role;\n")
    migration_parts.append("\n")
    for name in EXPECTED_VIEW_COUNTS:
        migration_parts.append(
            f"revoke all on table public.{name} from anon, authenticated;\n"
        )
        migration_parts.append(f"grant select on table public.{name} to service_role;\n")

    seed_parts = [header, "begin;\n\n"]
    for name in TABLE_ORDER:
        for statement in inserts[name]:
            seed_parts.append(statement + "\n\n")
    seed_parts.append("commit;\n")

    checks = [
        "-- Regression checks for the SetuHaul baseline.\n",
        f"-- Source SHA-256: {source_hash}\n",
        "do $$\n",
        "declare\n  actual_count bigint;\n",
        "begin\n",
    ]
    for name, expected in EXPECTED_COUNTS.items():
        checks.extend(
            [
                f"  select count(*) into actual_count from public.{name};\n",
                f"  if actual_count <> {expected} then\n",
                f"    raise exception '{name} row-count mismatch: expected {expected}, got %', actual_count;\n",
                "  end if;\n",
            ]
        )
    for name, expected in EXPECTED_VIEW_COUNTS.items():
        checks.extend(
            [
                f"  select count(*) into actual_count from public.{name};\n",
                f"  if actual_count <> {expected} then\n",
                f"    raise exception '{name} row-count mismatch: expected {expected}, got %', actual_count;\n",
                "  end if;\n",
            ]
        )
    checks.extend(
        [
            "  select count(*) into actual_count\n",
            "  from public.v_slot_availability\n",
            "  where availability_status = 'AVAILABLE';\n",
            "  if actual_count <> 85 then\n",
            "    raise exception 'AVAILABLE slot mismatch: expected 85, got %', actual_count;\n",
            "  end if;\n",
            "  select count(*) into actual_count\n",
            "  from public.v_slot_availability\n",
            "  where availability_status = 'BLOCKED';\n",
            "  if actual_count <> 7 then\n",
            "    raise exception 'BLOCKED slot mismatch: expected 7, got %', actual_count;\n",
            "  end if;\n",
            "  select count(*) into actual_count\n",
            "  from public.v_slot_availability\n",
            "  where availability_status = 'OCCUPIED';\n",
            "  if actual_count <> 14 then\n",
            "    raise exception 'OCCUPIED slot mismatch: expected 14, got %', actual_count;\n",
            "  end if;\n",
            "end $$;\n",
        ]
    )

    migration.parent.mkdir(parents=True, exist_ok=True)
    seed.parent.mkdir(parents=True, exist_ok=True)
    parity.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text("".join(migration_parts), encoding="utf-8", newline="\n")
    seed.write_text("".join(seed_parts), encoding="utf-8", newline="\n")
    parity.write_text("".join(checks), encoding="utf-8", newline="\n")

    print(f"source_sha256={source_hash}")
    print(f"tables={len(TABLE_ORDER)} rows={sum(EXPECTED_COUNTS.values())}")
    print(f"views={len(EXPECTED_VIEW_COUNTS)} indexes={len(indexes)}")
    print(f"dictionary_columns={dictionary_columns}")
    print(f"migration={migration}")
    print(f"seed={seed}")
    print(f"parity={parity}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs/database_docs/setuhaul_schema_and_seed.sql"),
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=Path("docs/database_docs/setuhaul_data_dictionary.csv"),
    )
    parser.add_argument("--migration", type=Path, required=True)
    parser.add_argument(
        "--seed", type=Path, default=Path("supabase/seed.sql")
    )
    parser.add_argument(
        "--parity",
        type=Path,
        default=Path("supabase/tests/database/parity.sql"),
    )
    args = parser.parse_args()
    build(args.source, args.dictionary, args.migration, args.seed, args.parity)


if __name__ == "__main__":
    main()
