import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
from urllib.parse import urljoin, urlparse
import time

def extract_xml_sitemap(url, max_total_time=25):
    """
    Extract URLs from a website's XML sitemap with improved timeout handling.
    
    Args:
        url (str): The base URL of the website (domain name)
        max_total_time (int): Maximum total time allowed for all requests (seconds)
        
    Returns:
        list: A list of URLs found in the sitemap
    """
    # Track start time to enforce total time limit
    start_time = time.time()
    
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
        'Connection': 'close',  # Don't keep connections open
    }
    
    all_urls = []
    sitemap_found = False
    
    # First try robots.txt to find sitemap with shorter timeout
    try:
        if time.time() - start_time >= max_total_time:
            return list(set(all_urls))
            
        robots_url = f"{base_domain}/robots.txt"
        response = requests.get(robots_url, timeout=3, headers=headers)
        
        if response.status_code == 200:
            # Look for Sitemap: directive in robots.txt
            for line in response.text.split('\n'):
                if line.lower().startswith('sitemap:'):
                    sitemap_url = line.split(':', 1)[1].strip()
                    print(f"Found sitemap in robots.txt: {sitemap_url}")
                    
                    # Process this sitemap
                    urls = process_sitemap(sitemap_url, headers, start_time, max_total_time)
                    if urls:
                        all_urls.extend(urls)
                        sitemap_found = True
    except Exception as e:
        print(f"Error checking robots.txt: {str(e)}")
    
    # If no sitemap found in robots.txt, try common locations
    if not sitemap_found:
        for path in sitemap_paths:
            try:
                # Check if we've already spent too much time
                if time.time() - start_time >= max_total_time:
                    break
                    
                sitemap_url = f"{base_domain}{path}"
                print(f"Trying sitemap at: {sitemap_url}")
                
                urls = process_sitemap(sitemap_url, headers, start_time, max_total_time)
                if urls:
                    all_urls.extend(urls)
                    sitemap_found = True
                    break
            except Exception as e:
                print(f"Error checking {sitemap_url}: {str(e)}")
    
    # If still no sitemap found, fall back to HTML scraping
    if (not sitemap_found or not all_urls) and (time.time() - start_time < max_total_time):
        try:
            print(f"No XML sitemap found, falling back to HTML scraping for: {base_domain}")
            response = requests.get(base_domain, timeout=3, headers=headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                
                # Skip empty links, fragments, and javascript links
                if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue
                
                # Convert relative URLs to absolute
                full_url = urljoin(base_domain, href)
                
                # Only include links from the same domain
                if urlparse(full_url).netloc == parsed_url.netloc:
                    all_urls.append(full_url)
        except Exception as e:
            print(f"Error with HTML fallback scraping {base_domain}: {str(e)}")
    
    # Return unique URLs, limited to 1000 if there are too many
    unique_urls = list(set(all_urls))
    if len(unique_urls) > 1000:
        print(f"Limiting results from {len(unique_urls)} to 1000 URLs")
        return unique_urls[:1000]
    return unique_urls

def process_sitemap(sitemap_url, headers, start_time, max_total_time):
    """
    Process a sitemap URL and extract all page URLs with timeout handling.
    
    Args:
        sitemap_url (str): URL of the sitemap to process
        headers (dict): HTTP headers to use for the request
        start_time (float): When the overall process started
        max_total_time (int): Maximum allowed time for all requests
        
    Returns:
        list: URLs found in the sitemap
    """
    # Check if we've already spent too much time
    if time.time() - start_time >= max_total_time:
        return []
        
    urls = []
    
    try:
        # Use shorter timeout for individual requests
        response = requests.get(sitemap_url, timeout=3, headers=headers)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '')
        
        # Skip if not XML (might be HTML error page, etc.)
        if 'xml' not in content_type.lower() and not (
            '<urlset' in response.text or 
            '<sitemapindex' in response.text
        ):
            return []
            
        # Check if it's a sitemap index (contains other sitemaps)
        if '<sitemapindex' in response.text:
            try:
                # Parse as sitemap index
                root = ET.fromstring(response.content)
                
                # Define namespace mapping if needed
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                # Find all sitemap URLs in the index
                for sitemap in root.findall('.//sm:sitemap/sm:loc', ns) or root.findall('.//sitemap/loc'):
                    # Check time again before processing each child sitemap
                    if time.time() - start_time >= max_total_time:
                        break
                        
                    child_sitemap_url = sitemap.text.strip()
                    # Recursively process child sitemaps
                    child_urls = process_sitemap(child_sitemap_url, headers, start_time, max_total_time)
                    if child_urls:
                        urls.extend(child_urls)
            except ET.ParseError:
                # If XML parsing fails, try to extract URLs using string methods
                for line in response.text.splitlines():
                    if '<loc>' in line and '</loc>' in line:
                        start_idx = line.find('<loc>') + 5
                        end_idx = line.find('</loc>')
                        if start_idx < end_idx:
                            child_url = line[start_idx:end_idx].strip()
                            if child_url.endswith('.xml'):
                                child_urls = process_sitemap(child_url, headers, start_time, max_total_time)
                                if child_urls:
                                    urls.extend(child_urls)
                            else:
                                urls.append(child_url)
                    
        # Process as regular sitemap
        elif '<urlset' in response.text:
            try:
                # Parse as regular sitemap
                root = ET.fromstring(response.content)
                
                # Define namespace mapping
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                # Find all page URLs
                for url_element in root.findall('.//sm:url/sm:loc', ns) or root.findall('.//url/loc'):
                    page_url = url_element.text.strip()
                    urls.append(page_url)
            except ET.ParseError:
                # If XML parsing fails, try to extract URLs using string methods
                for line in response.text.splitlines():
                    if '<loc>' in line and '</loc>' in line:
                        start_idx = line.find('<loc>') + 5
                        end_idx = line.find('</loc>')
                        if start_idx < end_idx:
                            urls.append(line[start_idx:end_idx].strip())
                
    except requests.exceptions.Timeout:
        print(f"Timeout while processing sitemap {sitemap_url}")
    except requests.exceptions.ConnectionError:
        print(f"Connection error while processing sitemap {sitemap_url}")
    except Exception as e:
        print(f"Error processing sitemap {sitemap_url}: {str(e)}")
    
    # Limit the number of URLs to prevent memory issues
    if len(urls) > 500:
        print(f"Limiting results from {len(urls)} to 500 URLs for sitemap {sitemap_url}")
        return urls[:500]
    return urls