import re
import unittest

from webapp import create_app


class StudentAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {"DATABASE_URL": "sqlite://", "TESTING": True, "SECRET_KEY": "test-secret"}
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["student_engine"].dispose()

    def csrf_token(self):
        response = self.client.get("/")
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def student_form(self, token, **overrides):
        values = {
            "csrf_token": token,
            "student_name": "Asha Kumar",
            "age": "20",
            "registration_number": "REG-1001",
            "section": "A",
            "study_year": "2",
            "department": "Computer Science",
        }
        values.update(overrides)
        return values

    def test_create_and_report_uses_saved_records(self):
        response = self.client.post(
            "/students", data=self.student_form(self.csrf_token()), follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Asha Kumar", response.data)
        report = self.client.get("/report")
        self.assertEqual(report.status_code, 200)
        self.assertIn(b"Student composition", report.data)
        self.assertIn(b"Computer Science", report.data)
        self.assertIn(b"AGGREGATE DISTRIBUTIONS", report.data)

    def test_edit_and_delete_student_record(self):
        self.client.post("/students", data=self.student_form(self.csrf_token()))
        directory = self.client.get("/").get_data(as_text=True)
        student_id = re.search(r"/students/(\d+)/edit", directory).group(1)
        updated = self.student_form(self.csrf_token(), student_name="Asha Rao", age="21")
        response = self.client.post(
            f"/students/{student_id}/edit", data=updated, follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Asha Rao", response.data)
        response = self.client.post(
            f"/students/{student_id}/delete",
            data={"csrf_token": self.csrf_token()},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No student records yet", response.data)

    def test_duplicate_registration_number_is_rejected(self):
        self.client.post("/students", data=self.student_form(self.csrf_token()))
        response = self.client.post(
            "/students",
            data=self.student_form(self.csrf_token(), student_name="Different Student"),
            follow_redirects=True,
        )
        self.assertIn(b"already in use", response.data)

    def test_invalid_age_is_not_saved(self):
        response = self.client.post(
            "/students", data=self.student_form(self.csrf_token(), age="0"), follow_redirects=True
        )
        self.assertIn(b"Age must be between 1 and 120", response.data)
        self.assertIn(b"No student records yet", response.data)


if __name__ == "__main__":
    unittest.main()