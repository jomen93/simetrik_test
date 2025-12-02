import os
import re
import logging
from typing import List, Dict, Any
from .tools import AgentTools
from .llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

class ReActAgent:
    """
    A minimal implementation of a ReAct (Reasoning + Acting) Agent.
    It uses an LLM to decide which tools to use to solve the problem.
    """
    def __init__(self, data_dir: str, provider: str = "mock", api_key: str = None, model: str = None):
        self.tools = AgentTools(data_dir)
        self.llm = get_llm_provider(provider, api_key, model)
        self.max_steps = 25
        
    def run(self, date_str: str) -> Dict[str, Any]:
        """
        Main loop of the agent.
        Goal: Analyze the data for the given date and produce a report.
        """
        # Goal is now more high-level, letting the agent rely on its tools/context to define "incidents"
        goal = f"Perform a Data Quality Analysis for {date_str}. Check for any critical anomalies based on the business rules defined for each source."
        logger.info(f"Starting Agent Run. Goal: {goal}")
        
        history = f"Goal: {goal}\n\nAvailable Tools:\n"
        history += "- scan_day_incidents(date_str): EFFICIENT. Scans ALL sources and returns a summary of incidents. USE THIS FIRST.\n"
        history += "- list_sources_for_date(date_str): Returns list of source IDs. (Use only if needed)\n"
        history += "- get_source_cv_rules(source_id): Returns expected patterns for a source.\n"
        history += "- check_anomalies(date_str, source_id): Runs technical detectors for a SINGLE source.\n"
        history += "- finish(summary): Returns the final answer. The summary MUST be a professional Markdown report following this EXACT structure:\n"
        history += "  ## Executive Summary\n  [Brief overview of the analysis]\n\n"
        history += "  ## Critical Incidents\n  (Group by Source)\n"
        history += "  ### Source [ID]\n  - **[Count] [Type] incident** (Severity: [High/Medium/Low])\n\n"
        history += "  ## Recommendations\n  - **[Action]**: [Description]\n"
        history += "  Use bolding and lists for readability.\n\n"
        
        step = 0
        history += "IMPORTANT: You must follow the ReAct pattern strictly:\n"
        history += "1. Output a 'Thought:' line explaining your reasoning.\n"
        history += "2. Output an 'Action:' line with the tool to use. Format: Action: tool_name(args)\n"
        history += "3. Wait for the 'Observation:' line.\n"
        history += "4. When you have the final report, you MUST use the finish tool. Do NOT just output the text.\n"
        history += "   CORRECT: Action: finish(\"The report is...\")\n"
        history += "   WRONG: The report is...\n"
        history += "Example:\nThought: I need to check sources.\nAction: list_sources_for_date(2025-09-09)\n\n"
        history += "Before taking any action, output a 'Plan:' line describing your strategy.\n"
        
        step = 0
        while step < self.max_steps:
            logger.info(f"Step {step + 1} (Max {self.max_steps})")
            
            # 1. LLM Decides (Thought + Action)
            llm_output = self.llm.generate(history)
            logger.info(f"LLM Output:\n{llm_output}")
            
            # Check for Plan
            if "Plan:" in llm_output:
                plan_match = re.search(r"Plan:(.*)", llm_output)
                if plan_match:
                    logger.info(f"Agent Plan: {plan_match.group(1).strip()}")

            history += f"{llm_output}\n"
            
            # 2. Parse Action
            # Use re.DOTALL to allow matching across newlines for the arguments
            action_match = re.search(r"Action: (\w+)\((.*)\)", llm_output, re.DOTALL)
            if not action_match:
                # If no action, maybe it's just thinking or done
                if "Final Answer:" in llm_output:
                    final_answer = llm_output.split("Final Answer:")[1].strip()
                    logger.info(f"Final Answer: {final_answer}")
                    return {
                        "summary": final_answer,
                        "incidents": self.tools.scan_results,
                        "stats": self.tools.source_stats,
                        "usage": self.llm.get_usage()
                    }
                
                # If finish is called without Action: prefix (sometimes LLMs do this)
                if "finish(" in llm_output:
                     match = re.search(r"finish\((.*)\)", llm_output)
                     if match:
                         final_answer = match.group(1).replace('"', '').replace("'", "").strip()
                         logger.info(f"Final Answer (inferred): {final_answer}")
                         return {
                            "summary": final_answer,
                            "incidents": self.tools.scan_results,
                            "stats": self.tools.source_stats,
                            "usage": self.llm.get_usage()
                        }

                step += 1
                continue
                
            tool_name = action_match.group(1)
            tool_args = action_match.group(2).replace('"', '').replace("'", "").strip()
            
            logger.info(f"Executing Tool: {tool_name} with args: {tool_args}")
            
            # 3. Execute Tool
            observation = self._execute_tool(tool_name, tool_args, date_str)
            logger.info(f"Observation: {observation}")
            
            # 4. Update History
            observation_str = f"Observation: {observation}\n"
            history += observation_str
            
            if tool_name == "finish":
                return {
                    "summary": tool_args,
                    "incidents": self.tools.scan_results,
                    "stats": self.tools.source_stats,
                    "usage": self.llm.get_usage()
                }
                
            step += 1
            
        return {
            "summary": "Agent stopped (max steps reached).",
            "incidents": self.tools.scan_results,
            "stats": self.tools.source_stats,
            "usage": self.llm.get_usage()
        }

    def _execute_tool(self, tool_name: str, args: str, date_str: str) -> str:
        try:
            if tool_name == "scan_day_incidents":
                return self.tools.scan_day_incidents(date_str)

            elif tool_name == "list_sources_for_date":
                sources = self.tools.list_sources_for_date(date_str)
                return f"Found {len(sources)} sources: {sources[:5]}... (truncated)"
            
            elif tool_name == "get_source_cv_rules":
                return self.tools.get_source_cv_rules(args)
            
            elif tool_name == "check_anomalies":
                # args might be "2025-09-09, 207936" or just "207936" if we infer date
                if "," in args:
                    d, s = args.split(",")
                    return self.tools.check_anomalies(d.strip(), s.strip())
                else:
                    return self.tools.check_anomalies(date_str, args.strip())
                    
            elif tool_name == "finish":
                return "Finished."
                
            else:
                return f"Error: Unknown tool '{tool_name}'"
        except Exception as e:
            return f"Error executing tool: {str(e)}"
