import os
import re

directories_to_scan = ['src', 'backend/app']

# Files we definitely DO NOT want to touch (to avoid breaking DB names, etc)
excluded_files = ['config.py']

def replace_in_file(filepath):
    if any(ex in filepath for ex in excluded_files):
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    content = content.replace("SprintPulse", "KPIMaster")
    content = content.replace("Sprintpulse", "Kpimaster")
    
    # We only replace lowercase 'sprintpulse' if it's not part of a db url or docker config
    # Actually, let's just stick to Capitalized because that's mostly what is in UI/Logs
    # Except for storageKey="sprintpulse-theme" in src/App.tsx
    content = content.replace("sprintpulse-theme", "kpimaster-theme")
    content = content.replace("sprintpulse.authToken", "kpimaster.authToken")
    content = content.replace("@sprintpulse.local", "@kpimaster.local")
    content = content.replace("sprintpulse.example.com", "kpimaster.example.com")
    content = content.replace("Sprint Tracker", "KPIMaster")
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for d in directories_to_scan:
    for root, dirs, files in os.walk(d):
        for f in files:
            if f.endswith(('.ts', '.tsx', '.py', '.md')):
                replace_in_file(os.path.join(root, f))
