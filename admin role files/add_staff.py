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


def insert_sample_staff(db):
    """Insert sample staff (idempotent)"""
    samples = [
        {
            "_id": "NN/0987",
            "fullName": "Chidima Philips",
            "type": "military",
            "directorate": "DNPT",
            "rankOrGrade": "Sqdr Ldr",
            "designation": "Senior Staff Officer",
            "roles": ["SSO"],
            "email": "chidima.philips@dsa.mil.ng",
            "isActive": True,
            "createdAt": datetime.utcnow()
        }
        # {
        #     "_id": "NN/45678",
        #     "fullName": "Tolu John",
        #     "type": "military",
        #     "directorate": "DCS",
        #     "rankOrGrade": "MWO",
        #     "designation": "Chief Clerk",
        #     "roles": ["Chief Clerk"],
        #     "email": "tolu.john@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "NA/2368",
        #     "fullName": "Markus Adeyemi",
        #     "type": "military",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "WO",
        #     "designation": "Chief Clerk",
        #     "roles": ["Chief Clerk"],
        #     "email": "markus.adeyemi@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "NAF/67890",
        #     "fullName": "Emmanuel Mohammed",
        #     "type": "military",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "Air Cdre",
        #     "designation": "Deputy Director",
        #     "roles": ["Deputy_Director"],           
        #     "email": "emmanuel.mohammed@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "NN/67890",
        #     "fullName": "Paul Emeka",
        #     "type": "military",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "Lt. Cmdr",
        #     "designation": "Senior Staff Officer",
        #     "roles": ["SSO"],
        #     "email": "paul.emeka@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "DSA/CIV/0120",
        #     "fullName": "Sunday Musa",
        #     "type": "civilian",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "Grade Level 10",
        #     "designation": "Space Scientist 1",
        #     "roles": ["Civilian Officer"],
        #     "email": "sunday.musa@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "DSA/CIV/0365",
        #     "fullName": "Maryam Jerry",
        #     "type": "civilian",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "Grade Level 8",
        #     "designation": "ENG OFFR 1",
        #     "roles": [],
        #     "email": "maryam.jerry@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # },
        # {
        #     "_id": "NA/1672",
        #     "fullName": "Tosin Ubong",
        #     "type": "military",
        #     "directorate": "DNPT",
        #     "rankOrGrade": "Staff Sergeant",          
        #     "designation": "Space Technician",
        #     "roles": [],
        #     "email": "tosin.ubong@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # }
        # ,{
        #     "_id": "NA/9167",
        #     "fullName": "Ibrahim Bello",
        #     "type": "military",
        #     "directorate": "DOA",
        #     "rankOrGrade": "Lieutenant Colonel",
        #     "designation": "SO1 Administration",
        #     "roles": ["SO1-DOA"],
        #     "email": "ibrahim.bello@dsa.mil.ng",
        #     "isActive": True,
        #     "createdAt": datetime.utcnow()
        # }
    ]
    
    inserted = 0
    for doc in samples:
        try:
            db.staff.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            pass
    
    print(f"→ Sample staff: {inserted} new inserted")


# ────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────
def main():
    print("Initializing MongoDB for Leave/Pass System\n")
    
    try:
        client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        client.admin.command('ping')
        db = client.get_database()   # or client[Config.DATABASE_NAME] if you have it
        
        print("OK: Connected to MongoDB")
        print("Database name:", db.name)
        print("Current collections:", db.list_collection_names())
        print("-" * 50)
        
        # create_collections_and_indexes(db)
        # insert_directorates(db)
        
        # Comment out if you don't want sample data every time
        insert_sample_staff(db)
        
        print("\n" + "="*50)
        print("Setup completed successfully!")
        print("You can now start building the Flask application.")
        
    except Exception as e:
        print("ERROR: Failed to connect or initialize MongoDB")
        print(str(e))
        sys.exit(1)
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    main()