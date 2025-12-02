"""
Agent Core Module
=================

This module defines the main Agent class which orchestrates the entire incident detection process.
It is responsible for:
1. Loading the daily file data.
2. Parsing the Source CVs (Curriculum Vitae) to understand expected patterns.
3. Running a suite of detectors to identify anomalies.
4. Consolidating the findings into a final report.

The Agent follows a modular design where detectors are independent components.
"""

import os
import json
from datetime import datetime
from typing import List, Dict
from .models import FileMetadata, SourceCV, ConsolidatedReport, Incident, IncidentSeverity, SourceReport, UsageStats
from .parsers import CVParser
from .detectors import (
    MissingFileDetector,
    DuplicatedFailedFileDetector,
    UnexpectedEmptyFileDetector,
    UnexpectedVolumeVariationDetector,
    LateUploadDetector,
    PreviousFileDetector
)
from .report import ReportGenerator
from .llm_analyzer import LLMAnalyzer
from .react_agent import ReActAgent

class Agent:
    def __init__(self, data_dir: str, use_llm: bool = False, mode: str = "pipeline", 
                 llm_provider: str = "mock", llm_api_key: str = None, llm_model: str = None):
        self.data_dir = data_dir
        self.use_llm = use_llm
        self.mode = mode # "pipeline" or "agentic"
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.cv_parser = CVParser()
        self.detectors = [
            MissingFileDetector(),
            DuplicatedFailedFileDetector(),
            UnexpectedEmptyFileDetector(),
            UnexpectedVolumeVariationDetector(),
            LateUploadDetector(),
            PreviousFileDetector()
        ]
        self.reporter = ReportGenerator()
        self.llm_analyzer = LLMAnalyzer() if use_llm else None

    def run(self, date_str: str) -> ConsolidatedReport:
        if self.mode == "agentic":
            # Run the ReAct Agent
            react_agent = ReActAgent(self.data_dir, provider=self.llm_provider, api_key=self.llm_api_key, model=self.llm_model)
            result = react_agent.run(date_str)
            
            # Convert incidents dict to List[SourceReport]
            source_reports = []
            stats = result.get("stats", {})

            for source_id, incidents in result["incidents"].items():
                # Determine status based on incidents
                status = IncidentSeverity.ALL_GOOD
                for inc in incidents:
                    if inc.severity == IncidentSeverity.URGENT:
                        status = IncidentSeverity.URGENT
                        break
                    elif inc.severity == IncidentSeverity.NEEDS_ATTENTION and status != IncidentSeverity.URGENT:
                        status = IncidentSeverity.NEEDS_ATTENTION
                
                source_stats = stats.get(source_id, {"processed_files_count": 0, "total_rows": 0})

                source_reports.append(SourceReport(
                    source_id=source_id,
                    status=status,
                    incidents=incidents,
                    processed_files_count=source_stats["processed_files_count"], 
                    total_rows=source_stats["total_rows"]
                ))
            
            # Calculate cost
            usage = result["usage"]
            # Pricing for gpt-4o-mini
            input_cost = (usage["prompt_tokens"] / 1_000_000) * 0.15
            output_cost = (usage["completion_tokens"] / 1_000_000) * 0.60
            total_cost = input_cost + output_cost
            
            usage_stats = UsageStats(
                total_tokens=usage["total_tokens"],
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_cost=total_cost,
                model=self.llm_model or "gpt-4o-mini"
            )

            return ConsolidatedReport(
                date=date_str,
                generated_at=datetime.now(),
                sources=source_reports,
                summary=f"# AGENTIC ANALYSIS\n\n{result['summary']}",
                status=IncidentSeverity.URGENT if any(s.status == IncidentSeverity.URGENT for s in source_reports) else IncidentSeverity.ALL_GOOD,
                usage=usage_stats
            )

        # date_str format: YYYY-MM-DD
        # Find the folder for this date
        # Folder format: {YYYY-MM-DD}_20_00_UTC
        target_folder = None
        for item in os.listdir(self.data_dir):
            if item.startswith(date_str):
                target_folder = os.path.join(self.data_dir, item)
                break
        
        if not target_folder:
            raise FileNotFoundError(f"No data folder found for date {date_str}")

        # Load files.json
        files_path = os.path.join(target_folder, "files.json")
        with open(files_path, 'r') as f:
            files_data = json.load(f)

        # Load CVs
        cvs_dir = os.path.join(self.data_dir, "datasource_cvs")
        source_reports = []
        cv_map = {} # Store CVs for LLM context

        current_date = datetime.strptime(date_str, "%Y-%m-%d")

        for source_id, file_list in files_data.items():
            # Filter files by date (uploaded_at matches execution date)
            daily_files = []
            for f in file_list:
                # uploaded_at format: "2025-09-09T08:09:23.298818+00:00"
                # We only care about the YYYY-MM-DD part
                if f.get("uploaded_at", "").startswith(date_str):
                    daily_files.append(f)
            
            # Parse files
            files = [FileMetadata(**f) for f in daily_files]
            
            # Find CV
            cv_path = os.path.join(cvs_dir, f"{source_id}_native.md")
            if not os.path.exists(cv_path):
                # Skip or log warning
                continue
            
            cv = self.cv_parser.parse(cv_path)
            cv_map[source_id] = cv
            
            # Run detectors
            incidents = []
            for detector in self.detectors:
                incidents.extend(detector.detect(files, cv, current_date))
            
            # Calculate stats
            total_rows = sum(f.rows for f in files)
            
            # Consolidate source report
            source_report = self.reporter.consolidate_source(source_id, incidents, len(files), total_rows)
            source_reports.append(source_report)

        # Generate final report
        final_report = self.reporter.generate(date_str, source_reports)
        
        # Optional: LLM Double Check
        if self.use_llm and self.llm_analyzer:
            llm_summary = self.llm_analyzer.analyze_report(final_report, cv_map)
            final_report.summary += f"\n\n--- LLM VALIDATION ---\n{llm_summary}"
            
        return final_report
