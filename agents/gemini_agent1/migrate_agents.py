import os
import re
import yaml

source_dir = r"D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat\agents\claude-code_agent1\.claude\agents"
target_dir = r"D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat\agents\gemini_agent1\.gemini\agents"

if not os.path.exists(target_dir):
    os.makedirs(target_dir)

files = [f for f in os.listdir(source_dir) if f.endswith('.md')]

def migrate_agent(filename):
    path = os.path.join(source_dir, filename)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract existing frontmatter
    body = content
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    title = ""
    if match:
        fm_text = match.group(1)
        body = match.group(2)
        try:
            fm = yaml.safe_load(fm_text)
            title = fm.get('title', '').replace('🤖 ', '').replace('👤 ', '')
        except:
            pass
            
    if not title:
        title = filename.replace('.md', '').replace('-', ' ').title()

    # Extract description from Purpose section
    description = ""
    purpose_match = re.search(r'#+\s*Purpose\s*\n+(.*)', body, re.IGNORECASE)
    if purpose_match:
        description = purpose_match.group(1).strip().split('\n')[0]
    
    if not description:
        # Try Identity section
        id_match = re.search(r'#+\s*Identity.*?\n+(.*)', body, re.IGNORECASE)
        if id_match:
            description = id_match.group(1).strip().split('\n')[0]

    if not description:
        description = f"Specialist agent: {title}"

    # Gemini specific fields
    gemini_fm = {
        'name': filename.replace('.md', '').lower(),
        'description': description,
        'kind': 'local',
        'tools': ['*']
    }
    
    new_fm_text = yaml.dump(gemini_fm, sort_keys=False)
    new_content = f"---\n{new_fm_text}---\n\n{body}"
    
    target_path = os.path.join(target_dir, filename)
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return gemini_fm['name']

for f in files:
    try:
        agent_name = migrate_agent(f)
        print(f"Migrated {f} as {agent_name}")
    except Exception as e:
        print(f"Error migrating {f}: {e}")
