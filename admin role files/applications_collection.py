# create_applications_collection_fixed.py
from pymongo import MongoClient
from datetime import datetime

def create_applications_collection():
    """
    Create / update applications collection schema to match the ACTUAL structure
    used in start_application.py
    """
    
    client = MongoClient("mongodb://localhost:27017/")
    db = client["dsa_pass_leave"]
    
    print("="*70)
    print("CREATING / UPDATING APPLICATIONS COLLECTION SCHEMA")
    print("To match the document structure from start_application.py")
    print("="*70)
    
    # ────────────────────────────────────────────────────────────────
    # Schema that closely matches your current document structure
    # ────────────────────────────────────────────────────────────────
    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "referenceId",
                "applicantName",
                "applicantId",
                "leave_type",
                "directorate",
                "status",
                "approvalChain",
                "finalApproval",
                "createdAt",
                "updatedAt",
                # strongly recommended to require these too
                "dates",
                "tacosDetails",
                "validation",
                "leaveBalances"
            ],
            "properties": {
                # ─── Core identification ───
                "referenceId": {
                    "bsonType": "string",
                    "description": "Unique reference ID for the application"
                },
                "applicantName": {"bsonType": "string"},
                "applicantId": {"bsonType": "string"},

                # ─── Leave type & status ───
                "leave_type": {
                    "bsonType": "string",
                    "enum": ["annual", "casual", "compassionate", "sick", "maternity", "paternity", "disembarkation", "terminal"]
                },
                "directorate": {"bsonType": "string"},
                "status": {
                    "bsonType": "string",
                    "enum": ["pending", "approved", "rejected", "issued", "cancelled"]
                },

                # ─── Dates ───
                "dates": {
                    "bsonType": "object",
                    "properties": {
                        "applicationDate": {"bsonType": "date"},
                        "effectiveDate": {"bsonType": "date"},
                        "endDate": {"bsonType": "date"}
                    }
                },

                # ─── Core leave details (now at root level) ───
                "startDate": {"bsonType": "date"},
                "endDate": {"bsonType": "date"},
                "effectiveDate": {"bsonType": "date"},
                "numberOfDays": {"bsonType": "int"},
                "reason": {"bsonType": "string"},               # ← note: reason, not reasons
                "placeIntended": {"bsonType": "string"},
                "contactAddress": {"bsonType": "string"},
                "telephone": {"bsonType": ["string", "null"]},
                "name_of_reliever": {"bsonType": ["string", "null"]},
                "appt_of_reliever": {"bsonType": ["string", "null"]},
                "attachments": {
                    "bsonType": ["array", "null"],
                    "items": {
                        "bsonType": "object",
                        "properties": {
                            "gridfs_id": {"bsonType": "string"},
                            "filename": {"bsonType": "string"},
                            "contentType": {"bsonType": "string"},
                            "size": {"bsonType": "int"},
                            "uploadedAt": {"bsonType": "date"}
                        }
                    }
                },

                # ─── TACOS details ───
                "tacosDetails": {
                    "bsonType": "object",
                    "properties": {
                        "hasMedicalCertificate": {"bsonType": "bool"},
                        "hospitalized": {"bsonType": "bool"},
                        "firstHospitalization": {"bsonType": "bool"},
                        "outsideNigeria": {"bsonType": "bool"},
                        "expectedDeliveryDate": {"bsonType": ["date", "null"]},
                        "attachmentMonths": {"bsonType": ["int", "null"]},
                        "calendarDays": {"bsonType": "int"}
                    }
                },

                # ─── Validation result ───
                "validation": {
                    "bsonType": "object",
                    "properties": {
                        "isValid": {"bsonType": "bool"},
                        "validationMessage": {"bsonType": ["string", "null"]},
                        "metadata": {"bsonType": ["object", "null"]},
                        "validatedAt": {"bsonType": "date"}
                    }
                },

                # ─── Approval ───
                "approvalChain": {
                    "bsonType": "array",
                    "items": {
                        "bsonType": "object",
                        "properties": {
                            "role": {"bsonType": "string"},
                            "approverId": {"bsonType": "string"},
                            "approverName": {"bsonType": ["string", "null"]},
                            "approverRank": {"bsonType": ["string", "null"]},
                            "approverDesignation": {"bsonType": ["string", "null"]},
                            "status": {"bsonType": "string", "enum": ["pending", "approved", "rejected"]},
                            "comments": {"bsonType": ["string", "null"]},
                            "timestamp": {"bsonType": ["date", "null"]},
                            "forward_status": {"bsonType": ["string", "null"]},
                            "forwardedAt": {"bsonType": ["date", "null"]}
                        },
                        "required": ["role", "approverId", "status"]
                    }
                },

                "finalApproval": {
                    "bsonType": "object",
                    "properties": {
                        "approverId": {"bsonType": "string"},
                        "status": {"bsonType": "string", "enum": ["pending", "approved", "rejected"]},
                        "comments": {"bsonType": ["string", "null"]},
                        "timestamp": {"bsonType": ["date", "null"]},
                        "receipt": {
                            "bsonType": "object",
                            "properties": {
                                "receiptNumber": {"bsonType": ["string", "null"]},
                                "issuedDate": {"bsonType": ["date", "null"]},
                                "pdfUrl": {"bsonType": ["string", "null"]}
                            }
                        }
                    },
                    "required": ["approverId", "status"]
                },

                # ─── Snapshots & metadata ───
                "leaveBalances": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "annualRemaining": {"bsonType": ["int", "null"]},
                        "compassionateUsed": {"bsonType": ["int", "null"]},
                        "casualCalendarDays": {"bsonType": ["int", "null"]},
                        "sickThisYear": {"bsonType": ["int", "null"]},
                        "sickRolling12m": {"bsonType": ["int", "null"]},
                        "terminalGranted": {"bsonType": ["bool", "null"]}
                    }
                },

                "tacosCompliance": {"bsonType": ["object", "null"]},

                "notifications": {
                    "bsonType": "array",
                    "items": {"bsonType": "object"}
                },
                "auditTrail": {
                    "bsonType": "array",
                    "items": {"bsonType": "object"}
                },

                # ─── Timestamps ───
                "createdAt": {"bsonType": "date"},
                "updatedAt": {"bsonType": "date"},
                "submittedAt": {"bsonType": ["date", "null"]}
            },
            "additionalProperties": True   # ← allows future fields
        }
    }

    try:
        # If collection exists → modify validator
        if "applications" in db.list_collection_names():
            print("Collection 'applications' already exists → updating validator...")
            result = db.command({
                "collMod": "applications",
                "validator": validator,
                "validationLevel": "moderate",   # or "strict"
                "validationAction": "error"
            })
            print("  → Validator updated successfully")
        else:
            print("Creating new collection 'applications'...")
            db.create_collection("applications", validator=validator["$jsonSchema"])
            print("  → Collection created with validator")

        # ─── Indexes ───────────────────────────────────────────────
        print("Creating indexes...")
        
        db.applications.create_index([("referenceId", 1)], unique=True)
        db.applications.create_index([("applicantId", 1)])
        db.applications.create_index([("status", 1)])
        db.applications.create_index([("directorate", 1), ("status", 1)])
        db.applications.create_index([("leave_type", 1)])
        db.applications.create_index([("createdAt", -1)])
        db.applications.create_index([("approvalChain.status", 1)])
        
        print("  → Indexes created")

        print("\n" + "="*70)
        print("SCHEMA UPDATE COMPLETE")
        print("="*70)
        print("\nYou should now be able to save documents with the structure")
        print("you are using in start_application.py")
        print("\nNext step: test form submission again")

    except Exception as e:
        print("\nERROR during collection setup:")
        print(str(e))
        return False

    finally:
        client.close()

    return True


if __name__ == "__main__":
    print("APPLICATIONS COLLECTION SCHEMA FIX SCRIPT\n")
    success = create_applications_collection()
    
    if success:
        print("\nRecommended next steps:")
        print("1. Run your Flask application")
        print("2. Try submitting a new leave application")
        print("3. If you still get validation error → copy the FULL error message")
        print("   (especially the 'errInfo' part) and share it here")
    else:
        print("\nFix did NOT complete successfully.")