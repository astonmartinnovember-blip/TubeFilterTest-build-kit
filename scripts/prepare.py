#!/usr/bin/env python3
"""Apply a small, inspectable identity patch to upstream NewPipe.

Playback stays in upstream code. This kit does not implement DNS filtering.
Run only against the upstream v0.29.1 checkout selected by the workflow.
"""
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE = 'io.github.tubefiltertest'
LABEL = 'TubeFilterTest'
ANDROID = '{http://schemas.android.com/apk/res/android}'


def prepare(root: Path) -> None:
    if not (root / 'LICENSE').is_file() or not (root / 'gradlew').is_file():
        raise RuntimeError('Expected a complete NewPipe source checkout.')
    app = root / 'app'
    candidates = [p for p in (app / 'build.gradle', app / 'build.gradle.kts') if p.is_file()]
    if len(candidates) != 1:
        raise RuntimeError('Could not resolve upstream app Gradle file.')
    gradle = candidates[0]
    text = gradle.read_text(encoding='utf-8')
    # Set the Android DSL value after upstream configuration. The upstream ID
    # may be held in a variable/version catalog rather than a string literal.
    # Keep Java/Kotlin packages and namespace intact. This syntax works in
    # both Groovy and Kotlin Gradle files; flavor/debug suffixes remain active.
    text += '\n// TubeFilterTest prototype application identity\n'
    text += 'android {\n    defaultConfig {\n'
    text += f'        applicationId = "{PACKAGE}"\n'
    text += '    }\n}\n'
    gradle.write_text(text, encoding='utf-8')

    # Change app_name resource values, including localized names. Leave credits intact.
    resource_count = 0
    name_pattern = r'(<string\b[^>]*\bname=[\"\']app_name[\"\'][^>]*>).*?(</string>)'
    for file in (app / 'src').rglob('*.xml'):
        if not file.parent.name.startswith('values'):
            continue
        original = file.read_text(encoding='utf-8')
        changed, n = re.subn(name_pattern, lambda m: m[1] + LABEL + m[2], original, flags=re.S)
        if n:
            file.write_text(changed, encoding='utf-8')
            resource_count += n

    # A dedicated manifest resource avoids flavor-specific upstream app labels/icons.
    res = app / 'src/main/res'
    (res / 'values').mkdir(parents=True, exist_ok=True)
    (res / 'drawable').mkdir(parents=True, exist_ok=True)
    (res / 'values/tubefiltertest.xml').write_text(
        '<resources><string name="tubefiltertest_name" translatable="false">'
        + LABEL + '</string></resources>\n', encoding='utf-8')
    (res / 'drawable/tubefiltertest_icon.xml').write_text('''<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#202338" android:pathData="M0,0h108v108h-108z"/>
    <path android:fillColor="#8176F5" android:pathData="M20,23h68v62h-68z"/>
    <path android:fillColor="#FFFFFF" android:pathData="M44,37l26,17l-26,17z"/>
</vector>\n''', encoding='utf-8')

    manifest_count = 0
    for manifest in (app / 'src').rglob('AndroidManifest.xml'):
        original = manifest.read_text(encoding='utf-8')
        # Patch application attributes in place to preserve XML namespace prefixes.
        def patch_application(match: re.Match) -> str:
            nonlocal manifest_count
            element = match[0]
            for attr, value in (
                ('label', '@string/tubefiltertest_name'),
                ('icon', '@drawable/tubefiltertest_icon'),
                ('roundIcon', '@drawable/tubefiltertest_icon'),
            ):
                expr = rf'android:{attr}\s*=\s*([\"\']).*?\1'
                if re.search(expr, element, flags=re.S):
                    element = re.sub(expr, f'android:{attr}="{value}"', element, flags=re.S)
                elif attr != 'roundIcon':
                    ending = '/>' if element.endswith('/>') else '>'
                    element = element[:-len(ending)] + f' android:{attr}="{value}"' + ending
            manifest_count += 1
            return element
        changed = re.sub(r'<application\b[^>]*>', patch_application, original, flags=re.S)
        if changed != original:
            ET.fromstring(changed)
            manifest.write_text(changed, encoding='utf-8')
    if manifest_count == 0:
        raise RuntimeError('No application manifest found.')
    print(f'Prepared {LABEL}: {PACKAGE}; {resource_count} app names; {manifest_count} manifests.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: prepare.py UPSTREAM_DIRECTORY')
    prepare(Path(sys.argv[1]).resolve())
