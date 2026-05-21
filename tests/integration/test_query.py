"""
Test of pipelines (simple aggregations first, up to complex aggregations: the ones in the scripts).
Note: That may detect change in the key numbers in receipts.
"""

import pytest

from carrefour_receipts_api.mongodb_querying import query_collection

# connection string locally

# Pipeline in order to query the collection
pipeline_summary = [
    # Step 1: Extract year and month from "attributes.dateKey"
    {
        "$addFields": {
            "year": {"$substr": ["$attributes.dateKey", 0, 4]},  # Extract year
            "month": {"$substr": ["$attributes.dateKey", 4, 2]},  # Extract month
            "yearMonthDay": {
                "$toDate": {
                    # Convert to date format YYYY-MM-DD
                    "$concat": [
                        {"$substr": ["$attributes.dateKey", 0, 4]},
                        "-",
                        {"$substr": ["$attributes.dateKey", 4, 2]},
                        "-01",
                    ]
                }
            },
        }
    },
    # Step 2: Group by year and month, and calculate the total amount
    {
        "$group": {
            "_id": {"year": "$year", "month": "$month"},  # Group by year and month
            "count": {"$sum": 1},  # Count the number of documents for each group
            "totalAmountBeforeDiscount": {
                "$sum": "$attributes.totalAmountBeforeDiscount"
            },
            "totalAmountImmediateDiscount": {
                "$sum": "$attributes.totalAmountImmediateDiscount"
            },
            "totalAmountDeferredDiscount": {
                "$sum": "$attributes.totalAmountDeferredDiscount"
            },
            "totalPaidAmount": {
                "$sum": "$attributes.totalPaidAmount"
            },  # Sum up the totalPaidAmount,
            "yearMonthDay": {"$first": "$yearMonthDay"},  # Convert yearMonthDay to date
        }
    },
    # Step 3: Project the fields to include in the final output
    {
        "$project": {
            "_id": 0,
            "year": "$_id.year",
            "month": "$_id.month",
            "count": "$count",
            "totalAmountBeforeDiscount": "$totalAmountBeforeDiscount",
            "totalAmountImmediateDiscount": "$totalAmountImmediateDiscount",
            "totalAmountDeferredDiscount": "$totalAmountDeferredDiscount",
            "totalPaidAmount": "$totalPaidAmount",
            "yearMonthDay": "$yearMonthDay",  # Include yearMonthDay for plotting
        }
    },
    # Step 4: Sort the results by year and month
    {"$sort": {"year": -1, "month": -1}},
]
@pytest.mark.skip(reason="This test requires a live MongoDB instance")
def test_simple_aggregation():
    """
    Test a simple aggregation pipeline.
    """
    df = query_collection(pipeline_summary, collection_name="receipts")
    assert not df.empty, "The aggregation result should not be empty"
    assert "year" in df.columns, "The 'year' column should be present in the result"
    assert "month" in df.columns, "The 'month' column should be present in the result"
    assert "count" in df.columns, "The 'count' column should be present in the result"
    assert "totalPaidAmount" in df.columns, "The 'totalPaidAmount' column should be present in the result"

@pytest.mark.skip(reason="Complex aggregation tests are not implemented yet")
def test_complex_aggregation():
    pass
