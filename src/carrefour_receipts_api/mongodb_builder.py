from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Dict, Any

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Provide the mongodb atlas url to connect python to mongodb using pymongo
# CONNECTION_STRING = "mongodb+srv://user:pass@cluster.mongodb.net/myFirstDatabase"
CONNECTION_STRING = "mongodb://localhost:27017/"
DATA_DIRECTORY = "data"


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
    ids_col: str | Any = None,
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
                    if ids_col:
                        item["_id"] = item.pop(ids_col)
                    list_data.append(item)
            else:
                if ids_col:
                    rec["_id"] = rec.pop(ids_col)
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


def update_data(
    collection: Collection, query: Dict[str, Any], new_values: Dict[str, Any]
):
    # Update data in the collection
    result = collection.update_one(query, new_values)

    # Log the number of documents updated
    logger.info(f"Documents updated: {result.modified_count}")


def delete_data(collection: Collection, query: Dict[str, Any]):

    # Delete data from the collection
    result = collection.delete_one(query)

    # Log the number of documents deleted
    logger.info(f"Documents deleted: {result.deleted_count}")


def main_store():

    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="receipts")

        # Insert JSON data
        insert_json_files(
            collection,
            directory=DATA_DIRECTORY,
            criterion1="carrefour_receipt_",
            criterion2=datetime.now().strftime("%Y%m%d"),
            ids_col="id",
        )

        # Read data
        # read_data(collection, n=10)

    logger.info("MongoDB connection closed automatically.")


def main_drive():
    """
    Note: Marketplace cause an error while fetching and should not be inserted in the database (errand)
    """

    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="orders")

        # Insert JSON data
        insert_json_files(
            collection,
            directory=DATA_DIRECTORY,
            criterion1="carrefour_order_",
            criterion2=datetime.now().strftime("%Y%m%d"),
        )

        # Read data
        # read_data(collection, n=10)

    logger.info("MongoDB connection closed automatically.")


def main_loyalty():
    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="loyalty")

        # Insert JSON data
        insert_json_files(
            collection,
            directory=DATA_DIRECTORY,
            criterion1="carrefour_loyalty_transactions",
            criterion2=datetime.now().strftime("%Y%m%d"),
        )
    logger.info("MongoDB connection closed automatically.")


def main_loyalty_operations():
    # mongoclient compatible with context manager
    with MongoClient(CONNECTION_STRING) as client:
        # Get the database
        db = get_database(client, "carrefour")

        # Create a collection
        collection = get_collection(db, collection_name="loyaltyOperations")

        # Insert JSON data
        insert_json_files(
            collection,
            directory=DATA_DIRECTORY,
            criterion1="carrefour_loyalty_operation",
            criterion2=datetime.now().strftime("%Y%m%d"),
        )

        # Read data
        # read_data(collection, n=10)

    logger.info("MongoDB connection closed automatically.")


def main(script_name: str = "store"):
    match script_name:
        case "store":
            main_store()
        case "drive":
            main_drive()
        case "loyalty":
            main_loyalty()
        case "loyaltyOperations":
            main_loyalty_operations()
        case _:
            logger.warning(
                "Please choose between script_name: 'store', 'drive', 'loyalty' or 'loyaltyOperations'."
            )


if __name__ == "__main__":
    main("loyaltyOperations")
