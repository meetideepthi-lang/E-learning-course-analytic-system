from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import URL, create_engine, text


def course_completion_summary(
    courses: pd.DataFrame, enrollments: pd.DataFrame
) -> pd.DataFrame:
    """Summarize status-based completion, excluding withdrawn enrollments."""
    columns = [
        "course_id",
        "course_name",
        "category",
        "enrollment_count",
        "completed_count",
        "completion_rate",
    ]
    summary = courses[["course_id", "course_name", "category"]].copy()
    eligible = enrollments.loc[
        enrollments["status"].fillna("").str.lower().ne("withdrawn")
    ].copy()
    eligible["is_completed"] = eligible["status"].fillna("").str.lower().eq("completed")

    counts = eligible.groupby("course_id", as_index=False).agg(
        enrollment_count=("enrollment_id", "nunique"),
        completed_count=("is_completed", "sum"),
    )
    summary = summary.merge(counts, on="course_id", how="left")
    summary[["enrollment_count", "completed_count"]] = summary[
        ["enrollment_count", "completed_count"]
    ].fillna(0).astype(int)
    denominator = summary["enrollment_count"].to_numpy(dtype=float)
    numerator = summary["completed_count"].to_numpy(dtype=float)
    summary["completion_rate"] = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator),
        where=denominator != 0,
    )
    return summary[columns].sort_values("course_name").reset_index(drop=True)


def weekly_activity_summary(
    enrollments: pd.DataFrame, activities: pd.DataFrame, as_of: date
) -> pd.DataFrame:
    columns = [
        "activity_week",
        "course_name",
        "activity_count",
        "completed_activity_count",
        "enrollments_with_activity",
    ]
    if activities.empty or enrollments.empty:
        return pd.DataFrame(columns=columns)

    records = activities.merge(
        enrollments[["enrollment_id", "course_id", "course_name"]],
        on="enrollment_id",
        how="inner",
    ).copy()
    records["activity_date"] = pd.to_datetime(records["activity_date"])
    end_exclusive = pd.Timestamp(as_of + timedelta(days=1))
    records = records.loc[records["activity_date"].lt(end_exclusive)]
    if records.empty:
        return pd.DataFrame(columns=columns)

    records["activity_week"] = (
        records["activity_date"].dt.to_period("W-SUN").dt.start_time.dt.date
    )
    records["completed"] = records["completed"].fillna(False).astype(bool)
    weekly = records.groupby(
        ["activity_week", "course_name"], as_index=False
    ).agg(
        activity_count=("activity_id", "count"),
        completed_activity_count=("completed", "sum"),
        enrollments_with_activity=("enrollment_id", "nunique"),
    )
    return weekly[columns].sort_values(["activity_week", "course_name"]).reset_index(
        drop=True
    )


def inactive_enrollments(
    enrollments: pd.DataFrame,
    activities: pd.DataFrame,
    as_of: date,
    inactive_days: int = 30,
) -> pd.DataFrame:
    """Find mature active enrollments without recorded activity in the window."""
    columns = [
        "enrollment_id",
        "learner_id",
        "roll_no",
        "course_id",
        "course_name",
        "enrolled_at",
        "last_activity_at",
        "days_since_activity",
    ]
    cutoff_date = as_of - timedelta(days=inactive_days)
    window_start = pd.Timestamp(cutoff_date + timedelta(days=1))
    candidates = enrollments.loc[
        enrollments["status"].fillna("").str.lower().eq("active")
    ].copy()
    candidates["enrolled_at"] = pd.to_datetime(candidates["enrolled_at"])
    candidates = candidates.loc[candidates["enrolled_at"].dt.date.le(cutoff_date)]

    if activities.empty:
        candidates["last_activity_at"] = pd.NaT
    else:
        activity_rows = activities.copy()
        activity_rows["activity_date"] = pd.to_datetime(activity_rows["activity_date"])
        end_exclusive = pd.Timestamp(as_of + timedelta(days=1))
        activity_rows = activity_rows.loc[
            activity_rows["activity_date"].lt(end_exclusive)
        ]
        latest = activity_rows.groupby("enrollment_id")["activity_date"].max()
        candidates["last_activity_at"] = candidates["enrollment_id"].map(latest)

    no_recent_record = candidates["last_activity_at"].isna() | candidates[
        "last_activity_at"
    ].lt(window_start)
    inactive = candidates.loc[no_recent_record].copy()
    inactive["days_since_activity"] = (
        pd.Timestamp(as_of) - pd.to_datetime(inactive["last_activity_at"]).dt.normalize()
    ).dt.days
    for column in ("learner_id", "roll_no"):
        if column not in inactive:
            inactive[column] = pd.NA
    return inactive[columns].sort_values(
        ["course_name", "enrollment_id"]
    ).reset_index(drop=True)


