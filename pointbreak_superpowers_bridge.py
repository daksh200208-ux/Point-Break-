"""
Point Break Superpowers Bridge - Tier 2 Software Factory
=========================================================
Connects Point Break (voice assistant) to the Autonomous Engineering engine
equipped with software development tools for autonomous, test-driven
software engineering from voice commands.

Usage:
    from pointbreak_superpowers_bridge import superpowers_factory
    superpowers_factory.dispatch_engineering_task('build a flask todo app', speak_fn, update_status_fn)
    status = superpowers_factory.get_project_status()
"""

import os
import re
import sys
import json
import time
import shutil
import threading
import subprocess
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List

# --- Configuration ---
AGY_EXE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'agy', 'bin', 'agy.exe')
PROJECTS_ROOT = os.path.join(os.path.expanduser('~'), 'PointBreak_Projects')

# Superpowers-enhanced system prompt prefix injected into every agy dispatch
SUPERPOWERS_PREAMBLE = (
    'You are an autonomous software engineer with full control of the project directory. '
    'Follow the Test-Driven Development (TDD) methodology: '
    '1) Write failing tests first (Red). '
    '2) Write minimal code to pass all tests (Green). '
    '3) Refactor for clean architecture. '
    '4) Run all tests and ensure 100% pass rate before declaring completion. '
    'Always create a README.md summarizing the project. '
    'When done, create a file called DONE.txt with the text COMPLETED on the first line.\n\n'
)

# Maximum concurrent projects
MAX_CONCURRENT_PROJECTS = 3


