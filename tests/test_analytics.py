import unittest
from datetime import date

import pandas as pd

from analytics import course_completion_summary, inactive_enrollments, weekly_activity_summary


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.courses = pd.DataFrame(
            [
                {"course_id": 1, "course_name": "Python", "category": "Tech"},
                {"course_id": 2, "course_name": "Design", "category": "Arts"},
            ]
        )
        self.enrollments = pd.DataFrame(
            [
                {
                    "enrollment_id": 10,
                    "learner_id": 1,
                    "roll_no": "R1",
                    "course_id": 1,
                    "course_name": "Python",
                    "enrolled_at": "2026-08-01 10:00:00",
                    "status": "completed",
                },
                {
                    "enrollment_id": 11,
                    "learner_id": 2,
                    "roll_no": None,
                    "course_id": 1,
                    "course_name": "Python",
                    "enrolled_at": "2026-08-01 10:00:00",
                    "status": "active",
                },
                {
                    "enrollment_id": 12,
                    "learner_id": 3,
                    "roll_no": "R3",
                    "course_id": 2,
                    "course_name": "Design",
                    "enrolled_at": "2026-08-01 10:00:00",
                    "status": "withdrawn",
                },
            ]
        )
        self.activities = pd.DataFrame(
            [
                {
                    "activity_id": 100,
                    "enrollment_id": 10,
                    "activity_date": "2026-10-20 12:00:00",
                    "activity_type": "lesson",
                    "completed": True,
                },
                {
                    "activity_id": 101,
                    "enrollment_id": 11,
                    "activity_date": "2026-09-20 12:00:00",
                    "activity_type": "quiz",
                    "completed": False,
                },
                {
                    "activity_id": 102,
                    "enrollment_id": 11,
                    "activity_date": "2026-10-27 12:00:00",
                    "activity_type": "lesson",
                    "completed": True,
                },
            ]
        )

    def test_completion_denominator_excludes_withdrawn_and_keeps_empty_course(self):
        summary = course_completion_summary(self.courses, self.enrollments)
        python = summary.set_index("course_id").loc[1]
        design = summary.set_index("course_id").loc[2]

        self.assertEqual(python["enrollment_count"], 2)
        self.assertEqual(python["completed_count"], 1)
        self.assertEqual(python["completion_rate"], 0.5)
        self.assertEqual(design["enrollment_count"], 0)
        self.assertEqual(design["completion_rate"], 0.0)

    def test_inactivity_rule_requires_age_and_uses_recorded_activity(self):
        results = inactive_enrollments(
            self.enrollments, self.activities, date(2026, 10, 26), inactive_days=30
        )

        self.assertEqual(results["enrollment_id"].tolist(), [11])

    def test_weekly_activity_uses_monday_week_and_excludes_future_records(self):
        weekly = weekly_activity_summary(
            self.enrollments, self.activities, date(2026, 10, 26)
        )

        self.assertEqual(weekly["activity_count"].sum(), 2)
        self.assertEqual(weekly["completed_activity_count"].sum(), 1)
        self.assertEqual(weekly["activity_week"].min(), date(2026, 9, 14))


if __name__ == "__main__":
    unittest.main()