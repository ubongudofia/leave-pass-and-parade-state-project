# create_medical_records_collection.py
from pymongo import MongoClient
from datetime import datetime
import random

def create_medical_records_collection():
    """
    Create medical_records collection with proper schema for TACOS compliance.
    Medical records are needed for:
    1. Sick leave validation (TACOS 08.04)
    2. Hospitalization tracking (TACOS 08.04c, 08.04e)
    3. Medical certificate verification
    """
    
    client = MongoClient("mongodb://localhost:27017/")
    db = client["dsa_pass_leave"]
    
    print("="*60)
    print("MEDICAL RECORDS COLLECTION SETUP")
    print("="*60)
    
    # Drop existing collection if it exists (optional)
    # db.medical_records.drop()
    
    # Define schema for medical records
    schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "serviceNumber",
                "fullName",
                "recordType",
                "issueDate",
                "createdAt"
            ],
            "properties": {
                "serviceNumber": {
                    "bsonType": "string",
                    "description": "Staff service number"
                },
                "fullName": {
                    "bsonType": "string",
                    "description": "Staff full name"
                },
                "directorate": {
                    "bsonType": "string",
                    "description": "Staff directorate"
                },
                "recordType": {
                    "bsonType": "string",
                    "enum": [
                        "medical_certificate",
                        "hospitalization",
                        "outpatient_treatment",
                        "specialist_referral",
                        "sick_parade",
                        "dental",
                        "optical",
                        "medical_board"
                    ],
                    "description": "Type of medical record"
                },
                "subType": {
                    "bsonType": "string",
                    "description": "Subtype for further classification"
                },
                "issueDate": {
                    "bsonType": "date",
                    "description": "Date medical record was issued"
                },
                "validFrom": {
                    "bsonType": "date",
                    "description": "Date from which medical condition started"
                },
                "validTo": {
                    "bsonType": "date",
                    "description": "Date medical condition ended"
                },
                "admissionDate": {
                    "bsonType": ["date", "null"],
                    "description": "Hospital admission date (for hospitalization records)"
                },
                "dischargeDate": {
                    "bsonType": ["date", "null"],
                    "description": "Hospital discharge date (for hospitalization records)"
                },
                "hospitalName": {
                    "bsonType": "string",
                    "description": "Name of hospital/clinic"
                },
                "hospitalType": {
                    "bsonType": "string",
                    "enum": ["government", "military", "private", "teaching"],
                    "description": "Type of hospital"
                },
                "doctorName": {
                    "bsonType": "string",
                    "description": "Name of attending doctor"
                },
                "doctorRank": {
                    "bsonType": "string",
                    "description": "Rank/Title of doctor"
                },
                "diagnosis": {
                    "bsonType": "string",
                    "description": "Medical diagnosis"
                },
                "icd10Code": {
                    "bsonType": "string",
                    "description": "ICD-10 diagnosis code"
                },
                "recommendedLeaveDays": {
                    "bsonType": "int",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Number of sick leave days recommended"
                },
                "actualLeaveDays": {
                    "bsonType": "int",
                    "minimum": 0,
                    "description": "Actual sick leave days taken"
                },
                "isContagious": {
                    "bsonType": "bool",
                    "description": "Whether condition is contagious"
                },
                "requiresIsolation": {
                    "bsonType": "bool",
                    "description": "Whether isolation is required"
                },
                "requiresFollowUp": {
                    "bsonType": "bool",
                    "description": "Whether follow-up treatment is needed"
                },
                "followUpDate": {
                    "bsonType": ["date", "null"],
                    "description": "Date for follow-up appointment"
                },
                "isFirstOccurrence": {
                    "bsonType": "bool",
                    "description": "Whether this is first occurrence of condition"
                },
                "previousOccurrences": {
                    "bsonType": "int",
                    "minimum": 0,
                    "description": "Number of previous occurrences"
                },
                "attachments": {
                    "bsonType": "array",
                    "items": {
                        "bsonType": "object",
                        "properties": {
                            "gridfs_id": {"bsonType": "string"},
                            "filename": {"bsonType": "string"},
                            "fileType": {"bsonType": "string"},
                            "description": {"bsonType": "string"}
                        }
                    }
                },
                "status": {
                    "bsonType": "string",
                    "enum": ["active", "closed", "archived", "rejected", "pending_review"],
                    "description": "Status of medical record"
                },
                "verificationStatus": {
                    "bsonType": "string",
                    "enum": ["pending", "verified", "rejected", "requires_clarification"],
                    "description": "Verification status by medical officer"
                },
                "verifiedBy": {
                    "bsonType": "string",
                    "description": "Service number of verifying medical officer"
                },
                "verifiedAt": {
                    "bsonType": ["date", "null"],
                    "description": "Date of verification"
                },
                "tacosReference": {
                    "bsonType": "object",
                    "properties": {
                        "chapter": {"bsonType": "string"},
                        "section": {"bsonType": "string"},
                        "paragraph": {"bsonType": "string"},
                        "notes": {"bsonType": "string"}
                    }
                },
                "notes": {
                    "bsonType": "string",
                    "description": "Additional notes/comments"
                },
                "createdAt": {"bsonType": "date"},
                "updatedAt": {"bsonType": "date"}
            }
        }
    }
    
    # Create collection with schema validation
    try:
        if "medical_records" in db.list_collection_names():
            # Modify existing collection
            db.command({
                "collMod": "medical_records",
                "validator": schema["$jsonSchema"]
            })
            print("✓ Updated medical_records collection schema")
        else:
            # Create new collection
            db.create_collection("medical_records", validator=schema["$jsonSchema"])
            print("✓ Created medical_records collection with schema validation")
        
        # Create indexes
        db.medical_records.create_index([("serviceNumber", 1), ("issueDate", -1)])
        db.medical_records.create_index([("recordType", 1)])
        db.medical_records.create_index([("admissionDate", 1)])
        db.medical_records.create_index([("status", 1)])
        db.medical_records.create_index([("verificationStatus", 1)])
        db.medical_records.create_index([("createdAt", -1)])
        
        # Compound indexes for common queries
        db.medical_records.create_index([
            ("serviceNumber", 1),
            ("recordType", 1),
            ("issueDate", -1)
        ])
        
        db.medical_records.create_index([
            ("serviceNumber", 1),
            ("admissionDate", 1),
            ("dischargeDate", 1)
        ])
        
        print("✓ Created all necessary indexes")
        
    except Exception as e:
        print(f"✗ Error setting up collection: {e}")
        return False
    
    print("\n" + "="*60)
    print("MEDICAL RECORDS COLLECTION CREATED")
    print("="*60)
    
    # Verify the setup
    coll_stats = db.command("collstats", "medical_records")
    print(f"\nCollection Statistics:")
    print(f"• Collection: {coll_stats['ns']}")
    print(f"• Documents: {coll_stats['count']}")
    print(f"• Size: {coll_stats['size'] / 1024 / 1024:.2f} MB")
    print(f"• Indexes: {len(coll_stats.get('indexSizes', {}))}")
    
    client.close()
    return True






if __name__ == "__main__":
    print("MEDICAL RECORDS COLLECTION SETUP")
    print("="*60)
    
    # 1. Create collection with schema
    create_medical_records_collection()
    
    
    print("\n" + "="*60)
    print("SETUP COMPLETE")
    print("="*60)
    print("\nMedical records collection is now ready for:")
    print("1. Sick leave validation (TACOS 08.04)")
    print("2. Hospitalization tracking (TACOS 08.04c, 08.04e)")
    print("3. Medical certificate verification")
    print("4. First hospitalization checks")
    print("5. Contagious disease tracking")