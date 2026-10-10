#!/usr/bin/env python3
"""GUAP CLI - Command line interface for GUAP university personal cabinet.

This is an autonomous CLI tool that doesn't require MCP server.
Users can choose between MCP server or CLI+skill mode.

Usage:
    guap pro auth              Authenticate via browser
    guap pro tasks             List all tasks
    guap pro task <id>         Get task details
    guap pro materials         List materials
    guap pro profile           Show my profile
    guap pro check             Check authentication status
    guap skill                 Show skill/instructions for AI assistants
"""

import argparse
import asyncio
import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Optional

# Import our modules
try:
    from . import guap_client as gc
    from . import auth as guap_auth
    from . import session_cookies
except ImportError:
    import guap_client as gc
    import auth as guap_auth
    import session_cookies


def output_json(data):
    """Output data as JSON."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def output_csv(data, headers, rows):
    """Output data as CSV.
    
    Args:
        data: The data object (for single item) or list of items
        headers: List of column headers
        rows: List of row data (list of lists or list of dicts)
    """
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(h, '') for h in headers])
        else:
            writer.writerow(row)
    print(output.getvalue())


def get_cookie():
    """Get cookie from file or raise error."""
    # Try auth module first
    cookie = session_cookies.configured()
    if cookie and cookie.cookies.jar:
        return cookie
    
    raise RuntimeError(
        "Not authenticated. Run 'guap pro auth' first or set GUAP_COOKIE environment variable."
    )


def cmd_auth(args):
    """Authenticate via browser."""
    print("🔐 Starting browser authentication...")
    print("A browser window will open. Please log in to pro.guap.ru")
    print("=" * 60)
    
    result = asyncio.run(guap_auth.authenticate_with_browser(timeout=args.timeout))
    
    if result.get("success"):
        print("\n" + "=" * 60)
        print("✅ Authentication successful!")
        print(f"Cookies saved to: {result.get('save_path')}")
        print(f"Total cookies: {len(result.get('cookies', []))}")
        return 0
    else:
        print("\n" + "=" * 60)
        print(f"❌ Authentication failed: {result.get('error')}")
        return 1


def cmd_check(args):
    """Check authentication status."""
    result = asyncio.run(guap_auth.check_auth())
    
    if result.get("valid"):
        print("✅ Authentication valid")
        print(f"   Status code: {result.get('status_code')}")
        print(f"   URL: {result.get('url')}")
    else:
        print("❌ Authentication invalid")
        print(f"   Error: {result.get('error')}")
    
    return 0 if result.get("valid") else 1


def cmd_tasks(args):
    """List tasks."""
    try:
        cookie = get_cookie()
        tasks = gc.get_tasks(
            cookie,
            semester=args.semester,
            subject=args.subject,
            task_type=args.type,
            show_status=args.status,
        )
        
        if not tasks:
            if args.format == "json":
                output_json([])
            else:
                print("No tasks found.")
            return 0
        
        # JSON output
        if args.format == "json":
            data = []
            for t in tasks:
                data.append({
                    "id": t.task_id,
                    "subject": t.discipline,
                    "name": t.name,
                    "type": t.task_type,
                    "status": t.status or None,
                    "points_earned": t.points_earned,
                    "points_max": t.points_max,
                    "deadline": t.deadline,
                    "teacher": t.teacher,
                })
            output_json(data)
            return 0
        
        # CSV output
        if args.format == "csv":
            headers = ["id", "subject", "name", "type", "status", "points_earned", "points_max", "deadline", "teacher"]
            rows = []
            for t in tasks:
                rows.append({
                    "id": t.task_id,
                    "subject": t.discipline,
                    "name": t.name,
                    "type": t.task_type,
                    "status": t.status or "",
                    "points_earned": t.points_earned or "",
                    "points_max": t.points_max or "",
                    "deadline": t.deadline or "",
                    "teacher": t.teacher or "",
                })
            output_csv(tasks, headers, rows)
            return 0
        
        # Table output (default)
        print(f"\n📋 Tasks ({len(tasks)} total):\n")
        print(f"{'ID':<10} {'Subject':<30} {'Name':<40} {'Status':<15} {'Points':<10} {'Deadline':<12}")
        print("-" * 120)
        
        for t in tasks:
            status = t.status or "не сдано"
            points = f"{t.points_earned or '0'}/{t.points_max or '?'}"
            deadline = t.deadline or "N/A"
            subject = t.discipline[:28] + ".." if len(t.discipline) > 30 else t.discipline
            name = t.name[:38] + ".." if len(t.name) > 40 else t.name
            
            print(f"{t.task_id:<10} {subject:<30} {name:<40} {status:<15} {points:<10} {deadline:<12}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_task(args):
    """Get task details."""
    try:
        cookie = get_cookie()
        task = gc.get_task(cookie, int(args.id))
        
        # JSON output
        if args.format == "json":
            data = {
                "id": task.task_id,
                "name": task.name,
                "subject": task.discipline,
                "type": task.task_type,
                "semester": task.semester,
                "teacher": task.teacher,
                "points_max": task.points_max,
                "deadline": task.deadline,
                "description": task.description,
                "allowed_extensions": task.allowed_extensions,
                "extra_materials": task.extra_materials,
                "reports": task.reports,
            }
            output_json(data)
            return 0
        
        # Table output (default)
        print(f"\n📄 Task #{task.task_id}: {task.name}\n")
        print(f"Subject:    {task.discipline}")
        print(f"Type:       {task.task_type}")
        print(f"Semester:   {task.semester}")
        print(f"Teacher:    {task.teacher}")
        print(f"Max points: {task.points_max or 'N/A'}")
        print(f"Deadline:   {task.deadline or 'Not specified'}")
        print(f"\nDescription:\n{task.description}\n")
        
        if task.allowed_extensions:
            print(f"Allowed file types: {task.allowed_extensions}")
        
        if task.extra_materials:
            print(f"\n📎 Extra materials:")
            for m in task.extra_materials:
                print(f"  - {m['text']}: {m['url']}")
        
        if task.reports:
            print(f"\n📝 Submitted reports:")
            for r in task.reports:
                print(f"  - Status: {r['status']}")
                print(f"    Uploaded: {r['uploaded_at']}")
                if r.get('student_comment'):
                    print(f"    Comment: {r['student_comment']}")
        else:
            print("\n📝 No reports submitted yet.")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_materials(args):
    """List materials."""
    try:
        cookie = get_cookie()
        materials = gc.get_materials(cookie, semester=args.semester, subject=args.subject)
        
        if not materials:
            if args.format == "json":
                output_json([])
            else:
                print("No materials found.")
            return 0
        
        # JSON output
        if args.format == "json":
            data = []
            for m in materials:
                data.append({
                    "name": m.name,
                    "subject": m.discipline,
                    "teacher": m.teacher,
                    "added_at": m.added_at,
                    "download_url": m.download_url,
                    "external_url": m.external_url,
                })
            output_json(data)
            return 0
        
        # CSV output
        if args.format == "csv":
            headers = ["name", "subject", "teacher", "added_at", "url"]
            rows = []
            for m in materials:
                url = m.download_url or m.external_url or ""
                rows.append({
                    "name": m.name,
                    "subject": m.discipline,
                    "teacher": m.teacher,
                    "added_at": m.added_at,
                    "url": url,
                })
            output_csv(materials, headers, rows)
            return 0
        
        # Table output (default)
        print(f"\n📚 Materials ({len(materials)} total):\n")
        print(f"{'Subject':<30} {'Name':<50} {'Teacher':<25} {'Added':<12}")
        print("-" * 120)
        
        for m in materials:
            subject = m.discipline[:28] + ".." if len(m.discipline) > 30 else m.discipline
            name = m.name[:48] + ".." if len(m.name) > 50 else m.name
            teacher = m.teacher[:23] + ".." if len(m.teacher) > 25 else m.teacher
            
            print(f"{subject:<30} {name:<50} {teacher:<25} {m.added_at:<12}")
            
            if args.urls:
                url = m.download_url or m.external_url or "N/A"
                print(f"  ↳ {url}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_profile(args):
    """Show user profile."""
    try:
        cookie = get_cookie()
        profile = gc.get_profile(cookie)
        
        # JSON output
        if args.format == "json":
            data = {
                "full_name": profile.full_name,
                "group": profile.group,
                "student_id": profile.student_id,
                "institute": profile.institute,
                "specialty": profile.specialty,
                "study_form": profile.study_form,
                "education_level": profile.education_level,
                "status": profile.status,
            }
            output_json(data)
            return 0
        
        # Table output (default)
        print(f"\n👤 Profile:\n")
        print(f"Name:           {profile.full_name}")
        print(f"Group:          {profile.group}")
        print(f"Student ID:     {profile.student_id}")
        if profile.institute:
            print(f"Institute:      {profile.institute}")
        if profile.specialty:
            print(f"Specialty:      {profile.specialty}")
        if profile.study_form:
            print(f"Study form:     {profile.study_form}")
        if profile.education_level:
            print(f"Education:      {profile.education_level}")
        if profile.status:
            print(f"Status:         {profile.status}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_skill(args):
    """Install GUAP skill to agents/skills/guap/ directory."""
    import shutil
    
    # Source skill directory (bundled with package)
    source_dir = Path(__file__).parent / "skill"
    
    # Target directory (agents/skills/guap/)
    if args.path:
        target_dir = Path(args.path) / "guap"
    else:
        # Default: look for agents/skills/ in current directory or home
        cwd_skills = Path.cwd() / "agents" / "skills"
        home_skills = Path.home() / "agents" / "skills"
        
        if cwd_skills.parent.exists():
            target_dir = cwd_skills / "guap"
        else:
            target_dir = home_skills / "guap"
    
    print("=" * 60)
    print("🔧 Installing GUAP Agent Skill")
    print("=" * 60)
    print(f"\nSource: {source_dir}")
    print(f"Target: {target_dir}")
    
    if not source_dir.exists():
        print(f"\n❌ Error: Skill directory not found at {source_dir}")
        return 1
    
    try:
        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy skill files
        for item in source_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, target_dir)
                print(f"  ✓ {item.name}")
            elif item.is_dir():
                dest = target_dir / item.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
                print(f"  ✓ {item.name}/")
        
        print(f"\n✅ Skill installed successfully!")
        print(f"\nLocation: {target_dir}")
        print(f"\nThe skill is now available to Agent Skills compatible clients.")
        print(f"\nTo use the skill:")
        print(f"  1. Ensure your agent supports Agent Skills")
        print(f"  2. The skill 'guap' will be auto-discovered")
        print(f"  3. Ask your agent to help with GUAP tasks")
        
        if not args.path:
            print(f"\nTo install to a custom location:")
            print(f"  guap skill --path /path/to/agents/skills")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Installation failed: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='guap',
        description='GUAP university personal cabinet CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  guap pro auth                    # Authenticate via browser
  guap pro tasks                   # List all tasks
  guap pro task 181395             # Get task details
  guap pro materials               # List materials
  guap pro profile                 # Show my profile
  guap skill                       # Install agent skill to agents/skills/

For MCP server mode, use: mcp-guap
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Pro commands
    pro_parser = subparsers.add_parser('pro', help='Pro.guap.ru commands')
    pro_subparsers = pro_parser.add_subparsers(dest='pro_command', help='Pro commands')
    
    # Auth
    auth_parser = pro_subparsers.add_parser('auth', help='Authenticate via browser')
    auth_parser.add_argument('--timeout', type=int, default=120, help='Authentication timeout (seconds)')
    auth_parser.set_defaults(func=cmd_auth)
    
    # Check
    check_parser = pro_subparsers.add_parser('check', help='Check authentication status')
    check_parser.set_defaults(func=cmd_check)
    
    # Tasks
    tasks_parser = pro_subparsers.add_parser('tasks', help='List tasks')
    tasks_parser.add_argument('--semester', type=int, help='Filter by semester ID')
    tasks_parser.add_argument('--subject', type=int, help='Filter by subject ID')
    tasks_parser.add_argument('--type', type=int, help='Filter by task type (1-16)')
    tasks_parser.add_argument('--status', type=int, help='Filter by status (0-5)')
    tasks_parser.add_argument('--format', choices=['table', 'json', 'csv'], default='table', help='Output format (default: table)')
    tasks_parser.set_defaults(func=cmd_tasks)
    
    # Task detail
    task_parser = pro_subparsers.add_parser('task', help='Get task details')
    task_parser.add_argument('id', help='Task ID')
    task_parser.add_argument('--format', choices=['table', 'json'], default='table', help='Output format (default: table)')
    task_parser.set_defaults(func=cmd_task)
    
    # Materials
    materials_parser = pro_subparsers.add_parser('materials', help='List materials')
    materials_parser.add_argument('--semester', type=int, help='Filter by semester ID')
    materials_parser.add_argument('--subject', type=int, help='Filter by subject ID')
    materials_parser.add_argument('--urls', action='store_true', help='Show download URLs')
    materials_parser.add_argument('--format', choices=['table', 'json', 'csv'], default='table', help='Output format (default: table)')
    materials_parser.set_defaults(func=cmd_materials)
    
    # Profile
    profile_parser = pro_subparsers.add_parser('profile', help='Show profile')
    profile_parser.add_argument('--format', choices=['table', 'json'], default='table', help='Output format (default: table)')
    profile_parser.set_defaults(func=cmd_profile)
    
    # Skill command
    skill_parser = subparsers.add_parser('skill', help='Install GUAP agent skill')
    skill_parser.add_argument('--path', type=str, help='Custom path to agents/skills/ directory')
    skill_parser.set_defaults(func=cmd_skill)
    
    # Parse args
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    if args.command == 'pro' and not args.pro_command:
        pro_parser.print_help()
        return 0
    
    # Execute command
    if hasattr(args, 'func'):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
