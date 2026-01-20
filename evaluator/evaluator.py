"""Evaluator for Android World tasks using Open-AutoGLM results."""

import sys
import os
from typing import Any, Dict, List, Optional, Tuple
import time

# Add android_world to path
android_world_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'android_world')
if android_world_path not in sys.path:
    sys.path.insert(0, android_world_path)

try:
    from android_world.env import env_launcher
    from android_world.env import interface
except ImportError as e:
    print(f"Warning: Could not import Android World environment modules: {e}")
    env_launcher = None
    interface = None


class AndroidWorldEvaluator:
    """Evaluates Open-AutoGLM task execution using Android World evaluation logic."""
    
    def __init__(self, device_id: str = "5554", adb_path: Optional[str] = None):
        """
        Initialize the evaluator.
        
        Args:
            device_id: Android device ID (console port)
            adb_path: Path to adb executable
        """
        self.device_id = device_id
        # Use default ADB path if none provided
        if env_launcher and hasattr(env_launcher, 'android_world_controller'):
            from android_world.env import android_world_controller
            self.adb_path = adb_path or android_world_controller.DEFAULT_ADB_PATH
        else:
            self.adb_path = adb_path or "adb"  # fallback to system adb
        self.env = None
        self._setup_environment()
    
    def _setup_environment(self):
        """Setup Android World environment for evaluation."""
        if env_launcher is None:
            print("Warning: Android World environment not available")
            return
        
        try:
            # Setup environment similar to Android World's approach
            console_port = int(self.device_id) if self.device_id.isdigit() else 5554
            
            self.env = env_launcher.load_and_setup_env(
                console_port=console_port,
                emulator_setup=False,  # Don't perform setup during evaluation
                adb_path=self.adb_path,
            )
            print(f"Android World environment initialized for device {self.device_id}")
            
        except Exception as e:
            print(f"Warning: Failed to setup Android World environment: {e}")
            self.env = None
    
    def evaluate_task(self, 
                     task_instance: Any, 
                     agent_result: Dict[str, Any],
                     metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a task using Android World's evaluation logic.
        
        Args:
            task_instance: Android World task instance
            agent_result: Result from Open-AutoGLM agent execution
            metadata: Task metadata
            
        Returns:
            Evaluation result dictionary
        """
        evaluation_result = {
            'task_name': metadata.get('task_name', 'unknown'),
            'success': False,
            'evaluation_score': 0.0,
            'error': None,
            'evaluation_details': {},
            'execution_time': agent_result.get('execution_time', 0),
            'num_actions': len(agent_result.get('actions', [])),
            'agent_finished': agent_result.get('finished', False)
        }
        
        if not self.env:
            evaluation_result['error'] = "⚠️ Android World environment not available"
            return evaluation_result
        
        if not task_instance:
            evaluation_result['error'] = "Task instance not available"
            return evaluation_result
        
        try:
            # DON'T re-initialize the task - this would reset the environment state
            # The task should already be initialized and the agent has completed its actions
            # We just need to evaluate the current state
            
            # Wait a moment for the environment to stabilize after agent actions
            time.sleep(5)
            
            # Use Android World's evaluation logic on the current state
            success_score = task_instance.is_successful(self.env)
            
            # Android World returns different types of success indicators
            if isinstance(success_score, bool):
                evaluation_result['success'] = success_score
                evaluation_result['evaluation_score'] = 1.0 if success_score else 0.0
            elif isinstance(success_score, (int, float)):
                evaluation_result['success'] = success_score > 0
                evaluation_result['evaluation_score'] = float(success_score)
            else:
                # Handle other return types
                evaluation_result['success'] = bool(success_score)
                evaluation_result['evaluation_score'] = 1.0 if success_score else 0.0
            
            # Get additional evaluation details if available
            evaluation_details = self._get_evaluation_details(task_instance, self.env)
            evaluation_result['evaluation_details'] = evaluation_details
            
            print(f"📏 Evaluation result for {metadata.get('task_name', 'unknown')}: "
                  f"Success={evaluation_result['success']}, Score={evaluation_result['evaluation_score']}")
            
        except Exception as e:
            evaluation_result['error'] = f"Evaluation failed: {str(e)}"
            print(f"Error evaluating task {metadata.get('task_name', 'unknown')}: {e}")
            import traceback
            traceback.print_exc()
        
        return evaluation_result
    
    def _get_evaluation_details(self, task_instance: Any, env: Any) -> Dict[str, Any]:
        """
        Get additional evaluation details from the task instance.
        
        Args:
            task_instance: Android World task instance
            env: Android World environment
            
        Returns:
            Dictionary with evaluation details
        """
        details = {}
        
        try:
            # Try to get additional information from the task
            if hasattr(task_instance, 'get_evaluation_details'):
                details.update(task_instance.get_evaluation_details(env))
            
            # Get current screen state
            if hasattr(env, 'get_state'):
                state = env.get_state()
                details['final_screen_elements'] = len(state.ui_elements) if hasattr(state, 'ui_elements') else 0
            
            # Get task-specific metrics if available
            if hasattr(task_instance, 'complexity'):
                details['task_complexity'] = task_instance.complexity
            
            if hasattr(task_instance, 'goal'):
                details['task_goal'] = str(task_instance.goal)
                
        except Exception as e:
            details['details_error'] = str(e)
        
        return details
    
    def evaluate_task_suite(self, 
                           task_results: List[Tuple[Any, Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Evaluate a suite of tasks.
        
        Args:
            task_results: List of (task_instance, agent_result, metadata) tuples
            
        Returns:
            Aggregated evaluation results
        """
        suite_results = {
            'total_tasks': len(task_results),
            'successful_tasks': 0,
            'failed_tasks': 0,
            'error_tasks': 0,
            'success_rate': 0.0,
            'average_score': 0.0,
            'total_actions': 0,
            'total_execution_time': 0.0,
            'task_results': [],
            'summary_by_family': {},
            'summary_by_complexity': {}
        }
        
        total_score = 0.0
        
        for task_instance, agent_result, metadata in task_results:
            # Evaluate individual task
            eval_result = self.evaluate_task(task_instance, agent_result, metadata)
            suite_results['task_results'].append(eval_result)
            
            # Update aggregated statistics
            if eval_result['error']:
                suite_results['error_tasks'] += 1
            elif eval_result['success']:
                suite_results['successful_tasks'] += 1
            else:
                suite_results['failed_tasks'] += 1
            
            total_score += eval_result['evaluation_score']
            suite_results['total_actions'] += eval_result['num_actions']
            suite_results['total_execution_time'] += eval_result['execution_time']
            
            # Update family-based statistics
            family = metadata.get('family', 'unknown')
            if family not in suite_results['summary_by_family']:
                suite_results['summary_by_family'][family] = {
                    'total': 0, 'successful': 0, 'failed': 0, 'error': 0
                }
            
            family_stats = suite_results['summary_by_family'][family]
            family_stats['total'] += 1
            if eval_result['error']:
                family_stats['error'] += 1
            elif eval_result['success']:
                family_stats['successful'] += 1
            else:
                family_stats['failed'] += 1
            
            # Update complexity-based statistics
            complexity = metadata.get('complexity', 1.0)
            complexity_bucket = self._get_complexity_bucket(complexity)
            if complexity_bucket not in suite_results['summary_by_complexity']:
                suite_results['summary_by_complexity'][complexity_bucket] = {
                    'total': 0, 'successful': 0, 'failed': 0, 'error': 0
                }
            
            complexity_stats = suite_results['summary_by_complexity'][complexity_bucket]
            complexity_stats['total'] += 1
            if eval_result['error']:
                complexity_stats['error'] += 1
            elif eval_result['success']:
                complexity_stats['successful'] += 1
            else:
                complexity_stats['failed'] += 1
        
        # Calculate final statistics
        if suite_results['total_tasks'] > 0:
            suite_results['success_rate'] = suite_results['successful_tasks'] / suite_results['total_tasks']
            suite_results['average_score'] = total_score / suite_results['total_tasks']
        
        # Calculate success rates for each family
        for family_stats in suite_results['summary_by_family'].values():
            if family_stats['total'] > 0:
                family_stats['success_rate'] = family_stats['successful'] / family_stats['total']
        
        # Calculate success rates for each complexity bucket
        for complexity_stats in suite_results['summary_by_complexity'].values():
            if complexity_stats['total'] > 0:
                complexity_stats['success_rate'] = complexity_stats['successful'] / complexity_stats['total']
        
        return suite_results
    
    def _get_complexity_bucket(self, complexity: float) -> str:
        """
        Get complexity bucket for a given complexity score.
        
        Args:
            complexity: Task complexity score
            
        Returns:
            Complexity bucket string
        """
        if complexity <= 1.0:
            return 'low'
        elif complexity <= 2.0:
            return 'medium'
        else:
            return 'high'
    
    def cleanup(self):
        """Clean up resources."""
        if self.env:
            try:
                # Close the environment if it has a close method
                if hasattr(self.env, 'close'):
                    self.env.close()
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")
            finally:
                self.env = None
