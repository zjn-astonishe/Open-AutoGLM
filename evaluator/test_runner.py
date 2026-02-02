"""Test runner for Android World tasks using Open-AutoGLM."""

import os
import time
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import traceback

from .task_loader import AndroidWorldTaskLoader
from .evaluator import AndroidWorldEvaluator
from .result_reporter import AndroidWorldResultReporter

# Import Open-AutoGLM components
from phone_agent.agent import PhoneAgent, AgentConfig
from phone_agent.device_factory import get_device_factory, DeviceFactory

from phone_agent.model import ModelConfig
from utils.config import load_config
from utils.util import print_with_color

from phone_agent.portal import (
    PORTAL_PACKAGE_NAME,
    toggle_overlay,
    download_portal_apk,
    download_versioned_portal_apk,
    enable_portal_accessibility,
    get_compatible_portal_version,
)

async def _setup_portal(path: str | None, device_factory: DeviceFactory, debug: bool, latest: bool = False, specific_version: str | None = None):
    """Internal async function to install and enable the DroidRun Portal on a device."""
    try:
        # Get device 
        from async_adbutils import adb
        devices = await adb.list()
        if not devices:
            print_with_color("No devices found!", "red")
            return
        
        device = devices[0].serial
        print_with_color(f"Using device: {devices}", "blue")

        device_obj = await adb.device(device)
        if not device_obj:
            print_with_color("Error: Could not connect to device!", "red")
            return
        
        # Check for local portal.apk first
        local_apk_path = "portal.apk"
        if not path and os.path.exists(local_apk_path):
            print_with_color(f"Found local Portal APK: {local_apk_path}", "green")
            path = local_apk_path

        if path:
            print_with_color(f"Using provided APK: {path}", "blue")
            from contextlib import nullcontext
            apk_context = nullcontext(path)
        elif specific_version:
            __version__ = specific_version.lstrip("v")
            __version__ = f"v{__version__}"
            download_base = "https://github.com/droidrun/droidrun-portal/releases/download"
            apk_context = download_versioned_portal_apk(__version__, download_base, debug)
        elif latest:
            print_with_color("Downloading latest Portal APK...", "blue")
            apk_context = download_portal_apk(debug)
        else:
            from importlib.metadata import version, PackageNotFoundError
            try:
                # Try to get version from installed package
                __version__ = version("phone-agent")
            except PackageNotFoundError:
                # If package not installed via pip, use a default version
                __version__ = "0.1.0"
                print_with_color(f"Package not installed, using default version: {__version__}", "yellow")
            
            portal_version, download_base, mapping_fetched = get_compatible_portal_version(__version__, debug)

            if portal_version:
                apk_context = download_versioned_portal_apk(portal_version, download_base, debug)
            else:
                if not mapping_fetched:
                    print_with_color("Could not fetch version mapping, falling back to latest...", "yellow")
                apk_context = download_portal_apk(debug)

        with apk_context as apk_path:
            if not os.path.exists(apk_path):
                print_with_color(f"Error: APK file not found at {apk_path}", "red")
                return

            print_with_color(f"Step 1/2: Installing APK: {apk_path}", "blue")
            try:
                await device_obj.install(
                    apk_path, uninstall=True, flags=["-g"], silent=not debug
                )
            except Exception as e:
                print_with_color(f"Installation failed: {e}", "red")
                return

            print_with_color("Installation successful!", "green")

            print_with_color("Step 2/2: Enabling accessibility service", "blue")

            try:
                await enable_portal_accessibility(device_factory)

                print_with_color("Accessibility service enabled successfully!", "green")
                print_with_color(
                    "\nSetup complete! The DroidRun Portal is now installed and ready to use.", 
                    "green"
                )
                await asyncio.sleep(1.0)
            except Exception as e:
                print_with_color(
                    f"Could not automatically enable accessibility service: {e}",
                    "yellow"
                )
                print_with_color(
                    "Opening accessibility settings for manual configuration...",
                    "yellow"
                )

                await device_factory.shell(
                    "am start -a android.settings.ACCESSIBILITY_SETTINGS"
                )

                print_with_color(
                    "\nPlease complete the following steps on your device:",
                    "yellow"
                )
                print_with_color(
                    f"1. Find {PORTAL_PACKAGE_NAME} in the accessibility services list"
                )
                print_with_color("2. Tap on the service name")
                print_with_color(
                    "3. Toggle the switch to ON to enable the service"
                )
                print_with_color("4. Accept any permission dialogs that appear")

                print_with_color(
                    "\nAPK installation complete![/] Please manually enable the accessibility service using the steps above.",
                    "green"
                )
        
        # Return to system home after setup
        print_with_color("\nReturning to system home...", "blue")
        await device_factory.shell("input keyevent KEYCODE_HOME")
        await asyncio.sleep(1.0)
        print_with_color("✓ Returned to home screen", "green")

    except Exception as e:
        print_with_color(f"Error: {e}", "red")

        if debug:
            import traceback

            traceback.print_exc()


