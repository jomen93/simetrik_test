import re
import os
from typing import Dict, Any
from .models import SourceCV

class CVParser:
    def parse(self, file_path: str) -> SourceCV:
        with open(file_path, 'r') as f:
            content = f.read()
        
        source_id = self._extract_source_id(content)
        expected_files = self._extract_file_stats(content)
        upload_window = self._extract_upload_window(content)
        filename_patterns = self._extract_filename_patterns(content)
        entity_stats = self._extract_entity_stats(content)
        empty_file_stats = self._extract_empty_file_stats(content)

        return SourceCV(
            source_id=source_id,
            expected_files_by_day=expected_files,
            upload_window_by_day=upload_window,
            filename_patterns=filename_patterns,
            entity_stats=entity_stats,
            empty_file_stats=empty_file_stats
        )

    def _extract_source_id(self, content: str) -> str:
        match = re.search(r'\*\*Resource ID\*\*: (\d+)', content)
        return match.group(1) if match else "Unknown"

    def _extract_file_stats(self, content: str) -> Dict[str, Any]:
        # Extract table "File Processing Statistics by Day"
        # | Day | Mean Files | Median Files | Mode Files | StdDev Files | Min Files | Max Files |
        stats = {}
        table_match = re.search(r'File Processing Statistics by Day.*?\n(\|.*\|\n)+', content, re.DOTALL)
        if table_match:
            table_str = table_match.group(0)
            rows = table_str.strip().split('\n')
            # Skip header and separator
            data_rows = [r for r in rows if r.startswith('|') and '---' not in r and 'Mean Files' not in r]
            for row in data_rows:
                cols = [c.strip() for c in row.split('|') if c.strip()]
                if len(cols) >= 7:
                    day = cols[0]
                    stats[day] = {
                        "mean": float(cols[1]) if cols[1].replace('.','',1).isdigit() else 0,
                        "median": float(cols[2]) if cols[2].replace('.','',1).isdigit() else 0,
                        "mode": float(cols[3]) if cols[3].replace('.','',1).isdigit() else 0,
                        "min": int(cols[5]) if cols[5].isdigit() else 0,
                        "max": int(cols[6]) if cols[6].isdigit() else 0,
                        "std_dev": float(cols[4]) if cols[4].replace('.','',1).isdigit() else 0
                    }
        return stats

    def _extract_upload_window(self, content: str) -> Dict[str, Any]:
        # Extract table "Upload Schedule Patterns by Day"
        # | Day | ... | Upload Time Window Expected | ... |
        windows = {}
        table_match = re.search(r'Upload Schedule Patterns by Day.*?\n(\|.*\|\n)+', content, re.DOTALL)
        if table_match:
            table_str = table_match.group(0)
            rows = table_str.strip().split('\n')
            data_rows = [r for r in rows if r.startswith('|') and '---' not in r and 'Upload Hour' not in r]
            for row in data_rows:
                cols = [c.strip() for c in row.split('|') if c.strip()]
                if len(cols) >= 6:
                    day = cols[0]
                    window_str = cols[5] # Upload Time Window Expected
                    # Format: 08:00:00–09:00:00 UTC
                    if '–' in window_str:
                        start, end = window_str.split('–')
                        windows[day] = {"start": start.strip().replace(' UTC', ''), "end": end.strip().replace(' UTC', '')}
                    elif '-' in window_str:
                         start, end = window_str.split('-')
                         windows[day] = {"start": start.strip().replace(' UTC', ''), "end": end.strip().replace(' UTC', '')}
                    else:
                        windows[day] = {"start": None, "end": None}
        return windows

    def _extract_filename_patterns(self, content: str) -> list:
        patterns = []
        match = re.search(r'Generic structure\s*`([^`]+)`', content)
        if match:
            patterns.append(match.group(1))
        return patterns

    def _extract_entity_stats(self, content: str) -> Dict[str, Any]:
        # Extract "Entity Statistics by Day of Week"
        # This is complex because cells contain multiline text with <br>
        # We will try to capture the table and parse it.
        stats = {}
        # Find the table after "Entity Statistics by Day of Week"
        # It starts with | Entity | Monday | ...
        
        # Regex to find the table block
        # It ends when we hit a double newline or end of file or a new header ##
        match = re.search(r'Entity Statistics by Day of Week.*?\n(\|.*\|\n)+', content, re.DOTALL)
        if match:
            table_str = match.group(0)
            rows = table_str.strip().split('\n')
            # Header
            header_row = [r for r in rows if 'Entity' in r and 'Monday' in r][0]
            headers = [c.strip() for c in header_row.split('|') if c.strip()]
            # Days are headers[1:]
            days = headers[1:]
            
            data_rows = [r for r in rows if r.startswith('|') and '---' not in r and 'Entity' not in r]
            
            for row in data_rows:
                cols = [c.strip() for c in row.split('|') if c.strip()]
                if not cols: continue
                entity = cols[0]
                stats[entity] = {}
                for i, day_stat in enumerate(cols[1:]):
                    if i < len(days):
                        day_name = days[i]
                        # Parse "Median Files: 1.00<br>..."
                        file_match = re.search(r'Median Files: ([\d\.]+)', day_stat)
                        row_match = re.search(r'Median Rows: ([\d\.]+)', day_stat)
                        
                        stats[entity][day_name] = {
                            "median_files": float(file_match.group(1)) if file_match else 0,
                            "median_rows": float(row_match.group(1)) if row_match else 0
                        }
        return stats

    def _extract_empty_file_stats(self, content: str) -> Dict[str, Any]:
        # Extract "Day-of-Week Summary" table for Empty Files Analysis
        # | Day | Row Statistics | Empty Files Analysis | Processing Notes |
        stats = {}
        match = re.search(r'Day-of-Week Summary.*?\n(\|.*\|\n)+', content, re.DOTALL)
        if match:
            table_str = match.group(0)
            rows = table_str.strip().split('\n')
            data_rows = [r for r in rows if r.startswith('|') and '---' not in r and 'Row Statistics' not in r]
            
            for row in data_rows:
                cols = [c.strip() for c in row.split('|') if c.strip()]
                if len(cols) >= 3:
                    day = cols[0]
                    empty_analysis = cols[2] # Empty Files Analysis column
                    
                    # Parse "Min: 0<br>Max: 1<br>Mean: 0.40..."
                    day_stats = {}
                    for line in empty_analysis.split('<br>'):
                        if ':' in line:
                            key, val = line.split(':', 1)
                            key = key.strip().lower().replace('• ', '').replace('•', '')
                            val = val.strip()
                            if val.replace('.','',1).isdigit():
                                day_stats[key] = float(val)
                    
                    stats[day] = day_stats
        return stats
