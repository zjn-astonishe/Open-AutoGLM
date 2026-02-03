# SpeculativeExecutor 算法伪代码

## Algorithm 1: Get Speculative Context

```
Algorithm 1: Generate Speculative Context
Input: current_app, current_elements, task
Output: formatted speculative context string or None

1:  workflows ← find_relevant_workflows(current_app)
2:  if workflows = ∅ then
3:      return None
4:  end if
5:  
6:  matches ← find_current_node_matches(current_elements, workflows)
7:  if matches = ∅ then
8:      return None
9:  end if
10: 
11: future_nodes ← predict_future_nodes(matches)
12: if future_nodes = ∅ then
13:     return None
14: end if
15: 
16: return format_speculative_context(future_nodes)
```

## Algorithm 2: Find Best Matching Node

```
Algorithm 2: Find Current Node Matches
Input: current_elements, workflows
Output: best matching node tuple or []

1:  matches ← []
2:  for each workflow ∈ workflows do
3:      for each (i, transition) ∈ workflow.path do
4:          node ← find_node_by_id(transition.from_node_id)
5:          similarity ← calc_similarity(current_elements, node.elements)
6:          if similarity > threshold then
7:              matches.append((node, workflow, i, similarity))
8:          end if
9:      end for
10: end for
11: 
12: if matches = ∅ then
13:     return []
14: end if
15: 
16: sort matches by similarity (descending)
17: best_match ← matches[0]
18: return [(best_match.node, best_match.workflow, best_match.position)]
```

## Algorithm 3: Calculate Element Similarity

```
Algorithm 3: Jaccard Similarity Calculation
Input: current_elements, stored_elements
Output: similarity score ∈ [0, 1]

1:  if current_elements = ∅ or stored_elements = ∅ then
2:      return 0.0
3:  end if
4:  
5:  current_contents ← {elem.content | elem ∈ current_elements, content ≠ ""}
6:  stored_contents ← {elem.content | elem ∈ stored_elements, content ≠ ""}
7:  
8:  if current_contents = ∅ or stored_contents = ∅ then
9:      return 0.0
10: end if
11: 
12: intersection ← current_contents ∩ stored_contents
13: union ← current_contents ∪ stored_contents
14: 
15: return |intersection| / |union|
```

## Algorithm 4: Predict Future Nodes

```
Algorithm 4: Two-Step Future Prediction
Input: current_matches [(node, workflow, position)]
Output: list of SpeculativeNode (max 2 nodes)

1:  if current_matches = ∅ then
2:      return []
3:  end if
4:  
5:  (node, workflow, pos) ← current_matches[0]
6:  future_nodes ← []
7:  
8:  // Predict next UI state (1 step ahead)
9:  next_pos ← pos + 1
10: if next_pos < |workflow.path| then
11:     next_node ← find_node_by_id(workflow.path[next_pos].from_node_id)
12:     if next_node ≠ None then
13:         future_nodes.append(SpeculativeNode(next_node))
14:     end if
15: end if
16: 
17: // Predict UI state after next (2 steps ahead)
18: next_next_pos ← pos + 2
19: if next_next_pos < |workflow.path| then
20:     next_next_node ← find_node_by_id(workflow.path[next_next_pos].from_node_id)
21:     if next_next_node ≠ None then
22:         future_nodes.append(SpeculativeNode(next_next_node))
23:     end if
24: end if
25: 
26: return future_nodes[:max_speculative_nodes]
```

## Algorithm 5: Execute Speculative Actions

```
Algorithm 5: Speculative Executor
Input: predictions, recorder, initial_screenshot
Output: final screenshot or None

1:  screenshot ← initial_screenshot or get_screenshot()
2:  current_elements ← extract_elements(screenshot)
3:  pending_completed ← False
4:  
5:  for i ← 0 to |future_nodes| - 1 do
6:      // Check UI match
7:      if not elements_match(current_elements, future_nodes[i].elements) then
8:          break  // Stop if UI doesn't match prediction
9:      end if
10:     
11:     // Complete pending transition (first time only)
12:     if not pending_completed and recorder.has_pending() then
13:         complete_pending_transition(screenshot)
14:         pending_completed ← True
15:     end if
16:     
17:     // Parse and execute action
18:     action ← parse_action(predictions[i], i, current_elements)
19:     if action = None or action = "Finish" then
20:         break
21:     end if
22:     
23:     // Record and execute
24:     from_node ← get_last_workflow_node()
25:     node_action ← from_node.add_action(action)
26:     result ← execute(action)
27:     
28:     // Create to_node and complete transition
29:     screenshot ← get_screenshot()
30:     to_node ← create_node(screenshot)
31:     recorder.on_action_executed(from_node.id, node_action, result.success)
32:     recorder.on_new_node(to_node.id)
33:     
34:     // Update for next iteration
35:     current_elements ← extract_elements(screenshot)
36: end for
37: 
38: return screenshot
```

## 核心流程图

```
┌─────────────────────────────────────────┐
│  get_speculative_context()              │
└──────────────────┬──────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │ Find relevant    │
         │ workflows        │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Find current     │──> Calculate similarity
         │ node matches     │──> Select best match
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Predict future   │──> Next UI (1 step)
         │ nodes            │──> Next-next UI (2 steps)
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Format context   │──> Add B-series elements
         │ for model        │──> Add C-series elements
         └──────────────────┘

┌─────────────────────────────────────────┐
│  executor(predictions)                  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │ For each future  │
         │ node prediction  │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
    ┌───│ UI matches?      │───No──> Stop execution
    │   └────────┬─────────┘
    │            │Yes
    │            ▼
    │   ┌──────────────────┐
    │   │ Parse action     │
    │   └────────┬─────────┘
    │            │
    │            ▼
    │   ┌──────────────────┐
    │   │ Execute action   │
    │   └────────┬─────────┘
    │            │
    │            ▼
    │   ┌──────────────────┐
    │   │ Record to        │
    │   │ workflow         │
    │   └────────┬─────────┘
    │            │
    └────────────┘
```

## 关键特性

**1. 相似度匹配**
- 使用 Jaccard 相似度 (threshold = 0.7)
- 只选择最佳匹配节点

**2. 两步预测**
- B系列: 下一步UI状态
- C系列: 再下一步UI状态

**3. 失败处理**
- UI不匹配 → 立即停止
- 解析失败 → 停止执行
- 执行异常 → 停止执行
