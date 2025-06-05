import logging

from typing import List, Dict, Any

from carrefour_receipts_api.mongodb_builder import get_collection, get_database
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from pymongo import MongoClient
from pymongo.command_cursor import CommandCursor
import seaborn as sns


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Provide the mongodb atlas url to connect python to mongodb using pymongo
# CONNECTION_STRING = "mongodb+srv://user:pass@cluster.mongodb.net/myFirstDatabase"
CONNECTION_STRING = "mongodb://localhost:27017/"
DATA_DIRECTORY = "data" # Directory relative to the current directory by default the root of the project


# Carrefour Constants
BAG_EAN = "9713236189234"
STORE_ID = "0525-150-29"


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

# Define the aggregation pipeline
pipeline_extracts = [
    {
        "$unwind": {
            "path": "$attributes.products.coupon",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": "$_id",
            "dateKey": {"$first": "$attributes.dateKey"},
            "totalAmountBeforeDiscount": {
                "$first": "$attributes.totalAmountBeforeDiscount"
            },
            "couponDiscount": {"$sum": "$attributes.products.coupon.immediateDiscount"},
            "totalAmountImmediateDiscount": {
                "$first": "$attributes.totalAmountImmediateDiscount"
            },
            "totalAmountDeferredDiscount": {
                "$first": "$attributes.totalAmountDeferredDiscount"
            },
            "totalPaidAmount": {"$first": "$attributes.totalPaidAmount"},
            "paymentInfo": {"$first": "$attributes.paymentInfo"},
        }
    },
    {"$unwind": {"path": "$paymentInfo", "preserveNullAndEmptyArrays": True}},
    {
        "$group": {
            "_id": {
                "id": "$_id",
                "paymentChoice": "$paymentInfo.choice",
            },
            "dateKey": {"$first": "$dateKey"},
            "totalAmountBeforeDiscount": {"$first": "$totalAmountBeforeDiscount"},
            "couponDiscount": {"$first": "$couponDiscount"},
            "totalAmountImmediateDiscount": {"$first": "$totalAmountImmediateDiscount"},
            "totalAmountDeferredDiscount": {"$first": "$totalAmountDeferredDiscount"},
            "totalPaidAmount": {"$first": "$totalPaidAmount"},
            "paymentAmount": {"$sum": "$paymentInfo.amount"},
        }
    },
    {
        "$project": {
            "_id": 0,
            "id": "$_id.id",
            "dateKey": "$dateKey",
            "paymentChoice": "$_id.paymentChoice",
            "totalAmountBeforeDiscount": "$totalAmountBeforeDiscount",
            "couponDiscount": "$couponDiscount",
            "totalAmountImmediateDiscount": "$totalAmountImmediateDiscount",
            "totalAmountDeferredDiscount": "$totalAmountDeferredDiscount",
            "totalPaidAmount": "$totalPaidAmount",
            "paymentAmount": "$paymentAmount",
        }
    },
    {
        "$sort": {
            "dateKey": -1,
            "id": -1,
            "paymentChoice": 1,
        }
    },
]

