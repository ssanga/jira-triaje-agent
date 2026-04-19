import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
from src.jira import reset_issue_types, reset_priorities

load_dotenv()

PROJECT_KEY = "PT"

print(f"Reseteando tipologías del proyecto '{PROJECT_KEY}' a Task...\n")
reset_issue_types(PROJECT_KEY)

print(f"\nReseteando prioridades del proyecto '{PROJECT_KEY}' a Medium...\n")
reset_priorities(PROJECT_KEY)

print("\nListo.")
