"""
app.py
------
Cleaned and deduplicated Flask application ready for deployment and rendering.
"""

import os
from datetime import timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)

import models
from models import (
    LibraryError, ValidationError, DuplicateError, NotFoundError,
    AuthError, PermissionError_, find_book, find_user_by_id,
    search_books, authenticate, register_user, add_book, update_book,
    delete_book, create_request, set_request_status, seed_data,
    open_session, validate_session, close_session,
)

# ---- Template & Static Folders ----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.environ.get("SECRET_KEY", "library-demo-secret-key-change-me")

# ---- Session Hardening ----
app.permanent_session_lifetime = timedelta(minutes=20)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_REFRESH_EACH_REQUEST=True,
)

seed_data()


# ============================================================
# DECORATORS
# ============================================================
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        if not validate_session(session.get("user_id"), session.get("token")):
            session.clear()
            flash("Your session ended (last active session was replaced). Please log in again.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        @login_required  # Reuses login_required to eliminate duplicated session validation code
        def wrapper(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                flash("Unauthorized access: your role cannot perform that action.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    if "user_id" not in session:
        return None
    if not validate_session(session.get("user_id"), session.get("token")):
        return None
    return find_user_by_id(session["user_id"])


@app.context_processor
def inject_user():
    return {"user": current_user()}


# ============================================================
# AUTH ROUTES
# ============================================================
@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = authenticate(username, password)
            session.clear()
            session.permanent = True
            session["user_id"] = user.user_id
            session["role"] = user.role
            session["username"] = user.username
            session["token"] = open_session(user.user_id)

            flash(f"Welcome back, {user.full_name}!", "success")
            return redirect(url_for("dashboard"))
        except AuthError as e:
            flash(str(e), "error")
        except LibraryError as e:
            flash(f"Unexpected problem: {e}", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "student")
        try:
            register_user(username, password, confirm, full_name, role)
            flash("Account created successfully. You can now log in.", "success")
            return redirect(url_for("login"))
        except (DuplicateError, ValidationError) as e:
            flash(str(e), "error")

    return render_template("signup.html", roles=list(models.ROLE_MAP.keys()))


@app.route("/logout")
def logout():
    username = session.get("username", "user")
    uid = session.get("user_id")
    if uid:
        close_session(uid)
    session.clear()
    flash(f"Goodbye, {username}. You have been logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    title = user.dashboard_title()
    perms = sorted(user.permissions())

    my_requests = []
    all_requests = []
    if user.can_do("view_own_requests"):
        my_requests = [r for r in models.borrow_requests if r["user_id"] == user.user_id]
    if user.can_do("view_requests"):
        all_requests = list(models.borrow_requests)

    return render_template(
        "dashboard.html", title=title, perms=perms,
        total_books=len(models.books), total_users=len(models.users),
        total_requests=len(models.borrow_requests),
        my_requests=my_requests, all_requests=all_requests,
        logs=models.activity_log[-8:] if user.can_do("view_logs") else [],
    )


# ============================================================
# CRUD
# ============================================================
@app.route("/books/add", methods=["GET", "POST"])
@role_required("admin", "staff")
def add_record():
    if request.method == "POST":
        try:
            add_book(
                request.form.get("title", "").strip(),
                request.form.get("author", "").strip(),
                request.form.get("genre", "").strip(),
                request.form.get("copies", ""),
                request.form.get("item_type", "Book"),
            )
            flash("Book added successfully.", "success")
            return redirect(url_for("view_records"))
        except (DuplicateError, ValidationError) as e:
            flash(str(e), "error")
        except LibraryError as e:
            flash(f"Could not add record: {e}", "error")
    return render_template("add_record.html")


@app.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
@role_required("admin", "staff")
def edit_record(book_id):
    book = find_book(book_id)
    if book is None:
        flash("Missing record: that book does not exist.", "error")
        return redirect(url_for("view_records"))

    if request.method == "POST":
        try:
            update_book(
                book_id,
                request.form.get("title", "").strip(),
                request.form.get("author", "").strip(),
                request.form.get("genre", "").strip(),
                request.form.get("copies", ""),
            )
            flash("Book updated successfully.", "success")
            return redirect(url_for("view_records"))
        except (ValidationError, NotFoundError) as e:
            flash(str(e), "error")

    return render_template("edit_record.html", book=book)


@app.route("/books/delete/<int:book_id>", methods=["POST"])
@role_required("admin")
def delete_record(book_id):
    try:
        book = delete_book(book_id)
        flash(f"Deleted '{book.title}'.", "success")
    except NotFoundError as e:
        flash(str(e), "error")
    return redirect(url_for("view_records"))


# ============================================================
# SEARCH
# ============================================================
@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    user = current_user()
    keyword = (
        request.form.get("keyword", "").strip()
        if request.method == "POST"
        else request.args.get("keyword", "").strip()
    )

    if not keyword:
        recommendations = sorted(models.books, key=lambda b: (not b.is_available(), b.title.lower()))
        return render_template("search.html", keyword="", results=recommendations,
                               is_recommendation=True, can_request=user.can_do("make_request"))

    results = search_books(keyword)
    if not results:
        flash(f"No records matched '{keyword}'. Here are books we do have:", "error")
        recommendations = sorted(models.books, key=lambda b: (not b.is_available(), b.title.lower()))
        return render_template("search.html", keyword="", results=recommendations,
                               is_recommendation=True, can_request=user.can_do("make_request"))

    return render_template("search.html", keyword=keyword, results=results,
                           is_recommendation=False, can_request=user.can_do("make_request"))


# ============================================================
# REQUESTS & BOOKS
# ============================================================
@app.route("/requests", methods=["GET", "POST"])
@login_required
def requests_page():
    user = current_user()
    if not user.can_do("view_own_requests") and not user.can_do("view_requests"):
        flash("Unauthorized access.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            try:
                if not user.can_do("make_request"):
                    raise PermissionError_("Only students can send borrow requests.")
                raw_id = (request.form.get("book_id") or "").strip()
                if not raw_id.isdigit():
                    raise ValidationError("Invalid book selected.")
                create_request(user, int(raw_id))
                flash("Borrow request submitted.", "success")
            except LibraryError as e:
                flash(str(e), "error")
            return redirect(url_for("requests_page"))

        if action in ("approve", "reject"):
            try:
                if not user.can_do("approve_requests"):
                    raise PermissionError_("You are not allowed to manage requests.")
                raw_id = (request.form.get("request_id") or "").strip()
                if not raw_id.isdigit():
                    raise ValidationError("Invalid request selected.")
                set_request_status(int(raw_id), "approved" if action == "approve" else "rejected")
                flash(f"Request {action}d.", "success")
            except LibraryError as e:
                flash(str(e), "error")
            return redirect(url_for("requests_page"))

        flash("Invalid operation.", "error")
        return redirect(url_for("requests_page"))

    rows = (
        list(models.borrow_requests)
        if user.can_do("view_requests")
        else [r for r in models.borrow_requests if r["user_id"] == user.user_id]
    )
    available_books = [b for b in models.books if b.is_available()]

    return render_template(
        "requests.html",
        rows=rows,
        can_create=user.can_do("make_request"),
        can_manage=user.can_do("approve_requests"),
        available_books=available_books,
        books=models.books,
        keyword="",
        users_needed=False,
        users=[],
        can_edit=False,
        can_delete=False,
    )


@app.route("/books")
@login_required
def view_records():
    user = current_user()
    if not user.can_do("view_books"):
        flash("Unauthorized access.", "error")
        return redirect(url_for("dashboard"))
    keyword = request.args.get("q", "")
    results = search_books(keyword)
    return render_template(
        "view_records.html",
        books=results,
        keyword=keyword,
        can_edit=user.can_do("edit_book"),
        can_delete=user.can_do("delete_book"),
        users_needed=False,
        users=[],
    )


@app.route("/users")
@role_required("admin")
def manage_users():
    return render_template("view_records.html", books=[], keyword="",
                           users_needed=True,
                           users=[u.to_dict() for u in models.users],
                           can_edit=False, can_delete=False)


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong on our side."), 500


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)