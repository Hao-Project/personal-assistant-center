#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import threading
import glob
from datetime import datetime
from flask import Flask, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, 'tasks.json')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
STATUS_FILE = os.path.join(LOGS_DIR, 'status.json')

os.makedirs(LOGS_DIR, exist_ok=True)

# Clear any stale "running" states left from a previous server instance
if os.path.exists(STATUS_FILE):
    with open(STATUS_FILE) as _f:
        _status = json.load(_f)
    _changed = False
    for _tid, _s in _status.items():
        if _s.get('state') == 'running':
            _status[_tid]['state'] = 'done'
            _status[_tid]['success'] = False
            _changed = True
    if _changed:
        with open(STATUS_FILE, 'w') as _f:
            json.dump(_status, _f)

app = Flask(__name__, static_folder='static')

# In-memory map of task_id → running subprocess
running_processes = {}


def find_claude_binary():
    patterns = [
        os.path.expanduser('~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude'),
        os.path.expanduser('~/.cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude'),
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return 'claude'
    candidates.sort(reverse=True)
    return candidates[0]


def load_tasks():
    with open(TASKS_FILE) as f:
        return json.load(f)['tasks']


def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {}


def save_status(status):
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f)


def run_task(task):
    task_id = task['id']
    log_file = os.path.join(LOGS_DIR, f'{task_id}.log')

    status = load_status()
    status[task_id] = {
        'state': 'running',
        'started_at': datetime.now().isoformat(),
        'finished_at': None,
        'success': None,
    }
    save_status(status)

    try:
        if task['type'] == 'claude':
            claude_bin = find_claude_binary()
            cmd = [claude_bin, '-p', task['prompt'], '--output-format', 'text', '--dangerously-skip-permissions']
            # Load .mcp.json from the task's cwd if present
            task_cwd = task.get('cwd', BASE_DIR)
            mcp_config = os.path.join(task_cwd, '.mcp.json')
            if os.path.exists(mcp_config):
                cmd += ['--mcp-config', mcp_config]
        else:
            cmd = task['command'].split()

        with open(log_file, 'a') as log:
            log.write(f'\n{"=" * 60}\n')
            log.write(f'Run started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            log.write(f'{"=" * 60}\n')

            proc = subprocess.Popen(
                cmd,
                cwd=task.get('cwd'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            running_processes[task_id] = proc

            stdout, stderr = proc.communicate(timeout=600)
            running_processes.pop(task_id, None)

            if stdout:
                log.write(stdout)
            if stderr:
                log.write('\n[STDERR]\n')
                log.write(stderr)

            log.write(f'\n[Exit code: {proc.returncode}]\n')
            log.write(f'Finished: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')

        success = proc.returncode == 0

    except Exception as e:
        running_processes.pop(task_id, None)
        with open(log_file, 'a') as log:
            log.write(f'\n[ERROR] {str(e)}\n')
            log.write(f'Finished: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        success = False

    status = load_status()
    status[task_id] = {
        'state': 'done',
        'started_at': status.get(task_id, {}).get('started_at', datetime.now().isoformat()),
        'finished_at': datetime.now().isoformat(),
        'success': success,
    }
    save_status(status)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/tasks')
def get_tasks():
    tasks = load_tasks()
    status = load_status()
    for task in tasks:
        task['status'] = status.get(task['id'], {'state': 'idle', 'success': None, 'finished_at': None})
    return jsonify(tasks)


@app.route('/api/tasks/<task_id>/run', methods=['POST'])
def run_task_endpoint(task_id):
    tasks = load_tasks()
    task = next((t for t in tasks if t['id'] == task_id), None)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    status = load_status()
    if status.get(task_id, {}).get('state') == 'running':
        return jsonify({'error': 'Task already running'}), 409

    thread = threading.Thread(target=run_task, args=(task,))
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'started'})


@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
def stop_task_endpoint(task_id):
    proc = running_processes.get(task_id)
    if not proc:
        return jsonify({'error': 'Task not running'}), 409
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    return jsonify({'status': 'stopped'})


@app.route('/api/tasks/<task_id>/status')
def get_task_status(task_id):
    status = load_status()
    return jsonify(status.get(task_id, {'state': 'idle'}))


@app.route('/api/tasks/<task_id>/log')
def get_log(task_id):
    log_file = os.path.join(LOGS_DIR, f'{task_id}.log')
    if not os.path.exists(log_file):
        return jsonify({'log': 'No log available yet.'})
    with open(log_file) as f:
        return jsonify({'log': f.read()})


if __name__ == '__main__':
    print('Personal Assistant Center running at http://localhost:5000')
    app.run(port=5000, debug=False)
