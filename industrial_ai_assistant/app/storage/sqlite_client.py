from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from app.core.constants import DB_PATH
from app.storage.models import Base

class SQLiteClient:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.init_db()

    def init_db(self):
        Base.metadata.create_all(bind=self.engine)
        self._migrate_schema()

    def _migrate_schema(self):
        """
        Comprehensive schema migration for all tables (Phase 21+).
        Adds missing columns to existing tables without data loss.
        Uses SQLite ALTER TABLE ADD COLUMN (non-destructive).
        """
        inspector = inspect(self.engine)
        existing_tables = inspector.get_table_names()

        with self.engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue  # Table is new — create_all() already handles it

                existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
                model_cols = {col.name: col for col in table.columns}

                for col_name, col_obj in model_cols.items():
                    if col_name not in existing_cols:
                        # Determine SQLite type
                        col_type = str(col_obj.type)
                        nullable = "NULL" if col_obj.nullable else "NOT NULL"
                        default = ""
                        if col_obj.default is not None:
                            try:
                                val = col_obj.default.arg
                                if callable(val):
                                    default = ""  # Can't set callable defaults in ALTER
                                elif isinstance(val, str):
                                    default = f" DEFAULT '{val}'"
                                elif isinstance(val, bool):
                                    default = f" DEFAULT {int(val)}"
                                elif isinstance(val, (int, float)):
                                    default = f" DEFAULT {val}"
                            except Exception:
                                default = ""

                        # SQLite ALTER TABLE ADD COLUMN cannot have NOT NULL without default
                        if nullable == "NOT NULL" and not default:
                            nullable = "NULL"

                        sql = f"ALTER TABLE {table.name} ADD COLUMN {col_name} {col_type} {nullable}{default}"
                        try:
                            conn.execute(text(sql))
                            conn.commit()
                            print(f"🔧 Migrated: {table.name}.{col_name} ({col_type})")
                        except Exception as e:
                            if "duplicate column" not in str(e).lower():
                                print(f"⚠️ Migration skipped {table.name}.{col_name}: {e}")

    def get_session(self) -> Session:
        return self.SessionLocal()
