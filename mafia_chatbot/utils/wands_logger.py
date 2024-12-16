import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import uuid

class WandsLogger:
    def __init__(self, path: str, name: str, interval_hours: int = 8):
        # Ensure the directory exists
        os.makedirs(path, exist_ok=True)

        # Generate unique UUID and set name
        self.name = name
        self.uuid = str(uuid.uuid4())

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)  # Capture both DEBUG and ERROR logs

        # Define the log file pattern
        self.log_file_pattern = os.path.join(
            path, f"[%Y-%m-%d_%H-%M-%S]_{name}_{self.uuid}.log"
        )

        # Create and configure handler
        self.handler = TimedRotatingFileHandler(
            filename=self._generate_log_file(),
            when='h',  # Rotate by hour
            interval=interval_hours,  # Rotate every specified hours
            backupCount=0,  # Keep unlimited logs, modify if needed
            encoding='utf-8',
        )

        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        # Add handler to logger
        self.logger.addHandler(self.handler)

    def _generate_log_file(self):
        """Generate the log file name with the current timestamp."""
        current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return os.path.join(
            os.path.dirname(self.log_file_pattern),
            f"[{current_time}]_{self.name}_{self.uuid}.log"
        )

    def debug(self, message: str):
        """Log a debug message."""
        self.logger.debug(message)

    def error(self, message: str):
        """Log an error message."""
        self.logger.error(message)
