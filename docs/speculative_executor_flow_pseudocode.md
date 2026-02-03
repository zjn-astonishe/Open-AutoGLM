# SpeculativeExecutor 流程伪代码

## 概述

SpeculativeExecutor（推测性执行器）用于预测未来的UI状态和动作，通过分析历史工作流来预测可能的下一步操作，帮助模型做出更好的决策。

## 数据结构

```pseudocode
DATACLASS SpeculativeNode:
    node_id: string
    elements_info: List[Dict]
    source_workflow: string
    transition_action: Optional[WorkAction]
END DATACLASS
```

## 主要流程

### 1. 生成推测性上下文

```pseudocode
FUNCTION get_speculative_context(
    current_app: string,
    current_elements: List[Dict],
    task: string
) -> Optional[string]:
    
    // ============================================
    // 1. 查找相关工作流
    // ============================================
    relevant_workflows = find_relevant_workflows(current_app)
    
    IF length(relevant_workflows) == 0 THEN
        print("No relevant workflows found")
        RETURN null
    END IF
    
    print(f"Found {length(relevant_workflows)} relevant workflows")
    
    // ============================================
    // 2. 查找当前节点匹配
    // ============================================
    current_node_matches = find_current_node_matches(
        current_elements, 
        relevant_workflows
    )
    
    IF length(current_node_matches) == 0 THEN
        print("No current node matches found")
        RETURN null
    END IF
    
    // ============================================
    // 3. 预测未来节点
    // ============================================
    future_nodes = predict_future_nodes(current_node_matches)
    
    IF length(future_nodes) == 0 THEN
        print("No future nodes predicted")
        RETURN null
    END IF
    
    // ============================================
    // 4. 格式化推测性上下文
    // ============================================
    speculative_context = format_speculative_context(future_nodes)
    
    RETURN speculative_context
END FUNCTION
```

### 2. 查找相关工作流

```pseudocode
FUNCTION find_relevant_workflows(current_app: string) -> List[Workflow]:
    
    relevant_workflows = []
    
    // 遍历历史工作流
    FOR EACH workflow IN memory.historical_workflows DO
        workflow_apps = empty_set()
        
        // 收集工作流涉及的应用
        FOR EACH transition IN workflow.path DO
            // 查找包含此节点的工作图
            FOR EACH workgraph IN memory.historical_workgraphs DO
                IF transition.from_node_id IN workgraph.nodes THEN
                    workflow_apps.add(workgraph.app)
                    BREAK
                END IF
            END FOR
        END FOR
        
        // 如果工作流包含当前应用，则添加到结果
        IF current_app IN workflow_apps THEN
            relevant_workflows.append(workflow)
        END IF
    END FOR
    
    RETURN relevant_workflows
END FUNCTION
```

### 3. 查找当前节点匹配（最高相似度）

```pseudocode
FUNCTION find_current_node_matches(
    current_elements: List[Dict],
    workflows: List[Workflow]
) -> List[Tuple[WorkNode, Workflow, int]]:
    
    all_matches = []
    
    // ============================================
    // 1. 收集所有匹配节点及其相似度
    // ============================================
    FOR EACH workflow IN workflows DO
        FOR i, transition IN enumerate(workflow.path) DO
            // 查找节点
            node = find_node_by_id(transition.from_node_id)
            
            IF node exists THEN
                // 计算相似度分数
                similarity = calculate_elements_similarity(
                    current_elements, 
                    node.elements_info
                )
                
                IF similarity > elements_match_threshold THEN
                    all_matches.append((node, workflow, i, similarity))
                END IF
            END IF
        END FOR
    END FOR
    
    // ============================================
    // 2. 选择最佳匹配
    // ============================================
    IF length(all_matches) == 0 THEN
        RETURN []
    END IF
    
    // 按相似度排序（降序）
    sort(all_matches, by=similarity, reverse=true)
    
    // 只返回最佳匹配（去掉相似度分数）
    best_match = all_matches[0]
    print(f"Selected best match with similarity: {best_match.similarity}")
    
    RETURN [(best_match.node, best_match.workflow, best_match.position)]
END FUNCTION
```

### 4. 计算元素相似度

