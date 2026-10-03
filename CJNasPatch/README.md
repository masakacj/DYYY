# CJNasPatch

A small companion dylib for stock DYYY.

## Goal

Keep the original `DYYY.dylib` untouched and inject `CJNasPatch.dylib` alongside it.

The patch uses Objective-C runtime hooks and dynamic symbol lookup, so it does not bundle or duplicate DYYY classes.

## Compatibility target

Initial target: DYYY 2.3-0 #19, arm64/arm64e.

## Build

Built only by GitHub Actions. The repository workflow publishes a standalone `CJNasPatch.dylib` in the `cjnas-latest` release.
