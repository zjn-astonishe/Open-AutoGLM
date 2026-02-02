#!/usr/bin/env python3
"""
Download DroidRun Portal APK to local directory.
"""
import sys
import shutil
from phone_agent.portal import download_portal_apk
from rich.console import Console

console = Console()

def main():
    output_path = "portal.apk"
    
    console.print("[bold green]Downloading Portal APK...[/bold green]")
    
    try:
        with download_portal_apk(debug=True) as temp_apk:
            # Copy the temporary APK to current directory
            shutil.copy2(temp_apk, output_path)
            console.print(f"\n[bold green]✓[/bold green] Portal APK downloaded successfully to: [bold]{output_path}[/bold]")
            return 0
    except Exception as e:
        console.print(f"\n[bold red]✗[/bold red] Failed to download Portal APK: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
