import os
import google.generativeai as genai
from dotenv import load_dotenv

from functools import wraps
import time
import concurrent.futures

# load the .env file
load_dotenv()

# setting up the gemini api key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Adding Circuit Breaker to the AI Processor
class CircuitBreaker:
    def __init__(self, max_failures=3, reset_timeout=60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.open_since = None

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.open_since is not None:
                if time.time() - self.open_since > self.reset_timeout:
                    # Reset if timeout passed
                    self.failures = 0
                    self.open_since = None
                else:
                    raise Exception("Circuit Breaker: AI Service is temporarily Unavailable. Please try again later.")
            try:
                result = func(*args, **kwargs)
                # Success, reset failure count
                self.failures = 0
                return result
            except Exception as e:
                self.failures += 1
                if self.failures >= self.max_failures:
                    self.open_since = time.time()
                raise e
        return wrapper
    
# Create AI Circuit Breaker
ai_circuit_breaker = CircuitBreaker(max_failures=3, reset_timeout=300)

# Helper Function to Analyze Sitemap with AI
def _do_analyze(company_name, sitemap_urls):
    time.sleep(0.5)
    sitemap_text = "\n".join(sitemap_urls)

    prompt = f"""You are analyzing a company's online presence based on its sitemap. Below is a list of all the URLs found on the company's website:
                {sitemap_text}
                Based on this structure, generate a concise business insight about the company. Identify key focus areas, business priorities, and any indications of growth, investment, or technology adoption.
                Format the response as:
                - Company Overview:
                - Key Focus Areas:
                - Potential Opportunities:
                """
    try:
        # Initialize the Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Generate content using Gemini
        response = model.generate_content(prompt)
        # Extract and return the AI-generated insight
        return response.text
    except Exception as e:
        error_message =  f"Error generating AI insights: {str(e)}"
        print(error_message)
    return f"Error: {error_message}. Please try again later."

@ai_circuit_breaker
def analyze_sitemap_with_ai(company_name, sitemap_urls, timeout=60):
    # Limit number of URLs to prevent timeouts or quota issues
    if len(sitemap_urls) > 100:
        print(f"Limiting sitemap URLs for {company_name} from {len(sitemap_urls)} to 100")
        sitemap_urls = sitemap_urls[:100]
    
    # Use timeout mechanism
    try:
        # Use a separate thread with timeout
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_do_analyze, company_name, sitemap_urls)
            result = future.result(timeout=timeout)
            return result
    except concurrent.futures.TimeoutError:
        return f"AI analysis for {company_name} timed out. Analysis limited to prevent system overload."
    except Exception as e:
        print(f"Error in AI analysis for {company_name}: {str(e)}")
        return f"Error during analysis: {str(e)}"