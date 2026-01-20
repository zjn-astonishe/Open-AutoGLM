# Copyright 2025 The android_world Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Controller for Android that adds UI tree information to the observation."""

import contextlib
import enum
import os
import time
from typing import Any
from typing import cast
from typing import Optional
from absl import logging
from android_env import env_interface
from android_env import loader
from android_env.components import config_classes
from android_env.proto.a11y import android_accessibility_forest_pb2
from android_env.wrappers import a11y_grpc_wrapper
from android_env.wrappers import base_wrapper
from android_world.env import adb_utils
from android_world.env import representation_utils
from android_world.utils import file_utils
import dm_env


def _has_wrapper(
    env: env_interface.AndroidEnvInterface,
    target_wrapper: Any,
) -> bool:
  """Checks recursively if an environment object has a certain wrapper.

  Args:
    env: The environment object potentially wrapped.
    target_wrapper: The wrapper type to search for.

  Returns:
    True if the target_wrapper is found, otherwise False.
  """
  if isinstance(env, target_wrapper):
    return True
  elif hasattr(env, '_env'):
    return _has_wrapper(env._env, target_wrapper)  # pylint: disable=protected-access
  else:
    return False


def get_a11y_tree(
    env: env_interface.AndroidEnvInterface,
    max_retries: int = 5,
    sleep_duration: float = 1.0,
) -> android_accessibility_forest_pb2.AndroidAccessibilityForest:
  """Gets a11y tree.

  Args:
    env: AndroidEnv.
    max_retries: Maximum number of retries to get a11y tree.
    sleep_duration: Time to sleep between each retry in seconds.

  Returns:
    A11y tree.

  Raises:
    RuntimeError: If the a11y tree was not able to be retrieved.
  """
  # print("DEBUG: get_a11y_tree called")
  
  if not _has_wrapper(env, a11y_grpc_wrapper.A11yGrpcWrapper):
    # print("DEBUG: No A11yGrpcWrapper found")
    raise ValueError(
        'Must use a11y_grpc_wrapper.A11yGrpcWrapper to get the a11y tree.'
    )
  
  # print("DEBUG: A11yGrpcWrapper found")
  env = cast(a11y_grpc_wrapper.A11yGrpcWrapper, env)
  
  if adb_utils.retry(3)(adb_utils.check_airplane_mode)(env):
    logging.warning(
        'Airplane mode is on -- cannot retrieve a11y tree via gRPC. Turning'
        ' it off...'
    )
    logging.info('Enabling networking...')
    env.attempt_enable_networking()
    time.sleep(1.0)

  forest: Optional[
      android_accessibility_forest_pb2.AndroidAccessibilityForest
  ] = None
  
  for attempt in range(max_retries):
    # print(f"DEBUG: Attempt {attempt + 1}/{max_retries} to get a11y tree")
    try:
      extras = env.accumulate_new_extras()
      # print(f"DEBUG: Got extras: {list(extras.keys())}")
      
      if 'accessibility_tree' in extras:
        accessibility_trees = extras['accessibility_tree']
        # print(f"DEBUG: Found {len(accessibility_trees)} accessibility trees")
        if len(accessibility_trees) > 0:
          forest = accessibility_trees[-1]
          # print(f"DEBUG: Using latest tree with {len(forest.windows)} windows")
          
          # 详细分析为什么forest为空
          if len(forest.windows) == 0:
            # print("DEBUG: *** FOREST IS EMPTY - ANALYZING REASONS ***")
            # print(f"DEBUG: Forest object: {forest}")
            
            # 检查extras中的其他信息
            # print(f"DEBUG: All extras keys: {list(extras.keys())}")
            if 'full_event' in extras:
              full_events = extras['full_event']
              # print(f"DEBUG: Found {len(full_events)} full_events")
              for i, event in enumerate(full_events[:2]):  # 只显示前2个
                event_str = str(event)
                if len(event_str) > 100:
                  event_str = event_str[:100] + "..."
                # print(f"DEBUG: Event {i}: {event_str}")
            
            # print("DEBUG: Possible causes: A11y forwarder app crash, permissions, or device state")
          
          return forest
        else:
          ...
          # print("DEBUG: accessibility_tree list is empty")
      else:
        ...
        # print("DEBUG: No 'accessibility_tree' key in extras")
        
    except KeyError as e:
      # print(f"DEBUG: KeyError in attempt {attempt + 1}: {e}")
      logging.warning('Could not get a11y tree, retrying.')
    except Exception as e:
      # print(f"DEBUG: Unexpected exception in attempt {attempt + 1}: {e}")
      ...
      
    if attempt < max_retries - 1:  # Don't sleep on the last attempt
      # print(f"DEBUG: Sleeping {sleep_duration}s before retry")
      time.sleep(sleep_duration)

  # print("DEBUG: All attempts failed")
  if forest is None:
    raise RuntimeError('Could not get a11y tree.')
  return forest


