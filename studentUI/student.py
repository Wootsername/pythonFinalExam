import os
import base64
import sqlite3
from flask import Flask, render_template, request, jsonify, send_file, g, url_for
import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import time

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
DB_PATH = os.path.join(os.path.dirname(__file__), "students.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------
# DATABASE FUNCTIONS
# ---------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.before_request
def init_db_once():
    if not hasattr(g, "db_initialized"):
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idno TEXT,
                lastname TEXT,
                firstname TEXT,
                course TEXT,
                level TEXT,
                photo_path TEXT,
                qr_path TEXT,
                created_at TEXT
            )
        """)
        db.commit()
        g.db_initialized = True

@app.teardown_appcontext
def close_db(error):
    if "db" in g:
        g.db.close()


# ---------------------------
# MAIN PAGE
# ---------------------------
@app.route("/")
def index():
    courses = ["BSIT", "BSCS", "BSIS", "BSHM", "BSA", "BSBA"]
    levels = ["1", "2", "3", "4"]
    return render_template("index.html", courses=courses, levels=levels)


# ---------------------------
# SAVE STUDENT
# ---------------------------
@app.route("/save", methods=["POST"])
def save_student():
    data = request.get_json(force=True)

    idno = data.get("idno", "").strip()
    lastname = data.get("lastname", "").strip()
    firstname = data.get("firstname", "").strip()
    course = data.get("course", "").strip()
    level = data.get("level", "").strip()
    photo_b64 = data.get("photo_data")

    if not (idno and lastname and firstname and course and level):
        return jsonify({"status": "error", "msg": "Missing fields"}), 400

    if not photo_b64 or "," not in photo_b64:
        return jsonify({"status": "error", "msg": "Invalid or missing photo"}), 400

    try:
        header, encoded = photo_b64.split(",", 1)
        image_data = base64.b64decode(encoded)
    except Exception as e:
        return jsonify({"status": "error", "msg": "Image decode failed", "error": str(e)}), 400

    photo_filename = f"{idno}_photo_{int(time.time())}.jpg"
    photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
    with open(photo_path, "wb") as f:
        f.write(image_data)

    # ---------------------------
    # QR GENERATION
    # ---------------------------
    qr_url_value = url_for("view_student", idno=idno, _external=True)
    qr_filename = f"{idno}_qr_{int(time.time())}.png"
    qr_path = os.path.join(UPLOAD_FOLDER, qr_filename)

    qr_obj = qrcode.QRCode(version=1, box_size=10, border=2)
    qr_obj.add_data(qr_url_value)
    qr_obj.make(fit=True)
    img = qr_obj.make_image(fill_color="black", back_color="white")
    img.save(qr_path)

    # Save record
    db = get_db()
    cur = db.execute("""
        INSERT INTO students (idno, lastname, firstname, course, level, photo_path, qr_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (idno, lastname, firstname, course, level, photo_filename, qr_filename))
    db.commit()

    student_id = cur.lastrowid

    return jsonify({
        "status": "ok",
        "id": student_id,
        "qr_url": url_for("static", filename=f"uploads/{qr_filename}")
    })


# ---------------------------
# STUDENT VIEWER (QR OPENS HERE)
# ---------------------------
@app.route("/student/<idno>")
def view_student(idno):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE idno=?", (idno,)).fetchone()

    if not student:
        return f"<h1>Student with ID {idno} not found.</h1>"

    return render_template("student_view.html", student=student)


# ---------------------------
# EXPORT FUNCTIONS
# ---------------------------
def generate_idcard(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        return None

    # Paths
    photo_path = os.path.join(UPLOAD_FOLDER, student["photo_path"])
    qr_path = os.path.join(UPLOAD_FOLDER, student["qr_path"])

    # Load images
    photo = Image.open(photo_path).convert("RGB")
    qr = Image.open(qr_path).convert("RGB")

    # ID CARD SIZE
    WIDTH, HEIGHT = 1100, 650
    card = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(card)

    # Load fonts
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 40)
        label_font = ImageFont.truetype("arialbd.ttf", 26)
        value_font = ImageFont.truetype("arial.ttf", 26)
        footer_font = ImageFont.truetype("arial.ttf", 20)
    except:
        title_font = label_font = value_font = footer_font = ImageFont.load_default()

    # ---------------------------
    # HEADER BAR
    # ---------------------------
    header_color = (25, 55, 130)  # Navy blue
    draw.rectangle([(0, 0), (WIDTH, 100)], fill=header_color)

    # SCHOOL LOGO (Optional)
    logo_path = os.path.join("static", "school_logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).resize((80, 80))
        card.paste(logo, (30, 10))

    # HEADER TEXT
    draw.text((150, 25), "UNIVERSITY STUDENT ID CARD", fill="white", font=title_font)

    # ---------------------------
    # STUDENT PHOTO
    # ---------------------------
    photo = photo.resize((300, 300))
    card.paste(photo, (50, 150))

    # ---------------------------
    # QR CODE
    # ---------------------------
    qr = qr.resize((220, 220))
    card.paste(qr, (WIDTH - 270, 150))

    # ---------------------------
    # STUDENT DETAILS (CENTER)
    # ---------------------------
    details_x = 400
    details_y = 160
    spacing = 55

    info = [
        ("IDNO:", student["idno"]),
        ("LASTNAME:", student["lastname"]),
        ("FIRSTNAME:", student["firstname"]),
        ("PROGRAM:", student["course"]),
        ("YEAR LEVEL:", student["level"]),
    ]

    for label, value in info:
        draw.text((details_x, details_y), label, fill="black", font=label_font)
        draw.text((details_x + 220, details_y), str(value), fill="black", font=value_font)
        details_y += spacing

    # ---------------------------
    # SIGNATURE & SEAL SECTION
    # ---------------------------
    draw.line([(50, HEIGHT - 150), (350, HEIGHT - 150)], fill="black", width=2)
    draw.text((50, HEIGHT - 140), "Registrar Signature", fill="black", font=value_font)

    seal_path = os.path.join("static", "seal.png")
    if os.path.exists(seal_path):
        seal = Image.open(seal_path).resize((120, 120))
        card.paste(seal, (WIDTH - 180, HEIGHT - 190))

    # Validity
    draw.text((400, HEIGHT - 130), "VALID UNTIL: 2026", fill="black", font=label_font)

    # ---------------------------
    # FOOTER
    # ---------------------------
    draw.text((50, HEIGHT - 40), "Copyright © Karl Gaviola, 2025",
              fill="black", font=footer_font)

    return card



@app.route("/export/png/<int:student_id>")
def export_png(student_id):
    card = generate_idcard(student_id)
    if not card:
        return "Student not found", 404
    bio = BytesIO()
    card.save(bio, "PNG")
    bio.seek(0)
    return send_file(bio, mimetype="image/png", as_attachment=True, download_name=f"idcard_{student_id}.png")


@app.route("/export/pdf/<int:student_id>")
def export_pdf(student_id):
    card = generate_idcard(student_id)
    if not card:
        return "Student not found", 404
    bio = BytesIO()
    card.save(bio, "PDF")
    bio.seek(0)
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name=f"idcard_{student_id}.pdf")


# ---------------------------
# RECORDS PAGE
# ---------------------------
@app.route("/records")
def records():
    db = get_db()
    rows = db.execute("SELECT * FROM students ORDER BY created_at DESC").fetchall()
    return render_template("records.html", students=rows)


# ---------------------------
# RUN SERVER
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
