"""
代码生成器使用示例
演示如何使用 CodeGenerator 类来生成功能函数
"""

from code_generator import CodeGenerator
import logging

# 设置日志级别
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def example_basic_generation():
    """基础代码生成示例（不使用LLM）"""
    print("=" * 50)
    print("基础代码生成示例")
    print("=" * 50)
    
    # 创建代码生成器实例
    generator = CodeGenerator()
    
    # 使用基础模板生成代码（不调用LLM）
    generator.run(use_llm=False, output_file="basic_generated_functions.py")
    
    print("基础代码生成完成！")

def example_llm_enhanced_generation():
    """LLM增强代码生成示例"""
    print("=" * 50)
    print("LLM增强代码生成示例")
    print("=" * 50)
    
    # 创建代码生成器实例
    generator = CodeGenerator()
    
    # 使用LLM增强生成代码
    generator.run(use_llm=True, output_file="enhanced_generated_functions.py")
    
    print("LLM增强代码生成完成！")

def example_custom_config():
    """使用自定义配置的示例"""
    print("=" * 50)
    print("自定义配置示例")
    print("=" * 50)
    
    # 使用自定义配置文件路径
    generator = CodeGenerator(config_path="config/config.yaml")
    
    # 检查配置是否加载成功
    if generator.api_key:
        print(f"API配置已加载，模型: {generator.model}")
        generator.run(use_llm=True, output_file="custom_generated_functions.py")
    else:
        print("API配置未找到，使用基础生成")
        generator.run(use_llm=False, output_file="custom_generated_functions.py")

def example_step_by_step():
    """分步骤演示代码生成过程"""
    print("=" * 50)
    print("分步骤代码生成演示")
    print("=" * 50)
    
    generator = CodeGenerator()
    
    # 步骤1：加载内存数据
    print("步骤1：加载内存数据...")
    memory_data = generator.load_memory_data()
    print(f"加载了 {len(memory_data['graphs'])} 个应用图形")
    print(f"加载了 {len(memory_data['workflows'])} 个工作流")
    
    # 步骤2：解析工作流
    print("\n步骤2：解析工作流...")
    workflows = generator.parse_workflows(memory_data)
    print(f"解析了 {len(workflows)} 个工作流路径")
    
    # 步骤3：生成函数代码
    print("\n步骤3：生成函数代码...")
    functions = {}
    
    for i, workflow in enumerate(workflows):
        print(f"  生成函数 {i+1}: {workflow.task}")
        
        # 生成基础代码
        basic_code = generator.generate_function_code(workflow)
        func_name = workflow.tag.replace(".", "_") if workflow.tag else f"function_{i}"
        functions[f"{func_name}_basic"] = basic_code
        
        # 如果配置了API，也生成LLM增强代码
        if generator.api_key and generator.api_base:
            try:
                enhanced_code = generator.generate_enhanced_code(workflow, memory_data)
                if enhanced_code:
                    functions[f"{func_name}_enhanced"] = enhanced_code
            except Exception as e:
                print(f"    LLM生成失败: {e}")
    
    # 步骤4：保存生成的代码
    print(f"\n步骤4：保存 {len(functions)} 个生成的函数...")
    generator.save_generated_code(functions, "step_by_step_generated_functions.py")
    
    print("分步骤生成完成！")

def example_analyze_memory_data():
    """分析内存数据的示例"""
    print("=" * 50)
    print("内存数据分析示例")
    print("=" * 50)
    
    generator = CodeGenerator()
    memory_data = generator.load_memory_data()
    
    # 分析图形数据
    print("应用图形分析:")
    for app_name, graph_data in memory_data['graphs'].items():
        nodes_count = len(graph_data.get('nodes', {}))
        print(f"  {app_name}: {nodes_count} 个节点")
        
        # 分析节点中的任务
        tasks = set()
        for node in graph_data.get('nodes', {}).values():
            for task in node.get('tasks', []):
                tasks.add(task)
        
        if tasks:
            print(f"    任务: {list(tasks)[:3]}...")  # 显示前3个任务
    
    # 分析工作流数据
    print(f"\n工作流分析:")
    workflows = generator.parse_workflows(memory_data)
    
    for workflow in workflows:
        print(f"  任务: {workflow.task}")
        print(f"  标签: {workflow.tag}")
        print(f"  步骤数: {len(workflow.steps)}")
        
        # 分析动作类型
        action_types = [step.action_type for step in workflow.steps]
        action_counts = {}
        for action in action_types:
            action_counts[action] = action_counts.get(action, 0) + 1
        
        print(f"  动作分布: {action_counts}")
        print()

def main():
    """主函数 - 运行所有示例"""
    print("代码生成器使用示例")
    print("=" * 60)
    
    try:
        # 1. 分析内存数据
        example_analyze_memory_data()
        
        # 2. 基础代码生成
        example_basic_generation()
        
        # 3. 分步骤演示
        example_step_by_step()
        
        # 4. 自定义配置
        example_custom_config()
        
        # 5. LLM增强生成（如果配置了API）
        generator = CodeGenerator()
        if generator.api_key and generator.api_base:
            example_llm_enhanced_generation()
        else:
            print("=" * 50)
            print("跳过LLM增强生成（未配置API）")
            print("=" * 50)
        
        print("\n所有示例运行完成！")
        print("生成的文件:")
        print("- basic_generated_functions.py")
        print("- step_by_step_generated_functions.py") 
        print("- custom_generated_functions.py")
        if generator.api_key and generator.api_base:
            print("- enhanced_generated_functions.py")
        
    except Exception as e:
        print(f"运行示例时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
