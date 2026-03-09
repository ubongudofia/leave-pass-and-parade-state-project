from pymongo import MongoClient
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["dsa_pass_leave"]

# Create collection with validator
db.create_collection(
    "notifications",
    validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "type",
                "applicationId",
                "target",
                "message",
                "createdAt",
                "isActive"
            ],
            "properties": {
                "type": {"bsonType": "string"},
                "applicationId": {"bsonType": "objectId"},
                "referenceId": {"bsonType": "string"},
                "target": {
                    "bsonType": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {
                            "enum": ["directorate_role", "role", "user"]
                        },
                        "directorate": {
                            "bsonType": ["string", "null"]
                        },
                        "role": {
                            "bsonType": ["string", "null"]
                        },
                        "userId": {
                            "bsonType": ["string", "null"]
                        }
                    }
                },
                "message": {"bsonType": "string"},
                "meta": {"bsonType": ["object"]},
                "readBy": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                },
                "createdAt": {"bsonType": "date"},
                "isActive": {"bsonType": "bool"}
            }
        }
    }
)

# Create indexes
db.notifications.create_index("target.type")
db.notifications.create_index("target.role")
db.notifications.create_index("target.directorate")
db.notifications.create_index("target.userId")
db.notifications.create_index("applicationId")
db.notifications.create_index("createdAt")
db.notifications.create_index("isActive")
db.notifications.create_index("readBy")

print("Notifications collection created successfully.")