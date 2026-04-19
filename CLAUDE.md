# Contexto del proyecto: jira-triaje-agent

## Descripción
Agente autónomo de triaje de incidencias Jira con GitHub Pages + GitHub Actions + GitHub Models.
Lee bugs de Jira, propone prioridades con gpt-4o via GitHub Models, y permite a usuarios de negocio
aprobar los cambios desde una web estática (GitHub Pages) sin acceso a Jira.

## Estructura
- `src/` — código fuente principal
- `tests/` — tests unitarios con pytest
- `data/triage.json` — resultados del triaje (generado automáticamente)
- `.github/workflows/` — automatización con GitHub Actions
- `index.html` — UI web para GitHub Pages
- `.env` — variables de entorno locales (no subir a git)

## Convenciones
- Tests con pytest
- Variables de entorno via python-dotenv
- Código en src/
