"""StudyHub: the first functional version of a study material sharing app.

Requirements: Python 3.10+ and Flask (which includes Jinja2 and Werkzeug).

Run on macOS/Linux:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install Flask
    python3 studyhub.py

Then visit http://127.0.0.1:5000

A SQLite database, studyhub.db, is automatically created beside this file.
For persistent sessions, set STUDYHUB_SECRET_KEY to a long random secret.
For HTTPS deployment, also set STUDYHUB_HTTPS=1. Do not commit the database,
passwords, or secrets to your public GitHub repository.

Flask routes, SQL, HTML, and CSS are in this one file.
This first version supports authentication and creating/listing/viewing materials.
Search, editing, deletion, profiles, and comments will be developed later.
"""

import os
import re
import secrets
import sqlite3
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for
)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash


APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("STUDYHUB_DB", str(APP_DIR / "studyhub.db")))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("STUDYHUB_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("STUDYHUB_HTTPS") == "1",
    MAX_CONTENT_LENGTH=128 * 1024,
)


# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

def get_db():
    """Return the SQLite connection scoped to the current Flask request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and the two sets of allowed classifications."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS material_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            type_id INTEGER NOT NULL REFERENCES material_types(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_materials_user ON materials(user_id);
        CREATE INDEX IF NOT EXISTS idx_materials_created ON materials(created_at);
    """)
    db.executemany(
        "INSERT OR IGNORE INTO subjects (name) VALUES (?)",
        [(x,) for x in ("Ohjelmointi", "Algoritmit", "Tietokannat", "Matematiikka", "Tekoäly", "Muu")]
    )
    db.executemany(
        "INSERT OR IGNORE INTO material_types (name) VALUES (?)",
        [(x,) for x in ("Video", "Artikkeli", "Kirja", "Verkkokurssi", "Opas")]
    )
    db.commit()


def classifications():
    db = get_db()
    return (
        db.execute("SELECT id, name FROM subjects ORDER BY name").fetchall(),
        db.execute("SELECT id, name FROM material_types ORDER BY name").fetchall(),
    )


MATERIAL_JOIN = """
    SELECT m.*, u.username, s.name AS subject_name, t.name AS type_name
    FROM materials m
    JOIN users u ON u.id = m.user_id
    JOIN subjects s ON s.id = m.subject_id
    JOIN material_types t ON t.id = m.type_id
"""


def get_material(material_id):
    material = get_db().execute(
        MATERIAL_JOIN + " WHERE m.id = ?", (material_id,)
    ).fetchone()
    if material is None:
        abort(404)
    return material



# -----------------------------------------------------------------------------
# Session authentication and CSRF protection
# -----------------------------------------------------------------------------

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.context_processor
def template_globals():
    return {"csrf_token": csrf_token}


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()

    # Every state-changing action in this application uses POST.
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, description="Lomakkeen turvatunniste puuttuu tai on vanhentunut.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Kirjaudu ensin sisään.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def safe_int(value):
    try:
        number = int(value)
        return number if number > 0 else None
    except (ValueError, TypeError):
        return None


def is_valid_http_url(url):
    if len(url) > 500:
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.netloc)
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not any(c.isspace() for c in url)
        )
    except ValueError:
        return False


# -----------------------------------------------------------------------------
# Web routes
# -----------------------------------------------------------------------------

@app.get("/")
def index():
    """Show the latest 24 materials, newest first."""
    materials = get_db().execute(
        MATERIAL_JOIN + " ORDER BY m.created_at DESC, m.id DESC LIMIT 24"
    ).fetchall()
    return render_template("index.html", title="Materiaalit", materials=materials)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("index"))
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,24}", username):
            flash("Käyttäjätunnus: 3–24 merkkiä (kirjaimet, numerot ja _).", "error")
        elif not 8 <= len(password) <= 128:
            flash("Salasanan pituuden on oltava 8–128 merkkiä.", "error")
        else:
            db = get_db()
            try:
                cursor = db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password))
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("Käyttäjätunnus on jo käytössä.", "error")
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                flash("Tervetuloa StudyHubiin!", "success")
                return redirect(url_for("index"))
    return render_template("auth.html", title="Rekisteröidy", action="register", username=username)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("index"))
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Virheellinen käyttäjätunnus tai salasana.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash("Kirjautuminen onnistui.", "success")
            return redirect(url_for("index"))
    return render_template("auth.html", title="Kirjaudu sisään", action="login", username=username)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Kirjauduit ulos.", "success")
    return redirect(url_for("index"))


