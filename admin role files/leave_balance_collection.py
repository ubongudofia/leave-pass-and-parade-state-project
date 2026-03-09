# leave_balance_collection.py - CORRECTED VERSION
from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import sys

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "dsa_pass_leave"

def create_leave_balances_collection():
    """Create and configure the leave_balances collection."""
    
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        
        print(f"Connected to database: {DATABASE_NAME}")
        print("="*60)
        print("SETTING UP LEAVE_BALANCES COLLECTION")
        print("="*60)
        
        # ──────────────────────────────────────────────────────────────
        # 1. CREATE COLLECTION (if it doesn't exist)
        # ──────────────────────────────────────────────────────────────
        collection_name = 'leave_balances'
        
        if collection_name in db.list_collection_names():
            print(f"⚠️  Collection '{collection_name}' already exists")
            response = input("Do you want to recreate it? (y/n): ")
            if response.lower() == 'y':
                db[collection_name].drop()
                print(f"✓ Dropped existing '{collection_name}' collection")
                db.create_collection(collection_name)
                print(f"✓ Created new '{collection_name}' collection")
            else:
                print(f"✓ Using existing '{collection_name}' collection")
        else:
            db.create_collection(collection_name)
            print(f"✓ Created '{collection_name}' collection")
        
        # ──────────────────────────────────────────────────────────────
        # 2. CREATE INDEXES
        # ──────────────────────────────────────────────────────────────
        print("\nCreating indexes...")
        
        # Primary index: serviceNumber + year (unique)
        db.leave_balances.create_index([
            ("serviceNumber", ASCENDING),
            ("year", DESCENDING)
        ], unique=True, name="service_year_unique")
        print("  ✓ Created index: service_year_unique (serviceNumber, year)")
        
        # Fast lookup by serviceNumber
        db.leave_balances.create_index([
            ("serviceNumber", ASCENDING)
        ], name="service_lookup")
        print("  ✓ Created index: service_lookup (serviceNumber)")
        
        # For reporting by year and directorate
        db.leave_balances.create_index([
            ("year", ASCENDING),
            ("directorate", ASCENDING)
        ], name="year_directorate_stats")
        print("  ✓ Created index: year_directorate_stats (year, directorate)")
        
        # For quick grade-based queries
        db.leave_balances.create_index([
            ("grade", ASCENDING)
        ], name="grade_lookup")
        print("  ✓ Created index: grade_lookup (grade)")
        
        # For active/inactive staff filtering
        db.leave_balances.create_index([
            ("isActive", ASCENDING)
        ], name="active_status")
        print("  ✓ Created index: active_status (isActive)")
        
        print("✓ All indexes created successfully")
        
        # ──────────────────────────────────────────────────────────────
        # 3. DEFINE COLLECTION VALIDATION SCHEMA
        # ──────────────────────────────────────────────────────────────
        print("\nSetting up schema validation...")
        
        validation_schema = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": [
                    "serviceNumber", 
                    "year",
                    "annualRemaining",
                    "compassionateUsed",
                    "casualCalendarDays",
                    "sickThisYear",
                    "sickRolling12m",
                    "terminalGranted"
                ],
                "properties": {
                    "serviceNumber": {
                        "bsonType": "string",
                        "description": "Staff service number (from _id in staff collection)"
                    },
                    "fullName": {
                        "bsonType": "string",
                        "description": "Staff full name"
                    },
                    "directorate": {
                        "bsonType": "string",
                        "description": "Staff directorate"
                    },
                    "grade": {
                        "bsonType": "int",
                        "minimum": 0,
                        "maximum": 15,
                        "description": "CONDSASS grade level (2-15), 0 if unknown"
                    },
                    "year": {
                        "bsonType": "int",
                        "minimum": 2020,
                        "maximum": 2100,
                        "description": "Year for which balances apply"
                    },
                    "annualRemaining": {
                        "bsonType": "int",
                        "minimum": 0,
                        "maximum": 30,
                        "description": "Remaining annual leave days"
                    },
                    "annualEntitlement": {
                        "bsonType": "int",
                        "minimum": 21,
                        "maximum": 30,
                        "description": "Annual leave entitlement"
                    },
                    "compassionateUsed": {
                        "bsonType": "int",
                        "minimum": 0,
                        "maximum": 10,
                        "description": "Compassionate leave days used"
                    },
                    "casualCalendarDays": {
                        "bsonType": "int",
                        "minimum": 0,
                        "description": "Casual leave calendar days used"
                    },
                    "sickThisYear": {
                        "bsonType": "int",
                        "minimum": 0,
                        "description": "Sick leave days used this calendar year"
                    },
                    "sickRolling12m": {
                        "bsonType": "int",
                        "minimum": 0,
                        "description": "Sick leave days in rolling 12 months"
                    },
                    "terminalGranted": {
                        "bsonType": "bool",
                        "description": "Whether terminal leave has been granted"
                    },
                    "isActive": {
                        "bsonType": "bool",
                        "description": "Whether staff is active"
                    },
                    "lastUpdatedBy": {
                        "bsonType": "string",
                        "description": "Who last updated this record"
                    },
                    "notes": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "string"
                        },
                        "description": "Notes about balance changes"
                    },
                    "createdAt": {
                        "bsonType": "date",
                        "description": "When this record was created"
                    },
                    "updatedAt": {
                        "bsonType": "date",
                        "description": "When this record was last updated"
                    }
                }
            }
        }
        
        # Apply validation (MongoDB 3.6+)
        try:
            db.command({
                "collMod": collection_name,
                "validator": validation_schema,
                "validationLevel": "strict"
            })
            print("✓ Schema validation applied")
        except Exception as e:
            print(f"⚠️  Could not apply schema validation: {e}")
            print("  (This is okay if you're using MongoDB < 3.6)")
        
        # ──────────────────────────────────────────────────────────────
        # 4. INITIALIZE BALANCES FOR EXISTING STAFF (CORRECTED)
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("INITIALIZING LEAVE BALANCES FOR STAFF")
        print("="*60)
        
        if 'staff' not in db.list_collection_names():
            print("⚠️  No 'staff' collection found. Cannot initialize balances.")
            print("   Please create staff collection first.")
            return
        
        current_year = datetime.now().year
        print(f"Initializing balances for year: {current_year}")
        
        # Get all active staff
        active_staff = db.staff.find({"isActive": True})
        staff_list = list(active_staff)
        
        if not staff_list:
            print("⚠️  No active staff found in 'staff' collection")
            return
        
        print(f"Found {len(staff_list)} active staff members")
        
        initialized_count = 0
        skipped_count = 0
        error_count = 0
        
        for staff in staff_list:
            # CORRECTED: Get service number from _id field
            service_number = staff.get('_id')
            if not service_number:
                # Try alternative field names
                service_number = staff.get('serviceNumber') or staff.get('service_number')
            
            if not service_number:
                print(f"  ⚠️  Skipping staff without identifier: {staff.get('fullName', 'Unknown')}")
                error_count += 1
                continue
            
            # Ensure service_number is a string
            if not isinstance(service_number, str):
                service_number = str(service_number)
            
            # Check if balance already exists for current year
            existing_balance = db.leave_balances.find_one({
                "serviceNumber": service_number,
                "year": current_year
            })
            
            if existing_balance:
                print(f"  ⚠️  Balance exists for {service_number} - skipping")
                skipped_count += 1
                continue
            
            # Extract grade from rankOrGrade
            grade = 0
            rank_or_grade = staff.get('rankOrGrade', '')
            
            if 'Grade Level' in rank_or_grade:
                try:
                    # Extract numeric grade from "Grade Level 8"
                    grade_str = rank_or_grade.split('Grade Level')[-1].strip()
                    grade = int(grade_str)
                except (ValueError, IndexError):
                    print(f"  ⚠️  Could not parse grade from '{rank_or_grade}' for {service_number}")
                    grade = 0
            elif any(mil_rank in rank_or_grade for mil_rank in ['Maj Gen', 'Brig Gen', 'Col', 'Lt Col', 'Maj', 'Capt', 'Lt', '2Lt']):
                # Military ranks - assign appropriate CONDSASS grade
                # This mapping needs to be defined per your organization
                grade = 7  # Default military grade - adjust as needed
            else:
                # Try to extract number from other formats
                try:
                    import re
                    numbers = re.findall(r'\d+', rank_or_grade)
                    if numbers:
                        grade = int(numbers[0])
                except:
                    grade = 0
            
            # Determine annual entitlement based on grade
            if 2 <= grade <= 6:
                annual_entitlement = 21
            elif 7 <= grade <= 15:
                annual_entitlement = 30
            else:
                annual_entitlement = 21  # Default for unknown grade
            
            # Create balance document
            balance_doc = {
                "serviceNumber": service_number,
                "fullName": staff.get('fullName', ''),
                "directorate": staff.get('directorate', ''),
                "grade": grade,
                "year": current_year,
                "annualRemaining": annual_entitlement,
                "annualEntitlement": annual_entitlement,
                "compassionateUsed": 0,
                "casualCalendarDays": 0,
                "sickThisYear": 0,
                "sickRolling12m": 0,
                "terminalGranted": False,
                "isActive": staff.get('isActive', True),
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
            
            try:
                db.leave_balances.insert_one(balance_doc)
                print(f"  ✓ Created balance for {service_number} ({staff.get('fullName')})")
                print(f"    Grade: {grade}, Annual Entitlement: {annual_entitlement} days")
                initialized_count += 1
            except Exception as e:
                print(f"  ✗ Error creating balance for {service_number}: {e}")
                error_count += 1
        
        # ──────────────────────────────────────────────────────────────
        # 5. SUMMARY REPORT
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("SETUP COMPLETE - SUMMARY")
        print("="*60)
        
        total_balances = db.leave_balances.count_documents({})
        current_year_balances = db.leave_balances.count_documents({"year": current_year})
        
        print(f"\nCollection: {collection_name}")
        print(f"Total documents: {total_balances}")
        print(f"Documents for {current_year}: {current_year_balances}")
        print(f"\nInitialization results:")
        print(f"  ✓ Successfully initialized: {initialized_count}")
        print(f"  ⚠️  Already existed (skipped): {skipped_count}")
        print(f"  ✗ Errors: {error_count}")
        
        # Show sample of created balances
        if initialized_count > 0:
            print(f"\nSample of created balances:")
            sample = db.leave_balances.find({"year": current_year}).limit(3)
            for balance in sample:
                print(f"  • {balance['serviceNumber']}: {balance['annualRemaining']} days annual leave")
        
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print("1. Verify balances were created correctly:")
        print(f"   db.leave_balances.find({{year: {current_year}}}).limit(5).pretty()")
        print("\n2. Check for any staff without balances:")
        print("   // In MongoDB shell:")
        print(f"   year = {current_year};")
        print("   db.staff.aggregate([")
        print("     {$lookup: {")
        print("       from: 'leave_balances',")
        print("       localField: '_id',")  # CHANGED: Use _id instead of serviceNumber
        print("       foreignField: 'serviceNumber',")
        print("       as: 'balances',")
        print("       pipeline: [{$match: {year: year}}]")
        print("     }}, {$match: {balances: {$size: 0}}}")
        print("   ])")
        print("\n3. Create balances for previous years if needed")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def create_balance_for_specific_staff():
    """Create or update balance for specific staff members."""
    
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    
    current_year = datetime.now().year
    
    print("\n" + "="*60)
    print("CREATE/UPDATE BALANCE FOR SPECIFIC STAFF")
    print("="*60)
    
    # Example staff based on your sample
    staff_updates = [
        {
            "serviceNumber": "DSA/CIV/0365",  # Maryam Jerry
            "fullName": "Maryam Jerry",
            "directorate": "DNPT",
            "grade": 8,  # From "Grade Level 8"
            "annualRemaining": 15,
            "compassionateUsed": 3,
            "casualCalendarDays": 2,
            "sickThisYear": 5,
            "sickRolling12m": 10,
            "notes": ["Initial balance set manually"]
        },
        {
            "serviceNumber": "NA/12345",  # Musa Ahmed (Maj Gen - military)
            "fullName": "Musa Ahmed",
            "directorate": "DCS",
            "grade": 15,  # High grade for military general
            "annualRemaining": 30,
            "compassionateUsed": 0,
            "casualCalendarDays": 0,
            "sickThisYear": 0,
            "sickRolling12m": 0,
            "notes": ["Military staff - Grade estimated"]
        },
        # Add more staff as needed
    ]
    
    for staff_data in staff_updates:
        service_number = staff_data['serviceNumber']
        
        # Check if exists
        existing = db.leave_balances.find_one({
            "serviceNumber": service_number,
            "year": current_year
        })
        
        update_data = {
            "serviceNumber": service_number,
            "fullName": staff_data['fullName'],
            "directorate": staff_data['directorate'],
            "grade": staff_data['grade'],
            "year": current_year,
            "annualRemaining": staff_data['annualRemaining'],
            "annualEntitlement": 21 if (2 <= staff_data['grade'] <= 6) else 30,
            "compassionateUsed": staff_data['compassionateUsed'],
            "casualCalendarDays": staff_data['casualCalendarDays'],
            "sickThisYear": staff_data['sickThisYear'],
            "sickRolling12m": staff_data['sickRolling12m'],
            "terminalGranted": False,
            "isActive": True,
            "notes": staff_data.get('notes', []),
            "updatedAt": datetime.utcnow()
        }
        
        if existing:
            # Update existing
            db.leave_balances.update_one(
                {"_id": existing['_id']},
                {"$set": update_data}
            )
            action = "Updated"
        else:
            # Create new
            update_data["createdAt"] = datetime.utcnow()
            db.leave_balances.insert_one(update_data)
            action = "Created"
        
        print(f"  {action} balance for {service_number}")
        print(f"    Annual: {staff_data['annualRemaining']} days remaining")
        print(f"    Compassionate used: {staff_data['compassionateUsed']} days")
        print(f"    Casual calendar days: {staff_data['casualCalendarDays']}")
    
    print("\n✓ Specific staff balances updated")

if __name__ == "__main__":
    print("LEAVE BALANCES COLLECTION SETUP - CORRECTED VERSION")
    print("="*60)
    
    # Step 1: Create collection and initialize all staff
    success = create_leave_balances_collection()
    
    if success:
        # Step 2: Optionally update specific staff
        response = input("\nDo you want to create/update balances for specific staff? (y/n): ")
        if response.lower() == 'y':
            create_balance_for_specific_staff()
        
        print("\n" + "="*60)
        print("SETUP COMPLETE!")
        print("="*60)
        print("\nYour leave_balances collection is ready.")
        print("\nTo query balances:")
        print(f"1. Get all balances for {datetime.now().year}:")
        print(f'   db.leave_balances.find({{year: {datetime.now().year}}})')
        print("\n2. Get balance for specific staff:")
        print('   db.leave_balances.find({serviceNumber: "DSA/CIV/0365"})')
        print("\n3. Get low annual leave (< 5 days):")
        print('   db.leave_balances.find({annualRemaining: {$lt: 5}})')
        print("\n4. Join with staff collection:")
        print('   db.staff.aggregate([')
        print('     {$lookup: {')
        print('       from: "leave_balances",')
        print('       localField: "_id",')
        print('       foreignField: "serviceNumber",')
        print('       as: "leaveInfo"')
        print('     }}')
        print('   ])')
    else:
        print("\n✗ Setup failed. Please check the error messages above.")
        sys.exit(1)