_TASK_PATH = file_utils.convert_to_posix_path(
    file_utils.get_local_tmp_directory(), 'default.textproto'
)
DEFAULT_ADB_PATH = '~/Android/Sdk/platform-tools/adb'


# UI tree-specific keys that are added to observations:

# The forest is essentially a comprehensive snapshot of all user interface
# elements currently displayed on an Android device's screen. Each 'tree' in
# this 'forest' represents the accessibility details of a different window or
# screen section, providing structured information. The tree's origin is from
# the AccessibilityService. Please see the following for more detail:
# https://developer.android.com/reference/android/accessibilityservice/AccessibilityService

OBSERVATION_KEY_FOREST = 'forest'
# UI elements are specific nodes extracted from forest. See
# representation_utils.forest_to_ui_elements for details.
OBSERVATION_KEY_UI_ELEMENTS = 'ui_elements'


class A11yMethod(enum.Enum):
  """Method to get a11y tree."""

  # Custom gRPC wrapper that uses a11y forwarder app.
  A11Y_FORWARDER_APP = 'a11y_forwarder_app'

  # From `uiautomator dump``.
  UIAUTOMATOR = 'uiautomator'

  # No A11y tree retrieval
  NONE = 'none'


def apply_a11y_forwarder_app_wrapper(
    env: env_interface.AndroidEnvInterface, install_a11y_forwarding_app: bool
) -> env_interface.AndroidEnvInterface:
  return a11y_grpc_wrapper.A11yGrpcWrapper(
      env,
      install_a11y_forwarding=install_a11y_forwarding_app,
      start_a11y_service=True,
      enable_a11y_tree_info=True,
      latest_a11y_info_only=True,
  )


