import json
import os
import yaml
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ActionStep:
    """表示一个动作步骤"""
    action_type: str
    description: str
    zone_path: Optional[str] = None
    element: Optional[str] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    dist: Optional[str] = None
    app: Optional[str] = None
    message: Optional[str] = None

@dataclass
class WorkflowPath:
    """表示一个工作流路径"""
    task: str
    tag: str
    steps: List[ActionStep]

class CodeGenerator:
    """代码生成器类，用于将内存数据上传到云端大模型并生成功能函数"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """初始化代码生成器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.api_base = self.config.get("OPENAI_API_BASE")
        self.api_key = self.config.get("OPENAI_API_KEY")
        self.model = self.config.get("OPENAI_API_MODEL")
        self.memory_dir = self.config.get("MEMORY_DIR", "./output/memory")
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def load_memory_data(self) -> Dict[str, Any]:
        """加载内存数据
        
        Returns:
            包含图形和工作流数据的字典
        """
        memory_data = {
            "graphs": {},
            "workflows": []
        }
        
        # 加载图形数据
        graph_dir = os.path.join(self.memory_dir, "graph")
        if os.path.exists(graph_dir):
            for filename in os.listdir(graph_dir):
                if filename.endswith('.json'):
                    app_name = filename[:-5]  # 移除.json后缀
                    try:
                        with open(os.path.join(graph_dir, filename), 'r', encoding='utf-8') as f:
                            memory_data["graphs"][app_name] = json.load(f)
                    except Exception as e:
                        logger.error(f"Failed to load graph {filename}: {e}")
        
        # 加载工作流数据
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                if filename.endswith('.json'):
                    try:
                        with open(os.path.join(workflow_dir, filename), 'r', encoding='utf-8') as f:
                            workflows = json.load(f)
                            if isinstance(workflows, list):
                                memory_data["workflows"].extend(workflows)
                            else:
                                memory_data["workflows"].append(workflows)
                    except Exception as e:
                        logger.error(f"Failed to load workflow {filename}: {e}")
        
        return memory_data
    
    def parse_workflows(self, memory_data: Dict[str, Any]) -> List[WorkflowPath]:
        """解析工作流数据为结构化格式
        
        Args:
            memory_data: 内存数据
            
        Returns:
            解析后的工作流路径列表
        """
        workflows = []
        
        for workflow in memory_data.get("workflows", []):
            steps = []
            
            for path_step in workflow.get("path", []):
                action = path_step.get("action", {})
                
                # 创建动作步骤
                step = ActionStep(
                    action_type=action.get("action_type", ""),
                    description=action.get("description", ""),
                    zone_path=action.get("zone_path")
                )
                
                # 根据动作类型设置特定参数
                if step.action_type == "Launch":
                    # 从描述中提取应用名称
                    desc = step.description.lower()
                    if "clock" in desc:
                        step.app = "Clock"
                    elif "camera" in desc:
                        step.app = "Camera"
                    elif "settings" in desc:
                        step.app = "Settings"
                    # 可以根据需要添加更多应用
                
                elif step.action_type == "Type":
                    # 从描述中提取文本内容
                    # 这里可能需要更复杂的解析逻辑
                    pass
                
                elif step.action_type == "Swipe":
                    # 从描述中提取滑动方向和距离
                    desc = step.description.lower()
                    if "up" in desc:
                        step.direction = "up"
                    elif "down" in desc:
                        step.direction = "down"
                    elif "left" in desc:
                        step.direction = "left"
                    elif "right" in desc:
                        step.direction = "right"
                    
                    if "short" in desc:
                        step.dist = "short"
                    elif "long" in desc:
                        step.dist = "long"
                    else:
                        step.dist = "medium"
                
                steps.append(step)
            
            workflow_path = WorkflowPath(
                task=workflow.get("task", ""),
                tag=workflow.get("tag", ""),
                steps=steps
            )
            workflows.append(workflow_path)
        
        return workflows
    
    def generate_function_code(self, workflow: WorkflowPath) -> str:
        """为单个工作流生成函数代码
        
        Args:
            workflow: 工作流路径
            
        Returns:
            生成的函数代码
        """
        # 生成函数名
        func_name = workflow.tag.replace(".", "_") if workflow.tag else "generated_function"
        
        # 生成函数代码
        code_lines = [
            f"def {func_name}():",
            f'    """',
            f'    {workflow.task}',
            f'    """',
        ]
        
        for i, step in enumerate(workflow.steps):
            if step.action_type == "Launch":
                code_lines.append(f'    do(action="Launch", app="{step.app}")')
            
            elif step.action_type == "Tap":
                # 从zone_path中提取元素标识符，这里简化处理
                element_id = f"element_{i+1}"
                code_lines.append(f'    do(action="Tap", element="{element_id}")  # {step.description}')
            
            elif step.action_type == "Type":
                text = step.text or "text_input"
                code_lines.append(f'    do(action="Type", text="{text}")  # {step.description}')
            
            elif step.action_type == "Swipe":
                element_id = f"element_{i+1}"
                direction = step.direction or "up"
                dist = step.dist or "medium"
                code_lines.append(f'    do(action="Swipe", element="{element_id}", direction="{direction}", dist="{dist}")  # {step.description}')
            
            elif step.action_type == "Long Press":
                element_id = f"element_{i+1}"
                code_lines.append(f'    do(action="Long Press", element="{element_id}")  # {step.description}')
            
            elif step.action_type == "Back":
                code_lines.append(f'    do(action="Back")  # {step.description}')
            
            elif step.action_type == "Finish":
                message = step.message or "Task completed"
                code_lines.append(f'    do(action="Finish", message="{message}")  # {step.description}')
        
        return "\n".join(code_lines)
    
    def call_llm_api(self, prompt: str) -> str:
        """调用云端大模型API
        
        Args:
            prompt: 输入提示
            
        Returns:
            模型响应
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.config.get("MAX_TOKENS", 1000),
            "temperature": self.config.get("TEMPERATURE", 0.0)
        }
        
        try:
            response = requests.post(self.api_base, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
        
        except Exception as e:
            logger.error(f"Failed to call LLM API: {e}")
            return ""
    
    def generate_enhanced_code(self, workflow: WorkflowPath, memory_data: Dict[str, Any]) -> str:
        """使用LLM生成增强的代码
        
        Args:
            workflow: 工作流路径
            memory_data: 内存数据
            
        Returns:
            LLM生成的增强代码
        """
        # 构建提示
        prompt = f"""
