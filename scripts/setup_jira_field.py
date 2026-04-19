"""
Crea el campo personalizado "IA: Prioridad Sugerida" en Jira e imprime su ID.

Uso:
    python scripts/setup_jira_field.py

Requiere .env con JIRA_URL, JIRA_EMAIL, JIRA_TOKEN.
Después, guarda el ID impreso como secret JIRA_SUGGESTED_PRIORITY_FIELD_ID en GitHub.
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]

FIELD_NAME = "IA: Prioridad Sugerida"

url = f"{JIRA_URL}/rest/api/3/field"
payload = {
    "name": FIELD_NAME,
    "description": "Sugerencia de prioridad generada por el agente de triaje IA",
    "type": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
    "searcherKey": "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
}

resp = requests.post(url, json=payload, auth=(JIRA_EMAIL, JIRA_TOKEN))

if resp.status_code == 400:
    print(f"Error 400: {resp.text}")
    print("\nEl campo puede que ya exista. Busca su ID en:")
    print(f"  {JIRA_URL}/rest/api/3/field")
    sys.exit(1)

resp.raise_for_status()
data = resp.json()

field_id = data["id"]
print(f"Campo creado correctamente:")
print(f"  Nombre : {data['name']}")
print(f"  ID     : {field_id}")
print()
print(f"Guarda este valor como secret en GitHub Actions:")
print(f"  JIRA_SUGGESTED_PRIORITY_FIELD_ID = {field_id}")
print()
print("Después activa el campo en el proyecto PT:")
print(f"  {JIRA_URL}/plugins/servlet/project-config/PT/fields")
