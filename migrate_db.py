import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    print("Error: No se encontro DATABASE_URL")
    exit(1)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    try:
        print("Migrando base de datos...")
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS camion INTEGER DEFAULT 1;"))
        conn.commit()
        print("OK: Columna 'camion' asegurada en la tabla 'items'.")
    except Exception as e:
        print(f"ERROR: {e}")
