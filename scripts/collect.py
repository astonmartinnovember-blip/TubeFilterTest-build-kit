#!/usr/bin/env python3
"""Collect actual APK outputs; fail rather than publish an empty artifact."""
import shutil
import sys
from pathlib import Path

root, destination = map(Path, sys.argv[1:])
apks = sorted((root / 'app/build/outputs/apk').rglob('*.apk'))
if not apks:
    raise SystemExit('Build produced no APK. Inspect the Gradle log.')
destination.mkdir(parents=True, exist_ok=True)
for index, apk in enumerate(apks, 1):
    output = destination / f'TubeFilterTest-{index}-{apk.name}'
    shutil.copy2(apk, output)
    print(output.name)
