#!/usr/bin/env python3

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from garminconnect import Garmin


TOKEN_DIR = Path("~/.garminconnect").expanduser()
OUTPUT_DIR = Path(__file__).parent / "output"
CUMULATIVE_FILE = OUTPUT_DIR / "garmin_activities.csv"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def safe_call(name, fn, *args, **kwargs):
    """
    Run one Garmin API call without aborting the whole export if that
    particular request is unavailable.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        print(f"  ! {name}: {exc}")
        return None


def seconds_to_minutes(value):
    if value is None:
        return None

    try:
        return round(float(value) / 60, 2)
    except (TypeError, ValueError):
        return None


def meters_to_km(value):
    if value is None:
        return None

    try:
        return round(float(value) / 1000, 2)
    except (TypeError, ValueError):
        return None


def first_non_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Activity helpers
# ---------------------------------------------------------------------------

def activity_type_name(activity):
    """
    Garmin normally returns:
        "activityType": {"typeKey": "..."}
    but keep this defensive in case the response changes.
    """
    activity_type = activity.get("activityType")

    if isinstance(activity_type, dict):
        return first_non_none(
            activity_type.get("typeKey"),
            activity_type.get("typeName"),
            activity_type.get("parentTypeId"),
        )

    return activity_type


def extract_zone_number(item, fallback=None):
    if not isinstance(item, dict):
        return fallback

    value = first_non_none(
        item.get("zoneNumber"),
        item.get("zone"),
        item.get("zoneIndex"),
        item.get("zoneId"),
    )

    if isinstance(value, str):
        # Accept values such as "ZONE_1" or "zone1".
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            value = digits

    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def extract_zone_seconds(item):
    if not isinstance(item, dict):
        return None

    value = first_non_none(
        item.get("secsInZone"),
        item.get("secondsInZone"),
        item.get("timeInZone"),
        item.get("duration"),
        item.get("seconds"),
        item.get("value"),
    )

    try:
        return round(float(value), 1) if value is not None else None
    except (TypeError, ValueError):
        return None


def extract_hr_zones(response):
    """
    Convert Garmin's hrTimeInZones response into:
        {1: seconds, 2: seconds, ...}

    The unofficial endpoint has had more than one response shape, so this
    parser is intentionally defensive. If Garmin changes the format again,
    the export still succeeds and the HR-zone fields remain blank.
    """
    result = {}

    if response is None:
        return result

    # Common case: endpoint returns a list of zone dictionaries.
    if isinstance(response, list):
        for index, item in enumerate(response, start=1):
            if not isinstance(item, dict):
                continue

            zone = extract_zone_number(item, fallback=index)
            seconds = extract_zone_seconds(item)

            if zone is not None and seconds is not None:
                result[zone] = seconds

        return result

    if not isinstance(response, dict):
        return result

    # Possible nested-list keys.
    for key in (
        "zones",
        "heartRateZones",
        "hrZones",
        "timeInZones",
        "zoneSummaries",
    ):
        value = response.get(key)

        if isinstance(value, list):
            nested = extract_hr_zones(value)
            if nested:
                return nested

    # Possible dictionary with keys such as "zone1", "ZONE_2", "1", etc.
    for key, value in response.items():
        if isinstance(value, dict):
            zone = extract_zone_number(value)

            if zone is None:
                digits = "".join(ch for ch in str(key) if ch.isdigit())
                zone = int(digits) if digits else None

            seconds = extract_zone_seconds(value)

            if zone is not None and seconds is not None:
                result[zone] = seconds

        elif isinstance(value, (int, float)):
            key_lower = str(key).lower()

            if "zone" in key_lower:
                digits = "".join(ch for ch in key_lower if ch.isdigit())

                if digits:
                    result[int(digits)] = round(float(value), 1)

    return result


# ---------------------------------------------------------------------------
# Existing CSV handling
# ---------------------------------------------------------------------------

def read_existing_csv(filename):
    """
    Read existing cumulative activity data into:
        activity_id -> row
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
            activity_id = row.get("activity_id")

            if activity_id:
                rows[str(activity_id)] = row

    return rows


def sort_key(row):
    return (
        row.get("start_time_local") or "",
        row.get("activity_id") or "",
    )


def write_csv(filename, rows):
    if not rows:
        raise RuntimeError("No rows available to write.")

    filename.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = sorted(rows, key=sort_key)

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
# Quality report
# ---------------------------------------------------------------------------

