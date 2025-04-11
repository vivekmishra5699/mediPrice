from flask import Flask, render_template, request, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import os
import logging
from urllib.parse import quote_plus, urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Import scraping functions from separate files
from pharmeasy import search_pharmeasy
from tata1mg import search_tata1mg
from amazon import search_amazon
from medicine_routine import medicine_bp


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['DATABASE'] = 'database.db'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.register_blueprint(medicine_bp)
def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

class User(UserMixin):
    def __init__(self, id, username, password, name, age):
        self.id = id
        self.username = username
        self.password = password
        self.name = name
        self.age = age

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        return User(user['id'], user['username'], user['password'], user['name'], user['age'])
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['password'], user['name'], user['age'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        age = request.form['age']
        
        db = get_db()
        error = None
        
        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif not name:
            error = 'Name is required.'
        elif not age or not age.isdigit():
            error = 'Valid age is required.'
        elif int(age) < 1 or int(age) > 120:
            error = 'Please enter a valid age between 1 and 120.'
        
        if error is None:
            try:
                db.execute(
                    "INSERT INTO users (username, password, name, age) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), name, age),
                )
                db.commit()
                flash('Registration successful! Please log in.')
                return redirect(url_for('login'))
            except db.IntegrityError:
                error = f"User {username} is already registered."
        
        flash(error)
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's recent searches
    recent_searches = []
    try:
        db = get_db()
        recent_searches = db.execute(
            """SELECT query, search_date, results_count 
               FROM search_history 
               WHERE user_id = ? 
               ORDER BY search_date DESC LIMIT 5""",
            (current_user.id,)
        ).fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch recent searches: {str(e)}")
    
    # Add the current datetime for use in the template
    from datetime import datetime
    now = datetime.now()
    
    return render_template('dashboard.html', user=current_user, recent_searches=recent_searches, now=now)
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def search_medicine(query):
    """
    Multi-source medicine search that returns only real results.
    """
    results = []
    encoded_query = quote_plus(query)
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    
    search_history_id = None
    try:
        db = get_db()
        if current_user and hasattr(current_user, 'id'):
            cursor = db.execute(
                "INSERT INTO search_history (user_id, query) VALUES (?, ?)",
                (current_user.id, query)
            )
            search_history_id = cursor.lastrowid
            db.commit()
    except Exception as e:
        logger.error(f"Failed to log search history: {str(e)}")
    
    all_sources = [
        {"name": "PharmEasy", "function": search_pharmeasy},
        {"name": "Tata 1mg", "function": search_tata1mg},
        {"name": "Amazon", "function": search_amazon}
    ]
    
    for source in all_sources:
        try:
            source_results = source["function"](encoded_query, query, user_agents, logger)
            if source_results:
                results.extend(source_results)
            logger.info(f"Found {len(source_results)} results from {source['name']}")
        except Exception as e:
            logger.error(f"Error searching {source['name']}: {str(e)}")
    
    # Update results count in search history
    if search_history_id:
        try:
            db = get_db()
            db.execute(
                "UPDATE search_history SET results_count = ? WHERE id = ?",
                (len(results), search_history_id)
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update search history results count: {str(e)}")
    
    logger.info(f"Returning {len(results)} real results")
    return results

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    if request.method == 'POST':
        query = request.form.get('query', '')
        if not query:
            flash('Please enter a medicine name')
            return redirect(url_for('dashboard'))
        
        # Save search to history (option for future enhancement)
        
        # Search for medicines
        results = search_medicine(query)
        return render_template('search_results.html', query=query, results=results)
    
    # Handle GET requests - this supports the clickable popular searches
    query = request.args.get('query', '')
    if query:
        results = search_medicine(query)
        return render_template('search_results.html', query=query, results=results)
    
    # If no query and GET request, redirect to dashboard
    return redirect(url_for('dashboard'))
@app.route('/clear_search_history')
@login_required
def clear_search_history():
    try:
        db = get_db()
        db.execute("DELETE FROM search_history WHERE user_id = ?", (current_user.id,))
        db.commit()
        flash("Search history cleared successfully")
    except Exception as e:
        logger.error(f"Failed to clear search history: {str(e)}")
        flash("Failed to clear search history")
    
    return redirect(url_for('dashboard'))
@app.route('/product_details')
@login_required
def product_details():
    product_url = request.args.get('url', '')
    source = request.args.get('source', '')
    if not product_url or not source:
        flash('Invalid product URL or source')
        return redirect(url_for('search'))
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html"
        }
        response = requests.get(product_url, headers=headers, timeout=15)
        if response.status_code != 200:
            flash(f"Failed to fetch product details from {source}. Status code: {response.status_code}")
            return redirect(url_for('search'))
        soup = BeautifulSoup(response.text, 'html.parser')
        product_name = "Product Name"
        product_price = "Price not available"
        product_image = None
        product_description = "No description available"
        
        if source == "PharmEasy":
            # Enhanced selectors for PharmEasy
            product_name_elem = soup.select_one(".MedicineOverviewSection_medicineName__dHDQZ, h1.ProductTitle_product-title__OkCXo, h1[class*='product-title'], h1[class*='medicineName'], .medicine-name, .product-title")
            if product_name_elem:
                product_name = product_name_elem.get_text(strip=True)
            
            price_elem = soup.select_one(".PriceInfo_ourPrice__jFYXr, div[class*='Price'], span[class*='Price'], div[class*='price'], span[class*='price'], div[class*='MRP'], span[class*='MRP']")
            if price_elem:
                product_price = price_elem.get_text(strip=True)
            else:
                # Fallback: look for any element containing the rupee symbol
                rupee_elems = soup.find_all(string=lambda s: s and "₹" in s)
                if rupee_elems:
                    product_price = rupee_elems[0].strip()
            
            img_elem = soup.select_one(".ProductImageCarousel_carousel-img__cJgkZ, .style__image___Sd7O3, img[class*='product'], img[class*='medicine'], .product-image img, .medicine-image img")
            if img_elem:
                product_image = img_elem.get("src")
            
            desc_elem = soup.select_one(".ProductDescription_product-description__gAYip, .MedicineOverviewSection_medicineOverview__yR8HD, div[class*='description'], div[class*='overview'], div[class*='details'], .product-details")
            if desc_elem:
                product_description = desc_elem.get_text(strip=True)
        
        elif source == "Tata 1mg":
            # Enhanced selectors for Tata 1mg
            product_name_elem = soup.select_one(".DrugHeader__title___2ZZX_ h1, .ProductTitle__product-title___3QMYH, h1[class*='title'], h1[class*='name'], div.DrugHeader__title-content___2ZZX_")
            if product_name_elem:
                product_name = product_name_elem.get_text(strip=True)
            
            price_elem = soup.select_one(".PriceBoxPlanOption__offer-price___3v_Nd, .ProductPriceBox__price___11Tjr, div[class*='price'], span[class*='price'], div[class*='offer-price']")
            if price_elem:
                product_price = price_elem.get_text(strip=True)
            else:
                rupee_elems = soup.find_all(string=lambda s: s and "₹" in s)
                if rupee_elems:
                    product_price = rupee_elems[0].strip()
            
            img_elem = soup.select_one(".ProductImage__image-container___2_MWm img, .style__image-container___2G57K img, img[class*='product'], img.style__product-image___1bkbA")
            if img_elem:
                product_image = img_elem.get("src")
            
            desc_elem = soup.select_one(".ProductDescription_description-content___A_qCZ, .DrugOverview__content___2ZZX_, div[class*='description'], div[class*='overview']")
            if desc_elem:
                product_description = desc_elem.get_text(strip=True)
        
        elif source == "Amazon":
            # Enhanced selectors for Amazon
            product_name_elem = (soup.select_one("#productTitle, #title, h1") or soup.select_one("title"))
            if product_name_elem:
                product_name = product_name_elem.get_text(strip=True)
                if "Amazon.in" in product_name:
                    product_name = product_name.split(":", 1)[0].strip()
            
            price_elem = (
                soup.select_one(".a-price .a-offscreen") or 
                soup.select_one(".a-price") or 
                soup.select_one("#priceblock_ourprice") or
                soup.select_one("#priceblock_dealprice") or
                soup.select_one("#priceblock_saleprice")
            )
            if price_elem:
                product_price = price_elem.get_text(strip=True)
            else:
                # Try to find any element with a rupee symbol
                rupee_elems = soup.find_all(string=lambda s: s and "₹" in s)
                if rupee_elems:
                    product_price = rupee_elems[0].strip()
            
            img_elem = (
                soup.select_one("#landingImage") or 
                soup.select_one("#imgBlkFront") or
                soup.select_one("img[id*='image'], img[data-old-hires]") or 
                soup.select_one("img[src*='product'], img[src*='large']") or 
                soup.select_one("img")
            )
            if img_elem:
                # Get the best quality image URL from Amazon
                product_image = img_elem.get("data-old-hires") or img_elem.get("src")
            
            desc_elem = (
                soup.select_one("#productDescription") or
                soup.select_one("#feature-bullets") or
                soup.select_one(".product-description") or
                soup.select_one("[id$='-description']")
            )
            if desc_elem:
                product_description = desc_elem.get_text(strip=True)
        
        # Generic fallbacks for missing data
        if not product_name or product_name == "Product Name":
            title_elem = (soup.select_one("h1") or soup.select_one("title"))
            if title_elem:
                product_name = title_elem.get_text(strip=True)
        
        if not product_image:
            img_elem = (soup.select_one("img[src*='product'], img[src*='large']") or soup.select_one("img"))
            if img_elem:
                product_image = img_elem.get("src")
                if product_image and not product_image.startswith(("http://", "https://")):
                    parsed_url = urlparse(product_url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    product_image = base_url + product_image if not product_image.startswith("/") else base_url + product_image
        
        # Try to extract better descriptions
        if product_description == "No description available" or len(product_description) < 50:
            # Look for any other elements that might contain descriptions
            for selector in ["meta[name='description']", "meta[property='og:description']", ".product-description", 
                           "[class*='description']", "[class*='info']", "[class*='detail']"]:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    if selector.startswith("meta"):
                        content = desc_elem.get("content", "")
                        if content and len(content) > len(product_description):
                            product_description = content
                    else:
                        text = desc_elem.get_text(strip=True)
                        if text and len(text) > len(product_description):
                            product_description = text
                    
                    if product_description != "No description available" and len(product_description) > 50:
                        break
        
        # Get current time for the "Last Updated" field
        current_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        
        return render_template('product_details.html',
                               product_name=product_name,
                               product_price=product_price,
                               product_image=product_image,
                               product_description=product_description,
                               source=source,
                               original_url=product_url,
                               current_time=current_time,
                               simulated=False)
    except Exception as e:
        logger.error(f"Error fetching product details: {str(e)}")
        # Try to use simulated_product as fallback
        try:
            return redirect(url_for('simulated_product', 
                                   url=product_url, 
                                   source=source, 
                                   title=request.args.get('title', ''),
                                   price=request.args.get('price', '')))
        except:
            flash(f"Failed to fetch product details: {str(e)}")
            return redirect(url_for('search'))

@app.route('/simulated_product')
@login_required
def simulated_product():
    url = request.args.get('url', '')
    source = request.args.get('source', '')
    title = request.args.get('title', '')
    price = request.args.get('price', '')
    if not title or not price:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            title = query_params.get('title', ['Unknown Product'])[0]
            price = query_params.get('price', ['Price not available'])[0]
            source = query_params.get('source', [source])[0]
        except Exception as e:
            logger.error(f"Error parsing simulated product URL: {str(e)}")
            title = "Unknown Product"
            price = "Price not available"
    product_name = title
    product_price = price
    placeholder_image_path = os.path.join(app.static_folder, 'images', 'placeholder.jpg')
    if os.path.exists(placeholder_image_path):
        product_image = "/static/images/placeholder.jpg"
    else:
        product_image = ("data:image/svg+xml;charset=UTF-8,"
                         "%3Csvg%20width%3D%22300%22%20height%3D%22300%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20300%20300%22%20preserveAspectRatio%3D%22none%22%3E"
                         "%3Cdefs%3E%3Cstyle%20type%3D%22text%2Fcss%22%3E%23holder_18d70640659%20text%20%7B%20fill%3A%23999%3Bfont-weight%3Anormal%3Bfont-family%3AArial%2C%20Helvetica%2C%20sans-serif%3Bfont-size%3A15pt%20%7D%20%3C%2Fstyle%3E%3C%2Fdefs%3E"
                         "%3Cg%20id%3D%22holder_18d70640659%22%3E%3Crect%20width%3D%22300%22%20height%3D%22300%22%20fill%3D%22%23E5E5E5%22%3E%3C%2Frect%3E%3Cg%3E%3Ctext%20x%3D%22110.5%22%20y%3D%22157.1%22%3ENo%20Image%3C%2Ftext%3E%3C%2Fg%3E%3C%2Fg%3E%3C%2Fsvg%3E")
    product_description = f"This is a simulated product for demonstration purposes. The {title} would typically be available from {source}. Detailed information would include dosage, composition, uses, side effects, and more. Please visit the actual pharmacy website for complete information."
    return render_template('product_details.html',
                           product_name=product_name,
                           product_price=product_price,
                           product_image=product_image,
                           product_description=product_description,
                           source=source,
                           current_time=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
                           simulated=True)

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        init_db()
    if not os.path.exists('logs'):
        os.makedirs('logs')
    app.run(debug=True)