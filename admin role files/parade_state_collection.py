from pymongo import MongoClient, ASCENDING
from pymongo.errors import CollectionInvalid
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["dsa_pass_leave"]

collection_name = "daily_parade_states"

# =========================
# 🔹 JSON SCHEMA VALIDATION
# =========================
schema = {
    "bsonType": "object",
    "required": ["date", "directorate", "batch", "strength", "on_parade", "createdAt"],
    "properties": {
        "date": {
            "bsonType": "string",
            "description": "YYYY-MM-DD format"
        },
        "directorate": {
            "bsonType": "string"
        },
        "batch": {
            "bsonType": "string",
            "enum": ["A", "B", "ALL"]
        },

        # 🔹 SUMMARY
        "strength": {"bsonType": "int"},
        "on_parade": {"bsonType": "int"},

        # 🔹 AUTO COUNTS
        "sick": {"bsonType": "int"},
        "leave": {"bsonType": "int"},
        "pass": {"bsonType": "int"},

        # 🔹 MANUAL COUNTS
        "hospital": {"bsonType": "int"},
        "course": {"bsonType": "int"},
        "absent": {"bsonType": "int"},
        "awol": {"bsonType": "int"},
        "excuse_duty": {"bsonType": "int"},
        "study_leave": {"bsonType": "int"},
        "cds": {"bsonType": "int"},

        # 🔹 STAFF DETAILS
        "details": {
            "bsonType": "object",
            "properties": {
                "absent": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "hospital": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "course": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "awol": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "excuse_duty": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "study_leave": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "cds": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "leave": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "pass": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "sick": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                }
            }
        },

        # 🔹 META
        "remark": {"bsonType": "string"},
        "createdBy": {"bsonType": "string"},
        "createdAt": {"bsonType": "date"}
    }
}

# =========================
# 🔹 CREATE COLLECTION
# =========================
try:
    db.create_collection(
        collection_name,
        validator={"$jsonSchema": schema}
    )
    print("✅ Collection created with schema validation")

except CollectionInvalid:
    print("ℹ️ Collection already exists (skipping creation)")

collection = db[collection_name]

# =========================
# 🔹 INDEXES
# =========================

# 🔥 Prevent duplicate parade entries per day + directorate + batch
collection.create_index(
    [("date", ASCENDING), ("directorate", ASCENDING), ("batch", ASCENDING)],
    unique=True,
    name="unique_daily_parade"
)

# 🔥 Fast queries by date
collection.create_index(
    [("date", ASCENDING)],
    name="idx_date"
)

# 🔥 Fast queries by directorate
collection.create_index(
    [("directorate", ASCENDING)],
    name="idx_directorate"
)

# 🔥 Sort by creation time
collection.create_index(
    [("createdAt", ASCENDING)],
    name="idx_createdAt"
)

print("✅ Indexes created successfully")

print("🎯 daily_parade_states is fully ready for use")