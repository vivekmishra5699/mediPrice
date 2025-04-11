import requests
from bs4 import BeautifulSoup
import random
import re
import json

def search_tata1mg(encoded_query, query, user_agents, logger):
    tata1mg_results = []
    try:
        # Use different sort parameters to get most bought/reviewed products
        tata1mg_url = f"https://www.1mg.com/search/all?name={encoded_query}&sort=popularity"
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html",
            "Cache-Control": "no-cache"
        }
        
        response = requests.get(tata1mg_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Try to extract data from script tags first - more reliable
            script_data = None
            for script in soup.find_all('script', type='application/json'):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and "data" in data:
                        script_data = data
                        break
                except:
                    pass
            
            # If we found structured data, use it
            if script_data and "data" in script_data and "products" in script_data["data"]:
                products = script_data["data"]["products"]
                all_products = []
                
                for product in products[:10]:  # Get more to sort by popularity
                    try:
                        title = product.get("name", "Unknown Product")
                        slug = product.get("slug", "")
                        mrp = product.get("mrp", 0)
                        price = product.get("price", mrp)
                        discount = product.get("discountPercent", 0)
                        rating = product.get("rating", 0) or 0
                        rating_count = product.get("ratingCount", 0) or 0
                        
                        link = f"https://www.1mg.com/{slug}"
                        price_text = f"₹{price}"
                        if discount > 0:
                            price_text = f"₹{price} (MRP: ₹{mrp}, {discount}% off)"
                        
                        # Calculate popularity score
                        popularity = rating * rating_count
                        
                        all_products.append({
                            "source": "Tata 1mg",
                            "title": title,
                            "link": link,
                            "price": price_text,
                            "raw_price": float(price),
                            "rating": rating,
                            "rating_count": rating_count,
                            "popularity": popularity
                        })
                    except Exception as e:
                        logger.error(f"Error parsing Tata 1mg product data: {str(e)}")
                
                # Sort by popularity (rating * number of ratings)
                all_products.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                
                # Take top 5 products
                for product in all_products[:5]:
                    # Remove rating fields before returning
                    if "rating" in product:
                        del product["rating"]
                    if "rating_count" in product:
                        del product["rating_count"]
                    if "popularity" in product:
                        del product["popularity"]
                    tata1mg_results.append(product)
            
            # Fallback to HTML scraping if API data not found
            if not tata1mg_results:
                # Try multiple selectors
                selectors = [
                    ".style__product-box___3oEU6", 
                    ".style__horizontal-card___1Zwmt",
                    ".style__product-grid___3ZQ7D div[data-auto-id='product-grid-card']"
                ]
                
                product_items = []
                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        product_items = items
                        break
                
                all_products = []
                
                for item in product_items[:10]:  # Get more to sort by ratings/popularity
                    try:
                        # Extract title
                        title_selectors = [
                            "[data-auto-id='product-name']", 
                            ".style__pro-title___3zxNC",
                            "a[title]", 
                            ".style__product-title___1Pst1"
                        ]
                        
                        title = "Unknown Product"
                        for selector in title_selectors:
                            title_elem = item.select_one(selector)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                if not title:
                                    title = title_elem.get("title", "Unknown Product")
                                break
                        
                        # Extract link
                        link_elem = item.select_one("a[href]")
                        link = link_elem.get("href", "#") if link_elem else "#"
                        if link != "#" and not link.startswith("http"):
                            link = "https://www.1mg.com" + link
                        
                        # Extract price
                        price_selectors = [
                            ".style__price-tag___B2csA", 
                            ".style__discount-price___25Bya"
                        ]
                        
                        price = "Price not available"
                        raw_price = 0
                        
                        for selector in price_selectors:
                            price_elem = item.select_one(selector)
                            if price_elem:
                                price_text = price_elem.get_text(strip=True)
                                price = price_text
                                try:
                                    # Extract numeric price
                                    raw_price = float(''.join(filter(lambda x: x.isdigit() or x == '.', price_text)))
                                except ValueError:
                                    raw_price = 0
                                break
                        
                        # Extract rating
                        rating = 0
                        rating_count = 0
                        
                        rating_elem = item.select_one(".style__rating___1T2L8, .style__rating-wrap___2oUm3")
                        if rating_elem:
                            rating_text = rating_elem.get_text(strip=True)
                            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                            if rating_match:
                                try:
                                    rating = float(rating_match.group(1))
                                except ValueError:
                                    rating = 0
                        
                        rating_count_elem = item.select_one(".style__rating-count___2oUm3")
                        if rating_count_elem:
                            count_text = rating_count_elem.get_text(strip=True)
                            count_match = re.search(r'(\d+)', count_text)
                            if count_match:
                                try:
                                    rating_count = int(count_match.group(1))
                                except ValueError:
                                    rating_count = 0
                        
                        # Calculate popularity score
                        popularity = rating * (rating_count or 1)  # Avoid multiply by 0
                        
                        all_products.append({
                            "source": "Tata 1mg",
                            "title": title,
                            "link": link,
                            "price": price,
                            "raw_price": raw_price,
                            "popularity": popularity
                        })
                    except Exception as e:
                        logger.error(f"Error parsing Tata 1mg product card: {str(e)}")
                        continue
                
                # Sort by popularity score
                all_products.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                
                # Take top 5 products
                for product in all_products[:5]:
                    if "popularity" in product:
                        del product["popularity"]
                    tata1mg_results.append(product)
        else:
            logger.error(f"Tata 1mg returned status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Tata 1mg search error: {str(e)}")
    
    return tata1mg_results