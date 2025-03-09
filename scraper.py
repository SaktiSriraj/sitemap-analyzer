import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def exract_sitemap(url):
    # Extract all navigable links from a website's homepage
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed_url = urlparse(url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        })
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract all links
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            # skip empty links
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            full_url = urljoin(base_domain, href)

            # only include links from the same domain
            if urlparse(full_url).netloc == parsed_url.netloc:
                links.add(full_url)

        return list(links)
    except Exception as e:
        print(f"Error extracting sitemap: {e}")
        return []