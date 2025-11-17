from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///almacen.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia_esta_clave")

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="operador")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    brand = db.Column(db.String(100))
    item_type = db.Column(db.String(100))
    size = db.Column(db.String(100))
    unit_base = db.Column(db.String(10), nullable=False)

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movement_no = db.Column(db.Integer, nullable=False, index=True)
    movement_type = db.Column(db.String(10), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    supplier = db.Column(db.String(150))
    customer = db.Column(db.String(150))
    note = db.Column(db.Text)

    user = db.relationship("User", backref="movements")

class MovementDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movement_id = db.Column(db.Integer, db.ForeignKey("movement.id"))
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    lot = db.Column(db.String(100))
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), nullable=False)

    movement = db.relationship("Movement", backref="details")
    item = db.relationship("Item", backref="details")

def get_next_movement_no():
    last = db.session.query(db.func.max(Movement.movement_no)).scalar()
    return (last or 4200) + 1

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

@app.route("/init_admin")
def init_admin():
    if User.query.filter_by(username="admin").first():
        return "Admin ya existe"
    admin = User(username="admin", role="admin")
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()
    return "Usuario admin creado. Usuario: admin / Pass: admin123"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Bienvenido, " + user.username)
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    total_items = Item.query.count()
    total_movements = Movement.query.count()
    last_movements = Movement.query.order_by(Movement.date.desc()).limit(5).all()
    return render_template(
        "dashboard.html",
        user=current_user(),
        total_items=total_items,
        total_movements=total_movements,
        last_movements=last_movements,
    )

@app.route("/items")
@login_required
def items():
    items = Item.query.order_by(Item.name).all()
    return render_template("items.html", items=items, user=current_user())

@app.route("/items/new", methods=["GET", "POST"])
@login_required
def new_item():
    if request.method == "POST":
        name = request.form["name"]
        brand = request.form.get("brand")
        item_type = request.form.get("item_type")
        size = request.form.get("size")
        unit_base = request.form["unit_base"]

        item = Item(
            name=name,
            brand=brand,
            item_type=item_type,
            size=size,
            unit_base=unit_base,
        )
        db.session.add(item)
        db.session.commit()
        flash("Artículo creado correctamente")
        return redirect(url_for("items"))

    return render_template("new_item.html", user=current_user())

@app.route("/movements/new", methods=["GET", "POST"])
@login_required
def new_movement():
    items = Item.query.order_by(Item.name).all()
    if not items:
        flash("Primero crea un artículo")
        return redirect(url_for("new_item"))

    if request.method == "POST":
        movement_type = request.form["movement_type"]
        supplier = request.form.get("supplier")
        customer = request.form.get("customer")
        note = request.form.get("note")

        item_id = int(request.form["item_id"])
        lot = request.form.get("lot")
        quantity = float(request.form["quantity"])
        unit = request.form["unit"]

        mov = Movement(
            movement_no=get_next_movement_no(),
            movement_type=movement_type,
            user_id=current_user().id,
            supplier=supplier,
            customer=customer,
            note=note,
        )
        db.session.add(mov)
        db.session.flush()

        detail = MovementDetail(
            movement_id=mov.id,
            item_id=item_id,
            lot=lot,
            quantity=quantity,
            unit=unit,
        )
        db.session.add(detail)
        db.session.commit()

        flash(f"{movement_type} registrada con No. {mov.movement_no}")
        return redirect(url_for("dashboard"))

    return render_template("new_movement.html", items=items, user=current_user())

@app.route("/movements")
@login_required
def list_movements():
    movements = Movement.query.order_by(Movement.date.desc()).all()
    return render_template("movements.html", movements=movements, user=current_user())

@app.route("/inventory")
@login_required
def inventory():
    rows = (
        db.session.query(
            Item.id,
            Item.name,
            MovementDetail.lot,
            MovementDetail.unit,
            Movement.movement_type,
            db.func.sum(MovementDetail.quantity),
        )
        .join(Movement, Movement.id == MovementDetail.movement_id)
        .join(Item, Item.id == MovementDetail.item_id)
        .group_by(
            Item.id,
            Item.name,
            MovementDetail.lot,
            MovementDetail.unit,
            Movement.movement_type,
        )
        .all()
    )

    inventory_dict = {}
    for item_id, name, lot, unit, movement_type, qty in rows:
        key = (item_id, name, lot, unit)
        sign = 1 if movement_type == "ENTRADA" else -1
        inventory_dict[key] = inventory_dict.get(key, 0) + sign * qty

    inventory_rows = []
    for (item_id, name, lot, unit), qty in inventory_dict.items():
        inventory_rows.append(
            {"item_id": item_id, "name": name, "lot": lot, "unit": unit, "qty": qty}
        )

    inventory_rows.sort(key=lambda r: (r["name"] or "", r["lot"] or ""))

    return render_template(
        "inventory.html", inventory=inventory_rows, user=current_user()
    )

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
