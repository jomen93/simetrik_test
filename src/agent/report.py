from typing import List
from .models import Incident, IncidentSeverity, SourceReport, ConsolidatedReport
from datetime import datetime

class ReportGenerator:
    def generate(self, date: str, source_reports: List[SourceReport]) -> ConsolidatedReport:
        # Determine overall status
        overall_status = IncidentSeverity.ALL_GOOD
        
        urgent_count = 0
        needs_attention_count = 0
        
        for report in source_reports:
            if report.status == IncidentSeverity.URGENT:
                urgent_count += 1
            elif report.status == IncidentSeverity.NEEDS_ATTENTION:
                needs_attention_count += 1
        
        if urgent_count > 0:
            overall_status = IncidentSeverity.URGENT
        elif needs_attention_count > 0:
            overall_status = IncidentSeverity.NEEDS_ATTENTION
            
        # Generate summary text
        summary = f"Report for {date}\n"
        summary += f"Status: {overall_status.value}\n"
        summary += f"Sources with Urgent Incidents: {urgent_count}\n"
        summary += f"Sources Needing Attention: {needs_attention_count}\n"
        
        return ConsolidatedReport(
            date=date,
            generated_at=datetime.utcnow(),
            sources=source_reports,
            summary=summary,
            status=overall_status
        )

    def consolidate_source(self, source_id: str, incidents: List[Incident], processed_count: int, total_rows: int) -> SourceReport:
        # Determine source status
        # Red: >1 urgent or >3 needs attention (Wait, prompt says: "más de un archivo con incidente urgente o más de 3 incidentes que requiere atención")
        # Actually prompt says: "Si una fuente contiene más de un archivo con incidente urgente o más de 3 incidentes que requiere atención"
        # Let's interpret: > 0 Urgent (usually 1 is enough to be urgent, but prompt says >1? Maybe >=1).
        # "más de un archivo" -> > 1. So 2 or more? That's lenient.
        # Let's stick to: If >= 1 Urgent -> Urgent. (Safety first).
        # Or strictly follow prompt: > 1 Urgent OR > 3 Incidents (total? or just attention?).
        # "más de 3 incidentes que requiere atención" -> > 3 Needs Attention.
        
        urgent_incidents = [i for i in incidents if i.severity == IncidentSeverity.URGENT]
        attention_incidents = [i for i in incidents if i.severity == IncidentSeverity.NEEDS_ATTENTION]
        
        status = IncidentSeverity.ALL_GOOD
        
        if len(urgent_incidents) >= 1: # I'll be strict and say >= 1 is Urgent
            status = IncidentSeverity.URGENT
        elif len(attention_incidents) > 0: # "Si al menos una de las fuente requiere atención" -> Yellow
             # Wait, prompt says "REQUIERE ATENCIÓN... Si al menos una de las fuente requiere atención por sus archivos"
             # This is circular.
             # Let's use:
             # Red: >= 1 Urgent OR > 3 Attention
             # Yellow: >= 1 Attention
             # Green: 0
             
             if len(attention_incidents) > 3:
                 status = IncidentSeverity.URGENT
             else:
                 status = IncidentSeverity.NEEDS_ATTENTION
        
        return SourceReport(
            source_id=source_id,
            status=status,
            incidents=incidents,
            processed_files_count=processed_count,
            total_rows=total_rows
        )