```pseudocode
FUNCTION calculate_elements_similarity(
    current_elements: List[Dict],
    stored_elements: List[Dict]
) -> float:
    
    IF current_elements is empty OR stored_elements is empty THEN
        RETURN 0.0
    END IF
    
    // ============================================
    // 1. 提取元素内容集合
    // ============================================
    current_contents = empty_set()
    stored_contents = empty_set()
    
    FOR EACH elem IN current_elements DO
        content = elem.get('content', '').strip()
        IF content is not empty THEN
            current_contents.add(content)
        END IF
    END FOR
    
    FOR EACH elem IN stored_elements DO
        content = elem.get('content', '').strip()
        IF content is not empty THEN
            stored_contents.add(content)
        END IF
    END FOR
    
    IF current_contents is empty OR stored_contents is empty THEN
        RETURN 0.0
    END IF
    
    // ============================================
    // 2. 计算 Jaccard 相似度
    // ============================================
    intersection = current_contents INTERSECT stored_contents
    union = current_contents UNION stored_contents
    
    similarity = length(intersection) / length(union)
    
    RETURN similarity
END FUNCTION
```

### 5. 预测未来节点

```pseudocode
FUNCTION predict_future_nodes(
    current_matches: List[Tuple[WorkNode, Workflow, int]]
) -> List[SpeculativeNode]:
    
    IF length(current_matches) == 0 THEN
        RETURN []
    END IF
    
    // 使用最佳匹配进行预测
    current_node, workflow, position = current_matches[0]
    
    print(f"Predicting from workflow '{workflow.id}' at position {position}")
    
    future_nodes = []
    
    // ============================================
    // 1. 预测下一个UI状态（1步之后）
    // ============================================
    next_position = position + 1
    
    IF next_position < length(workflow.path) THEN
        next_transition = workflow.path[next_position]
        next_node = find_node_by_id(next_transition.from_node_id)
        
        IF next_node exists THEN
            speculative_node = SpeculativeNode(
                node_id=next_node.id,
                elements_info=next_node.elements_info,
                source_workflow=workflow.id,
                transition_action=next_transition.action
            )
            future_nodes.append(speculative_node)
            print(f"Predicted next transition: {next_transition.from_node_id}")
        END IF
    END IF
    
    // ============================================
    // 2. 预测下下个UI状态（2步之后）
    // ============================================
    next_next_position = position + 2
    
    IF next_next_position < length(workflow.path) THEN
        next_next_transition = workflow.path[next_next_position]
        next_next_node = find_node_by_id(next_next_transition.from_node_id)
        
        IF next_next_node exists THEN
            speculative_node = SpeculativeNode(
                node_id=next_next_node.id,
                elements_info=next_next_node.elements_info,
                source_workflow=workflow.id,
                transition_action=next_next_transition.action
            )
            future_nodes.append(speculative_node)
            print(f"Predicted next-next transition: {next_next_transition.from_node_id}")
        END IF
    END IF
    
    // 限制最大预测数量
    RETURN future_nodes[:max_speculative_nodes]
END FUNCTION
```

### 6. 格式化推测性上下文

```pseudocode
FUNCTION format_speculative_context(
    future_nodes: List[SpeculativeNode]
) -> string:
    
    IF length(future_nodes) == 0 THEN
        RETURN ""
    END IF
    
    print(f"Formatting speculative context for {length(future_nodes)} nodes")
    
    context_lines = []
    
    // ============================================
    // 1. 格式化第一个节点（下一步）
    // ============================================
    IF length(future_nodes) >= 1 THEN
        node = future_nodes[0]
        context_lines.append("--- NEXT UI STATE (after current action) ---")
        context_lines.append("Key UI Elements:")
        
        // 添加关键UI元素
        FOR j, element IN enumerate(node.elements_info) DO
            content = element.get('content', '').strip()
            IF content is not empty THEN
                context_lines.append(f"  B{j+1}: {content}")
            END IF
        END FOR
    END IF
    
    // ============================================
    // 2. 格式化第二个节点（两步之后）
    // ============================================
    IF length(future_nodes) >= 2 THEN
        node = future_nodes[1]
        context_lines.append("--- UI STATE AFTER NEXT (two steps ahead) ---")
        context_lines.append("Key UI Elements:")
        
        // 添加关键UI元素
        FOR j, element IN enumerate(node.elements_info) DO
            content = element.get('content', '').strip()
            IF content is not empty THEN
                context_lines.append(f"  C{j+1}: {content}")
            END IF
        END FOR
    END IF
    
    RETURN join(context_lines, '\n')
END FUNCTION
```

