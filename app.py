from flask import Flask, render_template, request, jsonify, send_file, abort
from datetime import datetime
from pathlib import Path
import json
import os
import sqlite3
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = BASE_DIR / "products.json"
# On Railway, attach a Volume at /app/data. For local development, data is stored
# in ./data unless ORDER_DATA_DIR is explicitly set.
DATA_DIR = Path(os.environ.get("ORDER_DATA_DIR", str(BASE_DIR / "data"))).resolve()
ORDERS_DIR = DATA_DIR / "orders"
DB_FILE = DATA_DIR / "orders.sqlite3"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ORDERS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="public", static_url_path="")

with PRODUCTS_FILE.open("r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)


def db_connection():
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with db_connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT,
                total INTEGER NOT NULL,
                status TEXT NOT NULL,
                pdf_filename TEXT NOT NULL,
                order_details TEXT NOT NULL
            )
        """)
        # Persistent counter ensures order references are 1, 2, 3... across restarts.
        db.execute("""
            CREATE TABLE IF NOT EXISTS order_sequence (
                sequence_name TEXT PRIMARY KEY,
                last_number INTEGER NOT NULL
            )
        """)
        db.execute("""
            INSERT OR IGNORE INTO order_sequence (sequence_name, last_number)
            VALUES ('orders', 0)
        """)


def reserve_order_number():
    # BEGIN IMMEDIATE serializes simultaneous order submissions to avoid duplicates.
    with db_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT last_number FROM order_sequence WHERE sequence_name = 'orders'"
        ).fetchone()
        last_number = int(row["last_number"]) if row else 0
        number = last_number + 1
        db.execute(
            "INSERT INTO order_sequence (sequence_name, last_number) VALUES ('orders', ?) "
            "ON CONFLICT(sequence_name) DO UPDATE SET last_number = excluded.last_number",
            (number,)
        )
        db.commit()
        return number

initialize_database()


def escape_paragraph(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_order_pdf(order):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ShopTitle", parent=styles["Title"], alignment=TA_CENTER,
                              textColor=colors.HexColor("#172554"), spaceAfter=8))
    styles.add(ParagraphStyle(name="Meta", parent=styles["Normal"], leading=17))
    story = [
        Paragraph("KKP FIREWORKS — ORDER RECEIPT", styles["ShopTitle"]),
        Paragraph("Order reference: " + escape_paragraph(order["order_id"]), styles["Meta"]),
        Paragraph("Date: " + escape_paragraph(order["created_at"].replace("T", " ")), styles["Meta"]),
        Paragraph("Customer: " + escape_paragraph(order["customer_name"]), styles["Meta"]),
        Paragraph("Phone: " + escape_paragraph(order["phone"] or "Not provided"), styles["Meta"]),
        Spacer(1, 16),
    ]
    rows = [["Code", "Product", "Qty", "Unit price", "Amount"]]
    for item in order["items"]:
        rows.append([
            str(item["code"]), Paragraph(escape_paragraph(item["name"]), styles["BodyText"]),
            str(item["quantity"]), f'Rs. {item["unit_price"]:,}', f'Rs. {item["line_total"]:,}'
        ])
    rows.append(["", "", "", "TOTAL", f'Rs. {order["total"]:,}'])
    table = Table(rows, colWidths=[42, 220, 42, 75, 75], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172554")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8deea")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f4f7fb")]),
        ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        table, Spacer(1, 16),
        Paragraph("Order request only — confirm stock and final price with the customer.", styles["Italic"]),
        Spacer(1, 8), Paragraph("Created by Aditya Maganbhai Patel", styles["Normal"])
    ])
    doc.build(story)
    return buffer.getvalue()


@app.get("/")
def home():
    categories = list(dict.fromkeys(p["category"] for p in PRODUCTS))
    return render_template("index.html", products=PRODUCTS, categories=categories)


@app.get("/api/products")
def products():
    return jsonify({"success": True, "count": len(PRODUCTS), "products": PRODUCTS})


@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    customer_name = str(data.get("customer_name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    items = data.get("items", [])

    if not customer_name:
        return jsonify({"success": False, "message": "Please enter your name."}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "message": "Please select at least one product."}), 400

    product_by_id = {str(p["id"]): p for p in PRODUCTS}
    order_items, total = [], 0
    for item in items:
        if not isinstance(item, dict):
            continue
        product = product_by_id.get(str(item.get("product_id", item.get("id", ""))))
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if not product or quantity < 1 or quantity > 100:
            continue
        line_total = int(product["price"]) * quantity
        total += line_total
        order_items.append({
            "code": product["code"], "product_id": product["id"], "name": product["name"],
            "category": product["category"], "unit": product["unit"], "quantity": quantity,
            "unit_price": int(product["price"]), "line_total": line_total
        })

    if not order_items:
        return jsonify({"success": False, "message": "No valid products were selected."}), 400

    now = datetime.now().astimezone()
    order_number = reserve_order_number()
    order = {
        "order_id": str(order_number),
        "created_at": now.isoformat(timespec="seconds"),
        "customer_name": customer_name,
        "phone": phone,
        "items": order_items,
        "total": total,
        "status": "Order request received — confirm stock and final price with the customer."
    }
    pdf_bytes = build_order_pdf(order)
    pdf_filename = f'{order["order_id"]}_order.pdf'
    pdf_path = ORDERS_DIR / pdf_filename

    try:
        # Store the PDF on the persistent Railway Volume.
        pdf_path.write_bytes(pdf_bytes)
        # Store order history in SQLite on the same persistent Volume (no order.json files).
        with db_connection() as db:
            db.execute("""
                INSERT INTO orders (order_id, created_at, customer_name, phone, total, status, pdf_filename, order_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order["order_id"], order["created_at"], customer_name, phone, total,
                order["status"], pdf_filename, json.dumps(order, ensure_ascii=False)
            ))
    except Exception:
        # Do not report success if durable storage failed.
        try:
            if pdf_path.exists():
                pdf_path.unlink()
        except OSError:
            pass
        app.logger.exception("Failed to persist order")
        return jsonify({"success": False, "message": "Could not save the order. Please try again or contact the stall."}), 500

    import base64
    return jsonify({
        "success": True,
        "message": "Order saved successfully. Your PDF receipt is ready to download.",
        "order": order,
        "pdf_filename": pdf_filename,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "saved_pdf_path": f"orders/{pdf_filename}"
    }), 201


@app.get("/health")
def health():
    return jsonify({"status": "ok", "products": len(PRODUCTS)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
