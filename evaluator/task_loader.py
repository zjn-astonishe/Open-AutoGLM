"""Task loader for Android World tasks."""

import sys
import os
from typing import Dict, List, Tuple, Any, Optional
import random

# Add android_world to path
android_world_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'android_world')
if android_world_path not in sys.path:
    sys.path.insert(0, android_world_path)

try:
    from android_world import registry
    from android_world.task_evals import task_eval
except ImportError as e:
    print(f"Warning: Could not import Android World modules: {e}")
    registry = None
    task_eval = None


class AndroidWorldTaskLoader:
    """Loads and manages Android World tasks for Open-AutoGLM testing."""
    
    def __init__(self):
        """Initialize the task loader."""
        self.task_registry = None
        self._load_android_world_tasks()
    
    def _load_android_world_tasks(self):
        """Load Android World task registry."""
        if registry is None:
            print("Warning: Android World registry not available")
            return
        
        try:
            self.task_registry = registry.TaskRegistry()
            print(f"Loaded Android World task registry with {len(self.get_available_families())} families")
        except Exception as e:
            print(f"Error loading Android World tasks: {e}")
            self.task_registry = None
    
    def get_available_families(self) -> List[str]:
        """Get list of available task families."""
        if not self.task_registry:
            return []
        
        families = [
            self.task_registry.ANDROID_WORLD_FAMILY,
            self.task_registry.MINIWOB_FAMILY_SUBSET,
            self.task_registry.ANDROID_FAMILY,
            self.task_registry.INFORMATION_RETRIEVAL_FAMILY,
        ]
        return families
    
    def get_tasks_in_family(self, family: str) -> Dict[str, Any]:
        """Get all tasks in a specific family."""
        if not self.task_registry:
            return {}
        
        try:
            return self.task_registry.get_registry(family)
        except Exception as e:
            print(f"Error getting tasks for family {family}: {e}")
            return {}
    
    def get_all_task_names(self, family: Optional[str] = None) -> List[str]:
        """Get list of all available task names."""
        if not self.task_registry:
            return []
        
        if family:
            tasks = self.get_tasks_in_family(family)
            return list(tasks.keys())
        
        all_tasks = []
        for family_name in self.get_available_families():
            tasks = self.get_tasks_in_family(family_name)
            all_tasks.extend(tasks.keys())
        
        return list(set(all_tasks))  # Remove duplicates
    
    def get_task(self, task_name: str, family: Optional[str] = None) -> Tuple[str, Any, Dict[str, Any]]:
        """
        Get a specific Android World task.
        
        Args:
            task_name: Name of the task to load
            family: Optional family name to search in
            
        Returns:
            Tuple of (task_goal_description, task_instance, task_metadata)
        """
        if not self.task_registry:
            raise ValueError("Android World task registry not available")
        
        # Find the task in the specified family or search all families
        task_class = None
        found_family = None
        
        if family:
            families_to_search = [family]
        else:
            families_to_search = self.get_available_families()
        
        for family_name in families_to_search:
            tasks = self.get_tasks_in_family(family_name)
            if task_name in tasks:
                task_class = tasks[task_name]
                found_family = family_name
                break
        
        if not task_class:
            available_tasks = self.get_all_task_names()
            raise ValueError(f"Task '{task_name}' not found. Available tasks: {available_tasks}")
        
        # Generate random parameters for the task
        try:
            params = task_class.generate_random_params()
            task_instance = task_class(params)
            
            # Create a natural language description of the task goal
            task_goal = self._create_task_description(task_name, task_instance, params)
            
            # Create metadata
            metadata = {
                'task_name': task_name,
                'family': found_family,
                'params': params,
                'complexity': getattr(task_instance, 'complexity', 1.0),
                'task_class': task_class.__name__
            }
            
            return task_goal, task_instance, metadata
            
        except Exception as e:
            raise ValueError(f"Error creating task instance for '{task_name}': {e}")
    
    def _create_task_description(self, task_name: str, task_instance: Any, params: Dict[str, Any]) -> str:
        """
        Create a natural language description of the task goal.
        
        Args:
            task_name: Name of the task
            task_instance: Instance of the task
            params: Task parameters
            
        Returns:
            Natural language description suitable for Open-AutoGLM
        """
        # Try to get the goal from the task instance
        if hasattr(task_instance, 'goal'):
            base_goal = str(task_instance.goal)
        elif hasattr(task_instance, 'description'):
            base_goal = str(task_instance.description)
        else:
            # Fallback: create description from task name and params
            base_goal = self._generate_fallback_description(task_name, params)
        
        # Enhance the description with parameter details if available
        enhanced_goal = self._enhance_goal_with_params(base_goal, params)
        
        return enhanced_goal
    
    def _generate_fallback_description(self, task_name: str, params: Dict[str, Any]) -> str:
        """Generate a fallback description when task doesn't provide one."""
        # Convert CamelCase task name to readable format
        readable_name = ''.join([' ' + c.lower() if c.isupper() else c for c in task_name]).strip()
        
        description = f"Complete the {readable_name} task"
        
        # Add parameter information if available
        if params:
            param_strs = []
            for key, value in params.items():
                if isinstance(value, str) and value:
                    param_strs.append(f"{key}: {value}")
                elif isinstance(value, (int, float)) and value != 0:
                    param_strs.append(f"{key}: {value}")
            
            if param_strs:
                description += f" with {', '.join(param_strs)}"
        
        return description
    
    def _enhance_goal_with_params(self, base_goal: str, params: Dict[str, Any]) -> str:
        """Enhance the goal description with parameter details."""
        if not params:
            return base_goal
        
        # Common parameter mappings
        param_enhancements = []
        
        for key, value in params.items():
            if key in ['name', 'contact_name', 'person_name'] and value:
                param_enhancements.append(f"name: {value}")
            elif key in ['phone', 'phone_number', 'number'] and value:
                param_enhancements.append(f"phone: {value}")
            elif key in ['email', 'email_address'] and value:
                param_enhancements.append(f"email: {value}")
            elif key in ['time', 'alarm_time'] and value:
                param_enhancements.append(f"time: {value}")
            elif key in ['message', 'text', 'content'] and value:
                param_enhancements.append(f"message: {value}")
        
        if param_enhancements:
            enhanced_goal = f"{base_goal} ({', '.join(param_enhancements)})"
        else:
            enhanced_goal = base_goal
        
        return enhanced_goal
    
    def create_task_suite(self,
                         family: str = None,
                         task_names: List[str] = None,
                         n_combinations: int = 1,
                         seed: int = 42) -> List[Tuple[str, Any, Dict[str, Any]]]:
        """
        Create a suite of tasks for testing.

        Args:
            family: Task family to use (default: android_world)
            task_names: Specific task names to include (if None, use all)
            n_combinations: Number of parameter combinations per task
            seed: Random seed for reproducibility

        Returns:
            List of (task_goal, task_instance, metadata) tuples
        """
        if not self.task_registry:
            raise ValueError("Android World task registry not available")
        
        # Set random seed for reproducibility
        random.seed(seed)
        
        # Use default family if none specified
        if family is None:
            family = "android_world"
        
        # Get task names to include
        if task_names is None:
            task_names = self.get_all_task_names(family)
        
        task_suite = []
        
        for task_name in task_names:
            # Find the task class
            task_class = None
            found_family = None
            
            families_to_search = [family] if family else self.get_available_families()
            
            for family_name in families_to_search:
                tasks = self.get_tasks_in_family(family_name)
                if task_name in tasks:
                    task_class = tasks[task_name]
                    found_family = family_name
                    break
            
            if not task_class:
                print(f"Warning: Task '{task_name}' not found, skipping...")
                continue
            
            # Generate multiple parameter combinations for this task
            for combination_id in range(n_combinations):
                try:
                    # Generate random parameters
                    params = task_class.generate_random_params()
                    task_instance = task_class(params)
                    
                    # Create natural language description
                    task_goal = self._create_task_description(task_name, task_instance, params)
                    
                    # Create metadata with combination info
                    metadata = {
                        'task_name': task_name,
                        'family': found_family,
                        'params': params,
                        'complexity': getattr(task_instance, 'complexity', 1.0),
                        'task_class': task_class.__name__,
                        'combination_id': combination_id,
                        'seed': seed
                    }
                    
                    task_suite.append((task_goal, task_instance, metadata))
                    
                except Exception as e:
                    print(f"Warning: Failed to create task instance for '{task_name}' "
                          f"combination {combination_id}: {e}")
                    continue
        
        print(f"Created task suite with {len(task_suite)} task instances from {len(task_names)} unique tasks")
        return task_suite
