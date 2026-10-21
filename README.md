# SoundMess

## Local setup

The Django project lives in `my_app/`. The repository uses one shared virtual environment at `django/.venv/`.

```powershell
Set-Location 'C:\Univer\semestr 6\PY\django\my_app'
& '..\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '..\.venv\Scripts\python.exe' manage.py migrate
& '..\.venv\Scripts\python.exe' manage.py runserver
```

Run checks and tests with:

```powershell
& '..\.venv\Scripts\python.exe' manage.py check
& '..\.venv\Scripts\python.exe' manage.py test pc_store
```

Copy `my_app/.env.example` to `my_app/.env` and provide a production secret key before deployment. The application reads `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` and `JAMENDO_CLIENT_ID` from the environment.

## Importing legal metadata

The Jamendo importer is intentionally metadata-first. Preview results without writing to the database:

```powershell
& '..\.venv\Scripts\python.exe' manage.py import_jamendo --client-id YOUR_CLIENT_ID --dry-run
```

Media files are not downloaded automatically. Confirm the provider's current license and API terms before adding a media download step.