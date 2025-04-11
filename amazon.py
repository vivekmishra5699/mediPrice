import requests
from bs4 import BeautifulSoup
import random
import re
import json
import time

def search_amazon(encoded_query, query, user_agents, logger):
    amazon_results = []
    try:
        amazon_url = f"https://www.amazon.in/s?k={encoded_query}+medicine&s=relevanceblender"
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        
        response = requests.get(amazon_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for embedded JSON data first (more reliable)
            script_data = None
            for script in soup.find_all("script", {"type": "text/javascript"}):
                if script.string and "asin" in script.string and "search-result" in script.string:
                    try:
                        json_matches = re.search(r'data\s*=\s*({.*?});', script.string, re.DOTALL)
                        if json_matches:
                            script_data = json.loads(json_matches.group(1))
                            break
                    except Exception as e:
                        logger.error(f"Error parsing script JSON: {str(e)}")
            
            if script_data and "asinMetadataResults" in script_data:
                metadata = script_data["asinMetadataResults"]
                found_products = []
                for asin, product_data in metadata.items():
                    try:
                        title = product_data.get("title", "Unknown Product")
                        link = f"https://www.amazon.in/dp/{asin}"
                        price_text = product_data.get("price", {}).get("displayString", "Price not available")
                        rating = product_data.get("averageStarRating", 0) or 0
                        review_count = product_data.get("reviewCount", 0) or 0
                        raw_price = 0
                        if price_text != "Price not available":
                            price_match = re.search(r'₹\s*(\d+[,\d]*\.?\d*)', price_text)
                            if price_match:
                                raw_price = float(price_match.group(1).replace(',', ''))
                        popularity = rating * (review_count or 1)
                        relevance_score = 0
                        medicine_terms = ["medicine", "tablet", "capsule", "syrup", "drug", "pharma", "health", "medical", "dose", "mg"]
                        lower_title = title.lower()
                        for term in medicine_terms:
                            if term in lower_title:
                                relevance_score += 10
                        if query.lower() in lower_title:
                            relevance_score += 50
                        found_products.append({
                            "source": "Amazon",
                            "title": title,
                            "link": link,
                            "price": price_text,
                            "raw_price": raw_price,
                            "popularity": popularity,
                            "relevance": relevance_score
                        })
                    except Exception as e:
                        logger.error(f"Error processing Amazon JSON data: {str(e)}")
                found_products.sort(key=lambda x: (x.get("relevance", 0) + x.get("popularity", 0)), reverse=True)
                for product in found_products[:5]:
                    product.pop("popularity", None)
                    product.pop("relevance", None)
                    amazon_results.append(product)
            
            if not amazon_results:
                product_cards = soup.select("[data-component-type='s-search-result'], .s-result-item")
                all_products = []
                for card in product_cards[:10]:
                    try:
                        sponsored_tag = card.select_one(".s-sponsored-label")
                        if sponsored_tag:
                            continue
                        title_elem = card.select_one("h2 a span") or card.select_one(".a-text-normal")
                        title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
                        lower_title = title.lower()
                        is_medicine = any(term in lower_title for term in ["medicine", "tablet", "capsule", "syrup", "drug", "pharma", "health", "medical", "dose", "mg"])
                        if not is_medicine and query.lower() not in lower_title:
                            continue
                        link_elem = card.select_one("h2 a") or card.select_one(".a-link-normal")
                        link = link_elem.get("href", "#") if link_elem else "#"
                        if link.startswith("/"):
                            link = "https://www.amazon.in" + link
                        price_elem = card.select_one(".a-price .a-offscreen") or card.select_one(".a-price")
                        price = price_elem.get_text(strip=True) if price_elem else "Price not available"
                        raw_price = 0
                        if price != "Price not available":
                            price_match = re.search(r'₹\s*(\d+[,\d]*\.?\d*)', price)
                            if price_match:
                                try:
                                    raw_price = float(price_match.group(1).replace(',', ''))
                                except ValueError:
                                    raw_price = 0
                        rating = 0
                        review_count = 0
                        rating_elem = card.select_one("i.a-icon-star-small, i.a-icon-star")
                        if rating_elem:
                            rating_text = rating_elem.get_text(strip=True)
                            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                            if rating_match:
                                try:
                                    rating = float(rating_match.group(1))
                                except ValueError:
                                    rating = 0
                        review_elem = card.select_one(".a-size-base.s-underline-text")
                        if review_elem:
                            review_text = review_elem.get_text(strip=True)
                            review_match = re.search(r'(\d+[,\d]*)', review_text)
                            if review_match:
                                try:
                                    review_count = int(review_match.group(1).replace(',', ''))
                                except ValueError:
                                    review_count = 0
                        popularity = rating * (review_count or 1)
                        relevance_score = 0
                        for term in ["medicine", "tablet", "capsule", "syrup", "drug", "pharma", "health", "medical", "dose", "mg"]:
                            if term in lower_title:
                                relevance_score += 10
                        if query.lower() in lower_title:
                            relevance_score += 50
                        prime_badge = card.select_one(".s-prime")
                        if prime_badge:
                            relevance_score += 5
                        all_products.append({
                            "source": "Amazon",
                            "title": title,
                            "link": link,
                            "price": price,
                            "raw_price": raw_price,
                            "popularity": popularity,
                            "relevance": relevance_score
                        })
                    except Exception as e:
                        logger.error(f"Error parsing Amazon product card: {str(e)}")
                        continue
                all_products.sort(key=lambda x: (x.get("relevance", 0) + x.get("popularity", 0)), reverse=True)
                for product in all_products[:5]:
                    product.pop("popularity", None)
                    product.pop("relevance", None)
                    amazon_results.append(product)
                
                if not amazon_results:
                    basic_results = []
                    for card in product_cards:
                        try:
                            title_elem = card.select_one("h2 a span") or card.select_one(".a-text-normal")
                            if not title_elem:
                                continue
                            title = title_elem.get_text(strip=True)
                            lower_title = title.lower()
                            if not (query.lower() in lower_title or any(term in lower_title for term in ["medicine", "tablet", "capsule", "syrup", "health"])):
                                continue
                            link_elem = card.select_one("h2 a") or card.select_one(".a-link-normal")
                            link = link_elem.get("href", "#") if link_elem else "#"
                            if link.startswith("/"):
                                link = "https://www.amazon.in" + link
                            price_elem = card.select_one(".a-price .a-offscreen") or card.select_one(".a-price")
                            price = price_elem.get_text(strip=True) if price_elem else "Price not available"
                            basic_results.append({
                                "source": "Amazon",
                                "title": title,
                                "link": link,
                                "price": price,
                                "raw_price": 0
                            })
                        except Exception:
                            continue
                    amazon_results.extend(basic_results[:5])
        else:
            logger.error(f"Amazon returned status code: {response.status_code}")
            try:
                fallback_url = f"https://www.amazon.in/s?field-keywords={encoded_query}+medicine"
                response = requests.get(fallback_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    product_cards = soup.select("[data-component-type='s-search-result'], .s-result-item")
                    for card in product_cards[:5]:
                        try:
                            title_elem = card.select_one("h2 a span") or card.select_one(".a-text-normal")
                            if not title_elem:
                                continue
                            title = title_elem.get_text(strip=True)
                            link_elem = card.select_one("h2 a") or card.select_one(".a-link-normal")
                            link = link_elem.get("href", "#") if link_elem else "#"
                            if link.startswith("/"):
                                link = "https://www.amazon.in" + link
                            price_elem = card.select_one(".a-price .a-offscreen") or card.select_one(".a-price")
                            price = price_elem.get_text(strip=True) if price_elem else "Price not available"
                            amazon_results.append({
                                "source": "Amazon",
                                "title": title,
                                "link": link,
                                "price": price,
                                "raw_price": 0
                            })
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Amazon fallback search error: {str(e)}")
    except Exception as e:
        logger.error(f"Amazon search error: {str(e)}")
    
    amazon_results = amazon_results[:5]
    return amazon_results