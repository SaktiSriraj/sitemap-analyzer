import os
import openai
from dotenv import load_dotenv

# load the .env file
load_dotenv()

# setting up the openai api key
openai.api_key = os.environ.get('OPENAI_API_KEY')

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
        #  call openai api
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a business analyst examining comapny website"},
                {"role": "user", "content": prompt}
            ]
        )

        # extract and return the AI-generated insight
        return response.choices[0].message.content
    
    except Exception as e:
        print(f"Error generating AI insights for {company_name}: {str(e)}")
        return "Error generating insights. Please try again later."