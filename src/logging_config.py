import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging(name: str, log_level: str = "DEBUG") -> logging.Logger:
    """
    Set up comprehensive logging with file rotation
    
    Args:
        name: Logger name (usually __name__)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    
    # Create logs directory
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # File handler with rotation (10MB max, keep 5 backups)
    log_filename = os.path.join(log_dir, f'mexc_monitor_{datetime.now().strftime("%Y%m%d")}.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # File gets everything
    
    # Console handler (less verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Detailed formatter for file
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Simple formatter for console
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Also create separate files for different log types
    
    # Manipulation alerts log
    alerts_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f'manipulation_alerts_{datetime.now().strftime("%Y%m%d")}.log'),
        maxBytes=5*1024*1024,
        backupCount=10
    )
    alerts_handler.setLevel(logging.WARNING)
    alerts_handler.setFormatter(file_formatter)
    
    # Add filter to only log manipulation-related messages
    class ManipulationFilter(logging.Filter):
        def filter(self, record):
            return 'manipulation' in record.getMessage().lower() or record.levelno >= logging.WARNING
    
    alerts_handler.addFilter(ManipulationFilter())
    logger.addHandler(alerts_handler)
    
    # API errors log
    api_errors_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f'api_errors_{datetime.now().strftime("%Y%m%d")}.log'),
        maxBytes=5*1024*1024,
        backupCount=5
    )
    api_errors_handler.setLevel(logging.ERROR)
    api_errors_handler.setFormatter(file_formatter)
    logger.addHandler(api_errors_handler)
    
    # Dashboard snapshots log (for complete monitoring output)
    dashboard_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f'dashboard_{datetime.now().strftime("%Y%m%d")}.log'),
        maxBytes=10*1024*1024,
        backupCount=10
    )
    dashboard_handler.setLevel(logging.INFO)
    
    # Special formatter for dashboard
    dashboard_formatter = logging.Formatter(
        '\n%(asctime)s\n%(message)s\n' + '='*80,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    dashboard_handler.setFormatter(dashboard_formatter)
    
    # Remove filter - we'll use a different approach for dashboard logging
    logger.addHandler(dashboard_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with standard configuration"""
    return setup_logging(name, os.getenv('LOG_LEVEL', 'DEBUG'))