JEEV MARK I — PROTECTED CREATOR IDENTITY

Files:
  main.py
  speech_performance.py
  identity/__init__.py
  identity/identity_lock.py
  identity/identity.json
  requirements_identity_lock.txt

INSTALL
1. Copy main.py over the current JEEV main.py.
2. Copy speech_performance.py into the project root if you are using the vocal-performance layer.
3. Copy the complete identity folder into the project root.
4. Install the dependency:
   .venv\Scripts\python.exe -m pip install -r requirements_identity_lock.txt
5. Start JEEV normally.

PROTECTION
- identity.json is signed with Ed25519.
- The public verification key is embedded in identity_lock.py.
- The canonical creator is Sanjay Adhityan.
- Any edit/removal/corruption of the signed identity manifest causes startup to abort.
- A watchdog rechecks the identity while JEEV is running and requests shutdown on tampering.
- Creator questions are answered locally from the verified identity instead of relying on Gemini.
- prompt.txt, memory, personality, plugins, and conversation cannot override the protected identity at runtime.

GITHUB
Commit identity/identity.json, identity/identity_lock.py, identity/__init__.py and main.py.
Do NOT commit any private signing key. This release intentionally does not contain one.

IMPORTANT LIMITATION
Anyone who owns the complete source can theoretically modify the verifier itself and remove the security check. No Python-only protection can prevent that against a person with unrestricted source and machine access. The signed manifest does prevent a normal identity.json customization from silently working. For stronger release protection, distribute a signed executable/build with the verifier outside the editable source tree.