def collect_material_form():
    form = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "url": request.form.get("url", "").strip(),
        "subject_id": request.form.get("subject_id", ""),
        "type_id": request.form.get("type_id", ""),
    }
    errors = []
    if not 3 <= len(form["title"]) <= 120:
        errors.append("Otsikon pituuden on oltava 3–120 merkkiä.")
    if not 10 <= len(form["description"]) <= 2000:
        errors.append("Kuvauksen pituuden on oltava 10–2000 merkkiä.")
    if not is_valid_http_url(form["url"]):
        errors.append("Anna kelvollinen http- tai https-linkki (enintään 500 merkkiä).")

    subject_id, type_id = safe_int(form["subject_id"]), safe_int(form["type_id"])
    if subject_id is None or get_db().execute(
        "SELECT 1 FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone() is None:
        errors.append("Valitse kelvollinen aihealue.")
    if type_id is None or get_db().execute(
        "SELECT 1 FROM material_types WHERE id = ?", (type_id,)
    ).fetchone() is None:
        errors.append("Valitse kelvollinen materiaalityyppi.")
    return form, errors, subject_id, type_id


def material_form_page(title, form, errors):
    subjects, types = classifications()
    return render_template(
        "material_form.html", title=title, form=form, errors=errors,
        subjects=subjects, types=types
    )


@app.route("/materials/new", methods=["GET", "POST"])
@login_required
def new_material():
    form = dict(title="", description="", url="", subject_id="", type_id="")
    errors = []
    if request.method == "POST":
        form, errors, subject_id, type_id = collect_material_form()
        if not errors:
            db = get_db()
            cursor = db.execute("""
                INSERT INTO materials
                (user_id, subject_id, type_id, title, description, url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                g.user["id"], subject_id, type_id, form["title"],
                form["description"], form["url"]
            ))
            db.commit()
            flash("Materiaali lisätty.", "success")
            return redirect(url_for("material_detail", material_id=cursor.lastrowid))
    return material_form_page("Lisää materiaali", form, errors)


@app.get("/materials/<int:material_id>")
def material_detail(material_id):
    """Show one shared material and its external link."""
    material = get_material(material_id)
    return render_template("material_detail.html", title=material["title"], material=material)


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def error_page(error):
    messages = {
        400: "Virheellinen pyyntö. Päivitä sivu ja kokeile uudelleen.",
        403: "Sinulla ei ole oikeutta tehdä tätä.",
        404: "Sivua tai materiaalia ei löytynyt.",
        413: "Lähetetty lomake on liian suuri."
    }
    return render_template("error.html", title=f"Virhe {error.code}",
                           message=messages[error.code]), error.code


# -----------------------------------------------------------------------------
# Embedded HTML templates + handwritten CSS, rendered by render_template.
# This keeps the entire project in studyhub.py, as requested.
# -----------------------------------------------------------------------------

TEMPLATES = {
    'base.html': r"""<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} · StudyHub</title>
  <style>
    :root { --ink:#183047; --muted:#5b6b7b; --border:#dce4ed;
            --bg:#f5f7fb; --card:#fff; --blue:#1459ac; --light:#eaf3ff; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--bg);
           font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    a { color:var(--blue); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .topbar { background:#102f52; color:white; }
    .nav { max-width:1040px; margin:auto; display:flex; flex-wrap:wrap;
           align-items:center; gap:12px; padding:14px 20px; }
    .nav a { color:#fff; }
    .brand { font-weight:800; font-size:1.25rem; margin-right:auto; }
    .logout-form { display:inline; margin:0; }
    .nav-button { border:1px solid #8caacb; background:none; color:#fff;
                  padding:5px 9px; border-radius:7px; cursor:pointer; font:inherit; }
    main { max-width:1040px; margin:30px auto 70px; padding:0 20px; }
    .hero { margin-bottom:24px; }
    h1,h2,h3 { line-height:1.2; }
    h1 { font-size:2rem; margin:0 0 10px; }
    h2 { font-size:1.35rem; }
    h3 { margin:.25rem 0; }
    .muted { color:var(--muted); }
    .card,.panel { background:var(--card); border:1px solid var(--border);
                   border-radius:14px; padding:20px; box-shadow:0 3px 12px #16345108; }
    .card { display:flex; flex-direction:column; gap:8px; }
    .card p { margin:0; }
    .grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); }
    .filters { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:23px; }
    .filters .field { flex:1 1 170px; margin:0; }
    .field { margin-bottom:17px; }
    label { display:block; font-weight:650; margin-bottom:5px; }
    input,select,textarea { width:100%; border:1px solid #aebecd; padding:10px 12px;
                            border-radius:8px; background:white; font:inherit; color:inherit; }
    textarea { min-height:130px; resize:vertical; }
    input:focus,select:focus,textarea:focus { outline:2px solid #72b1f6; outline-offset:1px; }
    .button { display:inline-block; border:0; border-radius:8px; padding:10px 16px;
              background:var(--blue); color:white; cursor:pointer; font:inherit; font-weight:600; }
    .button:hover { text-decoration:none; background:#0e4383; }
    .button.secondary { color:var(--blue); background:var(--light); }
    .button.danger { background:#ab2626; }
    .button.small { font-size:.88rem; padding:7px 10px; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:15px; }
    .actions form { display:inline; }
    .tag { display:inline-block; padding:4px 8px; background:#ecf2f8; border-radius:7px;
           font-size:.85rem; margin:2px 5px 2px 0; color:#3a5369; }
    .flash { border:1px solid #91c2a0; padding:12px 15px; background:#e8f8ed;
             border-radius:8px; margin-bottom:13px; }
    .flash.error { border-color:#e8aaaa; background:#fff0f0; }
    .errors { color:#a52323; }
    .wide { max-width:720px; }
    .prose { white-space:pre-wrap; overflow-wrap:anywhere; }
    .detail-link { overflow-wrap:anywhere; }
    .comment { padding:14px 0; border-bottom:1px solid var(--border); }
    .comment:last-child { border-bottom:0; }
    .footer { text-align:center; font-size:.85rem; color:var(--muted); padding:18px; }
    @media(max-width:600px) { h1 { font-size:1.6rem; } .nav { gap:10px; } }
  </style>
</head>
<body>
<header class="topbar">
  <nav class="nav" aria-label="Päänavigaatio">
    <a class="brand" href="{{ url_for('index') }}">📘 StudyHub</a>
    <a href="{{ url_for('index') }}">Materiaalit</a>
    {% if g.user %}
      <a href="{{ url_for('new_material') }}">Lisää materiaali</a>
      <span>{{ g.user['username'] }}</span>
      <form class="logout-form" method="post" action="{{ url_for('logout') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button class="nav-button" type="submit">Kirjaudu ulos</button>
      </form>
    {% else %}
      <a href="{{ url_for('login') }}">Kirjaudu</a>
      <a href="{{ url_for('register') }}">Rekisteröidy</a>
    {% endif %}
  </nav>
</header>
<main>
  {% with flashes = get_flashed_messages(with_categories=true) %}
    {% for category, message in flashes %}
      <div class="flash {{ 'error' if category == 'error' else '' }}" role="status">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</main>
<footer class="footer">StudyHub · Tietokannat ja web-ohjelmointi · Flask + SQLite</footer>
</body>
</html>""",
    '_material_card.html': r"""
<article class="card">
  <h3><a href="{{ url_for('material_detail', material_id=material['id']) }}">{{ material['title'] }}</a></h3>
  <p class="muted">{{ material['description'] | truncate(150) }}</p>
  <div>
    <span class="tag">{{ material['subject_name'] }}</span>
    <span class="tag">{{ material['type_name'] }}</span>
  </div>
  <small class="muted">Lisännyt
    {{ material['username'] }}
    · {{ material['created_at'] }}
  </small>
</article>""",
    'index.html': r"""{% extends 'base.html' %}
{% block content %}
<div class="hero">
  <h1>Opiskelumateriaalit</h1>
  <p class="muted">Tutustu muiden opiskelijoiden jakamiin oppaisiin, kirjoihin ja videoihin.</p>
  {% if g.user %}<p><a class="button" href="{{ url_for('new_material') }}">+ Lisää materiaali</a></p>{% endif %}
</div>
{% if materials %}
  <div class="grid">
    {% for material in materials %}{% include '_material_card.html' %}{% endfor %}
  </div>
{% else %}
  <div class="panel"><p>Materiaaleja ei ole vielä lisätty.</p></div>
{% endif %}
{% endblock %}""",
    'auth.html': r"""{% extends 'base.html' %}
{% block content %}
<div class="panel wide">
  <h1>{{ title }}</h1>
  <form method="post" action="{{ url_for(action) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="field">
      <label for="username">Käyttäjätunnus</label>
      <input id="username" name="username" minlength="3" maxlength="24" required
             autocomplete="username" value="{{ username }}">
    </div>
    <div class="field">
      <label for="password">Salasana</label>
      <input id="password" type="password" name="password" minlength="8" maxlength="128"
             required autocomplete="{{ 'new-password' if action == 'register' else 'current-password' }}">
      {% if action == 'register' %}<small class="muted">Vähintään 8 merkkiä.</small>{% endif %}
    </div>
    <button class="button" type="submit">{{ title }}</button>
  </form>
  {% if action == 'register' %}
    <p>Onko sinulla jo tunnus? <a href="{{ url_for('login') }}">Kirjaudu sisään</a>.</p>
  {% else %}
    <p>Eikö sinulla ole tunnusta? <a href="{{ url_for('register') }}">Rekisteröidy</a>.</p>
  {% endif %}
</div>
{% endblock %}""",
    'material_form.html': r"""{% extends 'base.html' %}
{% block content %}
<div class="panel wide">
  <h1>{{ title }}</h1>
  {% if errors %}
    <div class="flash error" role="alert">
      <strong>Tarkista lomake:</strong>
      <ul>{% for error in errors %}<li>{{ error }}</li>{% endfor %}</ul>
    </div>
  {% endif %}
  <form method="post" action="{{ url_for('new_material') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="field">
      <label for="title">Materiaalin nimi</label>
      <input id="title" name="title" required minlength="3" maxlength="120" value="{{ form['title'] }}">
    </div>
    <div class="field">
      <label for="description">Kuvaus</label>
      <textarea id="description" name="description" required minlength="10" maxlength="2000">{{ form['description'] }}</textarea>
    </div>
    <div class="field">
      <label for="url">Materiaalin linkki (https://...)</label>
      <input id="url" type="url" name="url" required maxlength="500" value="{{ form['url'] }}">
    </div>
    <div class="field">
      <label for="subject_id">Aihealue</label>
      <select id="subject_id" name="subject_id" required>
        <option value="">Valitse aihealue</option>
        {% for s in subjects %}
          <option value="{{ s['id'] }}" {% if form['subject_id']|string == s['id']|string %}selected{% endif %}>{{ s['name'] }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="field">
      <label for="type_id">Materiaalin tyyppi</label>
      <select id="type_id" name="type_id" required>
        <option value="">Valitse tyyppi</option>
        {% for t in types %}
          <option value="{{ t['id'] }}" {% if form['type_id']|string == t['id']|string %}selected{% endif %}>{{ t['name'] }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="actions">
      <button class="button" type="submit">Tallenna</button>
      <a href="{{ url_for('index') }}">Peruuta</a>
    </div>
  </form>
</div>
{% endblock %}""",
    'material_detail.html': r"""{% extends 'base.html' %}
{% block content %}
<article class="panel">
  <p><a href="{{ url_for('index') }}">← Kaikki materiaalit</a></p>
  <h1>{{ material['title'] }}</h1>
  <div><span class="tag">{{ material['subject_name'] }}</span><span class="tag">{{ material['type_name'] }}</span></div>
  <p class="muted">Lisännyt {{ material['username'] }} · {{ material['created_at'] }}</p>
  <p class="prose">{{ material['description'] }}</p>
  <p class="detail-link"><strong>Linkki:</strong>
    <a href="{{ material['url'] }}" target="_blank" rel="noopener noreferrer">{{ material['url'] }}</a>
  </p>
</article>
{% endblock %}""",
    'error.html': r"""{% extends 'base.html' %}
{% block content %}
<div class="panel wide">
  <h1>{{ title }}</h1>
  <p>{{ message }}</p>
  <p><a href="{{ url_for('index') }}">Palaa etusivulle</a></p>
</div>
{% endblock %}""",
}

app.jinja_loader = DictLoader(TEMPLATES)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    print("StudyHub käynnistyy: http://127.0.0.1:5000")
    print("Huom: paikalliseen kehityskäyttöön; älä julkaise Flask-kehityspalvelinta internetiin.")
    app.run(host="127.0.0.1", port=5000, debug=False)
