import ast
import os

os.chdir(r'C:\Users\matan_hxko5r8\Documents\Remote Coding\MatMeet')

files = [
    'Client/Devices/Camera.py',
    'Client/Devices/AudioOutputDevice.py',
    'Client/Logic/callParticipant.py',
    'Client/Logic/Host.py',
    'Client/Comms/videoComm.py',
    'Client/Comms/ClientServerComm.py',
    'Client/GUI/call_frame.py'
]

has_errors = False
print("=" * 60)
print("PYTHON SYNTAX CHECK")
print("=" * 60)

for file in files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        print(f"✓ {file:<45} OK")
    except SyntaxError as e:
        print(f"✗ {file:<45} SYNTAX ERROR")
        print(f"  Line {e.lineno}: {e.msg}")
        if e.text:
            print(f"  {e.text.strip()}")
        has_errors = True
    except FileNotFoundError:
        print(f"✗ {file:<45} FILE NOT FOUND")
        has_errors = True
    except Exception as e:
        print(f"✗ {file:<45} ERROR: {type(e).__name__}: {e}")
        has_errors = True

print("=" * 60)
if not has_errors:
    print("Result: All files passed syntax check! ✓")
else:
    print("Result: Some files have errors ✗")
print("=" * 60)
