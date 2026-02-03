# PhoneAgent 算法伪代码

## Algorithm 1: PhoneAgent.run(task)

```
Algorithm 1: PhoneAgent Main Loop
Input: task (user task description)
Output: execution result dictionary

1:  Initialize: context, step_count=0, actions=[], workflow
2:  result ← execute_step(task, is_first=True)
3:  if result.finished then
4:      return {finished: True, actions, step_count}
5:  end if
6:  
7:  while step_count < max_steps do
8:      result ← execute_step(task, is_first=False)
9:      if result.finished then
10:         return {finished: True, actions, step_count}
11:     end if
12: end while
13: return {finished: False, actions, step_count}
```

## Algorithm 2: PhoneAgent.execute_step()

```
Algorithm 2: Execute Single Step
Input: task, recorder, is_first
Output: StepResult

1:  step_count ← step_count + 1
2:  screenshot ← get_screenshot_or_reuse_cache()
3:  
4:  // Planning phase (conditional)
5:  if should_plan() and not post_skill_execution then
6:      plan ← planner.plan_task(task)
7:      if plan.decision == "use_skill" then
8:          result ← execute_skill(plan.skill_name, plan.skill_params)
9:          reflection ← reflect(action="SkillExecution", before_screenshot)
10:         return StepResult(success, finished=False)
11:     end if
12: end if
13: 
14: // Extract UI elements and create node
15: elements ← extract_ui_elements(screenshot)
16: node ← work_graph.create_node(elements)
17: 
18: // Add screenshot and screen info to context
19: context.add_screenshot(screenshot)
20: context.add_screen_info(elements)
21: 
22: // Get model response
23: response ← model_client.request(context.to_messages())
24: action ← parse_action(response.action, elements)
25: 
26: // Execute action
27: result ← action_handler.execute(action)
28: 
29: // Reflection (if enabled)
30: if enable_reflection and action ≠ "Finish" then
31:     reflection ← reflect(action.type, before_screenshot)
32:     context.add_reflection(reflection)
33: end if
34: 
35: // Update context and records
36: actions.append(action)
37: context.add_history_entry(response.thinking, action)
38: recorder.on_action_executed(node.id, action, result.success)
39: 
40: // Cache screenshot for next step
41: if not result.finished then
42:     cache_screenshot()
43: end if
44: 
45: return StepResult(result.success, result.finished, action)
```

## Algorithm 3: PhoneAgent.reflect()

```
Algorithm 3: Reflection Analysis
Input: action_type, action_desc, before_screenshot
Output: reflection result dictionary

1:  current_screenshot ← get_screenshot()
2:  before_elements ← extract_elements(before_screenshot)
3:  after_elements ← extract_elements(current_screenshot)
4:  
5:  // Fast path: obvious changes detection
6:  changes ← analyze_interface_changes(before_elements, after_elements)
7:  if changes.has_obvious_changes and not is_skill_execution then
8:      return {action_successful: True, confidence: 0.9, ...}
9:  end if
10: 
11: // Model-based analysis
12: reflection_prompt ← build_reflection_prompt(action_type, action_desc)
13: reflection_context ← [system_msg, user_msg(prompt, before_screenshot), 
14:                       user_msg("After:", current_screenshot)]
15: 
16: response ← model_client.request(reflection_context, mode="reflect")
17: reflect_json ← extract_json(response)
18: 
19: // Normalize result
20: if reflect_json.execution_result == "success" then
21:     action_successful ← True
22: else if reflect_json.execution_result == "failure" then
23:     action_successful ← False
24: else
25:     action_successful ← None  // partial success
26: end if
27: 
28: return {
29:     action_successful,
30:     confidence_score: reflect_json.confidence,
31:     reasoning: reflect_json.reasoning,
32:     suggestions: reflect_json.improvement_suggestions
33: }
```

## 核心流程图

```
┌─────────────────────────────────────────┐
│         PhoneAgent.run(task)            │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│      Initialize context & workflow      │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│    execute_step(task, is_first=True)   │
└──────────────────┬──────────────────────┘
                   │
                   ▼
            ┌──────────┐
            │ Finished? │──Yes──> Return result
            └─────┬────┘
                  │No
                  ▼
         ┌────────────────┐
         │ Loop until      │
         │ finished or     │
         │ max_steps       │
         └───┬────────┬───┘
             │        │
             │        └─> execute_step()
             │               │
             │               ▼
             │         ┌──────────┐
             │         │ Planning │──> Skill execution (optional)
             │         └─────┬────┘
             │               │
             │               ▼
             │         ┌──────────┐
             │         │ Model    │──> Get action from VLM
             │         │ Request  │
             │         └─────┬────┘
             │               │
             │               ▼
             │         ┌──────────┐
             │         │ Execute  │──> Perform action
             │         │ Action   │
             │         └─────┬────┘
             │               │
             │               ▼
             │         ┌──────────┐
             │         │ Reflect  │──> Verify result
             │         └─────┬────┘
             │               │
             │               ▼
             └───────<──────────
