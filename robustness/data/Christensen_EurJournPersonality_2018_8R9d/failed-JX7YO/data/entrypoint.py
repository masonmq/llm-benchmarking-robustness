import sys, runpy, os
# Ensure apt-installed Python packages (e.g., numpy) are on path for /usr/local python
apt_dist = '/usr/lib/python3/dist-packages'
if apt_dist not in sys.path and os.path.isdir(apt_dist):
    sys.path.append(apt_dist)

scripts = [
    '/workspace/data/Analysis_Scr1_OSF__py.py',
    '/workspace/data/Analysis_Scr2_OSF__py.py'
]

exit_code = 0
for script in scripts:
    try:
        runpy.run_path(script, run_name='__main__')
    except SystemExit as e:
        # Capture non-zero exits from scripts
        code = int(e.code) if isinstance(e.code, int) else 1
        exit_code = exit_code or code
    except Exception as e:
        # Print error and mark failure but continue to next to attempt both tasks
        import traceback
        traceback.print_exc()
        exit_code = exit_code or 1

sys.exit(exit_code)
