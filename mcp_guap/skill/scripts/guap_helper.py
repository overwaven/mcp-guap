#!/usr/bin/env python3
"""
GUAP Skill Helper Script

This script provides a programmatic interface for AI agents to interact
with the GUAP university personal cabinet.

Usage:
    python scripts/guap_helper.py auth [--timeout 120]
    python scripts/guap_helper.py check
    python scripts/guap_helper.py tasks [--status 1] [--subject ID]
    python scripts/guap_helper.py task <id>
    python scripts/guap_helper.py materials [--urls]
    python scripts/guap_helper.py profile
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import guap_client as gc
    import auth as guap_auth
    import session_cookies
except ImportError:
    print(json.dumps({"error": "Failed to import guap modules. Ensure mcp-guap is installed."}))
    sys.exit(1)


def get_cookie():
    """Get authentication cookie."""
    cookie = session_cookies.configured()
    if not cookie or not cookie.cookies.jar:
        raise RuntimeError("Not authenticated. Run 'auth' first.")
    return cookie


def cmd_auth(args):
    """Authenticate via browser."""
    result = asyncio.run(guap_auth.authenticate_with_browser(timeout=args.timeout))
    
    if result.get("success"):
        output = {
            "success": True,
            "message": "Authentication successful",
            "cookies_count": len(result.get("cookies", [])),
            "save_path": result.get("save_path"),
        }
    else:
        output = {
            "success": False,
            "error": result.get("error", "Unknown error"),
        }
    
    print(json.dumps(output, ensure_ascii=False))
    return 0 if result.get("success") else 1


def cmd_check(args):
    """Check authentication status."""
    result = asyncio.run(guap_auth.check_auth())
    
    output = {
        "valid": result.get("valid", False),
        "error": result.get("error") if not result.get("valid") else None,
        "details": result,
    }
    
    print(json.dumps(output, ensure_ascii=False))
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
        
        output = {
            "success": True,
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.task_id,
                    "discipline": t.discipline,
                    "discipline_id": t.discipline_id,
                    "name": t.name,
                    "status": t.status,
                    "points_earned": t.points_earned,
                    "points_max": t.points_max,
                    "type": t.task_type,
                    "deadline": t.deadline,
                    "updated_at": t.updated_at,
                    "teacher": t.teacher,
                    "teacher_id": t.teacher_id,
                }
                for t in tasks
            ]
        }
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def cmd_task(args):
    """Get task details."""
    try:
        cookie = get_cookie()
        t = gc.get_task(cookie, int(args.id))
        
        output = {
            "success": True,
            "task": {
                "id": t.task_id,
                "name": t.name,
                "discipline": t.discipline,
                "discipline_id": t.discipline_id,
                "type": t.task_type,
                "semester": t.semester,
                "teacher": t.teacher,
                "teacher_id": t.teacher_id,
                "points_max": t.points_max,
                "order_num": t.order_num,
                "added_at": t.added_at,
                "allowed_extensions": t.allowed_extensions,
                "deadline": t.deadline,
                "description": t.description,
                "extra_materials": t.extra_materials,
                "reports": t.reports,
            }
        }
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def cmd_materials(args):
    """List materials."""
    try:
        cookie = get_cookie()
        materials = gc.get_materials(cookie, semester=args.semester, subject=args.subject)
        
        output = {
            "success": True,
            "count": len(materials),
            "materials": [
                {
                    "name": m.name,
                    "discipline": m.discipline,
                    "discipline_id": m.discipline_id,
                    "added_at": m.added_at,
                    "teacher": m.teacher,
                    "teacher_id": m.teacher_id,
                    "download_url": m.download_url,
                    "external_url": m.external_url,
                    "is_external": bool(not m.download_url and m.external_url),
                }
                for m in materials
            ]
        }
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def cmd_profile(args):
    """Get user profile."""
    try:
        cookie = get_cookie()
        p = gc.get_profile(cookie)
        
        output = {
            "success": True,
            "profile": {
                "full_name": p.full_name,
                "group": p.group,
                "student_id": p.student_id,
                "institute": p.institute,
                "specialty": p.specialty,
                "direction": p.direction,
                "study_form": p.study_form,
                "education_level": p.education_level,
                "status": p.status,
            }
        }
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="GUAP Skill Helper - JSON API for AI agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Auth
    auth_parser = subparsers.add_parser("auth", help="Authenticate via browser")
    auth_parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    
    # Check
    subparsers.add_parser("check", help="Check authentication status")
    
    # Tasks
    tasks_parser = subparsers.add_parser("tasks", help="List tasks")
    tasks_parser.add_argument("--semester", type=int, help="Filter by semester ID")
    tasks_parser.add_argument("--subject", type=int, help="Filter by subject ID")
    tasks_parser.add_argument("--type", type=int, help="Filter by task type (1-16)")
    tasks_parser.add_argument("--status", type=int, help="Filter by status (0-5)")
    
    # Task detail
    task_parser = subparsers.add_parser("task", help="Get task details")
    task_parser.add_argument("id", help="Task ID")
    
    # Materials
    materials_parser = subparsers.add_parser("materials", help="List materials")
    materials_parser.add_argument("--semester", type=int, help="Filter by semester ID")
    materials_parser.add_argument("--subject", type=int, help="Filter by subject ID")
    
    # Profile
    subparsers.add_parser("profile", help="Get user profile")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Route to appropriate command
    commands = {
        "auth": cmd_auth,
        "check": cmd_check,
        "tasks": cmd_tasks,
        "task": cmd_task,
        "materials": cmd_materials,
        "profile": cmd_profile,
    }
    
    if args.command in commands:
        return commands[args.command](args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
