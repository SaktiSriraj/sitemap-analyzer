import random
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def extract_sitemap(url):
    """
    Extract URLs from a website's XML sitemap.
    
    Args:
        url (str): The base URL of the website (domain name)
        
    Returns:
        list: A list of URLs found in the sitemap
    """
    # List of common user agents to rotate
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
    ]
    
    # Ensure URL has proper schema
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Get the base domain
    parsed_url = urlparse(url)
    base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    # Common sitemap paths to try
    sitemap_paths = [
        '/sitemap.xml',
        '/sitemaps.xml',
        '/sitemap_index.xml',
        '/sitemap-index.xml',
        '/sitemap1.xml',
        '/post-sitemap.xml',
        '/page-sitemap.xml',
        '/sitemap/sitemap.xml'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    all_urls = []
    sitemap_found = False
    
    # First try robots.txt to find sitemap
    try:
        robots_url = f"{base_domain}/robots.txt"
        response = requests.get(robots_url, timeout=10, headers=headers)
        
        if response.status_code == 200:
            # Look for Sitemap: directive in robots.txt
            for line in response.text.split('\n'):
                if line.lower().startswith('sitemap:'):
                    sitemap_url = line.split(':', 1)[1].strip()
                    print(f"Found sitemap in robots.txt: {sitemap_url}")
                    
                    # Process this sitemap
                    urls = process_sitemap(sitemap_url, headers)
                    if urls:
                        all_urls.extend(urls)
                        sitemap_found = True
    except Exception as e:
        print(f"Error checking robots.txt: {str(e)}")
    
    # If no sitemap found in robots.txt, try common locations
    if not sitemap_found:
        for path in sitemap_paths:
            try:
                sitemap_url = f"{base_domain}{path}"
                print(f"Trying sitemap at: {sitemap_url}")
                
                urls = process_sitemap(sitemap_url, headers)
                if urls:
                    all_urls.extend(urls)
                    sitemap_found = True
                    break
            except Exception as e:
                print(f"Error checking {sitemap_url}: {str(e)}")
    
    # Return unique URLs
    return list(set(all_urls))

def process_sitemap(sitemap_url, headers):
    """
    Process a sitemap URL and extract all page URLs.
    Handles both regular sitemaps and sitemap indexes.
    
    Args:
        sitemap_url (str): URL of the sitemap to process
        headers (dict): HTTP headers to use for the request
        
    Returns:
        list: URLs found in the sitemap
    """
    urls = []
    
    try:
        response = requests.get(sitemap_url, timeout=15, headers=headers)
        response.raise_for_status()
        
        # Check if it's a sitemap index (contains other sitemaps)
        if '<sitemapindex' in response.text:
            # Parse as sitemap index
            root = ET.fromstring(response.content)
            
            # Define namespace mapping if needed
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Find all sitemap URLs in the index
            for sitemap in root.findall('.//sm:sitemap/sm:loc', ns) or root.findall('.//sitemap/loc'):
                child_sitemap_url = sitemap.text.strip()
                # Recursively process child sitemaps
                child_urls = process_sitemap(child_sitemap_url, headers)
                if child_urls:
                    urls.extend(child_urls)
                    
        # Process as regular sitemap
        elif '<urlset' in response.text:
            # Parse as regular sitemap
            root = ET.fromstring(response.content)
            
            # Define namespace mapping
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Find all page URLs
            for url_element in root.findall('.//sm:url/sm:loc', ns) or root.findall('.//url/loc'):
                page_url = url_element.text.strip()
                urls.append(page_url)
                
    except Exception as e:
        print(f"Error processing sitemap {sitemap_url}: {str(e)}")
    
    return urls