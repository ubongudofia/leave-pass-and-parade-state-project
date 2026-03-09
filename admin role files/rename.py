from pymongo import MongoClient, ASCENDING, DESCENDING

client = MongoClient("mongodb://localhost:27017/")
db = client["dsa_pass_leave"]

old_collection = db.staff_backup
new_collection = db.staff

print("🚀 Starting migration...")

# -------------------------
# STEP 1: MIGRATE DATA
# -------------------------
for doc in old_collection.find():
    new_doc = doc.copy()

    # Move _id → service_number
    new_doc["service_number"] = str(doc["_id"])

    # Remove _id so MongoDB generates a new one
    del new_doc["_id"]

    new_collection.insert_one(new_doc)

print("✅ Data migration complete")

# -------------------------
# STEP 2: COPY INDEXES
# -------------------------
indexes = old_collection.index_information()

for name, index in indexes.items():
    if name == "_id_":
        continue  # skip default index

    keys = index["key"]
    unique = index.get("unique", False)

    print(f"🔧 Recreating index: {name}")

    new_collection.create_index(
        keys,
        name=name,
        unique=unique
    )

print("✅ Indexes copied")

# -------------------------
# STEP 3: ADD service_number UNIQUE INDEX
# -------------------------
print("🔧 Adding service_number unique index")

new_collection.create_index(
    [("service_number", ASCENDING)],
    unique=True,
    name="service_number_1"
)

print("✅ service_number index created")

# -------------------------
# STEP 4: SWAP COLLECTIONS
# -------------------------
print("🔁 Swapping collections...")

# old_collection.rename("staff_backup")   # backup
# new_collection.rename("staff")          # new becomes main

print("🎉 Migration complete!")