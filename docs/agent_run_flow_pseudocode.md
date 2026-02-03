# PhoneAgent Run 流程伪代码

## 主要流程概述

```pseudocode
FUNCTION run(task: string) -> dict:
    // ============================================
    // 1. 初始化阶段
    // ============================================
    start_time = current_time()
    
    // 重置上下文和状态
    context.reset()
    context.set_system_prompt(system_prompt)
    context.set_task(task)
    
    // 初始化计数器和状态变量
    step_count = 0
    actions_executed = []
    last_screenshot = null
    
    // 创建工作流记录器
    workflow = memory.create_workflow(task)
    recorder = WorkflowRecorder(task, workflow)
    
    // 重置执行状态
    post_skill_execution = false
    executed_skills = []
    planning_cache = {}
    planning_done = false
    
    // ============================================
    // 2. 执行第一步（带用户提示）
    // ============================================
    result = AWAIT execute_step(task, recorder, is_first=true)
    
    IF result.finished THEN
        memory.save_to_json()
        RETURN {
            finished: true,
            actions: actions_executed,
            result_message: result.message,
            step_count: step_count
        }
    END IF
    
    // ============================================
    // 3. 循环执行后续步骤
    // ============================================
    WHILE step_count < max_steps DO
        result = AWAIT execute_step(task, recorder, is_first=false)
        
        IF result.finished THEN
            end_time = current_time()
            workflow.set_step()
            workflow.set_timecost(end_time - start_time)
            memory.save_to_json()
            
            RETURN {
                finished: true,
                actions: actions_executed,
                result_message: result.message,
                step_count: step_count
            }
        END IF
    END WHILE
    
    // ============================================
    // 4. 达到最大步数未完成
    // ============================================
    end_time = current_time()
    
    RETURN {
        finished: false,
        actions: actions_executed,
        result_message: "Max steps reached",
        step_count: step_count
    }
END FUNCTION
```

## execute_step 详细流程