class AndroidWorldController(base_wrapper.BaseWrapper):
  """Controller for an Android instance that adds accessibility tree data.

  The Accessibility Tree in Android is a tree-based structure, originally for
  for assisting accessibility services. It provides information about UI
  elements (like text, buttons, and images) in a hierarchical format. The tree
  includes details such as the properties and actions available for each
  element.
  """

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      a11y_method: A11yMethod = A11yMethod.A11Y_FORWARDER_APP,
      install_a11y_forwarding_app: bool = False,
  ):
    self._original_env = env
    if a11y_method == A11yMethod.A11Y_FORWARDER_APP:
      self._env = apply_a11y_forwarder_app_wrapper(
          env, install_a11y_forwarding_app
      )
      self._env.reset()  # Initializes required server services in a11y wrapper.
    else:
      self._env = env
    self._a11y_method = a11y_method

  @property
  def device_screen_size(self) -> tuple[int, int]:
    """Returns the physical screen size of the device: (width, height)."""
    return adb_utils.get_screen_size(self._env)

  @property
  def logical_screen_size(self) -> tuple[int, int]:
    """Returns the logical screen size of the device.

    This will be different with the physical size if orientation or resolution
    is changed.
    """
    return adb_utils.get_logical_screen_size(self._env)

  @property
  def env(self) -> env_interface.AndroidEnvInterface:
    return self._env

  def refresh_env(self):
    # pylint: disable=protected-access
    # pytype: disable=attribute-error
    # Reconnect to emulator and reload a11y wrapper in case we lose connection.
    self._env = get_controller(
        console_port=self.env._coordinator._simulator._config.emulator_launcher.emulator_console_port,
        adb_path=self.env._coordinator._simulator._config.adb_controller.adb_path,
        grpc_port=self.env._coordinator._simulator._config.emulator_launcher.grpc_port,
    ).env
    # pylint: enable=protected-access
    # pytype: enable=attribute-error

  def _get_a11y_forest(
      self,
  ) -> android_accessibility_forest_pb2.AndroidAccessibilityForest:
    # print("DEBUG: _get_a11y_forest called")
    try:
      forest = get_a11y_tree(self._env)
      # print(f"DEBUG: get_a11y_tree returned forest with {len(forest.windows)} windows")
      return forest
    except Exception as e:
      # print(f"DEBUG: Exception in _get_a11y_forest: {e}")
      raise

  def get_a11y_forest(
      self,
  ) -> android_accessibility_forest_pb2.AndroidAccessibilityForest:
    """Returns the most recent a11y forest from the device."""
    try:
      return self._get_a11y_forest()
    except RuntimeError:
      print(
          'Could not get a11y tree. Reconnecting to Android, reinitializing'
          ' AndroidEnv, and restarting a11y forwarding.'
      )
      self.refresh_env()
      return self._get_a11y_forest()

  def get_ui_elements(self) -> list[representation_utils.UIElement]:
    """Returns the most recent UI elements from the device."""
    if self._a11y_method == A11yMethod.A11Y_FORWARDER_APP:
      try:
        forest = self.get_a11y_forest()
        ui_elements = representation_utils.forest_to_ui_elements(
            forest,
            exclude_invisible_elements=True,
        )
        
        # 如果A11y方法返回空结果，尝试备用方法
        if len(ui_elements) == 0:
          try:
            xml_dump = adb_utils.uiautomator_dump(self._env)
            ui_elements = representation_utils.xml_dump_to_ui_elements(xml_dump)
          except Exception as e:
            # Uiautomator备用方法失败，但这是可以接受的
            # 系统会继续使用空的UI元素列表
            logging.debug(f"Uiautomator fallback failed: {e}")
        return ui_elements
      except Exception as e:
        # print(f"DEBUG: A11y method failed: {e}, falling back to uiautomator")
        return representation_utils.xml_dump_to_ui_elements(
            adb_utils.uiautomator_dump(self._env)
        )
    elif self._a11y_method == A11yMethod.UIAUTOMATOR:
      return representation_utils.xml_dump_to_ui_elements(
          adb_utils.uiautomator_dump(self._env)
      )
    else:
      return []

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    """Adds a11y tree info to the observation."""
    # print(f"DEBUG: AndroidWorldController._process_timestep called")
    # print(f"DEBUG: a11y_method = {self._a11y_method}")
    
    if self._a11y_method == A11yMethod.A11Y_FORWARDER_APP:
      # print("DEBUG: Using A11Y_FORWARDER_APP method")
      try:
        forest = self.get_a11y_forest()
        # print(f"DEBUG: Got forest: {forest}")
        # print(f"DEBUG: Forest type: {type(forest)}")
        if forest:
          # print(f"DEBUG: Forest has {len(forest.windows)} windows")
          # for i, window in enumerate(forest.windows):
            # print(f"DEBUG: Window {i} has {len(window.tree.nodes)} nodes")
          ...
        
        # 使用get_ui_elements方法，它包含备用机制
        ui_elements = self.get_ui_elements()
        # print(f"DEBUG: get_ui_elements returned {len(ui_elements)} UI elements")
      except Exception as e:
        # print(f"DEBUG: Exception in A11Y_FORWARDER_APP: {e}")
        forest = None
        ui_elements = []
    else:
      # print("DEBUG: Using alternative method")
      forest = None
      ui_elements = self.get_ui_elements()
      # print(f"DEBUG: Got {len(ui_elements)} UI elements from alternative method")
    
    timestep.observation[OBSERVATION_KEY_FOREST] = forest
    timestep.observation[OBSERVATION_KEY_UI_ELEMENTS] = ui_elements
    # print(f"DEBUG: Final UI elements count: {len(ui_elements)}")
    return timestep

  def pull_file(
      self, remote_db_file_path: str, timeout_sec: Optional[float] = None
  ) -> contextlib._GeneratorContextManager[str]:
    """Pulls a file from the device to a temporary directory.

    The directory will be deleted when the context manager exits.
    Args:
      remote_db_file_path: The path to the file on the device.
      timeout_sec: Timeout in seconds for the adb calls.

    Returns:
      The path to the temporary directory containing the file.
    """
    remote_db_directory = os.path.dirname(remote_db_file_path)
    return file_utils.tmp_directory_from_device(
        remote_db_directory, self.env, timeout_sec
    )

  def push_file(
      self,
      local_db_file_path: str,
      remote_db_file_path: str,
      timeout_sec: Optional[float] = None,
  ) -> None:
    """Pushes a local file to the device."""

    remote_db_directory = os.path.dirname(remote_db_file_path)

    # First delete old .db, .db-wal, and .db-shm files.
    file_utils.clear_directory(remote_db_directory, self)
    file_utils.copy_data_to_device(
        local_db_file_path,
        remote_db_file_path,
        self.env,
        timeout_sec,
    )


def _write_default_task_proto() -> str:
  with open(_TASK_PATH, 'w') as f:
    f.write("""\
id: "default"

name: "Default task for device control."
description: "Empty task"

max_episode_sec: 7200  # Prevent infinite episodes.
  """)
  return _TASK_PATH


def get_controller(
    console_port: int = 5554,
    adb_path: str = DEFAULT_ADB_PATH,
    grpc_port: int = 8554,
) -> AndroidWorldController:
  """Creates a controller by connecting to an existing Android environment."""

  config = config_classes.AndroidEnvConfig(
      task=config_classes.FilesystemTaskConfig(
          path=_write_default_task_proto()
      ),
      simulator=config_classes.EmulatorConfig(
          emulator_launcher=config_classes.EmulatorLauncherConfig(
              emulator_console_port=console_port,
              adb_port=console_port + 1,
              grpc_port=grpc_port,
          ),
          adb_controller=config_classes.AdbControllerConfig(adb_path=adb_path),
      ),
  )
  android_env_instance = loader.load(config)
  logging.info('Setting up AndroidWorldController.')
  return AndroidWorldController(android_env_instance)
