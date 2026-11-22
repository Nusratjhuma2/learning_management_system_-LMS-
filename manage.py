#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # Auto-delegate to local .venv if invoked with system Python
    venv_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_py):
        venv_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'bin', 'python')

    if os.path.exists(venv_py) and os.path.realpath(sys.executable) != os.path.realpath(venv_py):
        import subprocess
        result = subprocess.run([venv_py] + sys.argv)
        sys.exit(result.returncode)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