class SuperpowersFactory:
    """
    Autonomous Project Dispatcher connecting Point Break voice commands
    to agy.exe with obra/superpowers for full-cycle software engineering.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active_projects: Dict[str, Dict[str, Any]] = {}
        os.makedirs(PROJECTS_ROOT, exist_ok=True)

    # -- Utility --

    @staticmethod
    def _slugify(goal: str) -> str:
        """Convert a natural language goal into a filesystem-safe project slug."""
        clean = re.sub(
            r'^(?:build|create|develop|engineer|code|make|design)\s+(?:a\s+|an\s+|the\s+)?',
            '', goal.lower().strip(), flags=re.I
        )
        slug = re.sub(r'[^a-z0-9\s]', '', clean).strip()
        slug = re.sub(r'\s+', '_', slug)
        slug = slug[:48] if slug else 'project'
        ts = datetime.now().strftime('%m%d_%H%M')
        return f'{slug}_{ts}'

    @staticmethod
    def _is_agy_available() -> bool:
        """Check if agy.exe is installed and accessible."""
        if os.path.isfile(AGY_EXE):
            return True
        return shutil.which('agy') is not None

    def _get_agy_path(self) -> str:
        """Resolve the agy executable path."""
        if os.path.isfile(AGY_EXE):
            return AGY_EXE
        found = shutil.which('agy')
        if found:
            return found
        raise FileNotFoundError(
            f'agy.exe not found at {AGY_EXE} or on PATH. '
            'Install with: winget install google.agy'
        )

    # -- Core Dispatch --

    def dispatch_engineering_task(
        self,
        goal: str,
        speak_fn: Optional[Callable[[str], None]] = None,
        update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Dispatches an autonomous software engineering task to agy.exe.
        1. Creates isolated project directory.
        2. Spawns agy in background with superpowers prompt.
        3. Monitors for DONE.txt completion marker.
        4. Announces completion via speak_fn.
        Returns dict with project_id, project_dir, status.
        """

        if not self._is_agy_available():
            err = 'Autonomous engineering engine is not configured. Cannot dispatch software engineering task.'
            if speak_fn:
                speak_fn(err)
            return {'success': False, 'error': err}

        with self._lock:
            active_count = sum(
                1 for p in self._active_projects.values()
                if p.get('status') == 'running'
            )
        if active_count >= MAX_CONCURRENT_PROJECTS:
            msg = f'Already running {active_count} engineering projects. Please wait for one to finish.'
            if speak_fn:
                speak_fn(msg)
            return {'success': False, 'error': msg}

        project_slug = self._slugify(goal)
        project_dir = os.path.join(PROJECTS_ROOT, project_slug)
        os.makedirs(project_dir, exist_ok=True)

        spec_path = os.path.join(project_dir, 'PROJECT_SPEC.md')
        with open(spec_path, 'w', encoding='utf-8') as f:
            f.write('# Project Specification\n\n')
            f.write(f'**Goal**: {goal}\n\n')
            f.write(f'**Created**: {datetime.now().isoformat()}\n\n')
            f.write('**Requested by**: Daksh (via Point Break voice command)\n')

        agy_path = self._get_agy_path()
        full_prompt = SUPERPOWERS_PREAMBLE + f'PROJECT GOAL: {goal}'

        cmd = [
            agy_path,
            '--print',
            '--add-dir', project_dir,
            '--dangerously-skip-permissions',
            '--print-timeout', '30m0s',
            full_prompt
        ]

        project_id = project_slug
        status_file = os.path.join(project_dir, 'engineering_status.json')
        log_file = os.path.join(project_dir, 'agy_output.log')

        project_info = {
            'project_id': project_id,
            'goal': goal,
            'project_dir': project_dir,
            'status': 'launching',
            'phase': 'init',
            'started_at': datetime.now().isoformat(),
            'completed_at': None,
            'log_file': log_file,
            'status_file': status_file,
            'process': None,
            'exit_code': None,
        }

        self._write_status(status_file, project_info)

        with self._lock:
            self._active_projects[project_id] = project_info

        if speak_fn:
            speak_fn(f'Dispatching engineering task: {goal}. Project directory created. Engineering engine spinning up now, sir.')

        if update_status_fn:
            update_status_fn({
                'type': 'superpowers',
                'project_id': project_id,
                'status': 'launching',
                'goal': goal
            })

        monitor_thread = threading.Thread(
            target=self._run_and_monitor,
            args=(cmd, project_id, project_dir, log_file, status_file, speak_fn, update_status_fn),
            daemon=True,
            name=f'superpowers-{project_id}'
        )
        monitor_thread.start()

        return {
            'success': True,
            'project_id': project_id,
            'project_dir': project_dir,
            'status': 'launched'
        }

    def _run_and_monitor(
        self,
        cmd: List[str],
        project_id: str,
        project_dir: str,
        log_file: str,
        status_file: str,
        speak_fn: Optional[Callable[[str], None]],
        update_status_fn: Optional[Callable[[Dict[str, Any]], None]]
    ):
        """Background thread: runs agy process, monitors output, detects completion."""

        print(f'[Superpowers] Launching agy for project {project_id}...')

        try:
            with open(log_file, 'w', encoding='utf-8') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=project_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    env={**os.environ, 'TERM': 'dumb'}
                )

            with self._lock:
                if project_id in self._active_projects:
                    self._active_projects[project_id]['process'] = process
                    self._active_projects[project_id]['status'] = 'running'
                    self._active_projects[project_id]['phase'] = 'engineering'

            self._write_status(status_file, self._active_projects.get(project_id, {}))

            if update_status_fn:
                update_status_fn({
                    'type': 'superpowers',
                    'project_id': project_id,
                    'status': 'running',
                    'phase': 'engineering'
                })

            try:
                exit_code = process.wait(timeout=2100)
            except subprocess.TimeoutExpired:
                print(f'[Superpowers] Project {project_id} timed out after 35 minutes. Terminating.')
                process.kill()
                exit_code = -1

            done_file = os.path.join(project_dir, 'DONE.txt')
            is_done = os.path.isfile(done_file)

            generated_files = []
            for root, dirs, files in os.walk(project_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                for fname in files:
                    if fname not in ('agy_output.log', 'engineering_status.json', 'PROJECT_SPEC.md'):
                        generated_files.append(os.path.relpath(os.path.join(root, fname), project_dir))

            if exit_code == 0 and is_done:
                final_status = 'completed'
                phase = 'done'
            elif exit_code == 0:
                final_status = 'completed_no_marker'
                phase = 'review_needed'
            elif exit_code == -1:
                final_status = 'timed_out'
                phase = 'aborted'
            else:
                final_status = 'failed'
                phase = 'error'

            with self._lock:
                if project_id in self._active_projects:
                    self._active_projects[project_id].update({
                        'status': final_status,
                        'phase': phase,
                        'exit_code': exit_code,
                        'completed_at': datetime.now().isoformat(),
                        'files_generated': generated_files,
                        'file_count': len(generated_files),
                    })
                    info_copy = {k: v for k, v in self._active_projects[project_id].items() if k != 'process'}
                    self._write_status(status_file, info_copy)

            if final_status == 'completed':
                msg = f'Engineering task complete, sir! Project {project_id} finished successfully. {len(generated_files)} files generated including passing tests.'
                print(f'[Superpowers] {msg}')
                if speak_fn:
                    speak_fn(msg)
            elif final_status == 'completed_no_marker':
                msg = f'Engineering task for {project_id} finished but completion marker not found. {len(generated_files)} files generated. Might need review.'
                print(f'[Superpowers] {msg}')
                if speak_fn:
                    speak_fn(msg)
            elif final_status == 'timed_out':
                msg = f'Engineering task {project_id} timed out after 35 minutes, sir.'
                print(f'[Superpowers] {msg}')
                if speak_fn:
                    speak_fn(msg)
            else:
                msg = f'Engineering task {project_id} encountered an error. Exit code: {exit_code}.'
                print(f'[Superpowers] {msg}')
                if speak_fn:
                    speak_fn(msg)

            if update_status_fn:
                update_status_fn({
                    'type': 'superpowers',
                    'project_id': project_id,
                    'status': final_status,
                    'file_count': len(generated_files),
                })

        except Exception as e:
            err_msg = f'Superpowers dispatch error for {project_id}: {e}'
            print(f'[Superpowers] {err_msg}')
            with self._lock:
                if project_id in self._active_projects:
                    self._active_projects[project_id]['status'] = 'error'
                    self._active_projects[project_id]['error'] = str(e)
            if speak_fn:
                speak_fn(f'Engineering task failed with error: {e}')

    # -- Status and Telemetry --

    def get_project_status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of a specific project or the latest active one."""
        with self._lock:
            if not self._active_projects:
                return {'status': 'no_projects', 'message': 'No engineering projects are currently tracked.'}

            if project_id and project_id in self._active_projects:
                proj = self._active_projects[project_id]
                return self._format_status(proj)

            latest = None
            latest_time = ''
            for pid, proj in self._active_projects.items():
                started = proj.get('started_at', '')
                if started > latest_time:
                    latest_time = started
                    latest = proj

            if latest:
                return self._format_status(latest)

            return {'status': 'no_projects', 'message': 'No engineering projects found.'}

    def get_all_projects_status(self) -> List[Dict[str, Any]]:
        """Get status summary of all tracked projects."""
        with self._lock:
            return [self._format_status(p) for p in self._active_projects.values()]

    def _format_status(self, proj: Dict[str, Any]) -> Dict[str, Any]:
        """Format project info for voice/status reporting."""
        status = proj.get('status', 'unknown')
        goal = proj.get('goal', 'Unknown goal')
        project_id = proj.get('project_id', 'unknown')
        phase = proj.get('phase', 'unknown')
        file_count = proj.get('file_count', 0)
        project_dir = proj.get('project_dir', '')

        if status == 'running':
            elapsed = ''
            started = proj.get('started_at')
            if started:
                try:
                    start_dt = datetime.fromisoformat(started)
                    delta = datetime.now() - start_dt
                    mins = int(delta.total_seconds() // 60)
                    elapsed = f' Running for {mins} minute{"s" if mins != 1 else ""}.'
                except Exception:
                    pass
            message = f'Project {project_id} is actively running.{elapsed} Phase: {phase}.'
        elif status == 'completed':
            message = f'Project {project_id} completed successfully! {file_count} files generated with passing tests.'
        elif status == 'completed_no_marker':
            message = f'Project {project_id} finished but needs review. {file_count} files generated.'
        elif status == 'timed_out':
            message = f'Project {project_id} timed out.'
        elif status in ('failed', 'error'):
            message = f'Project {project_id} failed. Check logs for details.'
        elif status == 'launching':
            message = f'Project {project_id} is being set up. Engineering engine is spinning up.'
        else:
            message = f'Project {project_id} status: {status}.'

        return {
            'project_id': project_id,
            'goal': goal,
            'status': status,
            'phase': phase,
            'message': message,
            'file_count': file_count,
            'project_dir': project_dir,
        }

    def cancel_project(self, project_id: Optional[str] = None, speak_fn: Optional[Callable[[str], None]] = None) -> bool:
        """Cancel a running engineering project."""
        with self._lock:
            target = None
            if project_id and project_id in self._active_projects:
                target = self._active_projects[project_id]
            elif not project_id:
                for pid, proj in self._active_projects.items():
                    if proj.get('status') == 'running':
                        target = proj
                        project_id = pid

            if not target:
                if speak_fn:
                    speak_fn('No running engineering project found to cancel, sir.')
                return False

            process = target.get('process')
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

            target['status'] = 'cancelled'
            target['phase'] = 'aborted'
            target['completed_at'] = datetime.now().isoformat()

        if speak_fn:
            speak_fn(f'Engineering project {project_id} cancelled, sir.')
        print(f'[Superpowers] Project {project_id} cancelled.')
        return True

    # -- Status File I/O --

    @staticmethod
    def _write_status(status_file: str, info: Dict[str, Any]):
        """Write project status to JSON file for persistence."""
        try:
            clean = {}
            for k, v in info.items():
                if k == 'process':
                    continue
                try:
                    json.dumps(v)
                    clean[k] = v
                except (TypeError, ValueError):
                    clean[k] = str(v)

            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(clean, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f'[Superpowers] Warning: Could not write status file: {e}')

    def load_persisted_projects(self):
        """Scan PROJECTS_ROOT for existing project status files and reload them."""
        if not os.path.isdir(PROJECTS_ROOT):
            return

        for entry in os.listdir(PROJECTS_ROOT):
            proj_dir = os.path.join(PROJECTS_ROOT, entry)
            status_file = os.path.join(proj_dir, 'engineering_status.json')
            if os.path.isfile(status_file):
                try:
                    with open(status_file, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                    pid = info.get('project_id', entry)
                    with self._lock:
                        if pid not in self._active_projects:
                            self._active_projects[pid] = info
                except Exception:
                    pass


# --- Module-Level Singleton ---
superpowers_factory = SuperpowersFactory()

try:
    superpowers_factory.load_persisted_projects()
except Exception:
    pass