### 7. 解析推测性动作

```pseudocode
FUNCTION parse_action(
    action_code: string,
    before_elements_index: int,
    elements_info: List[Dict],
    is_portal: bool = true
) -> Tuple[Dict, string]:
    
    TRY
        action_code = action_code.strip()
        
        IF action_code.startswith("do") THEN
            // ============================================
            // 1. 使用AST安全解析
            // ============================================
            // 转义特殊字符
            action_code = escape_special_chars(action_code)
            
            // 解析AST
            tree = ast.parse(action_code, mode="eval")
            
            IF NOT is_function_call(tree.body) THEN
                RAISE ValueError("Expected a function call")
            END IF
            
            call = tree.body
            action = {"_metadata": "do"}
            
            // 提取关键字参数
            FOR EACH keyword IN call.keywords DO
                key = keyword.arg
                value = ast.literal_eval(keyword.value)
                action[key] = value
            END FOR
            
            // ============================================
            // 2. 转换元素ID到实际坐标
            // ============================================
            IF "element" IN action AND is_string(action["element"]) THEN
                element_id = action["element"]
                
                // 在推测性节点中查找元素
                FOR EACH e2 IN future_nodes[before_elements_index].elements_info DO
                    IF element_id == e2["id"] THEN
                        print(f"Found element with id: {element_id}")
                        
                        // 构建元素内容标识
                        IF is_portal THEN
                            e2_content = f"{e2['resourceId']}/{e2['className']}/{e2['content']}"
                        ELSE
                            e2_content = e2["content"]
                        END IF
                        
                        // 在当前元素中查找匹配
                        bbox = null
                        FOR EACH e1 IN elements_info DO
                            IF is_portal THEN
                                e1_content = f"{e1['resourceId']}/{e1['className']}/{e1['content']}"
                            ELSE
                                e1_content = e1["content"]
                            END IF
                            
                            // 内容完全匹配
                            IF e1_content == e2_content THEN
                                print(f"Element content matched: {e1_content}")
                                bbox = e1['bbox']
                                BREAK
                            END IF
                        END FOR
                        
                        // 转换bbox到中心坐标
                        IF bbox exists THEN
                            center_x = (bbox[0][0] + bbox[1][0]) / 2
                            center_y = (bbox[0][1] + bbox[1][1]) / 2
                            action["element"] = [center_x, center_y]
                            
                            IF is_portal THEN
                                RETURN (action, f"{e1['resourceId']}/{e1['className']}/{e1['content']}")
                            ELSE
                                RETURN (action, e1["content"])
                            END IF
                        ELSE
                            RETURN (null, null)
                        END IF
                    END IF
                END FOR
                
                RETURN (null, null)
            END IF
            
            RETURN (action, null)
        ELSE
            RAISE ValueError(f"Failed to parse action: {action_code}")
        END IF
        
    CATCH exception
        RAISE ValueError(f"Failed to parse action: {exception}")
    END TRY
END FUNCTION
```

### 8. 执行推测性预测

