import os
import re
import time
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from openai import OpenAI
from utils.config import load_config

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CodeGenerator:
    """代码生成器类，用于将workflow抽象为功能函数"""
    
    def __init__(self, memory_dir: str = "./output/memory", config_path: str = "config/config.yaml"):
        """初始化代码生成器
        
        Args:
            memory_dir: 内存数据目录路径
            config_path: 配置文件路径
        """
        self.memory_dir = memory_dir
        
        self.configs = load_config(config_path)
        self.api_base = self.configs.get("OPENAI_API_BASE")
        self.api_key = self.configs.get("OPENAI_API_KEY")
        self.model = self.configs.get("OPENAI_CODE_API_MODEL")
        
        # skill库文件路径
        self.skill_library_path = None
        
    def load_workflows(self, target_tag: str | None = None) -> List[Dict[str, Any]]:
        """加载指定tag的workflow
        
        Returns:
            workflow数据列表
        """
        workflows = []
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        
        if not os.path.exists(workflow_dir):
            logger.warning(f"Workflow directory not found: {workflow_dir}")
            return workflows
            
        for filename in os.listdir(workflow_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(workflow_dir, filename)
                # 从文件名提取tag（去掉.json扩展名）
                file_tag = os.path.splitext(filename)[0]
                file_tag = file_tag.replace("_", ".")
                print(f"File Tag: {file_tag}")

                if target_tag and file_tag != target_tag:  # 检查tag字段
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                        # 如果数据是列表，处理每个workflow
                        if isinstance(data, list):
                            for workflow in data:
                                # 使用文件中的tag字段，如果没有则使用文件名
                                workflow_tag = workflow.get("tag", file_tag)
                                if target_tag and workflow_tag != target_tag:
                                    continue
                                workflows.append(workflow)
                        else:
                            # 单个workflow对象
                            workflow_tag = data.get("tag", file_tag)
                            if target_tag and workflow_tag != target_tag:
                                continue
                            workflows.append(data)
                except Exception as e:
                    logger.error(f"Failed to load workflow {filename}: {e}")
        
        return workflows
    
    def get_nodes(self, workflows: List[Dict[str, Any]]) -> List[str]:
        nodes_id = []
        for workflow in workflows:
            for path in workflow["path"]:
                if path["from_node_id"] not in nodes_id:
                    nodes_id.append(path["from_node_id"])
                # 修复：收集每个path的to_node_id
                if path["to_node_id"] not in nodes_id:
                    nodes_id.append(path["to_node_id"])
        return nodes_id

    
    def load_graph(self, workflows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        graph = []
        graph_dir = os.path.join(self.memory_dir, "graph")

        if not os.path.exists(graph_dir):
            logger.warning(f"Graph directory not found: {graph_dir}")
            return graph
        
        nodes_id = self.get_nodes(workflows)
        for filename in os.listdir(graph_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(graph_dir, filename)

                with open(filepath, 'r', encoding='utf-8') as f:
                    graph_data = json.load(f)
            
            for node_id, node_data in graph_data["nodes"].items():
                if node_id in nodes_id:
                    graph.append(node_data)

        return graph
    
    def call_llm_api(self, prompt: str) -> str:
        """调用LLM API
        
        Args:
            prompt: 输入提示
            
        Returns:
            模型响应
        """
        if not self.api_key or not self.api_base:
            logger.error("LLM API not configured")
            return ""
            
        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
            )
            
            completion = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates Python functions from mobile app automation workflows."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            return completion.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to call LLM API: {e}")
            return ""
    
    def generate_function_with_llm(self, workflows: List[Dict[str, Any]], tag: str) -> str:
        """使用LLM基于同一tag下的多个workflows生成抽象功能函数
        
        Args:
            workflows: 同一tag下的workflow数据列表
            tag: workflow标签
            
        Returns:
            生成的函数代码
        """
        if not workflows:
            return ""
        
        # 生成函数名
        func_name = tag.replace(".", "_") if tag else "generated_function"
        
        # 构建所有workflows的描述
        workflows_desc = []
        for idx, workflow in enumerate(workflows, 1):
            task = workflow.get("task", "")
            path = workflow.get("path", [])
            
            # 构建动作序列描述
            actions_desc = []
            for i, step in enumerate(path, 1):
                action = step.get("action", {})
                action_type = action.get("action_type", "")
                description = action.get("description", "")
                zone_path = action.get("zone_path")
                
                # 提取元素ID
                element_id = extract_element_id(zone_path) if zone_path else None
                
                action_info = f"  {i}. {action_type}: {description}"
                if element_id:
                    action_info += f" (element: {element_id})"
                actions_desc.append(action_info)
            
            workflow_info = f"Workflow {idx}:\n  Task: {task}\n  Actions:\n" + "\n".join(actions_desc)
            workflows_desc.append(workflow_info)
        
        workflows_text = "\n\n".join(workflows_desc)
        
        prompt = f"""
Based on the following multiple mobile app automation workflows with the same tag, generate a complete Python function that abstracts these workflows into a single reusable function.

Tag: {tag}
Function Name: {func_name}

Multiple Workflows:
{workflows_text}

Requirements:
1. Analyze all workflows to identify common patterns and variations
2. Create a single abstracted function that can handle the different scenarios represented by these workflows
3. Identify what parameters should be configurable by users to support different use cases
4. Generate a complete Python function with appropriate parameters that can cover all the workflow variations
5. The function should return a list of action dictionaries in the format: {{"action": "ActionType", "element": "element_id", ...}}
6. Include proper docstring with parameter descriptions explaining how the function abstracts multiple workflows
7. For Launch actions, include "app" field
8. For Tap/Long Press actions, include "element" field  
9. For Type actions, include "element" and "text" fields
10. For Swipe actions, include "element", "direction", and "dist" fields
11. The "element" field must maintain the exact format extracted from zone_path (resource-id|content-desc|text) to ensure proper matching during execution
12. Always preserve the original element identifier format without modification to avoid matching failures
13. Add comments for each action step
14. Make the function parameters meaningful and user-friendly
15. Use conditional logic or parameters to handle variations between workflows
16. Consider making the function flexible enough to handle similar but slightly different workflows

Generate ONLY the Python function code, no markdown code blocks, no additional explanation.
Start directly with "def function_name(" and end with "return actions".
"""
        
        start_time = time.time()
        response = self.call_llm_api(prompt)
        end_time = time.time()
        logger.info(f"Inference Time taken: {end_time - start_time:.2f} seconds")

        # 清理响应，去除可能的代码标记
        if response:
            # 去除``python和```标记
            response = re.sub(r'^```python\s*\n?', '', response, flags=re.MULTILINE)
            response = re.sub(r'\n?```\s*$', '', response, flags=re.MULTILINE)
            response = response.strip()
        
        return response
    
    def extract_function_info(self, func_code: str, func_name: str, tag: str, workflows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """从生成的函数代码中提取函数信息
        
        Args:
            func_code: 函数代码
            func_name: 函数名
            tag: workflow标签
            workflows: 相关的workflow列表
            
        Returns:
            函数信息字典
        """
        # 提取函数签名和参数
        func_signature_match = re.search(r'def\s+' + re.escape(func_name) + r'\s*\(([^)]*)\)', func_code)
        parameters = []
        if func_signature_match:
            params_str = func_signature_match.group(1).strip()
            if params_str:
                # 简单解析参数（不处理复杂的类型注解）
                param_parts = [p.strip() for p in params_str.split(',')]
                for param in param_parts:
                    if '=' in param:
                        param_name = param.split('=')[0].strip()
                        default_value = param.split('=')[1].strip()
                        parameters.append({"name": param_name, "default": default_value})
                    else:
                        parameters.append({"name": param, "default": None})
        
        # 提取docstring
        docstring_match = re.search(r'"""(.*?)"""', func_code, re.DOTALL)
        description = ""
        if docstring_match:
            description = docstring_match.group(1).strip()
        
        # 统计workflow信息
        workflow_tasks = [w.get("task", "") for w in workflows]
        workflow_count = len(workflows)
        
        return {
            "function_name": func_name,
            "tag": tag,
            "description": description,
            "parameters": parameters,
            "workflow_count": workflow_count,
            "workflow_tasks": workflow_tasks,
            "created_time": datetime.now().isoformat(),
            "file_path": f"{func_name}.py"
        }
    
    def load_skill_library(self, library_path: str) -> Dict[str, Any]:
        """加载skill库
        
        Args:
            library_path: skill库文件路径
            
        Returns:
            skill库数据
        """
        if not os.path.exists(library_path):
            return {
                "version": "1.0",
                "created_time": datetime.now().isoformat(),
                "updated_time": datetime.now().isoformat(),
                "skills": {}
            }
        
        try:
            with open(library_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load skill library {library_path}: {e}")
            return {
                "version": "1.0",
                "created_time": datetime.now().isoformat(),
                "updated_time": datetime.now().isoformat(),
                "skills": {}
            }
    
    def save_skill_library(self, library_data: Dict[str, Any], library_path: str):
        """保存skill库
        
        Args:
            library_data: skill库数据
            library_path: skill库文件路径
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(library_path), exist_ok=True)
            
            # 更新时间戳
            library_data["updated_time"] = datetime.now().isoformat()
            
            with open(library_path, 'w', encoding='utf-8') as f:
                json.dump(library_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Skill library saved to: {library_path}")
        except Exception as e:
            logger.error(f"Failed to save skill library {library_path}: {e}")
    
    def update_skill_library(self, functions: Dict[str, str], workflows_by_tag: Dict[str, List[Dict[str, Any]]], output_path: str):
        """更新skill库
        
        Args:
            functions: 生成的函数代码
            workflows_by_tag: 按tag分组的workflows
            output_path: 输出路径
        """
        # 设置skill库路径
        self.skill_library_path = os.path.join(output_path, "skill_library.json")
        
        # 加载现有的skill库
        library_data = self.load_skill_library(self.skill_library_path)
        
        # 更新每个函数的信息
        for func_name, func_code in functions.items():
            # 找到对应的tag和workflows
            tag = None
            workflows = []
            for t, ws in workflows_by_tag.items():
                if t.replace(".", "_") == func_name:
                    tag = t
                    workflows = ws
                    break
            
            if tag and workflows:
                # 提取函数信息
                func_info = self.extract_function_info(func_code, func_name, tag, workflows)
                
                # 更新skill库
                library_data["skills"][func_name] = func_info
                
                logger.info(f"Added function '{func_name}' to skill library")
        
        # 保存更新后的skill库
        self.save_skill_library(library_data, self.skill_library_path)
        
        logger.info(f"Skill library updated with {len(functions)} functions")
    
    def list_available_tags(self) -> List[str]:
        """列出所有可用的workflow tags
        
        Returns:
            tag列表
        """
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        tags = []
        
        if not os.path.exists(workflow_dir):
            logger.warning(f"Workflow directory not found: {workflow_dir}")
            return tags
            
        for filename in os.listdir(workflow_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(workflow_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        # 如果数据是列表，处理每个workflow
                        if isinstance(data, list):
                            for workflow in data:
                                tag = workflow.get("tag", "")
                                if tag and tag not in tags:
                                    tags.append(tag)
                        else:
                            # 单个workflow对象
                            tag = data.get("tag", "")
                            if tag and tag not in tags:
                                tags.append(tag)
                except Exception as e:
                    logger.error(f"Failed to load workflow {filename}: {e}")
        
        return sorted(tags)
    
    def query_skills(self, keyword: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询skill库中的函数
        
        Args:
            keyword: 关键词搜索
            tag: 按tag过滤
            
        Returns:
            匹配的函数信息列表
        """
        if not self.skill_library_path or not os.path.exists(self.skill_library_path):
            logger.warning("Skill library not found")
            return []
        
        library_data = self.load_skill_library(self.skill_library_path)
        skills = library_data.get("skills", {})
        
        results = []
        for func_name, func_info in skills.items():
            # 按tag过滤
            if tag and func_info.get("tag") != tag:
                continue
            
            # 按关键词搜索
            if keyword:
                search_text = f"{func_name} {func_info.get('description', '')} {func_info.get('tag', '')}"
                if keyword.lower() not in search_text.lower():
                    continue
            
            results.append(func_info)
        
        return results
    
    def generate_all_functions(self, target_tag: str | None = None) -> tuple[Dict[str, str], Dict[str, List[Dict[str, Any]]]]:
        """生成所有workflow的函数代码
        
        Args:
            target_tag: 目标tag，如果指定则只处理该tag的workflows
            
        Returns:
            (函数名到代码的映射, 按tag分组的workflows)
        """
        if target_tag:
            logger.info(f"Loading workflows for tag: {target_tag}")
        else:
            logger.info("Loading workflows from all files...")
        workflows = self.load_workflows(target_tag=target_tag)
        
        if not workflows:
            logger.warning("No workflows found")
            return {}, {}
        
        # 按tag分组workflows
        workflows_by_tag = {}
        for workflow in workflows:
            tag = workflow.get("tag", "")
            if not tag:
                logger.warning("Workflow without tag found, skipping")
                continue
                
            if tag not in workflows_by_tag:
                workflows_by_tag[tag] = []
            workflows_by_tag[tag].append(workflow)
        
        logger.info(f"Found {len(workflows_by_tag)} unique tags")
        for tag, tag_workflows in workflows_by_tag.items():
            logger.info(f"Tag '{tag}': {len(tag_workflows)} workflows")
        
        generated_functions = {}
        
        # 为每个tag生成抽象函数
        for tag, tag_workflows in workflows_by_tag.items():
            logger.info(f"Processing tag: {tag} with {len(tag_workflows)} workflows")
            
            try:
                func_code = self.generate_function_with_llm(tag_workflows, tag)
                if func_code:
                    # 提取函数名
                    func_name_match = re.search(r'def\s+(\w+)\s*\(', func_code)
                    if func_name_match:
                        func_name = func_name_match.group(1)
                        generated_functions[func_name] = func_code
                        logger.info(f"Generated function: {func_name} (based on {len(tag_workflows)} workflows)")
                    else:
                        logger.warning(f"Could not extract function name from generated code for tag {tag}")
                else:
                    logger.error(f"Failed to generate function code for tag {tag}")
            except Exception as e:
                logger.error(f"Failed to generate function for tag {tag}: {e}")
        
        return generated_functions, workflows_by_tag
    
    def save_generated_code(self, functions: Dict[str, str], output_path: str):
        """保存生成的代码到文件
        
        Args:
            functions: 生成的函数代码
            output_path: 输出文件的目录路径
        """
        
        # 确保目录存在
        os.makedirs(output_path, exist_ok=True)

        for func_name, code in functions.items():
            file_path = os.path.join(output_path, f"{func_name}.py")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
        
        logger.info(f"Generated code saved to: {output_path}")
    
    def run(self, output_path: str, target_tag: str | None = None):
        """运行代码生成器
        
        Args:
            output_path: 输出文件的目录路径
            target_tag: 目标tag，如果指定则只处理该tag的workflows
        """
        try:
            if target_tag:
                logger.info(f"Starting code generation for tag: {target_tag}")
            else:
                logger.info("Starting code generation for all tags...")
            
            # 生成所有函数
            functions, workflows_by_tag = self.generate_all_functions(target_tag=target_tag)
            
            if not functions:
                logger.warning("No functions generated")
                return
            
            # 保存生成的代码
            self.save_generated_code(functions, output_path)
            
            # 更新skill库
            self.update_skill_library(functions, workflows_by_tag, output_path)
            
            logger.info(f"Successfully generated {len(functions)} functions")
            
            # 打印生成的函数名
            for func_name in functions.keys():
                logger.info(f"Generated function: {func_name}")
                
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            raise


def extract_element_id(zone_path: str) -> str:
    """从zone_path提取简化的元素ID
    
    Args:
        zone_path: UI元素路径
        
    Returns:
        简化的元素ID
    """
    if not zone_path:
        return "unknown_element"
        
    # 优先提取最后一个resource-id（通常是最具体的）
    resource_ids = re.findall(r'@resource-id="([^"]+)"', zone_path)
    if resource_ids:
        element_id = resource_ids[-1]  # 取最后一个，通常是最具体的
    
    # 提取content-desc
    content_desc = re.findall(r'@content-desc="([^"]+)"', zone_path)
    if content_desc:
        element_id += "|" + content_desc[-1]
    
    # 提取text
    text_match = re.findall(r'@text="([^"]+)"', zone_path)
    if text_match:
        element_id += "|" + text_match[-1]

    # logger.info(f"element_id: {element_id}")

    if element_id:
        return element_id
    else:
        return "unknown_element"

def main():
    """主函数"""
    import sys
    
    start_time = time.time()
    generator = CodeGenerator()
    output_path = os.path.join(os.path.dirname(__file__), "skills")
    
    # 检查命令行参数，支持指定tag
    target_tag = None
    if len(sys.argv) > 1 and sys.argv[1] != "demo" and sys.argv[1] != "list":
        target_tag = sys.argv[1]
        logger.info(f"Processing specific tag: {target_tag}")
    
    generator.run(output_path=output_path, target_tag=target_tag)
    end_time = time.time()
    logger.info(f"Code generation completed in {end_time - start_time:.2f} seconds")


def demo_skill_library():
    """演示skill库的使用"""
    generator = CodeGenerator()
    output_path = os.path.join(os.path.dirname(__file__), "skills")
    
    # 设置skill库路径
    generator.skill_library_path = os.path.join(output_path, "skill_library.json")
    
    # 查询所有技能
    logger.info("=== All Skills ===")
    all_skills = generator.query_skills()
    for skill in all_skills:
        logger.info(f"Function: {skill['function_name']}")
        logger.info(f"Tag: {skill['tag']}")
        logger.info(f"Description: {skill['description'][:100]}...")
        logger.info(f"Parameters: {[p['name'] for p in skill['parameters']]}")
        logger.info(f"Workflow Count: {skill['workflow_count']}")
        logger.info("---")
    
    # 按关键词搜索
    logger.info("=== Search by keyword 'alarm' ===")
    alarm_skills = generator.query_skills(keyword="alarm")
    for skill in alarm_skills:
        logger.info(f"Found: {skill['function_name']} - {skill['tag']}")
    
    # 按tag搜索
    logger.info("=== Search by tag 'alarm.create' ===")
    tag_skills = generator.query_skills(tag="alarm.create")
    for skill in tag_skills:
        logger.info(f"Found: {skill['function_name']} - {skill['description'][:50]}...")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo_skill_library()
    else:
        main()
