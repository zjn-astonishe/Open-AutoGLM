"""Model client for AI inference using OpenAI-compatible API."""

import re
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from openai import OpenAI

from phone_agent.config.i18n import get_message
from utils.util import print_with_color


@dataclass
class ModelConfig:
    """Configuration for the AI model."""

    base_url: str = "http://localhost:8001/v1"
    api_key: str = "qwerasdfzxcv123"
    model_name: str = "autoglm-phone-9b-multilingual"
    max_tokens: int = 3000    # TODO: max_tokens may too long.
    # max_tokens: int = 1024
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)
    lang: str = "en"  # Language for UI messages: 'cn' or 'en'


@dataclass
class ModelResponse:
    """Response from the AI model."""

    thinking: str
    action: Dict[str, str]
    # predict: str
    raw_content: str
    # Performance metrics
    time_to_first_token: float | None = None  # Time to first token (seconds)
    time_to_thinking_end: float | None = None  # Time to thinking end (seconds)
    total_time: float | None = None  # Total inference time (seconds)


class ModelClient:
    """
    Client for interacting with OpenAI-compatible vision-language models.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def request(self, messages: list[dict[str, Any]], mode: str = "action") -> ModelResponse:
        """
        Send a request to the model.

        Args:
            messages: List of message dictionaries in OpenAI format.
            mode: Request mode - "action" for normal action execution, "reflect" for reflection analysis.

        Returns:
            ModelResponse containing thinking and action.

        Raises:
            ValueError: If the response cannot be parsed.
        """
        # Start timing
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None

        stream = self.client.chat.completions.create(
            messages=messages,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,
            stream=True,
        )

        raw_content = ""
        buffer = ""  # Buffer to hold content that might be part of a marker
        # action_markers = ["finish(message=", "do(action="]
        action_marker = "<answer>"
        in_action_phase = False  # Track if we've entered the action phase
        first_token_received = False

        for chunk in stream:
            if len(chunk.choices) == 0:
                continue
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                raw_content += content

                # Record time to first token
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                if in_action_phase:
                    # Already in action phase, just accumulate content without printing
                    continue

                buffer += content

                # Check if any marker is fully present in buffer
                marker_found = False

                if action_marker in buffer:
                    # Marker found, print everything before it
                    thinking_part = buffer.split(action_marker, 1)[0]
                    print(thinking_part, end="", flush=True)
                    print()  # Print newline after thinking is complete
                    in_action_phase = True
                    marker_found = True

                    # Record time to thinking end
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time

                if marker_found:
                    continue  # Continue to collect remaining content

                # Check if buffer ends with a prefix of any marker
                # If so, don't print yet (wait for more content)
                is_potential_marker = False

                if action_marker:
                    for i in range(1, len(action_marker)):
                        if buffer.endswith(action_marker[:i]):
                            is_potential_marker = True
                            break

                if not is_potential_marker:
                    # Safe to print the buffer
                    print(buffer, end="", flush=True)
                    buffer = ""

        # Calculate total time
        total_time = time.time() - start_time

        # print(f"🤖 Raw_content: {raw_content}")
        
        # Parse response based on mode
        if mode == "reflect":
            thinking, action = self._parse_reflect_response(raw_content)
        elif mode == "action":
            # Parse thinking and action from response for normal action mode
            # thinking, action = self._parse_response(raw_content)
            # thinking, answer, predict = self._parser_response_with_predict(raw_content)
            thinking, answer = self._parser_response_with_answer(raw_content)
            action = self._parse_action(answer)

        # Print performance metrics
        lang = self.config.lang
        print()
        print("=" * 50)
        print(f"⏱️  {get_message('performance_metrics', lang)}:")
        print("-" * 50)
        if time_to_first_token is not None:
            print(
                f"{get_message('time_to_first_token', lang)}: {time_to_first_token:.3f}s"
            )
        if time_to_thinking_end is not None:
            print(
                f"{get_message('time_to_thinking_end', lang)}:        {time_to_thinking_end:.3f}s"
            )
        print(
            f"{get_message('total_inference_time', lang)}:          {total_time:.3f}s"
        )
        print("=" * 50)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        Parse the model response into thinking and action parts.

        Parsing rules:
        1. If content contains 'finish(message=', everything before is thinking,
           everything from 'finish(message=' onwards is action.
        2. If rule 1 doesn't apply but content contains 'do(action=',
           everything before is thinking, everything from 'do(action=' onwards is action.
        3. Fallback: If content contains '<answer>', use legacy parsing with XML tags.
        4. Otherwise, return empty thinking and full content as action.

        Args:
            content: Raw response content.

        Returns:
            Tuple of (thinking, action).
        """
        # Rule 1: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            # print("+" * 50)
            # print(f"🤖 Action: {action}\n Thinking: {thinking}")
            # print("+" * 50)
            return thinking, action

        # Rule 2: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            # action = "do(action=" + parts[1]
            # print("+" * 50)
            # print(f"🤖 Action: {action}\n Thinking: {thinking}")
            # print("+" * 50)
            return thinking, action

        # Rule 3: Fallback to legacy XML tag parsing
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            # print("+" * 50)
            # print(f"🤖 Action: {action}\n Thinking: {thinking}")
            # print("+" * 50)
            return thinking, action

        # Rule 4: No markers found, return content as action
        return "", content
    
    def _parser_response_with_predict(self, content: str) -> tuple[str, str, str]:
        """
        Parse the model response into thinking, action parts and predict.

        Args:
            content: Raw response content.
        
        Returns:
            Tuple of (thinking, action, predict).
        """

        thinking = re.findall(r"<observe>(.*?)</observe>", content, re.DOTALL)[0]
        answer = re.findall(r"<answer>(.*?)</answer>", content, re.DOTALL)[0]
        predict = re.findall(r"<predict>(.*?)</predict>", content, re.DOTALL)[0]

        # print_with_color(f"🤖 Thinking: {thinking}", "yellow")
        # print_with_color(f"🤖 Action: {answer}", "green")
        # print_with_color(f"🤖 Predict: {predict}", "cyan")

        return thinking, answer, predict
    
    def _parser_response_with_answer(self, content: str) -> tuple[str, str]:
        """
        Parse the model response into thinking and answer parts.

        Args:
            content: Raw response content.
        
        Returns:
            Tuple of (thinking, answer).
        """

        thinking = re.findall(r"<observe>(.*?)</observe>", content, re.DOTALL)[0]
        answer = re.findall(r"<answer>(.*?)</answer>", content, re.DOTALL)[0]

        return thinking, answer

    def _parse_action(self, content: str) -> Dict[str, str]:
        """
        Parse the model response's answer into action description and action parts.

        Parsing rules:
        1. If content contains 'finish(message=', everything before is action description,
           everything from 'finish(message=' onwards is action.
        2. If rule 1 doesn't apply but content contains 'do(action=',
           everything before is action description, everything from 'do(action=' onwards is action.
        3. Otherwise, return empty action description and full content as action.

        Args:
            content: Raw response content.

        Returns:
            Dict[str, str] of (action description, action).
        """
        action_dict = {}

        # Rule 1: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            action_desc = parts[0].strip()
            action = "finish(message=" + parts[1]
            # print("+" * 50)
            # print(f"🤖 Action: {action}\n Description: {action_desc}")
            # print("+" * 50)
            action_dict[action_desc] = action
            return action_dict

        # Rule 2: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            action_desc = parts[0].strip()
            action = "do(action=" + parts[1]
            # print("+" * 50)
            # print(f"🤖 Action: {action}\n Description: {action_desc}")
            # print("+" * 50)
            action_dict[action_desc] = action
            return action_dict

        # Rule 4: No markers found, return content as action
        action_desc = ""
        action_dict[action_desc] = content
        return action_dict

    def _parse_reflect_response(self, content: str) -> tuple[str, Dict[str, str]]:
        """
        Parse the model response for reflection analysis.
        
        For reflect mode, we expect a simple text response analyzing the action success.
        We don't need complex action parsing, just the analysis result.

        Args:
            content: Raw response content.

        Returns:
            Tuple of (thinking, action_dict).
        """
        # For reflect mode, the entire content is the analysis
        # We can try to extract structured information if available
        
        # Try to extract structured reflection if available
        success_patterns = [
            r"success[:\s]*([^.\n]+)",
            r"successful[:\s]*([^.\n]+)", 
            r"成功[:\s]*([^.\n]+)",
        ]
        
        confidence_patterns = [
            r"confidence[:\s]*([0-9.]+)",
            r"置信度[:\s]*([0-9.]+)",
        ]
        
        # Extract success status
        success_info = "unknown"
        for pattern in success_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                success_info = match.group(1).strip()
                break
        
        # Extract confidence if available
        confidence = "0.5"  # default
        for pattern in confidence_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                confidence = match.group(1).strip()
                break
        
        # Create action dict for reflect response
        action_dict = {
            "reflection_analysis": content.strip(),
            "success_status": success_info,
            "confidence": confidence
        }
        
        return "", action_dict

class MessageBuilder:
    """Helper class for building conversation messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """Create a system message."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Create a user message with optional image.

        Args:
            text: Text content.
            image_base64: Optional base64-encoded image.

        Returns:
            Message dictionary.
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """Create an assistant message."""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        Remove image content from a message to save context space.

        Args:
            message: Message dictionary.

        Returns:
            Message with images removed.
        """

        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:
        """
        Build screen info string for the model.

        Args:
            current_app: Current app name.
            **extra_info: Additional info to include.

        Returns:
            JSON string with screen info.
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)