```pseudocode
FUNCTION executor(
    prediction: Dict[string, string],
    recorder: Optional[WorkflowRecorder],
    initial_screenshot: Optional[Screenshot],
    is_portal: bool = true
) -> Optional[Screenshot]:
    
    // ============================================
    // 1. 准备初始截图和元素
    // ============================================
    IF initial_screenshot exists THEN
        screenshot = initial_screenshot
    ELSE
        screenshot = AWAIT device.get_screenshot()
    END IF
    
    final_screenshot = screenshot
    current_elements = extract_elements(screenshot, is_portal)
    
    pending_transition_completed = false
    
    // ============================================
    // 2. 遍历推测性节点执行动作
    // ============================================
    FOR i IN range(length(future_nodes)) DO
        // 检查当前UI是否匹配推测性节点
        is_match = elements_match(current_elements, future_nodes[i].elements_info)
        
        print(f"Elements match with speculative node: {is_match}")
        
        IF NOT is_match THEN
            BREAK  // UI状态不匹配，停止推测性执行
        END IF
        
        // ============================================
        // 3. 完成agent.py的待处理转换（仅首次）
        // ============================================
        IF NOT pending_transition_completed AND recorder exists 
           AND recorder.pending_from_node_id exists THEN
            
            // 获取当前应用和工作图
            current_app = AWAIT device.get_current_app()
            work_graph = memory.get_work_graph(current_app)
            
            IF work_graph is null THEN
                work_graph = memory.add_work_graph(current_app)
            END IF
            
            // 创建to_node完成agent.py的动作
            after_elements = extract_elements(screenshot, is_portal)
            to_node = work_graph.create_node(after_elements)
            
            // 完成待处理转换
            recorder.on_new_node(current_node_id=to_node.id)
            pending_transition_completed = true
            
            print("✅ Completed agent.py's pending transition")
        END IF
        
        // ============================================
        // 4. 为推测性节点分配元素ID
        // ============================================
        FOR j IN range(length(future_nodes[i].elements_info)) DO
            IF i == 0 THEN
                future_nodes[i].elements_info[j]['id'] = f"B{j+1}"
            ELSE IF i == 1 THEN
                future_nodes[i].elements_info[j]['id'] = f"C{j+1}"
            END IF
        END FOR
        
        // ============================================
        // 5. 解析推测性动作
        // ============================================
        print(f"Parsing predictive action: {list(prediction.values())[i]}")
        
        action, element_content = AWAIT parse_action(
            list(prediction.values())[i],
            i,
            current_elements,
            is_portal
        )
        
        IF action is null THEN
            BREAK  // 解析失败，停止执行
        END IF
        
        IF action == "Finish" THEN
            print("Speculative action is Finish, skipping")
            BREAK
        END IF
        
        // ============================================
        // 6. 执行动作（如果有元素或不需要元素）
        // ============================================
        IF ('element' NOT IN action) OR (action['element'] AND element_content) THEN
            print(f"Executing speculative action: {action}")
            
            TRY
                // ----------------------------------------
                // 6.1 记录动作前的状态
                // ----------------------------------------
                from_node_id = null
                node_action = null
                
                IF recorder exists THEN
                    current_app = AWAIT device.get_current_app()
                    work_graph = memory.get_work_graph(current_app)
                    
                    IF work_graph is null THEN
                        work_graph = memory.add_work_graph(current_app)
                    END IF
                    
                    workflow = memory.get_current_workflow()
                    from_node_id = workflow.get_last_id()
                    
                    IF from_node_id is null THEN
                        print("⚠️ Warning: workflow has no last node")
                        CONTINUE
                    END IF
                    
                    from_node = work_graph.get_node_by_id(from_node_id)
                    
                    IF from_node is null THEN
                        print(f"⚠️ Warning: from_node {from_node_id} not found")
                        CONTINUE
                    END IF
                    
                    // 获取当前元素
                    before_elements = extract_elements(screenshot, is_portal)
                    
                    // 根据动作类型创建node_action
                    IF action["action"] == "Type" THEN
                        zone_path = find_zone_path(element_content, before_elements, is_portal)
                        node_action = from_node.add_action(
                            action_type="Type",
                            description=list(prediction.keys())[i],
                            text=action.get("text"),
                            zone_path=zone_path
                        )
                        
                    ELSE IF action["action"] == "Swipe" THEN
                        zone_path = find_zone_path(element_content, before_elements, is_portal)
                        node_action = from_node.add_action(
                            action_type="Swipe",
                            description=list(prediction.keys())[i],
                            zone_path=zone_path,
                            direction=action.get("direction"),
                            distance=action.get("dist")
                        )
                        
                    ELSE
                        zone_path = find_zone_path(element_content, before_elements, is_portal)
                        node_action = from_node.add_action(
                            action_type=action["action"],
                            description=list(prediction.keys())[i],
                            zone_path=zone_path
                        )
                    END IF
                END IF
                
                // ----------------------------------------
                // 6.2 执行动作
                // ----------------------------------------
                result = AWAIT action_handler.execute(
                    action, 
                    screenshot.width, 
                    screenshot.height
                )
                
                // ----------------------------------------
                // 6.3 记录动作执行结果
                // ----------------------------------------
                IF recorder exists AND from_node_id exists AND node_action exists THEN
                    // 记录动作执行
                    recorder.on_action_executed(
                        from_node_id=from_node_id,
                        action=node_action,
                        success=result.success
                    )
                    
                    // 获取执行后的截图创建to_node
                    after_screenshot = AWAIT device.get_screenshot()
                    after_elements = extract_elements(after_screenshot, is_portal)
                    
                    // 创建to_node
                    to_node = work_graph.create_node(after_elements)
                    
                    // 完成转换
                    recorder.on_new_node(current_node_id=to_node.id)
                    
                    // 更新状态供下一次迭代使用
                    screenshot = after_screenshot
                    final_screenshot = after_screenshot
                    current_elements = extract_elements(screenshot, is_portal)
                END IF
                
                // ----------------------------------------
                // 6.4 添加到上下文
                // ----------------------------------------
                action_dict = {list(prediction.keys())[i]: list(prediction.values())[i]}
                print(f"Speculative action executed: {action_dict}")
                context.add_history_entry(content="", action=action_dict)
                
            CATCH exception
                print(f"Speculative action execution error: {exception}")
                BREAK  // 执行失败，停止推测性执行
            END TRY
        END IF
    END FOR
    
    RETURN final_screenshot
END FUNCTION
```

