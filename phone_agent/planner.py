import os
import re
import json
import importlib.util
from openai import AsyncOpenAI
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
        self.client = AsyncOpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        
    async def plan_task(self, user_task: str) -> PlannerResponse:
        """
        Analyze user task and decide whether to use skills or atomic actions.
        
        Args:
            user_task: Natural language description of the user's task
            
        Returns:
            PlannerResponse containing the decision and execution plan
        """
        # print(f"SYSTEM_PROMPT_ROUTER:{SYSTEM_PROMPT_ROUTER}")
        # Build messages for the router
        # print(f"SYSTEM_PROMPT_ROUTER:{SYSTEM_PROMPT_ROUTER}")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_ROUTER},
            {"role": "user", "content": f"User task: {user_task}"}
        ]
        
        try:
            # Get response from the model
            response = await self.client.chat.completions.create(
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
