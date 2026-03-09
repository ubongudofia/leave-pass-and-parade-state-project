from pymongo import MongoClient
from config import Config
import sys
from pymongo.errors import CollectionInvalid, DuplicateKeyError
from datetime import datetime
from bson.objectid import ObjectId


from pymongo import MongoClient
from pymongo.errors import OperationFailure
import sys

# ────────────────────────────────────────────────
#  CONFIGURATION - Change these as needed
# ────────────────────────────────────────────────
MONGO_URI = "mongodb://localhost:27017/"  # Update to your URI
DATABASE_NAME = "dsa_pass_leave"       # Your DB name

# ────────────────────────────────────────────────
def set_applications_schema(db):
    """Set schema validation for the 'applications' collection"""
    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "applicantId", "type", "details", "directorate", "status",
                "approvalChain", "finalApproval", "notifications",
                "createdAt", "updatedAt"
            ],
            "properties": {
                "applicantId": {
                    "bsonType": "string",
                    "description": "Service number of the applicant (required)"
                },
                "type": {
                    "enum": ["leave", "pass"],
                    "description": "Type of application (leave or pass, required)"
                },
                "details": {
                    "bsonType": "object",
                    "required": [
                        "startDate", "endDate", "numberOfDays", "reason",
                        "placeIntended", "contactAddress"
                    ],
                    "properties": {
                        "startDate": {
                            "bsonType": "date",
                            "description": "Start date of leave/pass (required)"
                        },
                        "endDate": {
                            "bsonType": "date",
                            "description": "End date of leave/pass (required)"
                        },
                        "effectiveDate": {
                            "bsonType": ["date", "null"],
                            "description": "Optional effective date"
                        },
                        "numberOfDays": {
                            "bsonType": "int",
                            "description": "Number of days required (required)"
                        },
                        "reason": {
                            "bsonType": "string",
                            "description": "Reason for application (required)"
                        },
                        "placeIntended": {
                            "bsonType": "string",
                            "description": "Place of intended travel (required)"
                        },
                        "contactAddress": {
                            "bsonType": "string",
                            "description": "Contact address (required)"
                        },
                        "attachments": {
                            "bsonType": "array",
                            "description": "Array of attachments (optional)",
                            "items": {
                                "bsonType": "object",
                                "required": ["gridfs_id", "filename", "contentType", "size", "uploadedAt"],
                                "properties": {
                                    "gridfs_id": {"bsonType": "string"},
                                    "filename": {"bsonType": "string"},
                                    "contentType": {"bsonType": "string"},
                                    "size": {"bsonType": "int"},
                                    "uploadedAt": {"bsonType": "date"}
                                }
                            }
                        }
                    }
                },
                "directorate": {
                    "bsonType": "string",
                    "description": "Applicant's directorate code (required)"
                },
                "status": {
                    "enum": ["pending", "approved", "rejected", "issued"],
                    "description": "Overall status (required)"
                },
                "approvalChain": {
                    "bsonType": "array",
                    "description": "Array of approval steps (required)",
                    "items": {
                        "bsonType": "object",
                        "required": ["role", "approverId", "status", "comments", "timestamp"],
                        "properties": {
                            "role": {"bsonType": "string"},
                            "approverId": {"bsonType": "string"},
                            "status": {"enum": ["pending", "approved", "rejected"]},
                            "comments": {"bsonType": "string"},
                            "timestamp": {"bsonType": ["date", "null"]}
                        }
                    }
                },
                "finalApproval": {
                    "bsonType": "object",
                    "required": ["approverId", "status", "comments", "timestamp", "receipt"],
                    "properties": {
                        "approverId": {"bsonType": "string"},
                        "status": {"enum": ["pending", "approved", "rejected"]},
                        "comments": {"bsonType": "string"},
                        "timestamp": {"bsonType": ["date", "null"]},
                        "receipt": {
                            "bsonType": "object",
                            "properties": {
                                "receiptNumber": {"bsonType": ["string", "null"]},
                                "issuedDate": {"bsonType": ["date", "null"]},
                                "pdfUrl": {"bsonType": ["string", "null"]}
                            }
                        }
                    }
                },
                "notifications": {
                    "bsonType": "array",
                    "description": "Array for notifications (required, can be empty)",
                    "items": {
                        "bsonType": "object",
                        "properties": {
                            "toRole": {"bsonType": "string"},
                            "sent": {"bsonType": "bool"}
                        }
                    }
                },
                "createdAt": {
                    "bsonType": "date",
                    "description": "Creation timestamp (required)"
                },
                "updatedAt": {
                    "bsonType": "date",
                    "description": "Last update timestamp (required)"
                }
            }
        }
    }

    try:
        db.command({
            "collMod": "applications",
            "validator": validator,
            "validationLevel": "strict",  # or "moderate" for existing data
            "validationAction": "error"   # or "warn"
        })
        print("✅ Schema validation set for 'applications' collection")
    except OperationFailure as e:
        print(f"ERROR: Failed to set schema - {str(e)}")
        print("Tip: If collection doesn't exist, create it first with db.create_collection('applications')")