### 9. 检查元素匹配

```pseudocode
FUNCTION elements_match(
    current_elements: List[Dict],
    stored_elements: List[Dict]
) -> bool:
    
    similarity = calculate_elements_similarity(current_elements, stored_elements)
    
    print(f"Element similarity: {similarity:.2f}")
    
    // 使用70%相似度阈值
    RETURN similarity > elements_match_threshold
END FUNCTION
```

## 关键概念说明

### 1. **推测性执行流程**
推测性执行器通过以下步骤工作：
1. 查找与当前应用相关的历史工作流
2. 在工作流中找到与当前UI状态最匹配的节点
3. 基于工作流预测接下来1-2步的UI状态
4. 将预测的UI状态格式化后添加到提示词中
5. 如果模型给出推测性动作，验证UI状态并执行

### 2. **相似度匹配机制**
- 使用 Jaccard 相似度（交集/并集）计算UI元素相似度
- 默认阈值为70%，可以容忍部分UI变化
- 只选择最高相似度的匹配节点进行预测

### 3. **两步预测策略**
- **第1步预测**：当前动作执行后的UI状态（B系列元素）
- **第2步预测**：再下一步的UI状态（C系列元素）
- 这种策略帮助模型考虑更长远的影响

### 4. **动作解析与执行**
- 推测性动作使用不同的元素ID前缀（B、C）
- 需要将推测性元素ID映射回当前UI中的实际元素
- 通过内容匹配找到对应元素，获取其坐标执行动作

### 5. **工作流记录集成**
- 推测性执行的动作同样记录到工作流中
- 首次执行前需要完成agent.py的待处理转换
- 每个动作创建完整的from_node → action → to_node记录

### 6. **失败处理机制**
- UI状态不匹配时立即停止推测性执行
- 动作解析失败时停止执行
- 动作执行异常时停止执行
- 确保推测性执行不会影响主流程的稳定性

### 7. **上下文更新**
- 推测性执行的动作添加到对话上下文中
- 帮助模型理解已经执行了哪些推测性步骤
- 后续决策可以基于推测性执行的结果

### 8. **截图优化**
- 支持传入初始截图避免重复捕获
- 返回最终截图供下一步使用
- 减少设备通信开销，提高执行效率

## 优化要点

1. **最佳匹配选择**：只使用最高相似度的匹配进行预测，避免低质量预测
2. **提前终止**：任何不匹配或失败立即停止，避免错误累积
3. **完整记录**：确保推测性动作完整记录到工作流中
4. **状态同步**：每次执行后更新截图和元素状态
5. **异常处理**：每个关键步骤都有try-catch保护

## 使用场景

推测性执行特别适用于：
- 重复性任务（UI状态变化有规律）
- 已经有历史经验的任务类型
- 多步骤顺序操作
- 需要提前考虑后续影响的决策

不适用于：
- 全新的任务类型（无历史数据）
- UI状态变化不可预测
- 需要用户输入的交互
- 一次性的特殊操作
