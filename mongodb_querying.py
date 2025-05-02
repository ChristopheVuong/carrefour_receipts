from datetime import datetime
import logging
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError
import json
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_client(uri: str) -> MongoClient:
    """
    This function returns a MongoClient object.
    :param uri: MongoDB connection string
    :return: MongoClient object
    """
    # Create a connection using MongoClient. You can import MongoClient or use pymongo.MongoClient
    client = MongoClient(uri)

    # Print the client object
    logger.info(f"MongoDB Client: {client}")

    return client


def get_database(client: MongoClient, db_name: str) -> Database:
    """
    This function returns a database connection.
    :param client: MongoDB client object
    :param db_name: Name of the database to connect to
    :return: database object
    """
    # Create the database for our example (we will use the same database throughout the tutorial)
    logger.info(f"Connecting to database: {db_name}")
    return client[db_name]


# # This is added so that many files can reuse the function get_database()
# if __name__ == "__main__":

#    # Get the database
#    dbname = get_database()


def get_collection(db: Database, collection_name: str = "receipts") -> Collection:
    """
    This function returns a collection object.
    :param db: MongoDB database object
    :param collection_name: Name of the collection to connect to
    :return: collection object
    """
    # Create a collection
    collection = db[collection_name]

    # Log the collection name
    logger.info(f"Access to collection {collection_name}.")

    return collection


def insert_json_files(
    collection: Collection,
    directory: str,
    criterion1: str = "carrefour_receipt_",
    criterion2: str = "",
    keep_ids=False,
) -> None:
    """
    Insert JSON files into a MongoDB collection.
    :param collection: MongoDB collection object
    :param directory: Directory containing JSON files
    :param criterion1: Criterion to filter files
    :param criterion2: Additional criterion to filter files like date
    :param keep_ids: Whether to keep the original IDs from the JSON files
    Note: Limit insertion by criterion
    """
    list_data = []

    for file in Path(directory).rglob(
        f"{criterion2}*{criterion1}*.json"
    ):  # even subfolders
        with open(file) as f:
            rec = json.load(f)
            if not rec:
                logger.warning(f"Empty record in file {file}")
                continue
            if isinstance(rec, list):
                for item in rec:
                    if keep_ids:
                        item["_id"] = item.pop("id")
                    list_data.append(item)
            else:
                if keep_ids:
                    rec["_id"] = rec.pop("id")
                list_data.append(rec)

    try:
        result = collection.insert_many(
            list_data, ordered=False
        )  # ordered=False to allow bulk insert even if some records fail
    except BulkWriteError as bwe:
        logger.error(f"Bulk write error: {bwe.details}")
        raise
    logger.info(f"Data inserted with record ids {result.inserted_ids}")


def read_data(collection: Collection, n: int = 10):

    # Read data from the collection
    data = (
        collection.find().limit(n) if n > 0 else collection.find()
    )  # restrict to n records

    # Print the data
    for item in data:
        print(item)


def update_data(collection, query, new_values):
    # Update data in the collection
    result = collection.update_one(query, new_values)

    # Log the number of documents updated
    logger.info(f"Documents updated: {result.modified_count}")


def delete_data(collection, query):

    # Delete data from the collection
    result = collection.delete_one(query)

    # Log the number of documents deleted
    logger.info(f"Documents deleted: {result.deleted_count}")


def aggregate_and_unroll_to_dataframe(
    collection: Collection, pipeline: List[str]
) -> pd.DataFrame:
    """
    Get data from the collection as a pandas DataFrame.
    :param collection: MongoDB collection object
    :param pipeline: Aggregation pipeline to filter and transform data group by _id (which can be a nested structure)
    :return: DataFrame containing the data
    """
    # Read data from the collection using aggregation pipeline
    data = list(collection.aggregate(pipeline))

    # Convert to DataFrame
    df = pd.DataFrame(data)

    df = df._id.apply(pd.Series).join(
        df.drop(columns=["_id"]), how="left"
    )  # index-based join

    return df


def main_store():
    # MongoDB connection string: setup local connection
    CONNECTION_STRING = "mongodb://localhost:27017/"

    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="receipts")

        # Insert JSON data
        insert_json_files(
            collection,
            directory="data",
            criterion1="carrefour_receipt_",
            criterion2=datetime.now().strftime("%Y%m%d"),
            keep_ids=True,
        )

        # Read data
        # read_data(collection, n=10)

    logger.info("MongoDB connection closed automatically.")


def main_drive():
    # MongoDB connection string: setup local connection
    CONNECTION_STRING = "mongodb://localhost:27017/"

    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="orders")

        # Insert JSON data
        insert_json_files(
            collection,
            directory="data",
            criterion1="carrefour_order_",
            criterion2=datetime.now().strftime("%Y%m%d"),
            keep_ids=True,
        )

        # Read data
        # read_data(collection, n=10)

    logger.info("MongoDB connection closed automatically.")


if __name__ == "__main__":
    # main_store()
    main_drive()
