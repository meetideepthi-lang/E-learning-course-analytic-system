from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import DateTime, Integer, String, URL, create_engine, func, make_url, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_name: Mapped[str] = mapped_column(String(120), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    registration_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    study_year: Mapped[int] = mapped_column(Integer, nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


def build_database_url(config: dict) -> URL:
    if config.get("DATABASE_URL"):
        return make_url(config["DATABASE_URL"])
    return URL.create(
        "mysql+mysqlconnector",
        username=config.get("DB_USER", "root"),
        password=config.get("DB_PASSWORD", ""),
        host=config.get("DB_HOST", "localhost"),
        port=int(config.get("DB_PORT", 3306)),
        database=config.get("DB_NAME", "course_analytics"),
    )


def is_unknown_database(error: Exception) -> bool:
    original = getattr(error, "orig", None)
    if original is None:
        return False
    error_number = getattr(original, "errno", None)
    if error_number is None and getattr(original, "args", ()):
        first_argument = original.args[0]
        error_number = first_argument if isinstance(first_argument, int) else None
    return (
        error_number == 1049
        or "unknown database" in str(original).lower()
        or "unknown database" in str(error).lower()
    )


def safe_database_error(error: Exception, config: dict) -> str:
    message = str(error)
    password = str(config.get("DB_PASSWORD", ""))
    if password:
        message = message.replace(password, "[hidden]")
    return f"{type(error).__name__}: {message}"


def initialize_database(config: dict):
    database_url = build_database_url(config)
    mysql = database_url.drivername.startswith("mysql")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connection_timeout": 4} if mysql else {},
    )
    try:
        Base.metadata.create_all(engine)
        return engine, None
    except Exception as error:
        if mysql and is_unknown_database(error):
            admin_engine = create_engine(
                database_url.set(database=""),
                pool_pre_ping=True,
                connect_args={"connection_timeout": 4},
            )
            try:
                quoted_name = admin_engine.dialect.identifier_preparer.quote(
                    config.get("DB_NAME", "course_analytics")
                )
                with admin_engine.begin() as connection:
                    connection.exec_driver_sql(
                        f"CREATE DATABASE IF NOT EXISTS {quoted_name} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
            except Exception as create_error:
                engine.dispose()
                return None, "Could not create the configured MySQL database: " + safe_database_error(
                    create_error, config
                )
            finally:
                admin_engine.dispose()
            try:
                Base.metadata.create_all(engine)
                return engine, None
            except Exception as retry_error:
                engine.dispose()
                return None, "Database created, but table initialization failed: " + safe_database_error(
                    retry_error, config
                )
        engine.dispose()
        return None, "Could not initialize the configured database: " + safe_database_error(
            error, config
        )


def validate_student(form) -> tuple[dict, dict]:
    values = {
        "student_name": form.get("student_name", "").strip(),
        "registration_number": form.get("registration_number", "").strip().upper(),
        "section": form.get("section", "").strip(),
        "department": form.get("department", "").strip(),
    }
    errors = {}
    for field, label in (
        ("student_name", "Student name"),
        ("registration_number", "Registration number"),
        ("section", "Section"),
        ("department", "Department"),
    ):
        if not values[field]:
            errors[field] = f"{label} is required."
    for field, label, lower, upper in (
        ("age", "Age", 1, 120),
        ("study_year", "Year of study", 1, 12),
    ):
        try:
            values[field] = int(form.get(field, ""))
            if not lower <= values[field] <= upper:
                errors[field] = f"{label} must be between {lower} and {upper}."
        except ValueError:
            values[field] = None
            errors[field] = f"Enter a whole number for {label.lower()}."
    return values, errors


def make_report_chart(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    figure, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    figure.patch.set_facecolor("#ffffff")
    for axis in axes:
        axis.set_facecolor("#ffffff")
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.spines["bottom"].set_color("#dce4df")
        axis.tick_params(axis="both", length=0, colors="#64736e")
        axis.grid(axis="y", color="#e9efeb", linewidth=.8)
        axis.set_axisbelow(True)
    departments = frame.groupby("department").size().sort_values(ascending=True)
    axes[0].barh(departments.index, departments.values, color="#26705c")
    axes[0].set_title("Students by department", loc="left", fontsize=11)
    axes[0].set_xlabel("Students")
    years = frame.groupby("study_year").size().sort_index()
    axes[1].bar(years.index.astype(str), years.values, color="#cf735d")
    axes[1].set_title("Students by year", loc="left", fontsize=11)
    axes[1].set_xlabel("Year of study")
    axes[2].hist(
        frame["age"],
        bins=min(8, max(3, frame["age"].nunique())),
        color="#315a8a",
        edgecolor="white",
    )
    axes[2].set_title("Age distribution", loc="left", fontsize=11)
    axes[2].set_xlabel("Age")
    axes[2].set_ylabel("Students")
    figure.tight_layout()
    image = BytesIO()
    figure.savefig(image, format="png", dpi=150, bbox_inches="tight")
    plt.close(figure)
    return base64.b64encode(image.getvalue()).decode("ascii")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        DB_HOST=os.environ.get("DB_HOST", "localhost"),
        DB_PORT=os.environ.get("DB_PORT", "3306"),
        DB_USER=os.environ.get("DB_USER", "root"),
        DB_PASSWORD=os.environ.get("DB_PASSWORD", ""),
        DB_NAME=os.environ.get("DB_NAME", "course_analytics"),
    )
    if test_config:
        app.config.update(test_config)
    engine, connection_error = initialize_database(app.config)
    app.extensions["student_engine"] = engine
    app.extensions["database_error"] = connection_error
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    def require_database():
        active_engine = app.extensions.get("student_engine")
        if active_engine is None:
            abort(503, description="MySQL is not connected. Check the connection status shown on the page.")
        return active_engine

    def get_csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    @app.context_processor
    def inject_connection_status():
        return {
            "database_error": app.extensions.get("database_error"),
            "database_ready": app.extensions.get("student_engine") is not None,
            "csrf_token": get_csrf_token,
        }

    @app.before_request
    def protect_post_requests():
        if request.method == "POST":
            submitted = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not secrets.compare_digest(submitted, expected):
                abort(400, description="The form expired. Refresh the page and try again.")

    @app.get("/")
    def index():
        students = []
        metrics = {"total": 0, "departments": 0, "average_age": None, "sections": 0}
        query = request.args.get("q", "").strip()
        active_engine = app.extensions.get("student_engine")
        if active_engine is not None:
            with Session(active_engine) as database:
                statement = select(Student).order_by(
                    Student.department, Student.study_year, Student.student_name
                )
                if query:
                    pattern = f"%{query}%"
                    statement = statement.where(
                        or_(
                            Student.student_name.ilike(pattern),
                            Student.registration_number.ilike(pattern),
                            Student.department.ilike(pattern),
                            Student.section.ilike(pattern),
                        )
                    )
                students = database.scalars(statement).all()
                metrics = {
                    "total": database.scalar(select(func.count(Student.student_id))) or 0,
                    "departments": database.scalar(
                        select(func.count(func.distinct(Student.department)))
                    ) or 0,
                    "average_age": database.scalar(select(func.avg(Student.age))),
                    "sections": database.scalar(
                        select(func.count(func.distinct(Student.section)))
                    ) or 0,
                }
        return render_template("index.html", students=students, metrics=metrics, query=query)

    @app.post("/students")
    def create_student():
        values, errors = validate_student(request.form)
        if errors:
            for message in errors.values():
                flash(message, "error")
            return redirect(url_for("index"))
        try:
            with Session(require_database()) as database, database.begin():
                database.add(Student(**values))
        except IntegrityError:
            flash("That registration number is already in use.", "error")
            return redirect(url_for("index"))
        flash("Student record added.", "success")
        return redirect(url_for("index"))

    @app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
    def edit_student(student_id: int):
        active_engine = require_database()
        with Session(active_engine) as database:
            student = database.get(Student, student_id)
            if student is None:
                abort(404)
            if request.method == "GET":
                return render_template("edit_student.html", student=student)
            values, errors = validate_student(request.form)
            if errors:
                for message in errors.values():
                    flash(message, "error")
                return render_template(
                    "edit_student.html", student=student, form_values=request.form
                ), 422
            for field, value in values.items():
                setattr(student, field, value)
            try:
                database.commit()
            except IntegrityError:
                database.rollback()
                flash("That registration number is already in use.", "error")
                return render_template(
                    "edit_student.html", student=student, form_values=request.form
                ), 422
        flash("Student record updated.", "success")
        return redirect(url_for("index"))

    @app.post("/students/<int:student_id>/delete")
    def delete_student(student_id: int):
        with Session(require_database()) as database, database.begin():
            student = database.get(Student, student_id)
            if student is None:
                abort(404)
            database.delete(student)
        flash("Student record deleted.", "success")
        return redirect(url_for("index"))

    @app.get("/report")
    def report():
        records = []
        active_engine = app.extensions.get("student_engine")
        if active_engine is not None:
            with Session(active_engine) as database:
                students = database.scalars(select(Student)).all()
                records = [
                    {
                        "age": student.age,
                        "section": student.section,
                        "study_year": student.study_year,
                        "department": student.department,
                    }
                    for student in students
                ]
        frame = pd.DataFrame(records)
        if frame.empty:
            department_summary = year_summary = section_summary = []
            average_age = median_age = None
            chart = None
        else:
            department_summary = (
                frame.groupby("department").size().rename("student_count").reset_index().to_dict("records")
            )
            year_summary = (
                frame.groupby("study_year").size().rename("student_count").reset_index().to_dict("records")
            )
            section_summary = (
                frame.groupby(["department", "section"])
                .size()
                .rename("student_count")
                .reset_index()
                .to_dict("records")
            )
            ages = frame["age"].to_numpy(dtype=float)
            average_age = float(np.mean(ages))
            median_age = float(np.median(ages))
            chart = make_report_chart(frame)
        return render_template(
            "report.html",
            total=len(frame),
            department_count=frame["department"].nunique() if not frame.empty else 0,
            section_count=frame["section"].nunique() if not frame.empty else 0,
            average_age=average_age,
            median_age=median_age,
            department_summary=department_summary,
            year_summary=year_summary,
            section_summary=section_summary,
            chart=chart,
            generated_at=datetime.now().strftime("%d %b %Y, %H:%M"),
        )

    return app