# ────────────────────────────────────────────────
#  MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Connecting to MongoDB → {MONGO_URI}")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        set_applications_schema(db)
        print("\nSetup complete! ✓")
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)
    finally:
        client.close()




# ==================================================================================================================================


# # ────────────────────────────────────────────────
# def create_collections_and_indexes(db):
#     """Create collections and add useful indexes"""
    
#     print("\nCreating collections and indexes...")
    
#     # 1. directorates
#     try:
#         db.create_collection("directorates")
#         print("Created collection: directorates")
#     except CollectionInvalid:
#         print("Collection 'directorates' already exists")
    
#     db.directorates.create_index([("code", 1)], unique=True)
#     print("→ Unique index on directorates.code")

#     # 2. staff
#     try:
#         db.create_collection("staff")
#         print("Created collection: staff")
#     except CollectionInvalid:
#         print("Collection 'staff' already exists")
    

#     db.staff.create_index("directorate")
#     db.staff.create_index("type")
#     db.staff.create_index("roles")
#     db.staff.create_index("email", unique=True)
#     db.staff.create_index([("directorate", 1), ("roles", 1)])
#     print("→ Indexes added to staff collection")

#     # 3. applications
#     try:
#         db.create_collection("applications")
#         print("Created collection: applications")
#     except CollectionInvalid:
#         print("Collection 'applications' already exists")
    
#     db.applications.create_index("applicantId")
#     db.applications.create_index("directorate")
#     db.applications.create_index("status")
#     db.applications.create_index([("approvalChain.approverId", 1), ("approvalChain.status", 1)])
#     db.applications.create_index("finalApproval.approverId")
#     db.applications.create_index([("applicantId", 1), ("createdAt", -1)])
#     print("→ Indexes added to applications collection")


# def insert_directorates(db):
#     """Insert the 9 directorates (safe / idempotent)"""
#     directorates_list = [
#         {"code": "DCS",      "name": "Directorate of Communications Satellite"},
#         {"code": "DEO",      "name": "Directorate of Earth Observation"},
#         {"code": "DLSO",     "name": "Directorate of Launch Services Operation"},
#         {"code": "DOA",      "name": "Directorate of Administration"},
#         {"code": "DNPT",     "name": "Directorate of Navigation Positioning and Timing"},
#         {"code": "DPPR",     "name": "Directorate of Policy & Public Relations"},
#         {"code": "DCYBER",   "name": "Directorate of Cyber Security"},
#         {"code": "DFA",      "name": "Directorate of Finance & Accounts"},
#         {"code": "DELSPACE", "name": "Delta Space"},
#     ]
    
