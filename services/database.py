from helpers.custom_logger import CustomLogger

import os
from pymongo import MongoClient
from datetime import datetime

class Database:
    _instance = None
    
    FIELD_SERVICES_STATUS_COLLECTION = "services_status"
    FIELD_ACTION_HISTORY_COLLECTION = "action_history"

    FIELD_UID = "uid"
    FIELD_TIMESTAMP = "timestamp"
    FIELD_SERVICE_TYPE = "service_type"
    FIELD_DESCRIPTION = "description"

    def __new__(cls, config=None, test_mode=False):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._init_database(config, test_mode)
        return cls._instance

    def _init_database(self, config, test_mode=False):
        if config == None or not config.contains("mongo_url") or not config.contains("db_name"):
            config = {
                "mongo_url": os.getenv("MONGODB_URL"),
                "db_name": os.getenv("MONGODB_DB_NAME")
            }
            CustomLogger()._get_logger().info("Database's config: " + str(config))

        self.client = MongoClient(config["mongo_url"])
        
        if test_mode:
            CustomLogger()._get_logger().info("Database: Test mode.")
            self.db = self.client['test']
        else:
            self.db = self.client[config["db_name"]]
            CustomLogger()._get_logger().info(f"Database: Connected with database {self.db}.")
        self.collections = set()

    def _add_doc_with_timestamp(self, collection_name=None, document=None, session=None):
        '''Add new document to collection with timestamp'''
        if collection_name is None or document is None:
            return None
        
        document[self.FIELD_TIMESTAMP] = datetime.now()

        result = self.db[collection_name].insert_one(document)

        CustomLogger()._get_logger().info(f'Added document with ID: {result.inserted_id}')
        return result.inserted_id
    
    def get_services_status_collection(self):
        return self.db.get_collection(self.FIELD_SERVICES_STATUS_COLLECTION)
    
    def get_services_status_doc_by_id(self, id, is_one):
        if is_one:
            return self.get_services_status_collection().find_one(
                {
                    self.FIELD_UID: id
                }
            )
        else:
            return self.get_services_status_collection().find(
                {
                    self.FIELD_UID: id
                }
            )
        
    def get_action_history_collection(self):
        return self.db.get_collection(self.FIELD_ACTION_HISTORY_COLLECTION)
    
    def write_action_history(self, uid: str, service_type: str, value: any, session):
        action = {
            self.FIELD_UID: uid,
            self.FIELD_SERVICE_TYPE: service_type,
            self.FIELD_DESCRIPTION: f"{service_type} set to {value}"
        }

        self._add_doc_with_timestamp(
            collection_name=self.FIELD_ACTION_HISTORY_COLLECTION,
            document=action,
            session=session
        )
        
    def update_service_status(self, uid: str, service_type: str, value: str, session):
        self.get_services_status_collection().update_one(
            {
                self.FIELD_UID: uid
            },
            {
                "$set": {
                    service_type: value
                }
            },
            session=session
        )

if __name__ == '__main__':
    def test():
        CustomLogger()._get_logger().info("Database: Test mode.")

        document = {
            'key': 'value'
        }
        result = Database(None, True)._instance._add_doc_with_timestamp('test_collection', document)

    test()