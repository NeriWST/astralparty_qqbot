"""Offline deployment checks. Prints no tokens, openids, URLs or message bodies."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def environment_status(environment):
    base = environment.get('CARD_BASE_URL', '').strip()
    try:
        parsed = urlsplit(base)
        valid_url = parsed.scheme in ('http', 'https') and bool(parsed.hostname)
    except ValueError:
        valid_url = False
    return {'CARD_BASE_URL': 'set' if base else 'unset',
            'card_url_valid': valid_url if base else None,
            'QQ_APPID': 'set' if environment.get('QQ_APPID') else 'unset',
            'QQ_SECRET': 'set' if environment.get('QQ_SECRET') else 'unset'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', help='systemd unit name, e.g. astral-bot')
    args = parser.parse_args()
    print('diagnostic_project=' + str(ROOT))
    try:
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'],
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'unknown'
    print('checkout_commit=' + commit)
    if args.service:
        try:
            pid = subprocess.check_output(['systemctl', 'show', args.service, '-p', 'MainPID', '--value'],
                                          text=True, stderr=subprocess.DEVNULL).strip()
            if not pid.isdigit() or int(pid) <= 0:
                raise RuntimeError('service_not_running')
            root = Path('/proc') / pid
            entries = (root / 'environ').read_bytes().decode('utf-8', errors='replace').split('\0')
            env = dict(entry.split('=', 1) for entry in entries if '=' in entry)
            print('service_pid=' + pid)
            print('service_cwd=' + str((root / 'cwd').resolve(strict=True)))
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print('service_probe_failed=' + type(error).__name__ + '; 请用 sudo 运行，并确认服务名称')
            return 1
    else:
        env = os.environ
        print('environment_source=current_shell (not the systemd service)')
    print(json.dumps(environment_status(env), ensure_ascii=False))
    try:
        print('qq-botpy=' + importlib.metadata.version('qq-botpy'))
    except importlib.metadata.PackageNotFoundError:
        print('qq-botpy=missing_in_this_python')
    try:
        import bot_viz
        print('fonts=' + bot_viz.font_status())
        from stats_report import build_report
        png = bot_viz.render_report_png(build_report(
            {'nick': '本地诊断', 'uid': 0}, [{'hero': '芬妮', 'mode_id': 2, 'rank': 1}]))
        print('render_probe=ok; png_bytes=' + str(len(png)))
    except Exception as error:
        print('render_probe=failed; ' + type(error).__name__)
    print('No QQ/game requests were made. Fonts/SDK checks use this Python, not the service interpreter.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
