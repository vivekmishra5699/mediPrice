# init_db_script.py
from app import app, init_db
import os

# Needed because init_db uses app context
with app.app_context():
    db_path = app.config['DATABASE']
    # Basic check to avoid re-initializing if file exists (optional)
    if not os.path.exists(db_path):
         print(f"Database not found at {db_path}. Initializing...")
         try:
             init_db()
             print("Database initialized successfully.")
         except Exception as e:
             print(f"Error initializing database: {e}")
    else:
         print(f"Database {db_path} already exists.")