import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
from urllib.parse import urljoin, urlparse
import time
import threading

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
        '/sitemap-index.xml'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'close',  # Don't keep connections open
    }
    
    # Use a thread to enforce hard timeout
    def extraction_worker():
        nonlocal all_urls
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
                            all_urls.extend(urls)
                            sitemap_found = True
                            return  # Early return if we found URLs
        except Exception as e:
            print(f"Error checking robots.txt: {str(e)}")
        
        # If no sitemap found in robots.txt, try common locations
        if not sitemap_found:
            for path in sitemap_paths:
                try:
                    # Check if we've already spent too much time
                    if time.time() - start_time >= max_total_time * 0.7:  # 70% of allowed time
                        return
                        
                    sitemap_url = f"{base_domain}{path}"
                    print(f"Trying sitemap at: {sitemap_url}")
                    
                    urls = process_sitemap(sitemap_url, headers, start_time, max_total_time)
                    if urls:
                        all_urls.extend(urls)
                        sitemap_found = True
                        return  # Early return if we found URLs
                except Exception as e:
                    print(f"Error checking {sitemap_url}: {str(e)}")
        
        # If still no sitemap found, fall back to HTML scraping (but only if we have time)
        if not sitemap_found and time.time() - start_time < max_total_time * 0.8:  # 80% of allowed time
            try:
                print(f"No XML sitemap found, falling back to HTML scraping for: {base_domain}")
                response = requests.get(base_domain, timeout=2, headers=headers)
                
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
                    if urlparse(full_url).netloc == parsed_url.netloc:
                        all_urls.append(full_url)
                        link_count += 1
                        if link_count >= 100:  # Limit to first 100 links for speed
                            break
            except Exception as e:
                print(f"Error with HTML fallback scraping {base_domain}: {str(e)}")
    
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
    unique_urls = list(set(all_urls))
    if len(unique_urls) > 500:
        print(f"Limiting results from {len(unique_urls)} to 500 URLs")
        return unique_urls[:500]
    return unique_urls

def process_sitemap(sitemap_url, headers, start_time, max_total_time):
    
    # Check if we've already spent too much time
    if time.time() - start_time >= max_total_time * 0.8:  # 80% of allowed time
        return []
        
    urls = []
    
    try:
        # Use shorter timeout for individual requests
        response = requests.get(sitemap_url, timeout=2, headers=headers)
        
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
                for sitemap in root.findall('.//sm:sitemap/sm:loc', ns) or root.findall('.//sitemap/loc'):
                    # Check time again before processing each child sitemap
                    if time.time() - start_time >= max_total_time * 0.8 or count >= 3:
                        break
                        
                    child_sitemap_url = sitemap.text.strip()
                    # Recursively process child sitemaps
                    child_urls = process_sitemap(child_sitemap_url, headers, start_time, max_total_time)
                    if child_urls:
                        urls.extend(child_urls)
                    count += 1
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
                                    urls.extend(child_urls)
                                count += 1
                            else:
                                urls.append(child_url)
                    
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
                    page_url = url_element.text.strip()
                    urls.append(page_url)
                    count += 1
                    if count >= 100:
                        break
            except ET.ParseError:
                # If XML parsing fails, try to extract URLs using string methods
                count = 0
                for line in response.text.splitlines():
                    if '<loc>' in line and '</loc>' in line:
                        start_idx = line.find('<loc>') + 5
                        end_idx = line.find('</loc>')
                        if start_idx < end_idx:
                            urls.append(line[start_idx:end_idx].strip())
                            count += 1
                            if count >= 100:
                                break
                
    except requests.exceptions.RequestException as e:
        print(f"Request error processing sitemap {sitemap_url}: {str(e)}")
        return []
    except Exception as e:
        print(f"Error processing sitemap {sitemap_url}: {str(e)}")
        return []
    
    # Limit the number of URLs to prevent memory issues
    if len(urls) > 200:
        return urls[:200]
    return urls