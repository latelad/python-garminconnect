# Garmin Custom Health Exporter

This folder contains a small custom exporter for pulling daily health/recovery data from Garmin Connect using the local `garminconnect` Python library.

The goal is to keep the workflow simple:

1. Garmin CIRQA syncs to Garmin Connect.
2. Run the exporter locally.
3. It updates a clean CSV with daily health/recovery metrics.
4. Upload that CSV together with the Hevy workout export to an LLM for training/recovery analysis.

The custom script contains no Garmin username, password, or tokens.

---

## Folder layout

Recommended structure:

```text
python-garminconnect/
├── .venv/
├── garminconnect/
├── custom/
│   ├── export_health.py
│   ├── README.md
│   └── output/
│       └── garmin_health.csv
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
- Python 3.x
- Git Bash
- A working local clone/fork of `python-garminconnect`
- Garmin Connect account
- CIRQA or another Garmin device syncing health data

This setup was tested using a Python virtual environment.

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

After activation, the prompt should show:

```text
(.venv)
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

Every time you open a new Git Bash window, activate it again:

```bash
source .venv/Scripts/activate
```

---

## First Garmin login

The repository includes `example.py`, which is useful for confirming that Garmin authentication works.

On Windows Git Bash, use `winpty` for the first interactive login:

```bash
winpty python ./example.py
```

Git Bash may otherwise have problems with Python's hidden password prompt.

During login:

- enter the Garmin account email;
- enter the Garmin password;
- enter MFA/2FA if Garmin requests it.

The password field intentionally displays no characters while typing.

After successful authentication, Garmin reusable authentication tokens are stored locally.

Typical location:

```text
~/.garminconnect/garmin_tokens.json
```

On Windows this usually means something similar to:

```text
C:\Users\<username>\.garminconnect\garmin_tokens.json
```

The token file is outside the Git repository.

It should be treated like a password because a valid refresh token may allow access to Garmin account data.

Do **not**:

- commit this file;
- copy it into the repository;
- upload it to an LLM;
- paste its contents into chat;
- share it publicly.

The library stores Garmin authentication tokens there rather than storing the Garmin password in the repository.

After the first successful login, later commands normally use saved tokens and do not require `winpty`.

A successful test may look similar to:

```text
Logged in using saved tokens.
Steps today : ...
Calories    : ...
Distance    : ...
Resting HR  : ...
```

---

## Health exporter

The custom exporter is:

```text
custom/export_health.py
```

It performs read-only Garmin Connect requests and writes health/recovery data to CSV.

It does not upload, modify, or delete Garmin Connect data.

The exporter currently collects useful daily metrics such as:

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

The exporter intentionally does not calculate its own overall recovery score. Interpretation is done later using the raw/processed Garmin measurements together with workout data and context.

---

## Quick test

Activate the virtual environment:

```bash
source .venv/Scripts/activate
```

Fetch the previous seven complete days:

```bash
python custom/export_health.py --days 7
```

Today's data is intentionally excluded by default because Garmin may still be updating it.

The script creates a dated CSV under:

```text
custom/output/
```

For example:

```text
custom/output/garmin_health_2026-09-13_to_2026-09-19.csv
```

At the end, the script prints a missing-data summary.

Example:

```text
Data quality
------------
resting HR          : 0 missing / 7 days
sleep               : 0 missing / 7 days
sleep score         : 0 missing / 7 days
sleeping HR         : 0 missing / 7 days
HRV                 : 0 missing / 7 days
stress              : 0 missing / 7 days
Body Battery        : 0 missing / 7 days
Training Readiness  : 0 missing / 7 days
steps               : 0 missing / 7 days
```

Occasional missing data can be normal if Garmin has not yet synchronized or calculated a metric.

---

## Create the main cumulative file

For normal use, maintain one file:

```text
custom/output/garmin_health.csv
```

For the first run, fetch the whole period needed and use `--update`.

Example:

```bash
python custom/export_health.py --days 35 --update
```

This creates or updates:

```text
custom/output/garmin_health.csv
```

When dates already exist, newly fetched values replace the old rows for those dates.

This is useful because Garmin may finalize sleep, readiness, or other metrics after an earlier sync.

---

## Normal weekly workflow

Once per week:

```bash
source .venv/Scripts/activate
python custom/export_health.py --days 10 --update
```

Using 10 days instead of exactly 7 gives Garmin a few overlapping days that can be refreshed.

