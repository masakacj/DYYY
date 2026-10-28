#!/usr/bin/env python3
"""Ensure JPEG imports retain downloaded bytes and other media routes still exist."""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
source = (root / "DYYYManager.m").read_text(encoding="utf-8")
start = source.find("+ (void)saveMedia:(NSURL *)mediaURL")
end = source.find("+ (void)downloadLivePhoto:", start)
assert 0 <= start < end, "Missing saveMedia implementation"
method = source[start:end]

jpeg = method.find('if (mediaType == MediaTypeImage &&')
heic = method.find('if (mediaType == MediaTypeHeic)')
assert 0 < jpeg < heic, "JPEG fast path must precede other format paths"
block = method[jpeg:heic]
for expected in (
    'mediaType == MediaTypeImage',
    'PHAssetCreationRequest *request',
    'options.originalFilename = originalFilename;',
    'options.shouldMoveFile = NO;',
    'addResourceWithType:PHAssetResourceTypePhoto fileURL:mediaURL options:options',
    'reportResult(success);',
    'return;',
):
    assert expected in block, f"JPEG branch missing {expected}"
assert 'imageWithContentsOfFile' not in block, "JPEG must not create UIImage"
assert 'creationRequestForAssetFromImage' not in block, "JPEG must not re-encode via UIImage"
for existing in (
    'if (mediaType == MediaTypeHeic)',
    'if (mediaType == MediaTypeVideo)',
    'requestAuthorization:',
    'finalizeDownloadWithFileURL:mediaURL',
):
    assert existing in method, f"Existing media path lost: {existing}"
assert ('PHAssetResourceTypeVideo' in method or
        'creationRequestForAssetFromVideoAtFileURL:' in method), "Video save path lost"
print("PASS: JPEG raw Photos resource path, cleanup and unaffected media branches")
