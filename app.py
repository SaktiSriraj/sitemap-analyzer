import os
import pandas as pd
from flask import Flask, request, send_file, render_template, redirect, url_for, jsonify
from io import BytesIO
import time
from dotenv import load_dotenv
from scraper import extract_sitemap
from ai_processor import analyze_sitemap_with_ai
from database import init_db, store_company_data, get_company_data, reset_database

import threading
import queue
import uuid
import json

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(__name__)

# Initialize database connection
init_db()

# ADD JOB QUEUE AND RESULTS DICTIONARY
job_queue = queue.Queue()
results = {}

def worker():
    while True:
        job_id, company_name, website_url = job_queue.get()
        try:
            result = process_company(company_name, website_url)
            results[job_id] = {"status": "complete", "data": result}
        except Exception as e:
            print(f"Worker error processing {company_name}: {str(e)}")
            results[job_id] = {"status": "error", "message": str(e)}
        finally:
            job_queue.task_done()

# Start worker thread
worker_count = 5
for _ in range(worker_count):
    t = threading.Thread(target=worker, daemon=True)
    t.start()

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

def process_csv(csv_file, async_mode=True):
    # Read CSV in Chunks to avoid loading everything into memory
    chunk_size = 10
    output_data = []
    job_ids = []
    
    # Keep track of unique companies to avoid duplicates
    unique_companies = set()

    # Find column names first by reading just the header
    header_df = pd.read_csv(csv_file, nrows=0)
    company_col = None
    website_col = None

    for col in header_df.columns:
        if col.lower() == 'company':
            company_col = col
        elif col.lower() == 'website':
            website_col = col
    
    # if we cannot find exact matches, look for similar columns
    if not company_col:
        for col in header_df.columns:
            if 'company' in col.lower() or'name' in col.lower() or 'organization' in col.lower():
                company_col = col
                break

    if not website_col:
        for col in header_df.columns:
            if 'website' in col.lower() or 'url' in col.lower() or 'site' in col.lower():
                website_col = col
                break
    
    if not company_col or not website_col:
        error_msg = f"Could not find required columns. Your CSV has these columns: {list(header_df.columns)}"
        print(error_msg)
        raise ValueError(error_msg)
    
    # Reset file position
    csv_file.seek(0)

    # Chunk processing
    for chunk in pd.read_csv(csv_file, chunksize=chunk_size):
        for _, row in chunk.iterrows():
            company_name = row[company_col].strip() if isinstance(row[company_col], str) else str(row[company_col])
            website_url = row[website_col].strip() if isinstance(row[website_col], str) else str(row[website_col])
            
            # Check for empty values
            if not company_name or not website_url:
                continue
                
            # Normalize website URL
            if not website_url.startswith(('http://', 'https://')):
                website_url = 'https://' + website_url
                
            # Create a unique key for deduplication
            unique_key = f"{company_name.lower()}:{website_url.lower()}"
            
            # Skip if we've already processed this company+website combination
            if unique_key in unique_companies:
                continue
                
            unique_companies.add(unique_key)

            if async_mode:
                # Queue for async processing
                job_id = f"job_{uuid.uuid4()}"
                job_queue.put((job_id, company_name, website_url))
                job_ids.append(job_id)

                output_data.append({
                    'Company': company_name,
                    'Website': website_url,
                    'Processing': 'Queued for processing',
                    'Job ID': job_id
                })
    
    return output_data, job_ids

# Flask routes

# Routes for async processing
@app.route('/status')
def all_jobs_status():
    return jsonify(results)

@app.route('/status/<job_id>')
def job_status(job_id):
    if job_id in results:
        return jsonify(results[job_id])
    else:
        return jsonify({"status": "not found"})
    
@app.route('/results')
def get_results():
    # Check if all jobs are complete
    completed_results = []
    
    # Create a dictionary to deduplicate results by company name
    company_results = {}
    
    for job_id, result in results.items():
        if result['status'] == 'complete' and 'data' in result:
            # Use company_name as unique key
            company_name = result['data']['Company']
            
            # If company already exists with older data, update it
            if company_name in company_results:
                # Keep the most recent result (assumes job_id is roughly chronological)
                # In a more robust system, you might want to compare timestamps
                company_results[company_name] = result['data']
            else:
                company_results[company_name] = result['data']
    
    # Convert dictionary values to list
    completed_results = list(company_results.values())
    
    # Create output CSV
    output_df = pd.DataFrame(completed_results)

    # Save to BytesIO
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

@app.route('/health')
def health_check():
    # Check MongoDB Connection
    try:
        from database import db
        db.command('ping')
        mongo_status = 'OK'
    except Exception as e:
        mongo_status = f"error: {str(e)}"
    
    # Check AI Service
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        model = genai.get_model('gemini-2.0-flash')
        model.generate_content("test")
        ai_status = 'OK'
    except Exception as e:
        ai_status = f"error: {str(e)}"
    
    # Check worker queue
    queue_status = {
        'queue_size': job_queue.qsize(),
        'results_size': len(results)
    }
    status = {
        'app':'running',
        'mongo': mongo_status,
        'ai_service': ai_status,
        'job_queue': queue_status
    }

    return jsonify(status)
        
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and file.filename.endswith('.csv'):
        try:
            # Clear the Database
            reset_database()

            # Clear any existing results
            results.clear()

            # Process the CSV and get job IDs
            output_data, job_ids = process_csv(file, async_mode=True)
            
            # Return job IDs as JSON
            return jsonify({
                "status": "processing",
                "job_ids": job_ids,
                "message": f"Processing {len(job_ids)} companies"
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Invalid file format. Please upload a CSV file."}), 400

if __name__ == '__main__':
    # Run the app
    app.run(debug=True)