Then use:

```text
custom/output/garmin_health.csv
```

for analysis.

---

## Normal monthly workflow

Once per month:

```bash
source .venv/Scripts/activate
python custom/export_health.py --days 35 --update
```

Using 35 days provides several overlapping days and keeps the cumulative file current.

---

## Export a specific date range

To export a particular period without changing the cumulative file:

```bash
python custom/export_health.py \
  --start 2026-08-20 \
  --end 2026-09-19
```

To merge that period into the cumulative file:

```bash
python custom/export_health.py \
  --start 2026-08-20 \
  --end 2026-09-19 \
  --update
```

`--start` requires `--end`.

---

## Files used for training analysis

The intended analysis workflow is:

```text
Garmin CIRQA
    ↓
Garmin Connect
    ↓
custom/export_health.py
    ↓
garmin_health.csv

Hevy
    ↓
workout_data.csv
```

Upload both:

```text
garmin_health.csv
workout_data.csv
```

to the analysis project/chat.

Typical analysis can compare:

- workout performance;
- training frequency;
- exercise progression;
- sleep;
- HRV;
- resting HR;
- sleeping HR;
- stress;
- Body Battery;
- Training Readiness;
- daily activity.

Wearable metrics should generally be interpreted as trends relative to the individual's own baseline rather than as clinical measurements.

---

## Git safety

Before committing changes, check:

```bash
git status
```

The following should be safe to commit:

```text
custom/export_health.py
custom/README.md
```

The following should **not** be committed:

```text
custom/output/
garmin_health.csv
garmin_tokens.json
.env
```

Also avoid committing:

- Garmin username/password;
- API/session tokens;
- exported health data;
- Hevy workout exports;
- other personal health files.

If unsure whether something is ignored:

```bash
git check-ignore -v custom/output/garmin_health.csv
```

If Git reports the matching `.gitignore` rule, the file is ignored.

---

## Authentication troubleshooting

### Git Bash appears frozen after entering email

The first login may fail because Git Bash has trouble with Python's hidden password prompt.

Use:

```bash
winpty python ./example.py
```

The password remains invisible while typing.

### New Git Bash window

Virtual-environment activation does not survive closing the terminal.

Run:

```bash
source .venv/Scripts/activate
```

again.

You do **not** need to recreate `.venv`.

### Confirm the virtual environment is active

Run:

```bash
which python
python --version
```

`which python` should point somewhere inside:

```text
.../python-garminconnect/.venv/Scripts/python
```

### Check saved Garmin tokens

```bash
ls -la ~/.garminconnect
```

Do not print or share the token file contents.

### Saved login stops working

Garmin may expire or invalidate authentication tokens.

If necessary, rerun:

```bash
winpty python ./example.py
```

and authenticate again.

---

## Security notes

`python-garminconnect` uses unofficial Garmin Connect endpoints.

Important implications:

- the library may stop working if Garmin changes its private APIs;
- authentication behavior can change;
- Garmin may rate-limit automated access;
- this is not equivalent to Garmin's officially supported Health API.

The local source was reviewed before use for:

- credential handling;
- non-Garmin network destinations;
- token storage;
- filesystem writes;
- subprocess/shell execution;
- persistence mechanisms.

The custom exporter itself contains no secrets and performs read-only data retrieval.

The main sensitive local item is:

```text
~/.garminconnect/garmin_tokens.json
```

The other sensitive files are the health CSVs under:

```text
custom/output/
```

---

## Updating the upstream library

Because this repository is a fork, upstream changes can be merged when needed.

Keep custom work under:

```text
custom/
```

and avoid modifying the core `garminconnect` library unless necessary.

That minimizes merge conflicts when upstream authentication/API fixes are incorporated later.

Before upgrading or merging major upstream changes, it is sensible to review the diff, especially changes involving:

- authentication;
- network endpoints;
- token handling;
- dependencies;
- filesystem access.

---

## Recommended routine

Weekly:

```bash
cd ~/Documents/ClaudeCode/Garmin/python-garminconnect
source .venv/Scripts/activate
python custom/export_health.py --days 10 --update
```

Monthly:

```bash
cd ~/Documents/ClaudeCode/Garmin/python-garminconnect
source .venv/Scripts/activate
python custom/export_health.py --days 35 --update
```

Then upload:

```text
custom/output/garmin_health.csv
```

together with the latest Hevy workout export for analysis.