def load_data(
    *,
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    port: int | None = None,
    database: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    password = password if password is not None else os.environ.get("DB_PASSWORD")
    if password is None:
        raise RuntimeError("Set DB_PASSWORD in the environment before running analytics.")

    database_url = URL.create(
        "mysql+mysqlconnector",
        username=user or os.environ.get("DB_USER", "root"),
        password=password,
        host=host or os.environ.get("DB_HOST", "localhost"),
        port=port or int(os.environ.get("DB_PORT", "3306")),
        database=database or os.environ.get("DB_NAME", "course_analytics"),
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            courses = pd.read_sql_query(
                text("SELECT course_id, course_name, category FROM courses"), connection
            )
            enrollments = pd.read_sql_query(
                text(
                    "SELECT e.enrollment_id, e.learner_id, l.roll_no, e.course_id, "
                    "c.course_name, e.enrolled_at, e.status "
                    "FROM enrollments e "
                    "JOIN learners l ON l.learner_id = e.learner_id "
                    "JOIN courses c ON c.course_id = e.course_id"
                ),
                connection,
            )
            activities = pd.read_sql_query(
                text(
                    "SELECT activity_id, enrollment_id, activity_date, "
                    "activity_type, completed FROM activities"
                ),
                connection,
            )
    finally:
        engine.dispose()
    return courses, enrollments, activities


def write_course_chart(summary: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 5.5))
    if summary.empty:
        axis.text(0.5, 0.5, "No course records", ha="center", va="center")
        axis.set_axis_off()
    else:
        positions = np.arange(len(summary))
        width = 0.36
        axis.bar(positions - width / 2, summary["enrollment_count"], width, label="Enrolled")
        axis.bar(positions + width / 2, summary["completed_count"], width, label="Completed")
        axis.set_ylabel("Enrollments")
        axis.set_xticks(positions, summary["course_name"], rotation=25, ha="right")
        rate_axis = axis.twinx()
        rate_axis.plot(
            positions,
            summary["completion_rate"] * 100,
            color="black",
            marker="o",
            label="Completion rate",
        )
        rate_axis.set_ylabel("Completion rate (%)")
        rate_axis.set_ylim(0, 100)
        handles, labels = axis.get_legend_handles_labels()
        rate_handles, rate_labels = rate_axis.get_legend_handles_labels()
        axis.legend(handles + rate_handles, labels + rate_labels, loc="upper left")
    axis.set_title("Enrollments and completion by course")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def write_activity_chart(weekly: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 5.5))
    if weekly.empty:
        axis.text(0.5, 0.5, "No recorded activity", ha="center", va="center")
        axis.set_axis_off()
    else:
        totals = weekly.groupby("activity_week", as_index=False).agg(
            activity_count=("activity_count", "sum"),
            completed_activity_count=("completed_activity_count", "sum"),
        )
        axis.plot(totals["activity_week"], totals["activity_count"], marker="o", label="Recorded")
        axis.plot(
            totals["activity_week"],
            totals["completed_activity_count"],
            marker="o",
            label="Marked completed",
        )
        axis.set_ylabel("Activity records")
        axis.tick_params(axis="x", rotation=30)
        axis.legend()
    axis.set_title("Recorded activity by week")
    axis.set_xlabel("Week starting (Monday)")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def write_report(
    output_dir: Path,
    summary: pd.DataFrame,
    weekly: pd.DataFrame,
    inactive: pd.DataFrame,
    as_of: date,
    inactive_days: int,
) -> None:
    total_enrollments = int(summary["enrollment_count"].sum()) if not summary.empty else 0
    total_completions = int(summary["completed_count"].sum()) if not summary.empty else 0
    overall_rate = total_completions / total_enrollments if total_enrollments else 0.0
    report = [
        "# Course learning analytics",
        "",
        f"Report date: {as_of.isoformat()}",
        "",
        "## Course completion",
        "Completion rate = enrollments with status `completed` / all enrollments "
        "with status `active` or `completed`. Withdrawn enrollments are excluded. "
        "The denominator is enrollment records, not learners or lesson counts.",
        "",
        f"Overall: {total_completions} completed of {total_enrollments} eligible "
        f"enrollments ({overall_rate:.1%}).",
        "",
        "## Activity and inactivity",
        f"Weekly activity counts recorded activity rows; completed activity counts "
        f"rows marked completed. The inactivity report flags active enrollments "
        f"enrolled by the cutoff date with no recorded activity during the last "
        f"{inactive_days} calendar days, including the report date.",
        "A missing or absent activity record is not evidence that a learner did "
        "not learn. These are engagement-data signals only, not measures of "
        "ability or learning outcomes.",
        "",
        f"Inactive-by-rule enrollments: {len(inactive)}.",
        "",
        "## Generated files",
        "- `course_completion.csv`",
        "- `weekly_activity.csv`",
        "- `inactive_enrollments.csv`",
        "- `course_comparison.png`",
        "- `weekly_activity.png`",
    ]
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate aggregate course engagement reports.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--inactive-days", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    if args.inactive_days < 1:
        parser.error("--inactive-days must be at least 1")

    courses, enrollments, activities = load_data()
    summary = course_completion_summary(courses, enrollments)
    weekly = weekly_activity_summary(enrollments, activities, args.as_of)
    inactive = inactive_enrollments(
        enrollments, activities, args.as_of, args.inactive_days
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_dir / "course_completion.csv", index=False)
    weekly.to_csv(args.output_dir / "weekly_activity.csv", index=False)
    inactive.to_csv(args.output_dir / "inactive_enrollments.csv", index=False)
    write_course_chart(summary, args.output_dir / "course_comparison.png")
    write_activity_chart(weekly, args.output_dir / "weekly_activity.png")
    write_report(args.output_dir, summary, weekly, inactive, args.as_of, args.inactive_days)
    print(f"Analytics reports written to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()