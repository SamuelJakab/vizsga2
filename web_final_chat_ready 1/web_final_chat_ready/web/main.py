from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, bcrypt, User, Product, Cart, CartItem, Order, OrderItem, Coupon
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from datetime import timedelta
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

app = Flask(__name__)
app.config.from_object(Config)

# Kép feltöltési beállítások
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Inicializáció
db.init_app(app)
bcrypt.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Nincs jogosultsága az oldal megtekintéséhez!', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== ROUTES ====================

@app.route("/")
def home():
    products = Product.query.limit(12).all()
    return render_template("index.html", products=products)

@app.route("/shop")
def shop():
    category = request.args.get('category')
    if category:
        products = Product.query.filter_by(category=category).all()
    else:
        products = Product.query.all()
    return render_template("shop.html", products=products)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("single.html", product=product)

@app.route("/cart")
@login_required
def cart():
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not user_cart:
        user_cart = Cart(user_id=current_user.id)
        db.session.add(user_cart)
        db.session.commit()
    
    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    return render_template("cart.html", cart_items=cart_items, total=total)

@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    quantity = request.json.get('quantity', 1)
    product = Product.query.get_or_404(product_id)
    
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not user_cart:
        user_cart = Cart(user_id=current_user.id)
        db.session.add(user_cart)
        db.session.commit()
    
    cart_item = CartItem.query.filter_by(
        cart_id=user_cart.id, 
        product_id=product_id
    ).first()
    
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(cart_id=user_cart.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Termék hozzáadva a kosárhoz'})

@app.route("/remove-from-cart/<int:cart_item_id>", methods=["POST"])
@login_required
def remove_from_cart(cart_item_id):
    cart_item = CartItem.query.get_or_404(cart_item_id)
    user_cart = Cart.query.get(cart_item.cart_id)
    
    if user_cart.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    db.session.delete(cart_item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Termék eltávolítva a kosárból'})

@app.route("/update-cart-item/<int:cart_item_id>", methods=["POST"])
@login_required
def update_cart_item(cart_item_id):
    cart_item = CartItem.query.get_or_404(cart_item_id)
    user_cart = Cart.query.get(cart_item.cart_id)
    
    if user_cart.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    quantity = request.json.get('quantity', 1)
    
    if quantity <= 0:
        db.session.delete(cart_item)
    else:
        cart_item.quantity = quantity
    
    db.session.commit()
    
    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    return jsonify({
        'success': True, 
        'message': 'Kosár frissítve',
        'total': total
    })

@app.route("/apply-coupon", methods=["POST"])
@login_required
def apply_coupon():
    coupon_code = request.json.get('coupon_code')
    
    coupon = Coupon.query.filter_by(code=coupon_code).first()
    
    if not coupon:
        return jsonify({'success': False, 'message': 'Érvénytelen kuponkód'}), 404
    
    if not coupon.is_valid():
        return jsonify({'success': False, 'message': 'A kupon lejárt'}), 400
    
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not user_cart:
        return jsonify({'success': False, 'message': 'A kosár üres'}), 400
    
    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    discount = (total * coupon.discount_percent) / 100
    final_total = total - discount
    
    session['coupon_code'] = coupon_code
    session['discount'] = discount
    
    return jsonify({
        'success': True, 
        'message': f'{coupon.discount_percent}% kedvezmény alkalmazva',
        'discount': discount,
        'total': final_total
    })

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if request.method == "POST":
        user_cart = Cart.query.filter_by(user_id=current_user.id).first()
        cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all()
        
        if not cart_items:
            return redirect(url_for('cart'))
        
        shipping_cost = float(request.form.get('shipping_cost', 0))
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        city = request.form.get('city')
        country = request.form.get('country')
        postal_code = request.form.get('postal_code')
        
        total_price = sum(item.product.price * item.quantity for item in cart_items)
        
        discount = session.pop('discount', 0)
        final_total = total_price + shipping_cost - discount
        
        order = Order(
            user_id=current_user.id,
            total_price=final_total,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address=address,
            city=city,
            country=country,
            postal_code=postal_code,
            shipping_cost=shipping_cost,
            discount=discount
        )
        db.session.add(order)
        db.session.commit()
        
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price
            )
            db.session.add(order_item)
        
        CartItem.query.filter_by(cart_id=user_cart.id).delete()
        session.pop('coupon_code', None)
        db.session.commit()
        
        return redirect(url_for('order_success', order_id=order.id))
    
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()
    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all() if user_cart else []
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    return render_template("checkout.html", cart_items=cart_items, total=total)

@app.route("/order-success/<int:order_id>")
@login_required
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        return redirect(url_for('home'))
    return render_template("order_success.html", order=order, timedelta=timedelta)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        passwd = request.form.get("passwd")
        
        user = User.query.filter_by(email=email).first()
        if user and user.valid_passwd(passwd):
            login_user(user)
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Érvénytelen email vagy jelszó")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        passwd = request.form.get("passwd")
        passwd_confirm = request.form.get("passwd_confirm")
        
        if passwd != passwd_confirm:
            return render_template("register.html", error="A jelszavak nem egyeznek")
        
        if User.query.filter_by(email=email).first():
            return render_template("register.html", error="Ez az email már regisztrálva van")
        
        user = User(username=username, email=email)
        user.set_passwd(passwd)
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        subject = request.form.get("subject")
        message = request.form.get("message")
        
        print(f"Új üzenet: {name} - {email} - {subject}")
        
    return render_template("contact.html")

# ==================== ADMIN ROUTES ====================

@app.route("/admin")
@admin_required
def admin_dashboard():
    products_count = Product.query.count()
    users_count = User.query.count()
    orders_count = Order.query.count()
    return render_template("admin_dashboard.html", 
                         products_count=products_count,
                         users_count=users_count,
                         orders_count=orders_count)

@app.route("/admin/products")
@admin_required
def admin_products():
    page = request.args.get('page', 1, type=int)
    products = Product.query.paginate(page=page, per_page=10)
    return render_template("admin_products.html", products=products)

@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def add_product():
    if request.method == "POST":
        try:
            name = request.form.get("name")
            model = request.form.get("model")
            price = float(request.form.get("price"))
            category = request.form.get("category")
            description = request.form.get("description")
            stock = int(request.form.get("stock", 0))
            discount = float(request.form.get("discount", 0))
            image_file = request.files.get("image")
            
            if not name or not price or not category:
                flash("A név, ár és kategória kötelező!", "danger")
                return redirect(url_for("add_product"))
            
            image_path = ""
            if image_file and image_file.filename:
                if not allowed_file(image_file.filename):
                    flash("Csak PNG, JPG, JPEG és GIF fájlok engedélyezettek!", "danger")
                    return redirect(url_for("add_product"))
                
                filename = secure_filename(image_file.filename)
                filename = f"{datetime.utcnow().timestamp()}_{filename}"
                image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_path = f"uploads/{filename}"
            
            product = Product(
                name=name,
                model=model,
                price=price,
                category=category,
                description=description,
                image=image_path,
                stock=stock,
                discount=discount
            )
            db.session.add(product)
            db.session.commit()
            
            flash("Termék sikeresen hozzáadva!", "success")
            return redirect(url_for("admin_products"))
        
        except Exception as e:
            flash(f"Hiba történt: {str(e)}", "danger")
            return redirect(url_for("add_product"))
    
    return render_template("add_product.html")

@app.route("/admin/products/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == "POST":
        try:
            product.name = request.form.get("name")
            product.model = request.form.get("model")
            product.price = float(request.form.get("price"))
            product.category = request.form.get("category")
            product.description = request.form.get("description")
            product.stock = int(request.form.get("stock", 0))
            product.discount = float(request.form.get("discount", 0))
            
            image_file = request.files.get("image")
            if image_file and image_file.filename:
                if not allowed_file(image_file.filename):
                    flash("Csak PNG, JPG, JPEG és GIF fájlok engedélyezettek!", "danger")
                    return redirect(url_for("edit_product", product_id=product_id))
                
                # Régi kép törlése
                if product.image and os.path.exists(os.path.join("static", product.image)):
                    os.remove(os.path.join("static", product.image))
                
                filename = secure_filename(image_file.filename)
                filename = f"{datetime.utcnow().timestamp()}_{filename}"
                image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image = f"uploads/{filename}"
            
            db.session.commit()
            flash("Termék sikeresen frissítve!", "success")
            return redirect(url_for("admin_products"))
        
        except Exception as e:
            flash(f"Hiba történt: {str(e)}", "danger")
            return redirect(url_for("edit_product", product_id=product_id))
    
    return render_template("edit_product.html", product=product)

@app.route("/admin/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    try:
        # Kép törlése
        if product.image and os.path.exists(os.path.join("static", product.image)):
            os.remove(os.path.join("static", product.image))
        
        db.session.delete(product)
        db.session.commit()
        flash("Termék sikeresen törölve!", "success")
    except Exception as e:
        flash(f"Hiba történt: {str(e)}", "danger")
    
    return redirect(url_for("admin_products"))

@app.route("/set_admin")
@login_required
def set_damin():
    user = User.query.get(current_user.id)
    user.is_admin = True
    db.session.commit()
    

# ==================== API ROUTES ====================

@app.route("/api/products")
def api_products():
    products = Product.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'category': p.category,
        'image': p.image
    } for p in products])

@app.route("/api/cart", methods=["GET"])
@login_required
def api_cart():
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not user_cart:
        return jsonify([])
    
    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all()
    return jsonify([{
        'id': item.id,
        'product_id': item.product_id,
        'product_name': item.product.name,
        'price': item.product.price,
        'quantity': item.quantity,
        'total': item.product.price * item.quantity
    } for item in cart_items])

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)