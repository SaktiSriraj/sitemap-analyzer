import os
from pymongo import MongoClient
from dotenv import load_dotenv

import pymongo
from pymongo import ReturnDocument
import time

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
    client = MongoClient(
        mongo_uri,
        maxPoolSize=50,  # Adjust based on expected load
        waitQueueTimeoutMS=2000,
        connectTimeoutMS=2000,
        serverSelectionTimeoutMS=3000
    )
    db = client.get_database('sitemap-analyzer', 
                write_concern=pymongo.WriteConcern(w=1))
    company_collection = db['companies']

    # Create index for faster lookups
    try:
        company_collection.create_index([('company_name', pymongo.ASCENDING)], unique=True)
        # Add normalized website URL index for deduplication
        company_collection.create_index([('website_url', pymongo.ASCENDING)])
        # Add timestamp index for sorting by freshness
        company_collection.create_index([('last_updated', pymongo.DESCENDING)])
    except Exception as e:
        print(f"Error creating indexes: {str(e)}")

def store_company_data(company_data):
    global company_collection

    # Ensure we have a timestamp
    if 'last_updated' not in company_data:
        company_data['last_updated'] = time.time()
        
    # Normalize company name (lowercase for matching)
    company_data['company_name_normalized'] = company_data['company_name'].lower()

    # Upsert operation - update if exists, insert if not
    try:
        result = company_collection.update_one(
            {'company_name': company_data['company_name']},
            {'$set': company_data},
            upsert=True
        )
        return True
    except pymongo.errors.DuplicateKeyError:
        # If duplicate key (shouldn't happen with upsert, but just in case)
        try:
            # Try forced update
            company_collection.replace_one(
                {'company_name': company_data['company_name']},
                company_data
            )
            return True
        except Exception as e:
            print(f"Error storing company data for {company_data['company_name']}: {str(e)}")
            return False
    except Exception as e:
        print(f"Error storing company data for {company_data['company_name']}: {str(e)}")
        return False

# Batch Operation
def store_companies_batch(company_data_list):
    global company_collection

    if not company_data_list:
        return
    
    # Ensure each record has needed fields
    for company_data in company_data_list:
        if 'last_updated' not in company_data:
            company_data['last_updated'] = time.time()
        company_data['company_name_normalized'] = company_data['company_name'].lower()
    
    operations = []
    for company_data in company_data_list:
        operations.append(
            pymongo.UpdateOne(
                {'company_name': company_data['company_name']},
                {'$set': company_data},
                upsert=True
            )
        )
    
    if operations:
        try:
            result = company_collection.bulk_write(operations)
            print(f"Batch operation completed: {result.upserted_count} inserted, {result.modified_count} modified")
            return result
        except Exception as e:
            print(f"Error in batch operation: {str(e)}")
            # Fallback to individual operations
            for company_data in company_data_list:
                try:
                    store_company_data(company_data)
                except Exception as inner_e:
                    print(f"Error storing {company_data['company_name']}: {str(inner_e)}")

def get_company_data(company_name):
    global company_collection

    # Find company by name
    return company_collection.find_one({'company_name': company_name})

def get_company_by_website(website_url):
    global company_collection
    
    # Find company by website URL
    return company_collection.find_one({'website_url': website_url})

def get_all_companies():
    global company_collection

    # Return all companies
    return list(company_collection.find())

def reset_database():
    global company_collection
    try:
        # Delete all documents from the collection
        result = company_collection.delete_many({})
        print(f"Database reset: {result.deleted_count} documents deleted")
        return True
    except Exception as e:
        print(f"Error resetting database: {str(e)}")
        return False

def get_deduped_companies():
    global company_collection
    
    # Get only the latest record for each company by using aggregation
    pipeline = [
        {"$sort": {"last_updated": -1}},  # Sort by last_updated descending
        {"$group": {
            "_id": "$company_name_normalized",  # Group by normalized company name
            "doc": {"$first": "$$ROOT"}  # Take only the first (most recent) document
        }},
        {"$replaceRoot": {"newRoot": "$doc"}}  # Replace the root with the document
    ]
    
    return list(company_collection.aggregate(pipeline))