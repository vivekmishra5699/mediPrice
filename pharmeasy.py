import requests
from bs4 import BeautifulSoup
import random
import re
import json
import logging

def search_pharmeasy(encoded_query, query, user_agents, logger):
    pharmeasy_results = []
    try:
        # PharmEasy frequently changes their API/HTML structure, so we'll try multiple approaches
        
        # Approach 1: Direct API call
        api_url = f"https://pharmeasy.in/api/search/search?q={encoded_query}"
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json",
            "Referer": f"https://pharmeasy.in/search/all?name={encoded_query}"
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            try:
                data = response.json()
                if "data" in data and "products" in data["data"]:
                    # Get more results to filter for most bought/reviewed
                    all_products = []
                    
                    for product in data["data"]["products"][:10]:
                        try:
                            title = product.get("name", "Unknown Product")
                            slug = product.get("slug", "")
                            mrp = product.get("mrp", 0)
                            sale_price = product.get("salePrice", mrp)
                            discount = product.get("discountPercent", 0)
                            ratings = product.get("ratingCount", 0) or 0
                            popularity = product.get("popularity", 0) or 0
                            
                            link = f"https://pharmeasy.in/online-medicine-order/{slug}"
                            price = f"₹{sale_price}"
                            if discount > 0:
                                price = f"₹{sale_price}*MRP₹{mrp}Save {discount}%"
                            else:
                                price = f"MRP₹{mrp}*"
                            
                            all_products.append({
                                "source": "PharmEasy",
                                "title": title,
                                "link": link,
                                "price": price,
                                "raw_price": float(sale_price),
                                "ratings": ratings,
                                "popularity": popularity
                            })
                        except Exception:
                            continue
                    
                    # Sort by popularity and ratings to get most bought/reviewed products
                    all_products.sort(key=lambda x: (x.get("popularity", 0) + x.get("ratings", 0)), reverse=True)
                    
                    # Take the top 5 most popular products
                    pharmeasy_results = all_products[:5]
                    
                    # Strip out the metrics we added for sorting
                    for product in pharmeasy_results:
                        if "ratings" in product:
                            del product["ratings"]
                        if "popularity" in product:
                            del product["popularity"]
                    
            except ValueError:
                logger.warning("Failed to parse PharmEasy API response as JSON")
        else:
            logger.warning(f"PharmEasy API returned status code: {response.status_code}")
        
        # Approach 2: Fallback to HTML scraping if API failed
        if not pharmeasy_results or all(result.get("price") == "Price not available" for result in pharmeasy_results):
            search_url = f"https://pharmeasy.in/search/all?name={encoded_query}&sort_by=popularity"
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept": "text/html",
                "Cache-Control": "no-cache"
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Look for JavaScript data in the page that might contain product information
                html_content = response.text
                
                # Extract product data from any embedded JavaScript
                json_data_matches = re.findall(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html_content)
                if json_data_matches:
                    try:
                        json_data = json.loads(json_data_matches[0])
                        # Extract product data from the state
                        if 'search' in json_data and 'products' in json_data['search']:
                            products = json_data['search']['products']
                            all_products = []
                            
                            for product in products[:10]:
                                try:
                                    title = product.get('name', 'Unknown Product')
                                    mrp = product.get('mrp')
                                    sale_price = product.get('salePrice', mrp)
                                    discount = product.get('discountPercent', 0)
                                    slug = product.get('slug', '')
                                    ratings = product.get("ratingCount", 0) or 0
                                    popularity = product.get("popularity", 0) or 0
                                    
                                    link = f"https://pharmeasy.in/online-medicine-order/{slug}"
                                    price = f"₹{sale_price}"
                                    if discount > 0:
                                        price = f"₹{sale_price}*MRP₹{mrp}Save {discount}%"
                                    else:
                                        price = f"MRP₹{mrp}*"
                                        
                                    raw_price = float(sale_price) if sale_price else float(mrp) if mrp else 0
                                    
                                    all_products.append({
                                        "source": "PharmEasy",
                                        "title": title,
                                        "link": link,
                                        "price": price,
                                        "raw_price": raw_price,
                                        "ratings": ratings,
                                        "popularity": popularity
                                    })
                                except Exception as e:
                                    logger.error(f"Error processing embedded product data: {str(e)}")
                                    continue
                                    
                            # Sort by popularity and ratings to get most bought/reviewed products
                            all_products.sort(key=lambda x: (x.get("popularity", 0) + x.get("ratings", 0)), reverse=True)
                            
                            # Take the top 5 most popular products
                            pharmeasy_results = all_products[:5]
                            
                            # Strip out the metrics we added for sorting
                            for product in pharmeasy_results:
                                if "ratings" in product:
                                    del product["ratings"]
                                if "popularity" in product:
                                    del product["popularity"]
                    except Exception as e:
                        logger.error(f"Error parsing embedded JSON: {str(e)}")
                
                # If no results from embedded JSON, try traditional scraping
                if not pharmeasy_results:
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # Try to find the updated CSS selectors
                    product_cards = soup.select("[data-test='product-card'], .ProductCard_productCard__OXwT6, .ProductCard_medicineCard__8kZBB, .ProductCard_productCardWrapper__Emr18, div[class*='ProductCard_']")
                    
                    # If still no results, try more general approach
                    if not product_cards:
                        product_cards = soup.select("div[class*='card'], div[class*='Card'], div[data-test*='product']")
                    
                    # Process found cards with advanced price detection
                    all_products = []
                    for card in product_cards:
                        try:
                            # Try multiple approaches to find the title
                            title_elem = card.select_one("h2, h3, div[class*='name'], div[class*='title'], div[class*='Name'], div[class*='Title']")
                            if not title_elem:
                                title_elem = card.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'p'] and tag.get_text(strip=True))
                            
                            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
                            
                            # Multiple approaches to find price
                            price = "Price not available"
                            
                            # Method 1: Look for specific price classes
                            price_elem = card.select_one("div[class*='Price'], span[class*='Price'], div[class*='price'], span[class*='price'], div[class*='MRP'], span[class*='MRP'], div[class*='_sale'], span[class*='_sale'], div[class*='final'], span[class*='final']")
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                            
                            # Method 2: Search for rupee symbol (₹)
                            if price == "Price not available":
                                rupee_elems = card.find_all(string=lambda s: s and "₹" in s)
                                if rupee_elems:
                                    price = rupee_elems[0].strip()
                            
                            # Method 3: Check for HTML attributes that might contain price
                            if price == "Price not available":
                                for elem in card.select("[data-price], [data-mrp], [data-saleprice], [data-value]"):
                                    for attr in ['data-price', 'data-mrp', 'data-saleprice', 'data-value']:
                                        if attr in elem.attrs:
                                            try:
                                                price_val = float(elem[attr])
                                                price = f"₹{price_val}"
                                                break
                                            except:
                                                pass
                            
                            # Try to find ratings/reviews
                            ratings = 0
                            rating_elem = card.select_one("div[class*='rating'], span[class*='rating'], div[class*='Rating'], span[class*='Rating']")
                            if rating_elem:
                                rating_text = rating_elem.get_text(strip=True)
                                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                                if rating_match:
                                    try:
                                        ratings = float(rating_match.group(1))
                                    except ValueError:
                                        ratings = 0
                            
                            # Check for review count
                            reviews = 0
                            review_elem = card.select_one("div[class*='review'], span[class*='review'], div[class*='Review'], span[class*='Review']")
                            if review_elem:
                                review_text = review_elem.get_text(strip=True)
                                review_match = re.search(r'(\d+)', review_text)
                                if review_match:
                                    try:
                                        reviews = int(review_match.group(1))
                                    except ValueError:
                                        reviews = 0
                            
                            # Format price like the examples if we have MRP and discount info
                            mrp_match = re.search(r'MRP:?\s*₹?(\d+\.?\d*)', price) or re.search(r'MRP:?\s*₹?(\d+\.?\d*)', card.get_text())
                            price_match = re.search(r'₹(\d+\.?\d*)', price)
                            discount_match = re.search(r'(\d+)%\s*off', price) or re.search(r'(\d+)%\s*off', card.get_text())
                            
                            if price_match and mrp_match:
                                sale_price = float(price_match.group(1))
                                mrp = float(mrp_match.group(1))
                                discount = int(discount_match.group(1)) if discount_match else round((1 - sale_price/mrp) * 100)
                                
                                if discount > 0:
                                    price = f"₹{sale_price}*MRP₹{mrp}Save {discount}%"
                                else:
                                    price = f"MRP₹{mrp}*"
                            
                            # Try to find link
                            link = "#"
                            link_elem = card.select_one("a")
                            if link_elem and link_elem.has_attr("href"):
                                link = link_elem["href"]
                                if link.startswith("/"):
                                    link = f"https://pharmeasy.in{link}"
                            else:
                                # Try to construct link from product data
                                product_id = None
                                for attr in card.attrs:
                                    if "id" in attr.lower() and card[attr]:
                                        product_id = card[attr]
                                        break
                                
                                if product_id:
                                    # Try to generate slug from title
                                    slug = title.lower().replace(" ", "-")
                                    link = f"https://pharmeasy.in/online-medicine-order/{slug}"
                                else:
                                    continue  # Skip if no valid link can be found
                            
                            # Parse raw price for sorting
                            raw_price = 0
                            if price != "Price not available":
                                # Extract digits and decimal from price string
                                price_text = re.search(r'₹(\d+\.?\d*)', price)
                                if price_text:
                                    try:
                                        raw_price = float(price_text.group(1))
                                    except ValueError:
                                        raw_price = 0
                            
                            # If price still not found, use alternate approach to estimate price
                            if price == "Price not available":
                                # Try to find the price from title or other elements if it includes price info
                                title_price = re.search(r'(?:Rs\.?|₹|INR)\s*(\d+\.?\d*)', title)
                                if title_price:
                                    price = f"₹{title_price.group(1)}"
                                    try:
                                        raw_price = float(title_price.group(1))
                                    except ValueError:
                                        raw_price = 0
                                else:
                                    # Use a default price as a last resort
                                    price = "MRP₹--*"
                            
                            popularity_score = ratings * 2 + reviews  # Give more weight to ratings
                            
                            all_products.append({
                                "source": "PharmEasy",
                                "title": title,
                                "link": link,
                                "price": price,
                                "raw_price": raw_price,
                                "popularity": popularity_score
                            })
                        except Exception as e:
                            logger.error(f"Error processing PharmEasy product card: {str(e)}")
                            continue
                    
                    # Sort by popularity score
                    all_products.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                    
                    # Take top 5 products
                    pharmeasy_results = all_products[:5]
                    
                    # Remove sorting fields
                    for product in pharmeasy_results:
                        if "popularity" in product:
                            del product["popularity"]
                    
                    # If still no results, try even more general scraping as last resort
                    if not pharmeasy_results:
                        all_products = []
                        
                        # Find all links that look like product links
                        for link in soup.select("a"):
                            href = link.get("href", "")
                            if "/online-medicine-order/" in href or "product-details" in href:
                                product_text = link.get_text(strip=True)
                                if product_text:
                                    all_products.append({
                                        "title": product_text,
                                        "link": href if href.startswith("http") else f"https://pharmeasy.in{href}"
                                    })
                        
                        # Try to find prices near each product
                        scored_products = []
                        for product in all_products[:10]:  # Process more to find best ones
                            price_found = False
                            price = "MRP₹--*"
                            
                            # Scrape the product page directly for price
                            try:
                                product_response = requests.get(
                                    product["link"], 
                                    headers={"User-Agent": random.choice(user_agents)},
                                    timeout=5
                                )
                                
                                if product_response.status_code == 200:
                                    product_soup = BeautifulSoup(product_response.text, 'html.parser')
                                    
                                    # Look for price on product page
                                    price_elem = product_soup.select_one("div[class*='Price'], span[class*='Price'], div[class*='price'], span[class*='price'], div[class*='MRP'], span[class*='MRP']")
                                    if price_elem:
                                        price = price_elem.get_text(strip=True)
                                        price_found = True
                                    
                                    if not price_found:
                                        # Look for rupee symbol
                                        rupee_elems = product_soup.find_all(string=lambda s: s and "₹" in s)
                                        if rupee_elems:
                                            price = rupee_elems[0].strip()
                                            price_found = True
                                    
                                    # Try to extract structured price info
                                    mrp_match = re.search(r'MRP:?\s*₹?(\d+\.?\d*)', price) or re.search(r'MRP:?\s*₹?(\d+\.?\d*)', product_soup.get_text())
                                    price_match = re.search(r'₹(\d+\.?\d*)', price)
                                    discount_match = re.search(r'(\d+)%\s*off', price) or re.search(r'(\d+)%\s*off', product_soup.get_text())
                                    
                                    if price_match and mrp_match:
                                        sale_price = float(price_match.group(1))
                                        mrp = float(mrp_match.group(1))
                                        discount = int(discount_match.group(1)) if discount_match else round((1 - sale_price/mrp) * 100)
                                        
                                        if discount > 0:
                                            price = f"₹{sale_price}*MRP₹{mrp}Save {discount}%"
                                        else:
                                            price = f"MRP₹{mrp}*"
                                    
                                    # Look for ratings and reviews to score products
                                    ratings = 0
                                    reviews = 0
                                    
                                    # Rating elements
                                    rating_elem = product_soup.select_one("div[class*='rating'], span[class*='rating'], div[class*='Rating'], span[class*='Rating']")
                                    if rating_elem:
                                        rating_text = rating_elem.get_text(strip=True)
                                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                                        if rating_match:
                                            try:
                                                ratings = float(rating_match.group(1))
                                            except ValueError:
                                                ratings = 0
                                    
                                    # Review count elements
                                    review_elem = product_soup.select_one("div[class*='review'], span[class*='review'], div[class*='Review'], span[class*='Review']")
                                    if review_elem:
                                        review_text = review_elem.get_text(strip=True)
                                        review_match = re.search(r'(\d+)', review_text)
                                        if review_match:
                                            try:
                                                reviews = int(review_match.group(1))
                                            except ValueError:
                                                reviews = 0
                                    
                                    # Score by ratings and reviews
                                    popularity_score = ratings * 2 + reviews
                            except Exception as e:
                                logger.error(f"Error fetching product page: {str(e)}")
                                popularity_score = 0
                            
                            # Extract raw price for sorting
                            raw_price = 0
                            if price != "MRP₹--*":
                                price_text = re.search(r'₹(\d+\.?\d*)', price)
                                if price_text:
                                    try:
                                        raw_price = float(price_text.group(1))
                                    except ValueError:
                                        raw_price = 0
                            
                            scored_products.append({
                                "source": "PharmEasy",
                                "title": product["title"],
                                "link": product["link"],
                                "price": price,
                                "raw_price": raw_price,
                                "popularity": popularity_score
                            })
                        
                        # Sort by popularity
                        scored_products.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                        
                        # Take top 5
                        for product in scored_products[:5]:
                            if "popularity" in product:
                                del product["popularity"]
                            pharmeasy_results.append(product)
                
                # Limit the results
                pharmeasy_results = pharmeasy_results[:5]
    except Exception as e:
        logger.error(f"PharmEasy search error: {str(e)}")
    
    return pharmeasy_results