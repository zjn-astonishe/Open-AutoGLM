# Open-AutoGLM Integration with AndroidWorld

This document explains how to run AndroidWorld tests with your Open-AutoGLM agent.

## Overview

AndroidWorld is a comprehensive benchmarking environment for autonomous Android agents. It provides 116 diverse tasks across 20 real-world apps with dynamic task instantiation for millions of unique variations.

Your Open-AutoGLM agent has been integrated as a custom agent that can be tested against AndroidWorld's benchmark suite.

## Prerequisites

### 1. Android Emulator Setup

First, you need to set up an Android emulator:

1. **Install Android Studio** from [here](https://developer.android.com/studio)

2. **Create an Android Virtual Device (AVD)**:
   - Hardware: **Pixel 6**
   - System Image: **Tiramisu, API Level 33**
   - AVD name: **AndroidWorldAvd**

3. **Launch the emulator** from command line (not Android Studio UI):
   ```bash
   # Find your emulator path (typically one of these):
   ~/Library/Android/sdk/emulator/emulator  # macOS
   ~/Android/Sdk/emulator/emulator          # Linux
   
   # Launch with required flags
   EMULATOR_NAME=AndroidWorldAvd
   ~/Library/Android/sdk/emulator/emulator -avd $EMULATOR_NAME -no-snapshot -grpc 8554
   ```

### 2. Install Dependencies

Install AndroidWorld dependencies:

```bash
cd android_world
pip install -r requirements.txt
python setup.py install
```

### 3. Environment Variables

Set up your model API keys:

```bash
# Add to your .bashrc or .zshrc
export OPENAI_API_KEY=your-openai-key        # If using OpenAI
export GCP_API_KEY=your-gcp-key              # If using Google models
# Add other API keys as needed for your model
```

### 4. Install ffmpeg

```bash
# macOS
brew install ffmpeg

# Linux (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg
```

## Running Tests

### Quick Test

First, test your agent integration with a simple script:

```bash
cd android_world
python test_open_autoglm.py
```

This will run a basic test to ensure your agent is properly integrated.

### Single Task Test

Run your agent on a specific task:

```bash
cd android_world
python run.py \
  --agent_name=open_autoglm \
  --suite_family=android_world \
  --tasks=ContactsAddContact \
  --n_task_combinations=1
```

### Multiple Tasks

Run on multiple specific tasks:

```bash
cd android_world
python run.py \
  --agent_name=open_autoglm \
  --suite_family=android_world \
  --tasks=ContactsAddContact,ClockStopWatchRunning \
  --n_task_combinations=1
```

### Full Benchmark Suite

Run the complete AndroidWorld benchmark:

```bash
cd android_world
python run.py \
  --agent_name=open_autoglm \
  --suite_family=android_world \
  --perform_emulator_setup \  # Only needed first time
  --n_task_combinations=1
```

**Important**: Use `--perform_emulator_setup` only on the first run to install necessary apps and set permissions.

### MiniWoB++ Tasks

Run web-based MiniWoB++ tasks:

```bash
cd android_world
python run.py \
  --agent_name=open_autoglm \
  --suite_family=miniwob \
  --perform_emulator_setup \
  --n_task_combinations=1
```

## Configuration

### Model Configuration

You can customize your model configuration by modifying the agent initialization in `android_world/run.py`:

```python
# In the _get_agent function, modify these lines:
model_config = ModelConfig(
    base_url="http://localhost:8000/v1",  # Your model endpoint
    api_key="your-api-key",               # Your API key
    model_name="your-model-name",         # Your model name
)

agent_config = AgentConfig(
    max_steps=50,                         # Max steps per task
    lang="en",                           # Language (use "en" for AndroidWorld)
    verbose=True,                        # Enable verbose logging
    memory_dir="./output/memory",        # Memory directory
)
```

### Available Command Line Options

- `--agent_name=open_autoglm`: Use your Open-AutoGLM agent
- `--suite_family`: Choose from `android_world`, `miniwob`, `android_family`, etc.
- `--tasks`: Comma-separated list of specific tasks to run
- `--n_task_combinations`: Number of parameter variations per task
- `--console_port`: Android emulator console port (default: 5554)
- `--output_path`: Directory to save results
- `--checkpoint_dir`: Resume from checkpoint directory

## Task Families

AndroidWorld provides several task families:

1. **android_world**: Main benchmark with 116 tasks across 20 apps
2. **miniwob**: Web-based tasks from MiniWoB++ benchmark
3. **android_family**: Android-specific tasks
4. **information_retrieval**: Information gathering tasks

## Results and Analysis

Results are saved to `~/android_world/runs/` by default. Each run creates a directory with:

- Task execution logs
- Screenshots and UI dumps
- Performance metrics
- Error reports

## Troubleshooting

### Common Issues

1. **Emulator not found**: Ensure emulator is running with `-grpc 8554` flag
2. **ADB connection issues**: Check `adb devices` shows your emulator
3. **Import errors**: Ensure all dependencies are installed and paths are correct
4. **Model API errors**: Verify your API keys and model configuration

### Debug Mode

Enable verbose logging for debugging:

```bash
cd android_world
python run.py \
  --agent_name=open_autoglm \
  --tasks=ContactsAddContact \
  --n_task_combinations=1 \
  --verbose
```

### Logs

Check logs in the output directory for detailed execution information:
- Agent actions and reasoning
- AndroidWorld environment interactions
- Error messages and stack traces

## Performance Tips

1. **Start Small**: Begin with single tasks before running full benchmark
2. **Use Checkpoints**: Resume interrupted runs with `--checkpoint_dir`
3. **Monitor Resources**: AndroidWorld can be resource-intensive
4. **Optimize Model**: Consider using faster/cheaper models for initial testing

## Next Steps

1. **Test Integration**: Run the quick test script first
2. **Single Task**: Try one simple task like `ContactsAddContact`
3. **Analyze Results**: Review logs and performance metrics
4. **Iterate**: Improve your agent based on AndroidWorld feedback
5. **Full Benchmark**: Run complete suite when ready

## Support

For issues specific to:
- **AndroidWorld**: Check the [AndroidWorld repository](https://github.com/google-research/android_world)
- **Open-AutoGLM**: Check your agent implementation and configuration
- **Integration**: Review the adapter code in `android_world/agents/open_autoglm_agent.py`

## Example Output

When running successfully, you should see output like:

```
🚀 Starting AndroidWorld evaluation
📱 Environment initialized
🤖 Agent: OpenAutoGLM initialized
🎯 Task: ContactsAddContact
📍 Step 1: Agent analyzing screen...
✅ Action executed: click(x=100, y=200)
📍 Step 2: Agent typing contact info...
✅ Action executed: input_text("John Doe")
🎉 Task completed successfully!
📊 Results saved to ~/android_world/runs/run_20231231_120000/
