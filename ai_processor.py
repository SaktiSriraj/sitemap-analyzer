import os
import google.generativeai as genai
from dotenv import load_dotenv

# load the .env file
load_dotenv()

# setting up the gemini api key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def analyze_sitemap_with_ai(company_name, sitemap_urls):

    # prepare sitemap for prompts
    sitemap_text = "\n".join(sitemap_urls)

    # prepare prompt
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
        print(f"Error generating AI insights for {company_name}: {str(e)}")
        return "Error generating insights. Please try again later."