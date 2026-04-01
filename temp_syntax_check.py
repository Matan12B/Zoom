import ast
import os

os.chdir(r'C:\Users\matan_hxko5r8\Documents\Remote Coding\MatMeet')

files = [
    'Client/Comms/audioComm.py',
    'Client/Comms/videoComm.py',
    'Client/Logic/av_sync.py',
    'Client/Logic/callParticipant.py'
]

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
    except FileNotFoundError:
        print(f"✗ {file:<45} FILE NOT FOUND")
    except Exception as e:
        print(f"✗ {file:<45} ERROR: {type(e).__name__}: {e}")

print("=" * 60)
