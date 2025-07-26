import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from pymongo.errors import ConnectionFailure, DuplicateKeyError
import logging

logger = logging.getLogger(__name__)


class MongoDBConnection:
    """Manages MongoDB connection and database operations"""
    
    def __init__(self, connection_string: str = None, database_name: str = None):
        self.connection_string = connection_string or os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
        self.database_name = database_name or os.getenv("DATABASE_NAME", "mexc")
        self.client = None
        self.db = None
        
    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.server_info()
            self.db = self.client[self.database_name]
            logger.info(f"Connected to MongoDB database: {self.database_name}")
            return True
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    def setup_collections(self):
        """Create collections and indexes as per schema"""
        try:
            # Market Data Collection Indexes
            market_indexes = [
                IndexModel([("symbol", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("timestamp", DESCENDING)], expireAfterSeconds=604800),  # 7 days TTL
                IndexModel([("volume_analysis.is_spike", ASCENDING)]),
                IndexModel([("indicators.rsi_14", ASCENDING)])
            ]
            self.db.market_data.create_indexes(market_indexes)
            
            # Funding Data Collection Indexes
            funding_indexes = [
                IndexModel([("symbol", ASCENDING), ("timestamp", DESCENDING)]),
                IndexModel([("analysis.rate_extreme", ASCENDING)])
            ]
            self.db.funding_data.create_indexes(funding_indexes)
            
            # Alerts Collection Indexes
            alert_indexes = [
                IndexModel([("symbol", ASCENDING), ("detected_at", DESCENDING)]),
                IndexModel([("alert_type", ASCENDING)])
            ]
            self.db.alerts.create_indexes(alert_indexes)
            
            logger.info("Database collections and indexes created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up collections: {e}")
            return False
    
    def insert_market_data(self, data: Dict) -> bool:
        """Insert market data into collection"""
        try:
            self.db.market_data.insert_one(data)
            return True
        except DuplicateKeyError:
            logger.debug(f"Duplicate market data for {data['symbol']} at {data['timestamp']}")
            return False
        except Exception as e:
            logger.error(f"Error inserting market data: {e}")
            return False
    
    def insert_funding_data(self, data: Dict) -> bool:
        """Insert funding data into collection"""
        try:
            self.db.funding_data.insert_one(data)
            return True
        except DuplicateKeyError:
            logger.debug(f"Duplicate funding data for {data['symbol']} at {data['timestamp']}")
            return False
        except Exception as e:
            logger.error(f"Error inserting funding data: {e}")
            return False
    
    def insert_alert(self, alert: Dict) -> bool:
        """Insert alert into collection"""
        try:
            self.db.alerts.insert_one(alert)
            logger.warning(f"Alert created: {alert['alert_type']} for {alert['symbol']}")
            return True
        except Exception as e:
            logger.error(f"Error inserting alert: {e}")
            return False
    
    def get_recent_candles(self, symbol: str, limit: int = 60) -> List[Dict]:
        """Get recent candles for a symbol"""
        try:
            cursor = self.db.market_data.find(
                {"symbol": symbol},
                {"_id": 0}
            ).sort("timestamp", DESCENDING).limit(limit)
            
            candles = list(cursor)
            candles.reverse()  # Return in chronological order
            return candles
        except Exception as e:
            logger.error(f"Error fetching recent candles: {e}")
            return []
    
    def get_latest_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get latest funding rate for a symbol"""
        try:
            return self.db.funding_data.find_one(
                {"symbol": symbol},
                {"_id": 0},
                sort=[("timestamp", DESCENDING)]
            )
        except Exception as e:
            logger.error(f"Error fetching latest funding rate: {e}")
            return None
    
    def get_average_volume(self, symbol: str, minutes: int) -> float:
        """Calculate average volume over specified minutes"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            pipeline = [
                {
                    "$match": {
                        "symbol": symbol,
                        "timestamp": {"$gte": start_time}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "avg_volume": {"$avg": "$ohlcv.volume"}
                    }
                }
            ]
            
            result = list(self.db.market_data.aggregate(pipeline))
            return result[0]["avg_volume"] if result else 0
            
        except Exception as e:
            logger.error(f"Error calculating average volume: {e}")
            return 0
    
    def check_duplicate_candle(self, symbol: str, timestamp: datetime) -> bool:
        """Check if candle already exists"""
        try:
            exists = self.db.market_data.find_one(
                {"symbol": symbol, "timestamp": timestamp}
            )
            return exists is not None
        except Exception as e:
            logger.error(f"Error checking duplicate candle: {e}")
            return False