#     inserted = 0
#     for doc in directorates_list:
#         try:
#             db.directorates.insert_one(doc)
#             inserted += 1
#         except DuplicateKeyError:
#             pass
    
#     print(f"→ Directorates: {inserted} new inserted")


# def insert_sample_staff(db):
#     """Insert sample staff (idempotent)"""
#     samples = [
#         {
#             "_id": "NA/12345",
#             "fullName": "Musa Ahmed",
#             "type": "military",
#             "directorate": "DCS",
#             "rankOrGrade": "Maj Gen",
#             "designation": "Director",
#             "roles": ["Director"],
#             "email": "musa.ahmed@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "NN/12345",
#             "fullName": "Ibrahim Yusuf",
#             "type": "military",
#             "directorate": "DCS",
#             "rankOrGrade": "Cdre",
#             "designation": "Deputy Director",
#             "roles": ["Deputy_Director"],           # ← fixed typo
#             "email": "ibrahim.yusuf@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "NAF/12345",
#             "fullName": "Paul Emeka",
#             "type": "military",
#             "directorate": "DCS",
#             "rankOrGrade": "Ft. Cmdr",
#             "designation": "Senior Staff Officer",
#             "roles": ["SSO"],
#             "email": "paul.emeka@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "DSA/CIV/0010",
#             "fullName": "Bello Mustapha",
#             "type": "civilian",
#             "directorate": "DCS",
#             "rankOrGrade": "Grade Level 10",
#             "designation": "Space Scientist 1",
#             "roles": ["Civilian Officer"],
#             "email": "bello.mustapha@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "DSA/CIV/0245",
#             "fullName": "Ubong Udofia",
#             "type": "civilian",
#             "directorate": "DCS",
#             "rankOrGrade": "Grade Level 8",
#             "designation": "ENG OFFR 1",
#             "roles": [],
#             "email": "ubong.udofia@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "NA/1976F",
#             "fullName": "Fatima Ahmad",
#             "type": "military",
#             "directorate": "DCS",
#             "rankOrGrade": "Staff Sergeant",          # ← fixed spelling
#             "designation": "Space Technician",
#             "roles": [],
#             "email": "fatima.ahmad@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         },
#         {
#             "_id": "NA/9167",
#             "fullName": "Ibrahim Bello",
#             "type": "military",
#             "directorate": "DOA",
#             "rankOrGrade": "Lieutenant Colonel",
#             "designation": "SO1 Administration",
#             "roles": ["SO1-DOA"],
#             "email": "ibrahim.bello@dsa.mil.ng",
#             "isActive": True,
#             "createdAt": datetime.utcnow()
#         }
#     ]
    
#     inserted = 0
#     for doc in samples:
#         try:
#             db.staff.insert_one(doc)
#             inserted += 1
#         except DuplicateKeyError:
#             pass
    
#     print(f"→ Sample staff: {inserted} new inserted")


# # ────────────────────────────────────────────────
# #  MAIN
# # ────────────────────────────────────────────────
# def main():
#     print("Initializing MongoDB for Leave/Pass System\n")
    
#     try:
#         client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
#         # Test connection
#         client.admin.command('ping')
#         db = client.get_database()   # or client[Config.DATABASE_NAME] if you have it
        
#         print("OK: Connected to MongoDB")
#         print("Database name:", db.name)
#         print("Current collections:", db.list_collection_names())
#         print("-" * 50)
        
#         create_collections_and_indexes(db)
#         insert_directorates(db)
        
#         # Comment out if you don't want sample data every time
#         insert_sample_staff(db)
        
#         print("\n" + "="*50)
#         print("Setup completed successfully!")
#         print("You can now start building the Flask application.")
        
#     except Exception as e:
#         print("ERROR: Failed to connect or initialize MongoDB")
#         print(str(e))
#         sys.exit(1)
#     finally:
#         if 'client' in locals():
#             client.close()


# if __name__ == "__main__":
#     main()