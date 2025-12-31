# Copyright 2025 The android_world Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Open-AutoGLM Agent adapter for AndroidWorld."""

import logging
import sys
import os
from typing import Any

# Add the parent directory to sys.path to import Open-AutoGLM modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

from android_world.agents import base_agent
from android_world.env import interface
from android_world.env import json_action

# Import Open-AutoGLM components
from phone_agent.agent import PhoneAgent, AgentConfig
from phone_agent.planner import Planner
from phone_agent.skill_executor import SkillExecutor
from phone_agent.model import ModelConfig
from phone_agent.device_factory import DeviceType, set_device_type
from utils.config import load_config


class MSAgent(base_agent.EnvironmentInteractingAgent):
    """Adapter for Open-AutoGLM PhoneAgent to work with AndroidWorld."""

    def __init__(
        self,
        env: interface.AsyncEnv,
        model_config: Any = None,
        agent_config: Any = None,
        device_id: str = "5554",
        name: str = 'MSAgent',
    ):
        """Initialize the Open-AutoGLM agent adapter.
        
        Args:
            env: The AndroidWorld environment.
            model_config: Configuration for the AI model.
            agent_config: Configuration for the agent behavior.
            name: The agent name.
        """
        super().__init__(env, name)
        
        # Get device_id from AndroidWorld environment
        self.device_id = device_id
        
        # Load configuration following main.py pattern
        if model_config is None or agent_config is None:
            configs = load_config()
            
            # Create model config following main.py logic
            if model_config is None:
                if configs["MODEL"] == "OpenAI":
                    base_url = configs["OPENAI_API_BASE"]
                    model = configs["OPENAI_API_MODEL"]
                    apikey = configs["OPENAI_API_KEY"]
                else:
                    raise ValueError(f"Unsupported model type {configs['MODEL']}!")
                
                from phone_agent.model import ModelConfig
                model_config = ModelConfig(
                    base_url=base_url,
                    model_name=model,
                    api_key=apikey,
                    lang=configs["LANG"],
                )
            
            # Create agent config following main.py logic
            if agent_config is None:
                agent_config = AgentConfig(
                    max_steps=configs["MAX_ROUNDS"],
                    device_id=self.device_id,
                    verbose=not configs["QUIET"],
                    lang=configs["LANG"],
                    memory_dir=configs["MEMORY_DIR"],
                )
        
        # Ensure agent_config has the correct device_id
        if agent_config.device_id is None:
            agent_config.device_id = device_id
        
        # Initialize the PhoneAgent with configs
        self.phone_agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
        
        # Initialize Planner and SkillExecutor following main.py pattern
        self.planner = Planner(model_config=model_config)
        self.skill_executor = SkillExecutor(
            device_id=agent_config.device_id,
            confirmation_callback=None,
            takeover_callback=None,
        )
        
        # Track current goal for multi-step execution
        self._current_goal = None
        self._step_count = 0
        self._task_completed = False
        self._execution_mode = "auto"  # "auto", "planner", "direct"

    def reset(self, go_home: bool = False) -> None:
        """Reset the agent state."""
        super().reset(go_home)
        self.phone_agent.reset()
        self._current_goal = None
        self._step_count = 0

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        """Execute a single step towards the goal.
        
        Args:
            goal: The task goal description.
            
        Returns:
            AgentInteractionResult with step outcome.
        """
        self._step_count += 1
        logging.info('OpenAutoGLM Agent step %d: %s', self._step_count, goal)
        
        # Set current goal if this is the first step
        if self._current_goal is None:
            self._current_goal = goal
            
            try:
                # Use integrated planner and executor approach
                result_message = self._execute_with_planner_and_executor(goal)
                
                step_data = {
                    'goal': goal,
                    'step_count': self._step_count,
                    'agent_result': result_message,
                    'success': True,
                    'error': None,
                    'execution_mode': self._execution_mode,
                }
                
                # Task is completed after execution finishes
                self._task_completed = True
                return base_agent.AgentInteractionResult(True, step_data)
                
            except Exception as e:
                logging.error('Error in task execution: %s', e)
                step_data = {
                    'goal': goal,
                    'step_count': self._step_count,
                    'agent_result': None,
                    'success': False,
                    'error': str(e),
                    'execution_mode': self._execution_mode,
                }
                return base_agent.AgentInteractionResult(True, step_data)
        else:
            # Subsequent steps - task should already be completed
            step_data = {
                'goal': goal,
                'step_count': self._step_count,
                'agent_result': 'Task already completed',
                'success': True,
                'error': None,
                'execution_mode': self._execution_mode,
            }
            return base_agent.AgentInteractionResult(True, step_data)

    def _execute_with_planner_and_executor(self, goal: str) -> str:
        """Execute task using integrated planner and executor approach.
        
        This method follows the main.py pattern of using planner to decide
        between skill-based execution and direct PhoneAgent execution.
        
        Args:
            goal: The task goal description.
            
        Returns:
            Result message from task execution.
        """
        logging.info('Starting task planning phase')
        
        # Step 1: Use planner to analyze the task
        try:
            plan = self.planner.plan_task(goal)
            print('Planner decision: ', plan.decision)
            
            if plan.decision == "use_skill" and plan.skill_name:
                # Step 2a: Execute using skill-based approach
                logging.info('Executing with skill: %s, params: %s', 
                           plan.skill_name, plan.skill_params)
                self._execution_mode = "planner"
                
                # Get skill actions from planner
                actions = self.planner.execute_skill(plan.skill_name, plan.skill_params)
                
                if actions:
                    # Execute actions using SkillExecutor
                    result_message = self.skill_executor.run(actions)
                    logging.info('Skill execution completed: %s', result_message)
                    return result_message
                else:
                    # Fallback to direct execution if skill fails
                    logging.warning('Skill execution failed, falling back to direct execution')
                    self._execution_mode = "direct"
                    return self.phone_agent.run(goal)
                    
            else:
                # Step 2b: Execute using direct PhoneAgent approach
                logging.info('Executing with direct PhoneAgent approach')
                self._execution_mode = "direct"
                return self.phone_agent.run(goal)
                
        except Exception as e:
            # Fallback to direct execution if planning fails
            logging.error('Planning failed: %s, falling back to direct execution', e)
            self._execution_mode = "direct"
            return self.phone_agent.run(goal)