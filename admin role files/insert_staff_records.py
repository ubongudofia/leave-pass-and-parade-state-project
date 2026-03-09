from pymongo import MongoClient
import json

# === CONFIGURATION ===
MONGO_URI = "mongodb://localhost:27017"  # change if needed
DB_NAME = "dsa_pass_leave"
COLLECTION_NAME = "staff"
JSON_FILE = "staff_import.json"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]


# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Load JSON records
with open(JSON_FILE, "r") as f:
    records = json.load(f)

updated_count = 0
inserted_count = 0

for record in records:
    service_number = record.get("service_number")
    if not service_number:
        continue  # skip records without service_number

    existing = collection.find_one({"service_number": service_number})

    if existing:
        # Only add fields that are missing in the existing record
        update_fields = {k: v for k, v in record.items() if k not in existing}
        if update_fields:
            collection.update_one(
                {"service_number": service_number},
                {"$set": update_fields}
            )
            updated_count += 1
    else:
        # Insert new record if it doesn't exist
        collection.insert_one(record)
        inserted_count += 1

print(f"Upsert complete: {updated_count} records updated, {inserted_count} records inserted.")