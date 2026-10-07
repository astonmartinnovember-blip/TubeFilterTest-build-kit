#!/usr/bin/env python3
"""Apply the TubeFilterTest identity and player-control patches to NewPipe.

Playback and double-tap seeking stay in upstream code. Navigation buttons
remain visible when controls are shown, and are disabled at queue boundaries.
This kit does not implement DNS filtering.
Run only against the upstream v0.29.1 checkout selected by the workflow.
"""
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE = 'io.github.tubefiltertest'
LABEL = 'TubeFilterTest'
ANDROID = '{http://schemas.android.com/apk/res/android}'


def patch_player_controls(app: Path) -> None:
    file = app / 'src/main/java/org/schabi/newpipe/player/ui/VideoPlayerUi.java'
    original = file.read_text(encoding='utf-8')
    marker = '// TubeFilterTest: visible queue navigation'
    if marker in original:
        return
    replacements = {
        'protected void showOrHideButtons()': '''    protected void showOrHideButtons() {
        // TubeFilterTest: visible queue navigation
        @Nullable final PlayQueue playQueue = player.getPlayQueue();
        final int count = playQueue == null ? 0 : playQueue.getStreams().size();
        final int index = playQueue == null ? -1 : playQueue.getIndex();
        final boolean hasCurrent = index >= 0 && index < count;
        final boolean canPrevious = hasCurrent && index > 0;
        final boolean canNext = hasCurrent && index + 1 < count;

        binding.playPreviousButton.setVisibility(View.VISIBLE);
        binding.playPreviousButton.setEnabled(canPrevious);
        binding.playPreviousButton.setFocusable(canPrevious);
        binding.playPreviousButton.setAlpha(canPrevious ? 1.0f : 0.35f);
        binding.playNextButton.setVisibility(View.VISIBLE);
        binding.playNextButton.setEnabled(canNext);
        binding.playNextButton.setFocusable(canNext);
        binding.playNextButton.setAlpha(canNext ? 1.0f : 0.35f);
    }''',
        'private void animatePlayButtons(final boolean show, final long duration)':
        '''    private void animatePlayButtons(final boolean show, final long duration) {
        animate(binding.playPauseButton, show, duration, AnimationType.SCALE_AND_ALPHA);

        // The parent still hides all controls during playback. Keep queue buttons
        // dimmed when unavailable, instead of animating their alpha back to 1.
        if (show) {
            binding.playPreviousButton.setScaleX(1.0f);
            binding.playPreviousButton.setScaleY(1.0f);
            binding.playNextButton.setScaleX(1.0f);
            binding.playNextButton.setScaleY(1.0f);
            showOrHideButtons();
        } else {
            binding.playPreviousButton.setVisibility(View.INVISIBLE);
            binding.playNextButton.setVisibility(View.INVISIBLE);
        }
    }''',
    }
    changed = original
    for signature, replacement in replacements.items():
        pattern = r'    ' + re.escape(signature) + r' \{.*?\n    \}'
        changed, count = re.subn(pattern, lambda _: replacement, changed, flags=re.S)
        if count != 1:
            raise RuntimeError(f'Unsupported player source: expected one {signature}.')
    file.write_text(changed, encoding='utf-8')
    print('Player navigation: always visible in controls; disabled at queue boundaries.')


def prepare(root: Path) -> None:
    if not (root / 'LICENSE').is_file() or not (root / 'gradlew').is_file():
        raise RuntimeError('Expected a complete NewPipe source checkout.')
    app = root / 'app'
    patch_player_controls(app)
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