Based on the following mobile app automation workflow data, generate a Python function that can perform the described task.

Task: {workflow.task}
Tag: {workflow.tag}

Workflow Steps:
"""
        
        for i, step in enumerate(workflow.steps, 1):
            prompt += f"{i}. Action: {step.action_type}\n"
            prompt += f"   Description: {step.description}\n"
            if step.zone_path:
                prompt += f"   Zone Path: {step.zone_path}\n"
            prompt += "\n"
        
        prompt += """
Available Actions:
- Launch: Launch an app. Example: do(action="Launch", app="Clock")
- Tap: Tap on UI element. Example: do(action="Tap", element="R1")
- Type: Enter text. Example: do(action="Type", text="New York")
- Swipe: Swipe gesture. Example: do(action="Swipe", element="R1", direction="up", dist="medium")
- Long Press: Long press on element. Example: do(action="Long Press", element="R1")
- Back: Press back button. Example: do(action="Back")
- Finish: Complete task. Example: do(action="Finish", message="Task completed")

Please generate a clean, well-documented Python function that implements this workflow.
The function should:
1. Have a descriptive name based on the task
2. Include proper docstring
3. Use the correct action format
4. Include comments for clarity
5. Handle the workflow steps in the correct order

Return only the Python function code, no additional explanation.
"""
        
        return self.call_llm_api(prompt)
    
    def generate_all_functions(self, use_llm: bool = True) -> Dict[str, str]:
        """生成所有工作流的函数代码
        
        Args:
            use_llm: 是否使用LLM增强生成
            
        Returns:
            函数名到代码的映射
        """
        logger.info("Loading memory data...")
        memory_data = self.load_memory_data()
        
        logger.info("Parsing workflows...")
        workflows = self.parse_workflows(memory_data)
        
        generated_functions = {}
        
        for workflow in workflows:
            logger.info(f"Generating function for task: {workflow.task}")
            
            if use_llm and self.api_key and self.api_base:
                # 使用LLM生成增强代码
                code = self.generate_enhanced_code(workflow, memory_data)
                if not code:
                    # 如果LLM失败，回退到基础生成
                    code = self.generate_function_code(workflow)
            else:
                # 使用基础代码生成
                code = self.generate_function_code(workflow)
            
            func_name = workflow.tag.replace(".", "_") if workflow.tag else f"function_{len(generated_functions)}"
            generated_functions[func_name] = code
        
        return generated_functions
    
    def save_generated_code(self, functions: Dict[str, str], output_file: str = "generated_functions.py"):
        """保存生成的代码到文件
        
        Args:
            functions: 生成的函数代码
            output_file: 输出文件路径
        """
        output_path = os.path.join(os.path.dirname(__file__), output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('"""Generated functions from mobile app automation workflows"""\n\n')
            f.write('# Import required modules\n')
            f.write('# from your_automation_framework import do\n\n')
            
            for func_name, code in functions.items():
                f.write(f"{code}\n\n")
        
        logger.info(f"Generated code saved to: {output_path}")
    
    def run(self, use_llm: bool = True, output_file: str = "generated_functions.py"):
        """运行代码生成器
        
        Args:
            use_llm: 是否使用LLM增强生成
            output_file: 输出文件名
        """
        try:
            logger.info("Starting code generation...")
            
            # 生成所有函数
            functions = self.generate_all_functions(use_llm=use_llm)
            
            if not functions:
                logger.warning("No functions generated")
                return
            
            # 保存生成的代码
            self.save_generated_code(functions, output_file)
            
            logger.info(f"Successfully generated {len(functions)} functions")
            
            # 打印生成的函数名
            for func_name in functions.keys():
                logger.info(f"Generated function: {func_name}")
                
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            raise


def main():
    """主函数"""
    generator = CodeGenerator()
    
    # 运行代码生成器
    # use_llm=True 使用云端大模型增强生成
    # use_llm=False 使用基础模板生成
    generator.run(use_llm=True, output_file="generated_functions.py")


if __name__ == "__main__":
    main()