```pseudocode
FUNCTION execute_step(user_prompt: string, recorder: WorkflowRecorder, is_first: bool) -> StepResult:
    step_count++
    
    // ============================================
    // 1. 截图优化：复用缓存的截图
    // ============================================
    IF last_screenshot exists AND NOT is_first THEN
        before_screenshot = last_screenshot
        screenshot = before_screenshot
        print("📸 Reusing cached screenshot")
    ELSE
        screenshot = AWAIT device.get_screenshot()
        before_screenshot = screenshot
    END IF
    
    current_app = AWAIT device.get_current_app()
    
    // ============================================
    // 2. Planning 阶段（条件触发）
    // ============================================
    should_plan = determine_if_should_plan(is_first)
    
    IF should_plan AND NOT post_skill_execution THEN
        TRY
            // 检查缓存或生成新计划
            plan = get_cached_or_new_plan(user_prompt)
            
            IF plan is null THEN
                plan = AWAIT planner.plan_task(user_prompt)
                cache_planning_result(user_prompt, plan)
                planning_done = true
            END IF
            
            // ============================================
            // 3. Skill 执行（如果计划决定使用 skill）
            // ============================================
            IF plan.decision == "use_skill" AND plan.skill_name NOT IN executed_skills THEN
                print("🔧 Executing skill:", plan.skill_name)
                
                TRY
                    skill_result = AWAIT skill_executor.execute_skill(plan.skill_name, plan.skill_params)
                CATCH exception
                    skill_result = "Error"
                END TRY
                
                // 记录 skill 执行
                recorder.on_action_executed(
                    from_node_id="skill_" + plan.skill_name,
                    action=WorkAction(type="skill_execution", description=...),
                    success=(skill_result != "Error")
                )
                
                executed_skills.append(plan.skill_name)
                post_skill_execution = true
                
                // ============================================
                // 4. Skill 执行后立即验证（Reflection）
                // ============================================
                IF skill_result != "Error" THEN
                    after_skill_screenshot = AWAIT device.get_screenshot()
                    
                    IF reflection_enabled THEN
                        reflection_result = AWAIT reflect(
                            action_type="SkillExecution",
                            action_description=...,
                            before_screenshot=screenshot,
                            is_skill_execution=true
                        )
                        
                        IF reflection_result.action_successful == false THEN
                            print("⚠️ Reflection indicates skill execution may have failed")
                        END IF
                    END IF
                    
                    // 缓存 skill 执行后的截图
                    last_screenshot = after_skill_screenshot
                    post_skill_execution = false
                    
                    RETURN StepResult(
                        success=reflection_result.action_successful,
                        finished=false,
                        action={"action": "SkillExecution", "skill_name": plan.skill_name},
                        thinking=...,
                        message=...
                    )
                ELSE
                    print("❌ Skill execution failed, falling back to atomic actions")
                    post_skill_execution = false
                END IF
            END IF
        CATCH exception
            print("⚠️ Planning failed:", exception)
        END TRY
    END IF
    
    // ============================================
    // 5. 获取工作图和创建节点
    // ============================================
    work_graph = memory.get_work_graph(current_app)
    IF work_graph is null THEN
        work_graph = memory.add_work_graph(current_app)
    END IF
    
    // 提取 UI 元素信息
    elements_info = []
    FOR each element IN screenshot.elements DO
        elements_info.append({
            id: "A" + index,
            content: element.content,
            bbox: element.bounds,
            ...
        })
    END FOR
    
    // 创建节点
    node = work_graph.create_node(elements_info)
    node.add_task(user_prompt)
    
    IF NOT is_first AND recorder has pending transition THEN
        recorder.on_new_node(current_node_id=node.id)
    END IF
    
    // ============================================
    // 6. 构建屏幕信息并添加到上下文
    // ============================================
    screen_info = build_screen_info(current_app, elements_info)
    context.add_screenshot(screenshot.base64_data)
    context.add_screen_info(screen_info)
    
    // ============================================
    // 7. 调用模型获取响应
    // ============================================
    TRY
        print("💭 Thinking...")
        
        start_time = current_time()
        response = AWAIT model_client.request(context.to_messages())
        end_time = current_time()
        
        print("Inference Time:", end_time - start_time)
    CATCH exception
        RETURN StepResult(
            success=false,
            finished=true,
            action=null,
            thinking="",
            message="Model error: " + exception
        )
    END TRY
    
    // ============================================
    // 8. 解析和执行动作
    // ============================================
    TRY
        action, element_content = parse_action(response.action, elements_info)
        
        // 根据动作类型创建 node_action
        IF element_content exists THEN
            IF action.type == "Swipe" THEN
                node_action = node.add_action(type="Swipe", zone_path=..., direction=..., distance=...)
            ELSE IF action.type == "Type" THEN
                node_action = node.add_action(type="Type", zone_path=..., text=...)
            ELSE
                node_action = node.add_action(type=action.type, zone_path=...)
            END IF
        ELSE
            node_action = node.add_action(type=action.type, description=...)
        END IF
    CATCH ValueError
        action = finish(message=response.action)
    END TRY
    
    // ============================================
    // 9. 错误预防检查
    // ============================================
    IF action.type != "Finish" THEN
        ui_context = {
            current_app: current_app,
            element_count: length(elements_info),
            screenshot_size: (screenshot.width, screenshot.height)
        }
        
        prevention_guidance = error_analyzer.get_prevention_guidance(action, ui_context)
        IF prevention_guidance exists THEN
            print("🚨 Error Prevention Guidance:", prevention_guidance)
        END IF
    END IF
    
    // 清理当前步骤的上下文
    context.clear_current_step()
    context.clear_speculative_context()
    
    // ============================================
    // 10. 执行动作
    // ============================================
    TRY
        result = AWAIT action_handler.execute(action, screenshot.width, screenshot.height)
    CATCH exception
        result = AWAIT action_handler.execute(finish(message=exception), ...)
    END TRY
    
    // ============================================
    // 11. 动作执行后的反思（Reflection）
    // ============================================
    reflection_result = null
    
    IF reflection_enabled AND action.type != "Finish" AND NOT result.should_finish THEN
        should_reflect = true
        IF reflection_on_failure_only THEN
            should_reflect = NOT result.success
        END IF
        
        IF should_reflect THEN
            TRY
                reflection_result = AWAIT reflect(
                    action_type=action.type,
                    action_description=...,
                    before_screenshot=before_screenshot
                )
                
                // 更新 node_action 的反思结果
                node_action.reflection_result = reflection_result
                node_action.confidence_score = reflection_result.confidence_score
                
                IF reflection_result.action_successful == false THEN
                    print("⚠️ Reflection indicates action may have failed")
                END IF
            CATCH exception
                print("Reflection analysis failed:", exception)
            END TRY
        END IF
    END IF
    
    // ============================================
    // 12. 错误模式分析
    // ============================================
    error_analyzer.record_action_result(action, result.success)
    
    IF NOT result.success AND reflection_result exists AND reflection_result.action_successful == false THEN
        ui_context = {...}
        
        TRY
            error_pattern = error_analyzer.analyze_failure(
                action=action,
                reflection_result=reflection_result,
                ui_context=ui_context,
                recent_history=actions_executed[-5:]
            )
            
            IF error_pattern exists THEN
                print("🔍 Error Pattern Detected:", error_pattern.pattern_type)
                print("📝 Description:", error_pattern.description)
                print("💡 Suggestions:", error_pattern.suggested_alternatives)
            END IF
        CATCH exception
            print("Error pattern analysis failed:", exception)
        END TRY
    END IF
    
    // ============================================
    // 13. 更新上下文和记录
    // ============================================
    actions_executed.append(action)
    context.add_history_entry(response.thinking, response.action)
    
    // 添加反思结果到上下文（如果有）
    IF reflection_result exists THEN
        action_successful = reflection_result.action_successful
        confidence_score = reflection_result.confidence_score
        
        IF action_successful == true AND confidence_score >= 0.8 THEN
            context.add_reflection(
                action_type=action.type,
                success=true,
                confidence=confidence_score,
                reasoning="Action was successful",
                suggestions=""
            )
        ELSE IF action_successful == false THEN
            context.add_reflection(
                action_type=action.type,
                success=false,
                confidence=confidence_score,
                reasoning=reflection_result.reflection_reasoning,
                suggestions=reflection_result.improvement_suggestions
            )
        ELSE
            context.add_reflection(
                action_type=action.type,
                success=action_successful,
                confidence=confidence_score,
                reasoning=reflection_result.reflection_reasoning,
                suggestions=reflection_result.improvement_suggestions
            )
        END IF
    END IF
    
    // 记录动作执行
    recorder.on_action_executed(
        from_node_id=node.id,
        action=node_action,
        success=result.success
    )
    
    // ============================================
    // 14. 检查是否完成
    // ============================================
    finished = (action.type == "Finish") OR result.should_finish
    
    // 缓存执行后的截图供下一步使用
    IF NOT finished THEN
        TRY
            last_screenshot = AWAIT device.get_screenshot()
            print("📸 Cached after-action screenshot for next step")
        CATCH exception
            last_screenshot = null
        END TRY
    END IF
    
    IF finished THEN
        recorder.flush()
        print("🎉 Task completed:", result.message)
    END IF
    
    RETURN StepResult(
        success=result.success,
        finished=finished,
        action=action,
        thinking=response.thinking,
        predict=response.predict,
        message=result.message
    )
END FUNCTION
```

