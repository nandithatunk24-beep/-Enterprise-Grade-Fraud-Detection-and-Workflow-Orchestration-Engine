# Transaction Safety Monitor

A warm, responsive Flask web prototype for a simulated person-to-person transfer workflow. The app automatically calculates a rule-based risk score, risk level, suggested action, explanation, and saves the result to a local SQLite database.

## Run on Windows (PowerShell)

1. Open this folder in VS Code.
2. In the VS Code terminal, run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py
   ```

3. Open `http://127.0.0.1:5000` in your browser.
4. Stop the server with `Ctrl+C` in the terminal.

Using `.venv\Scripts\python.exe` directly avoids PowerShell's script activation policy issue.

## Automatic demo rules

- Amount above ₹50,000: +40
- New location compared with this sender's saved history: +30 (only applies when there is already saved sender history)
- Transfer time from 12:00 AM to 4:59 AM: +20
- At least 3 earlier saved transfers by this sender during the preceding 60 minutes: +20
- Scores 0–29: Low / Approve; 30–59: Medium / Review; 60+: High / Block

These are explicit prototype assumptions for demonstrating the workflow, not validated banking policy. The app does not connect to banks, move money, or use machine learning. It uses synthetic/manual data and SQLite by default to make local setup easy. If the final project must use MySQL, the database adapter should be switched before submission.

## Files

- `app.py` — Flask routes, rule engine and SQLite persistence
- `templates/` — page templates
- `static/style.css` — responsive warm/green styling
- `requirements.txt` — Python dependency
