import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
from urllib.parse import urljoin, urlparse
import time
import threading
import concurrent.futures
import itertools

# Add Session for connecting pooling
# Create a connection pool
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=3
)
session.mount('http://', adapter)
session.mount('https://', adapter)

def extract_sitemap(url, max_total_time=20):

    # Track start time to enforce total time limit
    start_time = time.time()
    
    # Use a list that can be accessed from worker thread
    all_urls = []
    
    # List of common user agents to rotate
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
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
        '/wp-sitemap.xml',
        '/site-map.xml',
        '/sitemap.php',
        '/sitemap.txt',
        '/sitemap/sitemap.xml'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'close',  # Don't keep connections open
    }
    
    # Track URLs we've seen to avoid duplicates
    seen_urls = set()
    
    # Use a thread to enforce hard timeout
    def extraction_worker():
        nonlocal all_urls, seen_urls
        sitemap_found = False
        
        # First try robots.txt to find sitemap with shorter timeout
        try:
            robots_url = f"{base_domain}/robots.txt"
            response = requests.get(robots_url, timeout=2, headers=headers)
            
            if response.status_code == 200:
                # Look for Sitemap: directive in robots.txt
                for line in response.text.split('\n'):
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        print(f"Found sitemap in robots.txt: {sitemap_url}")
                        
                        # Process this sitemap
                        urls = process_sitemap(sitemap_url, headers, start_time, max_total_time)
                        if urls:
                            # Add only unique URLs
                            for url in urls:
                                if url not in seen_urls:
                                    all_urls.append(url)
                                    seen_urls.add(url)
                            sitemap_found = True
                            return  # Early return if we found URLs
        except Exception as e:
            print(f"Error checking robots.txt: {str(e)}")
        
        # If no sitemap found in robots.txt, try common locations
        if not sitemap_found:
            # USE CONCURRENT PROCESSING
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_path = {
                    executor.submit(try_sitemap_path, base_domain, path, headers, start_time, max_total_time): path
                    for path in sitemap_paths
                }

                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        urls = future.result()
                        if urls:
                            # Add only unique URLs
                            for url in urls:
                                if url not in seen_urls:
                                    all_urls.append(url)
                                    seen_urls.add(url)
                            sitemap_found = True
                            break  # Early break if we found URLs
                    except Exception as e:
                        print(f"Error checking sitemap path {path}: {str(e)}")
       
        # If still no sitemap found, fall back to HTML scraping (but only if we have time)
        if not sitemap_found and time.time() - start_time < max_total_time * 0.8:  # 80% of allowed time
            try:
                print(f"No XML sitemap found, falling back to HTML scraping for: {base_domain}")
                response = session.get(base_domain, timeout=2, headers=headers)
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all links (limiting to first 100 to be quick)
                link_count = 0
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    
                    # Skip empty links, fragments, and javascript links
                    if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                        continue
                    
                    # Convert relative URLs to absolute
                    full_url = urljoin(base_domain, href)
                    
                    # Only include links from the same domain
                    if urlparse(full_url).netloc == parsed_url.netloc and full_url not in seen_urls:
                        all_urls.append(full_url)
                        seen_urls.add(full_url)
                        link_count += 1
                        if link_count >= 100:  # Limit to first 100 links for speed
                            break
            except Exception as e:
                print(f"Error with HTML fallback scraping {base_domain}: {str(e)}")
    
    # Helper Function
    def try_sitemap_path(base_domain, path, headers, start_time, max_total_time):
        # Check if we've already spent too much time
        if time.time() - start_time >= max_total_time * 0.7:  # 70% of allowed time
            return []
        
        sitemap_url = f"{base_domain}{path}"
        print(f"Trying sitemap at: {sitemap_url}")

        return process_sitemap(sitemap_url, headers, start_time, max_total_time)

    # Create and start the worker thread
    worker_thread = threading.Thread(target=extraction_worker)
    worker_thread.daemon = True
    worker_thread.start()
    
    # Wait for the worker to finish or timeout
    worker_thread.join(max_total_time)
    
    # If thread is still alive after timeout, we need to return what we have
    if worker_thread.is_alive():
        print(f"Extraction timed out after {max_total_time} seconds")
    
    # Return unique URLs, limited to 500 if there are too many
    unique_urls = list(seen_urls)
    if len(unique_urls) > 500:
        print(f"Limiting results from {len(unique_urls)} to 500 URLs")
        return unique_urls[:500]
    return unique_urls

