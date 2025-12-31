#!/usr/bin/env python3
"""
Script to update workflow JSON files to standardize action format.
Only Swipe actions should have direction and distance.
Only Type actions should have text.
All other actions should have these fields as null.
"""

import json
import os
from pathlib import Path


def update_action_format(action):
    """Update a single action to conform to the required format."""
    # Initialize the fields to null/None by default
    action.setdefault("direction", None)
    action.setdefault("distance", None)
    action.setdefault("text", None)
    
    # Set to null if not swipe/type
    if action.get("action_type") != "Swipe":
        action["direction"] = None
        action["distance"] = None
    else:
        # For Swipe actions, preserve existing values or keep as they are
        # If they were already set, don't change them
        pass  # Keep existing values or let them be as defined
    
    if action.get("action_type") != "Type":
        action["text"] = None
    else:
        # For Type actions, preserve existing text value
        pass  # Keep existing value or let it be as defined

    return action


def process_workflow_file(file_path):
    """Process a single workflow file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Process each workflow in the file
    for workflow in data:
        for path_item in workflow.get('path', []):
            if 'action' in path_item:
                path_item['action'] = update_action_format(path_item['action'])
    
    # Write back to file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    workflow_dir = Path("/home/zjn/Code/Agent/Open-AutoGLM/output/memory2/workflow")
    
    # Get all JSON files in the workflow directory
    json_files = list(workflow_dir.glob("*.json"))
    
    print(f"Processing {len(json_files)} workflow files...")
    
    for file_path in json_files:
        print(f"Processing {file_path.name}...")
        try:
            process_workflow_file(file_path)
            print(f"  ✓ Completed {file_path.name}")
        except Exception as e:
            print(f"  ✗ Error processing {file_path.name}: {str(e)}")
    
    print("Done!")


if __name__ == "__main__":
    main()