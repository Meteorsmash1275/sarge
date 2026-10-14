"""
models.py
---------
OOP core: Encapsulation, Inheritance, Polymorphism, Functions, Lists.
No database. Lists only.
"""


# ============================================================
# EXCEPTION HANDLING
# ============================================================
class LibraryError(Exception):
    pass


class ValidationError(LibraryError):
    pass


class DuplicateError(LibraryError):
    pass


class NotFoundError(LibraryError):
    pass


class AuthError(LibraryError):
    pass


class PermissionError_(LibraryError):
    pass


# ============================================================
# IN-MEMORY STORAGE — PYTHON LISTS ONLY
# ============================================================
users = []
books = []
borrow_requests = []
activity_log = []

# live session registry: one active token per user_id.
# { user_id: token_string }   -> logging in elsewhere replaces the token
live_sessions = {}

_next_user_id = [1]
_next_book_id = [1]
_next_request_id = [1]


# ============================================================
# BASE CLASS
# ============================================================
class User:
    ROLE = "user"

    def __init__(self, user_id, username, password, full_name, role=None):
        self.__user_id = user_id
        self.__username = username
        self.__password = password
        self.__full_name = full_name
        self._role = role or self.ROLE

    @property
    def user_id(self):
        return self.__user_id

    @property
    def username(self):
        return self.__username

    @property
    def full_name(self):
        return self.__full_name

    @property
    def role(self):
        return self._role

    def set_full_name(self, new_name):
        if not new_name or not new_name.strip():
            raise ValidationError("Full name cannot be empty.")
        self.__full_name = new_name.strip()

    def set_password(self, new_password):
        if len(new_password) < 4:
            raise ValidationError("Password must be at least 4 characters.")
        self.__password = new_password

    def check_password(self, attempt):
        return self.__password == attempt

    # ---------- POLYMORPHISM ----------
    def dashboard_title(self):
        return "Dashboard"

    def permissions(self):
        return set()

    def can_do(self, operation):
        return operation in self.permissions()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
        }

    def __str__(self):
        return f"{self.role.title()}: {self.full_name} (@{self.username})"


class Administrator(User):
    ROLE = "admin"

    def dashboard_title(self):
        return "Administrator Dashboard"

    def permissions(self):
        return {
            "view_books", "search_books",
            "add_book", "edit_book", "delete_book",
            "manage_users", "view_requests", "approve_requests",
            "view_logs",
        }


class Staff(User):
    ROLE = "staff"

    def dashboard_title(self):
        return "Staff Dashboard"

    def permissions(self):
        return {
            "view_books", "search_books",
            "add_book", "edit_book",
            "view_requests", "approve_requests",
        }


class Student(User):
    ROLE = "student"

    def dashboard_title(self):
        return "Student Dashboard"

    def permissions(self):
        return {
            "view_books", "search_books",
            "make_request", "view_own_requests",
        }


ROLE_MAP = {"admin": Administrator, "staff": Staff, "student": Student}


