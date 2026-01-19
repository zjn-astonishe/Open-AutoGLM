import re
import json
from dataclasses import dataclass
from openai import OpenAI
from phone_agent.model.client import ModelConfig
from typing import Dict, Any, List, Optional, Tuple
from phone_agent.config.prompts_en import SYSTEM_PROMPT_PLANNER, SYSTEM_PROMPT_TASK_DECOMPOSITION


@dataclass
class SubTask:
    """Represents a subtask in a decomposed workflow."""
    description: str
    tag: str


@dataclass 
class TaskPlan:
    """Represents a task decomposition plan."""
    is_decomposed: bool
    subtasks: List[SubTask]
    current_subtask_index: int = 0
    
    @property
    def current_subtask(self) -> Optional[SubTask]:
        """Get the current subtask being executed."""
        if 0 <= self.current_subtask_index < len(self.subtasks):
            return self.subtasks[self.current_subtask_index]
        return None
    
    def advance_subtask(self) -> bool:
        """Advance to the next subtask. Returns True if there are more subtasks."""
        self.current_subtask_index += 1
        return self.current_subtask_index < len(self.subtasks)
    
    def is_complete(self) -> bool:
        """Check if all subtasks are complete."""
        return self.current_subtask_index >= len(self.subtasks)


class PlannerResponse:
    """Response from the planner containing decision and execution plan."""
    
    def __init__(self, decision: str, execution: str = "", skill_name: str = "", 
                 skill_params: Dict[str, Any] = None, raw_content: str = "",
                 task_plan: Optional[TaskPlan] = None, subtask_status: Dict[str, Any] = None):
        self.decision = decision  # "use_skill" or "use_atomic_actions"
        self.execution = execution  # Raw execution string
        self.skill_name = skill_name  # Name of the skill to use
        self.skill_params = skill_params or {}  # Parameters for the skill
        self.raw_content = raw_content  # Raw LLM response
        self.task_plan = task_plan  # Task decomposition plan
        self.subtask_status = subtask_status or {}  # Subtask completion status


