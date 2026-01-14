"""
Logging Configuration Module for VOLT-X
Supports Run ID and CSV logging.
"""
import logging
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional

def setup_logger(
    name: str = "voltx",
    level: int = logging.INFO,
    log_dir: str = "./logs",
    run_id: Optional[str] = None
) -> logging.Logger:
    """Setup Volt-X Main Logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Format
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console Handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)
    
    # File Handler
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Filename Logic
    # if run_id provided: voltx_{run_id}.log
    # else: voltx_{date}.log
    if run_id:
        filename = f"{name}_{run_id}.log"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{name}_{today}.log"
        
    file_handler = logging.FileHandler(
        f"{log_dir}/{filename}",
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    
    return logger


def get_csv_logger(run_id: Optional[str] = None, report_dir: str = "./reports") -> logging.Logger:
    """
    Structured CSV Logger for Trades.
    Writes comma-separated values for analysis.
    """
    logger_name = f"voltx_trades_{run_id}" if run_id else "voltx_trades"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
        
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    
    if run_id:
        filename = f"trades_{run_id}.csv"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"trades_{today}.csv"
        
    filepath = f"{report_dir}/{filename}"
    
    # Check if file exists to write header
    file_exists = Path(filepath).exists()
    
    handler = logging.FileHandler(filepath, encoding="utf-8")
    # Pure message formatter
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    
    # Write Header if new
    if not file_exists:
        header = "timestamp,symbol,strategy,tier,regime,side,size,entry_price,exit_price,gross_pnl_pct,net_pnl_pct,fees_slippage,reason"
        logger.info(header)
        
    return logger

# Global Loggers (Initialized lazily or re-initialized in main)
# We keep a default logger but main should re-init with run_id
logger = setup_logger() 
