import os
import json
from typing import List, Dict
from .models import ConsolidatedReport, SourceCV, IncidentSeverity

class LLMAnalyzer:
    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        # Aquí inicializarías tu cliente, e.g., OpenAI(api_key=...)
        pass

    def analyze_report(self, report: ConsolidatedReport, cvs: Dict[str, SourceCV]) -> str:
        """
        Envía el reporte consolidado y el contexto de los CVs al LLM para un análisis cualitativo.
        """
        if not self.api_key:
            return "LLM Analysis Skipped: No API Key provided."

        # 1. Construir el Contexto (Prompt Engineering)
        prompt = self._build_prompt(report, cvs)

        # 2. Llamar al LLM (Simulado aquí para el ejemplo)
        # response = client.chat.completions.create(model=self.model, messages=[...])
        # return response.choices[0].message.content
        
        return f"[MOCK LLM OUTPUT]\nAnálisis de Inteligencia Artificial para {report.date}:\nEl reporte indica {len(report.sources)} fuentes con incidentes. La detección de 'Missing File' en la fuente 207936 es consistente con el patrón de martes..."

    def _build_prompt(self, report: ConsolidatedReport, cvs: Dict[str, SourceCV]) -> str:
        """
        Construye un prompt rico en contexto para que el LLM pueda razonar.
        """
        
        # Resumen de incidentes
        incidents_summary = []
        for source in report.sources:
            if source.status != IncidentSeverity.ALL_GOOD:
                cv_info = cvs.get(source.source_id)
                context_note = ""
                if cv_info:
                    # Le damos al LLM "pistas" del CV para que haga el doble check
                    context_note = f"(Contexto CV: Patrón esperado {cv_info.expected_files_by_day}, Ventana {cv_info.upload_window_by_day})"
                
                incidents_summary.append(f"""
                - Source: {source.source_id}
                  Status: {source.status}
                  Incidents: {[i.description for i in source.incidents]}
                  Context: {context_note}
                """)
        
        prompt = f"""
        Actúa como un Analista Senior de Operaciones de Datos (Data Ops).
        
        Tu tarea es realizar un "Double Check" y generar un resumen ejecutivo del siguiente reporte técnico de incidentes.
        
        FECHA DEL REPORTE: {report.date}
        
        INCIDENTES DETECTADOS POR EL SISTEMA:
        {"".join(incidents_summary)}
        
        INSTRUCCIONES:
        1. Validación Lógica: Revisa si los incidentes tienen sentido. Por ejemplo, si falta un archivo pero el CV dice que ese día no se esperan archivos, márcalo como "Falso Positivo Probable".
        2. Priorización: Identifica qué incidentes requieren acción inmediata real (URGENT).
        3. Redacción: Genera un texto final para el cliente en el formato:
           * Urgent Action Required
           * Needs Attention
           * No Action Needed
        
        Usa un tono profesional y directo.
        """
        return prompt
