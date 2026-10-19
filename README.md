# AquaSense

AquaSense water-quality monitoring and decision support system for selected rivers of Norzagaray, Bulacan.

## Project structure

The application includes a Flask dashboard, sensor ingestion, alert management,
historical records, analytics, reports, and a private local-data chat assistant.

## Initial setup (Windows / VS Code)

1. Install Python 3.11+. SQLite is used by default for local development.
2. Open this folder in VS Code.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Optionally copy `.env.example` to `.env` and configure your database. Do not commit `.env`.
6. Seed the demonstration rivers, sensors, readings, and alerts:

   ```powershell
   .\.venv\Scripts\python.exe scripts\seed_demo_data.py
   ```

7. Start the local website:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

## Important

- Seeded readings, including the all-channel example, are demonstration data and are not real measurements; river coordinates are not verified.
- Example threshold rules must be documented and validated before research use.
- Never put secrets in frontend JavaScript or commit `.env`.

## Sensor payload

Send each device reading to `POST /api/ingestion/reading` as JSON. The device
must include its registered `device_id`, the `river_id`, and at least one
numeric measurement. `recorded_at` is optional and accepts an ISO 8601
timestamp. Values are stored as sent; the app does not rescale sensor output.

```json
{
   "device_id": "device-001",
   "river_id": 1,
   "turbidity_ntu": 12,
   "tss": 8,
   "particle_level": 15,
   "clarity": 85,
   "tds_ppm": 245,
   "conductivity": 490,
   "ionic_content": 25,
   "salinity": 0,
   "ph_value": 725,
   "acidity": 0,
   "alkalinity": 0,
   "ph_stability": 95,
   "temperature_c": 2846,
   "ambient_temperature": 3000,
   "change_rate": 12,
   "thermal_anomaly": 0
}
```

All 16 measurements are available in dashboard sensor results, reading history,
analytics, reports, and linked alert details. Values are displayed as received;
document and apply the device's pH/temperature scaling before interpreting them.
The built-in quality assessment
uses the existing turbidity rule; other channels can trigger alerts when an
active threshold rule is configured for that field. Validate sensor scaling
and threshold limits against the device calibration before research use.

## Automatic alert thresholds

Administrators can add, edit, deactivate, and delete sensor thresholds from
the **Automatic alert thresholds** panel on the Alerts page. Each enabled rule
is evaluated against new readings; a breach creates an alert with the selected
severity. Thresholds do not retroactively create alerts for readings already
stored. pH, temperature, and temperature-change limits are entered in
human-readable units and stored internally at ×100 to match the ESP32 payload.
Validate thresholds against calibrated sensor specifications before operational
use.

## AI chat

For fast online replies, create a Groq API key and set `GROQ_API_KEY` in the
local `.env` file or the deployment platform's secret settings. The default
model is `openai/gpt-oss-20b`; change it with `GROQ_MODEL` if needed. The online
provider receives the user's question and locally calculated monitoring
summaries, including river averages and recent alert details. Do not configure
this provider if those data must remain on your own infrastructure.

Exact sensor averages, ranges, and other supported calculations are still
answered directly from the AquaSense database. If Groq is not configured or
unavailable, AquaSense uses local Ollama when available, then falls back to
database-derived answers. Ollama can be installed on Windows with:

```powershell
ollama pull qwen2.5:3b
```

Configure its model and endpoint with `OLLAMA_MODEL` and `OLLAMA_BASE_URL`.

## Deploy with Supabase and Vercel

1. Create a Supabase project. In its **Connect** dialog, choose the shared
   **Transaction pooler** connection string (port `6543`) for Vercel. Keep the
   connection string private and percent-encode reserved characters in its
   password.
2. Create the database schema using one of these methods:

   - In the Supabase **SQL Editor**, run [`scripts/supabase_schema.sql`](scripts/supabase_schema.sql).
     This script is for a new project and enables row-level security without
     adding public API policies. AquaSense accesses the database from its
     trusted Flask server using the project database owner.
   - Or initialize it from a trusted local machine with the application
     initializer below. Do not run both methods on a populated database.

   Set `DATABASE_URL` to the Supabase transaction-pooler URL and run:

   ```powershell
   $env:DATABASE_URL = "postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:6543/postgres?sslmode=require"
   $env:SECRET_KEY = "a-long-random-secret"
   .\.venv\Scripts\python.exe scripts\init_supabase_db.py
   ```

3. To copy the current local data, run the migration script once with the same
   `DATABASE_URL`:

   ```powershell
   .\.venv\Scripts\python.exe scripts\migrate_sqlite_to_supabase.py
   ```

   It copies records from `instance/aquasense.db`, preserving record IDs and
   password hashes, and refuses to copy into non-empty destination tables.
   Back up both databases first. Change the copied `admin` password before
   giving other people access.
4. Push the project to a Git repository and import it in Vercel. Set the Vercel
   project root to this folder and configure these Production and Preview
   environment variables:

   - `DATABASE_URL`: the same Supabase transaction-pooler URL.
   - `SECRET_KEY`: a strong random value, different from development.
   - `COOKIE_SECURE=1`
   - `AUTO_CREATE_SCHEMA=0`

   Vercel uses `main.py` as the Flask entrypoint. The configured build step
   copies `app/static` assets into `public/static` for Vercel's static serving.
5. Deploy and test sign-in, readings, reports, and alert updates. Create user
   accounts before sharing; AquaSense does not currently expose public signup.
   `GET /api/ingestion/health` checks that the application can connect to its
   database and reports `database: connected` when that check succeeds.

The database-backed pages and exact local-data chat answers can run on Vercel.
Qwen/Ollama currently runs only on the same machine as the app and is restricted
to loopback for privacy. Vercel cannot reach your computer's Ollama process, so
free-form local-model chat needs the app and Ollama hosted together on a server,
or a separately secured AI endpoint.