class AndroidWorldTestRunner:
    """Runs Android World tests using Open-AutoGLM agent."""
    
    def __init__(self, 
                 agent: Optional[PhoneAgent] = None,
                 model_config: Optional[ModelConfig] = None,
                 agent_config: Optional[AgentConfig] = None,
                 device_id: str = "5554",
                 adb_path: Optional[str] = None,
                 timeout_per_task: int = 300,
                 verbose: bool = True):
        """
        Initialize the test runner.
        
        Args:
            agent: Pre-initialized PhoneAgent instance (if provided, model_config and agent_config are ignored)
            model_config: Model configuration for Open-AutoGLM
            agent_config: Agent configuration for Open-AutoGLM
            device_id: Android device ID
            adb_path: Path to adb executable
            timeout_per_task: Default timeout per task in seconds
            verbose: Whether to print verbose output
        """
        self.device_id = device_id
        self.adb_path = adb_path
        self.timeout_per_task = timeout_per_task
        self.verbose = verbose
        
        # Use provided agent or create new one
        if agent is not None:
            self.agent = agent
            self.model_config = agent.model_config
            self.agent_config = agent.agent_config
        else:
            # Load configurations if not provided
            if model_config is None or agent_config is None:
                configs = load_config()
                
                if model_config is None:
                    if configs["MODEL"] == "OpenAI":
                        base_url = configs["OPENAI_API_BASE"]
                        model = configs["OPENAI_API_MODEL"]
                        apikey = configs["OPENAI_API_KEY"]
                    else:
                        raise ValueError(f"Unsupported model type {configs['MODEL']}!")
                    
                    model_config = ModelConfig(
                        base_url=base_url,
                        model_name=model,
                        api_key=apikey,
                        lang=configs["LANG"],
                    )
                
                if agent_config is None:
                    agent_config = AgentConfig(
                        max_steps=configs["MAX_ROUNDS"],
                        device_id=device_id,
                        verbose=verbose,
                        lang=configs["LANG"],
                        memory_dir=configs["MEMORY_DIR"],
                    )
            
            # Initialize components
            self.model_config = model_config
            self.agent_config = agent_config
            
            # Initialize agent
            self.agent = PhoneAgent(
                model_config=model_config,
                agent_config=agent_config,
            )
        
        # Initialize other components
        self.task_loader = AndroidWorldTaskLoader()
        self.evaluator = AndroidWorldEvaluator(device_id=device_id, adb_path=adb_path)
        self.result_reporter = AndroidWorldResultReporter()
        
        if self.verbose:
            print(f"Android World Test Runner initialized for device {device_id}")
    
    async def run_single_task(self, 
                       task_name: str, 
                       family: Optional[str] = None,
                       timeout: int = 300) -> Dict[str, Any]:
        """
        Run a single Android World task.
        
        Args:
            task_name: Name of the task to run
            family: Task family (optional)
            timeout: Timeout in seconds
            
        Returns:
            Task execution and evaluation result
        """
        print(f"\n🎯 Running task: {task_name}")
        
        start_time = time.time()
        
        try:
            # Load the task
            task_goal, task_instance, metadata = self.task_loader.get_task(task_name, family)
            print(f"📋 Task goal: {task_goal}")
            print(f"📊 Task metadata: {metadata}")
            
            # Initialize the task in AndroidWorld environment BEFORE agent execution
            print("🔧 Initializing AndroidWorld task...")
            if self.evaluator.env and task_instance:
                try:
                    task_instance.initialize_task(self.evaluator.env)
                    print("✅ AndroidWorld task initialized successfully")
                except Exception as e:
                    print(f"⚠️ Warning: Failed to initialize AndroidWorld task: {e}")
            
            # Re-check and setup Portal AFTER Android World environment initialization
            # This ensures Portal is properly configured after any Android World setup
            print("\n🔧 Verifying Portal after Android World initialization...")
            device_factory = await get_device_factory()
            
            await _setup_portal(
                path=None, 
                device_factory=device_factory,
                debug=False
            )
            # await toggle_overlay(device_factory, visible=False)

            # Reset agent state
            self.agent.reset()
            
            # Run the agent on the task
            print("🤖 Starting agent execution...")
            agent_start_time = time.time()
            
            try:
                agent_result = await self.agent.run(task_goal)
                agent_execution_time = time.time() - agent_start_time
                
                # Ensure agent_result has required fields
                if not isinstance(agent_result, dict):
                    agent_result = {
                        'finished': True,
                        'actions': [],
                        'execution_time': agent_execution_time,
                        'result_message': str(agent_result) if agent_result else "Task completed"
                    }
                else:
                    agent_result['execution_time'] = agent_execution_time
                
                print(f"✅ Agent execution completed in {agent_execution_time:.2f}s")
                print(f"📝 Agent result: {agent_result.get('result_message', 'Task completed')}")
                
            except Exception as e:
                agent_execution_time = time.time() - agent_start_time
                print(f"❌ Agent execution failed: {e}")
                agent_result = {
                    'finished': False,
                    'actions': [],
                    'execution_time': agent_execution_time,
                    'error': str(e),
                    'result_message': f"Agent execution failed: {e}"
                }
            
            # Evaluate the task (evaluator will NOT re-initialize the task)
            print("📏 Evaluating task completion...")
            evaluation_result = self.evaluator.evaluate_task(task_instance, agent_result, metadata)
            
            # Combine results
            total_time = time.time() - start_time
            
            result = {
                'task_name': task_name,
                'family': metadata.get('family', 'unknown'),
                'task_goal': task_goal,
                'metadata': metadata,
                'agent_result': agent_result,
                'evaluation': evaluation_result,
                'total_time': total_time,
                'timestamp': datetime.now().isoformat(),
                'success': evaluation_result['success']
            }
            
            # Print result summary
            status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
            print(f"{status} - {task_name}")
            print(f"   Score: {evaluation_result['evaluation_score']:.2f}")
            print(f"   Actions: {evaluation_result['num_actions']}")
            print(f"   Time: {total_time:.2f}s")
            
            if evaluation_result.get('error'):
                print(f"   Error: {evaluation_result['error']}")
            
            return result
            
        except Exception as e:
            total_time = time.time() - start_time
            error_msg = f"Task execution failed: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            
            return {
                'task_name': task_name,
                'family': family or 'unknown',
                'task_goal': f"Failed to load task {task_name}",
                'metadata': {'task_name': task_name, 'family': family},
                'agent_result': {'finished': False, 'actions': [], 'execution_time': 0, 'error': error_msg},
                'evaluation': {'success': False, 'evaluation_score': 0.0, 'error': error_msg},
                'total_time': total_time,
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'error': error_msg
            }
    
    async def run_task_list(self, 
                     task_names: List[str], 
                     family: Optional[str] = None,
                     timeout_per_task: int = 300) -> Dict[str, Any]:
        """
        Run a list of tasks.
        
        Args:
            task_names: List of task names to run
            family: Task family (optional)
            timeout_per_task: Timeout per task in seconds
            
        Returns:
            Aggregated results for all tasks
        """
        print(f"\n🚀 Running {len(task_names)} tasks from family: {family or 'all'}")
        
        results = []
        start_time = time.time()
        
        for i, task_name in enumerate(task_names, 1):
            print(f"\n--- Task {i}/{len(task_names)} ---")
            
            try:
                result = await self.run_single_task(task_name, family, timeout_per_task)
                results.append(result)
                
            except KeyboardInterrupt:
                print("\n⚠️ Test run interrupted by user")
                break
            except Exception as e:
                print(f"❌ Unexpected error running task {task_name}: {e}")
                # Add error result
                results.append({
                    'task_name': task_name,
                    'family': family or 'unknown',
                    'success': False,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        total_time = time.time() - start_time
        
        # Generate summary report
        summary = self._generate_summary(results, total_time)
        
        return {
            'summary': summary,
            'results': results,
            'total_time': total_time,
            'timestamp': datetime.now().isoformat()
        }
    
    def run_benchmark_suite(self, 
                           family: str = "android_world",
                           task_names: Optional[List[str]] = None,
                           n_combinations: int = 1,
                           timeout_per_task: int = 300) -> Dict[str, Any]:
        """
        Run the full Android World benchmark suite.
        
        Args:
            family: Task family to run
            task_names: Specific tasks to run (if None, run all in family)
            n_combinations: Number of parameter combinations per task
            timeout_per_task: Timeout per task in seconds
            
        Returns:
            Complete benchmark results
        """
        print(f"\n🏆 Running Android World Benchmark Suite")
        print(f"   Family: {family}")
        print(f"   Tasks: {len(task_names) if task_names else 'all'}")
        print(f"   Combinations per task: {n_combinations}")
        
        start_time = time.time()
        
        try:
            # Create task suite
            task_suite = self.task_loader.create_task_suite(
                family=family,
                task_names=task_names,
                n_combinations=n_combinations
            )
            
            print(f"📋 Created test suite with {len(task_suite)} task instances")
            
            results = []
            
            for i, (task_goal, task_instance, metadata) in enumerate(task_suite, 1):
                task_name = metadata['task_name']
                combination_id = metadata.get('combination_id', 0)
                
                print(f"\n--- Task {i}/{len(task_suite)}: {task_name} (combination {combination_id}) ---")
                
                try:
                    # Initialize the task in AndroidWorld environment BEFORE agent execution
                    print("🔧 Initializing AndroidWorld task...")
                    if self.evaluator.env and task_instance:
                        try:
                            task_instance.initialize_task(self.evaluator.env)
                            print("✅ AndroidWorld task initialized successfully")
                        except Exception as e:
                            print(f"⚠️ Warning: Failed to initialize AndroidWorld task: {e}")
                    
                    # Reset agent
                    self.agent.reset()
                    
                    # Run agent
                    print(f"🎯 Goal: {task_goal}")
                    agent_start_time = time.time()
                    
                    try:
                        agent_result = self.agent.run(task_goal)
                        agent_execution_time = time.time() - agent_start_time
                        
                        if not isinstance(agent_result, dict):
                            agent_result = {
                                'finished': True,
                                'actions': [],
                                'execution_time': agent_execution_time,
                                'result_message': str(agent_result)
                            }
                        else:
                            agent_result['execution_time'] = agent_execution_time
                            
                    except Exception as e:
                        agent_execution_time = time.time() - agent_start_time
                        agent_result = {
                            'finished': False,
                            'actions': [],
                            'execution_time': agent_execution_time,
                            'error': str(e)
                        }
                    
                    # Evaluate
                    evaluation_result = self.evaluator.evaluate_task(task_instance, agent_result, metadata)
                    
                    # Calculate total time for this task
                    task_total_time = time.time() - agent_start_time
                    
                    result = {
                        'task_name': task_name,
                        'combination_id': combination_id,
                        'family': metadata.get('family'),
                        'task_goal': task_goal,
                        'metadata': metadata,
                        'agent_result': agent_result,
                        'evaluation': evaluation_result,
                        'total_time': task_total_time,
                        'timestamp': datetime.now().isoformat(),
                        'success': evaluation_result['success']
                    }
                    
                    results.append(result)
                    
                    # Print progress
                    status = "✅" if result['success'] else "❌"
                    print(f"{status} {task_name} - Score: {evaluation_result['evaluation_score']:.2f}")
                    
                except KeyboardInterrupt:
                    print("\n⚠️ Benchmark interrupted by user")
                    break
                except Exception as e:
                    print(f"❌ Error in task {task_name}: {e}")
                    results.append({
                        'task_name': task_name,
                        'combination_id': combination_id,
                        'success': False,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
            
            total_time = time.time() - start_time
            
            # Generate comprehensive report
            benchmark_report = self.result_reporter.generate_benchmark_report(results, total_time)
            
            return benchmark_report
            
        except Exception as e:
            print(f"❌ Benchmark suite failed: {e}")
            return {
                'error': str(e),
                'total_time': time.time() - start_time,
                'timestamp': datetime.now().isoformat()
            }
    
    def _generate_summary(self, results: List[Dict[str, Any]], total_time: float) -> Dict[str, Any]:
        """Generate summary statistics for a set of results."""
        total_tasks = len(results)
        successful_tasks = sum(1 for r in results if r.get('success', False))
        failed_tasks = total_tasks - successful_tasks
        
        success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.0
        
        return {
            'total_tasks': total_tasks,
            'successful_tasks': successful_tasks,
            'failed_tasks': failed_tasks,
            'success_rate': success_rate,
            'total_time': total_time,
            'average_time_per_task': total_time / total_tasks if total_tasks > 0 else 0.0
        }
    
    def list_available_tasks(self, family: Optional[str] = None) -> List[str]:
        """List all available tasks."""
        return self.task_loader.get_all_task_names(family)
    
    def list_available_families(self) -> List[str]:
        """List all available task families."""
        return self.task_loader.get_available_families()
    
    def cleanup(self):
        """Cleanup resources."""
        if self.evaluator:
            self.evaluator.cleanup()
