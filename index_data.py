from elasticsearch import Elasticsearch
import pandas as pd
import os
import json
from datetime import datetime
import sys

# === CONFIGURATION ===
ES_ENDPOINT = "https://my-elasticsearch-project-fb163a.es.asia-south1.gcp.elastic.cloud:443"
ES_API_KEY = "S1BmR0xwb0JyQkNLQWZtRGJnU2U6R082bzl4UmNVWVl6VmpIY2VRYlNQUQ=="
INPUT_DIR = "."  # Current directory to look for CSV files

# === CONNECT TO ELASTIC ===
es = Elasticsearch(
    ES_ENDPOINT,
    api_key=ES_API_KEY,
    verify_certs=True
)

# === CHECK CONNECTION ===
if not es.ping():
    print("❌ Connection failed! Please check endpoint or API key.")
    exit()
else:
    print("✅ Connected to Elasticsearch!")


def get_csv_files():
    """Get all CSV files from the input directory"""
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Directory '{INPUT_DIR}' not found!")
        return []
    
    csv_files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.csv')]
    return csv_files


def create_index_if_not_exists(index_name):
    """Create index if it doesn't exist"""
    if not es.indices.exists(index=index_name):
        # Basic mapping for dynamic fields
        mapping = {
            "mappings": {
                "properties": {
                    "timestamp": {
                        "type": "date"
                    }
                }
            }
        }
        es.indices.create(index=index_name, body=mapping)
        print(f"✅ Created index: {index_name}")
    else:
        print(f"📦 Index '{index_name}' already exists")


def upload_csv_to_elastic(csv_file_path, index_name):
    """Upload CSV data to Elasticsearch"""
    print(f"\n🔄 Processing: {csv_file_path}")
    
    try:
        # Read CSV file
        df = pd.read_csv(csv_file_path)
        print(f"📊 Found {len(df)} records in CSV")
        
        if df.empty:
            print("⚠️ CSV file is empty, skipping...")
            return
        
        # Create index if it doesn't exist
        create_index_if_not_exists(index_name)
        
        # Add timestamp to each record
        df['upload_timestamp'] = datetime.now().isoformat()
        
        # Convert DataFrame to list of dictionaries
        records = df.to_dict('records')
        
        # Bulk upload to Elasticsearch
        from elasticsearch.helpers import bulk
        
        def generate_docs():
            for i, record in enumerate(records):
                # Convert any NaN values to None
                clean_record = {}
                for key, value in record.items():
                    if pd.isna(value):
                        clean_record[key] = None
                    else:
                        clean_record[key] = value
                
                yield {
                    "_index": index_name,
                    "_source": clean_record
                }
        
        # Perform bulk upload
        success_count, failed_items = bulk(es, generate_docs(), chunk_size=1000)
        
        print(f"✅ Successfully uploaded {success_count} documents to index '{index_name}'")
        
        if failed_items:
            print(f"⚠️ {len(failed_items)} documents failed to upload")
            
    except Exception as e:
        print(f"❌ Error processing {csv_file_path}: {str(e)}")


def main():
    """Main function to handle CSV upload process"""
    
    # Get available CSV files
    csv_files = get_csv_files()
    
    if not csv_files:
        print(f"❌ No CSV files found in '{INPUT_DIR}' directory!")
        return
    
    print(f"\n📁 Found CSV files in '{INPUT_DIR}':")
    for i, filename in enumerate(csv_files, start=1):
        print(f"{i}. {filename}")
    
    # Get user choice
    choice = input("\n👉 Enter file number to upload (or 'all' to upload all): ").strip()
    
    # Determine which files to upload
    if choice.lower() == "all":
        selected_files = csv_files
    else:
        try:
            file_num = int(choice)
            if 1 <= file_num <= len(csv_files):
                selected_files = [csv_files[file_num - 1]]
            else:
                print("⚠️ Invalid choice. Exiting.")
                return
        except ValueError:
            print("⚠️ Invalid input. Exiting.")
            return
    
    # Process selected files
    for csv_file in selected_files:
        csv_path = os.path.join(INPUT_DIR, csv_file)
        
        # Generate index name from filename (remove .csv extension and make lowercase)
        index_name = csv_file.replace('.csv', '').lower().replace(' ', '_')
        
        # Ask user for index name confirmation
        user_index = input(f"\n📝 Enter index name for '{csv_file}' (default: '{index_name}'): ").strip()
        if user_index:
            index_name = user_index.lower().replace(' ', '_')
        
        # Upload to Elasticsearch
        upload_csv_to_elastic(csv_path, index_name)
    
    print("\n🎉 Upload process complete!")


if __name__ == "__main__":
    # Check if ES configuration is provided
    if not ES_ENDPOINT or not ES_API_KEY:
        print("⚠️ Please configure ES_ENDPOINT and ES_API_KEY at the top of this file")
        print("ES_ENDPOINT = 'https://your-elasticsearch-endpoint.com'")
        print("ES_API_KEY = 'your-api-key-here'")
        exit()
    
    main()