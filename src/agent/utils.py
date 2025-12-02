import logging
import os
import sys

def setup_logging(name: str = None, log_file: str = "agent_run.log", level=logging.INFO):
    """
    Configures a logger that writes to both console and a file.
    If name is None, configures the root logger.
    """
    # Create a custom logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times if setup_logging is called repeatedly
    if logger.hasHandlers():
        return logger

    # Create handlers
    c_handler = logging.StreamHandler(sys.stdout)
    f_handler = logging.FileHandler(log_file)
    
    c_handler.setLevel(level)
    f_handler.setLevel(level)

    # Create formatters and add it to handlers
    # Detailed format for file, simpler for console
    f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    
    f_handler.setFormatter(f_format)
    c_handler.setFormatter(c_format)

    # Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    return logger
