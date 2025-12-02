"""
Detectors Module
================

This module contains the specific logic for detecting different types of incidents.
Each detector implements the `Detector` interface and is responsible for a single type of check.

Detectors implemented:
- MissingFileDetector: Checks if the number of files is below the expected minimum or if specific entities are missing.
- DuplicatedFailedFileDetector: Checks for files marked as duplicated, failed, or having duplicate filenames.
- UnexpectedEmptyFileDetector: Checks for files with 0 rows (unless expected).
- UnexpectedVolumeVariationDetector: Checks for significant deviations in file count or row count compared to historical stats.
- LateUploadDetector: Checks if files were uploaded significantly later than the expected window.
- PreviousFileDetector: Identifies files that belong to a previous period (historical uploads).
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import re
from .models import Incident, IncidentType, IncidentSeverity, FileMetadata, SourceCV

class Detector:
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        raise NotImplementedError

class MissingFileDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        day_name = current_date.strftime("%a") # Mon, Tue, ...
        
        expected_stats = cv.expected_files_by_day.get(day_name)
        if not expected_stats:
            return []

        min_files = expected_stats.get("min", 0)
        mean_files = expected_stats.get("mean", 0)
        median_files = expected_stats.get("median", 0)
        mode_files = expected_stats.get("mode", 0)
        
        # If min_files is 0, it might be an outlier. If mean is high (e.g. >= 1), getting 0 is suspicious.
        # Feedback indicates that for Source 207936, 0 files on Tue is Missing File, even if min=0 in CV.
        # So we trust mean/mode more if min is 0 but mean is significant.
        threshold = min_files
        if min_files == 0:
            # If min is 0, check if we usually expect files
            if median_files > 0 or mode_files > 0:
                threshold = 1 # Expect at least something
            else:
                threshold = 0 # 0 is normal
            
        if len(files) < threshold:
            incidents.append(Incident(
                incident_type=IncidentType.MISSING_FILE,
                severity=IncidentSeverity.URGENT,
                description=f"Expected at least {threshold} files (mean {mean_files}), but found {len(files)}.",
                recommendation="Contact provider to confirm generation and request immediate re-delivery.",
                source_id=cv.source_id,
                details={"expected_min": threshold, "found": len(files), "cv_min": min_files, "cv_mean": mean_files}
            ))
        
        # Check for missing entities
        # If an entity has median_files > 0 for this day, we expect it.
        present_entities = set()
        for f in files:
            # Extract entity from filename
            # Pattern: {randomId}_{Merchant}_{Entity}_settlement...
            # This is tricky without a robust regex for every file.
            # We can try to match against known entities in cv.entity_stats
            for entity in cv.entity_stats.keys():
                if f"_{entity}_" in f.filename:
                    present_entities.add(entity)
                    break
        
        for entity, stats in cv.entity_stats.items():
            day_stats = stats.get(current_date.strftime("%A")) # Monday, Tuesday...
            if not day_stats:
                 # Try matching short name to long name if needed, but CV parser uses full names for Entity stats
                 continue
            
            if day_stats["median_files"] > 0 and entity not in present_entities:
                 # It's missing
                 # But is it Urgent? If it's a high volume entity maybe.
                 # For now, let's mark as URGENT if it's completely missing and expected.
                 incidents.append(Incident(
                    incident_type=IncidentType.MISSING_FILE,
                    severity=IncidentSeverity.URGENT,
                    description=f"Expected files for entity '{entity}' but none received.",
                    recommendation=f"Verify if '{entity}' generated files today and request re-delivery.",
                    source_id=cv.source_id,
                    details={"entity": entity}
                 ))

        return incidents

class DuplicatedFailedFileDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        seen_filenames = set()
        for f in files:
            if f.is_duplicated or f.status == "STOPPED" or f.status == "failed":
                 incidents.append(Incident(
                    incident_type=IncidentType.DUPLICATED_FILE,
                    severity=IncidentSeverity.URGENT,
                    description=f"File {f.filename} is duplicated or failed.",
                    recommendation="Check file status and re-process if needed.",
                    source_id=cv.source_id,
                    file_name=f.filename,
                    details={"status": f.status, "is_duplicated": f.is_duplicated}
                ))
            
            if f.filename in seen_filenames:
                 incidents.append(Incident(
                    incident_type=IncidentType.DUPLICATED_FILE,
                    severity=IncidentSeverity.URGENT,
                    description=f"File {f.filename} has a duplicate name.",
                    recommendation="Check for duplicate uploads.",
                    source_id=cv.source_id,
                    file_name=f.filename
                ))
            seen_filenames.add(f.filename)
        return incidents

class UnexpectedEmptyFileDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        day_name = current_date.strftime("%a")
        empty_stats = cv.empty_file_stats.get(day_name, {})
        max_empty = empty_stats.get("max", 0)
        
        # If max empty files > 0, then empty files are allowed.
        # We should only flag if we have MORE empty files than max?
        # Or if the file is empty and max_empty is 0.
        
        # Count current empty files
        empty_files_count = sum(1 for f in files if f.rows == 0)
        
        for f in files:
            if f.rows == 0:
                # If empty files are allowed (max > 0), we might skip this.
                # But maybe we should check if THIS file is expected to be empty?
                # The CV says "POS files are structurally empty".
                # If we can't distinguish, we rely on stats.
                if max_empty > 0:
                    # Allowed.
                    continue
                
                incidents.append(Incident(
                    incident_type=IncidentType.UNEXPECTED_EMPTY,
                    severity=IncidentSeverity.URGENT,
                    description=f"File {f.filename} is empty (0 rows).",
                    recommendation="Verify if the empty file is expected.",
                    source_id=cv.source_id,
                    file_name=f.filename,
                    details={"rows": f.rows, "max_expected_empty": max_empty}
                ))
        return incidents

class UnexpectedVolumeVariationDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        day_name = current_date.strftime("%a")
        stats = cv.expected_files_by_day.get(day_name)
        
        if not stats:
            return []

        # Check total volume? Or per file?
        # Prompt: "si el archivo tiene un volumen de registros inesperados con base a sus patrones previos"
        # We have "Mean Files" and "StdDev Files" (volume of files).
        # We also have "Entity Statistics" with "Median Rows".
        
        # Let's check total files volume first
        total_files = len(files)
        mean_files = stats.get("mean", 0)
        std_dev = stats.get("std_dev", 0)
        
        # Simple anomaly detection: > 2 std dev?
        # Or just use Min/Max from CV?
        min_files = stats.get("min", 0)
        max_files = stats.get("max", 0)
        
        # If we are way off
        if total_files > max_files * 1.5 and max_files > 0: # Heuristic
             incidents.append(Incident(
                incident_type=IncidentType.VOLUME_VARIATION,
                severity=IncidentSeverity.NEEDS_ATTENTION,
                description=f"Total files ({total_files}) significantly higher than expected max ({max_files}).",
                recommendation="Investigate the surge in files.",
                source_id=cv.source_id,
                details={"total_files": total_files, "expected_max": max_files}
            ))

        # Check rows per entity if possible
        for f in files:
            # Identify entity
            entity = None
            for e in cv.entity_stats.keys():
                if f"_{e}_" in f.filename:
                    entity = e
                    break
            
            if entity:
                day_full = current_date.strftime("%A")
                entity_day_stats = cv.entity_stats.get(entity, {}).get(day_full)
                if entity_day_stats:
                    median_rows = entity_day_stats.get("median_rows", 0)
                    if median_rows > 0:
                        # If rows are way different. e.g. 10x or 0.1x
                        if f.rows > median_rows * 3 or f.rows < median_rows * 0.1:
                             incidents.append(Incident(
                                incident_type=IncidentType.VOLUME_VARIATION,
                                severity=IncidentSeverity.NEEDS_ATTENTION,
                                description=f"File {f.filename} has {f.rows} rows, deviating from median {median_rows}.",
                                recommendation="Check for data completeness or duplication.",
                                source_id=cv.source_id,
                                file_name=f.filename,
                                details={"rows": f.rows, "median_rows": median_rows}
                            ))

        return incidents

class LateUploadDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        day_name = current_date.strftime("%a")
        window = cv.upload_window_by_day.get(day_name)
        
        if not window or not window["end"]:
            return []

        try:
            # Parse window end time
            end_time_str = window["end"]
            # It's just time "HH:MM:SS". We need to combine with current_date
            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            expected_end_dt = datetime.combine(current_date.date(), end_time)
            
            # Add 4 hours tolerance
            tolerance_dt = expected_end_dt + timedelta(hours=4)
            
            for f in files:
                # Parse uploaded_at
                # Format: 2025-09-08T08:06:47.089856+00:00
                uploaded_at = datetime.fromisoformat(f.uploaded_at)
                # Remove timezone for comparison if needed, or ensure both are aware
                if uploaded_at.tzinfo:
                    uploaded_at = uploaded_at.replace(tzinfo=None) # Assume UTC as per prompt
                
                if uploaded_at > tolerance_dt:
                    incidents.append(Incident(
                        incident_type=IncidentType.LATE_UPLOAD,
                        severity=IncidentSeverity.NEEDS_ATTENTION, # Warning
                        description=f"File {f.filename} uploaded at {uploaded_at}, significantly after expected {end_time_str}.",
                        recommendation="Monitor upload delays.",
                        source_id=cv.source_id,
                        file_name=f.filename,
                        details={"uploaded_at": str(uploaded_at), "expected_end": str(expected_end_dt)}
                    ))
        except Exception as e:
            # Log error parsing time
            pass

        return incidents

class PreviousFileDetector(Detector):
    def detect(self, files: List[FileMetadata], cv: SourceCV, current_date: datetime) -> List[Incident]:
        incidents = []
        for f in files:
            # Extract date from filename
            # Pattern: ..._yyyymmdd.csv
            match = re.search(r'_(\d{8})\.csv$', f.filename)
            if match:
                file_date_str = match.group(1)
                try:
                    file_date = datetime.strptime(file_date_str, "%Y%m%d").date()
                    # If file date is not today (or yesterday depending on logic)
                    # Prompt says "Archivos de períodos anteriores... fuera del ECD"
                    # Usually files are for T-1 or T-0.
                    # If file date is < current_date - 2 days?
                    if file_date < current_date.date() - timedelta(days=2):
                         incidents.append(Incident(
                            incident_type=IncidentType.PREVIOUS_FILE,
                            severity=IncidentSeverity.ALL_GOOD, # Not critical
                            description=f"File {f.filename} is from a previous period ({file_date}).",
                            recommendation="No action needed, historical upload.",
                            source_id=cv.source_id,
                            file_name=f.filename,
                            details={"file_date": str(file_date)}
                        ))
                except ValueError:
                    pass
        return incidents