pipeline_receipts = [
    # First pipeline: Process receipts data
    {
        "$unwind": {
            "path": "$attributes.products.coupon",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": "$_id",
            "dateKey": {"$first": "$attributes.dateKey"},
            "totalAmountBeforeDiscount": {
                "$first": "$attributes.totalAmountBeforeDiscount"
            },
            "couponDiscount": {"$sum": "$attributes.products.coupon.immediateDiscount"},
            "totalAmountImmediateDiscount": {
                "$first": "$attributes.totalAmountImmediateDiscount"
            },
            "totalAmountDeferredDiscount": {
                "$first": "$attributes.totalAmountDeferredDiscount"
            },
            "totalPaidAmount": {"$first": "$attributes.totalPaidAmount"},
            "vats": {"$first": "$attributes.vats"},
            "paymentInfo": {"$first": "$attributes.paymentInfo"},
        }
    },
    {
        "$unwind": {
            "path": "$vats",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": "$_id",
            "dateKey": {"$first": "$dateKey"},
            "totalAmountBeforeDiscount": {"$first": "$totalAmountBeforeDiscount"},
            "couponDiscount": {"$first": "$couponDiscount"},
            "totalAmountImmediateDiscount": {"$first": "$totalAmountImmediateDiscount"},
            "totalAmountDeferredDiscount": {"$first": "$totalAmountDeferredDiscount"},
            "totalPaidAmount": {"$first": "$totalPaidAmount"},
            "paymentInfo": {"$first": "$paymentInfo"},
            "vatTotalProductsAt20": {
                "$first": {
                    "$cond": [
                        {"$eq": ["$vats.vatPercentage", "20.0"]},
                        "$vats.vatTotalProducts",
                        0,
                    ]
                }
            },
            "vatTotalProductsAt5": {
                "$first": {
                    "$cond": [
                        {"$eq": ["$vats.vatPercentage", "5.5"]},
                        "$vats.vatTotalProducts",
                        0,
                    ]
                }
            },
            "vatAt20": {
                "$sum": {
                    "$cond": {
                        "if": {"$eq": ["$vats.vatPercentage", "20.0"]},
                        "then": "$vats.vatAmount",
                        "else": 0,
                    }
                }
            },
            "vatAt5": {
                "$sum": {
                    "$cond": {
                        "if": {"$eq": ["$vats.vatPercentage", "5.5"]},
                        "then": "$vats.vatAmount",
                        "else": 0,
                    }
                }
            },
        }
    },
    {"$unwind": {"path": "$paymentInfo", "preserveNullAndEmptyArrays": True}},
    {
        "$group": {
            "_id": {"id": "$_id", "paymentChoice": "$paymentInfo.choice"},
            "dateKey": {"$first": "$dateKey"},
            "totalAmountBeforeDiscount": {"$first": "$totalAmountBeforeDiscount"},
            "couponDiscount": {"$first": "$couponDiscount"},
            "totalAmountImmediateDiscount": {"$first": "$totalAmountImmediateDiscount"},
            "totalAmountDeferredDiscount": {"$first": "$totalAmountDeferredDiscount"},
            "totalPaidAmount": {"$first": "$totalPaidAmount"},
            "vatTotalProductsAt20": {"$first": "$vatTotalProductsAt20"},
            "vatTotalProductsAt5": {"$first": "$vatTotalProductsAt5"},
            "vatAt5": {"$first": "$vatAt5"},
            "vatAt20": {"$first": "$vatAt20"},
            "paymentAmount": {"$sum": "$paymentInfo.amount"},
        }
    },
    {"$addFields": {"recordType": "receipt", "totalEarnedAmount": 0}},
    {
        "$project": {
            "_id": 0,
            "id": "$_id.id",
            "dateKey": "$dateKey",
            "recordType": "$recordType",
            "paymentChoice": "$_id.paymentChoice",
            "totalAmountBeforeDiscount": "$totalAmountBeforeDiscount",
            "couponDiscount": "$couponDiscount",
            "totalAmountImmediateDiscount": "$totalAmountImmediateDiscount",
            "totalAmountDeferredDiscount": "$totalAmountDeferredDiscount",
            "totalEarnedAmount": "$totalEarnedAmount",
            "totalPaidAmount": "$totalPaidAmount",
            "vatTotalProductsAt20": {"$ifNull": ["$vatTotalProductsAt20", 0]},
            "vatTotalProductsAt5": {"$ifNull": ["$vatTotalProductsAt5", 0]},
            "vatAt5": "$vatAt5",
            "vatAt20": "$vatAt20",
            "paymentAmount": "$paymentAmount",
        }
    },
]

