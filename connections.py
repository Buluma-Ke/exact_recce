import getpass
from sqlalchemy import create_engine


def get_db_engine():
  """
  Prompt for PostgreSQL credentials and return a SQLAlchemy engine instance.
  """

  password = getpass.getpass("Enter your PostgreSQL password: ")
  db_uri = (
      f"postgresql+psycopg2://Admin:{password}@localhost:5432/exact_experience"
  )
  return create_engine(db_uri)