# ============================================================
# LIBRARY ITEMS
# ============================================================
class LibraryItem:
    def __init__(self, book_id, title, author, genre, copies=1):
        self.__book_id = book_id
        self.__title = title
        self.__author = author
        self.__genre = genre
        self.__copies = int(copies)

    @property
    def book_id(self):
        return self.__book_id

    @property
    def title(self):
        return self.__title

    @property
    def author(self):
        return self.__author

    @property
    def genre(self):
        return self.__genre

    @property
    def copies(self):
        return self.__copies

    def set_title(self, value):
        if not value or not value.strip():
            raise ValidationError("Title cannot be empty.")
        self.__title = value.strip()

    def set_author(self, value):
        if not value or not value.strip():
            raise ValidationError("Author cannot be empty.")
        self.__author = value.strip()

    def set_genre(self, value):
        if not value or not value.strip():
            raise ValidationError("Genre cannot be empty.")
        self.__genre = value.strip()

    def set_copies(self, value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Copies must be a whole number.")
        if number < 0:
            raise ValidationError("Copies cannot be negative.")
        self.__copies = number

    def item_type(self):
        return "Book"

    def is_available(self):
        return self.__copies > 0

    def to_dict(self):
        return {
            "book_id": self.book_id, "title": self.title,
            "author": self.author, "genre": self.genre,
            "copies": self.copies, "type": self.item_type(),
            "available": self.is_available(),
        }


class EBook(LibraryItem):
    def item_type(self):
        return "E-Book"

    def is_available(self):
        return True


# ============================================================
# MODULE-LEVEL FUNCTIONS
# ============================================================
def _log(message):
    activity_log.append(message)
    if len(activity_log) > 200:
        activity_log.pop(0)


def find_user(username):
    for user in users:
        if user.username.lower() == username.lower():
            return user
    return None


def find_user_by_id(user_id):
    for user in users:
        if user.user_id == user_id:
            return user
    return None


def find_book(book_id):
    for book in books:
        if book.book_id == book_id:
            return book
    return None


def search_books(keyword):
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return list(books)
    return [
        b for b in books
        if keyword in b.title.lower()
        or keyword in b.author.lower()
        or keyword in b.genre.lower()
    ]


def register_user(username, password, confirm, full_name, role):
    if not username or not password or not full_name:
        raise ValidationError("All fields are required.")
    if len(username.strip()) < 3:
        raise ValidationError("Username must be at least 3 characters.")
    if password != confirm:
        raise ValidationError("Passwords do not match.")
    if len(password) < 4:
        raise ValidationError("Password must be at least 4 characters.")
    if role not in ROLE_MAP:
        raise ValidationError("Invalid role selected.")
    if find_user(username):
        raise DuplicateError(f"Username '{username}' is already taken.")

    cls = ROLE_MAP[role]
    user = cls(_next_user_id[0], username.strip(), password, full_name.strip())
    _next_user_id[0] += 1
    users.append(user)
    _log(f"New account created: {user.username} ({user.role})")
    return user


def authenticate(username, password):
    if not username or not password:
        raise AuthError("Username and password are required.")
    user = find_user(username)
    if user is None or not user.check_password(password):
        raise AuthError("Incorrect username or password.")
    _log(f"Login: {user.username} ({user.role})")
    return user


# ---------- SESSION TOKEN REGISTRY (fixes multi-browser auto login) ----------
def open_session(user_id):
    """Issue a fresh token. Any previous token for this user dies instantly."""
    import secrets
    token = secrets.token_urlsafe(32)
    live_sessions[user_id] = token
    return token


def validate_session(user_id, token):
    """True only if this token is the CURRENT one on the server."""
    if user_id is None or not token:
        return False
    return live_sessions.get(user_id) == token


def close_session(user_id):
    live_sessions.pop(user_id, None)


# ---------- CRUD ----------
def add_book(title, author, genre, copies, item_type="Book"):
    if not title or not author or not genre or copies in ("", None):
        raise ValidationError("All book fields are required.")
    if any(b.title.lower() == title.strip().lower()
           and b.author.lower() == author.strip().lower() for b in books):
        raise DuplicateError(f"'{title}' by {author} already exists.")

    cls = EBook if item_type == "ebook" else LibraryItem
    book = cls(_next_book_id[0], title, author, genre, copies)
    _next_book_id[0] += 1
    books.append(book)
    _log(f"Book added: {book.title}")
    return book


def update_book(book_id, title, author, genre, copies):
    book = find_book(book_id)
    if book is None:
        raise NotFoundError(f"No book found with ID {book_id}.")
    book.set_title(title)
    book.set_author(author)
    book.set_genre(genre)
    book.set_copies(copies)
    _log(f"Book updated: {book.title}")
    return book


def delete_book(book_id):
    book = find_book(book_id)
    if book is None:
        raise NotFoundError(f"No book found with ID {book_id}.")
    books.remove(book)
    _log(f"Book deleted: {book.title}")
    return book


def create_request(user, book_id):
    book = find_book(book_id)
    if book is None:
        raise NotFoundError("That book does not exist.")
    if not book.is_available():
        raise ValidationError("No copies available right now.")
    for r in borrow_requests:
        if r["user_id"] == user.user_id and r["book_id"] == book_id and r["status"] == "pending":
            raise DuplicateError("You already have a pending request for this book.")

    request = {
        "request_id": _next_request_id[0],
        "user_id": user.user_id,
        "username": user.username,
        "book_id": book.book_id,
        "book_title": book.title,
        "status": "pending",
    }
    _next_request_id[0] += 1
    borrow_requests.append(request)
    _log(f"Request #{request['request_id']} by {user.username}")
    return request


def set_request_status(request_id, status):
    if status not in ("approved", "rejected", "pending"):
        raise ValidationError("Invalid status.")
    for r in borrow_requests:
        if r["request_id"] == request_id:
            r["status"] = status
            _log(f"Request #{request_id} -> {status}")
            return r
    raise NotFoundError("Request not found.")


def seed_data():
    if users:
        return
    users.append(Administrator(_next_user_id[0], "admin", "admin123", "System Administrator")); _next_user_id[0] += 1
    users.append(Staff(_next_user_id[0], "staff", "staff123", "Library Staff")); _next_user_id[0] += 1
    users.append(Student(_next_user_id[0], "student", "student123", "Juan Student")); _next_user_id[0] += 1

    # ---- original 4 ----
    add_book("Noli Me Tangere", "Jose Rizal", "Classic", 3)
    add_book("Eloquent JavaScript", "Marijn Haverbeke", "Programming", 2)
    add_book("Python Crash Course", "Eric Matthes", "Programming", 4)
    add_book("Introduction to Algorithms", "Thomas H. Cormen", "Computer Science", 1, "ebook")

    # ---- 8 more ----
    add_book("El Filibusterismo", "Jose Rizal", "Classic", 2)
    add_book("Florante at Laura", "Francisco Balagtas", "Classic", 3)
    add_book("Harry Potter and the Sorcerer's Stone", "J.K. Rowling", "Fantasy", 5)
    add_book("The Hobbit", "J.R.R. Tolkien", "Fantasy", 2)
    add_book("Clean Code", "Robert C. Martin", "Programming", 3)
    add_book("Automate the Boring Stuff with Python", "Al Sweigart", "Programming", 4, "ebook")
    add_book("Sapiens: A Brief History of Humankind", "Yuval Noah Harari", "History", 2)
    add_book("Atomic Habits", "James Clear", "Self-Help", 6)

    activity_log.clear()
