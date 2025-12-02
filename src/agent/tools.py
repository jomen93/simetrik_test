from typing import List, Dict, Any
import os
import json
import logging
from datetime import datetime
from .models import FileMetadata, Incident
from .parsers import CVParser
from .detectors import (
    MissingFileDetector,
    UnexpectedVolumeVariationDetector,
    UnexpectedEmptyFileDetector
)

logger = logging.getLogger(__name__)

class AgentTools:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.cv_parser = CVParser()
        # Initialize detectors
        self.detectors = {
            "missing": MissingFileDetector(),
            "volume": UnexpectedVolumeVariationDetector(),
            "empty": UnexpectedEmptyFileDetector()
        }
        self.scan_results: Dict[str, List[Incident]] = {}
        self.source_stats: Dict[str, Dict[str, int]] = {}

    def list_sources_for_date(self, date_str: str) -> List[str]:
        """List all source IDs that have data folders or are expected for a given date."""
        # In a real scenario, this might query a DB. Here we check the file system.
        target_folder = None
        for item in os.listdir(self.data_dir):
            if item.startswith(date_str):
                target_folder = os.path.join(self.data_dir, item)
                break
        
        if not target_folder:
            return []
            
        files_path = os.path.join(target_folder, "files.json")
        if not os.path.exists(files_path):
            return []
            
        with open(files_path, 'r') as f:
            data = json.load(f)
        return list(data.keys())

    def get_daily_files(self, date_str: str, source_id: str) -> List[Dict[str, Any]]:
        """Retrieve the list of files uploaded for a specific source on a specific date."""
        target_folder = None
        for item in os.listdir(self.data_dir):
            if item.startswith(date_str):
                target_folder = os.path.join(self.data_dir, item)
                break
        
        if not target_folder:
            return []

        files_path = os.path.join(target_folder, "files.json")
        with open(files_path, 'r') as f:
            data = json.load(f)
            
        file_list = data.get(source_id, [])
        # Filter by date as per our previous fix
        daily_files = [f for f in file_list if f.get("uploaded_at", "").startswith(date_str)]
        return daily_files

    def get_source_cv_rules(self, source_id: str) -> str:
        """Retrieve the expected behavior rules (CV) for a source."""
        cv_path = os.path.join(self.data_dir, "datasource_cvs", f"{source_id}_native.md")
        if not os.path.exists(cv_path):
            return "No CV found for this source."
            
        cv = self.cv_parser.parse(cv_path)
        # Return a simplified text summary for the LLM
        return f"""
        Source ID: {cv.source_id}
        Expected Files by Day: {cv.expected_files_by_day}
        Upload Window: {cv.upload_window_by_day}
        Empty File Stats: {cv.empty_file_stats}
        """

    def check_anomalies(self, date_str: str, source_id: str) -> str:
        """Run technical detectors on the files and return a list of detected incidents."""
        files_data = self.get_daily_files(date_str, source_id)
        files = [FileMetadata(**f) for f in files_data]
        
        # Calculate stats
        file_count = len(files)
        total_rows = sum(f.rows for f in files)
        self.source_stats[source_id] = {
            "processed_files_count": file_count,
            "total_rows": total_rows
        }
        
        cv_path = os.path.join(self.data_dir, "datasource_cvs", f"{source_id}_native.md")
        if not os.path.exists(cv_path):
            return "Cannot check anomalies: CV missing."
        
        cv = self.cv_parser.parse(cv_path)
        current_date = datetime.strptime(date_str, "%Y-%m-%d")
        
        incidents = []
        for name, detector in self.detectors.items():
            found = detector.detect(files, cv, current_date)
            incidents.extend(found)
            
        # Store incidents for structured reporting
        self.scan_results[source_id] = incidents

        if not incidents:
            return "No technical anomalies detected."
            
        return "\n".join([f"- {i.incident_type.value}: {i.description} (Severity: {i.severity.value})" for i in incidents])

    def scan_day_incidents(self, date_str: str) -> str:
        """
        Scans ALL sources for the given date and returns a summary of ONLY the sources with incidents.
        This is efficient for getting a high-level overview.
        """
        logger.info(f"Scanning incidents for date: {date_str}")
        self.scan_results = {} # Clear previous results
        self.source_stats = {} # Clear stats
        sources = self.list_sources_for_date(date_str)
        if not sources:
            return "No sources found for this date."
            
        report_lines = []
        for source_id in sources:
            result = self.check_anomalies(date_str, source_id)
            if "No technical anomalies detected" not in result and "CV missing" not in result:
                # Summarize the result to save tokens
                lines = result.split('\n')
                missing_count = sum(1 for l in lines if "Missing File" in l)
                volume_count = sum(1 for l in lines if "Unexpected Volume Variation" in l)
                empty_count = sum(1 for l in lines if "Unexpected Empty File" in l)
                
                summary = []
                if missing_count:
                    summary.append(f"- {missing_count} Missing File incident(s)")
                if volume_count:
                    summary.append(f"- {volume_count} Volume Variation incident(s)")
                if empty_count:
                    summary.append(f"- {empty_count} Empty File incident(s)")
                
                report_lines.append(f"Source {source_id}:\n" + "\n".join(summary))
        
        if not report_lines:
            logger.info("No incidents detected.")
            return "No incidents detected across any source."
            
        logger.info(f"Found incidents in {len(report_lines)} sources.")
        return "\n\n".join(report_lines)
