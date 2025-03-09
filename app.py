import os
import pandas as pd
from flask import Flask, request, send_file, render_template, redirect, url_for
from io import BytesIO
import time
from dotenv import load_dotenv
from scraper import extract_sitemap
from ai_processor import analyze_sitemap_with_ai
from database import init_db, store_company_data, get_company_data

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(__name__)

# Initialize database connection
init_db()

def process_company(company_name, website_url):
    
    # Scrape the sitemap
    sitemap_urls = extract_sitemap(website_url)
    
    # Generate AI insights
    insights = analyze_sitemap_with_ai(company_name, sitemap_urls)
    
    # Store in database
    company_data = {
        'company_name': company_name,
        'website_url': website_url,
        'sitemap_urls': sitemap_urls,
        'ai_insights': insights,
        'last_updated': time.time()
    }
    
    # Store in database
    store_company_data(company_data)
    
    return {
        'Company': company_name,
        'Website': website_url,
        'Sitemap Complete': ", ".join(sitemap_urls),
        'Insight from Prompt': insights
    }

def process_csv(csv_file):

    # Read the input CSV
    df = pd.read_csv(csv_file)

    company_col = None
    website_col = None
    
    for col in df.columns:
        if col.lower() == 'company':
            company_col = col
        elif col.lower() == 'website':
            website_col = col
    
    # If we can't find exact matches, look for similar columns
    if not company_col:
        for col in df.columns:
            if 'company' in col.lower() or 'name' in col.lower() or 'organization' in col.lower():
                company_col = col
                break
    
    if not website_col:
        for col in df.columns:
            if 'website' in col.lower() or 'url' in col.lower() or 'site' in col.lower():
                website_col = col
                break
    
    if not company_col or not website_col:
        error_msg = f"Could not find required columns. Your CSV has these columns: {list(df.columns)}"
        print(error_msg)
        raise ValueError(error_msg)
    
    # Prepare output data
    output_data = []
    
    # Process each company
    for _, row in df.iterrows():
        company_name = row[company_col]
        website_url = row[website_col]
        
        # Check if we already have data for this company
        existing_data = get_company_data(company_name)
        
        # Process the company
        result = process_company(company_name, website_url)
        output_data.append(result)
    
    return output_data

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(request.url)
    
    if file and file.filename.endswith('.csv'):
        # Process the CSV
        output_data = process_csv(file)
        
        # Create output CSV
        output_df = pd.DataFrame(output_data)
        
        # Save to BytesIO instead of StringIO
        output_csv = BytesIO()
        output_df.to_csv(output_csv, index=False)
        output_csv.seek(0)
        
        # Create in-memory file for download
        return send_file(
            output_csv,
            mimetype='text/csv',
            download_name='sitemap_analysis_results.csv',
            as_attachment=True
        )
    
    return redirect(request.url)

if __name__ == '__main__':
    # Run the app
    app.run(debug=True)