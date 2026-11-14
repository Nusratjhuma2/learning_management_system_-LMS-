# Learning Management System (LMS) - Django

A clean, modular Django Learning Management System with user roles, courses, lessons, quizzes, and student enrollments.

---

## 📁 Project Structure

```text
Practicum software/
│
├── accounts/               # Custom user model with roles (Student, Instructor, Admin)
│   ├── models.py           # User model (role, bio, profile_picture)
│   ├── forms.py            # SignUpForm, ProfileUpdateForm
│   ├── views.py            # Signup, Profile, Login/Logout handlers
│   ├── urls.py             # /accounts/*
│   └── admin.py            # Custom UserAdmin
│
├── courses/                # Course creation and catalog
│   ├── models.py           # Category, Course (with status: Draft, Published, Archived)
│   ├── forms.py            # CourseForm
│   ├── views.py            # List, detail, create, update, delete
│   ├── urls.py             # /courses/*
│   └── admin.py            # CategoryAdmin, CourseAdmin
│
├── lessons/                # Lessons attached to courses
│   ├── models.py           # Lesson (Text, Video, File download)
│   ├── forms.py            # LessonForm
│   ├── views.py            # Lesson detail, add, edit, delete
│   ├── urls.py             # /courses/<slug>/lessons/*
│   └── admin.py            # LessonAdmin
│
├── quizzes/                # Quizzes and assessments
│   ├── models.py           # Quiz, Question, Choice, QuizAttempt
│   ├── views.py            # Quiz view and automatic grading submit
│   ├── urls.py             # /quizzes/*
│   └── admin.py            # Inline question & choice admin
│
├── enrollments/            # Student course enrollments
│   ├── models.py           # Enrollment model
│   ├── views.py            # Enroll, unenroll, and my_courses dashboard
│   ├── urls.py             # /enrollments/*
│   └── admin.py            # EnrollmentAdmin
│
├── lms_project/            # Project root settings and configuration
│   ├── settings.py         # App configs, custom user model, static & media roots
│   ├── urls.py             # Main router
│   ├── wsgi.py
│   └── asgi.py
│
├── templates/              # HTML templates (Bootstrap 5)
│   ├── base.html           # Base layout with navbar and alerts
│   ├── accounts/           # signup.html, login.html, profile.html
│   ├── courses/            # course_list.html, course_detail.html, course_form.html, etc.
│   ├── lessons/            # lesson_detail.html, lesson_form.html, etc.
│   ├── quizzes/            # quiz_detail.html, quiz_result.html
│   └── enrollments/        # my_courses.html
│
├── static/                 # Static assets (CSS, JS)
│   └── css/style.css
├── media/                  # Uploaded files (profile pictures, thumbnails, lesson files)
├── manage.py
├── requirements.txt
└── db.sqlite3              # Initialized SQLite database
```

---

## ⚙️ Database Configuration (PostgreSQL & SQLite)

The project is now configured to use **PostgreSQL** by default via `psycopg` (v3) and `django-environ`.

### Switching Databases via `.env`
Edit your [`.env`](file:///e:/Practicum%20software/.env) file:

```env
# Set to False to use PostgreSQL, or True for SQLite
USE_SQLITE=False

# PostgreSQL Connection Settings
DB_NAME=lms_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432

# Or provide a single cloud database URL (e.g. Neon, Supabase, Railway):
# DATABASE_URL=postgresql://user:password@ep-xyz.neon.tech/lms_db
```

### Initializing PostgreSQL:
1. Ensure your PostgreSQL server is running and create the database:
   ```sql
   CREATE DATABASE lms_db;
   ```
2. Run migrations:
   ```powershell
   python manage.py migrate
   ```
3. Load previously exported data (optional, restores users and records from SQLite):
   ```powershell
   python manage.py loaddata data_dump.json
   ```

---

## 🚀 Getting Started

### 1. Activate Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Create an Admin / Instructor Account
```powershell
python manage.py createsuperuser
```
*(When asked, enter username, email, and password. In Django Admin, you can assign roles `student`, `instructor`, or `admin`)*.

### 3. Run the Development Server
```powershell
python manage.py runserver
```

Open your browser at **`http://127.0.0.1:8000/`**.

---

## 🔑 Key Features

- **Role-based system**: Built-in `Student` and `Instructor` capabilities. Instructors can create courses and lessons; students can browse and enroll.
- **Course & Lesson Management**: Rich courses with categories, drafts/published statuses, and multi-format lessons (text, video, downloadable files).
- **Interactive Quizzes**: Multiple choice question sets with instant score calculation, percentage display, and pass/fail thresholds.
- **Enrollment Tracking**: Students can enroll with one click and monitor enrolled courses via "My Courses".
- **Responsive UI**: Pre-styled with Bootstrap 5 and custom styles.

