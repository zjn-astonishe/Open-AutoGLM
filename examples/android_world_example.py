#!/usr/bin/env python3
"""
Android World Integration Example

This script demonstrates how to use the Android World integration
with Open-AutoGLM to run benchmark tests.
"""

import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluator import (
    AndroidWorldTaskLoader,
    AndroidWorldEvaluator, 
    AndroidWorldTestRunner,
    AndroidWorldResultReporter
)
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig
from utils.config import load_config


def main():
    """Run Android World integration example."""
    print("🤖 Android World Integration Example")
    print("=" * 50)
    
    # Load configuration
    configs = load_config()
    
    # Create model and agent configurations
    model_config = ModelConfig(
        base_url=configs.get("OPENAI_API_BASE", "http://localhost:8001/v1"),
        model_name=configs.get("OPENAI_API_MODEL", "autoglm-phone-9b"),
        api_key=configs.get("OPENAI_API_KEY", "EMPTY"),
        lang=configs.get("LANG", "en"),
    )
    
    agent_config = AgentConfig(
        max_steps=configs.get("MAX_ROUNDS", 50),
        device_id=None,  # Use default device
        verbose=True,
        lang=configs.get("LANG", "en"),
        memory_dir=configs.get("MEMORY_DIR", "./output/memory"),
    )
    
    # Create agent
    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
    )
    
    print(f"✅ Agent initialized: {model_config.model_name}")
    
    # Example 1: List available tasks
    print("\n📋 Example 1: List Available Tasks")
    print("-" * 30)
    
    try:
        task_loader = AndroidWorldTaskLoader()
        families = task_loader.get_available_families()
        
        print(f"Available task families: {families}")
        
        # Show tasks from android_world family
        if "android_world" in families:
            tasks = task_loader.get_all_task_names("android_world")
            print(f"Android World tasks: {len(tasks)}")
            print(f"First 5 tasks: {tasks[:5]}")
        
    except Exception as e:
        print(f"❌ Error listing tasks: {e}")
        return
    
    # Example 2: Load and inspect a single task
    print("\n🎯 Example 2: Load Single Task")
    print("-" * 30)
    
    try:
        # Load a simple task
        task_name = "ContactsAddContact"  # A common Android World task
        task_instance = task_loader.get_task(task_name, family="android_world")
        
        if task_instance:
            print(f"✅ Loaded task: {task_name}")
            print(f"   Goal: {task_instance['goal']}")
            print(f"   Complexity: {task_instance.get('complexity', 'N/A')}")
        else:
            print(f"❌ Failed to load task: {task_name}")
            
    except Exception as e:
        print(f"❌ Error loading task: {e}")
    
    # Example 3: Run a simple test (commented out to avoid actual execution)
    print("\n🚀 Example 3: Test Runner Setup")
    print("-" * 30)
    
    try:
        test_runner = AndroidWorldTestRunner(
            agent=agent,
            timeout_per_task=300,
            verbose=True
        )
        
        print("✅ Test runner initialized successfully")
        print("   Ready to run Android World tests!")
        print("\n💡 To run actual tests, use:")
        print("   python main.py --aw-task ContactsAddContact")
        print("   python main.py --aw-tasks ContactsAddContact ClockStopWatchRunning")
        print("   python main.py --android-world --aw-family android_world")
        
    except Exception as e:
        print(f"❌ Error initializing test runner: {e}")
    
    # Example 4: Result reporter capabilities
    print("\n📊 Example 4: Result Reporter")
    print("-" * 30)
    
    try:
        reporter = AndroidWorldResultReporter()
        print("✅ Result reporter initialized")
        print("   Capabilities:")
        print("   - Generate benchmark reports")
        print("   - Export CSV summaries")
        print("   - Compare multiple runs")
        print("   - Analyze error patterns")
        
    except Exception as e:
        print(f"❌ Error initializing reporter: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Android World Integration Example Complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
