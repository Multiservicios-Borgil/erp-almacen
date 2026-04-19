
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Connecting to: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
    with engine.connect() as conn:
        print("Successfully connected to the database via IPv4 Pooler!")
except Exception as e:
    print(f"Error: {e}")
