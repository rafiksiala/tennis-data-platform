"""Configuration centralisee, lue depuis les variables d'environnement (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://tennis:tennis_dev_password@localhost:55432/tennis_data",
)
API_TENNIS_KEY = os.environ.get("API_TENNIS_KEY")