## Reflection（反思）流程

```pseudocode
FUNCTION reflect(action_type, action_description, before_screenshot, is_skill_execution) -> dict:
    // ============================================
    // 1. 验证输入
    // ============================================
    IF before_screenshot is null THEN
        RETURN {
            action_successful: null,
            execution_result: "failure",
            interface_changes: "Missing before screenshot",
            confidence_score: 0.0,
            ...
        }
    END IF
    
    // ============================================
    // 2. 捕获执行后的截图
    // ============================================
    current_screenshot = AWAIT device.get_screenshot()
    
    // ============================================
    // 3. 提取 UI 元素
    // ============================================
    before_elements = extract_elements(before_screenshot)
    after_elements = extract_elements(current_screenshot)
    
    // ============================================
    // 4. 分析界面变化（快速路径）
    // ============================================
    changes_analysis = analyze_interface_changes(before_elements, after_elements)
    has_obvious_changes = changes_analysis.has_obvious_changes
    
    // 对于原子动作，如果有明显变化则认为成功
    IF NOT is_skill_execution AND has_obvious_changes THEN
        print("✅ Obvious UI changes detected — atomic action assumed successful")
        RETURN {
            action_successful: true,
            execution_result: "success",
            interface_changes: changes_analysis.changes_description,
            confidence_score: 0.9,
            used_model_analysis: false,
            ...
        }
    END IF
    
    // ============================================
    // 5. 构建反思提示词
    // ============================================
    reflection_prompt = """
    You are an action execution evaluator for an Android UI agent.
    
    Executed action:
    - Type: {action_type}
    - Description: {action_description}
    
    Analyze the action effectiveness by comparing screenshots.
    Return JSON format:
    {
        "execution_result": "success | partial_success | failure",
        "ui_changes": "Brief description",
        "goal_achievement": "Whether goal was achieved",
        "abnormal_states": "Any errors or unexpected behaviors",
        "reasoning": "Clear reasoning",
        "improvement_suggestions": "Suggestions if not successful",
        "confidence": 0.0-1.0
    }
    """
    
    // ============================================
    // 6. 调用模型分析
    // ============================================
    reflection_context = [
        system_message("You are a professional Android UI reflection module"),
        user_message(text=reflection_prompt + "\n\nBefore screenshot:", image=before_screenshot),
        user_message(text="After screenshot:", image=current_screenshot)
    ]
    
    TRY
        response = AWAIT model_client.request(reflection_context, mode="reflect")
        raw_output = response.raw_content
        
        // ============================================
        // 7. 提取和验证 JSON
        // ============================================
        TRY
            reflect_json = extract_json(raw_output)
        CATCH exception
            print("❌ Invalid JSON returned by reflect model")
            RETURN {
                action_successful: null,
                execution_result: "failure",
                confidence_score: 0.0,
                used_model_analysis: true,
                ...
            }
        END TRY
        
        // ============================================
        // 8. 规范化结果
        // ============================================
        execution_result = reflect_json.execution_result
        
        IF execution_result == "success" THEN
            action_successful = true
        ELSE IF execution_result == "failure" THEN
            action_successful = false
        ELSE
            action_successful = null  // partial_success
        END IF
        
        confidence = normalize_to_range(reflect_json.confidence, 0.0, 1.0)
        
        RETURN {
            action_successful: action_successful,
            execution_result: execution_result,
            interface_changes: reflect_json.ui_changes,
            expected_vs_actual: reflect_json.goal_achievement,
            abnormal_states: reflect_json.abnormal_states,
            improvement_suggestions: reflect_json.improvement_suggestions,
            confidence_score: confidence,
            reflection_reasoning: reflect_json.reasoning,
            used_model_analysis: true,
            elements_before: length(before_elements),
            elements_after: length(after_elements)
        }
        
    CATCH exception
        print("❌ Exception during reflection:", exception)
        RETURN {
            action_successful: null,
            execution_result: "failure",
            confidence_score: 0.0,
            reflection_reasoning: "Reflection error: " + exception,
            used_model_analysis: true,
            ...
        }
    END TRY
END FUNCTION
```