class Planner:
    
    def __init__(self, model_config: ModelConfig | None = None):
        self.config = model_config or ModelConfig()
        self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        self._current_task_plan = None  # Track current task plan
        
    def plan_with_context(
        self, 
        user_task: str,
        current_subtask: Optional[str] = None,
        subtask_progress: Optional[str] = None,
        action_history: List[Dict[str, Any]] = None,
        reflection_result: Optional[List[Dict[str, Any]]] = None
    ) -> PlannerResponse:
        """
        Analyze user task with full context and decide whether to use skills or atomic actions,
        while also evaluating subtask completion status.
        
        Args:
            user_task: Natural language description of the user's task
            current_subtask: Description of current subtask being executed
            subtask_tag: Functional tag of current subtask
            subtask_progress: Progress in subtask sequence (e.g., "2/3")
            action_history: Complete history of actions and their results
            reflection_result: Reflection analysis of previous action (if failed)
            
        Returns:
            PlannerResponse containing decision, execution plan, and subtask status
        """
        
        # Build context information
        context_parts = [f"Overall Task: {user_task}"]
        
        if current_subtask:
            context_parts.append(f"Current Subtask: {current_subtask}")
        if subtask_progress:
            context_parts.append(f"Subtask Progress: {subtask_progress}")
        
        
        context_content = "\n".join(context_parts)
        
        # Build messages for planning
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_PLANNER},
            {"role": "user", "content": context_content}
        ]

        # Add complete action history
        if action_history:
            messages.append(action_history[0])
        if reflection_result:
            messages.append(reflection_result[0])


        print(f"{messages}")
        
        try:
            # Get response from the model
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                extra_body=self.config.extra_body
            )
            
            raw_content = response.choices[0].message.content
            
        except Exception as e:
            print(f"Error calling LLM API: {e}")
            raw_content = ""
        
        # Parse the response
        print(f"RAW PLANNER RESPONSE:\n{raw_content}\n")
        subtask_status = self._parse_subtask_status(raw_content)
        decision, execution = self._parse_router_response(raw_content)
        
        # If decision is to use skill, parse the skill call
        skill_name = ""
        skill_params = {}
        
        if decision == "use_skill" and execution:
            skill_name, skill_params = self._parse_skill_call(execution)
            
        return PlannerResponse(
            decision=decision,
            execution=execution,
            skill_name=skill_name,
            skill_params=skill_params,
            raw_content=raw_content,
            subtask_status=subtask_status
        )
    
    def _parse_router_response(self, content: str) -> Tuple[str, str]:
        """
        Parse the router response to extract decision and execution.
        
        Args:
            content: Raw response content from the model
            
        Returns:
            Tuple of (decision, execution)
        """
        try:
            # Extract decision
            decision_match = re.search(r"<decision>\s*(.*?)\s*</decision>", content, re.DOTALL)
            decision = decision_match.group(1).strip() if decision_match else "use_atomic_actions"
            
            # Extract execution
            execution_match = re.search(r"<execution>\s*(.*?)\s*</execution>", content, re.DOTALL)
            execution = execution_match.group(1).strip() if execution_match else ""
            
            return decision, execution
            
        except Exception as e:
            print(f"Error parsing router response: {e}")
            return "use_atomic_actions", ""
    
    def _parse_skill_call(self, execution: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse skill call string to extract skill name and parameters.
        
        Args:
            execution: Skill call string like "alarm_create(hour=7, minute=30, days=['M', 'W'])"
            
        Returns:
            Tuple of (skill_name, parameters_dict)
        """
        try:
            # Extract skill name and parameters using regex
            match = re.match(r"(\w+)\((.*)\)", execution.strip())
            if not match:
                return "", {}
                
            skill_name = match.group(1)
            params_str = match.group(2)
            
            # Parse parameters
            params = {}
            if params_str.strip():
                # Split by comma, but be careful with nested structures
                param_pairs = self._split_parameters(params_str)
                
                for pair in param_pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Try to evaluate the value safely
                        params[key] = self._safe_eval(value)
            
            return skill_name, params
            
        except Exception as e:
            print(f"Error parsing skill call: {e}")
            return "", {}
    
    def _split_parameters(self, params_str: str) -> List[str]:
        """
        Split parameter string by commas, handling nested structures.
        
        Args:
            params_str: Parameter string like "hour=7, minute=30, days=['M', 'W']"
            
        Returns:
            List of parameter pairs
        """
        params = []
        current_param = ""
        bracket_count = 0
        quote_char = None
        
        for char in params_str:
            if quote_char:
                current_param += char
                if char == quote_char and (len(current_param) == 1 or current_param[-2] != '\\'):
                    quote_char = None
            elif char in ['"', "'"]:
                quote_char = char
                current_param += char
            elif char in ['[', '(', '{']:
                bracket_count += 1
                current_param += char
            elif char in [']', ')', '}']:
                bracket_count -= 1
                current_param += char
            elif char == ',' and bracket_count == 0:
                if current_param.strip():
                    params.append(current_param.strip())
                current_param = ""
            else:
                current_param += char
        
        if current_param.strip():
            params.append(current_param.strip())
            
        return params
    
    def _safe_eval(self, value_str: str) -> Any:
        """
        Safely evaluate a parameter value string.
        
        Args:
            value_str: String representation of the value
            
        Returns:
            Evaluated value
        """
        value_str = value_str.strip()
        
        # Handle boolean values
        if value_str.lower() == 'true':
            return True
        elif value_str.lower() == 'false':
            return False
        
        # Handle None
        if value_str.lower() == 'none':
            return None
            
        # Handle strings (remove quotes)
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]
        
        # Handle lists
        if value_str.startswith('[') and value_str.endswith(']'):
            try:
                # Try to parse as JSON first for complex structures
                import json
                return json.loads(value_str)
            except json.JSONDecodeError:
                try:
                    # Fallback to simple list parsing for basic cases
                    content = value_str[1:-1].strip()
                    if not content:
                        return []
                    
                    items = []
                    current_item = ""
                    bracket_count = 0
                    brace_count = 0
                    quote_char = None
                    
                    for char in content:
                        if quote_char:
                            current_item += char
                            if char == quote_char and (len(current_item) == 1 or current_item[-2] != '\\'):
                                quote_char = None
                        elif char in ['"', "'"]:
                            quote_char = char
                            current_item += char
                        elif char == '{':
                            brace_count += 1
                            current_item += char
                        elif char == '}':
                            brace_count -= 1
                            current_item += char
                        elif char == '[':
                            bracket_count += 1
                            current_item += char
                        elif char == ']':
                            bracket_count -= 1
                            current_item += char
                        elif char == ',' and bracket_count == 0 and brace_count == 0:
                            if current_item.strip():
                                # Try to parse each item as JSON first
                                item = current_item.strip()
                                try:
                                    items.append(json.loads(item))
                                except json.JSONDecodeError:
                                    # Fallback to string processing
                                    if (item.startswith('"') and item.endswith('"')) or \
                                       (item.startswith("'") and item.endswith("'")):
                                        items.append(item[1:-1])
                                    else:
                                        items.append(item)
                            current_item = ""
                        else:
                            current_item += char
                    
                    if current_item.strip():
                        # Try to parse the last item as JSON first
                        item = current_item.strip()
                        try:
                            items.append(json.loads(item))
                        except json.JSONDecodeError:
                            # Fallback to string processing
                            if (item.startswith('"') and item.endswith('"')) or \
                               (item.startswith("'") and item.endswith("'")):
                                items.append(item[1:-1])
                            else:
                                items.append(item)
                    
                    return items
                except:
                    return value_str
        
        # Handle JSON objects
        if value_str.startswith('{') and value_str.endswith('}'):
            try:
                import json
                return json.loads(value_str)
            except json.JSONDecodeError:
                return value_str
        
        # Handle numbers
        try:
            if '.' in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass
        
        # Return as string if all else fails
        return value_str
    
    def decompose_task(self, user_task: str) -> TaskPlan:
        """
        Decompose a complex task into subtasks with appropriate tags.
        
        Args:
            user_task: Natural language description of the user's task
            
        Returns:
            TaskPlan containing the decomposition result
        """
        # Build messages for the planner
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_TASK_DECOMPOSITION},
            {"role": "user", "content": f"User task: {user_task}"}
        ]
        
        try:
            # Get response from the model
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                extra_body=self.config.extra_body
            )
            
            raw_content = response.choices[0].message.content
            
        except Exception as e:
            print(f"Error calling LLM API for task decomposition: {e}")
            # Fallback to single task
            return TaskPlan(
                is_decomposed=False,
                subtasks=[SubTask(description=user_task, tag="general.task")]
            )
        
        # Parse the decomposition response
        return self._parse_decomposition_response(raw_content, user_task)
    
    def _parse_decomposition_response(self, content: str, original_task: str) -> TaskPlan:
        """
        Parse the decomposition response to extract subtasks and tags.
        
        Args:
            content: Raw response content from the model
            original_task: Original task description for fallback
            
        Returns:
            TaskPlan with parsed subtasks
        """
        try:
            # Extract analysis section
            analysis_match = re.search(r"<analysis>\s*(.*?)\s*</analysis>", content, re.DOTALL)
            analysis = analysis_match.group(1).strip() if analysis_match else ""
            
            # Extract plan section
            plan_match = re.search(r"<plan>\s*(.*?)\s*</plan>", content, re.DOTALL)
            plan_content = plan_match.group(1).strip() if plan_match else ""
            
            if not plan_content:
                # Fallback to single task
                return TaskPlan(
                    is_decomposed=False,
                    subtasks=[SubTask(description=original_task, tag="general.task")]
                )
            
            # Check if decomposition is needed
            if "no decomposition needed" in plan_content.lower() or "single task:" in plan_content.lower():
                # Extract single task tag
                tag_match = re.search(r"tag:\s*([^\n\r]+)", plan_content, re.IGNORECASE)
                tag = tag_match.group(1).strip() if tag_match else "general.task"
                
                return TaskPlan(
                    is_decomposed=False,
                    subtasks=[SubTask(description=original_task, tag=tag)]
                )
            
            # Parse decomposed subtasks
            subtasks = []
            
            # Look for subtask patterns like "- Subtask 1: description\n  Tag: tag"
            subtask_pattern = r"- Subtask \d+:\s*([^\n\r]+)\s*Tag:\s*([^\n\r]+)"
            matches = re.findall(subtask_pattern, plan_content, re.IGNORECASE)
            
            for description, tag in matches:
                subtasks.append(SubTask(
                    description=description.strip(),
                    tag=tag.strip()
                ))
            
            if not subtasks:
                # Fallback parsing - look for any line with "Tag:" 
                lines = plan_content.split('\n')
                current_description = ""
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('- ') or line.startswith('* '):
                        current_description = line[2:].strip()
                    elif line.lower().startswith('tag:') and current_description:
                        tag = line[4:].strip()
                        subtasks.append(SubTask(
                            description=current_description,
                            tag=tag
                        ))
                        current_description = ""
            
            if not subtasks:
                # Final fallback to single task
                return TaskPlan(
                    is_decomposed=False,
                    subtasks=[SubTask(description=original_task, tag="general.task")]
                )
            
            return TaskPlan(
                is_decomposed=len(subtasks) > 1,
                subtasks=subtasks
            )
            
        except Exception as e:
            print(f"Error parsing decomposition response: {e}")
            # Fallback to single task
            return TaskPlan(
                is_decomposed=False,
                subtasks=[SubTask(description=original_task, tag="general.task")]
            )

    def _parse_subtask_status(self, content: str) -> Dict[str, Any]:
        """
        Parse the subtask status from the planner response.
        
        Args:
            content: Raw response content from the model
            
        Returns:
            Dictionary containing subtask status information
        """
        try:
            # Extract subtask_status section
            status_match = re.search(r"<subtask_status>\s*(.*?)\s*</subtask_status>", content, re.DOTALL)
            if not status_match:
                return {}
            
            status_content = status_match.group(1).strip()
            
            # Parse individual fields
            status_dict = {}
            
            # Parse Status
            status_pattern = r"Status:\s*[\"']?([^\"'\n\r]+)[\"']?"
            status_match = re.search(status_pattern, status_content, re.IGNORECASE)
            if status_match:
                status_dict['status'] = status_match.group(1).strip()
            
            # Parse Confidence
            confidence_pattern = r"Confidence:\s*[\"']?([^\"'\n\r]+)[\"']?"
            confidence_match = re.search(confidence_pattern, status_content, re.IGNORECASE)
            if confidence_match:
                status_dict['confidence'] = confidence_match.group(1).strip()
            
            # Parse Reasoning
            reasoning_pattern = r"Reasoning:\s*([^\n\r]+)"
            reasoning_match = re.search(reasoning_pattern, status_content, re.IGNORECASE)
            if reasoning_match:
                status_dict['reasoning'] = reasoning_match.group(1).strip()
            
            # Parse Next_Action
            next_action_pattern = r"Next_Action:\s*[\"']?([^\"'\n\r]+)[\"']?"
            next_action_match = re.search(next_action_pattern, status_content, re.IGNORECASE)
            if next_action_match:
                status_dict['next_action'] = next_action_match.group(1).strip()
            
            return status_dict
            
        except Exception as e:
            print(f"Error parsing subtask status: {e}")
            return {}
    
    def set_current_task_plan(self, task_plan: TaskPlan) -> None:
        """
        Set the current task plan for tracking.
        
        Args:
            task_plan: The task plan to track
        """
        self._current_task_plan = task_plan
    
    def get_current_task_plan(self) -> Optional[TaskPlan]:
        """
        Get the current task plan.
        
        Returns:
            Current task plan or None if not set
        """
        return self._current_task_plan
