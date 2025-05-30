from mongomock import MongoClient

def test_pipeline_summary():
    pipeline = [...]  # Replace with actual pipeline_summary
    client = MongoClient()
    db = client["test_db"]
    collection = db["test_collection"]

    # Insert mock data
    collection.insert_many([
        {"attributes": {"dateKey": "20250501", "totalAmountBeforeDiscount": 100}},
        {"attributes": {"dateKey": "20250502", "totalAmountBeforeDiscount": 200}}
    ])

    result = list(collection.aggregate(pipeline))

    # Assertions
    assert len(result) == 2
    assert result[0]["dateKey"] == "20250501"
    assert result[0]["totalAmountBeforeDiscount"] == 100