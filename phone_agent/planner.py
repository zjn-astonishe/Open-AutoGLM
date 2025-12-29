import os
import re
import json
import importlib.util
from openai import OpenAI
from phone_agent.model.client import ModelConfig
from typing import Dict, Any, List, Optional, Tuple
from phone_agent.config.prompts_en import SYSTEM_PROMPT_ROUTER


class PlannerResponse:
    """Response from the planner containing decision and execution plan."""
    
    def __init__(self, decision: str, execution: str = "", skill_name: str = "", 
                 skill_params: Dict[str, Any] = None, raw_content: str = ""):
        self.decision = decision  # "use_skill" or "use_atomic_actions"
        self.execution = execution  # Raw execution string
        self.skill_name = skill_name  # Name of the skill to use
        self.skill_params = skill_params or {}  # Parameters for the skill
        self.raw_content = raw_content  # Raw LLM response


class Planner:
    
    def __init__(self, model_config: ModelConfig | None = None):
        self.config = model_config or ModelConfig()
        self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        
    def plan_task(self, user_task: str) -> PlannerResponse:
        """
        Analyze user task and decide whether to use skills or atomic actions.
        
        Args:
            user_task: Natural language description of the user's task
            
        Returns:
            PlannerResponse containing the decision and execution plan
        """
        # Build messages for the router
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_ROUTER},
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
            print(f"Error calling LLM API: {e}")
            raw_content = ""
        
        # Parse the response
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
            raw_content=raw_content
        )
    
    def execute_skill(self, skill_name: str, skill_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute a skill with given parameters.
        
        Args:
            skill_name: Name of the skill to execute
            skill_params: Parameters to pass to the skill
            
        Returns:
            List of action dictionaries from the skill execution
        """
        try:
            # Load the skill module dynamically
            skill_path = self._get_skill_path(skill_name)
            if not skill_path or not os.path.exists(skill_path):
                raise FileNotFoundError(f"Skill file not found: {skill_name}")
                
            # Import the skill module
            spec = importlib.util.spec_from_file_location(skill_name, skill_path)
            skill_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(skill_module)
            
            # Get the skill function
            skill_function = getattr(skill_module, skill_name)
            
            # Execute the skill with parameters
            actions = skill_function(**skill_params)
            
            return actions
            
        except Exception as e:
            print(f"Error executing skill {skill_name}: {e}")
            return []
    
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
                # Simple list parsing for common cases
                content = value_str[1:-1].strip()
                if not content:
                    return []
                
                items = []
                for item in content.split(','):
                    item = item.strip()
                    if (item.startswith('"') and item.endswith('"')) or \
                       (item.startswith("'") and item.endswith("'")):
                        items.append(item[1:-1])
                    else:
                        items.append(item)
                return items
            except:
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
    
    def _get_skill_path(self, skill_name: str) -> Optional[str]:
        """
        Get the file path for a skill.
        
        Args:
            skill_name: Name of the skill
            
        Returns:
            Path to the skill file or None if not found
        """
        # Get the project root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        # Construct skill file path
        skill_path = os.path.join(project_root, "code_generator", "skills", f"{skill_name}.py")
        
        return skill_path if os.path.exists(skill_path) else None
    
    def get_available_skills(self) -> Dict[str, Any]:
        """
        Get information about available skills from the skill library.
        
        Returns:
            Dictionary containing skill information
        """
        try:
            # Get skill library path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            skill_library_path = os.path.join(project_root, "code_generator", "skills", "skill_library.json")
            
            if not os.path.exists(skill_library_path):
                return {}
            
            with open(skill_library_path, 'r', encoding='utf-8') as f:
                library_data = json.load(f)
            
            return library_data.get("skills", {})
            
        except Exception as e:
            print(f"Error loading skill library: {e}")
            return {}
    
