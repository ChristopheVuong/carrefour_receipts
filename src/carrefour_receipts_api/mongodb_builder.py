from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MongoDBManager:
    """
    Central class to manage MongoDB operations including connection,
    CRUD operations, and JSON file insertion.
    """

    def __init__(self, connection_string: str, db_name: str):
        """
        Initialize the MongoDBManager with a connection string and database name.
        :param connection_string: MongoDB connection string
        :param db_name: Name of the database to connect to
        """
        self.client: MongoClient = MongoClient(connection_string)
        self.db: Database = self.client[db_name]
        logger.info(f"Connected to MongoDB database: {db_name}")

    def get_collection(self, collection_name: str) -> Collection:
        """
        Get a MongoDB collection object.
        :param collection_name: Name of the collection to access
        :return: Collection object
        """
        collection = self.db[collection_name]
        logger.info(f"Accessed collection: {collection_name}")
        return collection

    def insert_json_files(
        self,
        collection: Collection,
        directory: str,
        criterion1: str = "",
        criterion2: str = "",
        id_col: str | None = None,
        keep_id: bool = False,
    ) -> None:
        """
        Insert JSON files into a MongoDB collection.
        :param collection: MongoDB collection object
        :param directory: Directory containing JSON files
        :param criterion1: Criterion to filter files
        :param criterion2: Additional criterion to filter files (e.g., date)
        :param id_col: Column in JSON files to use as `_id`
        :param keep_id: Whether to keep the `id_col` in the document
        """
        list_data: list[dict[str, Any]] = []

        for file in Path(directory).rglob(f"{criterion2}*{criterion1}*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                    if not rec:
                        logger.warning(f"Empty record in file {file}")
                        continue

                    if isinstance(rec, list):
                        for item in rec:
                            if id_col:
                                item["_id"] = item[id_col] if keep_id else item.pop(id_col)
                            list_data.append(item)
                    else:
                        if id_col:
                            rec["_id"] = rec[id_col] if keep_id else rec.pop(id_col)
                        list_data.append(rec)
            except Exception as e:
                logger.error(f"Error processing file {file}: {e}")

        try:
            result = collection.insert_many(list_data, ordered=False)
            logger.info(f"Inserted {len(result.inserted_ids)} records into the collection.")
        except BulkWriteError as bwe:
            logger.error(f"Bulk write error: {bwe.details}")
            raise

    def read_data(self, collection: Collection, n: int = 10) -> None:
        """
        Read data from a MongoDB collection.
        :param collection: MongoDB collection object
        :param n: Number of records to read (default: 10)
        """
        data = collection.find().limit(n) if n > 0 else collection.find()
        for item in data:
            print(item)

    def update_data(self, collection: Collection, query: dict[str, Any], new_values: dict[str, Any]) -> None:
        """
        Update data in a MongoDB collection.
        :param collection: MongoDB collection object
        :param query: Query to find documents to update
        :param new_values: New values to update
        """
        result = collection.update_one(query, {"$set": new_values})
        logger.info(f"Documents updated: {result.modified_count}")

    def delete_data(self, collection: Collection, query: dict[str, Any]) -> None:
        """
        Delete data from a MongoDB collection.
        :param collection: MongoDB collection object
        :param query: Query to find documents to delete
        """
        result = collection.delete_one(query)
        logger.info(f"Documents deleted: {result.deleted_count}")

    def close_connection(self) -> None:
        """
        Close the MongoDB client connection.
        """
        self.client.close()
        logger.info("MongoDB connection closed.")

query_labels = [] # unique labels in both

class MongoDBVectorEmbedManager(MongoDBManager):
    """
    TODO: Write the script in mongodb_querying.py which is a bit fat compared to the builder
    Keep the document DB clean with as less preprocessing as possible, this is done in csv.
    MongoDBManager subclass that adds vector embedding of product labels.
    This may not be the best idea. However, it seems fitting to compute a query for labels and save that to csv file
    with possibility to add non-duplicates
    """
    def create_vector_embeddings(self, collection: Collection, field: str):
        """
        Based on a query for labels, create or update the associated vector embeddings and add it to the document
        Note: That makes the vector embeddings persistent: Labels + embeddings in the same JSON doc → document DB with built-in vector search
        :param collection: MongoDB collection to compute
        :param field: the name of the field in the document
        """
        pass


def main_store(manager: MongoDBManager):
    """
    Main function for store operations.
    """
    collection = manager.get_collection("receipts")
    manager.insert_json_files(
        collection,
        directory="data",
        criterion1="carrefour_receipt_",
        criterion2=datetime.now().strftime("%Y%m%d"),
        id_col="id",
        keep_id=False,
    )


def main_drive(manager: MongoDBManager):
    """
    Main function for drive operations.
    """
    collection = manager.get_collection("orders")
    manager.insert_json_files(
        collection,
        directory="data",
        criterion1="carrefour_order_",
        criterion2=datetime.now().strftime("%Y%m%d"),
    )


def main_loyalty(manager: MongoDBManager):
    """
    Main function for loyalty operations.
    """
    collection = manager.get_collection("loyalty")
    manager.insert_json_files(
        collection,
        directory="data",
        criterion1="carrefour_loyalty_transactions",
        criterion2=datetime.now().strftime("%Y%m%d"),
    )


def main_loyalty_operations(manager: MongoDBManager):
    """
    Main function for loyalty operations.
    """
    collection = manager.get_collection("loyaltyOperations")
    manager.insert_json_files(
        collection,
        directory="data",
        criterion1="carrefour_loyalty_operation",
        criterion2=datetime.now().strftime("%Y%m%d"),
        id_col="operationId",
        keep_id=True,
    )


def main(script_name: str = "store"):
    """
    Main entry point for the script.
    :param script_name: Name of the script to run ('store', 'drive', 'loyalty', 'loyaltyOperations')
    """
    CONNECTION_STRING = "mongodb://localhost:27017/"
    DB_NAME = "carrefour"

    # Initialize MongoDBManager
    manager = MongoDBManager(CONNECTION_STRING, DB_NAME)

    try:
        match script_name:
            case "store":
                main_store(manager)
            case "drive":
                main_drive(manager)
            case "loyalty":
                main_loyalty(manager)
            case "loyaltyOperations":
                main_loyalty_operations(manager)
            case _:
                logger.warning(
                    "Please choose between script_name: 'store', 'drive', 'loyalty' or 'loyaltyOperations'."
                )
    finally:
        manager.close_connection()


if __name__ == "__main__":
    main("store")  # Default to store operations
    main("drive")  # Default to drive operations
    main("loyalty")  # Default to loyalty operations
    main("loyaltyOperations")