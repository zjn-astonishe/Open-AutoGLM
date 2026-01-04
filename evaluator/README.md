# Evaluation for Open-AutoGLM

This module provides seamless integration between Open-AutoGLM and Android World benchmark testing framework, allowing you to run standardized Android automation tests while maintaining Open-AutoGLM's native `do()` format.

## Overview

The integration consists of four main components:

- **AndroidWorldTaskLoader**: Loads and manages Android World tasks
- **AndroidWorldEvaluator**: Evaluates task completion using Android World's native logic
- **AndroidWorldTestRunner**: Orchestrates test execution with Open-AutoGLM agents
- **AndroidWorldResultReporter**: Generates comprehensive test reports and analysis

## Quick Start

### 1. List Available Tasks

```bash
# List all available Android World tasks
python main.py --aw-list-tasks
```

### 2. Run Single Task

```bash
# Run a specific task
python main.py --aw-task ContactsAddContact

# Run with multiple parameter combinations
python main.py --aw-task ContactsAddContact --aw-combinations 3
```

### 3. Run Multiple Tasks

```bash
# Run specific tasks
python main.py --aw-tasks ContactsAddContact ClockStopWatchRunning

# Run from different task family
python main.py --aw-tasks ContactsAddContact --aw-family android_world
```

### 4. Run Full Benchmark

```bash
# Run complete Android World benchmark
python main.py --android-world

# Run with custom settings
python main.py --android-world --aw-family android_world --aw-combinations 2 --aw-timeout 600
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--android-world` | Run full Android World benchmark | - |
| `--aw-task TASK` | Run specific task | - |
| `--aw-tasks TASK1 TASK2 ...` | Run multiple specific tasks | - |
| `--aw-family FAMILY` | Task family to use | `android_world` |
| `--aw-combinations N` | Parameter combinations per task | `1` |
| `--aw-timeout SECONDS` | Timeout per task | `300` |
| `--aw-list-tasks` | List available tasks and exit | - |

## Task Families

Available task families include:

- **android_world**: Main benchmark with 116 tasks across 20 apps
- **miniwob**: Web-based tasks from MiniWoB++ benchmark
- **android_family**: Android-specific tasks
- **information_retrieval**: Information gathering tasks

## Programmatic Usage

### Basic Example

```python
from android_world_integration import AndroidWorldTestRunner
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# Create agent
model_config = ModelConfig(
    base_url="http://localhost:8001/v1",
    model_name="autoglm-phone-9b",
    api_key="EMPTY"
)

agent_config = AgentConfig(max_steps=50)
agent = PhoneAgent(model_config, agent_config)

# Create test runner
test_runner = AndroidWorldTestRunner(
    agent=agent,
    timeout_per_task=300,
    verbose=True
)

# Run single task
result = test_runner.run_single_task("ContactsAddContact")
print(f"Success: {result['success']}")
```

### Advanced Usage

```python
from android_world_integration import (
    AndroidWorldTaskLoader,
    AndroidWorldEvaluator,
    AndroidWorldResultReporter
)

# Load tasks
task_loader = AndroidWorldTaskLoader()
task = task_loader.get_task("ContactsAddContact")

# Run with agent (your implementation)
agent_result = agent.run(task['goal'])

# Evaluate result
evaluator = AndroidWorldEvaluator()
evaluation = evaluator.evaluate_task(task, agent_result)

# Generate report
reporter = AndroidWorldResultReporter()
report = reporter.generate_task_report(evaluation)
```

## Results and Analysis

### Output Structure

Test results are saved to timestamped directories with:

```
output/android_world_results/run_20240102_142530/
├── summary.json          # Overall results summary
├── tasks/                # Individual task results
│   ├── ContactsAddContact_001.json
│   └── ClockStopWatchRunning_001.json
├── reports/              # Generated reports
│   ├── benchmark_report.html
│   └── summary.csv
└── logs/                 # Execution logs
    └── test_runner.log
```

### Result Format

Each task result includes:

```json
{
  "task_name": "ContactsAddContact",
  "success": true,
  "execution_time": 45.2,
  "steps_taken": 8,
  "goal": "Add a new contact named John Doe",
  "agent_actions": [...],
  "evaluation_details": {...},
  "error_message": null
}
```

### Summary Statistics

Benchmark summaries provide:

- Success rate by task and overall
- Average execution time
- Step count analysis
- Error categorization
- Performance trends

## Integration Architecture

### Design Principles

1. **Non-invasive**: No changes to Open-AutoGLM's core `do()` format
2. **Modular**: Each component can be used independently
3. **Compatible**: Works with existing Android World tasks and evaluation logic
4. **Extensible**: Easy to add new task families or evaluation metrics

### Data Flow

```
Android World Task → Task Loader → Natural Language Goal
                                        ↓
Open-AutoGLM Agent ← Agent.run() ← Task Goal
                                        ↓
Agent Actions → Evaluator → Android World Evaluation → Results
```

### Environment Bridge

The integration automatically handles:

- Task parameter generation
- Natural language goal creation
- Environment state management
- Action format conversion
- Result evaluation and reporting

## Troubleshooting

### Common Issues

1. **Import Error**: Ensure `android_world` is installed
   ```bash
   cd android_world
   pip install -r requirements.txt
   python setup.py install
   ```

2. **No Tasks Found**: Check Android World installation
   ```bash
   python -c "from android_world import registry; print(registry.TaskRegistry().get_registry('android_world'))"
   ```

3. **Device Connection**: Ensure Android emulator is running
   ```bash
   adb devices
   # Should show connected device
   ```

4. **Timeout Issues**: Increase timeout for complex tasks
   ```bash
   python main.py --aw-task ComplexTask --aw-timeout 600
   ```

### Debug Mode

Enable verbose logging:

```bash
python main.py --aw-task ContactsAddContact --verbose
```

Or set in code:

```python
test_runner = AndroidWorldTestRunner(
    agent=agent,
    verbose=True  # Enable detailed logging
)
```

## Performance Tips

1. **Start Small**: Begin with single tasks before running full benchmark
2. **Use Checkpoints**: Results are automatically saved for analysis
3. **Monitor Resources**: Android World can be resource-intensive
4. **Optimize Timeouts**: Adjust based on task complexity

## Contributing

To add new task families or evaluation metrics:

1. Extend `AndroidWorldTaskLoader` for new task sources
2. Modify `AndroidWorldEvaluator` for custom evaluation logic
3. Update `AndroidWorldResultReporter` for new report formats
4. Add tests in `tests/` directory

## Examples

See `examples/android_world_example.py` for a complete working example demonstrating all integration features.

## Support

For issues related to:
- **Android World**: Check the [Android World repository](https://github.com/google-research/android_world)
- **Open-AutoGLM**: Check the main project documentation
- **Integration**: Review this README and example code
