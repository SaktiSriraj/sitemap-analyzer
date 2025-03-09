import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import random

def extract_sitemap(url, max_retries=3):
    # Extract all navigable links from a website's homepage with retry logic.
    
    # List of common user agents to rotate
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
    ]
    
    for attempt in range(max_retries):
        try:
            # Ensure URL has proper schema
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Get the base domain
            parsed_url = urlparse(url)
            base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Select a random user agent
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Fetch the homepage with increased timeout
            response = requests.get(url, timeout=20, headers=headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links
            links = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                
                # Skip empty links, fragments, and javascript links
                if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue
                
                # Convert relative URLs to absolute
                full_url = urljoin(base_domain, href)
                
                # Only include links from the same domain
                if urlparse(full_url).netloc == parsed_url.netloc:
                    links.add(full_url)
            
            return list(links)
            
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}/{max_retries} failed for {url}: {str(e)}")
            
            # If it's the last attempt, re-raise the exception
            if attempt == max_retries - 1:
                print(f"Error extracting sitemap from {url}: {str(e)}")
                return []
            
            # Wait before next attempt with exponential backoff
            time.sleep(2 ** attempt)
            
        except Exception as e:
            print(f"Unexpected error scraping {url}: {str(e)}")
            return []