# Fieldnote Student Records

A Flask application for maintaining student records in MySQL and reviewing aggregate student composition. The directory stores student name, age, registration number, section, year of study, and department. Reports summarize saved rows without drawing conclusions about learning or ability.

## Setup

1. Ensure Python 3.10+ and MySQL 8+ are installed.
2. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. `.env` contains local MySQL connection settings and is excluded from Git. For a fresh setup, copy `.env.example` to `.env` and fill in the values.
4. Ensure MySQL is running. The app connects on startup and creates the `course_analytics` database (if missing) and `students` table when the configured account has permission.
5. Run the app:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

   Open <http://127.0.0.1:5000>. If MySQL is unavailable, the app still opens and displays the connection error and settings to check.

## Student records

All six fields are required. Age must be between 1 and 120; year of study must be between 1 and 12. Registration numbers are uppercased and unique. The directory supports search, edit, and delete. Summary counts and reports are reloaded from MySQL after each change.

## Reports

Choose **Build report** in the directory or **Reports** in the navigation. The report is queried from MySQL each time it is opened or refreshed. It summarizes students by department, year, and department/section, and displays mean/median age and category charts. Names and registration numbers are excluded from the report.

These are descriptive summaries of entered records. Demographic patterns or missing records are not evidence about a student's learning, performance, or ability.

## Schema and tests

The app creates the student table automatically. To initialize the full course analytics schema manually:

```powershell
mysql -u root -p < schema.sql
```

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```