def print_data_quality(rows):
    fields = {
        "start time": "start_time_local",
        "activity type": "activity_type",
        "duration": "duration_minutes",
        "average HR": "average_hr_bpm",
        "max HR": "max_hr_bpm",
        "HR zones": "hr_zone_1_seconds",
        "aerobic effect": "aerobic_training_effect",
        "anaerobic effect": "anaerobic_training_effect",
        "training load": "activity_training_load",
    }

    print()
    print("Data quality")
    print("------------")

    for label, field in fields.items():
        missing = sum(
            1
            for row in rows
            if row.get(field) in (None, "")
        )

        print(
            f"{label:20s}: "
            f"{missing} missing / {len(rows)} activities"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export Garmin activity summaries and heart-rate-zone durations "
            "to CSV."
        )
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to export. Default: 30.",
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
            "Defaults to today."
        ),
    )

    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "Merge activities into "
            "custom/output/garmin_activities.csv."
        ),
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Resolve date range
    # -----------------------------------------------------------------------

    if args.start and not args.end:
        parser.error("--start requires --end.")

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
            # Activities are completed events, so including today is useful.
            end_date = date.today()

        start_date = (
            end_date
            - timedelta(days=args.days - 1)
        )

    if start_date > end_date:
        parser.error("Start date must not be after end date.")

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
        f"Fetching activities from {start_str} through {end_str}"
    )
    print()

    # -----------------------------------------------------------------------
    # Fetch activity summaries
    # -----------------------------------------------------------------------

    activities = (
        safe_call(
            "activities",
            garmin.get_activities_by_date,
            start_str,
            end_str,
            sortorder="asc",
        )
        or []
    )

    print(f"Found {len(activities)} activities.")

    rows = []

    for index, activity in enumerate(activities, start=1):
        if not isinstance(activity, dict):
            continue

        activity_id = activity.get("activityId")

        if activity_id is None:
            print(
                f"  ! Activity {index} has no activityId; skipping."
            )
            continue

        activity_id = str(activity_id)

        name = first_non_none(
            activity.get("activityName"),
            activity.get("name"),
            "",
        )

        activity_type = activity_type_name(activity)

        start_local = first_non_none(
            activity.get("startTimeLocal"),
            activity.get("startLocal"),
        )

        print(
            f"[{index}/{len(activities)}] "
            f"{start_local or '?'} | "
            f"{activity_type or '?'} | "
            f"{name or activity_id}"
        )

        # HR zones are a separate read-only endpoint.
        hr_zone_response = safe_call(
            f"HR zones for {activity_id}",
            garmin.get_activity_hr_in_timezones,
            activity_id,
        )

        zones = extract_hr_zones(hr_zone_response)

        row = {
            "activity_id": activity_id,
            "start_time_local": start_local,
            "start_time_gmt": first_non_none(
                activity.get("startTimeGMT"),
                activity.get("startTimeGmt"),
            ),
            "activity_name": name,
            "activity_type": activity_type,

            # Duration / distance
            "duration_minutes": seconds_to_minutes(
                activity.get("duration")
            ),
            "moving_duration_minutes": seconds_to_minutes(
                activity.get("movingDuration")
            ),
            "elapsed_duration_minutes": seconds_to_minutes(
                activity.get("elapsedDuration")
            ),
            "distance_km": meters_to_km(
                activity.get("distance")
            ),

            # Heart rate
            "average_hr_bpm": activity.get("averageHR"),
            "max_hr_bpm": activity.get("maxHR"),

            # Garmin training metrics
            "aerobic_training_effect":
                activity.get("aerobicTrainingEffect"),
            "anaerobic_training_effect":
                activity.get("anaerobicTrainingEffect"),
            "activity_training_load":
                activity.get("activityTrainingLoad"),
            "training_effect_label":
                activity.get("trainingEffectLabel"),

            # Energy
            "calories_kcal": activity.get("calories"),

            # HR-zone duration.
            # Garmin devices/accounts can use a varying number of zones;
            # five standard zones are sufficient for our current analysis.
            "hr_zone_1_seconds": zones.get(1),
            "hr_zone_2_seconds": zones.get(2),
            "hr_zone_3_seconds": zones.get(3),
            "hr_zone_4_seconds": zones.get(4),
            "hr_zone_5_seconds": zones.get(5),
        }

        rows.append(row)

    # -----------------------------------------------------------------------
    # Handle no-activity period
    # -----------------------------------------------------------------------

    if not rows:
        print()
        print("No Garmin activities found in this date range.")
        return

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

        # Re-fetched activities replace earlier versions with the same ID.
        for row in rows:
            existing[row["activity_id"]] = row

        combined = list(existing.values())

        write_csv(
            CUMULATIVE_FILE,
            combined,
        )

        output_file = CUMULATIVE_FILE

        print()
        print(f"Updated: {output_file}")
        print(
            f"Total activities in file: {len(combined)}"
        )

    else:
        output_file = (
            OUTPUT_DIR
            / (
                f"garmin_activities_"
                f"{start_str}_to_{end_str}.csv"
            )
        )

        write_csv(
            output_file,
            rows,
        )

        print()
        print(f"Created: {output_file}")

    print(
        f"Fetched {len(rows)} activities from Garmin."
    )

    print_data_quality(rows)


if __name__ == "__main__":
    main()
