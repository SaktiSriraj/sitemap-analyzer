import os
from pymongo import MongoClient
from dotenv import load_dotenv

import pymongo
from pymongo import ReturnDocument

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
    company_collection.create_index('company_name', unique=True)

def store_company_data(company_data):
    global company_collection

    # Upsert operation - update if exists, insert if not
    company_collection.update_one(
        {'company_name': company_data['company_name']},
        {'$set': company_data},
        upsert=True
    )

# Batch Operation
def store_companies_batch(company_data_list):
    global company_collection

    if not company_data_list:
        return
    
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

def get_all_companies():
    global company_collection

    # Return all companies
    return list (company_collection.find())