# Define the pipeline for the 'receipts' collection
pipeline_all = [
    # First pipeline: Process receipts data
    {
        "$unwind": {
            "path": "$attributes.products.coupon",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": "$_id",
            "dateKey": {"$first": "$attributes.dateKey"},
            "totalAmountBeforeDiscount": {
                "$first": "$attributes.totalAmountBeforeDiscount"
            },
            "couponDiscount": {"$sum": "$attributes.products.coupon.immediateDiscount"},
            "totalAmountImmediateDiscount": {
                "$first": "$attributes.totalAmountImmediateDiscount"
            },
            "totalAmountDeferredDiscount": {
                "$first": "$attributes.totalAmountDeferredDiscount"
            },
            "totalPaidAmount": {"$first": "$attributes.totalPaidAmount"},
            "vats": {"$first": "$attributes.vats"},
            "paymentInfo": {"$first": "$attributes.paymentInfo"},
        }
    },
    {
        "$unwind": {
            "path": "$vats",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": "$_id",
            "dateKey": {"$first": "$dateKey"},
            "totalAmountBeforeDiscount": {"$first": "$totalAmountBeforeDiscount"},
            "couponDiscount": {"$first": "$couponDiscount"},
            "totalAmountImmediateDiscount": {"$first": "$totalAmountImmediateDiscount"},
            "totalAmountDeferredDiscount": {"$first": "$totalAmountDeferredDiscount"},
            "totalPaidAmount": {"$first": "$totalPaidAmount"},
            "paymentInfo": {"$first": "$paymentInfo"},
            "vatTotalProductsAt20": {
                "$sum": {
                    "$cond": [
                        {"$eq": ["$vats.vatPercentage", "20.0"]},
                        "$vats.vatTotalProducts",
                        0,
                    ]
                }
            },
            "vatTotalProductsAt5": {
                "$sum": {
                    "$cond": [
                        {"$eq": ["$vats.vatPercentage", "5.5"]},
                        "$vats.vatTotalProducts",
                        0,
                    ]
                }
            },
            "vatTotalProductsAt10": {
                "$sum": {
                    "$cond": [
                        {"$eq": ["$vats.vatPercentage", "10.0"]},
                        "$vats.vatTotalProducts",
                        0,
                    ]
                }
            },
            "vatAt10": {
                "$sum": {
                    "$cond": {
                        "if": {"$eq": ["$vats.vatPercentage", "10.0"]},
                        "then": "$vats.vatAmount",
                        "else": 0,
                    }
                }
            },
            "vatAt20": {
                "$sum": {
                    "$cond": {
                        "if": {"$eq": ["$vats.vatPercentage", "20.0"]},
                        "then": "$vats.vatAmount",
                        "else": 0,
                    }
                }
            },
            "vatAt5": {
                "$sum": {
                    "$cond": {
                        "if": {"$eq": ["$vats.vatPercentage", "5.5"]},
                        "then": "$vats.vatAmount",
                        "else": 0,
                    }
                }
            },
        }
    },
    {"$unwind": {"path": "$paymentInfo", "preserveNullAndEmptyArrays": True}},
    {
        "$group": {
            "_id": {"id": "$_id", "paymentChoice": "$paymentInfo.choice"},
            "dateKey": {"$first": "$dateKey"},
            "totalAmountBeforeDiscount": {"$first": "$totalAmountBeforeDiscount"},
            "couponDiscount": {"$first": "$couponDiscount"},
            "totalAmountImmediateDiscount": {"$first": "$totalAmountImmediateDiscount"},
            "totalAmountDeferredDiscount": {"$first": "$totalAmountDeferredDiscount"},
            "totalPaidAmount": {"$first": "$totalPaidAmount"},
            "vatTotalProductsAt20": {"$first": "$vatTotalProductsAt20"},
            "vatTotalProductsAt5": {"$first": "$vatTotalProductsAt5"},
            "vatTotalProductsAt10": {"$first": "$vatTotalProductsAt10"},
            "vatAt5": {"$first": "$vatAt5"},
            "vatAt20": {"$first": "$vatAt20"},
            "vatAt10": {"$first": "$vatAt10"},
            "paymentAmount": {"$sum": "$paymentInfo.amount"},
        }
    },
    {"$addFields": {"recordType": "receipt", "totalEarnedAmount": 0}},
    {
        "$project": {
            "_id": 0,
            "id": "$_id.id",
            "dateKey": "$dateKey",
            "recordType": "$recordType",
            "paymentChoice": "$_id.paymentChoice",
            "totalAmountBeforeDiscount": "$totalAmountBeforeDiscount",
            "couponDiscount": "$couponDiscount",
            "totalAmountImmediateDiscount": "$totalAmountImmediateDiscount",
            "totalAmountDeferredDiscount": "$totalAmountDeferredDiscount",
            "totalEarnedAmount": "$totalEarnedAmount",
            "totalPaidAmount": "$totalPaidAmount",
            "vatTotalProductsAt20": "$vatTotalProductsAt20",
            "vatTotalProductsAt5": "$vatTotalProductsAt5",
            "vatTotalProductsAt10": "$vatTotalProductsAt10",
            "vatAt5": "$vatAt5",
            "vatAt20": "$vatAt20",
            "vatAt10": "$vatAt10",
            "paymentAmount": "$paymentAmount",
        }
    },
    # Union with orders data
    {
        "$unionWith": {
            "coll": "orders",
            "pipeline": [
                # Second pipeline: Process orders data
                {
                    "$addFields": {
                        "dateKey": {
                            "$concat": [
                                {"$substr": ["$attributes.date", 0, 4]},
                                {"$substr": ["$attributes.date", 5, 2]},
                                {"$substr": ["$attributes.date", 8, 2]},
                            ]
                        }
                    }
                },
                {
                    "$unwind": {
                        "path": "$attributes.promotionCodes",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {"$match": {"attributes.promotionCodes": {"$ne": "eLOYALTY"}}},
                {
                    "$group": {
                        "_id": "$attributes.orderNumber",
                        "dateKey": {"$first": "$dateKey"},
                        "couponDiscount": {"$sum": "$attributes.promotionCodes.amount"},
                        "paidAmount": {"$first": "$attributes.totalAmount"},
                        "immediateDiscount": {
                            "$first": "$attributes.immediateDiscountAmount"
                        },
                        "totalEarnedAmount": {
                            "$first": "$attributes.totalEarnedAmount"
                        },
                        "vatAt5": {"$first": "$attributes.vatAt5"},
                        "vatAt20": {"$first": "$attributes.vatAt20"},
                        "paymentInfo": {"$first": "$attributes.paymentInfos"},
                        "productList": {"$first": "$attributes.productList"},
                    }
                },
                {
                    "$unwind": {
                        "path": "$productList.categories",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {
                    "$group": {
                        "_id": "$_id",
                        "dateKey": {"$first": "$dateKey"},
                        "couponDiscount": {"$first": "$couponDiscount"},
                        "paidAmount": {"$first": "$paidAmount"},
                        "immediateDiscount": {"$first": "$immediateDiscount"},
                        "totalEarnedAmount": {"$first": "$totalEarnedAmount"},
                        "vatAt5": {"$first": "$vatAt5"},
                        "vatAt20": {"$first": "$vatAt20"},
                        "paymentInfo": {"$first": "$paymentInfo"},
                        "bagCat": {"$last": "$productList.categories"},
                    }
                },
                {
                    "$unwind": {
                        "path": "$bagCat.products",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {
                    "$group": {
                        "_id": "$_id",
                        "dateKey": {"$first": "$dateKey"},
                        "couponDiscount": {"$first": "$couponDiscount"},
                        "paidAmount": {"$first": "$paidAmount"},
                        "immediateDiscount": {"$first": "$immediateDiscount"},
                        "totalEarnedAmount": {"$first": "$totalEarnedAmount"},
                        "vatAt5": {"$first": "$vatAt5"},
                        "vatAt20": {"$first": "$vatAt20"},
                        "paymentInfo": {"$first": "$paymentInfo"},
                        "bagProd": {"$first": "$bagCat.products"},
                    }
                },
                {
                    "$addFields": {
                        "totalAmountBeforeDiscount": {
                            "$add": [
                                "$paidAmount",
                                "$couponDiscount",
                                {"$ifNull": ["$immediateDiscount", 0]},
                            ]
                        },
                        "totalAmountImmediateDiscount": {
                            "$add": [
                                "$couponDiscount",
                                {"$ifNull": ["$immediateDiscount", 0]},
                            ]
                        },
                        "totalPaidAmount": {
                            "$subtract": [
                                "$paidAmount",
                                {
                                    "$ifNull": [
                                        f"$bagProd.attributes.offers.{BAG_EAN}.{STORE_ID}.attributes.price.totalPrice.refunded",
                                        0,
                                    ]
                                },
                            ]
                        },
                    }
                },
                {
                    "$unwind": {
                        "path": "$paymentInfo",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {
                    "$group": {
                        "_id": {"id": "$_id", "paymentChoice": "$paymentInfo.choice"},
                        "dateKey": {"$first": "$dateKey"},
                        "totalAmountBeforeDiscount": {
                            "$first": "$totalAmountBeforeDiscount"
                        },
                        "couponDiscount": {"$first": "$couponDiscount"},
                        "totalAmountImmediateDiscount": {
                            "$first": "$totalAmountImmediateDiscount"
                        },
                        "totalEarnedAmount": {"$first": "$totalEarnedAmount"},
                        "totalPaidAmount": {"$first": "$totalPaidAmount"},
                        "vatAt5": {"$first": "$vatAt5"},
                        "vatAt20": {"$first": "$vatAt20"},
                        "paymentAmount": {"$sum": "$paymentInfo.amount"},
                    }
                },
                {
                    "$addFields": {
                        "recordType": "order",
                        "totalAmountDeferredDiscount": 0,
                        "vatTotalProductsAt10": 0,
                        "vatAt10": 0,
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "id": "$_id.id",
                        "dateKey": "$dateKey",
                        "recordType": "$recordType",
                        "paymentChoice": "$_id.paymentChoice",
                        "totalAmountBeforeDiscount": "$totalAmountBeforeDiscount",
                        "couponDiscount": {"$multiply": ["$couponDiscount", -1]},
                        "totalAmountImmediateDiscount": {
                            "$multiply": ["$totalAmountImmediateDiscount", -1]
                        },
                        "totalAmountDeferredDiscount": "$totalAmountDeferredDiscount",
                        "totalEarnedAmount": "$totalEarnedAmount",
                        "totalPaidAmount": "$totalPaidAmount",
                        "vatTotalProductsAt20": {"$multiply": ["$vatAt20", 6]},
                        "vatTotalProductsAt5": {
                            "$multiply": ["$vatAt5", 1 + 100 / 5.5]
                        },
                        "vatTotalProductsAt10": "$vatTotalProductsAt10",
                        "vatAt5": "$vatAt5",
                        "vatAt20": "$vatAt20",
                        "vatAt10": "$vatAt10",
                        "paymentAmount": "$paymentAmount",
                    }
                },
            ],
        }
    },
    # Final Sort: Mixed and sorted by dateKey, id, and paymentType
    {"$sort": {"dateKey": -1, "id": -1, "paymentChoice": 1}},
]

# Perform the aggregation
pipeline_loyalty = [
    {"$unwind": {"path": "$history", "preserveNullAndEmptyArrays": True}},
    {
        "$project": {
            "operationId": {"$toString": "$history.operationId"},  # Convert to string
            "date": "$history.date",
            "earned": "$history.earned",
            "burned": "$history.burned",
        }
    },
    {
        "$lookup": {
            "from": "loyaltyOperations",
            "localField": "operationId",
            "foreignField": "operationId",
            "as": "operation",
        }
    },
    {"$unwind": {"path": "$operation", "preserveNullAndEmptyArrays": True}},
    {"$unwind": {"path": "$operation.data", "preserveNullAndEmptyArrays": True}},
    # {
    #     "$match": {
    #         "operation.data.attributes.itemRd": {"$exists": True, "$ne": ""}
    #     }
    # },
    {
        "$project": {
            "_id": 0,
            "operationId": "$operationId",
            "date": "$date",
            "earned": "$earned",
            "burned": "$burned",
            "itemLabel": "$operation.data.attributes.itemLabel",
            "promotionLabel": "$operation.data.attributes.promotionLabel",
            "itemRd": "$operation.data.attributes.itemRd",
            "loyaltyOperation": "$operation.data.attributes.loyaltyOperation",
        }
    },
]
# Define the aggregation pipeline
pipeline_prod = [
    # 1st step: query from collection 'receipts'
    {
        "$unwind": {
            "path": "$attributes.products.product",
            "preserveNullAndEmptyArrays": True,
        }
    },
    {
        "$group": {
            "_id": {
                "dateKey": "$attributes.dateKey",
                "productLabel": "$attributes.products.product.label",
            },  # Group by product ID
            "vatPercentage": {"$first": "$attributes.products.product.vatPercentage"},
            "countVisits": {"$sum": 1},  # count the number of receipts per day
            "totalQuantity": {
                "$sum": "$attributes.products.product.quantity"
            },  # Sum up the quantities for each product
            "totalWeight": {
                "$sum": "$attributes.products.product.weight"
            },  # Sum up the quantities for each product
            "unitPrice": {
                "$avg": "$attributes.products.product.unitPrice"
            },  # Average unit price per day
            "totalPrice": {
                "$sum": "$attributes.products.product.totalPrice"
            },  # Total price per day
            "totalImmediateDiscount": {
                "$sum": "$attributes.products.product.immediateDiscount"
            },  # total immediate discount for the day
        }
    },
    {
        "$addFields": {
            "category": {
                "$cond": {
                    "if": {"$eq": ["$vatPercentage", "5.5"]},
                    "then": "food",
                    "else": "other",
                }
            },  # Food or non-food
        }
    },
    {
        "$project": {
            "_id": 0,
            "dateKey": "$_id.dateKey",
            "recordType": "receipt",
            "countVisits": "$countVisits",
            "ean": "",
            "cdbase": "",
            "productLabel": "$_id.productLabel",
            "slugProductLabel": "$_id.productLabel",
            "category": "$category",
            "subCategory": "",
            "vatPercentage": "$vatPercentage",
            "totalQuantity": "$totalQuantity",
            "totalWeight": "$totalWeight",
            "unitPrice": "$unitPrice",
            "totalPrice": "$totalPrice",
            "totalImmediateDiscount": "$totalImmediateDiscount",
        }
    },
    # Union with orders data
    {
        "$unionWith": {
            "coll": "orders",
            "pipeline": [
                # Second pipeline: Process orders data
                {
                    "$addFields": {
                        "dateKey": {
                            "$concat": [
                                {"$substr": ["$attributes.date", 0, 4]},
                                {"$substr": ["$attributes.date", 5, 2]},
                                {"$substr": ["$attributes.date", 8, 2]},
                            ]
                        }
                    }
                },
                {
                    "$unwind": {
                        "path": "$attributes.productList.categories",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {
                    "$unwind": {
                        "path": "$attributes.productList.categories.products",
                        "preserveNullAndEmptyArrays": True,
                    }
                },
                {
                    "$project": {
                        "dateKey": "$dateKey",
                        "ean": "$attributes.productList.categories.products.attributes.ean",
                        "cdbase": "$attributes.productList.categories.products.attributes.cdbase",
                        "productLabel": "$attributes.productList.categories.products.attributes.title",
                        "slugProductLabel": "$attributes.productList.categories.products.attributes.slug",
                        "subCategory": "$attributes.productList.categories.products.attributes.category",
                        "totalQuantity": "$attributes.productList.categories.products.attributes.quantity.delivered",
                        "totalWeight": "$attributes.productList.categories.products.attributes.pickedQuantityPerWeight.value",
                        "offers": "$attributes.productList.categories.products.attributes.offers",
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "dateKey": "$dateKey",
                            "ean": "$ean",
                        },  # Group by product ID
                        "countVisits": {
                            "$sum": 1
                        },  # count the number of receipts per day
                        "cdbase": {"$first": "$cdbase"},
                        "productLabel": {"$first": "$productLabel"},
                        "slugProductLabel": {"$first": "$slugProductLabel"},
                        "subCategory": {"$first": "$subCategory"},
                        "totalQuantity": {
                            "$sum": "$totalQuantity"
                        },  # Sum up the quantities for each product
                        "totalWeight": {
                            "$sum": "$totalWeight"
                        },  # Sum up the quantities for each product
                        # immediate discount issue howto?
                        "unitPrice": {
                            "$first": {
                                "$getField": {
                                    "field": "price",
                                    "input": {
                                        "$getField": {
                                            "field": "price",
                                            "input": {
                                                "$getField": {
                                                    "field": "attributes",
                                                    "input": {
                                                        "$getField": {
                                                            "field": "v",
                                                            "input": {
                                                                "$arrayElemAt": [
                                                                    {
                                                                        "$objectToArray": {
                                                                            "$getField": {
                                                                                "field": "$ean",
                                                                                "input": "$offers",
                                                                            }
                                                                        }
                                                                    },
                                                                    0,
                                                                ]  # get the array under as v
                                                            },
                                                        }
                                                    },
                                                }
                                            },
                                        }
                                    },
                                }
                            }
                        },
                        "totalPrice": {
                            "$sum": {
                                "$getField": {
                                    "field": "delivered",
                                    "input": {
                                        "$getField": {
                                            "field": "totalPrice",
                                            "input": {
                                                "$getField": {
                                                    "field": "price",
                                                    "input": {
                                                        "$getField": {
                                                            "field": "attributes",
                                                            "input": {
                                                                "$getField": {
                                                                    "field": "v",
                                                                    "input": {
                                                                        "$arrayElemAt": [
                                                                            {
                                                                                "$objectToArray": {
                                                                                    "$getField": {
                                                                                        "field": "$ean",
                                                                                        "input": "$offers",
                                                                                    }
                                                                                }
                                                                            },
                                                                            0,
                                                                        ]  # get the array under as v
                                                                    },
                                                                }
                                                            },
                                                        }
                                                    },
                                                }
                                            },
                                        }
                                    },
                                }
                            }
                        },
                        "totalImmediateDiscount": {
                            "$sum": {
                                "$getField": {
                                    "field": "immediateDiscount",
                                    "input": {
                                        "$getField": {
                                            "field": "totalPrice",
                                            "input": {
                                                "$getField": {
                                                    "field": "price",
                                                    "input": {
                                                        "$getField": {
                                                            "field": "attributes",
                                                            "input": {
                                                                "$getField": {
                                                                    "field": "v",
                                                                    "input": {
                                                                        "$arrayElemAt": [
                                                                            {
                                                                                "$objectToArray": {
                                                                                    "$getField": {
                                                                                        "field": "$ean",
                                                                                        "input": "$offers",
                                                                                    }
                                                                                }
                                                                            },
                                                                            0,
                                                                        ]  # get the array under as v
                                                                    },
                                                                }
                                                            },
                                                        }
                                                    },
                                                }
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
                {"$addFields": {"vatPercentage": None}},
                {
                    "$project": {
                        "_id": 0,
                        "dateKey": "$_id.dateKey",
                        "recordType": "order",
                        "countVisits": "$countVisits",
                        "ean": "$_id.ean",
                        "cdbase": "$cdbase",
                        "productLabel": "$productLabel",
                        "slugProductLabel": "$slugProductLabel",
                        "category": "",
                        "subCategory": "$subCategory",
                        "vatPercentage": "$vatPercentage",
                        "totalQuantity": "$totalQuantity",
                        "totalWeight": "$totalWeight",
                        "unitPrice": "$unitPrice",
                        "totalPrice": "$totalPrice",
                        "totalAmountImmediateDiscount": {
                            "$multiply": ["$totalAmountImmediateDiscount", -1]
                        },
                    }
                },
            ],
        }
    },
    {"$sort": {"dateKey": -1}},
]

pipeline_merge_amounts = {
        "$merge": {
            "into": "targetCollection",  # Write to the target collection
            "on": ["email", "name"],  # Match documents by email and name (custom key)
            "whenMatched": "keepExisting",  # Keep existing documents in the target collection
            "whenNotMatched": "insert",  # Insert new documents that are not in the target collection
        }
    }


def query_collection(
    pipeline: List[Dict[str, Any]],
    collection_name: str = "receipts",
    db_name: str = "carrefour",
) -> pd.DataFrame:
    """
    Aggregation query with pipeline via MongoDB client and return a DataFrame for further analysis
    """

    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, db_name)
        # Create a collection
        collection = get_collection(db, collection_name=collection_name)
        # Query the collection and save it to a DataFrame
        results = collection.aggregate(pipeline)
        df = res_to_df(results)
    return df

def res_to_df(results: CommandCursor) -> pd.DataFrame:
    """
    Convert MongoDB aggregation results to a DataFrame.
    """
    df = pd.DataFrame(list(results))
    if df.empty:
        logger.warning("No result for this query. Please retry.")
    else:
        logger.info(f"Query successful with {len(df)} rows")
    return df


def display_amounts(
    df, col_amount: str = "totalPaidAmount", col_date: str = "dateKey", show_avg=True
):
    # df.plot(x='date', y=col_amount, kind='line', title='Total Paid Amount by Year and Month', marker='o')
    # Format the X-axis to show Month-Year
    plt.figure(figsize=(10, 6))
    plt.plot(
        df[col_date],
        df[col_amount],
        marker="o",
        linestyle="-",
        color="b",
        label="Total Paid Amount",
    )
    if show_avg:
        # Calculate the average total paid amount
        average_amount = df[col_amount].mean()
        # Add a horizontal line for the average
        plt.axhline(
            y=average_amount,
            color="r",
            linestyle="--",
            linewidth=2,
            label=f"Average {col_amount} ({average_amount:.2f})",
        )

    # Format the X-axis
    plt.gca().xaxis.set_major_formatter(
        mdates.DateFormatter("%b %Y")
    )  # Format as "Jan 2025"
    plt.gca().xaxis.set_major_locator(mdates.MonthLocator())  # Show one tick per month
    plt.xticks(rotation=45)  # Rotate labels for better readability

    # Add labels and title
    plt.title("Total Amounts by Month")
    plt.xlabel("Month-Year")
    plt.ylabel(col_amount)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

DEFAULT_DATE_UPDATE = "20250501"

def main_amounts(date_update: str = DEFAULT_DATE_UPDATE):
    """
    Main function to query the MongoDB collection for purchase amounts and save the results to a CSV file.
    """
    DISCOUNT_PERCENT_GIFT_CARD = 0.045  # around 5% since using MACIF avantages
    FILEPATH = f"{DATA_DIRECTORY}/{date_update}-carrefour_amounts.csv"
    # dictionary matching payment choices and discount
    PAYMENT_CHOICES = {
        "Cagnotte fidélité": 1,
        "eLOYALTY": 1,
        "Bons de réduction": 1,
        "Bons d'achat": DISCOUNT_PERCENT_GIFT_CARD,
        "CARREFOUR_EPAY": DISCOUNT_PERCENT_GIFT_CARD,
    }
    df_amounts = query_collection(pipeline=pipeline_all)
    # pivot to get the amounts associated to each payment choice
    table_amounts = pd.pivot_table(
        df_amounts,
        index=[
            col
            for col in df_amounts.columns
            if col not in ["paymentChoice", "paymentAmount"]
        ],
        columns="paymentChoice",
        values="paymentAmount",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    table_amounts.columns.name = None
    table_amounts["dateKey"] = pd.to_datetime(table_amounts["dateKey"])

    table_amounts["totalTrueAmount"] = table_amounts["totalPaidAmount"]
    for choice, discount in PAYMENT_CHOICES.items():
        table_amounts["totalTrueAmount"] -= table_amounts[choice] * discount

    table_amounts.to_csv(path_or_buf=FILEPATH, index=False)
    logger.info(f"Saved table amounts to {FILEPATH}")


def main_loyalty(date_update: str = DEFAULT_DATE_UPDATE):
    FILEPATH = f"{DATA_DIRECTORY}/{date_update}-carrefour_loyalty.csv"
    df_loyalty = query_collection(pipeline=pipeline_loyalty, collection_name="loyalty")
    df_loyalty["date"] = pd.to_datetime(df_loyalty["date"].apply(lambda x: x[:10]))
    df_loyalty.to_csv(path_or_buf=FILEPATH, index=False)
    logger.info(f"Saved table amounts to {FILEPATH}")


def main_prods(date_update: str = DEFAULT_DATE_UPDATE):
    FILEPATH = f"{DATA_DIRECTORY}/{date_update}-carrefour_prods.csv"
    df_receipts_prod = query_collection(pipeline_prod, collection_name="receipts")
    df_receipts_prod["dateKey"] = pd.to_datetime(df_receipts_prod["dateKey"])
    df_receipts_prod.to_csv(path_or_buf=FILEPATH, index=False)
    logger.info(f"Saved table amounts to {FILEPATH}")


def main(script_name: str = "store", date_update: str = DEFAULT_DATE_UPDATE):
    match script_name:
        case "amounts":
            main_amounts(date_update)
        case "prods":
            main_prods(date_update)
        case "loyalty":
            main_loyalty(date_update)
        case _:
            logger.warning(
                "Please choose between script_name: 'amounts', 'prods' or 'loyalty'."
            )


if __name__ == "__main__":
    # main(script_name="amounts", date_update="20250601")
    main(script_name="prods", date_update="20250601")
    # main(script_name="loyalty", date_update="20250601")
