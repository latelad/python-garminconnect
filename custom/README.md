# Garmin Custom Export Tools

This folder contains small custom exporters for pulling useful health, recovery, and activity data from Garmin Connect using the local `garminconnect` Python library.

The intended workflow is:

1. Garmin CIRQA syncs to Garmin Connect.
2. Run one local update script.
3. It refreshes:
   - daily health/recovery data;
   - recorded Garmin activity summaries.
4. Upload those CSV files together with the Hevy workout export for analysis.

The custom scripts contain no Garmin username, password, or authentication tokens.

---

## Recommended folder layout

```text
python-garminconnect/
├── .venv/
├── garminconnect/
├── custom/
│   ├── export_health.py
│   ├── export_activities.py
│   ├── update_garmin.sh
│   ├── README.md
│   └── output/
│       ├── garmin_health.csv
│       └── garmin_activities.csv
└── .gitignore
```

`custom/output/` contains personal health data and should not be committed.

Add this to the repository `.gitignore`:

```gitignore
custom/output/
```

---

## Requirements

- Windows
- Git Bash
- Python 3.x
- A local clone/fork of `python-garminconnect`
- Garmin Connect account
- Garmin CIRQA or another Garmin device syncing health data

The setup uses a Python virtual environment stored in:

```text
.venv/
```

---

## Initial Python setup

From Git Bash, go to the repository:

```bash
cd ~/Documents/ClaudeCode/Garmin/python-garminconnect
```

Create the virtual environment:

```bash
py -m venv .venv --copies
```

Activate it:

```bash
source .venv/Scripts/activate
```

Verify Python:

```bash
python --version
```

Install the local repository into the virtual environment:

```bash
python -m pip install --upgrade pip
pip install -e .
```

You normally only need to create and install the virtual environment once.

---

## First Garmin login

The repository includes `example.py`, which can be used to verify authentication.

On Windows Git Bash, use:

```bash
winpty python ./example.py
```

Git Bash may otherwise have trouble with Python's hidden password prompt.

During first login:

- enter the Garmin account email;
- enter the Garmin password;
- enter MFA/2FA if Garmin requests it.

The password field intentionally shows no characters while typing.

After successful login, reusable Garmin authentication tokens are stored locally.

Typical location:

```text
~/.garminconnect/garmin_tokens.json
```

On Windows this is usually similar to:

```text
C:\Users\<username>\.garminconnect\garmin_tokens.json
```

The token file is outside the Git repository.

Treat it like a password. Do not:

- commit it;
- copy it into the repository;
- upload it to an LLM;
- paste its contents into chat;
- share it publicly.

Normal exporter runs use the saved token and do not need your Garmin password.

---

# Health exporter

Script:

```text
custom/export_health.py
```

Output:

```text
custom/output/garmin_health.csv
```

The health exporter stores one row per day.

It currently collects useful daily recovery and health metrics such as:

- steps;
- distance;
- moderate/vigorous intensity minutes;
- calories;
- resting heart rate;
- sleeping heart rate;
- minimum/maximum heart rate;
- average stress;
- Body Battery high/low/charged/drained;
- sleep duration;
- naps;
- deep/light/REM/awake sleep;
- sleep score;
- sleep respiration;
- nightly HRV;
- rolling HRV average;
- 5-minute HRV high;
- HRV status;
- Training Readiness score/level;
- recovery time.

The exporter intentionally does not calculate its own overall recovery score.

---

## Health exporter test

Fetch the previous seven complete days:

```bash
python custom/export_health.py --days 7
```

Today's data is excluded by default because Garmin may still be updating it.

A dated test CSV is written under:

```text
custom/output/
```

Example:

```text
garmin_health_2026-09-13_to_2026-09-19.csv
```

The script also prints a missing-data summary.

---

## Create/update the cumulative health file

```bash
python custom/export_health.py --days 35 --update
```

This creates or updates:

```text
custom/output/garmin_health.csv
```

If an existing date is fetched again, the newly fetched row replaces the older row. This allows Garmin to finalize recently synchronized sleep/readiness data.

---

# Activity exporter

Script:

```text
custom/export_activities.py
```

Output:

```text
custom/output/garmin_activities.csv
```

The activity exporter stores one row per Garmin recorded activity.

It currently collects:

- Garmin activity ID;
- local/GMT start time;
- activity name;
- activity type;
- duration;
- moving duration;
- elapsed duration;
- distance;
- average heart rate;
- maximum heart rate;
- aerobic Training Effect;
- anaerobic Training Effect;
- Garmin activity training load;
- Training Effect label;
- calories;
- time in HR zones 1-5.

It intentionally does **not** download:

- GPS tracks;
- second-by-second heart-rate data;
- FIT files;
- raw exercise details;
- other large activity payloads.

The activity summary is intended to provide cardiovascular/systemic context around the detailed resistance-training data already available from Hevy.

---

## Activity exporter test

Fetch recent activities:

```bash
python custom/export_activities.py --days 14
```

A dated CSV is created under:

```text
custom/output/
```

Example:

```text
garmin_activities_2026-09-07_to_2026-09-20.csv
```

The script also prints a missing-data summary.

---

## Create/update the cumulative activity file

```bash
python custom/export_activities.py --days 35 --update
```

This creates or updates:

```text
custom/output/garmin_activities.csv
```

Activities are matched by Garmin activity ID, so re-fetching an existing activity replaces its previous row instead of creating a duplicate.

---

# One-command updater

The easiest normal workflow is to use:

```text
custom/update_garmin.sh
```

The script:

1. finds the repository root automatically;
2. checks that `.venv` exists;
3. uses `.venv/Scripts/python.exe` directly;
4. updates the health CSV;
5. updates the activities CSV;
6. stops if either exporter fails.

Because the script calls the virtual environment's Python directly, you do **not** need to run:

```bash
source .venv/Scripts/activate
```

first.

---

## Normal weekly update

From Git Bash:

```bash
./custom/update_garmin.sh
```

Default lookback:

```text
10 days
```

The overlap gives Garmin a chance to refresh/finalize recent data.

---

## Use a different lookback period

Pass the number of days as the first argument:

```bash
./custom/update_garmin.sh 35
```

This updates both health and activities for the previous 35 days.

Examples:

```bash
./custom/update_garmin.sh 10
./custom/update_garmin.sh 35
./custom/update_garmin.sh 60
```

---

## First full CIRQA history load

If roughly one month of Garmin history is available:

```bash
./custom/update_garmin.sh 35
```

Afterward, normal weekly use can return to:

```bash
./custom/update_garmin.sh
```

---

# Explicit date ranges

The individual Python scripts still support exact date ranges.

Health:

```bash
python custom/export_health.py \
  --start 2026-08-20 \
  --end 2026-09-19 \
  --update
```

Activities:

```bash
python custom/export_activities.py \
  --start 2026-08-20 \
  --end 2026-09-19 \
  --update
```

Use these when reconstructing a specific historical period.

---

# Files used for training analysis

The intended analysis setup is:

```text
Garmin CIRQA
    ↓
Garmin Connect
    ↓
export_health.py
    ↓
garmin_health.csv

Garmin CIRQA
    ↓
Garmin Connect
    ↓
export_activities.py
    ↓
garmin_activities.csv

Hevy
    ↓
workout_data.csv
```

Upload:

```text
garmin_health.csv
garmin_activities.csv
workout_data.csv
```

for analysis.

Together, these provide three complementary layers:

### Hevy

Detailed resistance-training performance:

- exercises;
- sets;
- reps;
- weights;
- exercise order;
- progression.

### Garmin activity data

Session-level cardiovascular/systemic load:

- duration;
- average/max HR;
- HR-zone distribution;
- Training Effect;
- activity training load.

### Garmin health data

Recovery/context between workouts:

- HRV;
- resting/sleeping HR;
- sleep;
- stress;
- Body Battery;
- Training Readiness;
- daily activity.

Wearable metrics should generally be interpreted as trends relative to the individual's own baseline rather than as clinical measurements.

---

# Git safety

Before committing:

```bash
git status
```

Safe to commit:

```text
custom/export_health.py
custom/export_activities.py
custom/update_garmin.sh
custom/README.md
```

Do **not** commit:

```text
custom/output/
garmin_health.csv
garmin_activities.csv
garmin_tokens.json
.env
```

Also avoid committing:

- Garmin credentials;
- session/authentication tokens;
- exported health/activity data;
- Hevy workout exports;
- other personal health files.

Check whether a file is ignored:

```bash
git check-ignore -v custom/output/garmin_health.csv
```

---

# Authentication troubleshooting

## Git Bash appears frozen during first login

Use:

```bash
winpty python ./example.py
```

The password remains invisible while typing.

## Saved login stops working

Garmin may invalidate or expire authentication tokens.

Run:

```bash
source .venv/Scripts/activate
winpty python ./example.py
```

and authenticate again.

## Check saved token location

```bash
ls -la ~/.garminconnect
```

Do not print or share the token file contents.

---

# Update-script troubleshooting

## Permission denied

If Git Bash says:

```text
Permission denied
```

run:

```bash
chmod +x custom/update_garmin.sh
```

Then try again:

```bash
./custom/update_garmin.sh
```

Git can track the executable flag, so this normally only needs to be done once.

## Virtual environment not found

The update script expects:

```text
.venv/Scripts/python.exe
```

at the repository root.

Create the venv if needed:

```bash
py -m venv .venv --copies
source .venv/Scripts/activate
pip install -e .
```

---

# Security notes

`python-garminconnect` uses unofficial Garmin Connect endpoints.

Important implications:

- Garmin can change its private APIs;
- authentication behavior may change;
- Garmin can rate-limit automated access;
- this is not the same as Garmin's officially supported Health API.

The local source was reviewed before use for:

- credential handling;
- non-Garmin network destinations;
- token storage;
- filesystem writes;
- subprocess/shell execution;
- persistence mechanisms.

The custom exporters perform read-only data retrieval.

The main sensitive local items are:

```text
~/.garminconnect/garmin_tokens.json
custom/output/garmin_health.csv
custom/output/garmin_activities.csv
```

---

# Updating the upstream library

Because this repository is a fork, upstream changes can be merged when needed.

Keep custom work under:

```text
custom/
```

and avoid modifying core `garminconnect` files unless necessary.

Before merging important upstream changes, review changes involving:

- authentication;
- network endpoints;
- token handling;
- dependencies;
- filesystem access.

---

# Recommended routine

Weekly:

```bash
cd ~/Documents/ClaudeCode/Garmin/python-garminconnect
./custom/update_garmin.sh
```

Monthly or after a longer gap:

```bash
cd ~/Documents/ClaudeCode/Garmin/python-garminconnect
./custom/update_garmin.sh 35
```

Then upload:

```text
custom/output/garmin_health.csv
custom/output/garmin_activities.csv
```

together with the latest Hevy workout export for analysis.
