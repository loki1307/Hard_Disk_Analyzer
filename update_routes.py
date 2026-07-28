import os

files_to_update = [
    'diskguardian/services/monitor_service.py',
    'diskguardian/dashboard/routes.py',
    'diskguardian/api/routes.py',
    'diskguardian/admin/routes.py',
    'diskguardian/auth/routes.py'
]

for file_path in files_to_update:
    if not os.path.exists(file_path):
        continue
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements
    content = content.replace('ScanResult', 'ScanHistory')
    content = content.replace('SystemSnapshot', 'SystemLogs')
    content = content.replace('Alert', 'Notifications')
    content = content.replace('LoginEvent', 'Sessions')
    
    # Also update any relationships that might be accessed
    # e.g., user.scan_results -> user.scan_history
    content = content.replace('.scan_results', '.scan_history')
    content = content.replace('.snapshots', '.system_logs')
    content = content.replace('.alerts', '.notifications')
    content = content.replace('.login_events', '.sessions')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
print("Successfully updated references in routes and services.")