def process_sitemap(sitemap_url, headers, start_time, max_total_time):
    
    # Check if we've already spent too much time
    if time.time() - start_time >= max_total_time * 0.8:  # 80% of allowed time
        return []
        
    urls = []
    seen_urls = set()  # Track URLs we've seen to avoid duplicates
    
    try:
        # Use shorter timeout for individual requests
        response = session.get(sitemap_url, timeout=2, headers=headers)
        
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
                
                # Find all sitemap URLs in the index (limit to first 3 for speed)
                count = 0
                sitemap_locs = root.findall('.//sm:sitemap/sm;loc', ns) or root.findall(".//sitemap/loc")

                # PROCESS CHILD SITEMAPS CONCURRENTLY
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    future_to_url = {}

                    for sitemap in sitemap_locs[:3]:
                        child_sitemap_url = sitemap.text.strip()
                        future = executor.submit(
                            process_sitemap, child_sitemap_url, headers, start_time, max_total_time
                        )
                        future_to_url[future] = child_sitemap_url
                    
                    for future in concurrent.futures.as_completed(future_to_url):
                        child_urls = future.result()
                        if child_urls:
                            for url in child_urls:
                                if url not in seen_urls:
                                    urls.append(url)
                                    seen_urls.add(url)

                        if time.time() - start_time >= max_total_time * 0.9:
                            break
                
            except ET.ParseError:
                # If XML parsing fails, try to extract URLs using string methods
                count = 0
                for line in response.text.splitlines():
                    if '<loc>' in line and '</loc>' in line and count < 3:
                        start_idx = line.find('<loc>') + 5
                        end_idx = line.find('</loc>')
                        if start_idx < end_idx:
                            child_url = line[start_idx:end_idx].strip()
                            if child_url.endswith('.xml'):
                                child_urls = process_sitemap(child_url, headers, start_time, max_total_time)
                                if child_urls:
                                    for url in child_urls:
                                        if url not in seen_urls:
                                            urls.append(url)
                                            seen_urls.add(url)
                                count += 1
                            elif child_url not in seen_urls:
                                urls.append(child_url)
                                seen_urls.add(child_url)
                    
        # Process as regular sitemap
        elif '<urlset' in response.text:
            try:
                # Parse as regular sitemap
                root = ET.fromstring(response.content)
                
                # Define namespace mapping
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                # Find all page URLs (limit to first 100 for speed)
                count = 0
                for url_element in root.findall('.//sm:url/sm:loc', ns) or root.findall('.//url/loc'):
                    if count >= 100:  # Limit to first 100 URLs for speed
                        break
                    url = url_element.text.strip()
                    if url not in seen_urls:
                        urls.append(url)
                        seen_urls.add(url)
                        count += 1
                    
                    # Check time limit
                    if time.time() - start_time >= max_total_time * 0.9:  # 90% of allowed time
                        break
                        
            except ET.ParseError:
                # If XML parsing fails, try to extract URLs using string methods
                count = 0
                for line in response.text.splitlines():
                    if '<loc>' in line and '</loc>' in line:
                        start_idx = line.find('<loc>') + 5
                        end_idx = line.find('</loc>')
                        if start_idx < end_idx:
                            url = line[start_idx:end_idx].strip()
                            if url not in seen_urls:
                                urls.append(url)
                                seen_urls.add(url)
                                count += 1
                                if count >= 100:  # Limit to first 100 URLs
                                    break
                                
    except Exception as e:
        print(f"Error processing sitemap {sitemap_url}: {str(e)}")
        
    return urls