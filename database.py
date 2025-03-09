import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Mongodb connection and collection vars
client = None
db = None
company_collection = None

# Load the .env file
load_dotenv()

def init_db():
    global client, db, company_collection

    # Get mongo connection uri from env
    mongo_uri = os.getenv('MONGO_URI')

    # Connect to the database
    client = MongoClient(mongo_uri)
    db = client['sitemap-analyzer']
    company_collection = db['companies']

    # Create index for faster lookups
    company_collection.create_index('company_name', unique=True)

def store_company_data(company_data):
    global company_collection

    # Upsert operation - update if exists, insert if not
    company_collection.update_one(
        {'company_name': company_data['company_name']},
        {'$set': company_data},
        upsert=True
    )

def get_company_data(company_name):
    global company_collection

    # Find company by name
    return company_collection.find_one({'company_name': company_name})

def get_all_companies():
    global company_collection

    # Return all companies
    return list (company_collection.find())