## 关键概念说明

### 1. **截图优化**
- 使用 `last_screenshot` 缓存机制避免重复截图
- 在每步结束时缓存截图供下一步使用
- 提高执行效率，减少设备通信开销

### 2. **Planning 机制**
- 智能决定何时执行 planning（首次、间隔步数等）
- 缓存 planning 结果避免重复计算
- 支持 skill 执行决策

### 3. **Skill 执行流程**
- Planning 决定是否使用 skill
- 执行 skill 并立即进行反思验证
- 失败时回退到原子动作

### 4. **Reflection（反思）机制**
- 对比执行前后的 UI 状态
- 快速路径：检测明显变化（原子动作）
- 模型分析：复杂情况调用 VLM 深度分析
- 结果反馈到上下文，指导后续决策

### 5. **错误处理**
- 错误预防：执行前检查潜在问题
- 错误记录：记录动作执行结果
- 错误模式分析：识别重复失败模式
- 改进建议：提供替代方案

### 6. **上下文管理**
- 结构化上下文存储任务、截图、屏幕信息
- 历史记录包含思考过程、动作和反思结果
- 动态清理减少内存占用

### 7. **工作流记录**
- 创建工作图节点表示 UI 状态
- 记录动作和转换关系
- 支持记忆系统的经验积累
