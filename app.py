"""The app uses separate HTML, CSS and SQL modules."""
import re
import secrets
import sqlite3
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

import config
import materials
import users

app = Flask(__name__)
app.secret_key = config.secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.secure_cookies,
    MAX_CONTENT_LENGTH=128 * 1024,
)


@app.before_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        g.user = users.get_user(user_id)
        if g.user is None:
            session.clear()


def require_login():
    if g.user is None:
        abort(403)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


def check_csrf():
    expected = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(403)


def valid_url(url):
    if len(url) > 500:
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme.lower() in ("http", "https")
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
                and not any(character.isspace() for character in url))
    except ValueError:
        return False


def positive_integer(value):
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def collect_material_form():
    """Validate all user input before passing it to SQL functions."""
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
    if not valid_url(form["url"]):
        errors.append("Anna kelvollinen http- tai https-linkki (enintään 500 merkkiä).")
    subject_id = positive_integer(form["subject_id"])
    type_id = positive_integer(form["type_id"])
    if subject_id is None or not materials.subject_exists(subject_id):
        errors.append("Valitse kelvollinen aihealue.")
    if type_id is None or not materials.type_exists(type_id):
        errors.append("Valitse kelvollinen materiaalityyppi.")
    return form, errors, subject_id, type_id


def material_form_page(title, action, form, errors):
    return render_template(
        "material_form.html", title=title, action=action, form=form,
        errors=errors, subjects=materials.get_subjects(), types=materials.get_types()
    )


def get_owned_material(material_id):
    material = materials.get_material(material_id)
    if material is None:
        abort(404)
    if g.user is None or material["user_id"] != g.user["id"]:
        abort(403)
    return material


@app.route("/")
def index():
    search_term = request.args.get("q", "").strip()
    if len(search_term) > 100:
        abort(400)
    all_materials = materials.get_materials(search_term)
    return render_template("index.html", title="Materiaalit",
                           materials=all_materials, search_term=search_term)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("index"))
    username = ""
    if request.method == "POST":
        check_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,24}", username):
            flash("Käyttäjätunnus: 3–24 merkkiä (kirjaimet, numerot ja _).", "error")
        elif not 8 <= len(password) <= 128:
            flash("Salasanan pituuden on oltava 8–128 merkkiä.", "error")
        else:
            try:
                user_id = users.create_user(username, password)
            except sqlite3.IntegrityError:
                flash("Käyttäjätunnus on jo käytössä.", "error")
            else:
                session.clear()
                session["user_id"] = user_id
                flash("Tervetuloa StudyHubiin!", "success")
                return redirect(url_for("index"))
    return render_template("auth.html", title="Rekisteröidy",
                           action="register", username=username)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("index"))
    username = ""
    if request.method == "POST":
        check_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_id = users.check_login(username, password)
        if user_id is None:
            flash("Virheellinen käyttäjätunnus tai salasana.", "error")
        else:
            session.clear()
            session["user_id"] = user_id
            flash("Kirjautuminen onnistui.", "success")
            return redirect(url_for("index"))
    return render_template("auth.html", title="Kirjaudu sisään",
                           action="login", username=username)


@app.route("/logout", methods=["POST"])
def logout():
    require_login()
    check_csrf()
    session.clear()
    flash("Kirjauduit ulos.", "success")
    return redirect(url_for("index"))


@app.route("/materials/new")
def new_material():
    require_login()
    form = {"title": "", "description": "", "url": "",
            "subject_id": "", "type_id": ""}
    return material_form_page("Lisää materiaali", url_for("create_material"), form, [])


@app.route("/materials/create", methods=["POST"])
def create_material():
    require_login()
    check_csrf()
    form, errors, subject_id, type_id = collect_material_form()
    if errors:
        return material_form_page("Lisää materiaali", url_for("create_material"),
                                  form, errors), 400
    material_id = materials.add_material(
        form["title"], form["description"], form["url"],
        subject_id, type_id, g.user["id"])
    flash("Materiaali lisätty.", "success")
    return redirect(url_for("material_detail", material_id=material_id))


@app.route("/materials/<int:material_id>")
def material_detail(material_id):
    material = materials.get_material(material_id)
    if material is None:
        abort(404)
    return render_template("material_detail.html", title=material["title"],
                           material=material)


@app.route("/materials/<int:material_id>/edit")
def edit_material(material_id):
    require_login()
    material = get_owned_material(material_id)
    form = {key: material[key] for key in
            ("title", "description", "url", "subject_id", "type_id")}
    return material_form_page("Muokkaa materiaalia",
                              url_for("update_material", material_id=material_id), form, [])


@app.route("/materials/<int:material_id>/update", methods=["POST"])
def update_material(material_id):
    require_login()
    check_csrf()
    get_owned_material(material_id)
    form, errors, subject_id, type_id = collect_material_form()
    if errors:
        return material_form_page("Muokkaa materiaalia",
                                  url_for("update_material", material_id=material_id),
                                  form, errors), 400
    materials.update_material(material_id, g.user["id"], form["title"],
                              form["description"], form["url"], subject_id, type_id)
    flash("Materiaali päivitetty.", "success")
    return redirect(url_for("material_detail", material_id=material_id))


@app.route("/materials/<int:material_id>/delete", methods=["GET", "POST"])
def delete_material(material_id):
    require_login()
    material = get_owned_material(material_id)
    if request.method == "POST":
        check_csrf()
        materials.delete_material(material_id, g.user["id"])
        flash("Materiaali poistettu.", "success")
        return redirect(url_for("index"))
    return render_template("material_delete.html", title="Poista materiaali",
                           material=material)


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def error_page(error):
    messages = {400: "Virheellinen pyyntö.",
                403: "Sinulla ei ole oikeutta tehdä tätä.",
                404: "Sivua tai materiaalia ei löytynyt.",
                413: "Lähetetty lomake on liian suuri."}
    return render_template("error.html", title=f"Virhe {error.code}",
                           message=messages[error.code]), error.code


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
