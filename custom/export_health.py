#!/usr/bin/env python3

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

from garminconnect import Garmin


TOKEN_DIR = Path("~/.garminconnect").expanduser()
OUTPUT_DIR = Path(__file__).parent / "output"
CUMULATIVE_FILE = OUTPUT_DIR / "garmin_health.csv"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def daterange(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def nested(data, *keys, default=None):
    """Safely retrieve a nested dictionary value."""
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def seconds_to_hours(value):
    if value is None:
        return None

    return round(value / 3600, 2)


def minutes_to_hours(value):
    if value is None:
        return None

    return round(value / 60, 2)


def safe_call(name, fn, *args):
    """
    Run one Garmin API call without aborting the whole export
    if that particular metric is unavailable.
    """
    try:
        return fn(*args)

    except Exception as exc:
        print(f"  ! {name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# HRV
# ---------------------------------------------------------------------------

def build_hrv_lookup(hrv_range):
    """
    Garmin's HRV range response has changed shape between API versions.
    Build a date -> HRV summary lookup defensively.
    """
    result = {}

    if not isinstance(hrv_range, dict):
        return result

    possible_rows = (
        hrv_range.get("hrvSummaries")
        or hrv_range.get("hrvSummaryList")
        or hrv_range.get("dailySummaries")
        or []
    )

    if isinstance(possible_rows, list):
        for row in possible_rows:
            if not isinstance(row, dict):
                continue

            day = row.get("calendarDate")

            if day:
                result[day] = row

    return result


# ---------------------------------------------------------------------------
# Sleeping heart rate
# ---------------------------------------------------------------------------

def extract_hr_samples(heart_rate_response):
    """
    Garmin normally returns:
        "heartRateValues": [
            [timestamp_ms, heart_rate],
            ...
        ]

    Return clean (timestamp_ms, bpm) tuples.
    """
    if not isinstance(heart_rate_response, dict):
        return []

    values = heart_rate_response.get("heartRateValues")

    if not isinstance(values, list):
        return []

    samples = []

    for item in values:
        if not isinstance(item, (list, tuple)):
            continue

        if len(item) < 2:
            continue

        timestamp = item[0]
        bpm = item[1]

        if timestamp is None or bpm is None:
            continue

        try:
            timestamp = int(timestamp)
            bpm = float(bpm)

        except (TypeError, ValueError):
            continue

        # Ignore obviously invalid HR values.
        if bpm <= 0:
            continue

        samples.append((timestamp, bpm))

    return samples


def calculate_sleeping_hr(
    sleep_dto,
    current_hr_data,
    previous_hr_data,
):
    """
    Calculate average HR during Garmin's recorded sleep window.

    Sleep commonly starts on the previous calendar day, so combine
    heart-rate samples from both the sleep date and previous date.
    """
    if not isinstance(sleep_dto, dict):
        return None

    sleep_start = sleep_dto.get("sleepStartTimestampGMT")
    sleep_end = sleep_dto.get("sleepEndTimestampGMT")

    if sleep_start is None or sleep_end is None:
        return None

    try:
        sleep_start = int(sleep_start)
        sleep_end = int(sleep_end)

    except (TypeError, ValueError):
        return None

    samples = []

    samples.extend(extract_hr_samples(previous_hr_data))
    samples.extend(extract_hr_samples(current_hr_data))

    sleeping_values = [
        bpm
        for timestamp, bpm in samples
        if sleep_start <= timestamp <= sleep_end
    ]

    if not sleeping_values:
        return None

    return round(mean(sleeping_values), 1)


# ---------------------------------------------------------------------------
# Recovery time
# ---------------------------------------------------------------------------

def recovery_time_hours(readiness):
    """
    python-garminconnect documents Garmin's recoveryTime field as minutes.

    Garmin may preserve the last assigned numeric value even after recovery
    reaches zero, so REACHED_ZERO explicitly means zero remaining recovery.
    """
    if not isinstance(readiness, dict):
        return None

    change_phrase = readiness.get("recoveryTimeChangePhrase")

    if change_phrase == "REACHED_ZERO":
        return 0.0

    recovery_minutes = readiness.get("recoveryTime")

    return minutes_to_hours(recovery_minutes)


# ---------------------------------------------------------------------------
# Existing CSV handling
# ---------------------------------------------------------------------------

def read_existing_csv(filename):
    """
    Read an existing cumulative export into:
        date -> row
    """
    rows = {}

    if not filename.exists():
        return rows

    with filename.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:

        reader = csv.DictReader(handle)

        for row in reader:
            day = row.get("date")

            if day:
                rows[day] = row

    return rows


def write_csv(filename, rows):
    if not rows:
        raise RuntimeError("No rows available to write.")

    filename.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = sorted(
        rows,
        key=lambda row: row["date"],
    )

    with filename.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Missing-data report
# ---------------------------------------------------------------------------

def print_data_quality(rows):
    important_fields = {
        "resting HR": "resting_hr_bpm",
        "sleep": "sleep_hours",
        "sleep score": "sleep_score",
        "sleeping HR": "sleeping_hr_bpm",
        "HRV": "hrv_last_night_avg_ms",
        "stress": "average_stress",
        "Body Battery": "body_battery_high",
        "Training Readiness": "training_readiness_score",
        "steps": "steps",
    }

    print()
    print("Data quality")
    print("------------")

    for label, field in important_fields.items():
        missing = sum(
            1
            for row in rows
            if row.get(field) in (None, "")
        )

        print(
            f"{label:20s}: "
            f"{missing} missing / {len(rows)} days"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export Garmin daily health and recovery data to CSV."
        )
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help=(
            "Number of days to export. "
            "Default: 30."
        ),
    )

    parser.add_argument(
        "--start",
        help=(
            "First date to export as YYYY-MM-DD. "
            "Use together with --end."
        ),
    )

    parser.add_argument(
        "--end",
        help=(
            "Last date to export as YYYY-MM-DD. "
            "Defaults to yesterday."
        ),
    )

    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "Merge exported dates into "
            "custom/output/garmin_health.csv."
        ),
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Resolve date range
    # -----------------------------------------------------------------------

    if args.start and not args.end:
        parser.error(
            "--start requires --end."
        )

    if args.start:
        start_date = datetime.strptime(
            args.start,
            "%Y-%m-%d",
        ).date()

        end_date = datetime.strptime(
            args.end,
            "%Y-%m-%d",
        ).date()

    else:
        if args.end:
            end_date = datetime.strptime(
                args.end,
                "%Y-%m-%d",
            ).date()

        else:
            # Today's data is incomplete, so default to yesterday.
            end_date = date.today() - timedelta(days=1)

        start_date = (
            end_date
            - timedelta(days=args.days - 1)
        )

    if start_date > end_date:
        parser.error(
            "Start date must not be after end date."
        )

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # -----------------------------------------------------------------------
    # Login
    # -----------------------------------------------------------------------

    print("Logging in using saved Garmin tokens...")

    garmin = Garmin()
    garmin.login(str(TOKEN_DIR))

    print("Logged in.")
    print(
        f"Exporting {start_str} through {end_str}"
    )
    print()

    # -----------------------------------------------------------------------
    # Range APIs
    # -----------------------------------------------------------------------

    rhr_data = (
        safe_call(
            "resting HR",
            garmin.get_rhr_daily,
            start_str,
            end_str,
        )
        or []
    )

    body_battery_data = (
        safe_call(
            "Body Battery",
            garmin.get_body_battery,
            start_str,
            end_str,
        )
        or []
    )

    hrv_range = safe_call(
        "HRV",
        garmin.get_hrv_data_range,
        start_str,
        end_str,
    )

    rhr_by_date = {
        row.get("calendarDate"): row.get("value")
        for row in rhr_data
        if isinstance(row, dict)
    }

    battery_by_date = {
        row.get("date"): row
        for row in body_battery_data
        if isinstance(row, dict)
        and row.get("date")
    }

    hrv_by_date = build_hrv_lookup(
        hrv_range
    )

    # Cache HR API responses because sleeping HR needs the previous day too.
    heart_rate_cache = {}

    def get_hr_cached(day):
        day_str = day.isoformat()

        if day_str not in heart_rate_cache:
            heart_rate_cache[day_str] = (
                safe_call(
                    f"heart rate {day_str}",
                    garmin.get_heart_rates,
                    day_str,
                )
                or {}
            )

        return heart_rate_cache[day_str]

    # -----------------------------------------------------------------------
    # Daily APIs
    # -----------------------------------------------------------------------

    rows = []

    for day in daterange(
        start_date,
        end_date,
    ):
        day_str = day.isoformat()

        print(f"Fetching {day_str}...")

        summary = (
            safe_call(
                "daily summary",
                garmin.get_user_summary,
                day_str,
            )
            or {}
        )

        sleep = (
            safe_call(
                "sleep",
                garmin.get_sleep_data,
                day_str,
            )
            or {}
        )

        readiness = (
            safe_call(
                "training readiness",
                garmin.get_morning_training_readiness,
                day_str,
            )
            or {}
        )

        sleep_dto = (
            sleep.get("dailySleepDTO")
            or {}
        )

        # -------------------------------------------------------------------
        # Sleep score
        # -------------------------------------------------------------------

        sleep_scores = (
            sleep_dto.get("sleepScores")
            or {}
        )

        overall_sleep_score = nested(
            sleep_scores,
            "overall",
            "value",
        )

        # -------------------------------------------------------------------
        # HRV
        # -------------------------------------------------------------------

        hrv = hrv_by_date.get(day_str)

        if hrv is None:
            daily_hrv = (
                safe_call(
                    "daily HRV",
                    garmin.get_hrv_data,
                    day_str,
                )
                or {}
            )

            hrv = (
                daily_hrv.get("hrvSummary")
                or {}
            )

        # -------------------------------------------------------------------
        # Sleeping HR
        # -------------------------------------------------------------------

        current_hr = get_hr_cached(day)

        previous_hr = get_hr_cached(
            day - timedelta(days=1)
        )

        sleeping_hr = calculate_sleeping_hr(
            sleep_dto,
            current_hr,
            previous_hr,
        )

        # -------------------------------------------------------------------
        # Body Battery
        # -------------------------------------------------------------------

        battery = battery_by_date.get(
            day_str,
            {},
        )

        # -------------------------------------------------------------------
        # Output row
        # -------------------------------------------------------------------

        row = {
            "date": day_str,

            # ---------------------------------------------------------------
            # General activity
            # ---------------------------------------------------------------

            "steps":
                summary.get("totalSteps"),

            "distance_km":
                (
                    round(
                        summary[
                            "totalDistanceMeters"
                        ] / 1000,
                        2,
                    )
                    if summary.get(
                        "totalDistanceMeters"
                    ) is not None
                    else None
                ),

            "moderate_intensity_minutes":
                summary.get(
                    "moderateIntensityMinutes"
                ),

            "vigorous_intensity_minutes":
                summary.get(
                    "vigorousIntensityMinutes"
                ),

            "total_calories_kcal":
                summary.get(
                    "totalKilocalories"
                ),

            "active_calories_kcal":
                summary.get(
                    "activeKilocalories"
                ),

            # ---------------------------------------------------------------
            # Heart rate
            # ---------------------------------------------------------------

            "resting_hr_bpm":
                (
                    rhr_by_date.get(day_str)
                    or summary.get(
                        "restingHeartRate"
                    )
                ),

            "sleeping_hr_bpm":
                sleeping_hr,

            "min_hr_bpm":
                summary.get(
                    "minHeartRate"
                ),

            "max_hr_bpm":
                summary.get(
                    "maxHeartRate"
                ),

            # ---------------------------------------------------------------
            # Stress
            # ---------------------------------------------------------------

            "average_stress":
                summary.get(
                    "averageStressLevel"
                ),

            # ---------------------------------------------------------------
            # Body Battery
            # ---------------------------------------------------------------

            "body_battery_high":
                summary.get(
                    "bodyBatteryHighestValue"
                ),

            "body_battery_low":
                summary.get(
                    "bodyBatteryLowestValue"
                ),

            "body_battery_charged":
                battery.get(
                    "charged"
                ),

            "body_battery_drained":
                battery.get(
                    "drained"
                ),

            # ---------------------------------------------------------------
            # Sleep
            # ---------------------------------------------------------------

            "sleep_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "sleepTimeSeconds"
                    )
                ),

            "nap_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "napTimeSeconds"
                    )
                ),

            "deep_sleep_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "deepSleepSeconds"
                    )
                ),

            "light_sleep_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "lightSleepSeconds"
                    )
                ),

            "rem_sleep_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "remSleepSeconds"
                    )
                ),

            "awake_sleep_hours":
                seconds_to_hours(
                    sleep_dto.get(
                        "awakeSleepSeconds"
                    )
                ),

            "sleep_score":
                overall_sleep_score,

            "sleep_respiration_avg":
                sleep_dto.get(
                    "averageRespirationValue"
                ),

            # ---------------------------------------------------------------
            # HRV
            # ---------------------------------------------------------------

            "hrv_last_night_avg_ms":
                (
                    hrv.get("lastNightAvg")
                    if isinstance(hrv, dict)
                    else None
                ),

            "hrv_weekly_avg_ms":
                (
                    hrv.get("weeklyAvg")
                    if isinstance(hrv, dict)
                    else None
                ),

            "hrv_5min_high_ms":
                (
                    hrv.get(
                        "lastNight5MinHigh"
                    )
                    if isinstance(hrv, dict)
                    else None
                ),

            "hrv_status":
                (
                    hrv.get("status")
                    if isinstance(hrv, dict)
                    else None
                ),

            # ---------------------------------------------------------------
            # Training readiness
            # ---------------------------------------------------------------

            "training_readiness_score":
                (
                    readiness.get("score")
                    if isinstance(
                        readiness,
                        dict,
                    )
                    else None
                ),

            "training_readiness_level":
                (
                    readiness.get("level")
                    if isinstance(
                        readiness,
                        dict,
                    )
                    else None
                ),

            "recovery_time_hours":
                recovery_time_hours(
                    readiness
                ),
        }

        rows.append(row)

    # -----------------------------------------------------------------------
    # Write output
    # -----------------------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.update:
        existing = read_existing_csv(
            CUMULATIVE_FILE
        )

        # New data replaces existing data for the same date.
        for row in rows:
            existing[row["date"]] = row

        combined = list(
            existing.values()
        )

        write_csv(
            CUMULATIVE_FILE,
            combined,
        )

        output_file = CUMULATIVE_FILE

        print()
        print(
            f"Updated: {output_file}"
        )
        print(
            f"Total dates in file: "
            f"{len(combined)}"
        )

    else:
        output_file = (
            OUTPUT_DIR
            / (
                f"garmin_health_"
                f"{start_str}_to_{end_str}.csv"
            )
        )

        write_csv(
            output_file,
            rows,
        )

        print()
        print(
            f"Created: {output_file}"
        )

    print(
        f"Fetched {len(rows)} days "
        f"from Garmin."
    )

    print_data_quality(rows)


if __name__ == "__main__":
    main()